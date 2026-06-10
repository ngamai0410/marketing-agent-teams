"""
Core agentic loop — shared by every agent in the pipeline.

LLM provider and search engine are configured in config.yaml.
No provider-specific code lives here.

Usage:
    result = asyncio.run(run_agent(system, messages, tools, model_settings))
"""

from pathlib import Path

from config import settings, ModelSettings
from llm import get_provider, LLMProvider
from logger import get_logger

_log = get_logger("agent_loop")

# Module-level singletons — instantiated once, reused across all agents
_provider: LLMProvider | None = None
_search = None
_search_count = 0


def _get_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        _provider = get_provider()
    return _provider


def _get_search():
    global _search
    if _search is None:
        from search import get_search_provider
        _search = get_search_provider()
    return _search


def reset_search_count():
    """Call before each agent run to reset the per-run search counter."""
    global _search_count
    _search_count = 0


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

    while call_count < max_tool_calls:
        response = provider.create_message(
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
            return response.text

        if response.stop_reason == "tool_use":
            messages.append(response.assistant_message)

            tool_results = []
            for tc in response.tool_calls:
                _log.debug("agent=%s tool=%s inputs=%s", agent_name, tc.name, _truncate(str(tc.input), 120))
                result = await _execute_tool(tc.name, tc.input)
                _log.debug("agent=%s tool=%s result_chars=%d", agent_name, tc.name, len(str(result)))
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tc.id,
                    "content": result,
                })
            messages.append({"role": "user", "content": tool_results})
            continue

        _log.info("agent=%s done calls=%d total_in=%d total_out=%d", agent_name, call_count, total_in, total_out)
        return response.text

    _log.warning("agent=%s max_tool_calls=%d reached", agent_name, max_tool_calls)
    return "[max_tool_calls reached]"


def _log_usage(usage, model: str, call_num: int, agent_name: str = "agent") -> None:
    _log.info(
        "agent=%s call=%d model=%s in=%d out=%d",
        agent_name, call_num, model, usage.input_tokens, usage.output_tokens,
    )


def _truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[:n] + "…"


# ─────────────────────────────────────────────
# Tool executor
# ─────────────────────────────────────────────

async def _execute_tool(name: str, inputs: dict) -> str:
    global _search_count

    if name == "echo":
        return inputs.get("message", "")

    if name == "write_file":
        result = _tool_write_file(inputs["filename"], inputs["content"])
        _log.info("tool=write_file file=%s", inputs["filename"])
        return result

    if name == "read_file":
        result = _tool_read_file(inputs["filename"])
        _log.debug("tool=read_file file=%s chars=%d", inputs["filename"], len(result))
        return result

    if name == "web_search":
        if _search_count >= settings.search.max_searches:
            _log.warning("tool=web_search search_limit=%d reached", settings.search.max_searches)
            return f"[search limit reached: {settings.search.max_searches} searches per run]"
        _search_count += 1
        _log.info("tool=web_search count=%d query=%s", _search_count, inputs["query"])
        return await _get_search().search(inputs["query"], inputs.get("num_results", 10))

    if name == "web_fetch":
        _log.info("tool=web_fetch url=%s", inputs["url"])
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
