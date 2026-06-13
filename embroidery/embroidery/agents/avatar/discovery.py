"""
Avatar Stage 2 — Avatar Discovery & Qualification.

Three SEARCH-ONLY scouts run in parallel, each adapted to the shop's four
segments (A Team Pride · B Gift Giver · C Brand Builder · D Aesthetic Buyer):
  reddit_scout — site:reddit.com clusters by shared struggle
  amazon_voc   — Amazon/Etsy review VOC + competitor failure modes
  fb_ad_scout  — facebook.com/ads/library: competitor ads + sophistication + avatar gaps
Then avatar_qualifier (NO TOOLS) scores candidates on the Evolve 4-gate framework
and selects the top `priority_count`.
"""

import asyncio

from embroidery.agents.avatar._common import AvatarAgent, catalog_items, run_json_agent
from embroidery.agents.research.subagents import SHOP_BRIEF, shop_context
from embroidery.core.config import settings
from embroidery.core.tools import SEARCH_TOOLS

_DISCOVERY_RULES = """RESEARCH DISCIPLINE:
- ALL findings must come from real search results — never invent quotes, reviews, names, or ads.
- Budget: at most 6 web_search + 3 web_fetch calls. Prefer site:reddit.com / site:amazon.com /
  facebook.com/ads/library queries that surface real customer language.
- Quotes are VERBATIM from snippets/fetched pages, each with its source URL.
- FINAL message = ONLY one JSON object matching the schema. No fences, no commentary. English."""

REDDIT_SCOUT = AvatarAgent(
    name="reddit_scout", label="Stage 2A — Reddit Avatar Scout", model_key="reddit_scout",
    output_file="avatar_discovery_reddit.json",
    system_template="""You are a market researcher finding real customer sub-avatars by how people
cluster themselves by SHARED STRUGGLE — not by guessing demographics.

{shop_context}

Search site:reddit.com for communities discussing custom embroidery, personalised gifts,
team/club apparel, small-business merch, and embroidery-as-fashion. For each relevant post/comment,
infer who the person is, their occasion, the struggle they share, and record verbatim quotes.
Group people into sub-avatar clusters (by occasion / role / emotional need), mapped to segments A–D.
{rules}

OUTPUT SCHEMA:
{{
  "clusters": [
    {{"cluster_name": "...", "segment": "A|B|C|D", "who_they_are": "...",
      "their_occasion": "...", "dominant_emotion": "...", "estimated_size": "large|medium|small",
      "verbatim_quotes": [{{"quote": "...", "source": "url"}}]}}
  ]
}}""".replace("{rules}", _DISCOVERY_RULES),
)

AMAZON_VOC = AvatarAgent(
    name="amazon_voc", label="Stage 2B — Amazon/Etsy VOC Scout", model_key="amazon_voc",
    output_file="avatar_discovery_amazon.json",
    system_template="""You are a voice-of-customer analyst mining Amazon/Etsy reviews for avatar signals.

{shop_context}

Search for the top custom-embroidery / personalised-apparel products by review count. From recent +
most-helpful reviews extract: WHO writes them, WHAT triggered the purchase (gift vs self, occasion),
VERBATIM emotional language, recurring buzzwords (3+ times), price-sensitivity signals, and
COMPETITOR FAILURE MODES from 1–2★ reviews (delivery, quality, wrong info, packaging).
{rules}

OUTPUT SCHEMA:
{{
  "buyer_types": ["..."],
  "top_occasions": ["..."],
  "emotional_language": [{{"quote": "...", "source": "url"}}],
  "buzzwords": ["..."],
  "competitor_gaps": [{{"complaint": "verbatim", "source": "url"}}],
  "price_sensitivity_signals": ["..."]
}}""".replace("{rules}", _DISCOVERY_RULES),
)

FB_AD_SCOUT = AvatarAgent(
    name="fb_ad_scout", label="Stage 2C — Facebook Ad Library Scout", model_key="fb_ad_scout",
    output_file="avatar_discovery_fb.json",
    system_template="""You are a competitive-intelligence analyst scanning the Facebook Ad Library
(https://www.facebook.com/ads/library/) for custom embroidery / personalised gift / custom apparel ads.

{shop_context}

Fetch ad-library result pages (best-effort). For each ad: describe the creative (who/emotion/setting),
copy the headline + primary text verbatim, identify the targeted avatar, estimate run-length (longer =
working), and rate sophistication S1–S5 (S1 plain claim → S2 bigger claim → S3 new mechanism →
S4 bigger mechanism → S5 identity/persona). Then do an AVATAR-GAP analysis.
{rules}

OUTPUT SCHEMA:
{{
  "active_ads_found": 0,
  "ads": [
    {{"creative": "...", "headline": "...", "primary_text": "...", "targeted_avatar": "...",
      "run_length_signal": "...", "sophistication": "S1|S2|S3|S4|S5", "source": "url"}}
  ],
  "avatars_being_targeted": ["..."],
  "under_served_avatars": ["..."],
  "dominant_sophistication_stage": "S1|S2|S3|S4|S5"
}}""".replace("{rules}", _DISCOVERY_RULES),
)

QUALIFIER = AvatarAgent(
    name="avatar_qualifier", label="Stage 2D — Avatar Qualification (4-gate)", model_key="avatar_qualifier",
    output_file="avatar_qualification.json",
    system_template="""You qualify sub-avatar candidates collected from Reddit, Amazon/Etsy, and the
Facebook Ad Library, using the Evolve 4-gate framework. You have NO tools — reason over the data given.

{shop_context}

You will receive the three discovery JSON blobs plus the market research report. Build a candidate
list (merge/dedupe clusters across sources) and score EACH candidate 1–5 on every gate:
  GATE 1 DESIRE MAGNITUDE — burning, identity-level desire = 5; nice-to-have = 1
  GATE 2 COMPETITION (inverted) — under-served (few ads) = 5; saturated = 1
  GATE 3 ECONOMIC ABILITY — price is trivial / gift-budget = 5; price is a barrier = 1
  GATE 4 SCALABILITY — millions enter the segment yearly = 5; <100k addressable = 1
total = sum (max 20). verdict = "PASS" if all four ≥3, "FAIL" if any <2, else "MAYBE".
Rank by total, then select the top {priority_count} PASS candidates as priority_avatars.

OUTPUT DISCIPLINE: FINAL message = ONLY one JSON object matching the schema. No fences. English.

OUTPUT SCHEMA:
{{
  "candidates": [
    {{"name": "...", "segment": "A|B|C|D", "desire": 1, "competition": 1, "economic": 1,
      "scalability": 1, "total": 4, "verdict": "PASS|FAIL|MAYBE",
      "rationale": "one line citing the evidence"}}
  ],
  "priority_avatars": ["candidate name 1", "candidate name 2"]
}}""",
)

_SCOUTS = [REDDIT_SCOUT, AMAZON_VOC, FB_AD_SCOUT]
_PLACEHOLDERS = {
    "reddit_scout": ["shop_context"], "amazon_voc": ["shop_context"], "fb_ad_scout": ["shop_context"],
    "avatar_qualifier": ["shop_context", "priority_count"],
}


async def run_discovery(brief: dict = SHOP_BRIEF) -> dict:
    """Run the three scouts in parallel (sharing the per-run search budget)."""
    ctx = {"shop_context": shop_context(brief)}
    reddit, amazon, fb = await asyncio.gather(
        run_json_agent(REDDIT_SCOUT, "Find Reddit sub-avatar clusters. Search first, then JSON.",
                       tools=SEARCH_TOOLS, ctx=ctx),
        run_json_agent(AMAZON_VOC, "Mine Amazon/Etsy reviews. Search first, then JSON.",
                       tools=SEARCH_TOOLS, ctx=ctx),
        run_json_agent(FB_AD_SCOUT, "Scan the FB Ad Library. Fetch first, then JSON.",
                       tools=SEARCH_TOOLS, ctx=ctx),
    )
    return {"reddit": reddit, "amazon": amazon, "fb": fb}


async def run_qualify(discovery: dict, research_report: dict, brief: dict = SHOP_BRIEF) -> dict:
    import json
    kickoff = (
        "Qualify these candidates and select the priority avatars.\n\n"
        f"=== REDDIT ===\n{json.dumps(discovery.get('reddit', {}), ensure_ascii=False)}\n\n"
        f"=== AMAZON/ETSY ===\n{json.dumps(discovery.get('amazon', {}), ensure_ascii=False)}\n\n"
        f"=== FB AD LIBRARY ===\n{json.dumps(discovery.get('fb', {}), ensure_ascii=False)}\n\n"
        f"=== MARKET RESEARCH REPORT (segments/awareness/sophistication) ===\n"
        f"{json.dumps(research_report, ensure_ascii=False)[:6000]}"
    )
    ctx = {"shop_context": shop_context(brief), "priority_count": str(settings.avatar.priority_count)}
    return await run_json_agent(QUALIFIER, kickoff, tools=[], ctx=ctx)


def prompt_catalog() -> list[dict]:
    return catalog_items(_SCOUTS + [QUALIFIER], _PLACEHOLDERS, "Avatar — discovery")
