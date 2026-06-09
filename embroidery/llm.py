"""
LLM provider abstraction.

Internal message format uses Anthropic's structure (canonical).
Each provider converts to/from it transparently.

Switching providers: change `llm.provider` in config.yaml.
"""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from config import settings


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict


@dataclass
class Usage:
    input_tokens: int
    output_tokens: int


@dataclass
class LLMResponse:
    stop_reason: str            # "end_turn" | "tool_use"
    text: str                   # final text when stop_reason == "end_turn"
    tool_calls: list[ToolCall]  # populated when stop_reason == "tool_use"
    usage: Usage
    assistant_message: dict     # provider-native dict, ready to append to messages


class LLMProvider(ABC):
    @abstractmethod
    def create_message(
        self,
        model: str,
        max_tokens: int,
        system: str,
        messages: list[dict],
        tools: list[dict],
    ) -> LLMResponse:
        ...


# ─────────────────────────────────────────────
# Anthropic
# ─────────────────────────────────────────────

class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str):
        import anthropic
        self._client = anthropic.Anthropic(api_key=api_key)

    def create_message(self, model, max_tokens, system, messages, tools) -> LLMResponse:
        import anthropic
        kwargs: dict[str, Any] = dict(
            model=model, max_tokens=max_tokens, system=system, messages=messages
        )
        if tools:
            kwargs["tools"] = tools

        resp = self._client.messages.create(**kwargs)

        text = ""
        tool_calls: list[ToolCall] = []
        for block in resp.content:
            if hasattr(block, "text"):
                text = block.text
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(id=block.id, name=block.name, input=block.input))

        return LLMResponse(
            stop_reason="tool_use" if tool_calls else resp.stop_reason,
            text=text,
            tool_calls=tool_calls,
            usage=Usage(resp.usage.input_tokens, resp.usage.output_tokens),
            # Anthropic needs the raw content blocks (not dicts) in message history
            assistant_message={"role": "assistant", "content": resp.content},
        )


# ─────────────────────────────────────────────
# OpenAI
# ─────────────────────────────────────────────

class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str):
        from openai import OpenAI
        self._client = OpenAI(api_key=api_key)

    def create_message(self, model, max_tokens, system, messages, tools) -> LLMResponse:
        oai_messages = _to_openai_messages(system, messages)
        oai_tools = [_to_openai_tool(t) for t in tools] if tools else None

        kwargs: dict[str, Any] = dict(
            model=model, max_tokens=max_tokens, messages=oai_messages
        )
        if oai_tools:
            kwargs["tools"] = oai_tools

        resp = self._client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message

        tool_calls: list[ToolCall] = []
        oai_tool_calls = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    input=json.loads(tc.function.arguments),
                ))
                oai_tool_calls.append({
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                })

        # OpenAI assistant message uses its own format
        assistant_msg: dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
        if oai_tool_calls:
            assistant_msg["tool_calls"] = oai_tool_calls

        return LLMResponse(
            stop_reason="tool_use" if tool_calls else "end_turn",
            text=msg.content or "",
            tool_calls=tool_calls,
            usage=Usage(resp.usage.prompt_tokens, resp.usage.completion_tokens),
            assistant_message=assistant_msg,
        )


# ─────────────────────────────────────────────
# OpenAI format converters
# ─────────────────────────────────────────────

def _to_openai_tool(tool: dict) -> dict:
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "parameters": tool.get("input_schema", {}),
        },
    }


def _to_openai_messages(system: str, messages: list[dict]) -> list[dict]:
    """
    Convert Anthropic-format message history to OpenAI format.
    - System prompt becomes role=system at position 0
    - tool_result blocks become role=tool messages
    - Assistant content blocks (objects) become role=assistant with tool_calls
    """
    out: list[dict] = [{"role": "system", "content": system}]

    for msg in messages:
        role = msg["role"]
        content = msg["content"]

        if role == "user":
            if isinstance(content, str):
                out.append({"role": "user", "content": content})
            elif isinstance(content, list):
                tool_results = [b for b in content if isinstance(b, dict) and b.get("type") == "tool_result"]
                text_parts = [b for b in content if isinstance(b, dict) and b.get("type") == "text"]
                for tr in tool_results:
                    result_content = tr["content"]
                    out.append({
                        "role": "tool",
                        "tool_call_id": tr["tool_use_id"],
                        "content": result_content if isinstance(result_content, str) else json.dumps(result_content),
                    })
                if text_parts:
                    out.append({"role": "user", "content": " ".join(t.get("text", "") for t in text_parts)})

        elif role == "assistant":
            # Content may be a string (from OpenAI round-trip) or Anthropic content blocks
            if isinstance(content, str):
                out.append({"role": "assistant", "content": content})
            elif isinstance(content, dict) and "tool_calls" in content:
                # Already OpenAI format (stored from a previous OpenAI turn)
                out.append(content)
            elif isinstance(content, list):
                text = ""
                tool_calls = []
                for block in content:
                    if hasattr(block, "text"):
                        text = block.text
                    elif hasattr(block, "type") and block.type == "tool_use":
                        tool_calls.append({
                            "id": block.id,
                            "type": "function",
                            "function": {"name": block.name, "arguments": json.dumps(block.input)},
                        })
                oai_msg: dict[str, Any] = {"role": "assistant", "content": text}
                if tool_calls:
                    oai_msg["tool_calls"] = tool_calls
                out.append(oai_msg)

    return out


# ─────────────────────────────────────────────
# Factory
# ─────────────────────────────────────────────

def get_provider() -> LLMProvider:
    provider = settings.llm_provider
    if provider == "anthropic":
        return AnthropicProvider(api_key=settings.anthropic_api_key)
    if provider == "openai":
        return OpenAIProvider(api_key=settings.openai_api_key)
    raise ValueError(f"Unknown llm.provider: '{provider}'. Options: anthropic | openai")
