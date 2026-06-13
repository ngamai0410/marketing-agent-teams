"""
Shared plumbing for the Avatar Builder sub-agents.

Every avatar agent is an `AvatarAgent` (name + label + .format system template +
model_key + optional output_file). Search/discovery agents return a JSON object
as their final text message — `run_json_agent` parses it and (if output_file is
set) persists it under data/output/ so the next stage can read it and the
dashboard can show it. Prompts render through the prompt_store so they are
user-editable (avatar.<name>), with {placeholder} context and {{}} literal braces.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from embroidery.agents.research.subagents import parse_json_output  # reuse tolerant parser
from embroidery.core.agent_loop import run_agent
from embroidery.core.config import settings
from embroidery.core.logger import get_logger
from embroidery.core.prompt_store import get_prompt_store
from embroidery.core.reporter import get_reporter

log = get_logger(__name__)


@dataclass(frozen=True)
class AvatarAgent:
    name: str                 # agent_name + prompt-id stem + log name
    label: str                # human label for the ⚙ prompt editor
    model_key: str            # attribute on settings.agents
    system_template: str      # .format template ({placeholder}, {{}} literal braces)
    output_file: str | None = None   # if set, JSON output persisted under data/output/


def _to_dollar(format_template: str) -> str:
    """Convert a `.format`-style template to a `string.Template` `$placeholder` form.

    Steps:
      1. Unescape `{{` → `{` and `}}` → `}` (format-style literal braces).
      2. Convert every remaining `{name}` placeholder to `${name}`.

    This generalises `prompt_store.to_dollar` to arbitrary placeholder names,
    which avatar agents need since their context keys vary per-agent.
    """
    # Step 1: unescape literal braces
    t = format_template.replace("{{", "\x00LBRACE\x00").replace("}}", "\x00RBRACE\x00")
    # Step 2: convert {name} → ${name} for any identifier
    t = re.sub(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", r"${\1}", t)
    # Step 3: restore literal braces
    t = t.replace("\x00LBRACE\x00", "{").replace("\x00RBRACE\x00", "}")
    return t


def build_system(agent: AvatarAgent, **ctx) -> str:
    """Render an agent's system prompt, honouring any saved user override."""
    store = get_prompt_store()
    return store.render(f"avatar.{agent.name}", _to_dollar(agent.system_template), **ctx)


async def run_json_agent(agent: AvatarAgent, kickoff: str, *, tools: list[dict],
                         ctx: dict, max_tool_calls: int = 16) -> dict:
    """Run one agent that returns a JSON object as final text; persist if output_file set."""
    raw = await run_agent(
        system=build_system(agent, **ctx),
        messages=[{"role": "user", "content": kickoff}],
        tools=tools,
        model_settings=getattr(settings.agents, agent.model_key),
        max_tool_calls=max_tool_calls,
        agent_name=agent.name,
    )
    result = parse_json_output(raw)
    if agent.output_file:
        path = Path(settings.paths.output) / agent.output_file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        get_reporter().agent_output(agent.name, agent.output_file)
        log.info("agent=%s output saved file=%s", agent.name, path)
    return result


def catalog_items(agents: list[AvatarAgent], placeholders: dict[str, list[str]],
                  stage_label: str) -> list[dict]:
    """Build prompt_catalog() entries for a group of avatar agents."""
    store = get_prompt_store()
    items: list[dict] = []
    for a in agents:
        pid = f"avatar.{a.name}"
        default = _to_dollar(a.system_template)
        items.append({
            "id": pid,
            "name": a.label,
            "stage": stage_label,
            "placeholders": placeholders.get(a.name, []),
            "default": default,
            "text": store.text(pid, default),
            "overridden": store.is_overridden(pid),
        })
    return items


def load_json(name: str) -> dict:
    """Load a previously-saved stage output from data/output/ (for skipped stages)."""
    path = Path(settings.paths.output) / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
