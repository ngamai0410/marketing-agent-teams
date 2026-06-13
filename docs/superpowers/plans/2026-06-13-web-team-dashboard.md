# Whole-Team Web Dashboard — Implementation Plan (Phases 1–4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generalize `embroidery/web/` from the research-only dashboard it is today into a registry-driven control surface that can **monitor / test / edit** every workflow of the agent team, proven on Research + the existing QA agent.

**Architecture:** A declarative `WorkflowSpec` registry (`core/workflow.py`) is the single source of truth. A generic `core/orchestrator.py` walks it (enforcing data-contract input gating + boundary gates); the web layer renders **workflow lanes** and a **Test/Run panel** from `GET /workflows`. The reporter/checkpoint gain a `workflow` tag so agent rows group into lanes. Each workflow's pipeline registers a spec + accepts `start_stage`/`stop_stage`; adding a workflow never touches the web or orchestrator code.

**Tech Stack:** Python 3.11 (`embroidery` package), FastAPI + uvicorn + SSE, vanilla HTML/JS (`web/static/index.html`). Run everything from `embroidery/` as modules. Tests are standalone modules in the house style — a `main()` that prints `✓/✗` checks and returns an exit code, run via `venv/bin/python -m tests.<name>` (NOT pytest). Use `venv/bin/python` for every command.

**Spec:** `docs/superpowers/specs/2026-06-13-web-team-dashboard-design.md`. Branch: `web-team-dashboard`.

---

## File Structure

**New files**
- `embroidery/embroidery/core/workflow.py` — `Stage`, `WorkflowSpec`, registry (`register`/`get_registry`/`get_spec`/`clear_registry`), and `load_workflows()` (canonical-order lazy imports).
- `embroidery/embroidery/core/orchestrator.py` — `run_team()`: registry walk, data-contract input gating, boundary gates, QA-FAIL re-loop, run-level `done`/`aborted`/`blocked` events + `run_report.md`.
- `embroidery/embroidery/agents/qa/pipeline.py` — registers the QA `WorkflowSpec`, `run_qa()` entry point, `prompt_catalog()`.
- `embroidery/tests/test_workflow.py`, `test_reporter_workflow.py`, `test_research_stages.py`, `test_web_workflows.py`, `test_web_test_panel.py`, `test_orchestrator.py`, `test_qa_workflow.py`, `test_start_routing.py`.

**Modified files**
- `core/reporter.py` — `AgentRecord.workflow` field + `workflow_context()` contextmanager (contextvar).
- `core/checkpoint.py` — `workflow` param threaded into the gate event + `open_gates()`.
- `agents/research/pipeline.py` — register a `WorkflowSpec`; `run_market_research(brief, *, start_stage, stop_stage, gate)`; wrap in `workflow_context`; short stage names; stop publishing run-level `done` (orchestrator owns it).
- `agents/qa/qa_reviewer.py` — render `SYSTEM_PROMPT` through `prompt_store` so it's editable.
- `web/server.py` — `load_workflows()` at import; `GET /workflows`; registry-driven `/prompts`; `GET /artifacts`; `POST /prompts/preview`; `/start` routes to `run_team` with `target`/`start_stage`/`stop_stage`/`seed_fixtures`.
- `web/static/index.html` — workflow lanes + rail; Test/Run panel.
- Docs: `core/README.md`, `web/README.md`, `agents/README.md`, `CLAUDE.md`, `development-plan.md`.

---

# Phase 1 — Harness core

### Task 1: `core/workflow.py` — Stage / WorkflowSpec / registry

**Files:**
- Create: `embroidery/embroidery/core/workflow.py`
- Test: `embroidery/tests/test_workflow.py`

- [ ] **Step 1: Write the failing test**

Create `embroidery/tests/test_workflow.py`:

```python
"""
Unit test for the WorkflowSpec registry (core/workflow.py). No providers.

Run: cd embroidery && venv/bin/python -m tests.test_workflow
"""
import sys
from embroidery.core.workflow import (
    Stage, WorkflowSpec, register, get_registry, get_spec, clear_registry,
)

failures: list[str] = []

def check(cond: bool, msg: str):
    print(("✓ " if cond else "✗ ") + msg)
    if not cond:
        failures.append(msg)

async def _noop(brief=None, *, start_stage=None, stop_stage=None, gate=None):
    return {}

def main() -> int:
    clear_registry()

    a = WorkflowSpec(
        id="alpha", label="Alpha",
        stages=[Stage("one", ["agent_x"]), Stage("two", ["agent_y", "agent_z"])],
        entry_point=_noop, outputs=["a.json"],
    )
    b = WorkflowSpec(
        id="beta", label="Beta", stages=[Stage("solo", ["q"])],
        entry_point=_noop, inputs=["a.json"], fixtures=["a.json"],
    )
    register(a)
    register(b)

    reg = get_registry()
    check([s.id for s in reg] == ["alpha", "beta"], "registry preserves registration order")
    check(get_spec("beta").inputs == ["a.json"], "get_spec returns the right spec")
    check(a.stage_names() == ["one", "two"], "stage_names lists stage names in order")
    check(get_spec("alpha").config_schema == {}, "config_schema defaults to empty dict")

    # re-register same id is idempotent (replaces, no duplicate row)
    register(WorkflowSpec(id="alpha", label="Alpha2", stages=[], entry_point=_noop))
    reg2 = get_registry()
    check([s.id for s in reg2] == ["alpha", "beta"], "re-register replaces, no duplicate")
    check(get_spec("alpha").label == "Alpha2", "re-register updates the spec")

    clear_registry()
    check(get_registry() == [], "clear_registry empties the registry")

    if failures:
        print(f"\n✗ test_workflow FAILED ({len(failures)})")
        return 1
    print("\n✓ test_workflow passed")
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it — verify it fails**

Run: `cd embroidery && venv/bin/python -m tests.test_workflow`
Expected: FAIL — `ModuleNotFoundError: No module named 'embroidery.core.workflow'`.

- [ ] **Step 3: Implement `core/workflow.py`**

Create `embroidery/embroidery/core/workflow.py`:

```python
"""
WorkflowSpec registry — the single source of truth for the agent team.

Each campaign workflow (research, copy, qa, feedback) registers ONE WorkflowSpec
describing its shape: its ordered stages (each naming the agents it runs), an
async entry point that supports start/stop-stage slicing, its editable prompt
catalog, and its data-contract inputs/outputs/fixtures. The web layer
(embroidery/web/) and the orchestrator (core/orchestrator.py) are fully generic:
they iterate this registry and gain no per-workflow code. Adding a workflow =
write its pipeline module + call register(...) at import — nothing else.

load_workflows() imports the workflow modules in canonical team order so the
registry is populated deterministically regardless of who triggers it first.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from embroidery.core.logger import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class Stage:
    name: str                 # short stage label, e.g. "sub-agents A/B/C"
    agents: list[str]         # agent_name values this stage runs (maps rows -> lane stage)
    digest: Callable[..., dict] | None = None   # builds this stage's gate-card digest


@dataclass(frozen=True)
class WorkflowSpec:
    id: str                                       # "research", "copy", "qa", "feedback"
    label: str                                    # "Research"
    stages: list[Stage]
    entry_point: Callable[..., Awaitable[Any]]    # async run(brief, *, start_stage, stop_stage, gate)
    prompt_catalog: Callable[[], list[dict]] = lambda: []
    inputs: list[str] = field(default_factory=list)    # data-contract files read (under data/output)
    outputs: list[str] = field(default_factory=list)   # data-contract files written
    fixtures: list[str] = field(default_factory=list)  # committed samples (under fixtures/) that seed inputs
    config_schema: dict = field(default_factory=dict)

    def stage_names(self) -> list[str]:
        return [s.name for s in self.stages]


_REGISTRY: dict[str, WorkflowSpec] = {}


def register(spec: WorkflowSpec) -> None:
    """Add or replace a spec by id. Idempotent — safe on module re-import."""
    _REGISTRY[spec.id] = spec
    log.debug("workflow registered id=%s stages=%d", spec.id, len(spec.stages))


def get_registry() -> list[WorkflowSpec]:
    """All specs in registration (canonical team) order."""
    return list(_REGISTRY.values())


def get_spec(spec_id: str) -> WorkflowSpec:
    return _REGISTRY[spec_id]


def clear_registry() -> None:
    """Test helper — drop all registered specs."""
    _REGISTRY.clear()


def load_workflows() -> list[WorkflowSpec]:
    """Import every workflow module in canonical order so each registers itself.

    Lazy + tolerant: a workflow whose agents aren't built yet simply isn't
    imported. The web layer / orchestrator call this once at startup.
    """
    import importlib
    for module in (
        "embroidery.agents.research.pipeline",
        "embroidery.agents.qa.pipeline",
    ):
        try:
            importlib.import_module(module)
        except ImportError as exc:           # workflow not built yet — skip
            log.debug("workflow module not loadable (%s): %s", module, exc)
    return get_registry()
```

- [ ] **Step 4: Run it — verify it passes**

Run: `cd embroidery && venv/bin/python -m tests.test_workflow`
Expected: PASS — all checks `✓`.

- [ ] **Step 5: Commit**

```bash
git add embroidery/embroidery/core/workflow.py embroidery/tests/test_workflow.py
git commit -m "Add WorkflowSpec registry (core/workflow.py)"
```

---

### Task 2: `reporter` + `checkpoint` workflow tagging

**Files:**
- Modify: `embroidery/embroidery/core/reporter.py`
- Modify: `embroidery/embroidery/core/checkpoint.py`
- Test: `embroidery/tests/test_reporter_workflow.py`

- [ ] **Step 1: Write the failing test**

Create `embroidery/tests/test_reporter_workflow.py`:

```python
"""
The reporter tags each agent row with the active workflow (set via a contextvar),
and checkpoint() carries the workflow on its gate event. No providers.

Run: cd embroidery && venv/bin/python -m tests.test_reporter_workflow
"""
import asyncio
import sys

from embroidery.core.reporter import get_reporter
from embroidery.core.checkpoint import checkpoint, resolve_gate, open_gates, Decision

failures: list[str] = []

def check(cond, msg):
    print(("✓ " if cond else "✗ ") + msg)
    if not cond:
        failures.append(msg)

def test_workflow_tag():
    r = get_reporter()
    r.reset()
    r.agent_start("loose_agent", "m", 100)            # no context -> ""
    with r.workflow_context("research"):
        r.agent_start("audience_researcher", "m", 100)
    rows = {row["name"]: row for row in r.snapshot()["rows"]}
    check(rows["audience_researcher"]["workflow"] == "research", "agent tagged with active workflow")
    check(rows["loose_agent"]["workflow"] == "", "untagged agent has empty workflow")

def test_gate_carries_workflow():
    async def run():
        r = get_reporter()
        r.reset()
        q = r.subscribe()                              # makes a subscriber so checkpoint blocks
        task = asyncio.create_task(
            checkpoint("solo", {"k": 1}, workflow="qa", request={"b": 2})
        )
        await asyncio.sleep(0.05)
        gates = open_gates()
        ev = await q.get()                             # the published gate event
        check(ev["type"] == "gate" and ev["workflow"] == "qa", "gate event carries workflow")
        check(gates and gates[0]["workflow"] == "qa", "open_gates carries workflow")
        resolve_gate(ev["gate_id"], "approve")
        res = await task
        check(res.decision is Decision.APPROVE, "gate resolves to APPROVE")
        r.unsubscribe(q)
    asyncio.run(run())

def main() -> int:
    test_workflow_tag()
    test_gate_carries_workflow()
    if failures:
        print(f"\n✗ test_reporter_workflow FAILED ({len(failures)})")
        return 1
    print("\n✓ test_reporter_workflow passed")
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it — verify it fails**

Run: `cd embroidery && venv/bin/python -m tests.test_reporter_workflow`
Expected: FAIL — `AttributeError: 'RunReporter' object has no attribute 'workflow_context'` (and the row has no `workflow` key).

- [ ] **Step 3: Implement reporter changes**

In `embroidery/embroidery/core/reporter.py`:

Add imports at the top (after `import time`):

```python
import contextlib
import contextvars
```

Add the contextvar right above `@dataclass class AgentRecord`:

```python
# The workflow whose agents are currently running — set via
# RunReporter.workflow_context() so each AgentRecord knows its lane without
# threading a parameter through every run_agent() call site.
_current_workflow: contextvars.ContextVar[str] = contextvars.ContextVar("workflow", default="")
```

Add a `workflow` field to `AgentRecord` (right after `name: str`):

```python
    name: str
    workflow: str = ""
    model: str = ""
```

Add `"workflow": self.workflow,` to `as_row()` (first key, before `"name"`):

```python
    def as_row(self) -> dict:
        return {
            "workflow": self.workflow,
            "name": self.name,
            "model": self.model,
            ...
```

In `agent_start`, set the workflow on both branches:

```python
    def agent_start(self, name: str, model: str, max_tokens: int) -> None:
        wf = _current_workflow.get()
        rec = self._agents.get(name)
        if rec is None:
            rec = AgentRecord(name=name, workflow=wf, model=model)
            self._agents[name] = rec
        else:  # re-run of the same agent within a run — reset its counters
            rec.workflow = wf
            rec.model = model
            rec.status = "running"
            rec.calls = rec.in_tokens = rec.out_tokens = rec.searches = 0
            rec.t_start = time.monotonic()
            rec.t_end = None
        self._publish_agents()
```

Add the context manager as a method on `RunReporter` (e.g. just below `reset`):

```python
    @contextlib.contextmanager
    def workflow_context(self, workflow_id: str):
        """Within this block, agent_start() tags rows with workflow_id."""
        token = _current_workflow.set(workflow_id)
        try:
            yield
        finally:
            _current_workflow.reset(token)
```

- [ ] **Step 4: Implement checkpoint changes**

In `embroidery/embroidery/core/checkpoint.py`:

Add `workflow: str` to `_PendingGate` (after `stage`):

```python
@dataclass
class _PendingGate:
    gate_id: str
    stage: str
    workflow: str
    digest: dict
    request: dict | None
    future: asyncio.Future
```

Update `open_gates()` to include it:

```python
def open_gates() -> list[dict]:
    return [
        {"type": "gate", "gate_id": g.gate_id, "stage": g.stage,
         "workflow": g.workflow, "digest": g.digest, "request": g.request}
        for g in _pending.values()
    ]
```

Change the `checkpoint` signature and body to thread `workflow`:

```python
async def checkpoint(stage: str, digest: dict, *, workflow: str = "",
                     request: dict | None = None) -> CheckpointResult:
    """Pause the pipeline for human QC. See module docstring."""
    global _counter

    if _auto_approve():
        log.info("checkpoint=%s auto-approved (no dashboard / EMBROIDERY_YES)", stage)
        return CheckpointResult(Decision.APPROVE, request)

    _counter += 1
    gate_id = f"gate-{_counter}"
    loop = asyncio.get_running_loop()
    future: asyncio.Future = loop.create_future()
    _pending[gate_id] = _PendingGate(gate_id, stage, workflow, digest, request, future)

    log.info("checkpoint=%s gate_id=%s workflow=%s awaiting user decision", stage, gate_id, workflow)
    get_reporter().publish({
        "type": "gate", "gate_id": gate_id, "stage": stage,
        "workflow": workflow, "digest": digest, "request": request,
    })

    try:
        result = await future
    finally:
        _pending.pop(gate_id, None)

    log.info("checkpoint=%s gate_id=%s decision=%s", stage, gate_id, result.decision.value)
    get_reporter().publish({"type": "gate_closed", "gate_id": gate_id})
    return result
```

- [ ] **Step 5: Run it — verify it passes**

Run: `cd embroidery && venv/bin/python -m tests.test_reporter_workflow`
Expected: PASS.

- [ ] **Step 6: Regression — existing tests still green**

Run: `cd embroidery && venv/bin/python -m tests.smoke_test`
Expected: PASS (the new `workflow` row key is additive).

- [ ] **Step 7: Commit**

```bash
git add embroidery/embroidery/core/reporter.py embroidery/embroidery/core/checkpoint.py embroidery/tests/test_reporter_workflow.py
git commit -m "Tag reporter rows + gates with the active workflow"
```

---

### Task 3: Retrofit research pipeline onto the registry

**Files:**
- Modify: `embroidery/embroidery/agents/research/pipeline.py`
- Test: `embroidery/tests/test_research_stages.py`

- [ ] **Step 1: Write the failing test**

Create `embroidery/tests/test_research_stages.py`:

```python
"""
The research pipeline registers a WorkflowSpec and honours start_stage/stop_stage
without calling any provider (we stub the sub-agents + synthesizer). No tokens.

Run: cd embroidery && venv/bin/python -m tests.test_research_stages
"""
import asyncio
import sys

import embroidery.agents.research.pipeline as P
from embroidery.core.workflow import get_spec
from embroidery.core.checkpoint import Decision, CheckpointResult

failures: list[str] = []
calls: list[str] = []

def check(cond, msg):
    print(("✓ " if cond else "✗ ") + msg)
    if not cond:
        failures.append(msg)

async def _fake_subagent(key, brief, reset_searches=False):
    calls.append(f"sub_{key}")
    return {"desires": [], "problems": [], "hooks": [], "objections": []}

async def _fake_synth(a, b, c, brief):
    calls.append("synth")
    return ({"desires": [], "problems": [], "hooks": []}, "# narrative")

async def _auto_gate(stage, digest, *, workflow="", request=None):
    return CheckpointResult(Decision.APPROVE, request)

def main() -> int:
    # Spec registered at import
    spec = get_spec("research")
    check(spec.label == "Research", "research spec registered with label")
    check(spec.stage_names() == ["sub-agents A/B/C", "synthesis"], "research stage names")
    check(spec.outputs == ["market_research_report.json", "brand_intelligence_report.md"],
          "research declares its data-contract outputs")

    # Monkeypatch providers + gate
    P.run_subagent = _fake_subagent
    P.run_synthesizer = _fake_synth

    # start at synthesis -> skip A/B/C, load static (stub the static loader + synth: no files, no tokens)
    P.synth_module_static = lambda: ({}, {}, {})
    calls.clear()
    asyncio.run(P.run_market_research(start_stage="synthesis", gate=_auto_gate))
    check("synth" in calls and not any(c.startswith("sub_") for c in calls),
          "start_stage=synthesis skips sub-agents")

    # stop at sub-agents -> run A/B/C, no synth
    calls.clear()
    asyncio.run(P.run_market_research(stop_stage="sub-agents A/B/C", gate=_auto_gate))
    check(any(c.startswith("sub_") for c in calls) and "synth" not in calls,
          "stop_stage=sub-agents A/B/C skips synthesis")

    if failures:
        print(f"\n✗ test_research_stages FAILED ({len(failures)})")
        return 1
    print("\n✓ test_research_stages passed")
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it — verify it fails**

Run: `cd embroidery && venv/bin/python -m tests.test_research_stages`
Expected: FAIL — `KeyError: 'research'` (no spec yet) / `run_market_research` lacks `start_stage`.

- [ ] **Step 3: Rewrite `agents/research/pipeline.py`**

Replace the body of `run_market_research` and add the spec registration. The new file (keep the module docstring and the two `_*_digest` helpers as they are; replace from `async def run_market_research` through the end):

```python
# stage names (also the WorkflowSpec.stages names)
STAGE_SUBAGENTS = "sub-agents A/B/C"
STAGE_SYNTH = "synthesis"
_STAGES = [STAGE_SUBAGENTS, STAGE_SYNTH]


def _active(start_stage: str | None, stop_stage: str | None) -> set[str]:
    si = _STAGES.index(start_stage) if start_stage else 0
    ei = _STAGES.index(stop_stage) if stop_stage else len(_STAGES) - 1
    return {s for i, s in enumerate(_STAGES) if si <= i <= ei}


async def run_market_research(
    brief: dict | None = None,
    *,
    start_stage: str | None = None,
    stop_stage: str | None = None,
    gate=checkpoint,
) -> dict[str, Path] | None:
    """Run the Agent 1 research workflow with QC gates between stages.

    start_stage/stop_stage slice the workflow for the Test pillar. Skipped
    upstream stages expect their outputs already on disk (a prior run or a
    seeded fixture). Returns the output paths, or None if the user quit.
    """
    brief = dict(brief) if brief else dict(SHOP_BRIEF)
    active = _active(start_stage, stop_stage)
    reporter = get_reporter()

    research_a = research_b = research_c = None
    with reporter.workflow_context("research"):
        # ---- Stage: sub-agents A/B/C (gated) ----
        if STAGE_SUBAGENTS in active:
            while True:
                reset_search_count()
                reporter.publish({"type": "stage", "workflow": "research", "stage": STAGE_SUBAGENTS})
                log.info("research: dispatching sub-agents A/B/C")
                research_a, research_b, research_c = await asyncio.gather(
                    run_subagent("a", brief, reset_searches=False),
                    run_subagent("b", brief, reset_searches=False),
                    run_subagent("c", brief, reset_searches=False),
                )
                res = await gate(STAGE_SUBAGENTS, _research_digest(research_a, research_b, research_c),
                                 workflow="research", request=brief)
                if res.decision is Decision.QUIT:
                    return None
                if res.decision is Decision.EDIT:
                    brief = res.request or brief
                    continue
                break
        else:
            research_a, research_b, research_c = synth_module_static()

        if STAGE_SYNTH not in active:
            log.info("research: stopping after %s (stop_stage)", STAGE_SUBAGENTS)
            return None

        # ---- Stage: synthesis (gated; Edit re-runs A/B/C if that stage is active) ----
        while True:
            reporter.publish({"type": "stage", "workflow": "research", "stage": STAGE_SYNTH})
            report, markdown = await run_synthesizer(research_a, research_b, research_c, brief)
            res = await gate(STAGE_SYNTH, _synth_digest(report, markdown),
                             workflow="research", request=brief)
            if res.decision is Decision.QUIT:
                return None
            if res.decision is Decision.EDIT and STAGE_SUBAGENTS in active:
                brief = res.request or brief
                reset_search_count()
                research_a, research_b, research_c = await asyncio.gather(
                    run_subagent("a", brief, reset_searches=False),
                    run_subagent("b", brief, reset_searches=False),
                    run_subagent("c", brief, reset_searches=False),
                )
                continue
            if res.decision is Decision.EDIT:
                brief = res.request or brief
                continue
            break

    # ---- Persist this workflow's data-contract outputs ----
    out = Path(settings.paths.output)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "market_research_report.json"
    md_path = out / "brand_intelligence_report.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")
    BrandAI(SHOP_SLUG).save_research(report, markdown)
    log.info("research workflow done json=%s md=%s", json_path, md_path)
    return {"market_research_report": json_path, "brand_intelligence_report": md_path}


def synth_module_static() -> tuple[dict, dict, dict]:
    """Load the saved A/B/C outputs from output/ (seeded fixture or prior run)."""
    from embroidery.agents.research.synthesizer import _load_static_research
    return _load_static_research()


def _prompt_catalog() -> list[dict]:
    from embroidery.agents.research import subagents, synthesizer
    return subagents.prompt_catalog() + synthesizer.prompt_catalog()


# Register this workflow in the team registry (import-time, idempotent).
from embroidery.core.workflow import Stage, WorkflowSpec, register   # noqa: E402

register(WorkflowSpec(
    id="research",
    label="Research",
    stages=[
        Stage(STAGE_SUBAGENTS, ["audience_researcher", "competitor_analyst", "social_media_analyst"]),
        Stage(STAGE_SYNTH, ["synthesizer_json", "synthesizer_md"]),
    ],
    entry_point=run_market_research,
    prompt_catalog=_prompt_catalog,
    inputs=[],
    outputs=["market_research_report.json", "brand_intelligence_report.md"],
    fixtures=[],
    config_schema={
        "audience_researcher": {"model": settings.agents.audience_researcher.model},
        "synthesizer": {"model": settings.agents.synthesizer.model},
    },
))
```

Then update the imports at the top of the file: ensure `from embroidery.core.checkpoint import Decision, checkpoint` is present (it is), and **delete** the now-unused `reporter.publish({"type": "done"...})` / `_abort` calls — replace the old `_abort` helper and the `__main__` block with:

```python
if __name__ == "__main__":
    if "--yes" in sys.argv:
        os.environ["EMBROIDERY_YES"] = "1"
    paths = asyncio.run(run_market_research())
    if not paths:
        print("Pipeline stopped (quit or stop-stage).")
    else:
        for name, path in paths.items():
            size = path.stat().st_size if path.exists() else 0
            print(f"{name}: {path} ({size:,} bytes)")
```

(Run-level `done`/`aborted` events and `run_report.md` now belong to `run_team` — Task 8. Standalone CLI runs print instead.)

- [ ] **Step 4: Run it — verify it passes**

Run: `cd embroidery && venv/bin/python -m tests.test_research_stages`
Expected: PASS.

- [ ] **Step 5: Regression**

Run: `cd embroidery && venv/bin/python -m tests.smoke_test`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add embroidery/embroidery/agents/research/pipeline.py embroidery/tests/test_research_stages.py
git commit -m "Retrofit research pipeline onto WorkflowSpec + start/stop stages"
```

---

# Phase 2 — Web generic

### Task 4: `load_workflows` at startup + `GET /workflows` + registry-driven `/prompts`

**Files:**
- Modify: `embroidery/embroidery/web/server.py`
- Test: `embroidery/tests/test_web_workflows.py`

- [ ] **Step 1: Write the failing test**

Create `embroidery/tests/test_web_workflows.py`:

```python
"""
The web layer exposes the registry at /workflows and aggregates /prompts across
all registered workflows. We call the async route functions directly (no httpx).

Run: cd embroidery && venv/bin/python -m tests.test_web_workflows
"""
import asyncio
import sys

from embroidery.web import server

failures: list[str] = []

def check(cond, msg):
    print(("✓ " if cond else "✗ ") + msg)
    if not cond:
        failures.append(msg)

def main() -> int:
    wf = asyncio.run(server.list_workflows())
    ids = [w["id"] for w in wf["workflows"]]
    check("research" in ids, "/workflows lists research")
    research = next(w for w in wf["workflows"] if w["id"] == "research")
    check(research["stages"][0]["name"] == "sub-agents A/B/C", "/workflows carries stage names")
    check(research["outputs"] == ["market_research_report.json", "brand_intelligence_report.md"],
          "/workflows carries data-contract outputs")

    pr = asyncio.run(server.list_prompts())
    pids = {p["id"] for p in pr["prompts"]}
    check("research.audience_researcher" in pids, "/prompts aggregates research prompts from registry")

    if failures:
        print(f"\n✗ test_web_workflows FAILED ({len(failures)})")
        return 1
    print("\n✓ test_web_workflows passed")
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it — verify it fails**

Run: `cd embroidery && venv/bin/python -m tests.test_web_workflows`
Expected: FAIL — `AttributeError: module 'embroidery.web.server' has no attribute 'list_workflows'`.

- [ ] **Step 3: Implement server changes**

In `embroidery/embroidery/web/server.py`:

Replace the import block + `_prompt_catalog` helper with registry-driven versions. After the existing imports add:

```python
from embroidery.core.workflow import get_registry, get_spec, load_workflows

# Populate the workflow registry once at import (lazy per-module imports inside).
load_workflows()


def _prompt_catalog() -> list[dict]:
    items: list[dict] = []
    for spec in get_registry():
        items.extend(spec.prompt_catalog())
    return items
```

Delete the old `_prompt_catalog` that hardcoded `from embroidery.agents.research import subagents, synthesizer`.

Add the `/workflows` route (near the page route):

```python
@app.get("/workflows")
async def list_workflows():
    return {"workflows": [
        {
            "id": s.id,
            "label": s.label,
            "stages": [{"name": st.name, "agents": st.agents} for st in s.stages],
            "inputs": s.inputs,
            "outputs": s.outputs,
            "fixtures": s.fixtures,
            "config_schema": s.config_schema,
        }
        for s in get_registry()
    ]}
```

(`list_prompts` already exists and now uses the registry-driven `_prompt_catalog` — no change to its body.)

- [ ] **Step 4: Run it — verify it passes**

Run: `cd embroidery && venv/bin/python -m tests.test_web_workflows`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add embroidery/embroidery/web/server.py embroidery/tests/test_web_workflows.py
git commit -m "Web: load registry at startup, add GET /workflows, registry-driven /prompts"
```

---

### Task 5: Workflow lanes + rail in the dashboard

**Files:**
- Modify: `embroidery/embroidery/web/static/index.html`

This is a static asset — verified by launching the server and observing, not unit-tested.

- [ ] **Step 1: Add lane + rail CSS**

In the `<style>` block of `index.html`, append before the closing `</style>`:

```css
  /* workflow rail + lanes */
  .rail { display:flex; align-items:center; gap:6px; flex-wrap:wrap; margin:0 0 16px; }
  .rail .wf { font-size:12px; padding:4px 10px; border:1px solid var(--line); border-radius:6px; color:var(--muted); }
  .rail .wf.active { border-color:var(--accent); color:var(--txt); font-weight:600; }
  .rail .wf.done { border-color:var(--ok); color:var(--ok); }
  .rail .wf.error { border-color:var(--bad); color:var(--bad); }
  .rail .sep { color:var(--line); }
  .lane { border:1px solid var(--line); border-radius:10px; margin-bottom:10px; background:var(--panel); overflow:hidden; }
  .lane > .lane-head { display:flex; gap:12px; align-items:center; padding:10px 14px; cursor:pointer; }
  .lane.active > .lane-head { background:rgba(91,140,255,.08); }
  .lane .lane-title { font-weight:600; }
  .lane .lane-meta { color:var(--muted); font-size:12px; margin-left:auto; }
  .lane table { border:none; border-radius:0; margin:0; }
  .lane .sub td:first-child { padding-left:30px; color:var(--muted); }
  .gatebar { padding:8px 14px; font-size:12px; color:var(--run); border-top:1px solid var(--line); }
  .gatebar.passed { color:var(--ok); }
```

- [ ] **Step 2: Replace the single `<table>` with a lanes container**

In the `<main>`, replace the whole `<table>…</table>` block (lines with `<thead>`/`<tbody id="rows">`/`<tfoot id="totals">`) with:

```html
  <div class="rail" id="rail"></div>
  <div id="lanes"><p class="stage" style="text-align:center">No agents running yet.</p></div>
  <p class="stage" id="grandtotal" style="text-align:right"></p>
```

- [ ] **Step 3: Add lane rendering JS**

In `<script>`, add a module-level cache of workflow metadata and replace `renderAgents`. After `let running = false;` add:

```javascript
let workflowsMeta = [];     // [{id,label,stages:[{name,agents}], ...}]
let activeStage = {};       // workflow id -> active stage name
let openGatesByWf = {};     // workflow id -> {stage, passed}

async function loadWorkflows() {
  const res = await fetch("/workflows");
  workflowsMeta = (await res.json()).workflows;
  renderRail();
}

function renderRail() {
  const rail = $("rail");
  rail.innerHTML = workflowsMeta.map((w, i) =>
    `${i ? '<span class="sep">→</span>' : ''}<span class="wf" data-wf="${w.id}">${esc(w.label)}</span>`
  ).join("");
}
```

Replace the existing `renderAgents(ev)` with a lane-grouping version:

```javascript
function renderAgents(ev) {
  const rows = ev.rows || [];
  const byWf = {};
  rows.forEach(r => { (byWf[r.workflow || ""] = byWf[r.workflow || ""] || []).push(r); });

  const lanes = $("lanes");
  if (!rows.length) { lanes.innerHTML = `<p class="stage" style="text-align:center">No agents running yet.</p>`; return; }

  // one lane per registered workflow that has rows (plus an "other" lane for untagged)
  const order = workflowsMeta.map(w => w.id).concat(Object.keys(byWf).filter(k => !workflowsMeta.find(w => w.id === k)));
  lanes.innerHTML = order.filter(id => byWf[id]).map(id => {
    const meta = workflowsMeta.find(w => w.id === id);
    const wfRows = byWf[id];
    const calls = wfRows.reduce((a, r) => a + r.calls, 0);
    const cost = wfRows.reduce((a, r) => a + (r.cost_usd || 0), 0);
    const anyRunning = wfRows.some(r => r.status === "running");
    const gate = openGatesByWf[id];
    const gbar = gate
      ? `<div class="gatebar ${gate.passed ? 'passed' : ''}">${gate.passed ? '▣ ' + esc(gate.stage) + ' — approved' : '▢ awaiting QC: ' + esc(gate.stage)}</div>`
      : "";
    return `
      <div class="lane ${anyRunning ? 'active' : ''}">
        <div class="lane-head">
          <span class="lane-title">${esc(meta ? meta.label : id || 'other')}</span>
          ${activeStage[id] ? `<span class="pstage">${esc(activeStage[id])}</span>` : ""}
          <span class="lane-meta">${calls} calls · ${money(cost)}</span>
        </div>
        <table><tbody>
          ${wfRows.map(r => `
            <tr class="${r.name.includes('synthesizer') || meta && meta.stages[0] && meta.stages[0].agents.includes(r.name) ? '' : 'sub'}">
              <td>${esc(r.name)}</td>
              <td class="mono" style="color:var(--muted)">${r.model || ""}</td>
              <td><span class="badge ${r.status}">${r.status}</span></td>
              <td style="text-align:right">${r.calls}</td>
              <td class="mono" style="text-align:right">${num(r.in_tokens)}/${num(r.out_tokens)}</td>
              <td>${r.searches}</td>
              <td class="mono" style="text-align:right">${money(r.cost_usd)}</td>
              <td class="mono" style="text-align:right">${r.elapsed_s}s</td>
            </tr>`).join("")}
        </tbody></table>
        ${gbar}
      </div>`;
  }).join("");

  const t = ev.totals || {};
  $("grandtotal").textContent =
    `Total: ${t.calls ?? 0} calls · ${num(t.in_tokens)} in / ${num(t.out_tokens)} out · ${money(t.cost_usd)} · ${(t.elapsed_s ?? 0)}s`;
}
```

Update `setStage` to also drive the rail + active-stage, and `handle` to track gates per workflow:

```javascript
function setStage(text, bold, wf) {
  $("stage").innerHTML = bold ? `Running: <b>${esc(text)}</b>` : esc(text);
  if (wf) {
    activeStage[wf] = text;
    document.querySelectorAll(".rail .wf").forEach(el => {
      if (el.dataset.wf === wf) el.classList.add("active");
    });
  }
}
```

In `handle`, update the `stage` and `gate`/`gate_closed`/`done` cases:

```javascript
function handle(ev) {
  switch (ev.type) {
    case "agents": renderAgents(ev); break;
    case "stage": setStage(ev.stage, true, ev.workflow); break;
    case "gate":
      if (ev.workflow) openGatesByWf[ev.workflow] = { stage: ev.stage, passed: false };
      showGate(ev);
      break;
    case "gate_closed":
      if (currentGate && currentGate.gate_id === ev.gate_id) hideGate();
      break;
    case "done":
      // mark all rail workflows done/error
      document.querySelectorAll(".rail .wf").forEach(el => {
        el.classList.remove("active");
        el.classList.add(ev.status === "complete" ? "done" : ev.status === "error" || ev.status === "blocked" ? "error" : "");
      });
      Object.keys(openGatesByWf).forEach(k => openGatesByWf[k].passed = true);
      showDone(ev);
      break;
  }
}
```

(`showGate`, `sendGate`, gate buttons stay as-is.) Add `loadWorkflows();` at the very bottom of the script next to the existing `loadPrompts();`.

- [ ] **Step 4: Manual verification**

Run: `cd embroidery && EMBROIDERY_YES= venv/bin/python -m embroidery.web --no-browser`
Then open `http://127.0.0.1:8765`. Confirm: the rail shows **Research → QA**; pressing **Start campaign** (it still posts `{}`) streams agent rows grouped under the **Research** lane; the gate modal still opens and Approve/Edit/Quit still work. Ctrl-C to stop.

- [ ] **Step 5: Commit**

```bash
git add embroidery/embroidery/web/static/index.html
git commit -m "Dashboard: workflow lanes + rail, grouped agent rows"
```

---

# Phase 3 — Test panel

### Task 6: `GET /artifacts`, `POST /prompts/preview`, `/start` fixture seeding

**Files:**
- Modify: `embroidery/embroidery/web/server.py`
- Test: `embroidery/tests/test_web_test_panel.py`

- [ ] **Step 1: Write the failing test**

Create `embroidery/tests/test_web_test_panel.py`:

```python
"""
Test-pillar endpoints: /artifacts lists present output files; /prompts/preview
renders a template with sample context; seed-fixture copies a fixture into output.

Run: cd embroidery && venv/bin/python -m tests.test_web_test_panel
"""
import asyncio
import sys
from pathlib import Path

from embroidery.web import server
from embroidery.core.config import settings

failures: list[str] = []

def check(cond, msg):
    print(("✓ " if cond else "✗ ") + msg)
    if not cond:
        failures.append(msg)

def main() -> int:
    out = Path(settings.paths.output)
    out.mkdir(parents=True, exist_ok=True)
    (out / "_probe.json").write_text("{}", encoding="utf-8")

    arts = asyncio.run(server.list_artifacts())
    check("_probe.json" in arts["files"], "/artifacts lists present output files")

    pv = asyncio.run(server.preview_prompt(server.PreviewBody(
        id="research.audience_researcher",
        text="Shop is ${shop_context} end")))
    check("SHOP CONTEXT" in pv["rendered"], "/prompts/preview substitutes sample shop_context")

    # seed a known fixture into output and confirm the helper copies it
    seeded = server._seed_fixtures(["positioning_matrix.json"])
    check((out / "positioning_matrix.json").exists(), "_seed_fixtures copies fixture into output")
    check(seeded == ["positioning_matrix.json"], "_seed_fixtures returns the copied names")

    if failures:
        print(f"\n✗ test_web_test_panel FAILED ({len(failures)})")
        return 1
    print("\n✓ test_web_test_panel passed")
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it — verify it fails**

Run: `cd embroidery && venv/bin/python -m tests.test_web_test_panel`
Expected: FAIL — `list_artifacts` / `preview_prompt` / `_seed_fixtures` not defined.

- [ ] **Step 3: Implement the endpoints + helper**

In `embroidery/embroidery/web/server.py`:

Add imports near the top:

```python
import shutil
import string
from embroidery.agents.research.subagents import SHOP_BRIEF, shop_context
```

Add the artifact listing route:

```python
@app.get("/artifacts")
async def list_artifacts():
    out = Path(settings.paths.output)
    files = sorted(p.name for p in out.glob("*") if p.suffix in (".json", ".md")) if out.exists() else []
    return {"files": files}
```

Add the prompt-preview route (renders with sample context so the user can dry-run a prompt edit without spending tokens):

```python
class PreviewBody(BaseModel):
    id: str
    text: str | None = None     # if omitted, preview the currently-saved prompt

_SAMPLE_CTX = None

def _sample_ctx() -> dict:
    global _SAMPLE_CTX
    if _SAMPLE_CTX is None:
        _SAMPLE_CTX = {
            "shop_context": shop_context(SHOP_BRIEF),
            "shared_rules": "(shared research rules)",
            "research_date": "2026-06-13",
            "shop_name": SHOP_BRIEF["name"],
        }
    return _SAMPLE_CTX

@app.post("/prompts/preview")
async def preview_prompt(body: PreviewBody):
    item = next((p for p in _prompt_catalog() if p["id"] == body.id), None)
    if item is None:
        raise HTTPException(404, f"unknown prompt {body.id}")
    text = body.text if body.text is not None else item["text"]
    rendered = string.Template(text).safe_substitute(**_sample_ctx())
    return {"id": body.id, "rendered": rendered}
```

Add the fixture-seeding helper (used by `/start` in Task 10, unit-tested here):

```python
def _seed_fixtures(files: list[str]) -> list[str]:
    """Copy committed fixtures/<file> -> data/output/<file>. Returns copied names."""
    src_dir = Path(settings.paths.fixtures)
    out = Path(settings.paths.output)
    out.mkdir(parents=True, exist_ok=True)
    copied = []
    for name in files:
        if "/" in name or ".." in name:
            raise HTTPException(400, f"invalid fixture name {name}")
        src = src_dir / name
        if not src.exists():
            raise HTTPException(404, f"no fixture {name}")
        shutil.copy(src, out / name)
        copied.append(name)
    log.info("seeded fixtures into output: %s", copied)
    return copied
```

- [ ] **Step 4: Run it — verify it passes**

Run: `cd embroidery && venv/bin/python -m tests.test_web_test_panel`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add embroidery/embroidery/web/server.py embroidery/tests/test_web_test_panel.py
git commit -m "Web: /artifacts, /prompts/preview, fixture-seeding helper (Test pillar)"
```

---

### Task 7: Test/Run panel UI

**Files:**
- Modify: `embroidery/embroidery/web/static/index.html`

Static asset — verified by launch + observe.

- [ ] **Step 1: Add the panel markup**

In `<main>`, right after the `#promptsPanel` `</details>`, add:

```html
  <details id="testPanel">
    <summary>🧪 Test / run — pick a workflow, stage range, seed fixtures</summary>
    <div class="promptlist">
      <div class="prow">
        <label class="pstage">Run</label>
        <select id="t-target"></select>
        <label class="pstage">from</label>
        <select id="t-start"></select>
        <label class="pstage">to</label>
        <select id="t-stop"></select>
      </div>
      <div id="t-seed" class="phint"></div>
      <div class="prow">
        <button id="t-dryrun">Dry-run prompts (no tokens)</button>
      </div>
      <pre id="t-preview" class="hide" style="background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:12px;white-space:pre-wrap;max-height:300px;overflow:auto"></pre>
    </div>
  </details>
```

Reuse `#promptsPanel` styling by giving `#testPanel` the same selector — in `<style>` change `details#promptsPanel` rules to `details#promptsPanel, details#testPanel` (4 occurrences: the container, `> summary`, `> summary::before`, `[open] > summary::before`).

- [ ] **Step 2: Populate the panel from `/workflows` + `/artifacts`**

In `<script>`, extend `loadWorkflows()` to populate the selects, and add seed/dry-run handlers:

```javascript
async function loadWorkflows() {
  const res = await fetch("/workflows");
  workflowsMeta = (await res.json()).workflows;
  renderRail();
  const tgt = $("t-target");
  tgt.innerHTML = `<option value="team">Full team</option>` +
    workflowsMeta.map(w => `<option value="${w.id}">${esc(w.label)}</option>`).join("");
  tgt.onchange = refreshTestPanel;
  refreshTestPanel();
}

async function refreshTestPanel() {
  const id = $("t-target").value;
  const meta = workflowsMeta.find(w => w.id === id);
  const stages = meta ? meta.stages.map(s => s.name) : [];
  const opts = stages.map(s => `<option value="${esc(s)}">${esc(s)}</option>`).join("");
  $("t-start").innerHTML = `<option value="">(first)</option>` + opts;
  $("t-stop").innerHTML = `<option value="">(last)</option>` + opts;
  // which declared inputs are missing from data/output -> offer to seed
  const arts = (await (await fetch("/artifacts")).json()).files;
  const need = (meta ? meta.inputs : []).filter(f => !arts.includes(f));
  const seedable = need.filter(f => (meta.fixtures || []).includes(f));
  $("t-seed").innerHTML = need.length
    ? `Missing inputs: ${need.map(f => `<code>${esc(f)}</code>`).join(" ")}` +
      (seedable.length ? ` — <label><input type="checkbox" id="t-doseed" checked> seed ${seedable.length} from fixtures</label>` : ` <b style="color:var(--bad)">(no fixtures — run upstream first)</b>`)
    : `All declared inputs present.`;
  $("t-seed").dataset.seedable = JSON.stringify(seedable);
}

$("t-dryrun").onclick = async () => {
  const open = document.querySelector("#promptList .prompt[open]");
  const id = open ? open.dataset.id : (workflowsMeta[0] && "research.audience_researcher");
  const text = open ? open.querySelector("textarea").value : null;
  const res = await fetch("/prompts/preview", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id, text }) });
  const { rendered } = await res.json();
  const pre = $("t-preview"); pre.textContent = rendered; pre.classList.remove("hide");
};
```

- [ ] **Step 3: Wire Start to the panel** (the body now carries target/stages/seed)

Replace the `$("startBtn").onclick` body's fetch with:

```javascript
  const target = $("t-target").value;
  const seedable = JSON.parse($("t-seed").dataset.seedable || "[]");
  const doSeed = $("t-doseed") && $("t-doseed").checked;
  const body = {
    target,
    start_stage: $("t-start").value || null,
    stop_stage: $("t-stop").value || null,
    seed_fixtures: doSeed ? seedable : [],
  };
  const res = await fetch("/start", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
```

- [ ] **Step 4: Manual verification** (after Task 10 lands the `/start` routing)

Defer the live check to Task 10 Step 5 (the `/start` body isn't honored until then). For now confirm the panel renders and the selects populate.

Run: `cd embroidery && venv/bin/python -m embroidery.web --no-browser`, open the page, expand **🧪 Test / run**, switch target to **QA** → confirm it lists missing inputs (`positioning_matrix.json`, `video_scripts.json`, `static_ad_copy.json`) with a seed checkbox.

- [ ] **Step 5: Commit**

```bash
git add embroidery/embroidery/web/static/index.html
git commit -m "Dashboard: Test/Run panel (target, stage range, seed fixtures, dry-run)"
```

---

# Phase 4 — Orchestrator

### Task 8: `core/orchestrator.py` — `run_team`

**Files:**
- Create: `embroidery/embroidery/core/orchestrator.py`
- Test: `embroidery/tests/test_orchestrator.py`

- [ ] **Step 1: Write the failing test**

Create `embroidery/tests/test_orchestrator.py`:

```python
"""
run_team walks the registry: enforces inputs⊆outputs gating, slices start/stop,
and loops QA on FAIL. All stubbed — no providers, deterministic.

Run: cd embroidery && venv/bin/python -m tests.test_orchestrator
"""
import asyncio
import json
import sys
from pathlib import Path

from embroidery.core import orchestrator
from embroidery.core.workflow import Stage, WorkflowSpec, register, clear_registry
from embroidery.core.checkpoint import Decision, CheckpointResult
from embroidery.core.config import settings

failures: list[str] = []
ran: list[str] = []

def check(cond, msg):
    print(("✓ " if cond else "✗ ") + msg)
    if not cond:
        failures.append(msg)

async def _approve(stage, digest, *, workflow="", request=None):
    return CheckpointResult(Decision.APPROVE, request)

def _out(name):
    return Path(settings.paths.output) / name

def main() -> int:
    out = Path(settings.paths.output); out.mkdir(parents=True, exist_ok=True)

    # ---- gating: wfb needs a.json that wfa produces ----
    clear_registry(); ran.clear()
    for f in ("a.json",):
        (_out(f)).unlink(missing_ok=True)

    async def wfa(brief=None, *, start_stage=None, stop_stage=None, gate=None):
        ran.append("wfa"); _out("a.json").write_text("{}", encoding="utf-8"); return {}
    async def wfb(brief=None, *, start_stage=None, stop_stage=None, gate=None):
        ran.append("wfb"); return {}

    register(WorkflowSpec("wfa", "A", [Stage("s", ["x"])], wfa, outputs=["a.json"]))
    register(WorkflowSpec("wfb", "B", [Stage("s", ["y"])], wfb, inputs=["a.json"]))
    asyncio.run(orchestrator.run_team(gate=_approve))
    check(ran == ["wfa", "wfb"], "team runs wfa then wfb when inputs satisfied")

    # ---- gating blocks wfb when a.json missing ----
    clear_registry(); ran.clear(); _out("a.json").unlink(missing_ok=True)
    register(WorkflowSpec("wfb", "B", [Stage("s", ["y"])], wfb, inputs=["a.json"]))
    res = asyncio.run(orchestrator.run_team(gate=_approve))
    check(ran == [] and res is None, "team blocks a workflow whose inputs are missing")

    # ---- slicing: start=stop runs only that workflow ----
    clear_registry(); ran.clear()
    register(WorkflowSpec("wfa", "A", [Stage("s", ["x"])], wfa, outputs=["a.json"]))
    register(WorkflowSpec("wfb", "B", [Stage("s", ["y"])], wfb))   # no inputs
    asyncio.run(orchestrator.run_team(start="wfb", stop="wfb", gate=_approve))
    check(ran == ["wfb"], "start=stop runs only the selected workflow")

    # ---- QA FAIL re-loops copy once ----
    clear_registry(); ran.clear()
    copy_runs = {"n": 0}
    async def copy(brief=None, *, start_stage=None, stop_stage=None, gate=None):
        ran.append("copy"); copy_runs["n"] += 1; return {}
    async def qa(brief=None, *, start_stage=None, stop_stage=None, gate=None):
        ran.append("qa")
        overall = "FAIL" if copy_runs["n"] < 2 else "PASS"
        _out("qa_report.json").write_text(json.dumps({"overall": overall, "ads": []}), encoding="utf-8")
        return {}
    register(WorkflowSpec("copy", "Copy", [Stage("s", ["h"])], copy, outputs=["video_scripts.json"]))
    register(WorkflowSpec("qa", "QA", [Stage("s", ["q"])], qa, inputs=[], outputs=["qa_report.json"]))
    asyncio.run(orchestrator.run_team(gate=_approve, max_qa_loops=2))
    check(ran == ["copy", "qa", "copy", "qa"], "QA FAIL re-loops copy then re-runs QA")

    clear_registry()
    if failures:
        print(f"\n✗ test_orchestrator FAILED ({len(failures)})")
        return 1
    print("\n✓ test_orchestrator passed")
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it — verify it fails**

Run: `cd embroidery && venv/bin/python -m tests.test_orchestrator`
Expected: FAIL — `ModuleNotFoundError: embroidery.core.orchestrator`.

- [ ] **Step 3: Implement `core/orchestrator.py`**

Create `embroidery/embroidery/core/orchestrator.py`:

```python
"""
Generic team orchestrator — walks the WorkflowSpec registry to run the campaign
end to end, with no per-workflow code.

run_team():
  * slices the registry to [start..stop] (defaults: whole team);
  * before each workflow, asserts its declared `inputs` exist in data/output
    (a prior workflow's outputs or a seeded fixture) — this enforces the
    data-contract gates ("no positioning_matrix.json -> Copy doesn't run");
  * runs each workflow's entry_point inside reporter.workflow_context(id);
  * after the QA workflow, reads qa_report.json: on overall FAIL it re-loops the
    Copy workflow (bounded by max_qa_loops) then re-runs QA;
  * owns the run-level reporter lifecycle + the terminal done/aborted/blocked
    event + the run_report.md perf digest.

Stage-level QC gates live inside each entry_point; this module adds the
data-contract gate between workflows.
"""

import json
from pathlib import Path

from embroidery.core.checkpoint import checkpoint
from embroidery.core.config import settings
from embroidery.core.logger import get_logger
from embroidery.core.reporter import get_reporter
from embroidery.core.workflow import get_registry

log = get_logger(__name__)


def _missing_inputs(spec) -> list[str]:
    out = Path(settings.paths.output)
    return [f for f in spec.inputs if not (out / f).exists()]


def _write_report(reporter) -> None:
    out = Path(settings.paths.output)
    out.mkdir(parents=True, exist_ok=True)
    (out / "run_report.md").write_text(reporter.render_markdown(), encoding="utf-8")


async def run_team(
    brief: dict | None = None,
    *,
    start: str | None = None,
    stop: str | None = None,
    start_stage: str | None = None,
    stop_stage: str | None = None,
    gate=checkpoint,
    max_qa_loops: int = 2,
) -> dict | None:
    """Run the registry [start..stop]. Returns a summary dict, or None if blocked/quit."""
    registry = get_registry()
    ids = [s.id for s in registry]
    si = ids.index(start) if start else 0
    ei = ids.index(stop) if stop else len(registry) - 1
    selected = registry[si:ei + 1]

    reporter = get_reporter()
    reporter.reset()
    log.info("run_team start=%s stop=%s workflows=%s", start, stop, [s.id for s in selected])

    qa_loops = 0
    i = 0
    while i < len(selected):
        spec = selected[i]

        missing = _missing_inputs(spec)
        if missing:
            log.warning("run_team blocked at %s — missing inputs %s", spec.id, missing)
            _write_report(reporter)
            reporter.publish({"type": "done", "status": "blocked", "workflow": spec.id,
                              "reason": f"missing required inputs: {', '.join(missing)}"})
            return None

        # stage slicing only applies to the first selected workflow
        ss = start_stage if i == 0 else None
        es = stop_stage if i == 0 else None
        with reporter.workflow_context(spec.id):
            result = await spec.entry_point(brief, start_stage=ss, stop_stage=es, gate=gate)

        if result is None:           # the workflow's own gate quit / stopped
            _write_report(reporter)
            reporter.publish({"type": "done", "status": "aborted", "workflow": spec.id,
                              "reason": "stopped at a stage gate"})
            return None

        # QA FAIL re-loop: jump back to the copy workflow if one is selected.
        if spec.id == "qa" and qa_loops < max_qa_loops:
            report_path = Path(settings.paths.output) / "qa_report.json"
            overall = "PASS"
            if report_path.exists():
                try:
                    overall = json.loads(report_path.read_text(encoding="utf-8")).get("overall", "PASS")
                except json.JSONDecodeError:
                    overall = "PASS"
            copy_idx = next((j for j, s in enumerate(selected) if s.id == "copy"), None)
            if overall == "FAIL" and copy_idx is not None:
                qa_loops += 1
                log.info("run_team QA FAIL — re-loop %d/%d back to copy", qa_loops, max_qa_loops)
                i = copy_idx
                continue

        i += 1

    _write_report(reporter)
    files = [f for s in selected for f in s.outputs]
    reporter.publish({"type": "done", "status": "complete", "files": files,
                      "totals": reporter.snapshot()["totals"]})
    log.info("run_team complete workflows=%s", [s.id for s in selected])
    return {"workflows": [s.id for s in selected], "files": files}
```

- [ ] **Step 4: Run it — verify it passes**

Run: `cd embroidery && venv/bin/python -m tests.test_orchestrator`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add embroidery/embroidery/core/orchestrator.py embroidery/tests/test_orchestrator.py
git commit -m "Add generic team orchestrator (run_team) with data-contract gating"
```

---

### Task 9: Register the QA workflow

**Files:**
- Modify: `embroidery/embroidery/agents/qa/qa_reviewer.py`
- Create: `embroidery/embroidery/agents/qa/pipeline.py`
- Test: `embroidery/tests/test_qa_workflow.py`

- [ ] **Step 1: Write the failing test**

Create `embroidery/tests/test_qa_workflow.py`:

```python
"""
The QA workflow registers a spec, exposes an editable prompt, and its entry_point
runs the reviewer + a gate (stubbed — no provider). No tokens.

Run: cd embroidery && venv/bin/python -m tests.test_qa_workflow
"""
import asyncio
import json
import sys
from pathlib import Path

import embroidery.agents.qa.pipeline as Q
from embroidery.core.workflow import get_spec
from embroidery.core.checkpoint import Decision, CheckpointResult
from embroidery.core.config import settings

failures: list[str] = []

def check(cond, msg):
    print(("✓ " if cond else "✗ ") + msg)
    if not cond:
        failures.append(msg)

async def _approve(stage, digest, *, workflow="", request=None):
    return CheckpointResult(Decision.APPROVE, request)

def main() -> int:
    spec = get_spec("qa")
    check(spec.label == "QA", "qa spec registered")
    check(spec.inputs == ["positioning_matrix.json", "video_scripts.json", "static_ad_copy.json"],
          "qa declares its three data-contract inputs")
    check(spec.outputs == ["qa_report.json"], "qa declares qa_report.json output")
    cat = spec.prompt_catalog()
    check(any(p["id"] == "qa.reviewer" for p in cat), "qa exposes an editable reviewer prompt")

    # entry_point with the reviewer stubbed to just drop a report
    async def fake_review():
        out = Path(settings.paths.output); out.mkdir(parents=True, exist_ok=True)
        (out / "qa_report.json").write_text(json.dumps({"overall": "PASS", "ads": []}), encoding="utf-8")
        return str(out / "qa_report.json")
    Q.run_qa_review = fake_review
    res = asyncio.run(Q.run_qa(gate=_approve))
    check(res and "qa_report" in res, "run_qa returns the report path")

    if failures:
        print(f"\n✗ test_qa_workflow FAILED ({len(failures)})")
        return 1
    print("\n✓ test_qa_workflow passed")
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it — verify it fails**

Run: `cd embroidery && venv/bin/python -m tests.test_qa_workflow`
Expected: FAIL — `ModuleNotFoundError: embroidery.agents.qa.pipeline`.

- [ ] **Step 3: Make the QA prompt editable**

In `embroidery/embroidery/agents/qa/qa_reviewer.py`, render the system prompt through the store. Add the import:

```python
from embroidery.core.prompt_store import get_prompt_store
```

Change the `run_agent(system=SYSTEM_PROMPT, ...)` call in `run_qa_review` to:

```python
    await run_agent(
        system=get_prompt_store().render("qa.reviewer", SYSTEM_PROMPT),
        messages=messages,
        tools=FILE_TOOLS,
        model_settings=settings.agents.qa_reviewer,
        max_tool_calls=20,
        agent_name="qa_reviewer",
    )
```

(`SYSTEM_PROMPT` has no `$placeholders`, so `safe_substitute` returns it verbatim unless the user edits it.)

- [ ] **Step 4: Implement `agents/qa/pipeline.py`**

Create `embroidery/embroidery/agents/qa/pipeline.py`:

```python
"""
QA workflow (Agent 7) wired onto the WorkflowSpec registry.

The reviewer itself lives in qa_reviewer.py; this module gives it a registry
spec, an editable prompt catalog, and a gated entry_point so the dashboard can
monitor/test/edit it like any other workflow.
"""

import json
from pathlib import Path

from embroidery.agents.qa.qa_reviewer import SYSTEM_PROMPT, run_qa_review
from embroidery.core.checkpoint import Decision, checkpoint
from embroidery.core.config import settings
from embroidery.core.logger import get_logger
from embroidery.core.prompt_store import get_prompt_store
from embroidery.core.reporter import get_reporter
from embroidery.core.workflow import Stage, WorkflowSpec, register

log = get_logger(__name__)

QA_STAGE = "qa review"


def _digest(report: dict) -> dict:
    ads = report.get("ads", [])
    return {
        "overall": report.get("overall"),
        "ads_reviewed": len(ads),
        "fails": [a.get("ad_id") for a in ads if a.get("revision_required")],
    }


async def run_qa(brief: dict | None = None, *, start_stage=None, stop_stage=None, gate=checkpoint) -> dict | None:
    """Run Agent 7 and pause at one QC gate. Returns {'qa_report': path} or None on quit."""
    reporter = get_reporter()
    reporter.publish({"type": "stage", "workflow": "qa", "stage": QA_STAGE})
    path = await run_qa_review()
    report = json.loads(Path(path).read_text(encoding="utf-8"))
    res = await gate(QA_STAGE, _digest(report), workflow="qa", request=brief)
    if res.decision is Decision.QUIT:
        return None
    return {"qa_report": path}


def prompt_catalog() -> list[dict]:
    store = get_prompt_store()
    return [{
        "id": "qa.reviewer",
        "name": "Agent 7 — QA Reviewer",
        "stage": "QA — review",
        "placeholders": [],
        "default": SYSTEM_PROMPT,
        "text": store.text("qa.reviewer", SYSTEM_PROMPT),
        "overridden": store.is_overridden("qa.reviewer"),
    }]


register(WorkflowSpec(
    id="qa",
    label="QA",
    stages=[Stage(QA_STAGE, ["qa_reviewer"])],
    entry_point=run_qa,
    prompt_catalog=prompt_catalog,
    inputs=["positioning_matrix.json", "video_scripts.json", "static_ad_copy.json"],
    outputs=["qa_report.json"],
    fixtures=["positioning_matrix.json", "video_scripts.json", "static_ad_copy.json"],
    config_schema={"qa_reviewer": {"model": settings.agents.qa_reviewer.model}},
))
```

- [ ] **Step 5: Run it — verify it passes**

Run: `cd embroidery && venv/bin/python -m tests.test_qa_workflow`
Expected: PASS.

- [ ] **Step 6: Regression — Agent 7 manual test still works**

Run: `cd embroidery && venv/bin/python -m tests.test_agent7` (needs API key + live; if no key, skip and note). The prompt-store change is transparent (no override set → verbatim prompt).

- [ ] **Step 7: Commit**

```bash
git add embroidery/embroidery/agents/qa/pipeline.py embroidery/embroidery/agents/qa/qa_reviewer.py embroidery/tests/test_qa_workflow.py
git commit -m "Register QA workflow (Agent 7) on the registry + editable prompt"
```

---

### Task 10: Route `/start` through `run_team`

**Files:**
- Modify: `embroidery/embroidery/web/server.py`
- Test: `embroidery/tests/test_start_routing.py`

- [ ] **Step 1: Write the failing test**

Create `embroidery/tests/test_start_routing.py`:

```python
"""
/start computes the run_team call from {target, start_stage, stop_stage,
seed_fixtures}. We stub run_team to capture the call; no pipeline runs.

Run: cd embroidery && venv/bin/python -m tests.test_start_routing
"""
import asyncio
import sys
from pathlib import Path

from embroidery.web import server
from embroidery.core.config import settings

failures: list[str] = []
captured = {}

def check(cond, msg):
    print(("✓ " if cond else "✗ ") + msg)
    if not cond:
        failures.append(msg)

def main() -> int:
    # ensure no run in progress
    server._run_task = None

    async def fake_run_team(brief=None, *, start=None, stop=None, start_stage=None, stop_stage=None, gate=None):
        captured.update(start=start, stop=stop, start_stage=start_stage, stop_stage=stop_stage)
    # patch the symbol run_team is looked up as inside server
    server._run_team_for_test = fake_run_team

    # Drive start() AND let its background task run on the SAME event loop, else
    # the created task is orphaned when asyncio.run() closes the loop.
    async def drive(body):
        await server.start(body)
        await asyncio.sleep(0.02)

    # target=research -> start=stop="research"
    captured.clear()
    asyncio.run(drive(server.StartBody(target="research", start_stage="synthesis")))
    check(captured.get("start") == "research" and captured.get("stop") == "research",
          "target=research runs only the research workflow")
    check(captured.get("start_stage") == "synthesis", "start_stage forwarded")

    # target=team -> start=stop=None
    server._run_task = None
    captured.clear()
    asyncio.run(drive(server.StartBody(target="team")))
    check(captured.get("start") is None and captured.get("stop") is None, "target=team runs the whole registry")

    # seed_fixtures copies before launch (synchronous, before the task is created)
    server._run_task = None
    (Path(settings.paths.output) / "positioning_matrix.json").unlink(missing_ok=True)
    asyncio.run(drive(server.StartBody(target="qa", seed_fixtures=["positioning_matrix.json"])))
    check((Path(settings.paths.output) / "positioning_matrix.json").exists(),
          "seed_fixtures copies fixtures before the run")

    if failures:
        print(f"\n✗ test_start_routing FAILED ({len(failures)})")
        return 1
    print("\n✓ test_start_routing passed")
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it — verify it fails**

Run: `cd embroidery && venv/bin/python -m tests.test_start_routing`
Expected: FAIL — `StartBody` has no `target`; `start()` still calls `run_market_research`.

- [ ] **Step 3: Rewrite `/start` in `server.py`**

Replace the `StartBody` model and `start` / `_guarded_run` block with:

```python
from embroidery.core.orchestrator import run_team

# Test seam: tests set server._run_team_for_test to capture calls.
_run_team_for_test = None


class StartBody(BaseModel):
    target: str = "team"               # workflow id or "team"
    start_stage: str | None = None
    stop_stage: str | None = None
    brief: dict | None = None
    seed_fixtures: list[str] = []


@app.post("/start")
async def start(body: StartBody | None = None):
    global _run_task
    if _run_in_progress():
        raise HTTPException(409, "a run is already in progress")
    body = body or StartBody()

    if body.seed_fixtures:
        _seed_fixtures(body.seed_fixtures)

    runner = _run_team_for_test or run_team
    if body.target == "team":
        start = stop = None
    else:
        if body.target not in {s.id for s in get_registry()}:
            raise HTTPException(404, f"unknown workflow {body.target}")
        start = stop = body.target

    _run_task = asyncio.create_task(
        _guarded_run(runner, body.brief, start, stop, body.start_stage, body.stop_stage)
    )
    return {"status": "started", "target": body.target}


async def _guarded_run(runner, brief, start, stop, start_stage, stop_stage):
    try:
        await runner(brief, start=start, stop=stop, start_stage=start_stage, stop_stage=stop_stage)
    except Exception as exc:   # surface crashes to the dashboard instead of dying silently
        log.exception("team run failed")
        get_reporter().publish({"type": "done", "status": "error", "reason": str(exc)})
```

- [ ] **Step 4: Run it — verify it passes**

Run: `cd embroidery && venv/bin/python -m tests.test_start_routing`
Expected: PASS.

- [ ] **Step 5: Full manual verification (Monitor + Test + Edit, end to end)**

Run: `cd embroidery && venv/bin/python -m embroidery.web --no-browser`, open `http://127.0.0.1:8765`. Verify:
1. **Rail** shows **Research → QA**; **🧪 Test / run** lists both workflows.
2. Target **QA**, no seed → **Start** → the **QA** lane goes `blocked` (rail QA turns red, done panel shows "missing required inputs: …") — data-contract gate works.
3. Target **QA**, seed the three fixtures → **Start** → QA lane runs, gate opens with the digest, Approve → complete. (Needs an API key; otherwise confirm the blocked path only.)
4. **⚙ Agent prompts** lists research **and** QA prompts; **Dry-run prompts** shows a rendered prompt with `$shop_context` filled.
Ctrl-C to stop.

- [ ] **Step 6: Run the whole test suite**

Run each and confirm `✓`:
```bash
cd embroidery
for t in test_workflow test_reporter_workflow test_research_stages test_web_workflows test_web_test_panel test_orchestrator test_qa_workflow test_start_routing smoke_test; do
  echo "== $t =="; venv/bin/python -m tests.$t || echo "FAILED $t"
done
```
Expected: every module prints its `✓ … passed`.

- [ ] **Step 7: Commit**

```bash
git add embroidery/embroidery/web/server.py embroidery/tests/test_start_routing.py
git commit -m "Web: route /start through run_team (target/stages/seed)"
```

---

### Task 11: Documentation

**Files:**
- Modify: `embroidery/embroidery/core/README.md`, `embroidery/embroidery/web/README.md`, `embroidery/embroidery/agents/README.md`, `CLAUDE.md`, `development-plan.md`

Per the repo README rule, a new module / changed data-contract enforcement / new endpoints are all "significant".

- [ ] **Step 1: `core/README.md`** — add `workflow.py` (the registry contract: `Stage`/`WorkflowSpec`/`register`/`load_workflows`) and `orchestrator.py` (`run_team`: registry walk, input gating, QA re-loop, run-level events). Note `reporter.py` now tags rows with `workflow` and exposes `workflow_context()`, and `checkpoint()` takes a `workflow=` arg.

- [ ] **Step 2: `web/README.md`** — add `GET /workflows`, `GET /artifacts`, `POST /prompts/preview` to the Endpoints table; extend `POST /start`'s body to `{target, start_stage, stop_stage, brief, seed_fixtures}`; note the UI is now workflow lanes + rail + Test/Run panel. In the **Design requirements** section, flip the now-shipped boxes: Monitor sub-agent rows ✅; Test stage-select ✅, fixture seeding ✅, dry-run ✅, standalone entry points ✅ (research+qa); Edit QC-gate-at-boundary ✅ (research+qa), data-contract gate visible ✅. Leave Copy/Feedback ☐ and config-from-UI ☐ and the QA-FAIL-reloop visible-gate ◐ (logic exists; copy not built).

- [ ] **Step 3: `agents/README.md`** — document the register-a-spec contract: a workflow module exposes an async `entry_point(brief, *, start_stage, stop_stage, gate)`, a `prompt_catalog()`, and calls `register(WorkflowSpec(...))` at import; `load_workflows()` imports them in team order. Note QA now has `agents/qa/pipeline.py` alongside `qa_reviewer.py`.

- [ ] **Step 4: `CLAUDE.md`** — in the architecture diagram add `core/workflow.py` (registry) and `core/orchestrator.py` (run_team); in the data-contract table note gating is now **enforced by the orchestrator** (no `positioning_matrix.json` → Copy blocked). Update the dashboard line to "lanes + rail + Test/Run panel; research + QA wired."

- [ ] **Step 5: `development-plan.md`** — add a dated note (June 13, 2026) recording phases 1–4 of the whole-team dashboard: WorkflowSpec registry, generic orchestrator with data-contract gating, research retrofitted + QA wired as the second workflow, lanes UI + Test panel. Reference the spec + this plan.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "Docs: WorkflowSpec registry, orchestrator, lanes/Test panel across READMEs + CLAUDE.md"
```

---

## Notes for the implementer

- **Run order:** do the tasks in number order — each builds on the last. Phases 1–2 are independently mergeable; phase 3 needs phase 2's lanes; phase 4 needs phases 1–3.
- **No provider tests:** every test here stubs at the workflow/provider boundary (fake `entry_point`s, monkeypatched `run_subagent`/`run_synthesizer`/`run_qa_review`). Do not add live-provider tests — real agent runs stay manual via the dashboard (`tests.test_agent7` and a full research run are the live checks, run only with API keys).
- **House test style:** keep the `main()` + `check()` + exit-code pattern (matches `tests/test_agent7.py`); no pytest.
- **Out of scope (later phases):** config editing from the UI, Copy/Feedback workflows, and the cross-run persistence/`CampaignStore` are phases 5–6 in the spec — do not build them here.
```
