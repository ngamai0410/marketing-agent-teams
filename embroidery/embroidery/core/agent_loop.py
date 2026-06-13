"""
Core agentic loop — shared by every agent in the pipeline.

LLM provider and search engine are configured in config.yaml.
No provider-specific code lives here.

Usage:
    result = asyncio.run(run_agent(system, messages, tools, model_settings))
"""

import asyncio
from pathlib import Path

from embroidery.core.config import settings, ModelSettings
from embroidery.core.llm import get_provider, LLMProvider
from embroidery.core.logger import get_logger
from embroidery.core.reporter import get_reporter

_log = get_logger("agent_loop")

# Module-level singletons — instantiated once, reused across all agents
_provider: LLMProvider | None = None
_search = None
_search_count = 0                          # shared budget per pipeline run
_search_count_by_agent: dict[str, int] = {}  # per-agent cap — flash ignores prompt budgets


def _get_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        _provider = get_provider()
    return _provider


def _get_search():
    global _search
    if _search is None:
        from embroidery.core.search import get_search_provider
        _search = get_search_provider()
    return _search


def reset_search_count():
    """Call before each agent run to reset the per-run search counters."""
    global _search_count
    _search_count = 0
    _search_count_by_agent.clear()


def reset_provider():
    """Force the provider singleton to reinitialize on the next run_agent() call.
    Useful in tests that need to switch providers mid-session."""
    global _provider
    _provider = None


async def run_agent(
    system: str,
    messages: list[dict],
    tools: list[dict],
    model_settings: ModelSettings | None = None,
    max_tool_calls: int = 50,
    agent_name: str = "agent",
) -> str:
    """
    Run an agent until it produces a final text response.

    Args:
        system:         System prompt.
        messages:       Conversation history (mutated in place).
        tools:          Tool definitions in Anthropic JSON schema format.
        model_settings: Model + max_tokens. Defaults to haiku (dev/test).
        max_tool_calls: Safety ceiling on total tool calls per run.
        agent_name:     Human-readable name included in log lines.

    Returns:
        The agent's final text response.
    """
    if model_settings is None:
        model_settings = settings.agents.audience_researcher  # haiku default

    provider = _get_provider()
    call_count = 0
    total_in = 0
    total_out = 0

    _log.info("agent=%s model=%s max_tokens=%d starting", agent_name, model_settings.model, model_settings.max_tokens)
    get_reporter().agent_start(agent_name, model_settings.model, model_settings.max_tokens)

    while call_count < max_tool_calls:
        # Provider calls are sync (and may time.sleep in retries) — run in a
        # thread so asyncio.gather() actually parallelizes concurrent agents.
        response = await asyncio.to_thread(
            provider.create_message,
            model=model_settings.model,
            max_tokens=model_settings.max_tokens,
            system=system,
            messages=messages,
            tools=tools,
        )

        total_in += response.usage.input_tokens
        total_out += response.usage.output_tokens
        _log_usage(response.usage, model_settings.model, call_count, agent_name)
        call_count += 1

        if response.stop_reason == "end_turn":
            _log.info(
                "agent=%s done calls=%d total_in=%d total_out=%d",
                agent_name, call_count, total_in, total_out,
            )
            get_reporter().agent_done(agent_name)
            return response.text

        if response.stop_reason == "tool_use":
            messages.append(response.assistant_message)

            tool_results = []
            for tc in response.tool_calls:
                _log.debug("agent=%s tool=%s inputs=%s", agent_name, tc.name, _truncate(str(tc.input), 120))
                result = await _execute_tool(tc.name, tc.input, agent_name)
                _log.debug("agent=%s tool=%s result_chars=%d", agent_name, tc.name, len(str(result)))
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tc.id,
                    "content": result,
                })
            messages.append({"role": "user", "content": tool_results})
            continue

        _log.info("agent=%s done calls=%d total_in=%d total_out=%d", agent_name, call_count, total_in, total_out)
        get_reporter().agent_done(agent_name)
        return response.text

    _log.warning("agent=%s max_tool_calls=%d reached", agent_name, max_tool_calls)
    get_reporter().agent_done(agent_name)
    return "[max_tool_calls reached]"


def _log_usage(usage, model: str, call_num: int, agent_name: str = "agent") -> None:
    _log.info(
        "agent=%s call=%d model=%s in=%d out=%d",
        agent_name, call_num, model, usage.input_tokens, usage.output_tokens,
    )
    get_reporter().agent_call(agent_name, usage.input_tokens, usage.output_tokens)


def _truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[:n] + "…"


# ─────────────────────────────────────────────
# Tool executor
# ─────────────────────────────────────────────

async def _execute_tool(name: str, inputs: dict, agent_name: str = "agent") -> str:
    global _search_count

    if name == "echo":
        return inputs.get("message", "")

    if name == "write_file":
        result = _tool_write_file(inputs["filename"], inputs["content"])
        _log.info("tool=write_file file=%s", inputs["filename"])
        get_reporter().agent_write(agent_name, inputs["filename"])
        return result

    if name == "read_file":
        result = _tool_read_file(inputs["filename"])
        _log.debug("tool=read_file file=%s chars=%d", inputs["filename"], len(result))
        return result

    if name == "web_search":
        # Per-agent cap enforced in code — flash ignores the prompt's search
        # budget and would starve concurrent sub-agents of the shared budget.
        agent_used = _search_count_by_agent.get(agent_name, 0)
        if agent_used >= settings.search.max_searches_per_agent:
            _log.warning("tool=web_search agent=%s agent_search_limit=%d reached",
                         agent_name, settings.search.max_searches_per_agent)
            return (f"[your search limit of {settings.search.max_searches_per_agent} is used up — "
                    f"stop searching and produce your final output from the evidence you have]")
        if _search_count >= settings.search.max_searches:
            _log.warning("tool=web_search search_limit=%d reached", settings.search.max_searches)
            return (f"[shared search limit reached: {settings.search.max_searches} searches per run — "
                    f"stop searching and produce your final output from the evidence you have]")
        _search_count += 1
        _search_count_by_agent[agent_name] = agent_used + 1
        _log.info("tool=web_search agent=%s count=%d agent_count=%d query=%s",
                  agent_name, _search_count, agent_used + 1, inputs["query"])
        get_reporter().agent_search(agent_name, inputs["query"], inputs.get("num_results", 10))
        return await _get_search().search(inputs["query"], inputs.get("num_results", 10))

    if name == "web_fetch":
        _log.info("tool=web_fetch url=%s", inputs["url"])
        get_reporter().agent_fetch(agent_name, inputs["url"])
        return await _get_search().fetch(inputs["url"])

    _log.warning("tool=%s unknown — no handler registered", name)
    return f"[unknown tool: {name}]"


def _tool_write_file(filename: str, content: str) -> str:
    path = Path(settings.paths.output) / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return f"Written: {path}"


def _tool_read_file(filename: str) -> str:
    path = Path(settings.paths.output) / filename
    if not path.exists():
        return f"[file not found: {filename}]"
    return path.read_text(encoding="utf-8")
