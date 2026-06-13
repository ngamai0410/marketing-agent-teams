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
