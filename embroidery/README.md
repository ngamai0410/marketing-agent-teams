# embroidery/ — Market Research Agent (Stage 1)

## Workflow

```
config.yaml  ──►  config.py  ──►  ModelSettings / Config
                                        │
                       ┌────────────────┼────────────────┐
                       ▼                ▼                 ▼
                    llm.py          search.py        agent files
             AnthropicProvider    BraveSearch     agent1_market_research.py
             OpenAIProvider       DuckDuckGoSearch agent7_qa_reviewer.py
             GeminiProvider             │                 │
                       │                │                 │
                       └────────┬───────┴◄────────────────┘
                                ▼
                          agent_loop.py
                          run_agent()
                          │  • calls LLM provider          ──► logger.py
                          │  • executes tool calls              │  INFO  → stdout
                          │  • caps search usage                │  DEBUG → logs/<run_id>.log
                          │  • logs every call + tool      ◄───┘
                                ▼
                              output/

  Agent 1 writes:  market_research_report.json ──►  Agents 2 & 3 (Stage 2+)
                   brand_intelligence_report.md ─►  Agents 2 & 3 (Stage 2+)

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
venv/bin/python agent1_market_research.py
```

Edit `SHOP_BRIEF` at the top of `agent1_market_research.py` before each campaign run.
Outputs land in `output/`: `market_research_report.json` (structured) and
`brand_intelligence_report.md` (narrative). Search count is capped by
`search.max_searches` in `config.yaml` (default 20/run).

## Run Agent 7 (QA gatekeeper)

```bash
venv/bin/python agent7_qa_reviewer.py   # reads positioning_matrix + scripts/copy from output/
venv/bin/python test_agent7.py          # manual gate test against fixtures/ (one good, one bad ad)
```

Agent 7 runs the EcomTalent 8-question diagnostic + buying-psychology
checklist on every ad and writes `qa_report.json`. `overall: FAIL` if any ad
needs revision; per-ad `revision_notes` tell Agents 5/6 what to fix.

**Gemini model caveat:** `gemini-2.5-flash` reliably fails with
`MALFORMED_FUNCTION_CALL` when emitting tool calls in this pipeline (large
`write_file` payloads, and for the QA agent even small `read_file` calls).
Agents on the Gemini provider should use `gemini-2.5-pro`. `llm.py` retries
empty Gemini responses 3× and logs the `finish_reason` before raising.

## Files

| File | Purpose |
|---|---|
| `config.yaml` | All settings — provider, model per agent, search engine, paths |
| `config.py` | Loads `config.yaml` + env vars into typed `Config` / `ModelSettings` objects |
| `llm.py` | `AnthropicProvider`, `OpenAIProvider`, `GeminiProvider` — all implement `LLMProvider` |
| `search.py` | `BraveSearch` and `DuckDuckGoSearch` — both implement `SearchProvider` |
| `logger.py` | `get_logger(name)` — shared log sink: INFO→stdout, DEBUG→`logs/<run_id>.log` |
| `agent_loop.py` | `run_agent()` — the single agentic loop used by every agent |
| `agent1_market_research.py` | Agent 1 — EcomTalent 8-step market research; writes the two reports Agents 2 & 3 consume |
| `agent7_qa_reviewer.py` | Agent 7 — QA gatekeeper; 8-question diagnostic + psychology checklist → `qa_report.json` |
| `fixtures/` | Sample upstream outputs (positioning matrix, scripts, static copy) for testing Agent 7 before Agents 3/5/6 exist |
| `test_agent7.py` | Manual gate test — asserts QA passes the strong fixture ad and fails the corporate one |
| `tools.py` | Tool schemas (Anthropic JSON format) — `RESEARCH_TOOLS`, `FILE_TOOLS` |
| `smoke_test.py` | Verifies the full stack end-to-end with two tool calls |
| `output/` | Agent-written artifacts (reports, briefs) — the pipeline's data contracts |
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
