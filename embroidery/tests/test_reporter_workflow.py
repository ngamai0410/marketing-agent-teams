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
