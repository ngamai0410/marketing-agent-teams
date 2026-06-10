# embroidery/ — Market Research Agent (Stage 1)

## Workflow

```
config.yaml  ──►  config.py  ──►  ModelSettings / Config
                                        │
                       ┌────────────────┼────────────────┐
                       ▼                ▼                 ▼
                    llm.py          search.py        agent files
             AnthropicProvider    BraveSearch      agent1_market_research.py
             OpenAIProvider        (1.1s spacing   agent1_subagents.py
             GeminiProvider         + 429 retry)   agent1_synthesizer.py
                       │          DuckDuckGoSearch agent7_qa_reviewer.py
                       │                │                 │
                       └────────┬───────┴◄────────────────┘
                                ▼
                          agent_loop.py
                          run_agent()  — provider call in asyncio.to_thread
                          │  • executes tool calls          ──► logger.py
                          │  • caps searches: shared budget     │  INFO  → stdout
                          │    + per-agent cap (in code)        │  DEBUG → logs/<run_id>.log
                          │  • logs every call + tool      ◄───┘
                                ▼
                              output/

  Agent 1 pipeline — agent1_market_research.py :: run_market_research(brief):

    brief ──► asyncio.gather( A, B, C )            search-only tools, JSON as final text
       A audience_researcher  ──► output/research_a_audience.json   ┐
       B competitor_analyst   ──► output/research_b_competitor.json ├──► Synthesizer
       C social_media_analyst ──► output/research_c_social.json     ┘    (no tools; 2 calls:
                                                                          JSON, then markdown)
                              ┌────────────────────────────────────────────┤
                              ▼                                            ▼
       output/market_research_report.json             brand_ai/embroidery_shop/
       output/brand_intelligence_report.md            <timestamp>_*.{json,md}  (BrandAI history)
                              │
                              └──► Agents 2 & 3 (Stage 2+)

  Agent 7 reads:   positioning_matrix.json (Agent 3)
                   video_scripts.json (Agent 5) + static_ad_copy.json (Agent 6)
          writes:  qa_report.json ──► Orchestrator gate (Stage 4 loops 5/6 on FAIL)
```

Provider-agnostic agentic loop for the custom embroidery shop campaign. Provider and search engine switch via one line in `config.yaml`.

## Setup

```bash
# Python 3.11 — system Python 3.14 has broken pip
~/.pyenv/versions/3.11.9/bin/python3 -m venv venv
venv/bin/pip install "anthropic>=0.40" aiohttp python-dotenv rich pyyaml openai ddgs "google-genai>=1.0"
cp .env.example .env   # then add API keys
venv/bin/python smoke_test.py   # verifies loop + tools + file write
```

## Run Agent 1 (Market Research)

```bash
venv/bin/python agent1_market_research.py        # FULL pipeline: gather(A,B,C) → Synthesizer → reports
venv/bin/python agent1_subagents.py a            # run one sub-agent standalone: a | b | c
venv/bin/python agent1_synthesizer.py            # Synthesizer only, from static output/research_*.json
venv/bin/python test_agent1_subagents.py         # live schema test for all 3 sub-agents (or pass a|b|c)
venv/bin/python test_market_research.py          # Day 4 test: offline caps/storage + live Synthesizer
venv/bin/python test_market_research.py --full   # same, but runs the whole live pipeline (~$0.30–0.50)
```

Edit `SHOP_BRIEF` at the top of `agent1_subagents.py` before each campaign run.
Sub-agents A (audience/desires), B (competitors/positioning), C (social/hooks) run **in
parallel** (`asyncio.gather`; provider calls are wrapped in `asyncio.to_thread` so they
actually overlap), have **search-only tools**, and return their JSON as final text — the
Python wrapper saves it to `output/research_{a_audience,b_competitor,c_social}.json`.
The Synthesizer (no tools, `gemini-2.5-pro`) merges these in two calls — structured
`market_research_report.json`, then narrative `brand_intelligence_report.md` — and the
pipeline also saves a timestamped `BrandAI` snapshot to `brand_ai/embroidery_shop/`.

Search cost guards (`config.yaml`, enforced in `agent_loop.py` — prompts alone are
ignored by flash): `search.max_searches` (shared budget per pipeline run, default 20)
and `search.max_searches_per_agent` (default 8, stops one sub-agent starving the others).
`BraveSearch` additionally spaces requests ≥1.1s apart (free tier ≈ 1 req/s, shared
`asyncio.Lock` across parallel sub-agents) and retries HTTP 429 up to 3 times.

## Run Agent 7 (QA gatekeeper)

```bash
venv/bin/python agent7_qa_reviewer.py   # reads positioning_matrix + scripts/copy from output/
venv/bin/python test_agent7.py          # manual gate test against fixtures/ (one good, one bad ad)
```

Agent 7 runs the EcomTalent 8-question diagnostic + buying-psychology
checklist on every ad and writes `qa_report.json`. `overall: FAIL` if any ad
needs revision; per-ad `revision_notes` tell Agents 5/6 what to fix.

**Gemini model caveat:** `gemini-2.5-flash` reliably fails with
`MALFORMED_FUNCTION_CALL` when emitting large tool-call payloads (e.g.
`write_file` with a full report; for the QA agent even small `read_file` calls).
Agents that write files via tools should use `gemini-2.5-pro`. The Agent 1
sub-agents avoid this entirely by returning JSON as plain final text (no
`write_file`), so they run safely on flash. `llm.py` retries empty Gemini
responses 3×, escalating temperature 0.3 → 0.6 → 0.9 (a fixed-temp retry
tends to repeat the same empty candidate), and logs the `finish_reason`
before raising.

## Files

| File | Purpose |
|---|---|
| `config.yaml` | All settings — provider, model per agent, search engine, paths |
| `config.py` | Loads `config.yaml` + env vars into typed `Config` / `ModelSettings` objects |
| `llm.py` | `AnthropicProvider`, `OpenAIProvider`, `GeminiProvider` — all implement `LLMProvider` |
| `search.py` | `BraveSearch` and `DuckDuckGoSearch` — both implement `SearchProvider` |
| `logger.py` | `get_logger(name)` — shared log sink: INFO→stdout, DEBUG→`logs/<run_id>.log` |
| `agent_loop.py` | `run_agent()` — the single agentic loop used by every agent |
| `agent1_market_research.py` | Agent 1 pipeline entry — `run_market_research(brief)`: `gather(A,B,C)` → Synthesizer → output files + BrandAI snapshot |
| `agent1_subagents.py` | Agent 1 sub-agents A/B/C — prompts, registry, `run_subagent()`; saves each output to `output/research_*.json` |
| `agent1_synthesizer.py` | Agent 1 Synthesizer — no tools; merges A/B/C into the master JSON + markdown narrative (2 calls on `gemini-2.5-pro`) |
| `brand_store.py` | `BrandAI` class — timestamped research history per shop under `brand_ai/<shop_slug>/`, `save_research()` / `latest_research()` |
| `test_agent1_subagents.py` | Live Day 3 test — runs each sub-agent and asserts its JSON schema contract |
| `test_market_research.py` | Day 4 test — offline search-cap + BrandAI checks, live Synthesizer validation; `--full` runs the whole pipeline |
| `agent7_qa_reviewer.py` | Agent 7 — QA gatekeeper; 8-question diagnostic + psychology checklist → `qa_report.json` |
| `fixtures/` | Sample upstream outputs (positioning matrix, scripts, static copy) for testing Agent 7 before Agents 3/5/6 exist |
| `test_agent7.py` | Manual gate test — asserts QA passes the strong fixture ad and fails the corporate one |
| `tools.py` | Tool schemas (Anthropic JSON format) — `RESEARCH_TOOLS`, `SEARCH_TOOLS` (sub-agents, no write), `FILE_TOOLS` |
| `smoke_test.py` | Verifies the full stack end-to-end with two tool calls |
| `output/` | Agent-written artifacts (reports, briefs) — the pipeline's data contracts (overwritten each run) |
| `brand_ai/` | Timestamped research history per shop (written by `BrandAI`) — survives across runs |
| `.env` | API keys (gitignored) |
| `.env.example` | Key names with placeholder values (committed) |
| `logs/` | Per-run log files (gitignored); one file per process, named by timestamp |

## Adding a new agent

1. Write a system prompt string.
2. Define tool schemas in Anthropic JSON format.
3. Add an entry under `agents:` in `config.yaml` with the target model.
4. Call `run_agent(system, messages, tools, settings.agents.<your_agent>, agent_name="<your_agent>")`.

The loop, tool execution, token usage logging, search limits, and file logging are all handled automatically. Pass `agent_name` so log lines are labelled correctly.

## Env keys

| Key | Required when |
|---|---|
| `ANTHROPIC_API_KEY` | `llm.provider: anthropic` |
| `OPENAI_API_KEY` | `llm.provider: openai` |
| `GEMINI_API_KEY` | `llm.provider: gemini` |
| `BRAVE_API_KEY` | `search.provider: brave` |
