"""
Agent 1 Synthesizer — merges the three sub-agent research outputs (A/B/C)
into the two Stage 1 data-contract files (Day 4 of the development plan):

  market_research_report.json   structured data → Agents 2, 3
  brand_intelligence_report.md  narrative report → Agents 2, 3 + human review

The Synthesizer has NO tools — pure synthesis. It runs twice on
settings.agents.synthesizer (gemini-2.5-pro for report quality):
  call 1 → the JSON report (returned as final text, parsed in Python)
  call 2 → the markdown narrative (written from the JSON + raw sub-agent evidence)
Python writes both files; the model never emits large tool payloads.

Run standalone against the static Day 3 outputs in output/ (no new searches):
    cd embroidery && venv/bin/python agent1_synthesizer.py
"""

import asyncio
import json
from datetime import date
from pathlib import Path

from agent1_subagents import SHOP_BRIEF, parse_json_output, shop_context
from agent_loop import run_agent
from config import settings
from logger import get_logger

log = get_logger(__name__)

# ─────────────────────────────────────────────
# Call 1 — structured JSON report
# ─────────────────────────────────────────────

SYNTH_JSON_SYSTEM_TEMPLATE = """You are the Research Synthesizer for a custom embroidery shop —
the final stage of a 3-agent market research pipeline. You receive the JSON outputs of:
  Agent A — Audience & Desire Researcher (desires, problems, objections, voice bank, identity)
  Agent B — Competitor & Positioning Analyst (competitors, sophistication, awareness, mechanisms)
  Agent C — Social Media & Hook Analyst (hook patterns, comment themes, content structures)

{shop_context}

YOUR JOB: cross-reference all three sources and produce ONE master research JSON.

SYNTHESIS RULES:
- RANK by frequency × intensity: an insight appearing in two or three sources outranks
  a single-source insight; within equal frequency, higher emotional intensity wins.
- CROSS-REFERENCE: C's comment themes confirm or amplify A's desires/problems; C's recurring
  questions are objections — merge them into the objections list; B's awareness evidence
  refines segment assignments.
- DIMENSIONALIZE to reach targets — this is REQUIRED, not optional. For each evidenced core
  desire, write the segment-specific variants as SEPARATE ranked entries: "make my team look
  legit" (A), "give a gift that proves I paid attention" (B), "make my small business look
  established" (C), "wear something no one else has" (D) are four desires, not one. The same
  verbatim quote may back several derived entries. Do the same for problems (the same delay
  hurts a gift-giver and a team captain differently). That is how ~12 evidenced desires become
  30 — by segment and altitude, NEVER by invention.
- OBJECTIONS COME FROM THREE PLACES — merge all of them: A's objections list, C's recurring
  comment questions (every recurring question is an objection in disguise), and B's
  price/quality tensions vs alternatives (DTF, iron-on, DTG, screen print).
- NEVER FABRICATE: every quote stays verbatim from the sub-agent evidence, with its source.
  Derived entries reuse real quotes; only if a section genuinely cannot reach its MINIMUM
  after full segment expansion, deliver fewer and explain in coverage_gaps.

SECTION TARGETS (target — hard minimum):
- desires: 30 — at least 24      - problems: 20 — at least 14
- hooks: 20 — at least 14        - objections: 15 — at least 12
- buzzwords: 20+ — at least 16   - success_patterns: 15+ — at least 10
The sub-agent material always supports the minimums once expanded per segment — falling
short means you skipped the dimensionalization step.

FRAMEWORK SECTIONS (definitions):
- desire_map (at least 8 entries — minimum the top 2 desires of EACH segment): each desire
  mapped UP (the identity/transformation it ladders to — who the buyer becomes) and DOWN
  (the concrete, photographable moment that proves it).
- yes_stack: 6–10 statements the target customer already believes, ordered so each "yes"
  makes the next easier — ending one step before the pitch.
- bright_dark_side (at least 6 entries, covering all 4 segments): for each top desire, the
  bright side (aspirational framing) and the dark side (the pain/fear of NOT having it) —
  both in customer-flavoured language.
- belief_mechanisms: the proof elements that make claims believable (process video,
  before/after, UGC reactions, reviews citing specifics).

OUTPUT DISCIPLINE:
- Your FINAL message must be ONLY a single JSON object matching the schema below.
- No markdown fences, no commentary. All strings in English.

OUTPUT SCHEMA:
{{
  "shop": {{"name": "...", "research_date": "{research_date}"}},
  "segments": {{
    "A_team_pride":     {{"awareness_level": 1, "sophistication_stage": 1, "size": "large|medium|small", "evidence": "..."}},
    "B_gift_giver":     {{...same...}},
    "C_brand_builder":  {{...same...}},
    "D_aesthetic_buyer": {{...same...}}
  }},
  "desires": [
    {{"rank": 1, "statement": "...", "lf8_tag": "LF7", "segment": "A|B|C|D|all",
      "intensity": "high|medium", "sources_agreeing": 2,
      "evidence": {{"quote": "verbatim", "source": "url"}}}}
  ],
  "problems": [
    {{"rank": 1, "statement": "...", "when": "...", "emotion": "...", "why": "...",
      "segment": "A|B|C|D|all", "urgency": "high|medium|low",
      "evidence": {{"quote": "verbatim", "source": "url"}}}}
  ],
  "hooks": [
    {{"rank": 1, "visual_hook": "frame 1", "text_hook": "on-screen words",
      "category": "size-of-claim|speed-of-claim|curiosity-gap|problem-first|identity",
      "segment": "A|B|C|D|all", "adapted_from": "observed pattern or source"}}
  ],
  "objections": [
    {{"objection": "...", "underlying_fear": "...", "counter": "...", "segment": "A|B|C|D|all"}}
  ],
  "market_sophistication": {{
    "stage": 3, "reasoning": "...",
    "observed_claims": [{{"claim": "...", "source": "url", "stage_signal": 1}}]
  }},
  "desire_map": [
    {{"desire": "...", "up": "identity/transformation it ladders to",
      "down": "concrete photographable moment", "segment": "A|B|C|D|all"}}
  ],
  "yes_stack": ["belief 1 ...", "belief 2 ..."],
  "bright_dark_side": [
    {{"desire": "...", "bright": "...", "dark": "...", "segment": "A|B|C|D|all"}}
  ],
  "unique_mechanism_candidates": [
    {{"name": "...", "type": 1, "description": "...", "credibility": "...", "copy_resistance": "..."}}
  ],
  "belief_mechanisms": ["..."],
  "buzzwords": ["..."],
  "success_patterns": ["..."],
  "voice_bank": {{
    "desire_phrases": ["verbatim"], "pain_phrases": ["verbatim"], "objection_phrases": ["verbatim"]
  }},
  "coverage_gaps": ["sections where evidence fell short of target and what extra research would fill it"]
}}"""

SYNTH_JSON_KICKOFF_TEMPLATE = """Here are the three sub-agent research outputs. Synthesize them into the master research JSON.

=== AGENT A — AUDIENCE & DESIRE ===
{research_a}

=== AGENT B — COMPETITOR & POSITIONING ===
{research_b}

=== AGENT C — SOCIAL MEDIA & HOOKS ===
{research_c}"""


# ─────────────────────────────────────────────
# Call 2 — narrative markdown report
# ─────────────────────────────────────────────

SYNTH_MD_SYSTEM_TEMPLATE = """You are the Research Synthesizer for a custom embroidery shop, now writing
the brand intelligence report — the long-form narrative a human strategist will read for 1–4 hours
before any ad is written. You receive the synthesized master research JSON plus the three raw
sub-agent outputs (for extra verbatim evidence).

{shop_context}

WRITE A THOROUGH MARKDOWN REPORT with exactly these sections:

# Brand Intelligence Report — {shop_name}
1. **Executive Summary** — market opportunity, the single recommended positioning, top 3 moves
2. **Market Sophistication & Awareness** — Schwartz stage with observed-claim evidence; the
   awareness dial per segment; what the 5×5 cell implies for lead style and mechanism timing
3. **Segment Profiles** (one subsection per segment A–D) — desires, problems (WHEN+WHY),
   identity markers, awareness level, what an ad must do first for this segment
4. **Desire Map** — top desires mapped UP (identity) and DOWN (concrete moment), bright/dark side
5. **Competitive Landscape** — direct + indirect competitors, their dominant claims, the gaps;
   why each indirect alternative (DTF, DTG, iron-on, screen print) wins or loses
6. **Unique Mechanism Candidates** — each with type (1/2/3), credibility logic, copy-resistance
7. **Hook Strategies by Segment** — visual + text hook pairs, category, why they fit the
   segment's awareness level
8. **Objection Handling Guide** — objection → underlying fear → counter, ordered by frequency
9. **Yes Stack** — the belief ladder, with one line on why each step is already believed
10. **Customer Language Bank** — buzzwords, desire/pain/objection phrases (verbatim, quoted),
    success story patterns
11. **Recommended Messaging Angles** — 5–8 concrete ad angles tying segment × desire ×
    mechanism × hook category together
12. **Evidence Appendix** — every verbatim quote used, with source URL
13. **Coverage Gaps** — where evidence was thin and what to research next

WRITING RULES:
- Long-form and specific: every claim cites its evidence (quote or source) inline.
- Customer quotes stay VERBATIM and in "quotes", with the source URL.
- No filler ("in today's fast-paced world…") — a strategist reads this, not a search engine.
- Use tables where they compress (segment comparisons, competitor matrix, objection guide).
- Output ONLY the markdown document — no preamble, no fences around the whole document."""

SYNTH_MD_KICKOFF_TEMPLATE = """Write the brand intelligence report from this research.

=== MASTER RESEARCH JSON (synthesized) ===
{report_json}

=== RAW AGENT A (extra verbatim evidence) ===
{research_a}

=== RAW AGENT B ===
{research_b}

=== RAW AGENT C ===
{research_c}"""


# ─────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────

async def run_synthesizer(
    research_a: dict, research_b: dict, research_c: dict, brief: dict = SHOP_BRIEF
) -> tuple[dict, str]:
    """Two no-tool synthesis calls: (master report dict, markdown narrative)."""
    ctx = shop_context(brief)
    model = settings.agents.synthesizer

    raw = await run_agent(
        system=SYNTH_JSON_SYSTEM_TEMPLATE.format(
            shop_context=ctx, research_date=date.today().isoformat()
        ),
        messages=[{"role": "user", "content": SYNTH_JSON_KICKOFF_TEMPLATE.format(
            research_a=json.dumps(research_a, indent=2, ensure_ascii=False),
            research_b=json.dumps(research_b, indent=2, ensure_ascii=False),
            research_c=json.dumps(research_c, indent=2, ensure_ascii=False),
        )}],
        tools=[],
        model_settings=model,
        agent_name="synthesizer_json",
    )
    report = parse_json_output(raw)
    log.info("agent=synthesizer_json sections=%d desires=%d problems=%d hooks=%d",
             len(report), len(report.get("desires", [])),
             len(report.get("problems", [])), len(report.get("hooks", [])))

    markdown = await run_agent(
        system=SYNTH_MD_SYSTEM_TEMPLATE.format(shop_context=ctx, shop_name=brief["name"]),
        messages=[{"role": "user", "content": SYNTH_MD_KICKOFF_TEMPLATE.format(
            report_json=json.dumps(report, indent=2, ensure_ascii=False),
            research_a=json.dumps(research_a, indent=2, ensure_ascii=False),
            research_b=json.dumps(research_b, indent=2, ensure_ascii=False),
            research_c=json.dumps(research_c, indent=2, ensure_ascii=False),
        )}],
        tools=[],
        model_settings=model,
        agent_name="synthesizer_md",
    )
    markdown = markdown.strip()
    if markdown.startswith("```"):  # tolerate a fenced whole-document response
        markdown = markdown.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    log.info("agent=synthesizer_md chars=%d", len(markdown))
    return report, markdown


def _load_static_research() -> tuple[dict, dict, dict]:
    """Load the saved sub-agent outputs from output/ (no new searches)."""
    out = Path(settings.paths.output)
    return tuple(
        json.loads((out / f).read_text(encoding="utf-8"))
        for f in ("research_a_audience.json", "research_b_competitor.json", "research_c_social.json")
    )


if __name__ == "__main__":
    a, b, c = _load_static_research()
    report, md = asyncio.run(run_synthesizer(a, b, c))
    out = Path(settings.paths.output)
    (out / "market_research_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "brand_intelligence_report.md").write_text(md, encoding="utf-8")
    print(f"Wrote {out / 'market_research_report.json'} and {out / 'brand_intelligence_report.md'}")
    print(f"Report sections: {sorted(report.keys())}")
