# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## README rule

**After every edit to any file in this repo, update `README.md` in the same directory as the edited file.**

- If no `README.md` exists there yet, create one.
- Keep it current: reflect the actual state of the files after the edit, not before.
- Scope: one README per directory that contains code. The root `README.md` covers the repo overview; `embroidery/README.md` covers the implementation.
- What to include: what the directory does, how to run it, what each file is for. Skip anything derivable by reading the filenames.

---

## Project purpose

This repository designs and implements AI agent teams that run end-to-end marketing campaigns. The agents follow the **EcomTalent framework** and run on a configurable LLM backend (Anthropic Claude by default, OpenAI-compatible) — a direct-response marketing methodology covering market research, customer psychology, ad copywriting, and performance feedback loops.

The primary reference implementation is the custom embroidery shop campaign (`ai-agent-team-embroidery-marketing.md`), which serves as the canonical architecture document for all future campaigns.

The working code lives in `embroidery/`.

---

## Commands

```bash
# Use the project venv (Python 3.11 — system Python 3.14 has a broken pip)
PYTHON=embroidery/venv/bin/python

# Install dependencies
embroidery/venv/bin/pip install "anthropic>=0.40" aiohttp python-dotenv rich pyyaml openai duckduckgo-search

# Smoke test — verifies loop, tools, and file write
cd embroidery && ../venv/bin/python smoke_test.py   # or use full path above

# Run any agent script from the embroidery/ directory
cd embroidery && /path/to/venv/bin/python <script>.py
```

---

## Implementation — `embroidery/`

The implementation uses a layered architecture so LLM provider and search engine are swapped without touching agent code:

```
config.yaml        ← single source of truth for all settings
    ↓
config.py          ← loads yaml + env vars into typed ModelSettings / Config objects
    ↓
llm.py             ← AnthropicProvider | OpenAIProvider  (both implement LLMProvider)
search.py          ← BraveSearch | DuckDuckGoSearch       (both implement SearchProvider)
    ↓
agent_loop.py      ← run_agent() — provider-agnostic loop used by every agent
```

### Switching providers

**LLM engine** — change one line in `config.yaml`:
```yaml
llm:
  provider: anthropic   # → openai
```
Add the matching key to `.env`: `OPENAI_API_KEY=...`

**Search engine** — change one line in `config.yaml`:
```yaml
search:
  provider: duckduckgo   # → brave  (requires BRAVE_API_KEY in .env)
```

**Per-agent model** — edit any agent entry under `agents:` in `config.yaml`:
```yaml
agents:
  audience_researcher:
    model: claude-haiku-4-5   # → claude-sonnet-4-6 or gpt-4o-mini
    max_tokens: 8096
```

### `run_agent()` signature

```python
from agent_loop import run_agent
from config import settings   # ModelSettings objects live on settings.agents.*

result = await run_agent(
    system=SYSTEM_PROMPT,
    messages=[{"role": "user", "content": user_input}],
    tools=TOOL_LIST,
    model_settings=settings.agents.audience_researcher,  # or ModelSettings("claude-haiku-4-5")
)
```

- `tools` use **Anthropic JSON schema format** regardless of provider — `llm.py` converts to OpenAI format internally.
- `messages` accumulate in Anthropic format. The loop appends `response.assistant_message` (provider-native) so history stays correct across providers.
- `response.usage` is logged automatically on every API call.
- Search calls are capped at `search.max_searches` (default 20) per run.

### `.env` keys

```
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...          # only needed when llm.provider=openai
BRAVE_API_KEY=...              # only needed when search.provider=brave
```

`.env` is gitignored. `.env.example` is committed with placeholder values.

---

## Complexity stages — build in order, stop when sufficient

**Rule: validate each stage before adding complexity. Do not add orchestration, parallelism, or feedback loops until the current stage produces quality output.**

### Stage 1 — Single agent (no orchestration)

The simplest useful thing: one agent, one task, one output file. Start here.

```python
import anthropic

client = anthropic.Anthropic()

response = client.messages.create(
    model="claude-haiku-4-5",      # use Haiku for development/testing
    max_tokens=4096,
    system=AGENT_SYSTEM_PROMPT,
    messages=[{"role": "user", "content": user_input}]
)
print(response.content[0].text)
```

Use this for: validating a single system prompt, testing output quality, manual runs.

**Cost target:** < $0.05 per run in development. Switch to production model only after the prompt is validated.

---

### Stage 2 — 2-agent linear pipeline

Add a second agent only after the first produces reliable output. Pass the first agent's output as context to the second. No orchestrator needed — wire them directly in Python.

```python
# Agent 1 produces research
research = run_agent(market_research_agent, product_brief)
write_file("market_research_report.json", research)

# Agent 2 consumes it
positioning = run_agent(positioning_agent, read_file("market_research_report.json"))
write_file("positioning_matrix.json", positioning)
```

Use this for: validating the research → positioning hand-off before building anything else.

**Cost target:** ~$0.10–0.30 per pipeline run. Both agents on Sonnet 4.6 during development.

---

### Stage 3 — Full parallel pipeline (all 8 agents)

Introduce the Orchestrator and `asyncio.gather()` only after Stage 2 passes QA manually. Agents 2+3 and Agents 5+6 run in parallel — everything else is sequential.

```python
import asyncio

# Research phase: Agent 1 blocks, then 2+3 run in parallel
research_data = await run_agent(market_research_agent, brief)

avatar_output, positioning_output = await asyncio.gather(
    run_agent(avatar_agent, research_data),
    run_agent(positioning_agent, research_data)
)

# Copy phase: Agent 4 blocks (hooks needed by scripts), then 5+6 in parallel
hooks = await run_agent(hook_generator, positioning_output)

script_output, static_output = await asyncio.gather(
    run_agent(script_writer, hooks),
    run_agent(static_copy_writer, hooks)
)
```

Use this for: full campaign production runs.

**Cost target:** $1–3 per full pipeline run on production models (see Cost section).

---

### Stage 4 — QA gate + feedback loop

Add Agent 7 (QA) and Agent 8 (Feedback) only after Stage 3 is stable. QA is a blocking gate — loop back to copy agents on FAIL. Feedback Agent runs post-launch, not during production.

```python
# QA gate (blocking)
qa_result = await run_agent(qa_agent, {"scripts": script_output, "static": static_output})
if qa_result["status"] == "FAIL":
    # Re-run copy agents with QA feedback injected into context
    ...

# Feedback loop (post-launch only — requires real ad performance data)
if ad_data_available:
    learnings = await run_agent(feedback_agent, ad_performance_csv)
```

---

## Architecture

### Agent hierarchy

```
Orchestrator (Campaign Director)
  └── Workflow 1 — Research (sequential then parallel)
        ├── Agent 1: Market Research      [blocking first]
        ├── Agent 2: Customer Avatar Builder  [parallel with Agent 3]
        └── Agent 3: Positioning Strategist   [parallel with Agent 2]
  └── Workflow 2 — Copy Production
        ├── Agent 4: Hook Generator       [blocking]
        ├── Agent 5: Video Script Writer  [parallel with Agent 6]
        └── Agent 6: Static Ad Copy Writer [parallel with Agent 5]
  └── Workflow 3 — QA & Feedback
        ├── Agent 7: Quality Check (gatekeeper — loops back to 5/6 on FAIL)
        └── Agent 8: Feedback Loop Analyst (post-launch, triggers new sprint)
```

### Key pipeline rules (enforce in Orchestrator system prompt)

- Research phase is mandatory before any copy. No `positioning_matrix.json` = no copy agents run.
- QA Agent (7) is a blocking gate. Nothing reaches the client until it passes.
- Iteration ratio: no winners yet → 80–90% new angles; winner found → 80% iterations.
- Reset signal: 3 consecutive weeks without a winner → restart from Agent 1.

### Data contracts between agents

Each agent reads and writes named files that form the pipeline:

| File | Produced by | Consumed by |
|---|---|---|
| `market_research_report.json` | Agent 1 | Agents 2, 3 |
| `brand_intelligence_report.md` | Agent 1 | Agents 2, 3 |
| `customer_avatars.md` | Agent 2 | Agents 3, 4, 5, 6 |
| `positioning_matrix.json` | Agent 3 | Agents 4, 5, 6, 7, 8 |
| `hooks_library.json` | Agent 4 | Agents 5, 6 |
| `video_scripts.json` | Agent 5 | Agent 7 |
| `static_ad_copy.json` | Agent 6 | Agent 7 |
| `qa_report.json` | Agent 7 | Orchestrator |
| `weekly_learnings.json` | Agent 8 | Orchestrator (new sprint) |
| `next_week_brief.json` | Agent 8 | Orchestrator |

### Model allocation (production)

| Agent | Model | Reason |
|---|---|---|
| Orchestrator, Market Research, Positioning, Script Writer | `claude-opus-4-8` | Deep reasoning, strategy |
| Avatar Builder, Hook Generator, Static Copy, QA, Feedback | `claude-sonnet-4-6` | Structured output, lower cost |

### Agentic loop pattern

The loop is implemented once in `embroidery/agent_loop.py` and shared by all agents. Do not reimplement it per-agent.

```python
# agent_loop.py handles this internally — callers just use run_agent()
result = await run_agent(system, messages, tools, model_settings)
```

The internal loop (for reference):
```python
while call_count < max_tool_calls:
    response = provider.create_message(model, max_tokens, system, messages, tools)
    if response.stop_reason == "end_turn":
        return response.text
    if response.stop_reason == "tool_use":
        messages.append(response.assistant_message)   # provider-native format
        tool_results = [execute_tool(tc) for tc in response.tool_calls]
        messages.append({"role": "user", "content": tool_results})
```

### Tool types per agent

- **Market Research (Agent 1):** `web_search`, `web_fetch` (server-executed, per-call cost), `write_file` (client-executed)
- **Analysis/Copy agents (2–6):** `read_file`, `write_file` — no web access needed
- **QA Agent (7):** `read_file`, `write_file`, `call_agent` (revision loop trigger)
- **Feedback Agent (8):** `read_csv`, `read_file`, `write_file`, `call_orchestrator`

---

## Cost management

### Model pricing

| Model | Input $/1M | Output $/1M | Use for |
|---|---|---|---|
| `claude-haiku-4-5` | $1.00 | $5.00 | Development, prompt testing, simple structured tasks |
| `claude-sonnet-4-6` | $3.00 | $15.00 | Structured agents (Avatar, Hooks, Static Copy, QA) |
| `claude-opus-4-8` | $5.00 | $25.00 | Deep reasoning (Research, Positioning, Script) |

### Development workflow — minimize cost while building

1. **Write and test every system prompt on Haiku first.** Haiku is ~5x cheaper than Opus. Only switch to the production model after the prompt produces the right output structure.
2. **Use short synthetic inputs during development.** A 500-token test product brief costs 10x less than a real 5,000-token one.
3. **Mock downstream agents.** When testing Agent 5 (Script Writer), feed it a static `hooks_library.json` instead of running Agents 1–4 each time.
4. **Log token counts.** Add `response.usage` logging from day one so you know which agents consume the most tokens.

### Per-stage cost estimates (production models, typical campaign)

| Stage | Agents running | Estimated cost per run |
|---|---|---|
| Stage 1 (single agent test) | 1 agent on Haiku | < $0.05 |
| Stage 2 (research → positioning) | 2 agents on Sonnet | $0.10–0.30 |
| Stage 3 (full 8-agent pipeline) | Mix of Opus + Sonnet | $1.00–3.00 |
| Stage 4 (+ QA loop, 1 revision) | All agents + 1 retry | $1.50–4.00 |

### web_search cost warning

`web_search` and `web_fetch` are server-executed tools billed per call on top of token costs. Agent 1 (Market Research) may trigger 10–20 searches per run. Budget an extra $0.20–0.50 per research run.

To control this: set a `max_searches` counter in Agent 1's tool execution logic and stop the agentic loop after the limit.

### Parallel agents multiply simultaneous token usage

When `asyncio.gather()` runs Agents 2+3 or Agents 5+6 in parallel, both agents consume tokens at the same time. This doesn't change the total cost but does affect rate limits. If you hit rate limits, convert parallel stages to sequential temporarily.

### Prompt caching — use when research data is fed to multiple agents

Research output (`market_research_report.json`, `brand_intelligence_report.md`) is large and consumed by Agents 2, 3, 4, 5, and 6. If these agents are called in the same session, enable prompt caching on the shared research context:

```python
# Mark the research data as cacheable in the system prompt
{"type": "text", "text": research_data, "cache_control": {"type": "ephemeral"}}
```

Cache hits reduce input token cost by ~90%. On a 10,000-token research context read by 5 agents, caching saves ~$0.14 at Sonnet pricing — meaningful at scale.

---

## EcomTalent framework concepts

New agents must respect these marketing principles embedded in every system prompt:

- **Market Awareness (1–5):** Unaware → Problem Aware → Solution Aware → Product Aware → Most Aware. Hook style is determined by this dial.
- **Market Sophistication (1–5, Schwartz):** Default Stage 3+ for any market with Etsy competition.
- **Unique Mechanism:** Introduced only after problem belief is established — wrong order kills the ad.
- **8-element UGC structure:** Hook → Problem → Twist the knife → Product intro → Feature→Benefit → Bad alternative → Results → CTA.
- **Hook architecture:** Every hook is two hooks: visual hook (frame 1 image) + text hook (on-screen words).
- **QA diagnostic:** 8 questions + buying psychology checklist must both pass before any ad is approved.

---

## Build order for new campaigns

1. Agent 1 (Market Research) — validate with live web search on Haiku, then Sonnet
2. Agent 7 (QA) — build the gatekeeper before any content agents; test manually first
3. Agent 3 (Positioning) — strategic layer all copy depends on
4. Agents 4 + 5 (Hooks + Scripts)
5. Agents 2 + 6 (Avatar + Static Copy) — can build in parallel with 4+5
6. Agent 8 (Feedback Loop) — implement only after first ad performance data exists
7. Orchestrator — wire all agents together last; don't add it until Steps 1–6 work manually

---

## References

- EcomTalent Wiki (internal): `https://getifyco.atlassian.net/wiki/spaces/MarketingK3/`
  - Creative Strategy Workflow: page 274468
  - Buying Psychology Playbook: page 144872
  - Market Awareness × Sophistication: page 78820
  - Video Ad Creation System: page 274485
  - AI Marketing Stack: page 144855
- Claude API docs: tool use, agentic loop, parallel tool calls, prompt caching
