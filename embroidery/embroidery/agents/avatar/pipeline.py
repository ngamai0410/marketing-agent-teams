"""
Agent 2 — Customer Avatar Builder pipeline (Evolve 9-stage avatar engine).

  research report ─► onboarding ─► product ─► discovery ─► [qualify gate]
                  ─► voc ─► awareness ─► competitor ─► mechanism ─► synthesis
                  ─► customer_avatars.md + avatar_deep_dive.json

Reads Agent 1's market_research_report.json + brand_intelligence_report.md (the
orchestrator's data-contract gate blocks this workflow if they are absent). A QC
gate fires at every stage boundary (Approve / Edit / Quit); standalone runs
auto-approve. start_stage/stop_stage slice the run; skipped stages load their
saved JSON from data/output/.

Run (standalone, auto-approves; needs the research outputs or seeded fixtures on disk):
    cd embroidery && venv/bin/python -m embroidery.agents.avatar.pipeline [--yes]
"""

import asyncio
import json
import os
import sys
from pathlib import Path

from embroidery.agents.avatar._common import load_json
from embroidery.agents.avatar.discovery import run_discovery, run_qualify
from embroidery.agents.avatar.framing import run_onboarding, run_product
from embroidery.agents.avatar.reframe import run_awareness, run_competitor, run_mechanism
from embroidery.agents.avatar.synthesizer import run_synthesis
from embroidery.agents.avatar.voc import run_voc
from embroidery.agents.research.subagents import SHOP_BRIEF
from embroidery.core.agent_loop import reset_search_count
from embroidery.core.checkpoint import Decision, checkpoint
from embroidery.core.config import settings
from embroidery.core.logger import get_logger
from embroidery.core.reporter import get_reporter

log = get_logger(__name__)

_STAGES = ["onboarding", "product", "discovery", "qualify", "voc",
           "awareness", "competitor", "mechanism", "synthesis"]


def _active(start_stage: str | None, stop_stage: str | None) -> set[str]:
    si = _STAGES.index(start_stage) if start_stage else 0
    ei = _STAGES.index(stop_stage) if stop_stage else len(_STAGES) - 1
    if si > ei:
        raise ValueError(f"start_stage {start_stage!r} is after stop_stage {stop_stage!r}")
    return {s for i, s in enumerate(_STAGES) if si <= i <= ei}


def load_research() -> tuple[dict, str]:
    """Load Agent 1's outputs (monkeypatched in tests)."""
    out = Path(settings.paths.output)
    report_path = out / "market_research_report.json"
    md_path = out / "brand_intelligence_report.md"
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
    md = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
    return report, md


def _digest(stage: str, result) -> dict:
    """Compact gate card per stage."""
    if stage == "qualify":
        return {"priority_avatars": result.get("priority_avatars", []),
                "candidates": len(result.get("candidates", []) or [])}
    if stage == "discovery":
        return {"reddit_clusters": len((result.get("reddit") or {}).get("clusters", []) or []),
                "fb_ads": (result.get("fb") or {}).get("active_ads_found", 0)}
    if stage == "voc":
        return {"coded_quotes": len(result.get("coded_quotes", []) or [])}
    if stage == "synthesis":
        dd, md = result
        return {"avatars": len(dd.get("avatars", []) or []), "md_chars": len(md)}
    if isinstance(result, dict):
        return {"keys": sorted(result.keys())}
    return {}


async def run_avatar_builder(
    brief: dict | None = None,
    *,
    start_stage: str | None = None,
    stop_stage: str | None = None,
    gate=checkpoint,
):
    """Run the 9-stage avatar workflow with a QC gate at every boundary.

    Returns the output paths dict, or None if the user quit / stopped early.
    """
    brief = dict(brief) if brief else dict(SHOP_BRIEF)
    active = _active(start_stage, stop_stage)
    reporter = get_reporter()
    research_report, _brand_md = load_research()
    st: dict = {}   # accumulated stage results (run or loaded from disk)

    async def stage(name: str, runner, *, loader):
        """Run a gated stage if active, else load its output from disk.
        Returns (result, control) where control is 'quit' or None."""
        nonlocal brief
        if name not in active:
            return loader(), None
        while True:
            reset_search_count()
            reporter.publish({"type": "stage", "workflow": "avatar", "stage": name})
            result = await runner()
            res = await gate(name, _digest(name, result), workflow="avatar", request=brief)
            if res.decision is Decision.QUIT:
                return result, "quit"
            if res.decision is Decision.EDIT:
                brief = res.request or brief
                continue
            return result, None

    with reporter.workflow_context("avatar"):
        # Stage 0 — onboarding
        st["onboarding"], ctl = await stage(
            "onboarding", lambda: run_onboarding(brief),
            loader=lambda: load_json("avatar_onboarding.json"))
        if ctl == "quit":
            return None

        # Stage 1 — product
        st["product"], ctl = await stage(
            "product", lambda: run_product(brief),
            loader=lambda: load_json("avatar_product.json"))
        if ctl == "quit":
            return None

        # Stage 2a — discovery
        st["discovery"], ctl = await stage(
            "discovery", lambda: run_discovery(brief),
            loader=lambda: {"reddit": load_json("avatar_discovery_reddit.json"),
                            "amazon": load_json("avatar_discovery_amazon.json"),
                            "fb": load_json("avatar_discovery_fb.json")})
        if ctl == "quit":
            return None

        # Stage 2b — qualify (key human gate)
        st["qualification"], ctl = await stage(
            "qualify", lambda: run_qualify(st["discovery"], research_report, brief),
            loader=lambda: load_json("avatar_qualification.json"))
        if ctl == "quit":
            return None
        priority = st["qualification"].get("priority_avatars", [])

        # Stage 3 — voc
        st["voc"], ctl = await stage(
            "voc", lambda: run_voc(priority, st["discovery"], brief),
            loader=lambda: load_json("avatar_voc.json"))
        if ctl == "quit":
            return None

        # Stage 4 — awareness
        st["awareness"], ctl = await stage(
            "awareness", lambda: run_awareness(st["voc"], research_report, priority, brief),
            loader=lambda: load_json("avatar_awareness.json"))
        if ctl == "quit":
            return None

        # Stage 5 — competitor
        st["competitor"], ctl = await stage(
            "competitor", lambda: run_competitor(st["voc"], research_report, brief),
            loader=lambda: load_json("avatar_competitor.json"))
        if ctl == "quit":
            return None

        # Stage 6 — mechanism
        st["mechanism"], ctl = await stage(
            "mechanism", lambda: run_mechanism(st["voc"], research_report, brief),
            loader=lambda: load_json("avatar_mechanism.json"))
        if ctl == "quit":
            return None

        if "synthesis" not in active:
            log.info("avatar: stopping before synthesis (stop_stage)")
            return None

        # Stage 7 — synthesis
        result, ctl = await stage(
            "synthesis", lambda: run_synthesis(st, research_report, priority, brief),
            loader=lambda: (load_json("avatar_deep_dive.json"), ""))
        if ctl == "quit":
            return None

    out = Path(settings.paths.output)
    log.info("avatar workflow done -> customer_avatars.md + avatar_deep_dive.json")
    return {"customer_avatars": out / "customer_avatars.md",
            "avatar_deep_dive": out / "avatar_deep_dive.json"}


def _prompt_catalog() -> list[dict]:
    from embroidery.agents.avatar import discovery, framing, reframe, synthesizer, voc
    return (framing.prompt_catalog() + discovery.prompt_catalog() + voc.prompt_catalog()
            + reframe.prompt_catalog() + synthesizer.prompt_catalog())


# Register in the team registry (import-time, idempotent).
from embroidery.core.workflow import Stage, WorkflowSpec, register   # noqa: E402

register(WorkflowSpec(
    id="avatar",
    label="Avatar Builder",
    stages=[
        Stage("onboarding", ["avatar_onboarder"]),
        Stage("product", ["product_analyst"]),
        Stage("discovery", ["reddit_scout", "amazon_voc", "fb_ad_scout"]),
        Stage("qualify", ["avatar_qualifier"]),
        Stage("voc", ["voc_miner"]),
        Stage("awareness", ["awareness_mapper"]),
        Stage("competitor", ["competitor_teardown"]),
        Stage("mechanism", ["mechanism_builder"]),
        Stage("synthesis", ["avatar_synthesizer", "avatar_synthesizer_md"]),
    ],
    entry_point=run_avatar_builder,
    prompt_catalog=_prompt_catalog,
    inputs=["market_research_report.json", "brand_intelligence_report.md"],
    outputs=["customer_avatars.md", "avatar_deep_dive.json"],
    fixtures=["market_research_report.json", "brand_intelligence_report.md"],
    config_schema={
        "priority_count": settings.avatar.priority_count,
        "avatar_synthesizer": {"model": settings.agents.avatar_synthesizer.model},
    },
))


if __name__ == "__main__":
    if "--yes" in sys.argv:
        os.environ["EMBROIDERY_YES"] = "1"
    paths = asyncio.run(run_avatar_builder())
    if not paths:
        print("Avatar pipeline stopped (quit or stop-stage).")
    else:
        for name, path in paths.items():
            size = path.stat().st_size if path.exists() else 0
            print(f"{name}: {path} ({size:,} bytes)")
