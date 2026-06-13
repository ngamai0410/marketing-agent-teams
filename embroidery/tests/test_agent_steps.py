"""
The reporter records an ordered `steps` list per agent (call / search / write /
fetch / output), and as_row() carries it so the dashboard can render a pipeline.
Also covers the write_file tap in agent_loop._execute_tool. No providers.

Run: cd embroidery && venv/bin/python -m tests.test_agent_steps
"""
import asyncio
import sys
from pathlib import Path

from embroidery.core.reporter import get_reporter
from embroidery.core.agent_loop import _execute_tool
from embroidery.core.config import settings

failures: list[str] = []

def check(cond, msg):
    print(("✓ " if cond else "✗ ") + msg)
    if not cond:
        failures.append(msg)

def test_steps_recorded_in_order():
    r = get_reporter()
    r.reset()
    r.agent_start("ag", "claude-sonnet-4-6", 100)
    r.agent_call("ag", 100, 20)
    r.agent_search("ag", "embroidery gifts", 10)
    r.agent_write("ag", "out.json")
    r.agent_done("ag")
    rec = r.snapshot()["rows"][0]
    steps = rec["steps"]
    check([s["type"] for s in steps] == ["call", "search", "write"], "steps recorded in order")
    check(steps[0]["in_tok"] == 100 and steps[0]["out_tok"] == 20, "call step carries tokens")
    check(steps[1]["label"] == "embroidery gifts" and steps[1]["results"] == 10, "search step carries query + results")
    check(steps[2]["output_file"] == "out.json", "write step carries output_file")
    check([s["seq"] for s in steps] == [1, 2, 3], "steps numbered sequentially")

def test_output_step_and_rerun_clears():
    r = get_reporter()
    r.reset()
    r.agent_start("ag", "m", 100)
    r.agent_call("ag", 1, 1)
    r.agent_output("ag", "report.json")
    rec = r.snapshot()["rows"][0]
    check(rec["steps"][-1]["type"] == "output" and rec["steps"][-1]["output_file"] == "report.json",
          "agent_output appends an output node")
    r.agent_start("ag", "m", 100)  # re-run resets
    check(r.snapshot()["rows"][0]["steps"] == [], "re-run clears steps")

def test_write_file_tap():
    async def run():
        r = get_reporter()
        r.reset()
        r.agent_start("writer", "m", 100)
        await _execute_tool("write_file", {"filename": "_steptest.json", "content": "{}"}, "writer")
        steps = r.snapshot()["rows"][0]["steps"]
        check(any(s["type"] == "write" and s["output_file"] == "_steptest.json" for s in steps),
              "_execute_tool(write_file) records a write step")
        (Path(settings.paths.output) / "_steptest.json").unlink(missing_ok=True)
    asyncio.run(run())

def main() -> int:
    test_steps_recorded_in_order()
    test_output_step_and_rerun_clears()
    test_write_file_tap()
    if failures:
        print(f"\n✗ test_agent_steps FAILED ({len(failures)})")
        return 1
    print("\n✓ test_agent_steps passed")
    return 0

if __name__ == "__main__":
    sys.exit(main())
