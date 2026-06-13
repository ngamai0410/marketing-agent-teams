"""
The avatar pipeline registers a WorkflowSpec and honours start/stop-stage slicing
and gate decisions, with every stage runner stubbed. No providers, no tokens.

Run: cd embroidery && venv/bin/python -m tests.test_avatar_stages
"""
import asyncio
import sys

import embroidery.agents.avatar.pipeline as P
from embroidery.core.workflow import get_spec
from embroidery.core.checkpoint import Decision, CheckpointResult

failures: list[str] = []
calls: list[str] = []

def check(cond, msg):
    print(("✓ " if cond else "✗ ") + msg)
    if not cond:
        failures.append(msg)

async def _approve(stage, digest, *, workflow="", request=None):
    return CheckpointResult(Decision.APPROVE, request)

async def _rec(name, ret):
    calls.append(name)
    return ret

def _stub_all():
    calls.clear()
    # one stub per stage runner (each returns a coroutine via _rec)
    P.run_onboarding   = (lambda *a, **k: _rec("onboarding", {}))
    P.run_product      = (lambda *a, **k: _rec("product", {}))
    P.run_discovery    = (lambda *a, **k: _rec("discovery", {"reddit": {}, "amazon": {}, "fb": {}}))
    P.run_qualify      = (lambda *a, **k: _rec("qualify", {"priority_avatars": ["X"]}))
    P.run_voc          = (lambda *a, **k: _rec("voc", {}))
    P.run_awareness    = (lambda *a, **k: _rec("awareness", {}))
    P.run_competitor   = (lambda *a, **k: _rec("competitor", {}))
    P.run_mechanism    = (lambda *a, **k: _rec("mechanism", {}))
    P.run_synthesis    = (lambda *a, **k: _rec("synthesis", ({}, "# md")))
    P.load_research    = lambda: ({"segments": {}}, "")

def main() -> int:
    spec = get_spec("avatar")
    check(spec.label == "Avatar Builder", "avatar spec registered with label")
    check(spec.stage_names() == ["onboarding", "product", "discovery", "qualify", "voc",
                                 "awareness", "competitor", "mechanism", "synthesis"],
          "avatar declares 9 stages in order")
    check(spec.inputs == ["market_research_report.json", "brand_intelligence_report.md"],
          "avatar declares its research inputs")
    check(spec.outputs == ["customer_avatars.md", "avatar_deep_dive.json"],
          "avatar declares its data-contract outputs")

    from embroidery.core.workflow import load_workflows
    order = [s.id for s in load_workflows()]
    check(order.index("research") < order.index("avatar") < order.index("qa"),
          "load_workflows orders research -> avatar -> qa")

    # full run hits every stage in order
    _stub_all()
    asyncio.run(P.run_avatar_builder(gate=_approve))
    check(calls == ["onboarding", "product", "discovery", "qualify", "voc",
                    "awareness", "competitor", "mechanism", "synthesis"],
          "full run executes all 9 stages in order")

    # start at synthesis -> only synthesis runs (others load from disk)
    _stub_all()
    asyncio.run(P.run_avatar_builder(start_stage="synthesis", gate=_approve))
    check(calls == ["synthesis"], "start_stage=synthesis skips upstream stages")

    # stop at qualify -> stops after qualify
    _stub_all()
    res = asyncio.run(P.run_avatar_builder(stop_stage="qualify", gate=_approve))
    check(calls == ["onboarding", "product", "discovery", "qualify"],
          "stop_stage=qualify stops after the qualify stage")
    check(res is None, "stop_stage before synthesis returns None")

    # QUIT at the first gate aborts immediately
    _stub_all()
    async def _quit_once(stage, digest, *, workflow="", request=None):
        return CheckpointResult(Decision.QUIT, request)
    res = asyncio.run(P.run_avatar_builder(gate=_quit_once))
    check(res is None and calls == ["onboarding"], "QUIT at first gate aborts the run")

    if failures:
        print(f"\n✗ test_avatar_stages FAILED ({len(failures)})")
        return 1
    print("\n✓ test_avatar_stages passed")
    return 0

if __name__ == "__main__":
    sys.exit(main())
