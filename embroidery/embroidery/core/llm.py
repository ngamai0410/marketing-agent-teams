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

from embroidery.core.config import settings


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
# Gemini
# ─────────────────────────────────────────────

class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str):
        from google import genai
        self._client = genai.Client(api_key=api_key)

    def create_message(self, model, max_tokens, system, messages, tools) -> LLMResponse:
        import time
        from google.genai import types
        from google.genai.errors import ClientError

        contents = _to_gemini_messages(messages)
        config_kwargs: dict[str, Any] = {
            "system_instruction": system,
            "max_output_tokens": max_tokens,
            # Default temp (1.0) makes gemini-2.5-flash prone to
            # MALFORMED_FUNCTION_CALL on large tool payloads (e.g. write_file
            # with a full report). Lower temp markedly reduces this.
            "temperature": 0.3,
        }
        if tools:
            config_kwargs["tools"] = _to_gemini_tools(tools)

        for attempt in range(3):
            try:
                # Escalate temperature on retries — at fixed temp an "empty
                # candidate" response tends to repeat identically.
                config_kwargs["temperature"] = 0.3 + 0.3 * attempt
                resp = self._client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=types.GenerateContentConfig(**config_kwargs),
                )
                # Gemini intermittently returns an empty candidate (no text,
                # no function call) — e.g. finish_reason MALFORMED_FUNCTION_CALL
                # or a blocked/empty response. Retry instead of ending the run.
                if _gemini_response_is_empty(resp):
                    if attempt < 2:
                        finish = _gemini_finish_reason(resp)
                        print(f"  [gemini] empty response (finish_reason={finish}) — retrying (attempt {attempt + 1}/3)")
                        time.sleep(2 * (attempt + 1))
                        continue
                    raise RuntimeError(
                        f"Gemini returned an empty response 3 times in a row "
                        f"(finish_reason={_gemini_finish_reason(resp)})."
                    )
                break
            except ClientError as e:
                if e.code == 429 and attempt < 2:
                    import re
                    err_str = str(e)
                    # Non-retriable billing errors — fail fast with clear message
                    if "limit: 0" in err_str:
                        raise RuntimeError(
                            "Gemini free-tier quota is limit=0. "
                            "Enable billing at console.cloud.google.com for this project."
                        ) from e
                    if "prepayment credits are depleted" in err_str:
                        raise RuntimeError(
                            "Gemini prepaid credits are depleted. "
                            "Top up at https://aistudio.google.com/plan or switch to pay-as-you-go billing."
                        ) from e
                    delay_match = re.search(r"retryDelay.*?(\d+)s", err_str)
                    delay = int(delay_match.group(1)) + 2 if delay_match else 60
                    print(f"  [gemini] rate limited — waiting {delay}s (attempt {attempt + 1}/3)")
                    time.sleep(delay)
                else:
                    raise

        candidate = resp.candidates[0] if resp.candidates else None
        parts = candidate.content.parts if (candidate and candidate.content) else []

        text = ""
        tool_calls: list[ToolCall] = []
        for part in parts:
            if getattr(part, "text", None):
                text += part.text
            fc = getattr(part, "function_call", None)
            if fc:
                # Use name as ID so tool_result can reference it in next turn
                tc_id = fc.name if not any(t.id == fc.name for t in tool_calls) else f"{fc.name}_{len(tool_calls)}"
                tool_calls.append(ToolCall(id=tc_id, name=fc.name, input=dict(fc.args or {})))

        # Store in Anthropic-compatible dict format for the shared history
        assistant_content: list[dict] = []
        if text:
            assistant_content.append({"type": "text", "text": text})
        for tc in tool_calls:
            assistant_content.append({"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.input})

        usage_meta = getattr(resp, "usage_metadata", None)
        return LLMResponse(
            stop_reason="tool_use" if tool_calls else "end_turn",
            text=text,
            tool_calls=tool_calls,
            usage=Usage(
                getattr(usage_meta, "prompt_token_count", 0) or 0,
                getattr(usage_meta, "candidates_token_count", 0) or 0,
            ),
            assistant_message={"role": "assistant", "content": assistant_content},
        )


def _gemini_response_is_empty(resp) -> bool:
    candidate = resp.candidates[0] if resp.candidates else None
    parts = candidate.content.parts if (candidate and candidate.content) else None
    if not parts:
        return True
    return not any(getattr(p, "text", None) or getattr(p, "function_call", None) for p in parts)


def _gemini_finish_reason(resp) -> str:
    candidate = resp.candidates[0] if resp.candidates else None
    return str(getattr(candidate, "finish_reason", "NO_CANDIDATE"))


def _to_gemini_tools(tools: list[dict]) -> list:
    from google.genai import types

    declarations = []
    for tool in tools:
        declarations.append(types.FunctionDeclaration(
            name=tool["name"],
            description=tool.get("description", ""),
            parameters=tool.get("input_schema", {}),
        ))
    return [types.Tool(function_declarations=declarations)]


def _to_gemini_messages(messages: list[dict]) -> list:
    """Convert Anthropic-format message history to Gemini contents list."""
    from google.genai import types

    contents = []
    for msg in messages:
        role = "model" if msg["role"] == "assistant" else "user"
        content = msg["content"]
        parts = []

        if isinstance(content, str):
            parts.append(types.Part.from_text(text=content))
        elif isinstance(content, list):
            for block in content:
                # Dict blocks (from Gemini or OpenAI round-trips stored as dicts)
                if isinstance(block, dict):
                    btype = block.get("type")
                    if btype == "text":
                        parts.append(types.Part.from_text(text=block["text"]))
                    elif btype == "tool_use":
                        parts.append(types.Part.from_function_call(
                            name=block["name"], args=block["input"]
                        ))
                    elif btype == "tool_result":
                        result = block["content"]
                        if isinstance(result, list):
                            result = " ".join(b.get("text", "") for b in result if isinstance(b, dict))
                        # tool_use_id == name for Gemini (set in GeminiProvider above)
                        parts.append(types.Part.from_function_response(
                            name=block["tool_use_id"],
                            response={"result": str(result)},
                        ))
                # Anthropic SDK objects (from Anthropic round-trips)
                elif hasattr(block, "type"):
                    if block.type == "text":
                        parts.append(types.Part.from_text(text=block.text))
                    elif block.type == "tool_use":
                        parts.append(types.Part.from_function_call(
                            name=block.name, args=block.input
                        ))

        if parts:
            contents.append(types.Content(role=role, parts=parts))

    return contents


# ─────────────────────────────────────────────
# Factory
# ─────────────────────────────────────────────

def get_provider() -> LLMProvider:
    provider = settings.llm_provider
    if provider == "anthropic":
        return AnthropicProvider(api_key=settings.anthropic_api_key)
    if provider == "openai":
        return OpenAIProvider(api_key=settings.openai_api_key)
    if provider == "gemini":
        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY not set. Add it to .env.")
        return GeminiProvider(api_key=settings.gemini_api_key)
    raise ValueError(f"Unknown llm.provider: '{provider}'. Options: anthropic | openai | gemini")
