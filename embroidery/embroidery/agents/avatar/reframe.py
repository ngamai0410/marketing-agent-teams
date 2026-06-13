"""
Avatar Stages 4/5/6 — reframers (NO TOOLS). Each leans on the Agent-1 research
report (market-level competitor/sophistication/mechanism) and reframes it for the
priority avatars + the VOC just collected — no new searches, so the avatar doc
never contradicts the research report.

  awareness_mapper     — Stage 4: awareness × sophistication entry point + arc + hooks
  competitor_teardown  — Stage 5: offer/claims/messaging teardown + opportunity gaps
  mechanism_builder    — Stage 6: objection reframes + solution-mechanism map + credibility check
"""

import json

from embroidery.agents.avatar._common import AvatarAgent, catalog_items, run_json_agent
from embroidery.agents.research.subagents import SHOP_BRIEF, shop_context

AWARENESS_MAPPER = AvatarAgent(
    name="awareness_mapper", label="Stage 4 — Awareness × Sophistication Mapping", model_key="awareness_mapper",
    output_file="avatar_awareness.json",
    system_template="""You are a strategic copywriter trained in Eugene Schwartz's framework. You have NO
tools — reason over the VOC and the market research report provided.

{shop_context}

For EACH priority avatar, diagnose its AWARENESS stage (Unaware→Problem→Solution→Product→Most Aware)
from the VOC evidence, and its SOPHISTICATION stage (S1–S5) from the research report's sophistication
+ per-segment awareness (do NOT search — the report already established the market level). Then
prescribe the ad entry point, the carry-the-conversation-forward arc (3 steps), the differentiation
lever (claim|mechanism|identity), and 3 hook formulas. Cite a VOC quote as evidence for each diagnosis.

OUTPUT DISCIPLINE: FINAL message = ONLY one JSON object matching the schema. No fences. English.

OUTPUT SCHEMA:
{{
  "avatars": [
    {{"avatar": "...", "awareness_stage": "Unaware|Problem|Solution|Product|Most Aware",
      "awareness_evidence": "verbatim VOC quote",
      "sophistication_stage": "S1|S2|S3|S4|S5", "sophistication_evidence": "what claim everyone makes",
      "ad_entry_point": "...", "arc": ["step 1", "step 2", "step 3"],
      "differentiation_lever": "claim|mechanism|identity",
      "hook_formulas": ["hook 1", "hook 2", "hook 3"]}}
  ]
}}""",
)

COMPETITOR_TEARDOWN = AvatarAgent(
    name="competitor_teardown", label="Stage 5 — Competitor Teardown", model_key="competitor_teardown",
    output_file="avatar_competitor.json",
    system_template="""You are a competitive-intelligence analyst. You have NO tools — tear down the
competitors already identified in the market research report (and the FB ad scout), facts only.

{shop_context}

For the top 3 competitors vs the priority avatars: audit the offer stack (shipping, guarantee,
installments, warranty, bonuses), audit the top 3 claims (backed by proof yes/no), list messaging
weaknesses from negative reviews, and the opportunity gaps we can own. Also audit ALTERNATIVE
solutions the avatar uses instead (DIY, generic store-bought, gift card) and each alternative's FLAW
(= our competitive angle).

OUTPUT DISCIPLINE: FINAL message = ONLY one JSON object matching the schema. No fences. English.

OUTPUT SCHEMA:
{{
  "competitors": [
    {{"name": "...", "offer_stack": ["..."], "claims": [{{"claim": "...", "proof": true}}],
      "weaknesses": ["..."], "opportunity_gaps": ["..."]}}
  ],
  "alternatives": [{{"alternative": "...", "flaw": "...", "our_angle": "..."}}]
}}""",
)

MECHANISM_BUILDER = AvatarAgent(
    name="mechanism_builder", label="Stage 6 — Objection Reframes + Solution Mechanism", model_key="mechanism_builder",
    output_file="avatar_mechanism.json",
    system_template="""You are a direct-response copywriter for skeptic-heavy markets. You have NO tools —
build from the research report's unique_mechanism_candidates + the objections collected so far.

{shop_context}

TASK 1 — OBJECTION REFRAMES: for each objection write a reframe (analogy | category | belief-breaking |
authority), in the customer's own language.
TASK 2 — SOLUTION MECHANISM MAP: core problem → root cause → how the product addresses the root cause →
why alternatives fail at the root cause → the specific feature that makes it real.
TASK 3 — CREDIBILITY CHECK: rate the mechanism NEW / OBVIOUS / COMPLETE 1–5; flag any <3 for revision.

OUTPUT DISCIPLINE: FINAL message = ONLY one JSON object matching the schema. No fences. English.

OUTPUT SCHEMA:
{{
  "objection_reframes": [{{"objection": "...", "technique": "analogy|category|belief|authority", "reframe": "..."}}],
  "solution_mechanism": {{"core_problem": "...", "root_cause": "...", "how_it_addresses": "...",
    "why_alternatives_fail": "...", "delivered_via": "..."}},
  "credibility_check": {{"new": 1, "obvious": 1, "complete": 1, "needs_revision": false}}
}}""",
)

_AGENTS = [AWARENESS_MAPPER, COMPETITOR_TEARDOWN, MECHANISM_BUILDER]
_PLACEHOLDERS = {a.name: ["shop_context"] for a in _AGENTS}


def _ctx_kickoff(label: str, voc: dict, research_report: dict) -> str:
    return (
        f"{label}\n\n"
        f"=== VOC (coded quotes) ===\n{json.dumps(voc, ensure_ascii=False)[:6000]}\n\n"
        f"=== MARKET RESEARCH REPORT ===\n{json.dumps(research_report, ensure_ascii=False)[:8000]}"
    )


async def run_awareness(voc: dict, research_report: dict, priority_avatars: list[str],
                        brief: dict = SHOP_BRIEF) -> dict:
    kickoff = _ctx_kickoff(
        f"Map awareness × sophistication for the priority avatars: {', '.join(priority_avatars) or '(all)'}.",
        voc, research_report)
    return await run_json_agent(AWARENESS_MAPPER, kickoff, tools=[], ctx={"shop_context": shop_context(brief)})


async def run_competitor(voc: dict, research_report: dict, brief: dict = SHOP_BRIEF) -> dict:
    kickoff = _ctx_kickoff("Tear down the top competitors and alternatives.", voc, research_report)
    return await run_json_agent(COMPETITOR_TEARDOWN, kickoff, tools=[], ctx={"shop_context": shop_context(brief)})


async def run_mechanism(voc: dict, research_report: dict, brief: dict = SHOP_BRIEF) -> dict:
    kickoff = _ctx_kickoff("Build objection reframes and the solution-mechanism map.", voc, research_report)
    return await run_json_agent(MECHANISM_BUILDER, kickoff, tools=[], ctx={"shop_context": shop_context(brief)})


def prompt_catalog() -> list[dict]:
    return catalog_items(_AGENTS, _PLACEHOLDERS, "Avatar — reframe")
