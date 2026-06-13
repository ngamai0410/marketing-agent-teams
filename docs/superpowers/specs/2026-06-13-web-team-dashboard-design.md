# Whole-Team Web Dashboard — Design (North-Star)

**Date:** 2026-06-13
**Status:** Approved design — ready for implementation plan
**Scope:** Generalize the local web dashboard from the research-only wiring it is today
into one control surface that can **monitor / test / edit** every workflow of the 8-agent
team (Research → Copy → QA → Feedback, under an Orchestrator). This is a north-star spec:
it describes the full end state and folds in a phased build order. Pieces that cannot be
built until their agents exist are marked **[later]** / **[documented-not-built]**.

---

## 1. Goal & context

Today `embroidery/web/` (FastAPI + uvicorn + SSE, one vanilla HTML page) wires only the
**research** pipeline: a live agent table, QC gates between the two research stages, and the
⚙ Agent-prompts editor. A standalone Agent 7 (QA) exists in code but is not wired in.

The team's three UI pillars (already documented in `CLAUDE.md` and `web/README.md`) are the
target for the **whole team**, not just research:

- **Monitor** — every agent across all workflows visible live as it runs.
- **Test** — exercise one agent / one workflow in isolation without the whole chain.
- **Edit** — change prompts, the per-stage brief, and run config before *and between* stages,
  with a QC gate at every workflow boundary.

The core architectural decision: a **declarative `WorkflowSpec` registry** is the single
source of truth. The web layer and the Orchestrator are **generic** — they iterate the
registry and gain no per-workflow code. Adding a workflow = write its pipeline + register a
spec.

### Decisions locked during brainstorming

| Decision | Choice |
|---|---|
| Design deliverable | Full end-state north-star with a phased build order |
| Test model | **Stage selection + seeded input artifacts**, always-live. No fake/stub LLM provider, no record-replay. "Dry-run a prompt" = render & preview the resolved prompt, no execution. |
| Run lifecycle | **Single linear pass** (Research→Copy→QA) with human gates; QA `FAIL` re-loops Copy in the same run. Cross-run "weeks without a winner" persistence is a **documented later phase**. |
| Monitor layout | **Workflow lanes** — one collapsible lane per workflow, its own agent sub-table, inline gate bars between lanes, parallel sub-agents indented, active lane auto-expands. |
| Harness style | **`WorkflowSpec` registry (declarative)** — chosen over duck-typing/convention and over an event-viewer-only dashboard. |

---

## 2. Architecture

```
core/workflow.py — WorkflowSpec registry (NEW, source of truth)
  WorkflowSpec(id, label,
    stages=[Stage(name, agents, digest)],
    entry_point=async run(brief, *, start_stage=None, stop_stage=None, gate=checkpoint),
    prompt_catalog,           # existing per-agent prompt list
    inputs=[...],             # data-contract files this workflow reads
    outputs=[...],            # data-contract files it writes
    fixtures=[...],           # committed sample artifacts that can seed `inputs`
    config_schema={...})      # editable run config (per-agent model, search caps)
            │ register()                         ▲ get_registry()
            ▼                                     │
  agents/research/ ✓ (retrofit)   agents/copy/ [later]   agents/qa/ + feedback/ [later/exists]
            │  both consume the registry; neither changes per-workflow │
            ▼                                     ▼
  core/orchestrator.py (NEW, generic)      embroidery/web/ (generic)
    run_team(start, stop, brief)             /workflows → registry
    · walks registry in order                /start {workflow|team, stages, fixtures, config}
    · enforces inputs ⊆ prior outputs        /gate · /prompts · /output · /report
    · checkpoint() at each boundary          lanes render from stages[]
    · QA FAIL → re-loop Copy
            │ taps existing bus │
            ▼
  core/reporter.py + checkpoint.py (extend: add a `workflow` tag to events)
    run_agent emits agent/stage/workflow events → SSE → lanes grouped by workflow
```

**Invariant:** the web layer and orchestrator never gain per-workflow branches. All
per-workflow knowledge lives in that workflow's `WorkflowSpec`.

---

## 3. Components

### 3.1 `core/workflow.py` (new)

Dataclasses + a process-wide registry.

```python
@dataclass(frozen=True)
class Stage:
    name: str                      # e.g. "sub-agents A/B/C", "synthesis", "hooks"
    agents: list[str]              # agent_name values this stage runs (for lane rows)
    digest: Callable[..., dict]    # builds the compact gate-card digest for this stage

@dataclass(frozen=True)
class WorkflowSpec:
    id: str                        # "research", "copy", "qa", "feedback"
    label: str                     # "Research"
    stages: list[Stage]
    entry_point: Callable          # async run(brief, *, start_stage, stop_stage, gate)
    prompt_catalog: Callable[[], list[dict]]
    inputs: list[str]              # data-contract filenames read (relative to data/output)
    outputs: list[str]             # data-contract filenames written
    fixtures: list[str]            # committed sample files (relative to fixtures/) that seed inputs
    config_schema: dict            # editable run config + defaults

_REGISTRY: dict[str, WorkflowSpec] = {}
def register(spec: WorkflowSpec) -> None: ...
def get_registry() -> list[WorkflowSpec]: ...   # ordered
def get_spec(id: str) -> WorkflowSpec: ...
```

Workflow modules call `register(...)` at import. The web layer imports the workflow package
once so registration happens (lazy, as today, to avoid web↔agents hard-coupling at load).

### 3.2 `entry_point` contract

`async def run(brief, *, start_stage=None, stop_stage=None, gate=checkpoint) -> result`

- Runs the workflow's stages in order. If `start_stage` is set, earlier stages are skipped
  and their `outputs` are expected to already exist on disk (real prior run or seeded fixture).
  If `stop_stage` is set, execution halts after that stage.
- `gate` defaults to `core/checkpoint.checkpoint`; injectable so tests can pass a stub.
- The research `run_market_research` is retrofitted to this signature (it already takes a
  `brief` and runs two gated stages).

### 3.3 `core/orchestrator.py` (new, generic)

`async def run_team(start=<first>, stop=<last>, brief=None)`:

1. Slice the registry to `[start..stop]`.
2. For each workflow in order: assert every `inputs` file exists in `data/output`
   (satisfied by a prior workflow's `outputs` or a seeded fixture). If not → publish a
   blocked-gate event naming the missing file; do not run. **This is the enforcement of
   "no `positioning_matrix.json` → Copy doesn't run."**
3. Run the workflow's `entry_point`. At each workflow boundary call `checkpoint()`:
   `APPROVE`→next, `EDIT`→re-run current workflow with edited brief, `QUIT`→abort.
4. **QA FAIL re-loop:** after QA, read `qa_report.json`; on `FAIL`, loop back to Copy with
   the QA notes as the brief (bounded retry count, surfaced as a gate).
5. "Full team" run = `start=first, stop=last`. Single in-flight run per process (keep the
   current `_run_task` model in `web/server.py`).

### 3.4 `core/reporter.py` + `core/checkpoint.py` (extend)

- Add an optional `workflow` field to agent metric records, and to `stage`/`gate`/`done`
  events. Set via a `reporter.workflow_context(id)` (a `contextvar`) that `run_agent` reads,
  so each agent row knows its lane without threading a parameter through every call site.
- No behavioural change when unused; standalone runs and existing tests unaffected.
- `checkpoint.py` boundary gates additionally carry `workflow` so the UI can render the gate
  bar in the correct lane.

### 3.5 `embroidery/web/` (generalize, no new per-workflow code)

- `GET /workflows` (new) → the registry as JSON: each spec's `id`, `label`, `stages`
  (name + agents), `inputs`, `outputs`, `fixtures`, `config_schema`. Drives lanes + Test panel.
- `POST /start` (extend) → `{target: "<workflow id>"|"team", start_stage?, stop_stage?,
  brief?, seed_fixtures?: [filenames], config?}`. 409 if a run is in progress.
- `GET /prompts` (generalize) → aggregate `prompt_catalog()` across the registry instead of
  hardcoding research.
- `POST /gate`, `GET /output/{file}`, `GET /report`, `POST /prompts`, `POST /prompts/reset`
  — unchanged.
- `static/index.html` — replace the flat table with **workflow lanes** (layout B): lane per
  registered workflow, header (label · status · aggregate calls/$/elapsed), active lane
  auto-expands to stages → agent rows (grouped by `workflow` tag), sub-agents indented,
  inline gate bars between lanes. Add a **Test/Run panel** (§4) and keep the ⚙ prompts panel.

---

## 4. Test pillar (UI)

A run-config panel on the dashboard:

- **Target:** pick one workflow or "full team".
- **Stage range:** pick `start_stage` / `stop_stage` from the target's declared stages.
- **Seed inputs:** for the chosen start point, the panel lists the workflow's `inputs` that
  are missing from `data/output`, each with a "seed from fixture" toggle that copies
  `fixtures/<file>` → `data/output/<file>` before the run. Lets Copy run off a sample
  `positioning_matrix.json` with no Research run.
- **Dry-run prompt:** render the resolved system prompt(s) for selected agents through
  `prompt_store` and display them. No execution, no tokens.
- **Config:** edit the small `config_schema` subset (per-agent model, search caps) for this run.

`fixtures/` holds one committed sample per data-contract file. (Directory already referenced
in `config.yaml` → `paths.fixtures`.)

---

## 5. Edit pillar

- **Prompts** — existing ⚙ panel + `prompt_store.py`; only change is registry-driven catalog
  aggregation.
- **Per-stage brief** — existing `EDIT` gate decision, now available at every workflow
  boundary and stage gate.
- **Run config** — `config_schema` editable per run via the `/start` body, with a defaults view.
- **Gates as the edit surface** — data-contract block (missing input → seed-fixture offer),
  QA `FAIL` → re-loop, and (later) 3-week restart all appear as gate options in the lane.

---

## 6. Documented-not-built phase: persistence / multi-week controller

Sketched interfaces only; built when Agent 8 (Feedback) and real ad-performance data exist.

```python
@dataclass
class CampaignState:
    week_index: int
    has_winner: bool
    weeks_without_winner: int
    last_brief: dict

class CampaignStore:                 # persisted across runs (data/campaign/state.json)
    def load() -> CampaignState: ...
    def record_week(report) -> CampaignState: ...   # ingests Agent 8 outputs
```

Hook points in `run_team`: consult `CampaignState` before a run (iteration ratio, 3-week
restart → start from Research) and update it after Feedback. Until built, `run_team` is a
single linear pass and these transitions are human-triggered gate options.

---

## 7. Error handling

- Generalize the existing `_guarded_run` wrapper around every `entry_point` (and around
  `run_team`): any exception → `done`/`error` event carrying `workflow`, `stage`, `reason`;
  the lane turns red; the pending-gate registry is cleaned. Never a silent hang.
- Provider-level retries stay in `core/agent_loop.py` (unchanged).
- Headless auto-approve preserved: `EMBROIDERY_YES=1` or no SSE subscriber → gates
  auto-approve (standalone runs and tests never block).

---

## 8. Testing strategy

Unit tests use **stub `WorkflowSpec`s with fake async `entry_point`s** — no live providers,
fully deterministic — covering:

- registry ordering and `get_spec`;
- data-contract gating: blocks a workflow when an `inputs` file is missing, passes when present/seeded;
- `start_stage`/`stop_stage` slicing (skips earlier stages, halts after stop);
- orchestrator QA-FAIL re-loop (bounded);
- fixture seeding copies the correct files into `data/output`;
- gate resolve / auto-approve paths (extend existing checkpoint tests).

Existing tests must stay green: `tests.smoke_test`, the Agent-7 QA gate test, and the
research gate-loop integration test. **No new live-provider tests** (consistent with the
no-stub decision — keeps CI cheap; real agent runs remain manual via the dashboard).

---

## 9. Build phasing

| # | Step | Buildable |
|---|---|---|
| 1 | **Harness core** — `core/workflow.py` (Spec/Stage/registry); retrofit research to register + accept `start_stage`/`stop_stage`; add `workflow` tag to reporter/checkpoint. | now |
| 2 | **Web generic** — `GET /workflows`; rebuild `static/index.html` as workflow lanes (B); registry-driven `/prompts`. | now |
| 3 | **Test panel** — stage select + fixture seeding + dry-run prompt; commit `fixtures/` samples for research outputs; proven on research. | now |
| 4 | **Orchestrator** — `core/orchestrator.py` (`run_team`, data-contract gating, boundary gates, QA-FAIL re-loop); **wire existing Agent 7 (QA) as a second registered workflow** to prove the harness with two workflows. | now |
| 5 | **Copy / Feedback** — register `WorkflowSpec`s as those agents are built. | later |
| 6 | **Config-edit polish + persistence-phase interfaces** (`CampaignStore`). | later |

Build-now slice = steps 1–4: the harness, research retrofitted onto it, the Test panel, and
the Orchestrator proven on research **and** the already-existing QA agent. Steps 5–6 plug into
the same registry over time with zero web/orchestrator changes.

---

## 10. Documentation impact (per repo README rule)

On implementation, update: `embroidery/core/README.md` (new `workflow.py`, `orchestrator.py`),
`embroidery/web/README.md` (new `/workflows` endpoint, lanes, Test panel — flip the
design-requirements checkboxes as they ship), `embroidery/agents/README.md` (the
register-a-spec contract), and `CLAUDE.md` (architecture diagram + data-contract gating now
enforced by the orchestrator). Keep each workflow chart in sync.
