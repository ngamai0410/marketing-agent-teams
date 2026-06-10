"""
Agent 1: Market Research

EcomTalent 8-step deep market research for a custom embroidery shop.
Produces two output files consumed by Agents 2 and 3:
  - market_research_report.json  (structured data)
  - brand_intelligence_report.md (narrative synthesis)

Run:
    cd embroidery && venv/bin/python agent1_market_research.py
"""

import asyncio
from agent_loop import run_agent, reset_search_count
from config import settings
from tools import RESEARCH_TOOLS

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

SYSTEM_PROMPT = f"""You are an expert market research analyst for a custom embroidery shop.

SHOP CONTEXT:
Name: {SHOP_BRIEF["name"]}
URL: {SHOP_BRIEF["url"]}
Top products: {", ".join(SHOP_BRIEF["top_products"])}
Price range: {SHOP_BRIEF["price_range"]}
Turnaround: {SHOP_BRIEF["turnaround"]}
Differentiator: {SHOP_BRIEF["differentiator"]}

YOUR JOB:
Execute the EcomTalent 8-step Deep Market Research framework using web_search and web_fetch.
ALL insights must come from actual search results — do not hallucinate data.

RESEARCH FRAMEWORK (execute in this order):

STEP 1 — TOP 30 DESIRE STATEMENTS (ranked by emotional intensity)
Search: customer reviews on Etsy, Reddit posts, TikTok comments about custom embroidery.
What does the ideal customer REALLY want beyond "custom embroidery"?
Focus on transformation desires: belonging, identity, gift-giving love, team pride, status.

STEP 2 — PROBLEM STATEMENTS (ranked by urgency and pain intensity)
Search: complaints, 1–3 star reviews, Reddit rants about custom embroidery shops.
What frustrates buyers? Common pain points: price, turnaround, quality, MOQ, design process.

STEP 3 — TOP 20 HOOK IDEAS adaptable to embroidery ads
Search: viral TikTok and Instagram ads for custom apparel and embroidery.
What scroll-stopping angles are working? Pattern-interrupt hooks, identity hooks, social-proof hooks.

STEP 4 — 15–20 COMMON OBJECTIONS + counter-strategies
Search: FAQ sections of top Etsy embroidery shops, Reddit Q&A threads.
Objections: price vs alternatives (DTF, iron-on), quality doubts, turnaround anxiety, design process fear.

STEP 5 — MARKET SOPHISTICATION assessment (Schwartz Stage 1–5)
Research how many competitors exist, how saturated "custom" / "personalised" messaging is.
Default Stage 3+ for any market with strong Etsy competition.

STEP 6 — MARKET AWARENESS per segment (dial 1–5)
For each of the 4 segments below, assess where they sit on the awareness spectrum.

STEP 7 — TOP 10 BELIEF-DRIVING MECHANISMS
What proof elements make customers believe the quality claim? (Before/after photos, UGC, celebrity use, etc.)

STEP 8 — 20+ NICHE BUZZWORDS + 15+ customer success story patterns
Search: positive reviews, testimonial language, social media captions about embroidery gifts.

TARGET SEGMENTS (research each separately):
- Segment A "Team Pride": clubs, sports teams, school groups (bulk orders, team identity)
- Segment B "Gift Giver": personal occasions — weddings, graduations, pet memorials, baby gifts
- Segment C "Brand Builder": small businesses ordering uniforms, merch, employee gifts
- Segment D "Aesthetic Buyer": TikTok/Instagram-native, "quiet luxury", embroidery as fashion

REQUIRED SEARCHES (do all of these):
1. web_search("custom embroidery Etsy reviews complaints site:reddit.com")
2. web_search("custom embroidery shop Etsy best seller reviews 2024 2025")
3. web_search("custom embroidery gift ideas trending TikTok 2024 2025")
4. web_search("personalised embroidery hoodie hat review Reddit")
5. web_search("custom team embroidery bulk order problems Reddit")
6. web_search("embroidery vs DTF vs screen print customer opinion Reddit")
7. web_search("custom embroidery small business uniform Etsy reviews")
8. web_search("embroidered baby gift personalised keepsake reviews Etsy")
9. web_search("quiet luxury embroidery aesthetic TikTok trend 2024 2025")
10. web_search("custom embroidery competitor analysis Etsy top shops")

After searching, use web_fetch to read 3–5 of the most relevant pages (Reddit threads or Etsy reviews).

OUTPUT INSTRUCTIONS:
First, write a file called "market_research_report.json" with this exact structure:
{{
  "shop": {{"name": "...", "research_date": "YYYY-MM-DD"}},
  "segments": {{
    "A_team_pride": {{"awareness_level": 1-5, "sophistication_stage": 1-5, "size": "large|medium|small"}},
    "B_gift_giver": {{"awareness_level": 1-5, "sophistication_stage": 1-5, "size": "..."}},
    "C_brand_builder": {{"awareness_level": 1-5, "sophistication_stage": 1-5, "size": "..."}},
    "D_aesthetic_buyer": {{"awareness_level": 1-5, "sophistication_stage": 1-5, "size": "..."}}
  }},
  "desires": [{{"rank": 1, "statement": "...", "segment": "A|B|C|D|all", "intensity": "high|medium"}}],
  "problems": [{{"rank": 1, "statement": "...", "segment": "...", "urgency": "high|medium|low"}}],
  "hooks": [{{"rank": 1, "hook": "...", "type": "identity|social_proof|pattern_interrupt|curiosity", "segment": "..."}}],
  "objections": [{{"objection": "...", "counter": "...", "segment": "..."}}],
  "market_sophistication": 3,
  "belief_mechanisms": ["..."],
  "buzzwords": ["..."],
  "success_patterns": ["..."]
}}

Then write a file called "brand_intelligence_report.md" — a narrative synthesis covering:
1. Executive Summary (market opportunity and recommended positioning)
2. Segment-by-segment profiles (desires, problems, awareness/sophistication assessment)
3. Competitive landscape (top 5 competitors, their messaging, their gaps)
4. Hook strategies by segment
5. Objection handling guide
6. Recommended messaging angles for paid ads
7. Key buzzwords and customer language to use

Be specific. Every claim must cite a source (Reddit thread, Etsy listing, search result).
"""


async def run_market_research() -> dict[str, str]:
    """Run Agent 1 and return paths to the two output files."""
    reset_search_count()

    model = settings.agents.audience_researcher  # gemini-2.5-flash — validate here first
    messages = [{"role": "user", "content": "Begin the market research. Execute all steps in order."}]

    result = await run_agent(
        system=SYSTEM_PROMPT,
        messages=messages,
        tools=RESEARCH_TOOLS,
        model_settings=model,
        max_tool_calls=60,
        agent_name="market_research",
    )

    print(f"\nAgent 1 complete.\n{result[:500]}{'...' if len(result) > 500 else ''}")
    return {
        "market_research_report": f"{settings.paths.output}/market_research_report.json",
        "brand_intelligence_report": f"{settings.paths.output}/brand_intelligence_report.md",
    }


if __name__ == "__main__":
    asyncio.run(run_market_research())
