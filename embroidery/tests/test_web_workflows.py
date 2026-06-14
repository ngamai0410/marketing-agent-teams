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

    # manual onboarding — author Stage 0 by hand, pre-filled from disk
    import json
    from pathlib import Path
    from embroidery.core.config import settings
    ob_file = Path(settings.paths.output) / "avatar_onboarding.json"
    ob_backup = ob_file.read_text(encoding="utf-8") if ob_file.exists() else None
    try:
        ob = asyncio.run(server.get_onboarding())
        check(len(ob["questions"]) == 11, "/onboarding exposes the 11 Stage-0 questions")
        check(ob["questions"][0]["key"] == "Q1" and ob["file"] == "avatar_onboarding.json",
              "/onboarding carries question keys + the target file")
        res = asyncio.run(server.save_onboarding(server.OnboardingBody(answers={"Q1": "test blanket", "Q5": "keepsake"})))
        check(res["status"] == "saved" and res["answered"] == 2, "POST /onboarding writes answered fields")
        saved = json.loads(ob_file.read_text(encoding="utf-8"))
        check(saved["Q1"] == "test blanket" and saved["Q3"] == "", "onboarding file has all keys, blanks where unanswered")
        ob2 = asyncio.run(server.get_onboarding())
        check(ob2["answers"]["Q1"] == "test blanket", "/onboarding pre-fills from the saved file")
    finally:
        if ob_backup is not None:
            ob_file.write_text(ob_backup, encoding="utf-8")
        elif ob_file.exists():
            ob_file.unlink()

    if failures:
        print(f"\n✗ test_web_workflows FAILED ({len(failures)})")
        return 1
    print("\n✓ test_web_workflows passed")
    return 0

if __name__ == "__main__":
    sys.exit(main())
