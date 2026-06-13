# embroidery/ — EcomTalent marketing-agent pipeline

Provider-agnostic agentic pipeline for the custom embroidery shop campaign.
Provider and search engine switch via one line in `config.yaml`.

## Layout

```
embroidery/                      ← project root (PROJECT_ROOT); run commands from here
  config.yaml   .env(.example)   ← settings + secrets
  README.md     development-plan.md
  venv/                          ← Python 3.11 virtualenv
  fixtures/                      ← sample upstream outputs for testing Agent 7
  data/                          ← runtime artifacts (gitignored except brand_ai/)
    output/                        agent-written data-contract files (overwritten each run)
    brand_ai/<shop>/               timestamped research history (kept across runs)
    logs/                          one DEBUG log file per process

  embroidery/                    ← the importable package
    core/                          reusable framework (provider-agnostic kernel)
      config.py  llm.py  search.py  logger.py  agent_loop.py  tools.py  brand_store.py
    agents/
      research/                    Workflow 1 — Market Research (Agents 1,2,3)
        pipeline.py  subagents.py  synthesizer.py
      copy/                        Workflow 2 — Copy (Agents 4,5,6)  [future]
      qa/                          Workflow 3 — QA & Feedback (Agents 7,8)
        qa_reviewer.py

  tests/                         ← test + smoke scripts (run as modules)
```

The directory layout mirrors the agent hierarchy in `../CLAUDE.md`: `core/` is the
reusable framework, `agents/<workflow>/` is campaign logic grouped by the documented
Workflow 1/2/3 stages. The agent *number* lives in docs and `config.yaml`, not in filenames.

## Workflow

```
config.yaml  ──►  core/config.py  ──►  settings (PROJECT_ROOT-anchored paths)
                                        │
                       ┌────────────────┼────────────────┐
                       ▼                ▼                 ▼
                  core/llm.py     core/search.py     agents/**
             Anthropic|OpenAI|     Brave|DuckDuckGo   research/* , qa/*
              GeminiProvider       (1.1s spacing,
                       │            429 retry)              │
                       └────────┬───────┴◄─────────────────┘
                                ▼
                       core/agent_loop.py
                       run_agent()  — provider call in asyncio.to_thread
                       │  • executes tool calls          ──► core/logger.py
                       │  • caps searches: shared budget     │  INFO  → stdout
                       │    + per-agent cap (in code)        │  DEBUG → data/logs/<run_id>.log
                       │  • logs every call + tool      ◄───┘
                                ▼
                            data/output/

  Agent 1 pipeline — agents/research/pipeline.py :: run_market_research(brief):

    brief ──► asyncio.gather( A, B, C )            search-only tools, JSON as final text
       A audience_researcher  ──► data/output/research_a_audience.json   ┐
       B competitor_analyst   ──► data/output/research_b_competitor.json ├──► Synthesizer
       C social_media_analyst ──► data/output/research_c_social.json     ┘    (no tools; 2 calls:
                                                                               JSON, then markdown)
                              ┌─────────────────────────────────────────────────┤
                              ▼                                                 ▼
       data/output/market_research_report.json          data/brand_ai/embroidery_shop/
       data/output/brand_intelligence_report.md         <timestamp>_*.{json,md}  (BrandAI history)
                              │
                              └──► Agents 2 & 3 (Stage 2+)

  Agent 7 — agents/qa/qa_reviewer.py reads positioning_matrix.json (Agent 3),
            video_scripts.json (Agent 5) + static_ad_copy.json (Agent 6);
            writes data/output/qa_report.json ──► Orchestrator gate (loops 5/6 on FAIL)
```

## Setup

```bash
# Python 3.11 — system Python 3.14 has broken pip
~/.pyenv/versions/3.11.9/bin/python3 -m venv venv
venv/bin/pip install "anthropic>=0.40" aiohttp python-dotenv rich pyyaml openai ddgs "google-genai>=1.0"
cp .env.example .env   # then add API keys
venv/bin/python -m tests.smoke_test   # verifies loop + tools + file write
```

**Run everything from this directory** (`embroidery/`) as modules — flat `python file.py`
no longer works because the code is a package. CWD must be the project root so `import
embroidery` resolves; all data paths are anchored at `PROJECT_ROOT`, so it is CWD-independent
in practice, but `-m` resolution still needs you here.

## Run Agent 1 (Market Research)

```bash
venv/bin/python -m embroidery.agents.research.pipeline       # FULL pipeline: gather(A,B,C) → Synthesizer → reports
venv/bin/python -m embroidery.agents.research.subagents a    # one sub-agent standalone: a | b | c
venv/bin/python -m embroidery.agents.research.synthesizer    # Synthesizer only, from static data/output/research_*.json
venv/bin/python -m tests.test_agent1_subagents               # live schema test for all 3 sub-agents (or pass a|b|c)
venv/bin/python -m tests.test_market_research                # offline caps/storage + live Synthesizer
venv/bin/python -m tests.test_market_research --full         # same, but runs the whole live pipeline (~$0.30–0.50)
```

Edit `SHOP_BRIEF` at the top of `embroidery/agents/research/subagents.py` before each campaign run.
Sub-agents A (audience/desires), B (competitors/positioning), C (social/hooks) run **in
parallel** (`asyncio.gather`; provider calls are wrapped in `asyncio.to_thread`), have
**search-only tools**, and return their JSON as final text — the Python wrapper saves it
to `data/output/research_{a_audience,b_competitor,c_social}.json`. The Synthesizer (no
tools, `gemini-2.5-pro`) merges these in two calls — structured `market_research_report.json`,
then narrative `brand_intelligence_report.md` — and the pipeline also saves a timestamped
`BrandAI` snapshot to `data/brand_ai/embroidery_shop/`.

Search cost guards (`config.yaml`, enforced in `core/agent_loop.py` — prompts alone are
ignored by flash): `search.max_searches` (shared budget per pipeline run, default 20)
and `search.max_searches_per_agent` (default 8). `BraveSearch` additionally spaces requests
≥1.1s apart (shared `asyncio.Lock`) and retries HTTP 429 up to 3 times.

## Run Agent 7 (QA gatekeeper)

```bash
venv/bin/python -m embroidery.agents.qa.qa_reviewer   # reads positioning_matrix + scripts/copy from data/output/
venv/bin/python -m tests.test_agent7                  # gate test against fixtures/ (one good, one bad ad)
```

Agent 7 runs the EcomTalent 8-question diagnostic + buying-psychology checklist on every ad
and writes `qa_report.json`. `overall: FAIL` if any ad needs revision; per-ad `revision_notes`
tell Agents 5/6 what to fix.

**Gemini model caveat:** `gemini-2.5-flash` reliably fails with `MALFORMED_FUNCTION_CALL`
when emitting large tool-call payloads (e.g. `write_file` with a full report; for the QA agent
even small `read_file` calls). Agents that write files via tools should use `gemini-2.5-pro`.
The Agent 1 sub-agents avoid this by returning JSON as plain final text (no `write_file`), so
they run safely on flash. `core/llm.py` retries empty Gemini responses 3×, escalating
temperature 0.3 → 0.6 → 0.9, and logs the `finish_reason` before raising.

## Paths & config

- `core/config.py` defines `PROJECT_ROOT` (this directory) and resolves every path in
  `config.yaml` `paths:` against it, so `data/output`, `data/brand_ai`, `data/logs`,
  `fixtures` are absolute regardless of CWD. `settings.paths.*` are `Path` objects.
- Switching provider or search engine = one line in `config.yaml` (`llm.provider` /
  `search.provider`). Per-agent model + max_tokens live under `agents:`.

## Adding a new agent

1. Pick the workflow it belongs to and create `embroidery/agents/<workflow>/<role>.py`.
2. Write a system prompt; define tool schemas in Anthropic JSON format (or reuse `core/tools.py`).
3. Add an entry under `agents:` in `config.yaml` with the target model.
4. `from embroidery.core.agent_loop import run_agent` and call
   `run_agent(system, messages, tools, settings.agents.<your_agent>, agent_name="<your_agent>")`.

The loop, tool execution, token logging, search limits, and file logging are automatic.
Always pass `agent_name` so log lines are labelled correctly.

## Env keys

| Key | Required when |
|---|---|
| `ANTHROPIC_API_KEY` | `llm.provider: anthropic` |
| `OPENAI_API_KEY` | `llm.provider: openai` |
| `GEMINI_API_KEY` | `llm.provider: gemini` |
| `BRAVE_API_KEY` | `search.provider: brave` |
