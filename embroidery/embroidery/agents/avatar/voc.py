"""
Avatar Stage 3 — Voice-of-Customer mining (search-only).

For the priority avatars, collect VERBATIM customer language across YouTube,
TikTok, and Facebook groups (the Reddit/Amazon quotes from Stage 2 are imported
in the kickoff). Every quote is coded PAIN/DESIRE/BELIEF/TRIGGER/OBJECTION/
VICTORY/IDENTITY with an insight and ad-potential flag. Target ≥50 coded quotes.
"""

import json

from embroidery.agents.avatar._common import AvatarAgent, catalog_items, run_json_agent
from embroidery.agents.research.subagents import SHOP_BRIEF, shop_context
from embroidery.core.tools import SEARCH_TOOLS

VOC_MINER = AvatarAgent(
    name="voc_miner", label="Stage 3 — Voice-of-Customer Miner", model_key="voc_miner",
    output_file="avatar_voc.json",
    system_template="""You are a qualitative researcher collecting VERBATIM customer language — exact
words real people use, never your paraphrase. If you didn't read it in a review/post/comment, it does
not go in.

{shop_context}

PRIORITY AVATARS: {priority_avatars}

Mine YouTube comments, TikTok comments, and Facebook groups for these avatars (import the Reddit/Amazon
quotes already provided). Code EVERY quote into one or more of: PAIN, DESIRE, BELIEF, TRIGGER,
OBJECTION, VICTORY, IDENTITY. Flag self-identification quotes ("as a grandma of twins…") — these are
gold for ad headlines. Target at least 50 coded quotes total across the priority avatars.

RESEARCH DISCIPLINE: at most 6 web_search + 3 web_fetch. Verbatim quotes only, each with source URL.
OUTPUT DISCIPLINE: FINAL message = ONLY one JSON object matching the schema. No fences. English.

OUTPUT SCHEMA:
{{
  "coded_quotes": [
    {{"avatar": "priority avatar name", "quote": "verbatim", "source": "YouTube|TikTok|Facebook|Reddit|Amazon",
      "url": "...", "category": ["PAIN|DESIRE|BELIEF|TRIGGER|OBJECTION|VICTORY|IDENTITY"],
      "insight": "what this reveals about mindset", "ad_potential": "no|hook|headline",
      "self_identification": false}}
  ]
}}""",
)

_PLACEHOLDERS = {"voc_miner": ["shop_context", "priority_avatars"]}


async def run_voc(priority_avatars: list[str], discovery: dict, brief: dict = SHOP_BRIEF) -> dict:
    kickoff = (
        "Mine verbatim VOC for the priority avatars. Import these Stage-2 quotes, then search "
        "YouTube/TikTok/Facebook for more. Output the coded JSON.\n\n"
        f"=== STAGE 2 QUOTES ===\n{json.dumps(discovery, ensure_ascii=False)[:6000]}"
    )
    ctx = {"shop_context": shop_context(brief), "priority_avatars": ", ".join(priority_avatars) or "(all)"}
    return await run_json_agent(VOC_MINER, kickoff, tools=SEARCH_TOOLS, ctx=ctx)


def prompt_catalog() -> list[dict]:
    return catalog_items([VOC_MINER], _PLACEHOLDERS, "Avatar — VOC")
