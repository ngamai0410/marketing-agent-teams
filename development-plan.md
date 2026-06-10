# Embroidery Marketing System — Development Plan

**Start date:** June 8, 2026  
**Target completion:** July 3, 2026 (~4 weeks)  
**Methodology:** build in stages — validate each stage (see gates below) before adding the next.

> **Status as of June 10, 2026 (late evening):** Days 1–4 complete — **Day 4 finished a day early** (June 10). Provider is **Gemini** (`27790f2`) — cost tables below still assume Claude pricing. **Day 4 done:** all three Day 3 carry-overs fixed and verified live (provider call in `asyncio.to_thread` — A/B/C now truly parallel, ~70s combined; per-agent search cap `max_searches_per_agent: 8` enforced in code and observed firing; Brave spacing 1.1s + 429 retry). Pipeline wired in `agent1_market_research.py` (legacy single-agent replaced): `brief → gather(A,B,C) → Synthesizer (agent1_synthesizer.py, 2 no-tool pro calls: JSON then markdown) → output files + BrandAI snapshot (brand_store.py)`. Full live run passes `test_market_research.py --full` (~4.5 min wall clock): 25 desires / 14 problems / 15 hooks / 12 objections, 100% verbatim-evidenced desires, 36.5k-char narrative. Agent 7 (pulled forward from Day 6) committed in `a7be3dd`. **Next: Day 5 manual validation read** (1–4h immersion, do not skip).

---

## Architecture reminder

```
Stage 1 — Agent 1: Market Research (3 sub-agents + Synthesizer)
Stage 2 — Agent 7: QA gate + Agent 3: Positioning (2-agent linear pipeline)
Stage 3 — Agents 2, 4, 5, 6: Avatar + Hooks + Scripts + Static Copy (full parallel)
Stage 4 — Orchestrator + Agent 8: Feedback Loop + end-to-end wiring
```

---

## Stage 1 — Market Research Agent
**Week 1, June 8–12 | Target: brief → 34-page research doc**

The Market Research Agent is itself a mini-pipeline: Orchestrator dispatches 3 sub-agents in parallel (Audience Researcher, Competitor Analyst, Social Media Analyst), then a Synthesizer merges their outputs. Build this first because every downstream agent depends on its output.

### Day 1 — June 8 | Foundation [~4h] — ✅ DONE June 9 (`3c30a76`)

- [x] Create project structure: `embroidery/`, `brand_ai/`, `output/`
- [x] Set up Python venv, install: `anthropic>=0.40 aiohttp python-dotenv rich`
- [x] Create `.env` with `ANTHROPIC_API_KEY` (later also `GEMINI_API_KEY`, `BRAVE_API_KEY`)
- [x] Implement core agentic loop — the pattern all agents share:
  ```python
  while response.stop_reason == "tool_use":
      messages.append({"role": "assistant", "content": response.content})
      results = [execute_tool(b.name, b.input, b.id) for b in response.content if b.type == "tool_use"]
      messages.append({"role": "user", "content": results})
      response = client.messages.create(...)
  ```
- [x] Smoke test: dummy `echo` tool — verify loop enters, executes tool, returns final text (`smoke_test.py`)
- [x] Add `response.usage` logging to every `messages.create` call (critical for cost monitoring)

**Cost:** $0 (no real calls yet)

---

### Day 2 — June 9 | Tool Layer [~4h] — ✅ DONE June 9–10 (`3c30a76`…`b0cdaa1`)

- [x] Implement `web_search(query, num_results=10)` — Brave Search API primary; DuckDuckGo fallback (`search.py`)
- [x] Implement `web_fetch(url)` — fetch full page content via `aiohttp`
- [x] Implement `write_file(filename, content)` — save to `output/` directory
- [x] Define `RESEARCH_TOOLS` list with JSON schemas for all 3 tools (`tools.py`, Anthropic schema format)
- [x] Test: single agent with 1 web_search call, tool result feeds back correctly — *deviation: validated on Gemini flash, not Haiku; provider switched to Gemini (`27790f2`)*
- [x] Add `max_searches` counter: stop agentic loop after 20 searches to cap `web_search` cost (`search.max_searches` in config.yaml)

**Cost:** < $0.05 (Haiku smoke tests)  
**Watch:** Each `web_search` call = ~$0.003. An uncapped agent doing 50+ searches = $0.15+ just in search costs.

---

### Day 3 — June 10 | Build 3 Sub-Agent Prompts [~5h] — ✅ DONE June 10 (`agent1_subagents.py`)

> **Resolution of the Day 3 open decision:** split into A/B/C **per plan**. Sub-agents live in `agent1_subagents.py`; each gets **search-only tools** (`SEARCH_TOOLS` = web_search + web_fetch, no write_file) and returns its JSON as final text — the Python wrapper saves `output/research_{a,b,c}_*.json`. This sidesteps flash's MALFORMED_FUNCTION_CALL on large tool payloads, so `audience_researcher` moved back to `gemini-2.5-flash`. Tests ran on flash with the real (short) shop brief, not Haiku — provider is Gemini.

**Agent A — Audience & Desire Researcher** (Steps 1, 2, 4, 5, 6 of 8-step framework)
- [x] Write system prompt: product analysis → desire/problem mapping → Reddit/Amazon mining
- [x] CA additions to embed: LF8 tag per desire, WHEN+WHY emotion format, Problem Node 3-check
- [x] Evidence classification: DIRECT (proves node) / FUEL (voice bank) / FALSE (discard)
- [x] Output schema: `top_desires[]`, `top_problems[]`, `voice_bank{}`, `objections[]`, `identity_markers{}`
- [x] Test with short brief — verify JSON output structure (*on gemini-2.5-flash; all 10 assertions pass*)

**Agent B — Competitor & Positioning Analyst** (Steps 3, 4, 8)
- [x] Write system prompt: direct + indirect competitor research → Sophistication Stage 1–5 → Unique Mechanism candidates
- [x] Embed rule: "Sophistication raised by ALL alternatives, not just direct competitors" (DTG, DTF, iron-on, screen print all count)
- [x] Output schema: `sophistication_assessment{}`, `awareness_levels_by_segment{}`, `unique_mechanism_candidates[]`, `5x5_matrix_cell`
- [x] Test (*assessed Stage 3, 6 alternatives, 3 UM candidates typed 1/2/3 — all assertions pass*)

**Agent C — Social Media & Hook Analyst** (Step 7)
- [x] Write system prompt: TikTok/Instagram/YouTube hook patterns, comment theme analysis, visual patterns, influencer landscape
- [x] Hook categories: size-of-claim, speed-of-claim, curiosity-gap, problem-first, identity
- [x] Output schema: `hook_patterns[]`, `comment_themes{}`, `top_hooks_to_adapt[]`, `content_structure_patterns[]`
- [x] Test (*first run hit Gemini empty-response flake — fixed in `llm.py` by escalating temperature 0.3→0.6→0.9 on retry; second run passes all assertions*)

**Cost:** ~$0.10 actual (flash + ~40 Brave searches across test runs)

**Findings carried to Day 4/5:**
- Flash ignores the prompt's 6-search budget (Agent A consumed the full 20-search cap solo) → Day 4 needs a **per-agent search cap in code**, or A starves B/C of the shared budget.
- `run_agent` calls the provider synchronously → `asyncio.gather()` won't parallelize until the call is wrapped in `asyncio.to_thread`.
- Brave free tier is rate-limited → parallel sub-agents need request spacing in `search.py`.
- Quality (Day 5): some Agent A evidence comes from hobbyist/machine-owner threads (r/embroidery DIY) rather than buyers — steer queries toward buyer-intent sources.

---

### Day 4 — June 11 | Parallel Execution + Synthesizer [~4h] — ✅ DONE June 10 (a day early)

- [x] Make `run_agent` non-blocking: wrap `provider.create_message` in `asyncio.to_thread` (provider calls are sync — without this, `gather()` serializes) *(added Day 3)* — *verified: A/B/C log lines fully interleave; the three sub-agents finish in ~70s wall-clock combined*
- [x] Enforce a per-agent search cap in code — flash ignores the prompt budget *(added Day 3)* — *`search.max_searches_per_agent: 8` in config.yaml, enforced per `agent_name` in `agent_loop._execute_tool`; fired live (Agent C hit 8 and was told to synthesize)*
- [x] Add request spacing/retry to `BraveSearch` for parallel sub-agents (free tier ≈ 1 req/s) *(added Day 3)* — *shared `asyncio.Lock` + 1.1s min interval + 3× retry on HTTP 429*
- [x] Implement `run_market_research(brief)` — *in `agent1_market_research.py` (legacy single-agent version replaced, per Day 3 note); calls `run_subagent("a"|"b"|"c")` under `asyncio.gather` with one shared search budget*
- [x] Build Synthesizer system prompt: cross-reference findings, rank by frequency + intensity, produce all required sections — *`agent1_synthesizer.py`; targets kept (30/20/20/15) with hard minimums and an explicit per-segment dimensionalization procedure (pro under-delivered counts until the expansion step was made mandatory); `coverage_gaps` section added for Day 5 review*
- [x] Synthesizer gets no tools — pure synthesis from A+B+C outputs (model set to `gemini-2.5-pro` in config — report-writing quality; Python writes the files from its text output) — *deviation: TWO no-tool calls, not one — call 1 emits the JSON report, call 2 writes the markdown narrative from JSON + raw evidence (a single 16k-token response can't hold both)*
- [x] Implement `BrandAI` storage class: save timestamped JSON + markdown report to `brand_ai/embroidery_shop/` — *in `brand_store.py` (named to avoid clashing with the `brand_ai/` data dir); `save_research()` / `latest_research()`*
- [x] Wire together: `brief → gather(A,B,C) → Synthesizer → write market_research_report.json + brand_intelligence_report.md` — *full live run passes `test_market_research.py --full`: 24 desires / 14 problems / 14 hooks / 15 objections, 100% of desires with verbatim evidence, ~38–41k-char narrative*

**Cost:** ~$0.30–0.50 planned (Sonnet) → actual on Gemini ≈ $0.15–0.25 across 3 synthesizer dev runs + 1 full pipeline run (~16 Brave searches)

**Carried to Day 5:** synthesizer minimums (24/14/14) sit below the original 30/20/20 targets — judge during the manual read whether per-segment expansion should be pushed harder or the evidence base (more sub-agent searches) is the real lever. `test_market_research.py` (no flag) revalidates the Synthesizer from static files without new searches.

---

### Day 5 — June 12 | Validate Output [~3h]

- [ ] Run full pipeline with real embroidery brief on `claude-sonnet-4-6`
- [ ] Read output manually — course requirement: 1–4h of immersion (do not skip)
  - Desires and problems feel real, not AI-generic?
  - Unique Mechanism candidates — credible for this shop?
  - Sophistication level supported by evidence?
  - Customer language quotes sound authentic?
- [ ] Refine any weak prompts based on reading
- [ ] Run one validation run on `claude-opus-4-8` to compare quality

**Cost:** ~$0.50–1.50 (Sonnet run) + ~$2–3 (Opus validation)

**Stage 1 Gate — do not proceed until:**
> Research doc is 30+ pages. Top desires feel psychographically specific (not generic). Customer language quotes are verbatim, not paraphrased. Unique Mechanism candidates are shop-specific.

---

## Stage 2 — QA Agent + Positioning
**Week 2, June 15–17 | Target: research → positioning_matrix.json, gated by QA**

Build QA *before* any content agents. Every ad script or static copy will pass through it.

### Day 6 — June 15 | Agent 7: QA Agent [~3h] — 🔀 PULLED FORWARD to June 10

> **Actual:** `agent7_qa_reviewer.py` + `test_agent7.py` + `fixtures/` (positioning_matrix, video_scripts, static_ad_copy samples) built June 10, committed `a7be3dd`. `qa_reviewer` model moved to `gemini-2.5-pro` — flash emits MALFORMED_FUNCTION_CALL even on small contexts.

- [x] Write QA system prompt: 8-question diagnostic + Buying Psychology checklist
- [x] Output schema: `passed_8_questions`, `question_scores{}`, `checklist_failures[]`, `hook_rate_prediction`, `revision_required`, `revision_notes`
- [x] Test with 3 fixture ads: gift-giver script PASS, corporate script FAIL, overall FAIL — *verified June 10, all `test_agent7` assertions hold against `qa_report.json`*
- [x] Verify: FAIL output contains actionable revision notes, not vague feedback — *notes name the segment, the style to emulate, and the reference ad*

**Cost:** < $0.10 (Haiku, hand-crafted test inputs)

---

### Day 7 — June 16 | Agent 3: Positioning Strategist [~4h]

- [ ] Write Positioning Strategist system prompt: Awareness × Sophistication calibration per segment, Unique Mechanism selection (Type 1/2/3), 5×5 matrix output
- [ ] Embed rule: "Unique Mechanism introduced ONLY after problem belief is built"
- [ ] Test with static `market_research_report.json` from Stage 1 (do not re-run research)
- [ ] Output: `positioning_matrix.json` with all 4 segments (Team Pride, Gift Giver, Brand Builder, Aesthetic Buyer)

**Cost:** < $0.20 (Haiku dev)

---

### Day 8 — June 17 | Wire Stage 2 Pipeline [~3h]

- [ ] Connect: `market_research_report.json` → Positioning Agent → `positioning_matrix.json`
- [ ] Test end-to-end pipeline: Stage 1 file output → Stage 2 agent reads it → correct positioning
- [ ] Validate all 4 segments have plausible Awareness + Sophistication assignments with evidence

**Cost:** ~$0.20–0.50 (Sonnet end-to-end)

**Stage 2 Gate — do not proceed until:**
> Positioning matrix correctly assigns Awareness × Sophistication for all 4 segments with specific evidence. Unique Mechanism recommendation is shop-specific, not generic.

---

## Stage 3 — Copy Production
**Week 2–3, June 18–24 | Target: full parallel copy pipeline → QA-gated output**

### Day 9 — June 18 | Agent 2: Customer Avatar Builder [~3h]

- [ ] Write Avatar Builder system prompt: 4 avatars × (Demographics + Psychographics + Buying Psychology + Content Behavior + Ad Implications)
- [ ] Test with static `market_research_report.json` on Haiku
- [ ] Output: `customer_avatars.md` — 4 profiles + comparison matrix

**Cost:** < $0.10

---

### Day 10 — June 19 | Agent 4: Hook Generator [~4h]

- [ ] Write Hook Generator system prompt: visual hook + text hook architecture, 3 variants per concept (H1 control / H2 alt messaging / H3 alt visual), awareness-matched hook types
- [ ] Test with static `positioning_matrix.json` + `customer_avatars.md` on Haiku
- [ ] Output: `hooks_library.json` — 36 hooks (3 variants × 4 segments × 3 formats)

**Cost:** < $0.10

---

### Day 11 — June 20 | Agent 5: Video Script Writer [~5h]

- [ ] Write Script Writer system prompt: 8-element UGC structure (Hook→Problem→Twist→Intro→Feature/Benefit→Bad Alt→Results→CTA), retention techniques, authenticity rules
- [ ] Test with static `hooks_library.json` + `customer_avatars.md` + `positioning_matrix.json` on Haiku
- [ ] This is the hardest prompt — plan 2–3 iterations to get authentic-sounding scripts
- [ ] Output: `video_scripts.json` — H1/H2/H3 variants per segment

**Cost:** < $0.20

---

### Day 12 — June 21 | Agent 6: Static Ad Copy Writer [~3h]

- [ ] Write Static Copy system prompt: "Art of One Frame" — headline (5 levers) + visual direction + body copy + callouts + CTA
- [ ] 5 static ad types: Social Proof / Before-After / Objection Crusher / Offer-Urgency / Identity Statement
- [ ] Test with static positioning + hooks on Haiku

**Cost:** < $0.10

---

### Day 13–14 — June 22–23 | Wire Stage 3: Parallel + QA [~5h]

- [ ] Wire asyncio.gather() for Agents 2+3 (run in parallel after research)
- [ ] Wire asyncio.gather() for Agents 5+6 (run in parallel after hooks)
- [ ] Integrate Agent 7 QA gate: each script/static ad passes through QA before saving
- [ ] Test full Stage 3 pipeline on Sonnet: research → parallel analysis → hooks → parallel copy → QA
- [ ] At least 1 script per segment should pass QA on first try

**Cost:** ~$1–2 (Sonnet full pipeline run)

**Stage 3 Gate — do not proceed until:**
> At least 1 ad per segment passes QA on first try. Scripts use verbatim customer language from research. Hook + body are segment-specific, not interchangeable.

---

## Stage 4 — Orchestrator + Feedback Loop
**Week 4, June 25–July 3 | Target: fully automated campaign pipeline**

### Day 15 — June 25 | QA Revision Loop [~4h]

- [ ] Implement FAIL → revision loop: QA returns `revision_required=true` → inject `revision_notes` as context → re-run originating copy agent
- [ ] Add `max_revisions=3` guard to prevent infinite loops
- [ ] Test: deliberately submit a bad script → verify 3-attempt loop behavior → verify final PASS or graceful FAIL exit

**Cost:** < $0.30

---

### Day 16 — June 26 | Orchestrator [~5h]

- [ ] Write Orchestrator system prompt (Campaign Director): delegation protocol, pipeline rules (no copy before research, QA is blocking gate, iteration ratios, reset signal)
- [ ] Wire all 7 agents through Orchestrator with the full delegation sequence
- [ ] Test: single call to Orchestrator with brief → produces complete creative brief
- [ ] Enable prompt caching on shared research data (feeds 5 agents — saves ~$0.14/run at Sonnet):
  ```python
  {"type": "text", "text": research_data, "cache_control": {"type": "ephemeral"}}
  ```

**Cost:** ~$2–4 (Opus orchestrator + full pipeline)

---

### Day 17 — June 27 | Agent 8: Feedback Analyst [~3h]

Note: Feedback Agent requires real ad performance data. Build scaffold now, activate after first ads run.

- [ ] Write Feedback Analyst system prompt: weekly review cadence, metrics (Hook Rate, Hold Rate, CPA, CVR), diagnostic logic table, RESET protocol
- [ ] Create `sample_ad_performance.csv` with mock data for testing
- [ ] Verify output: `weekly_learnings.json` + `next_week_brief.json` with correct iteration ratio and brand_ai_updates
- [ ] Wire as post-launch step — Orchestrator only calls it when `ad_data_available = True`

**Cost:** < $0.20

---

### Day 18 — June 28 | End-to-End Validation [~4h]

- [ ] Run complete 8-agent pipeline with real embroidery brief on production models (Opus for Orchestrator, Research, Positioning, Script; Sonnet for others)
- [ ] Measure: total wall-clock time, total API cost, token counts per agent
- [ ] Verify data contract: every file in the pipeline table exists and is valid JSON/MD
- [ ] Fix any integration bugs

**Cost:** ~$2–4 per full production run

---

### Days 19–20 — June 30–July 3 | Buffer + Polish [~4h]

- [ ] Refine any prompts that consistently produce low-quality output
- [ ] Add retry logic for rate limit errors (exponential backoff)
- [ ] Write `run_campaign.py` — clean entry point with `--brief` argument
- [ ] Final full run: log token counts, confirm cost < $3

---

## Cost Summary

| Stage | Dev cost (Haiku) | Validation (Sonnet/Opus) | Total |
|---|---|---|---|
| Stage 1 — Market Research | < $1.00 | $2–4 | **~$3–5** |
| Stage 2 — QA + Positioning | < $0.50 | $0.50 | **~$1** |
| Stage 3 — Copy pipeline | < $0.50 | $1–2 | **~$2** |
| Stage 4 — Orchestrator + loop | < $0.50 | $2–4 | **~$3–5** |
| **Total development** | | | **~$9–13** |
| **Per production run** | | | **$1.50–4.00** |

Cost control rules:
- Every system prompt tested on Haiku before Sonnet/Opus
- Short synthetic briefs during development (< 500 tokens)
- Mock downstream files to isolate single-agent testing
- `max_searches=20` cap on Agent 1's web_search loop
- Prompt caching on research data fed to Agents 2–6

---

## Go/No-Go Gates Summary

| After stage | Gate condition |
|---|---|
| Stage 1 | Research doc 30+ pages, desires are segment-specific, customer language quotes are verbatim not paraphrased |
| Stage 2 | Positioning matrix has correct Awareness×Sophistication for all 4 segments with evidence, Unique Mechanism is shop-specific |
| Stage 3 | At least 1 ad per segment passes QA on first try, scripts use customer's actual language |
| Stage 4 | Full pipeline runs end-to-end, total cost < $4, all 10 data contract files produced correctly |

---

## Weekly Timeline

| Week | Dates | Agents built | Stage |
|---|---|---|---|
| Week 1 | June 8–12 | Agent 1 (Market Research: 3 sub-agents + Synthesizer) | Stage 1 |
| Week 2 | June 15–21 | Agent 7 (QA) + Agent 3 (Positioning) + Agents 2, 4, 5, 6 | Stage 2–3 |
| Week 3 | June 22–24 | Parallel wiring + QA integration for copy pipeline | Stage 3 complete |
| Week 4 | June 25–July 3 | QA loop + Orchestrator + Agent 8 (Feedback) + end-to-end | Stage 4 |

**Total: ~4 weeks, ~65 hours of development**

---

## File output checklist (all 10 data contract files)

| File | Agent | Stage it becomes available |
|---|---|---|
| `market_research_report.json` | Agent 1 | End of Stage 1 |
| `brand_intelligence_report.md` | Agent 1 | End of Stage 1 |
| `positioning_matrix.json` | Agent 3 | End of Stage 2 |
| `customer_avatars.md` | Agent 2 | End of Stage 3 |
| `hooks_library.json` | Agent 4 | End of Stage 3 |
| `video_scripts.json` | Agent 5 | End of Stage 3 |
| `static_ad_copy.json` | Agent 6 | End of Stage 3 |
| `qa_report.json` | Agent 7 | End of Stage 3 |
| `weekly_learnings.json` | Agent 8 | Post-launch (Stage 4+) |
| `next_week_brief.json` | Agent 8 | Post-launch (Stage 4+) |
