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
