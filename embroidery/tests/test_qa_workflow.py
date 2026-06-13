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
