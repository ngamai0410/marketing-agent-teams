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
) -> str:
    """
    Run an agent until it produces a final text response.

    Args:
        system:         System prompt.
        messages:       Conversation history (mutated in place).
        tools:          Tool definitions in Anthropic JSON schema format.
        model_settings: Model + max_tokens. Defaults to haiku (dev/test).
        max_tool_calls: Safety ceiling on total tool calls per run.

    Returns:
        The agent's final text response.
    """
    if model_settings is None:
        model_settings = settings.agents.audience_researcher  # haiku default

    provider = _get_provider()
    call_count = 0

    while call_count < max_tool_calls:
        response = provider.create_message(
            model=model_settings.model,
            max_tokens=model_settings.max_tokens,
            system=system,
            messages=messages,
            tools=tools,
        )

        _log_usage(response.usage, model_settings.model, call_count)
        call_count += 1

        if response.stop_reason == "end_turn":
            return response.text

        if response.stop_reason == "tool_use":
            messages.append(response.assistant_message)

            tool_results = []
            for tc in response.tool_calls:
                result = await _execute_tool(tc.name, tc.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tc.id,
                    "content": result,
                })
            messages.append({"role": "user", "content": tool_results})
            continue

        return response.text

    return "[max_tool_calls reached]"


def _log_usage(usage, model: str, call_num: int) -> None:
    print(f"  [usage] call={call_num} in={usage.input_tokens} out={usage.output_tokens} model={model}")


# ─────────────────────────────────────────────
# Tool executor
# ─────────────────────────────────────────────

async def _execute_tool(name: str, inputs: dict) -> str:
    global _search_count

    if name == "echo":
        return inputs.get("message", "")

    if name == "write_file":
        return _tool_write_file(inputs["filename"], inputs["content"])

    if name == "read_file":
        return _tool_read_file(inputs["filename"])

    if name == "web_search":
        if _search_count >= settings.search.max_searches:
            return f"[search limit reached: {settings.search.max_searches} searches per run]"
        _search_count += 1
        return await _get_search().search(inputs["query"], inputs.get("num_results", 10))

    if name == "web_fetch":
        return await _get_search().fetch(inputs["url"])

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
