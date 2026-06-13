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
