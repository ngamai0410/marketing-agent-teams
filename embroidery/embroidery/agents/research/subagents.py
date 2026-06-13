"""
Agent 1 sub-agents A/B/C — the three parallel researchers of the
Market Research mini-pipeline (Day 3 of the development plan).

  Agent A — Audience & Desire Researcher   (8-step framework steps 1, 2, 4, 5, 6)
  Agent B — Competitor & Positioning Analyst (steps 3, 4, 8)
  Agent C — Social Media & Hook Analyst    (step 7)

Each sub-agent has search-only tools and returns a single JSON object as
its final text message. This module parses that JSON and saves a copy to
output/ so the Day 4 Synthesizer can be developed against static files.

Run one sub-agent standalone (prompt development / Day 3 testing):
    cd embroidery && venv/bin/python -m embroidery.agents.research.subagents a   # or b / c
"""

import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from embroidery.core.agent_loop import run_agent, reset_search_count
from embroidery.core.config import settings
from embroidery.core.logger import get_logger
from embroidery.core.prompt_store import get_prompt_store, to_dollar
from embroidery.core.tools import SEARCH_TOOLS

log = get_logger(__name__)

# ─────────────────────────────────────────────
# Shop brief — edit before each campaign run
# ─────────────────────────────────────────────
SHOP_BRIEF = {
    "name": "Custom Embroidery Co",
    "url": "https://www.etsy.com/shop/CustomEmbroideryShop",
    "top_products": [
        "Custom embroidered hats and beanies",
        "Personalised embroidered hoodies and sweatshirts",
        "Custom team / club embroidered jackets",
        "Embroidered baby gifts and keepsakes",
        "Custom logo patches and iron-on emblems",
    ],
    "price_range": "$25–$120 per item, bulk discounts available",
    "turnaround": "5–10 business days standard, 2–3 day rush available",
    "differentiator": "Hand-digitised designs, no minimum order, ships worldwide",
}


def shop_context(brief: dict = SHOP_BRIEF) -> str:
    return f"""SHOP CONTEXT:
Name: {brief["name"]}
URL: {brief["url"]}
Top products: {", ".join(brief["top_products"])}
Price range: {brief["price_range"]}
Turnaround: {brief["turnaround"]}
Differentiator: {brief["differentiator"]}

TARGET SEGMENTS (research each separately):
- Segment A "Team Pride": clubs, sports teams, school groups (bulk orders, team identity)
- Segment B "Gift Giver": personal occasions — weddings, graduations, pet memorials, baby gifts
- Segment C "Brand Builder": small businesses ordering uniforms, merch, employee gifts
- Segment D "Aesthetic Buyer": TikTok/Instagram-native, "quiet luxury", embroidery as fashion"""


_SHARED_RULES = """
RESEARCH DISCIPLINE:
- ALL insights must come from actual search results — never invent quotes, reviews, or competitor names.
- Budget: at most 6 web_search calls and 3 web_fetch calls. Choose queries carefully; prefer
  site:reddit.com and Etsy/review-focused queries that surface real customer language.
- Quotes must be VERBATIM from search snippets or fetched pages, with their source URL.

OUTPUT DISCIPLINE:
- Your FINAL message must be ONLY a single JSON object matching the schema below.
- No markdown fences, no commentary before or after the JSON.
- Every string field in English. Use null only where a value genuinely could not be found."""


# ─────────────────────────────────────────────
# Agent A — Audience & Desire Researcher
# Steps 1 (desires), 2 (problems), 4 (objections), 5 (emotion mapping), 6 (identity)
# ─────────────────────────────────────────────

AGENT_A_KICKOFF = "Begin audience and desire research. Search first, then output the JSON."

AGENT_A_SYSTEM_TEMPLATE = """You are the Audience & Desire Researcher for a custom embroidery shop —
one of three parallel market-research sub-agents. Your specialty: what customers WANT,
what PAINS them, and WHO they are trying to be. You mine Reddit threads, Etsy reviews,
and Q&A communities for real customer voice.

{shop_context}

YOUR FRAMEWORK (steps 1, 2, 4, 5, 6 of the 8-step deep research):

STEP 1 — DESIRE STATEMENTS (target 12–15, ranked by emotional intensity)
What does the ideal customer REALLY want beyond "custom embroidery"? Transformation desires:
belonging, identity, gift-giving love, team pride, status, being seen as thoughtful.
Tag every desire with its LF8 driver (Life-Force 8):
  LF1 survival/life-extension · LF2 enjoyment of food/drink · LF3 freedom from fear/pain/danger
  LF4 sexual companionship · LF5 comfortable living conditions · LF6 superiority/winning/keeping up
  LF7 care and protection of loved ones · LF8 social approval
For embroidery expect mostly LF6, LF7, LF8 — but verify against evidence, don't assume.

STEP 2 — PROBLEM STATEMENTS (target 8–10, ranked by urgency × pain intensity)
Mine complaints, 1–3 star reviews, Reddit rants. Express every emotion in WHEN+WHY format:
  "WHEN [specific situation], they feel [emotion], WHY: [underlying belief or stake]"
Apply the Problem Node 3-check to every problem — all three must hold or discard it:
  1. MOMENT — it is felt at a specific, nameable moment (not a vague dissatisfaction)
  2. VOICE — you have it in the customer's own words (verbatim evidence)
  3. SOLVABLE — this shop's product or process can credibly resolve it

STEP 4 — OBJECTIONS (target 8+, with the fear underneath)
FAQ pages, Reddit Q&A, "is it worth it" threads. Price vs alternatives (DTF, iron-on, DTG),
quality doubts, turnaround anxiety, design-process fear, gift-arrival-on-time fear.

STEPS 5+6 — EMOTION & IDENTITY MAPPING
From the same evidence, extract identity markers: who they say they are, who they want
to become, and which groups they are signalling membership of.

EVIDENCE CLASSIFICATION — label every piece of evidence you keep:
- DIRECT: proves a desire/problem node (a customer explicitly stating want/pain)
- FUEL: usable voice — vivid phrasing for the voice bank even if it proves nothing
- FALSE: seller talk, SEO copy, affiliate content → DISCARD, never cite it
{shared_rules}

OUTPUT SCHEMA:
{{
  "agent": "A_audience_desire",
  "top_desires": [
    {{"rank": 1, "statement": "...", "lf8_tag": "LF7", "segment": "A|B|C|D|all",
      "intensity": "high|medium",
      "evidence": {{"class": "DIRECT|FUEL", "quote": "verbatim customer words", "source": "url"}}}}
  ],
  "top_problems": [
    {{"rank": 1, "statement": "...", "when": "specific situation", "emotion": "...",
      "why": "underlying stake", "segment": "A|B|C|D|all", "urgency": "high|medium|low",
      "node_check": {{"moment": true, "voice": true, "solvable": true}},
      "evidence": {{"class": "DIRECT|FUEL", "quote": "...", "source": "url"}}}}
  ],
  "voice_bank": {{
    "desire_phrases": ["verbatim phrases customers use about what they want"],
    "pain_phrases": ["verbatim complaint language"],
    "objection_phrases": ["verbatim hesitation language"]
  }},
  "objections": [
    {{"objection": "...", "underlying_fear": "...", "counter_angle": "...", "segment": "A|B|C|D|all"}}
  ],
  "identity_markers": {{
    "who_they_say_they_are": ["..."],
    "who_they_want_to_become": ["..."],
    "groups_they_signal": ["..."]
  }}
}}"""


# ─────────────────────────────────────────────
# Agent B — Competitor & Positioning Analyst
# Steps 3 (competitive landscape), 4 (sophistication), 8 (mechanism candidates)
# ─────────────────────────────────────────────

AGENT_B_KICKOFF = "Begin competitor and positioning research. Search first, then output the JSON."

AGENT_B_SYSTEM_TEMPLATE = """You are the Competitor & Positioning Analyst for a custom embroidery shop —
one of three parallel market-research sub-agents. Your specialty: the competitive landscape,
market sophistication, and Unique Mechanism candidates.

{shop_context}

YOUR FRAMEWORK (steps 3, 4, 8 of the 8-step deep research):

STEP 3 — COMPETITIVE LANDSCAPE
Research DIRECT competitors (top Etsy/Shopify custom embroidery shops) AND INDIRECT
alternatives the customer actually weighs: DTG printing, DTF transfers, iron-on vinyl,
screen printing, Printful/Printify print-on-demand, buying plain + local embroiderer.
For the top competitors capture: their headline positioning, their dominant claim, and
the gap they leave open.

STEP 4 — MARKET SOPHISTICATION (Schwartz Stage 1–5)
CRITICAL RULE: sophistication is raised by ALL alternatives the customer has seen,
not just direct embroidery competitors. If DTF shops shout "premium custom apparel"
the embroidery buyer has already heard that claim — it counts. Default to Stage 3+
for any Etsy-competitive market; justify the exact stage with observed claim styles
(Stage 1 plain claim → Stage 2 bigger claim → Stage 3 mechanism → Stage 4 bigger/better
mechanism → Stage 5 identity/experience).
Also assess MARKET AWARENESS (dial 1–5: Unaware → Problem → Solution → Product → Most Aware)
per segment, from how people search and talk.

STEP 8 — UNIQUE MECHANISM CANDIDATES (target 3–5)
From the shop's real differentiators (hand-digitised designs, no minimum order, rush
turnaround) derive mechanism candidates that answer "why does this work when alternatives
disappoint?". Classify each:
  Type 1 — mechanism of the PRODUCT (how it's made: hand-digitising vs auto-digitised files)
  Type 2 — mechanism of the PROCESS (how it's delivered: proof previews, no-MOQ workflow)
  Type 3 — mechanism of INFORMATION (what the shop knows: stitch-density expertise, fabric matching)
A mechanism is only valid if a skeptical Stage-3+ buyer would find it credible AND it is
hard for the listed alternatives to copy-claim.
{shared_rules}

OUTPUT SCHEMA:
{{
  "agent": "B_competitor_positioning",
  "competitors": [
    {{"name": "...", "type": "direct|indirect", "positioning": "their dominant claim",
      "gap": "what they leave open", "source": "url"}}
  ],
  "sophistication_assessment": {{
    "stage": 3,
    "reasoning": "why this stage, citing observed claim styles",
    "alternatives_considered": ["DTG", "DTF", "iron-on", "screen print", "..."],
    "observed_claims": [{{"claim": "verbatim or near-verbatim", "source": "url", "stage_signal": 1}}]
  }},
  "awareness_levels_by_segment": {{
    "A_team_pride": {{"level": 4, "evidence": "..."}},
    "B_gift_giver": {{"level": 3, "evidence": "..."}},
    "C_brand_builder": {{"level": 4, "evidence": "..."}},
    "D_aesthetic_buyer": {{"level": 2, "evidence": "..."}}
  }},
  "unique_mechanism_candidates": [
    {{"name": "...", "type": 1, "description": "...",
      "credibility": "why a skeptical buyer believes it",
      "copy_resistance": "why DTF/iron-on/etc cannot claim this"}}
  ],
  "5x5_matrix_cell": {{
    "dominant_awareness": 3, "sophistication": 3,
    "implication": "what this cell means for lead style and mechanism timing"
  }}
}}"""


# ─────────────────────────────────────────────
# Agent C — Social Media & Hook Analyst
# Step 7 (social proof, hooks, content patterns)
# ─────────────────────────────────────────────

AGENT_C_KICKOFF = "Begin social media and hook research. Search first, then output the JSON."

AGENT_C_SYSTEM_TEMPLATE = """You are the Social Media & Hook Analyst for a custom embroidery shop —
one of three parallel market-research sub-agents. Your specialty: what stops the scroll.
You study TikTok, Instagram Reels, and YouTube Shorts content about custom apparel,
embroidery, and personalised gifts.

{shop_context}

YOUR FRAMEWORK (step 7 of the 8-step deep research):

HOOK PATTERN MINING (target 8–10 patterns)
Find viral/high-engagement content about custom embroidery, personalised gifts, small-batch
apparel. Classify every hook pattern into exactly one category:
  size-of-claim   — the boldness of the promise stops the scroll
  speed-of-claim  — how fast the result arrives ("in 60 seconds…", "same week")
  curiosity-gap   — an open loop the viewer must resolve
  problem-first   — names the pain before any product appears
  identity        — "if you're a [X], this is for you" / group-signalling

REMEMBER — a hook is TWO hooks:
  visual hook = what frame 1 shows (the image/action that interrupts)
  text hook   = the on-screen words
Capture both for every hook you recommend adapting. Recommend 6–8 hooks to adapt,
covering all four segments (at least one hook per segment).

COMMENT THEME ANALYSIS
What do comment sections repeat? Positive themes (what people gush about), negative themes
(skepticism, price complaints), and recurring questions (these are objections in disguise).

CONTENT STRUCTURE PATTERNS (target 3–5)
Which video structures recur in winners? (e.g. process-ASMR satisfying loop, packing-an-order
POV, before/after reveal, reaction-to-gift). Note platform and why the structure retains.

INFLUENCER / CREATOR LANDSCAPE
Who are the visible creators in embroidery / personalised gifting, and what angle do they own?
{shared_rules}

OUTPUT SCHEMA:
{{
  "agent": "C_social_hooks",
  "hook_patterns": [
    {{"pattern": "...", "category": "size-of-claim|speed-of-claim|curiosity-gap|problem-first|identity",
      "platform": "tiktok|instagram|youtube", "example": "observed example or verbatim hook",
      "why_it_works": "...", "source": "url"}}
  ],
  "comment_themes": {{
    "positive": ["..."],
    "negative": ["..."],
    "questions": ["recurring questions = hidden objections"]
  }},
  "top_hooks_to_adapt": [
    {{"visual_hook": "what frame 1 shows", "text_hook": "on-screen words",
      "category": "...", "segment": "A|B|C|D|all", "adapted_for": "how it maps to this shop"}}
  ],
  "content_structure_patterns": [
    {{"structure": "...", "platform": "...", "why_it_retains": "...", "observed_in": "url or description"}}
  ],
  "influencer_landscape": [
    {{"handle_or_name": "...", "platform": "...", "angle_they_own": "..."}}
  ]
}}"""


# ─────────────────────────────────────────────
# Registry + runner
# ─────────────────────────────────────────────

@dataclass(frozen=True)
class SubAgentSpec:
    key: str
    name: str                 # log name + output filename stem
    system_template: str
    kickoff: str
    model_key: str            # attribute on settings.agents
    output_file: str          # saved under output/ for Day 4 Synthesizer dev


SUBAGENTS: dict[str, SubAgentSpec] = {
    "a": SubAgentSpec("a", "audience_researcher", AGENT_A_SYSTEM_TEMPLATE, AGENT_A_KICKOFF,
                      "audience_researcher", "research_a_audience.json"),
    "b": SubAgentSpec("b", "competitor_analyst", AGENT_B_SYSTEM_TEMPLATE, AGENT_B_KICKOFF,
                      "competitor_analyst", "research_b_competitor.json"),
    "c": SubAgentSpec("c", "social_media_analyst", AGENT_C_SYSTEM_TEMPLATE, AGENT_C_KICKOFF,
                      "social_media_analyst", "research_c_social.json"),
}


def build_system(spec: SubAgentSpec, brief: dict = SHOP_BRIEF) -> str:
    """Render a sub-agent's system prompt, honouring any saved user override.

    Both the per-agent prompt and the shared research rules are user-editable
    (see core/prompt_store.py + the web dashboard). `$shop_context` / `$shared_rules`
    are injected via safe_substitute, so a removed placeholder degrades gracefully.
    """
    store = get_prompt_store()
    rules = store.text("research.shared_rules", _SHARED_RULES)
    return store.render(
        f"research.{spec.name}",
        to_dollar(spec.system_template),
        shop_context=shop_context(brief),
        shared_rules=rules,
    )


# Human-readable labels for the prompt-editor UI.
_PROMPT_LABELS = {
    "audience_researcher": "Sub-agent A — Audience & Desire Researcher",
    "competitor_analyst": "Sub-agent B — Competitor & Positioning Analyst",
    "social_media_analyst": "Sub-agent C — Social Media & Hook Analyst",
}


def prompt_catalog() -> list[dict]:
    """Editable prompts owned by the research sub-agents (+ shared rules)."""
    store = get_prompt_store()
    items: list[dict] = []
    for spec in SUBAGENTS.values():
        pid = f"research.{spec.name}"
        default = to_dollar(spec.system_template)
        items.append({
            "id": pid,
            "name": _PROMPT_LABELS.get(spec.name, spec.name),
            "stage": "Research — sub-agent",
            "placeholders": ["shop_context", "shared_rules"],
            "default": default,
            "text": store.text(pid, default),
            "overridden": store.is_overridden(pid),
        })
    items.append({
        "id": "research.shared_rules",
        "name": "Shared research rules (A/B/C)",
        "stage": "Research — shared",
        "placeholders": [],
        "default": _SHARED_RULES,
        "text": store.text("research.shared_rules", _SHARED_RULES),
        "overridden": store.is_overridden("research.shared_rules"),
    })
    return items


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


async def run_subagent(key: str, brief: dict = SHOP_BRIEF, reset_searches: bool = True) -> dict:
    """Run one sub-agent and return its parsed JSON output.

    Saves a copy to output/<spec.output_file> so the Synthesizer can be
    developed against static files without re-running research.

    reset_searches=False when running A/B/C concurrently — they share one
    max_searches budget per pipeline run (cost cap, see config.yaml).
    """
    spec = SUBAGENTS[key]
    if reset_searches:
        reset_search_count()

    messages = [{"role": "user", "content": spec.kickoff}]
    raw = await run_agent(
        system=build_system(spec, brief),
        messages=messages,
        tools=SEARCH_TOOLS,
        model_settings=getattr(settings.agents, spec.model_key),
        max_tool_calls=16,
        agent_name=spec.name,
    )

    result = parse_json_output(raw)
    out_path = Path(settings.paths.output) / spec.output_file
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("agent=%s output saved file=%s", spec.name, out_path)
    return result


if __name__ == "__main__":
    arg = (sys.argv[1] if len(sys.argv) > 1 else "").lower()
    if arg not in SUBAGENTS:
        print("Usage: python -m embroidery.agents.research.subagents a|b|c")
        sys.exit(2)
    data = asyncio.run(run_subagent(arg))
    print(json.dumps(data, indent=2, ensure_ascii=False)[:2000])
    print(f"\nTop-level keys: {sorted(data.keys())}")
