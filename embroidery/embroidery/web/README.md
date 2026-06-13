# embroidery/web/ — live monitoring dashboard + QC gates

A local web dashboard so the end user can **edit each agent's prompt before Start**, **watch
the agent team work live**, and **QC / adjust the request at each step**. FastAPI + uvicorn
serve a single vanilla HTML page (no build step); the page streams agent metrics over
Server-Sent Events and resolves the human-in-the-loop checkpoints (`core/checkpoint.py`) with
Approve / Edit / Quit buttons. The **⚙ Agent prompts** panel (collapsed by default) lists every
system prompt — expand to edit, Save persists an override (`core/prompt_store.py` →
`data/prompts/overrides.json`), Reset restores the default. Prompts lock while a run is in flight.

## Run

```bash
cd embroidery && venv/bin/python -m embroidery.web            # opens the browser
venv/bin/python -m embroidery.web --no-browser                # don't auto-open
venv/bin/python -m embroidery.web --yes                       # watch live, but auto-approve gates
```

Host/port come from `config.yaml` → `web:` (default `127.0.0.1:8765`). Localhost,
single-user, no auth.

## Files

| File | Purpose |
|---|---|
| `server.py` | FastAPI `app` + endpoints (below). Calls `load_workflows()` at import to populate the registry; routes `POST /start` through `run_team`. |
| `__main__.py` | Launcher — `uvicorn.run(...)` + opens the browser. `--yes` / `--no-browser` flags. |
| `static/index.html` | The whole UI: workflow **lanes** (one column per registered workflow, agent rows grouped by lane) + workflow **rail** header; **🧪 Test / run** panel (target, stage range, seed-from-fixtures, dry-run prompt preview); gate card; done panel. Vanilla HTML/CSS/JS + `EventSource`. |

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Serve `static/index.html`. |
| GET | `/events` | SSE stream. On connect: current `reporter.snapshot()` + any open gate, then live events. |
| GET | `/workflows` | Registry snapshot: all registered `WorkflowSpec`s with their stages, inputs, outputs, fixtures, config_schema. |
| POST | `/start` | Kick off a run as an asyncio task via `run_team` (409 if already running). Body: `{target: "team"\|<workflow_id>, start_stage?, stop_stage?, brief?, seed_fixtures?}`. |
| POST | `/gate` | Resolve a pending gate: `{gate_id, decision: approve\|edit\|quit, request?}`. |
| GET | `/report` | Raw `data/output/run_report.md`. |
| GET | `/output/{file}` | A whitelisted `.json`/`.md` artifact for inspection during QC. |
| GET | `/artifacts` | List all `.json`/`.md` files currently in `data/output/`. |
| GET | `/prompts` | Registry-driven catalog of every editable agent prompt (`id`, `name`, `placeholders`, `text`, `default`, `overridden`) + `editable` (false while a run is in flight). |
| POST | `/prompts` | Save an override: `{id, text}`. 409 while a run is in progress, 404 for unknown id. |
| POST | `/prompts/reset` | `{id}` → drop the override, return the refreshed (default) item. |
| POST | `/prompts/preview` | Dry-run render: `{id, text?}` → `{rendered}`. Substitutes sample context variables into the prompt template without spending tokens. |

## Event types (reporter → browser, over SSE)

`agents` (table snapshot + totals) · `stage` (banner) · `gate` (open a QC card with digest +
editable brief) · `gate_closed` · `done` (status complete/aborted/error + artifact links).

## Workflow

```
browser ──GET /────────────► index.html  (lanes + rail + Test/Run panel)
        ──GET /events──────► SSE  ◄──pub/sub── core/reporter.py ◄─emit─ core/agent_loop.py
        ──GET /workflows───► registry snapshot (WorkflowSpec list)
        ──POST /start──────► create_task(run_team)
                                     │  core/orchestrator.py
                                     │  ├─ data-contract input gate → "blocked" done event
                                     │  ├─ reporter.workflow_context(id) per workflow
                                     │  ├─ entry_point(brief, start_stage, stop_stage, gate)
                                     │  └─ QA FAIL re-loop → copy (bounded by max_qa_loops)
                                     │ between stages
                                     ▼
        ◄── "gate" event ──  core/checkpoint.py  (awaits a Future; carries workflow=)
        ──POST /gate───────► resolve_gate(gate_id, decision, request)
                                     │ Approve→continue  Edit→re-run stage  Quit→abort
                                     ▼
        ◄── "done" event ──  run_report.md + output artifacts linked
```

Everything runs in one asyncio loop: uvicorn serves while the pipeline runs as a task
(`run_agent` offloads blocking provider calls via `asyncio.to_thread`, keeping SSE responsive).
`POST /start` with `target="team"` walks all registered workflows in order; `target=<id>`
runs a single workflow in isolation (useful for the Test panel).

## Design requirements (whole-team scope)

This dashboard is the single local control surface for the **entire 8-agent team**
(Research → Copy → QA → Feedback, under the Orchestrator). Research and QA are wired;
Copy and Feedback are future work. Status: ✅ built · ◐ partial (research + QA wired; copy/feedback later) · ☐ not yet built.

### Monitor — see the team work live
- ✅ Per-agent live row the moment it starts: calls / tokens / $ / searches / elapsed (`reporter.py`).
- ✅ Stage banner shows the current step; `done`/`error` event surfaces crashes (never a silent hang).
- ✅ Sub-agent fan-out (A/B/C-style parallelism) renders as **distinct rows**, not collapsed into the parent.
- ✅ Workflow **lanes** + **rail** — agent rows grouped by workflow, visible the moment `workflow_context` is entered (`reporter.py` `workflow` field).

### Test — exercise a part without running the whole chain
- ✅ Pick a **start/stop stage** so one agent or one workflow runs in isolation (`start_stage`/`stop_stage` in `POST /start`).
- ✅ Run against committed **fixtures** (`fixtures/`) instead of live providers — `seed_fixtures` in `POST /start` copies them to `data/output/` before the run.
- ✅ **Dry-run a prompt edit** — `POST /prompts/preview` renders the system prompt with sample context without spending tokens.
- ◐ Each workflow exposes a standalone entry point the dashboard invokes (research = `run_market_research`, qa = `run_qa`);
  Copy and Feedback entry points remain future work; `run_team` provides the "full team" entry today.

### Edit — change inputs before *and between* stages
- ✅ Any agent **system prompt** via the ⚙ Agent prompts panel (`prompt_store.py`), locked mid-run.
- ✅ The **request/brief** a stage re-runs with — the `EDIT` gate decision (`checkpoint.py`).
- ☐ Run **config** (model, search caps) from the UI (phase 5).
- ◐ A **QC gate at every workflow boundary** — after Research (✅), after QA (✅), after Copy (☐ — copy not built yet) — Approve / Edit & re-run / Quit before the next workflow consumes the artifacts.
- ✅ Data-contract input gate: `run_team` (orchestrator) checks each workflow's declared `inputs` exist in `data/output/` before starting it; publishes `blocked` done event (not a silent skip) when files are missing.
- ◐ QA FAIL → re-loop: orchestrator logic exists and is wired; the Copy workflow it loops back to is not yet built; **3-weeks-no-winner → restart-from-Agent-1** remains a future gate (☐).

### Wiring a new workflow in
Register a `WorkflowSpec` (see `core/workflow.py`): give the pipeline module an async
`entry_point(brief, *, start_stage, stop_stage, gate)`, a `prompt_catalog()`, and call
`register(WorkflowSpec(...))` at import; add the module to `load_workflows()` in
`core/workflow.py`. The current `/start` · `/gate` · `/workflows` · `/prompts` ·
`/prompts/reset` · `/prompts/preview` · `/artifacts` · `/output` · `/report` set covers
it — add an endpoint (and a row to the table above) only when a workflow needs a contract
these can't express.
