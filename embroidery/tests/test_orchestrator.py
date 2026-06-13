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
