"""Tolerant parsing of JSON returned as an LLM's final text message.

Sub-agents across workflows return a single JSON object as plain text (rather
than via a tool call — this avoids large-tool-payload failures on some models).
`parse_json_output` extracts that object, tolerating ```json fences and stray prose.
"""

import json


def parse_json_output(raw: str) -> dict:
    """Parse a JSON object from a model's final text, tolerating fences/prose."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(f"No JSON object in sub-agent output: {raw[:300]!r}")
    return json.loads(text[start:end + 1])
