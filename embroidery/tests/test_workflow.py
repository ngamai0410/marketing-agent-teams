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
