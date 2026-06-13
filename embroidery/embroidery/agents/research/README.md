# agents/research/ — Workflow 1: Market Research (Agent 1)

The first pipeline stage. Three **parallel, search-only** sub-agents gather raw market
evidence; a **no-tool Synthesizer** merges their JSON into the two Stage-1 data-contract
files consumed by Agents 2 & 3. Entry point: `run_market_research(brief)` in `pipeline.py`.

## Workflow

```
SHOP_BRIEF (in subagents.py)
        │
        ▼  pipeline.run_market_research()  — one shared search budget; reset_search_count() first
   asyncio.gather(
     A  audience_researcher    gemini-2.5-flash  SEARCH_TOOLS  ─► data/output/research_a_audience.json
     B  competitor_analyst     gemini-2.5-flash  SEARCH_TOOLS  ─► data/output/research_b_competitor.json
     C  social_media_analyst   gemini-2.5-flash  SEARCH_TOOLS  ─► data/output/research_c_social.json
   )                              │ each returns ONE JSON object as final text;
        │                         │ Python (run_subagent) parses + saves it
        ▼
   ◆ QC GATE 1  checkpoint("Research — sub-agents A/B/C")   Approve / Edit brief & re-run A/B/C / Quit
        ▼
   synthesizer.run_synthesizer(A, B, C)   gemini-2.5-pro, NO tools, 2 calls:
     call 1 → master JSON report   ─► data/output/market_research_report.json
     call 2 → markdown narrative   ─► data/output/brand_intelligence_report.md
        ▼
   ◆ QC GATE 2  checkpoint("Research — synthesis report")  Approve / Edit brief & re-run all / Quit
        │
        ├─► BrandAI snapshot ─► data/brand_ai/embroidery_shop/<timestamp>_*.{json,md}
        │                       (read by Agents 2 & 3 + Agent 8's feedback loop)
        └─► perf digest ─► data/output/run_report.md
```

The two **QC gates** (`core/checkpoint.py`) pause the pipeline for human review when driven
from the dashboard (`python -m embroidery.web`); standalone runs auto-approve them. **Edit**
returns an adjusted `SHOP_BRIEF` and re-runs from A/B/C. Live per-agent metrics stream to the
dashboard throughout via `core/reporter.py`.

**Editable prompts.** Each sub-agent's system prompt, the shared research rules, and the two
Synthesizer prompts are user-editable from the dashboard's **⚙ Agent prompts** panel before
Start. `build_system()` and `run_synthesizer()` render through `core/prompt_store.py` (via
`to_dollar()` + `prompt_catalog()`), so a saved override in `data/prompts/overrides.json`
replaces the default; `$shop_context` / `$shared_rules` / `$research_date` / `$shop_name`
placeholders are injected safely (a removed placeholder just isn't substituted).

## Files

| File | Role | Key symbols |
|---|---|---|
| `subagents.py` | Sub-agents A/B/C — prompts, the `SUBAGENTS` registry, and `run_subagent(key)` which runs one sub-agent and saves its JSON. **Holds `SHOP_BRIEF`** (edit before each campaign). | `SHOP_BRIEF`, `SUBAGENTS`, `SubAgentSpec`, `run_subagent`, `shop_context` |
| `synthesizer.py` | Synthesizer — merges A/B/C into the master report + narrative (two `gemini-2.5-pro` calls, no tools, Python writes the files). | `run_synthesizer(a, b, c)`, `_load_static_research()` |
| `pipeline.py` | Agent 1 entry — `gather(A,B,C)` → QC gate → Synthesizer → QC gate → output files + BrandAI snapshot + `run_report.md`. Returns `None` if the user quits at a gate. | `run_market_research(brief)`, `_research_digest`, `_synth_digest`, `SHOP_SLUG` |

## The three sub-agents (8-step EcomTalent framework)

| Key | Agent (`config.yaml` key) | Covers framework steps | Output file |
|---|---|---|---|
| `a` | `audience_researcher` | 1, 2, 4, 5, 6 — desires, problems, objections, voice bank | `research_a_audience.json` |
| `b` | `competitor_analyst` | 3, 4, 8 — competitors, sophistication, unique-mechanism, awareness×segment | `research_b_competitor.json` |
| `c` | `social_media_analyst` | 7 — hook patterns, hooks-to-adapt, content structures | `research_c_social.json` |

Sub-agents are **search-only** (`SEARCH_TOOLS` = `web_search` + `web_fetch`, no `write_file`)
and return their JSON as plain final text — this sidesteps `gemini-2.5-flash`'s
`MALFORMED_FUNCTION_CALL` on large tool payloads, so they run safely on flash. The Synthesizer
runs on `gemini-2.5-pro` for report quality.

## Data contracts

| Direction | File(s) |
|---|---|
| **In** | `SHOP_BRIEF` dict (in `subagents.py`) |
| **Intermediate** | `data/output/research_{a_audience,b_competitor,c_social}.json` |
| **Out → Agents 2, 3** | `data/output/market_research_report.json`, `data/output/brand_intelligence_report.md` |
| **History** | `data/brand_ai/embroidery_shop/<timestamp>_*.{json,md}` (kept across runs) |

## Run

```bash
# from embroidery/ (project root)
venv/bin/python -m embroidery.web                            # FULL pipeline + live dashboard + QC gates
venv/bin/python -m embroidery.agents.research.pipeline       # FULL pipeline, headless (gates auto-approve)
venv/bin/python -m embroidery.agents.research.pipeline --yes # explicit auto-approve
venv/bin/python -m embroidery.agents.research.subagents a    # one sub-agent: a | b | c
venv/bin/python -m embroidery.agents.research.synthesizer    # Synthesizer only, from static research_*.json
venv/bin/python -m tests.test_agent1_subagents               # live A/B/C schema test (or pass a|b|c)
venv/bin/python -m tests.test_market_research                # offline caps/storage + live Synthesizer
venv/bin/python -m tests.test_market_research --full         # whole live pipeline (~$0.30–0.50, ~4.5 min)
```

## Cost & reliability guards

- Search budget: `search.max_searches` (shared per run, default 20) + `search.max_searches_per_agent`
  (default 8) — both enforced in `core/agent_loop.py`, not the prompts (flash ignores prompt budgets).
- `BraveSearch` spaces requests ≥1.1s apart (shared `asyncio.Lock`) and retries HTTP 429 up to 3×.
- `core/llm.py` retries empty Gemini responses 3×, escalating temperature 0.3 → 0.6 → 0.9.
