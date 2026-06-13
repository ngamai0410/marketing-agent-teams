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
