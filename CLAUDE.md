# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## README rule

After every file edit, update `README.md` in the same directory (create if absent). Must include: what the directory does, how to run it, what each file is for (skip derivable-from-filename entries), and a **workflow chart** (ASCII or Mermaid) showing component relationships and data flow. Update the chart whenever workflow, data contracts, or component relationships change.

---

## Project

EcomTalent-framework AI agent teams running end-to-end marketing campaigns (market research → copy → QA → feedback loop). Reference implementation: `ai-agent-team-embroidery-marketing.md`. Working code: `embroidery/`.

## Commands

```bash
# Python 3.11 venv required — system Python 3.14 has broken pip
embroidery/venv/bin/pip install "anthropic>=0.40" aiohttp python-dotenv rich pyyaml openai duckduckgo-search "google-genai>=1.0"
cd embroidery && venv/bin/python smoke_test.py   # verifies loop + tools + file write
```

`.env` keys (gitignored; `.env.example` committed): `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `BRAVE_API_KEY`

---

## Architecture

```
config.yaml → config.py (typed Config / ModelSettings)
                   ↓
  llm.py (Anthropic|OpenAI|GeminiProvider)  +  search.py (Brave|DuckDuckGo)
                   ↓
  agent_loop.py: run_agent(system, messages, tools, model_settings, agent_name)
                   ↓
  logger.py → stdout INFO+  /  logs/<YYYYMMDD_HHMMSS>.log DEBUG+
```

- Tool schemas are always in **Anthropic JSON schema format** — `llm.py` converts to OpenAI/Gemini internally.
- Messages accumulate in **Anthropic format** across all providers.
- Switching provider or search engine = one line in `config.yaml` (`llm.provider` / `search.provider`).
- **Always pass `agent_name=`** to `run_agent()` — defaults to `"agent"` in log lines without it.

## Logging (emitted automatically by `agent_loop.py`)

| Event | Log line |
|---|---|
| Start | `agent=X model=Y max_tokens=N starting` |
| Each LLM call | `agent=X call=N model=Y in=N out=N` |
| Tool execution | `tool=write_file file=X` / `tool=web_search count=N query=X` |
| End | `agent=X done calls=N total_in=N total_out=N` |

Add to any module: `from logger import get_logger; log = get_logger(__name__)`

---

## Complexity stages — validate before advancing

| Stage | What's added | Cost/run (prod models) |
|---|---|---|
| 1 — Single agent | One agent, one output file. All prompt dev on Haiku | <$0.05 |
| 2 — Linear pipeline | Agent 1 output feeds Agent 2; no orchestrator | $0.10–0.30 |
| 3 — Parallel pipeline | Orchestrator + `asyncio.gather()` for agents 2+3, 5+6 | $1–3 |
| 4 — QA gate + feedback | Agent 7 blocks; re-runs 5+6 on FAIL. Agent 8 post-launch only | $1.50–4 |

Stage 3 execution order (non-obvious — 4 must block because 5+6 need hooks):
```python
research = await run_agent(agent1, ...)
avatar, positioning = await asyncio.gather(run_agent(agent2), run_agent(agent3))
hooks = await run_agent(agent4, ...)   # sequential — 5+6 depend on this
scripts, static = await asyncio.gather(run_agent(agent5), run_agent(agent6))
```

---

## Agent hierarchy and pipeline

```
Orchestrator
  Workflow 1 — Research
    Agent 1: Market Research         [sequential, blocking]
    Agent 2: Customer Avatar Builder  [parallel with 3]
    Agent 3: Positioning Strategist   [parallel with 2]
  Workflow 2 — Copy
    Agent 4: Hook Generator          [sequential, blocking]
    Agent 5: Video Script Writer      [parallel with 6]
    Agent 6: Static Ad Copy Writer    [parallel with 5]
  Workflow 3 — QA & Feedback
    Agent 7: QA Reviewer             [gatekeeper — loops 5+6 on FAIL]
    Agent 8: Feedback Analyst        [post-launch only]
```

**Pipeline invariants (enforce in Orchestrator system prompt):**
- No `positioning_matrix.json` → copy agents don't run.
- 3 consecutive weeks without a winner → restart from Agent 1.
- Iteration ratio: no winner → 80–90% new angles; winner exists → 80% iterations on winner.

**Data contracts:**

| File(s) | Written by | Read by |
|---|---|---|
| `market_research_report.json`, `brand_intelligence_report.md` | 1 | 2, 3 |
| `customer_avatars.md` | 2 | 3, 4, 5, 6 |
| `positioning_matrix.json` | 3 | 4, 5, 6, 7, 8 |
| `hooks_library.json` | 4 | 5, 6 |
| `video_scripts.json` | 5 | 7 |
| `static_ad_copy.json` | 6 | 7 |
| `qa_report.json` | 7 | Orchestrator |
| `weekly_learnings.json`, `next_week_brief.json` | 8 | Orchestrator |

**Tool access per agent:**
- Agent 1: `web_search`, `web_fetch` (billed per call — budget +$0.20–0.50/run; capped by `search.max_searches`), `write_file`
- Agents 2–6: `read_file`, `write_file`
- Agent 7: `read_file`, `write_file`, `call_agent`
- Agent 8: `read_csv`, `read_file`, `write_file`, `call_orchestrator`

---

## Model allocation and cost

| Model | $/1M in | $/1M out | Assigned agents |
|---|---|---|---|
| `claude-haiku-4-5` | $1 | $5 | Dev/prompt validation only |
| `claude-sonnet-4-6` | $3 | $15 | Avatar, Hooks, Static Copy, QA, Feedback |
| `claude-opus-4-8` | $5 | $25 | Orchestrator, Market Research, Positioning, Script |

- Prompt caching: mark shared research context with `{"cache_control": {"type": "ephemeral"}}` — ~90% input cost reduction for the 5 agents that re-read it.
- `asyncio.gather()` doesn't change total cost but exhausts rate limits simultaneously — convert to sequential if rate-limited.

---

## Build order for new campaigns

1. Agent 1 (Market Research) — validate on Haiku with live search, then promote to Sonnet
2. Agent 7 (QA) — build gatekeeper before any content agents; test manually first
3. Agent 3 (Positioning) — all copy agents depend on this output
4. Agents 4+5 (Hooks + Scripts)
5. Agents 2+6 (Avatar + Static Copy) — can run in parallel with step 4
6. Agent 8 (Feedback) — implement only after first real ad performance data exists
7. Orchestrator — wire last; don't add until steps 1–6 work in manual runs

---

## EcomTalent framework (embed in every agent system prompt)

- **Awareness dial (1–5):** Unaware → Problem Aware → Solution Aware → Product Aware → Most Aware. Hook style follows this.
- **Sophistication (Schwartz 1–5):** Default Stage 3+ for any Etsy-competitive market.
- **Unique Mechanism:** Introduce only after problem belief is established — wrong order kills conversion.
- **UGC 8-element structure:** Hook → Problem → Twist the knife → Product intro → Feature→Benefit → Bad alternative → Results → CTA.
- **Hook = two hooks:** visual hook (frame 1 image) + text hook (on-screen words).
- **QA gate:** 8 diagnostic questions + buying psychology checklist — both must pass.

---

## References

EcomTalent Wiki: `https://getifyco.atlassian.net/wiki/spaces/MarketingK3/`
— Creative Strategy: p274468 | Buying Psychology: p144872 | Awareness×Sophistication: p78820 | Video Ad System: p274485 | AI Stack: p144855
