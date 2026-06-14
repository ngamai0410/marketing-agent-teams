# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## README rule

Each meaningful directory has a `README.md` covering: what the directory does, how to run it, what each file is for (skip derivable-from-filename entries), and a **workflow chart** (ASCII or Mermaid) showing component relationships and data flow. The package agent dirs each own one — `embroidery/README.md` (top), `embroidery/core/`, `embroidery/agents/` (index) + one **per workflow** (`agents/research/`, `agents/avatar/`, `agents/qa/`, future `agents/copy/`), and `tests/`.

**Create or update the relevant README(s) when a change is significant** — i.e. when it alters something a README documents. Significant = any of:
- a new file/module, agent, or directory; a renamed/moved/deleted one;
- a changed **data contract** (a file an agent reads/writes, or its schema/fields);
- a changed **workflow or component relationship** (who calls whom, parallel→sequential, a new tool, a model reassignment);
- a changed **run command, entry point, or setup/dependency**;
- new or changed config keys that affect how the directory is used.

Then update **every** README that references the changed thing — a moved file or new data contract usually touches the dir's own README, the `agents/` index, and `CLAUDE.md`'s architecture/data-contract tables. Keep the workflow chart in sync; a stale chart is worse than none.

**Not significant** (skip the README): typo/comment/formatting fixes, internal refactors that don't change a public interface or data flow, prompt-wording tweaks that don't change a contract, log-message changes. When unsure, ask: "would someone reading the README now be misled?" — if yes, update it.

## Plan status rule

At the end of every working day (and before ending any session that built or changed an agent), update `development-plan.md` to reflect actual state: check off completed items, and record deviations from the plan inline (e.g. architecture differs from spec, work pulled forward/pushed back, provider changes). The plan must never claim something is pending that is already built, or vice versa.

---

## Project

EcomTalent-framework AI agent teams running end-to-end marketing campaigns (market research → copy → QA → feedback loop). Reference implementation: `ai-agent-team-embroidery-marketing.md`. Working code: `embroidery/`.

## Commands

```bash
# Python 3.11 venv required — system Python 3.14 has broken pip
embroidery/venv/bin/pip install "anthropic>=0.40" aiohttp python-dotenv rich pyyaml openai duckduckgo-search "google-genai>=1.0" "fastapi>=0.110" "uvicorn[standard]>=0.27"
cd embroidery && venv/bin/python -m tests.smoke_test   # verifies loop + tools + file write
cd embroidery && venv/bin/python -m embroidery.web     # live monitoring dashboard + QC gates (browser)
```

**Package layout (run everything from `embroidery/` as modules):** the code is the
`embroidery` package — `embroidery/core/` (reusable kernel) and `embroidery/agents/<workflow>/`
(campaign agents, grouped Research/Copy/QA). Tests live in `tests/`. Runtime artifacts go to
`data/{output,brand_ai,logs}` (paths resolved against `PROJECT_ROOT` in `core/config.py`).
Flat `python file.py` no longer works — use `python -m embroidery.agents.research.pipeline`,
`python -m tests.smoke_test`, etc.

`.env` keys (gitignored; `.env.example` committed): `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `BRAVE_API_KEY`

---

## Architecture

```
config.yaml → core/config.py (typed Config / ModelSettings; PROJECT_ROOT-anchored paths)
                   ↓
  core/llm.py (Anthropic|OpenAI|GeminiProvider)  +  core/search.py (Brave|DuckDuckGo)
                   ↓
  core/agent_loop.py: run_agent(system, messages, tools, model_settings, agent_name)
                   ↓
  core/logger.py → stdout INFO+  /  data/logs/<YYYYMMDD_HHMMSS>.log DEBUG+
  core/reporter.py ← run_agent emits per-agent metrics (calls/tokens/searches/$/elapsed)
                   ↓ async pub/sub  (workflow field tags each row to its lane)
  core/workflow.py  WorkflowSpec registry ← each pipeline module registers itself at import
                   ↓ load_workflows() / get_registry()
  core/orchestrator.py  run_team(): registry walk · data-contract input gating · QA re-loop
                   ↓
  embroidery/web/ (FastAPI + uvicorn + SSE)  ⇄  core/checkpoint.py (QC gates, workflow= field)
  └─ browser dashboard: lanes + rail + Test/Run panel; research + avatar + QA wired
                        monitor (live agent rows per lane) · test (stage-range, fixture seed,
                        prompt preview) · edit (prompts + per-gate brief) · Approve / Edit / Quit
```

**Monitoring + human-in-the-loop layer.** `core/reporter.py` (`RunReporter` singleton) is a
passive metrics accumulator + async event bus; `run_agent()` taps it at start/call/search/done
(no behaviour change, no-op without subscribers). `AgentRecord` now carries a `workflow` field
(set via `reporter.workflow_context(id)` contextmanager) so the dashboard can group rows by lane.
`core/checkpoint.py`'s `await checkpoint(stage, digest, *, workflow="", request=...)` pauses a
pipeline between stages, publishing a `gate` event (with `workflow=`) the dashboard renders; the
user's decision (`APPROVE`/`EDIT`/`QUIT`) flows back so a stage can re-run with an adjusted
request. `embroidery/web/` serves the single-page dashboard (SSE live stream + `/gate`
resolution); standalone CLI runs auto-approve gates (`EMBROIDERY_YES=1` or no subscriber). Each
run writes a perf digest to `data/output/run_report.md`. Web host/port: `config.yaml` → `web:`
(default `127.0.0.1:8765`).

**WorkflowSpec registry + orchestrator.** `core/workflow.py` is the single source of truth for
the agent team: each pipeline module calls `register(WorkflowSpec(...))` at import, declaring its
stages, async `entry_point`, `prompt_catalog`, data-contract `inputs`/`outputs`, `fixtures`, and
`config_schema`. `load_workflows()` imports all pipeline modules in canonical order (research →
avatar → qa; tolerant of not-yet-built ones). `core/orchestrator.py`'s `run_team()` is fully generic: it
walks the registry `[start..stop]`, asserts each workflow's declared `inputs` exist under
`data/output/` before it starts (the data-contract gate — **no `positioning_matrix.json` → Copy
is blocked**, publishes a `blocked` done event), runs each `entry_point` inside
`reporter.workflow_context(id)`, and after the `qa` workflow re-loops back to `copy` on overall
FAIL (bounded by `max_qa_loops`). `run_team` owns the run-level `done`/`aborted`/`blocked` event
and `run_report.md`. The web layer calls `run_team` for every `POST /start` request.

**Editable prompts.** `core/prompt_store.py` lets the user view/edit/save each agent's **system
prompt** before a run (dashboard **⚙ Agent prompts** panel). Templates are authored as
`.format` strings (JSON braces escaped `{{}}`, context via `{shop_context}`); `to_dollar()`
converts them once to a brace-safe `$placeholder` form for editing, overrides persist to
`data/prompts/overrides.json`, and `build_system()` / `run_synthesizer()` render via
`PromptStore.render` (`Template.safe_substitute` — a removed placeholder degrades gracefully).
A new agent makes its prompts editable by exposing a `prompt_catalog()` and rendering through
the store (see `agents/research/`). The shared **`{shop_context}` block itself is editable**
(catalog id `shared.shop_context`, "Shared — Shop context"): research + avatar agents resolve it
via `resolved_shop_context()` / `effective_shop_context()` in `agents/research/subagents.py`, so a
saved override replaces the brief-rendered default for **every** agent in both workflows.

**Editable models.** Each agent's row in the ⚙ panel also has a **model picker** (`core/model_store.py`
+ `core/model_catalog.py`, endpoints `/models` · `/models/reset`): pick a provider model (with
pros/cons + $/1M cost shown) per agent. The choice persists to `data/prompts/model_overrides.json`
and is applied onto `settings.agents.<key>` at startup, so `run_agent()` picks it up. The picker
offers only the active provider's models (`config.yaml` `llm.provider`); `core/model_catalog.py` is
the single source of Gemini pricing, merged into `core/reporter.py`'s cost table so badges never drift.

**Web UI — needs for the whole team (monitor / test / edit).** Research, Avatar, and QA are wired;
Copy and Feedback remain future work. The dashboard is the single local control surface for the
**entire 8-agent team** (Research → Copy → QA → Feedback). Build every new workflow toward these
three pillars — each is a *requirement on the UI*, not just the pipeline:

- **Monitor** — every agent across all workflows appears in the live table the moment it starts
  (call/token/$/search/elapsed via `reporter.py`), grouped into workflow **lanes** with a
  **rail** header. Sub-agent fan-out (A/B/C-style parallelism) is visible as distinct rows.
  Each agent row **expands into a labeled step pipeline** (call/search/fetch/write) ending in
  an inline output viewer (`reporter.py` `steps` → `GET /output/{file}`).
  Crashes surface as a `done`/`error` event, never a silent hang. ✅ built.
- **Test** — the user can exercise one agent or one workflow in isolation: pick a start/stop
  stage, run against committed **fixtures** (`fixtures/`) via `seed_fixtures` in `POST /start`,
  and dry-run a prompt edit via `POST /prompts/preview`. The 🧪 Test/Run panel in the UI wires
  all three. Each workflow's `entry_point` is invokable standalone via `target=<id>` in
  `POST /start`; `run_team` covers the "full team" entry. ✅ built (research + avatar + QA).
- **Edit** — before *and between* stages: (a) any agent **system prompt** (`prompt_store.py`,
  **⚙ Agent prompts**), (b) the **request/brief** via the `EDIT` gate decision, (c) run config
  from the UI ☐ (phase 5). A **QC gate (`checkpoint.py`) sits at every workflow boundary** (after
  Research ✅, after Avatar ✅, after QA ✅; after Copy ☐ — not built yet). The data-contract gate is enforced by
  the orchestrator (no `positioning_matrix.json` → Copy blocked, `blocked` event surfaced).

Extending the dashboard to a workflow = give its pipeline a gate-driven loop (publish `stage`,
`await checkpoint(workflow=id)` at boundaries), wrap in `reporter.workflow_context(id)`, pass
`agent_name=` everywhere, expose `prompt_catalog()`, call `register(WorkflowSpec(...))` at
import, and add the module to `load_workflows()` in `core/workflow.py`. No new endpoints needed
until a workflow needs a contract the current `/start` · `/gate` · `/workflows` · `/prompts` ·
`/prompts/reset` · `/prompts/preview` · `/artifacts` · `/output` · `/report` set can't express —
add to `web/README.md` if so.

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

Add to any module: `from embroidery.core.logger import get_logger; log = get_logger(__name__)`

---

## Agent hierarchy and pipeline

```
Orchestrator
  Workflow 1 — Research
    Agent 1: Market Research         [sequential, blocking]
  Workflow 2 — Avatar  [own lane — 9 Evolve stages; see docs/superpowers/specs/2026-06-13-avatar-builder-workflow-design.md]
    Agent 2: Customer Avatar Builder  [sequential gated pipeline: onboarding→product→discovery→qualify→voc→awareness→competitor→mechanism→synthesis]
  Workflow 3 — Copy
    Agent 3: Positioning Strategist   [sequential, blocking]
    Agent 4: Hook Generator          [sequential, blocking]
    Agent 5: Video Script Writer      [parallel with 6]
    Agent 6: Static Ad Copy Writer    [parallel with 5]
  Workflow 4 — QA & Feedback
    Agent 7: QA Reviewer             [gatekeeper — loops 5+6 on FAIL]
    Agent 8: Feedback Analyst        [post-launch only]
```

**Pipeline invariants (enforce in Orchestrator system prompt):**
- No `positioning_matrix.json` → copy agents don't run.
- 3 consecutive weeks without a winner → restart from Agent 1.
- Iteration ratio: no winner → 80–90% new angles; winner exists → 80% iterations on winner.

**Data contracts** (all live in `data/output/`, overwritten each run):

| File(s) | Written by | Read by |
|---|---|---|
| `market_research_report.json`, `brand_intelligence_report.md` | 1 | 2, 3 |
| `customer_avatars.md` | 2 | 3, 4, 5, 6 |
| `avatar_deep_dive.json` | 2 | 3 |
| `positioning_matrix.json` | 3 | 4, 5, 6, 7, 8 |
| `hooks_library.json` | 4 | 5, 6 |
| `video_scripts.json` | 5 | 7 |
| `static_ad_copy.json` | 6 | 7 |
| `qa_report.json` | 7 | Orchestrator |
| `weekly_learnings.json`, `next_week_brief.json` | 8 | Orchestrator |
| `run_report.md` (per-run agent perf digest: calls/tokens/$/elapsed) | `core/reporter.py` (any pipeline) | human / dashboard |

**Tool access per agent:**
- Agent 1: `web_search`, `web_fetch` (billed per call — budget +$0.20–0.50/run; capped by `search.max_searches` shared per run **and** `search.max_searches_per_agent`, both enforced in `core/agent_loop.py` — prompts alone are ignored by flash). Sub-agents A/B/C are **search-only** (`SEARCH_TOOLS`) and return JSON as final text — Python persists `data/output/research_*.json`; this avoids flash's MALFORMED_FUNCTION_CALL on large tool payloads. The Synthesizer has **no tools** (2 calls on pro: JSON report, then markdown narrative); `BrandAI` (`core/brand_store.py`) keeps timestamped history in `data/brand_ai/<shop>/`.
- Agent 2 (avatar): search agents (onboarder/product/3 scouts/voc) use `web_search`/`web_fetch` and return JSON-as-text (same flash pattern as Agent 1); qualifier/reframers/synthesizer have **no tools** (gemini-2.5-pro, 9 stages total). Config: `avatar.priority_count` (default 2 — top-N avatars to carry forward from qualify stage).
- Agents 3–6: `read_file`, `write_file`
- Agent 7: `read_file`, `write_file`, `call_agent`
- Agent 8: `read_csv`, `read_file`, `write_file`, `call_orchestrator`

---

## Model allocation and cost

| Model | $/1M in | $/1M out | Assigned agents |
|---|---|---|---|
| `claude-haiku-4-5` | $1 | $5 | Dev/prompt validation; Avatar **search** agents (onboarder, product, Reddit/Amazon/FB scouts, VOC) |
| `claude-sonnet-4-6` | $3 | $15 | Avatar **reasoning** agents (qualifier, awareness/competitor/mechanism reframers, synthesizer), Hooks, Static Copy, QA, Feedback |
| `claude-opus-4-8` | $5 | $25 | Orchestrator, Market Research, Positioning, Script |

> The table is the Anthropic-tier allocation. The live `config.yaml` runs everything on **Gemini** (flash ≈ haiku tier for search/JSON-as-text agents, pro ≈ sonnet/opus tier for reasoning/synthesis) — switch providers in one line (`llm.provider`).

- Prompt caching: mark shared research context with `{"cache_control": {"type": "ephemeral"}}` — ~90% input cost reduction for the 5 agents that re-read it.
- `asyncio.gather()` doesn't change total cost but exhausts rate limits simultaneously — convert to sequential if rate-limited.

---

## Build order for new campaigns

1. Agent 1 (Market Research) — validate on Haiku with live search, then promote to Sonnet ✅ built
2. Agent 7 (QA) — build gatekeeper before any content agents; test manually first ✅ built
3. Agent 2 (Avatar) — built as the standalone `avatar` workflow lane (9 Evolve stages), wired into registry + dashboard; runs after research, before copy ✅ built
4. Agent 3 (Positioning) — all copy agents depend on this output
5. Agents 4+5 (Hooks + Scripts)
6. Agent 6 (Static Copy) — can run in parallel with step 5
7. Agent 8 (Feedback) — implement only after first real ad performance data exists
8. Orchestrator — wire last; don't add until steps 1–7 work in manual runs

As each workflow comes online, wire it into the dashboard the same step it's built — gate-driven
loop, `prompt_catalog()`, standalone entry point (see **Web UI — needs for the whole team**). A
workflow isn't "done" until you can monitor, test (fixture/per-stage), and edit it from the UI.

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
