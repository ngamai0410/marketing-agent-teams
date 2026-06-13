"""
Avatar Stage 7 — Synthesizer (NO TOOLS). Merges Stages 0–6 into the Avatar Deep
Dive. Two calls (like the research synthesizer):
  call 1 → avatar_deep_dive.json  (structured, one object per priority avatar)
  call 2 → customer_avatars.md    (the human-readable doc — data contract for Agents 3–6)
Python writes both files; the model never emits a large tool payload.
"""

import json
from datetime import date
from pathlib import Path

from embroidery.agents.avatar._common import build_system, AvatarAgent
from embroidery.agents.research.subagents import SHOP_BRIEF, shop_context
from embroidery.core.agent_loop import run_agent
from embroidery.core.config import settings
from embroidery.core.json_utils import parse_json_output
from embroidery.core.logger import get_logger
from embroidery.core.reporter import get_reporter

log = get_logger(__name__)

_SYNTH_JSON = AvatarAgent(
    name="avatar_synthesizer", label="Stage 7 — Avatar Synthesizer (JSON)", model_key="avatar_synthesizer",
    system_template="""You are a senior creative strategist merging 7 stages of avatar research into a
structured Avatar Deep Dive. NON-NEGOTIABLE: include EVERY verbatim quote (no sampling/dedup), preserve
original customer language, every quote gets an insight.

{shop_context}

Produce ONE JSON object: an array `avatars`, one entry per priority avatar, each carrying the snapshot,
demographics, occasion map, desire chain (surface→functional→emotional→identity→deepest), awareness +
sophistication, the FULL coded VOC, competitor-gap map, solution mechanism, objection reframes, ad angles,
and hooks. FINAL message = ONLY the JSON object. No fences. English.

OUTPUT SCHEMA:
{{
  "research_date": "{research_date}",
  "avatars": [
    {{"name": "...", "snapshot": "...",
      "demographics": {{"age": "...", "gender": "...", "role": "...", "occasion": "...", "income_signal": "..."}},
      "desire_chain": {{"surface": "...", "functional": "...", "emotional": "...", "identity": "...", "deepest": "..."}},
      "awareness_stage": "...", "sophistication_stage": "...",
      "voc": [{{"quote": "...", "category": ["..."], "insight": "...", "source": "url"}}],
      "competitor_gaps": [{{"gap": "...", "angle": "..."}}],
      "solution_mechanism": {{"root_cause": "...", "mechanism": "...", "why_others_fail": "...", "delivered_via": "..."}},
      "objection_reframes": [{{"objection": "...", "reframe": "..."}}],
      "ad_angles": [{{"name": "...", "awareness_entry": "...", "hook_idea": "...", "core_message": "...", "tactic": "claim|mechanism|identity"}}],
      "hooks_to_test": ["..."]}}
  ]
}}""",
)

_SYNTH_MD = AvatarAgent(
    name="avatar_synthesizer_md", label="Stage 7 — Avatar Synthesizer (Markdown)", model_key="avatar_synthesizer",
    system_template="""You are a senior creative strategist writing the AVATAR DEEP DIVE document a
copywriter will use to build ads. You receive the structured deep-dive JSON plus the raw stage outputs.

{shop_context}

Write a thorough markdown document. For EACH priority avatar include these sections:
one-line snapshot · demographics · occasion map · desire chain (surface→deepest) · awareness stage +
entry point · sophistication stage + what NOT to say · VOICE OF CUSTOMER (ALL coded quotes, grouped by
PAIN/DESIRE/TRIGGER/OBJECTION/BELIEF/IDENTITY, every quote with its insight) · competitor-gap map (table)
· solution mechanism · objection reframes (ready for copy) · ad angles (priority order) · hooks to test.
NON-NEGOTIABLE: every verbatim quote is preserved exactly, in "quotes", with its source. No filler.
Output ONLY the markdown document — no preamble, no fences around the whole document.""",
)


async def run_synthesis(stages: dict, research_report: dict, priority_avatars: list[str],
                        brief: dict = SHOP_BRIEF) -> tuple[dict, str]:
    """Two no-tool calls → (deep_dive dict, markdown). Writes both data-contract files."""
    blob = json.dumps(stages, ensure_ascii=False)

    raw = await run_agent(
        system=build_system(_SYNTH_JSON, shop_context=shop_context(brief), research_date=date.today().isoformat()),
        messages=[{"role": "user", "content":
                   f"Synthesize the structured Avatar Deep Dive for: {', '.join(priority_avatars) or '(all)'}.\n\n"
                   f"=== ALL STAGE OUTPUTS ===\n{blob[:24000]}"}],
        tools=[], model_settings=settings.agents.avatar_synthesizer, agent_name="avatar_synthesizer",
    )
    deep_dive = parse_json_output(raw)

    markdown = await run_agent(
        system=build_system(_SYNTH_MD, shop_context=shop_context(brief)),
        messages=[{"role": "user", "content":
                   "Write the Avatar Deep Dive document.\n\n"
                   f"=== DEEP DIVE JSON ===\n{json.dumps(deep_dive, ensure_ascii=False)}\n\n"
                   f"=== RAW STAGE OUTPUTS ===\n{blob[:16000]}"}],
        tools=[], model_settings=settings.agents.avatar_synthesizer, agent_name="avatar_synthesizer_md",
    )
    markdown = markdown.strip()
    if markdown.startswith("```"):
        markdown = markdown.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    out = Path(settings.paths.output); out.mkdir(parents=True, exist_ok=True)
    (out / "avatar_deep_dive.json").write_text(json.dumps(deep_dive, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "customer_avatars.md").write_text(markdown, encoding="utf-8")
    get_reporter().agent_output("avatar_synthesizer", "avatar_deep_dive.json")
    get_reporter().agent_output("avatar_synthesizer_md", "customer_avatars.md")
    log.info("avatar synthesis done deep_dive_avatars=%d md_chars=%d",
             len(deep_dive.get("avatars", [])), len(markdown))
    return deep_dive, markdown


def prompt_catalog() -> list[dict]:
    from embroidery.agents.avatar._common import catalog_items
    return catalog_items([_SYNTH_JSON, _SYNTH_MD],
                         {"avatar_synthesizer": ["shop_context", "research_date"],
                          "avatar_synthesizer_md": ["shop_context"]},
                         "Avatar — synthesis")
