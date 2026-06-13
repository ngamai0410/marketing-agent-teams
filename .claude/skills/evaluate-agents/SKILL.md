---
name: evaluate-agents
description: Evaluate performance of each market-research pipeline agent (sub-agents A/B/C and the Synthesizer) from the latest run's output files and logs. Each agent is graded in a FRESH subagent so raw JSON/log bulk never enters the main context — only compact scorecards come back. Use after running the research pipeline (python -m embroidery.agents.research.pipeline), or when asked "how did the agents perform", "đánh giá agent", "grade the research run".
---

# Evaluate Agents

Grade each pipeline agent against the targets hardcoded in its own system prompt, using only that agent's artifacts. **Context discipline is the point of this skill**: the main conversation must never hold full sub-agent JSON or full log files — one evaluator subagent per pipeline agent, each returning a ≤25-line scorecard, then synthesize.

Optional argument: an agent key (`a`, `b`, `c`, `synth`) to evaluate just one; default is all four.

## Step 1 — Locate artifacts (main thread, cheap)

Run small shell commands only — never Read the big files in the main thread:

```bash
# newest pipeline log = the one containing the pipeline-done line
grep -l "market_research pipeline done" embroidery/data/logs/*.log | tail -1
ls -la embroidery/data/output/research_*.json embroidery/data/output/market_research_report.json embroidery/data/output/brand_intelligence_report.md
```

If no pipeline log or outputs exist, say so and stop — do not grade stale files from different runs (compare file mtimes against the log timestamp; warn if they differ by more than the run duration).

Extract ONLY the per-agent summary lines from the log (this is the main thread's entire view of the log):

```bash
LOG=<path from above>
grep -E "agent=(audience_researcher|competitor_analyst|social_media_analyst|synthesizer_json|synthesizer_md) (done|.*starting)|search_limit|agent_search_limit|sections=|chars=" "$LOG"
```

## Step 2 — One fresh evaluator subagent per pipeline agent

Launch evaluator subagents (subagent_type: `general-purpose`) — they can run concurrently in one message since they are independent. Each prompt must be **self-contained**: include the rubric below verbatim for that agent, the artifact path(s), the log summary lines for that agent only, and the required output format. Do NOT pass other agents' data — that is the truncation contract.

Each evaluator must return EXACTLY this compact format (≤25 lines, no file dumps, no quotes longer than one line):

```
AGENT: <name>
SCORE: <x>/10
TARGETS: <section>: <actual>/<target> <✅|⚠️|❌>  (one line per section)
EVIDENCE: <n> unique sources; <n> junk/SEO sources (list domains only); verbatim+URL compliance <ok|issues>
EFFICIENCY: calls=<n> tokens_in=<n> tokens_out=<n> searches=<used>/<cap> duration≈<s>
TOP 3 ISSUES: numbered, one line each
ONE FIX: the single highest-leverage prompt/code change
```

### Rubric — Agent A (audience_researcher), file `embroidery/data/output/research_a_audience.json`

Targets from `embroidery/agents/research/subagents.py` AGENT_A_SYSTEM_TEMPLATE:
- `top_desires`: 12–15, each with LF8 tag, segment, DIRECT/FUEL evidence (verbatim quote + URL)
- `top_problems`: 8–10, WHEN+WHY format (`when`/`emotion`/`why` as separate fields — a "why:" mashed into `statement` is a format defect), node_check all-true on every kept problem
- `objections`: 8+, each with underlying_fear + counter_angle
- `voice_bank`: pain_phrases and objection_phrases matter most for downstream copy — flag if either < 6
- Segment coverage: desires must span all four of A/B/C/D; `segment` values like `"A|C"` are contract drift (schema means pick one) — note but don't penalize heavily
- Source quality: customer-voice domains (reddit.com, etsy.com reviews) good; SEO/marketing-blog/seller domains = FALSE class, each one found is a defect

### Rubric — Agent B (competitor_analyst), file `embroidery/data/output/research_b_competitor.json`

Targets from AGENT_B_SYSTEM_TEMPLATE:
- `competitors`: must include BOTH direct (named shops, not just "(General)") and indirect (DTG, DTF, iron-on, screen print, POD) — missing alternatives that appear in `alternatives_considered` but not in `competitors` is a gap
- `sophistication_assessment`: stage justified by ≥3 observed_claims, each with source + plausible stage_signal (check the signal matches the claim style: plain claim=1, bigger=2, mechanism=3)
- `unique_mechanism_candidates`: 3–5, typed 1/2/3; flag if all are just SHOP_BRIEF differentiators renamed and none is Type 3 (information/expertise)
- `awareness_levels_by_segment`: all 4 segments with evidence; `5x5_matrix_cell` implication must state lead style + mechanism timing

### Rubric — Agent C (social_media_analyst), file `embroidery/data/output/research_c_social.json`

Targets from AGENT_C_SYSTEM_TEMPLATE:
- `hook_patterns`: 8–10, and check the CATEGORY DISTRIBUTION — all 5 categories (size-of-claim, speed-of-claim, curiosity-gap, problem-first, identity) should appear; any category with 0 entries is a finding (especially speed-of-claim, since the shop sells 2–3-day rush)
- `top_hooks_to_adapt`: 6–8, ≥1 per segment A–D, each with BOTH visual_hook and text_hook
- `content_structure_patterns`: 3–5; `comment_themes.questions` should read as hidden objections
- Source quality is C's known weakness: generic tag pages (tiktok.com/tag/...) and hook-listicle SEO blogs (e.g. insense.pro, 50poundsocial.co.uk) are FALSE-class sources — count them explicitly

### Rubric — Synthesizer, files `embroidery/data/output/market_research_report.json` + `brand_intelligence_report.md`

Targets from `embroidery/agents/research/synthesizer.py`:
- JSON hard minimums (target): desires ≥24 (30), problems ≥14 (20), hooks ≥14 (20), objections ≥12 (15), buzzwords ≥16 (20+), success_patterns ≥10 (15+); note sitting exactly at minimums vs reaching targets
- Dimensionalization check: desires count should exceed Agent A's evidenced desires (expansion happened) AND quotes should be reused verbatim, not invented — spot-check 3 quotes against sub-agent files' quotes
- Markdown: exactly the 13 numbered sections; verbatim quotes carry URLs; `coverage_gaps` honest (non-empty)
- Flag anything in the report with NO traceable evidence in any sub-agent output (the Synthesizer papering over upstream gaps)

## Step 3 — Synthesize (main thread)

From the four scorecards build:
1. A comparison table: model, calls, tokens, searches, duration, targets-met, evidence quality, score /10
2. The pipeline's weakest link and why (lowest score weighted by downstream impact — research defects compound through Agents 2–8)
3. Top 3–5 prioritized fixes, deduplicated across agents; prefer single-point fixes in `_SHARED_RULES` or `embroidery/core/agent_loop.py` over per-agent prompt patches
4. One-line verdict: is this run's output safe to feed Agents 2/3, or should the pipeline re-run after fixes?

Keep the final answer under ~60 lines. Do not paste scorecards verbatim — merge them.
