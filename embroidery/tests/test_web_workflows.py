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
    prompts = pr["prompts"]
    pids = [p["id"] for p in prompts]
    check("research.audience_researcher" in pids, "/prompts aggregates research prompts from registry")

    # workflow-aligned ordering: shared blocks first (global before workflow-scoped),
    # then agent prompts in registry order, each workflow in its stage/execution order.
    pos = {pid: i for i, pid in enumerate(pids)}
    check(pids[0] == "shared.shop_context", "/prompts lists the global shared shop context first")
    check(pos["shared.shop_context"] < pos["research.shared_rules"] < pos["research.audience_researcher"],
          "shared blocks precede agent prompts (global before workflow-scoped)")
    # research agents in stage order, before avatar agents, before qa
    check(pos["research.audience_researcher"] < pos["research.synthesizer_json"] < pos["avatar.avatar_onboarder"],
          "research agents (sub-agents -> synthesis) precede avatar")
    # avatar agents follow the 9-stage execution order
    check(pos["avatar.avatar_onboarder"] < pos["avatar.reddit_scout"] < pos["avatar.avatar_qualifier"]
          < pos["avatar.voc_miner"] < pos["avatar.awareness_mapper"] < pos["avatar.avatar_synthesizer"],
          "avatar prompts follow stage/execution order")
    check(pos["avatar.avatar_synthesizer"] < pos["qa.reviewer"], "qa prompt comes last (after avatar)")
    # no shared block is wedged among the agent prompts
    first_agent = pos["research.audience_researcher"]
    check(all(("shared" not in prompts[i]["stage"].lower() and not prompts[i]["id"].startswith("shared."))
              for i in range(first_agent, len(prompts))),
          "no shared block appears after the first agent prompt")

    if failures:
        print(f"\n✗ test_web_workflows FAILED ({len(failures)})")
        return 1
    print("\n✓ test_web_workflows passed")
    return 0

if __name__ == "__main__":
    sys.exit(main())
