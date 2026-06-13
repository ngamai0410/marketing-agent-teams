"""
Agent 1: Market Research — the full mini-pipeline (Day 4 wiring).

    brief → asyncio.gather(A, B, C) → [QC gate] → Synthesizer → [QC gate] → output files + BrandAI

Research is done by three parallel search-only sub-agents (subagents.py) whose
JSON outputs are merged by a no-tool Synthesizer (synthesizer.py). Between
stages the pipeline pauses at a human-in-the-loop checkpoint (core/checkpoint.py)
so the end user can Approve, Edit the brief & re-run, or Quit — driven from the
web dashboard (embroidery/web/). Standalone runs auto-approve every gate.

Produces the two Stage 1 data-contract files consumed by Agents 2 and 3:

  output/market_research_report.json
  output/brand_intelligence_report.md

plus a timestamped history snapshot in brand_ai/embroidery_shop/ and a
per-run performance digest in output/run_report.md.

Run (standalone, auto-approves gates):
    cd embroidery && venv/bin/python -m embroidery.agents.research.pipeline [--yes]

Run (with live dashboard + interactive gates):
    cd embroidery && venv/bin/python -m embroidery.web
"""

import asyncio
import json
import os
import sys
from pathlib import Path

from embroidery.agents.research.subagents import SHOP_BRIEF, run_subagent
from embroidery.agents.research.synthesizer import run_synthesizer
from embroidery.core.agent_loop import reset_search_count
from embroidery.core.brand_store import BrandAI
from embroidery.core.checkpoint import Decision, checkpoint
from embroidery.core.config import settings
from embroidery.core.logger import get_logger
from embroidery.core.reporter import get_reporter

log = get_logger(__name__)

SHOP_SLUG = "embroidery_shop"   # brand_ai/ subdirectory for this shop


# ─────────────────────────────────────────────
# QC digests — compact, JSON-able summaries the dashboard renders at each gate
# ─────────────────────────────────────────────

def _research_digest(a: dict, b: dict, c: dict) -> dict:
    def counts(d: dict) -> dict:
        return {
            "desires": len(d.get("desires", []) or []),
            "problems": len(d.get("problems", []) or []),
            "hooks": len(d.get("hooks", []) or []),
            "objections": len(d.get("objections", []) or []),
            "empty_sections": [k for k, v in d.items() if isinstance(v, list) and not v],
        }
    return {
        "audience (A)": counts(a),
        "competitor (B)": counts(b),
        "social (C)": counts(c),
    }


def _synth_digest(report: dict, markdown: str) -> dict:
    soph = report.get("market_sophistication", {})
    preview = "\n".join(markdown.splitlines()[:15])
    return {
        "report_sections": len(report),
        "desires": len(report.get("desires", []) or []),
        "problems": len(report.get("problems", []) or []),
        "hooks": len(report.get("hooks", []) or []),
        "sophistication_stage": soph.get("stage") if isinstance(soph, dict) else soph,
        "coverage_gaps": report.get("coverage_gaps", []) or [],
        "markdown_chars": len(markdown),
        "markdown_preview": preview,
    }


# stage names (also the WorkflowSpec.stages names)
STAGE_SUBAGENTS = "sub-agents A/B/C"
STAGE_SYNTH = "synthesis"
_STAGES = [STAGE_SUBAGENTS, STAGE_SYNTH]


def _active(start_stage: str | None, stop_stage: str | None) -> set[str]:
    si = _STAGES.index(start_stage) if start_stage else 0
    ei = _STAGES.index(stop_stage) if stop_stage else len(_STAGES) - 1
    return {s for i, s in enumerate(_STAGES) if si <= i <= ei}


async def run_market_research(
    brief: dict | None = None,
    *,
    start_stage: str | None = None,
    stop_stage: str | None = None,
    gate=checkpoint,
) -> dict[str, Path] | None:
    """Run the Agent 1 research workflow with QC gates between stages.

    start_stage/stop_stage slice the workflow for the Test pillar. Skipped
    upstream stages expect their outputs already on disk (a prior run or a
    seeded fixture). Returns the output paths, or None if the user quit.
    """
    brief = dict(brief) if brief else dict(SHOP_BRIEF)
    active = _active(start_stage, stop_stage)
    reporter = get_reporter()

    research_a = research_b = research_c = None
    with reporter.workflow_context("research"):
        # ---- Stage: sub-agents A/B/C (gated) ----
        if STAGE_SUBAGENTS in active:
            while True:
                reset_search_count()
                reporter.publish({"type": "stage", "workflow": "research", "stage": STAGE_SUBAGENTS})
                log.info("research: dispatching sub-agents A/B/C")
                research_a, research_b, research_c = await asyncio.gather(
                    run_subagent("a", brief, reset_searches=False),
                    run_subagent("b", brief, reset_searches=False),
                    run_subagent("c", brief, reset_searches=False),
                )
                res = await gate(STAGE_SUBAGENTS, _research_digest(research_a, research_b, research_c),
                                 workflow="research", request=brief)
                if res.decision is Decision.QUIT:
                    return None
                if res.decision is Decision.EDIT:
                    brief = res.request or brief
                    continue
                break
        else:
            research_a, research_b, research_c = synth_module_static()

        if STAGE_SYNTH not in active:
            log.info("research: stopping after %s (stop_stage)", STAGE_SUBAGENTS)
            return None

        # ---- Stage: synthesis (gated; Edit re-runs A/B/C if that stage is active) ----
        while True:
            reporter.publish({"type": "stage", "workflow": "research", "stage": STAGE_SYNTH})
            report, markdown = await run_synthesizer(research_a, research_b, research_c, brief)
            res = await gate(STAGE_SYNTH, _synth_digest(report, markdown),
                             workflow="research", request=brief)
            if res.decision is Decision.QUIT:
                return None
            if res.decision is Decision.EDIT and STAGE_SUBAGENTS in active:
                brief = res.request or brief
                reset_search_count()
                research_a, research_b, research_c = await asyncio.gather(
                    run_subagent("a", brief, reset_searches=False),
                    run_subagent("b", brief, reset_searches=False),
                    run_subagent("c", brief, reset_searches=False),
                )
                continue
            if res.decision is Decision.EDIT:
                brief = res.request or brief
                continue
            break

    # ---- Persist this workflow's data-contract outputs ----
    out = Path(settings.paths.output)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "market_research_report.json"
    md_path = out / "brand_intelligence_report.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")
    BrandAI(SHOP_SLUG).save_research(report, markdown)
    log.info("research workflow done json=%s md=%s", json_path, md_path)
    return {"market_research_report": json_path, "brand_intelligence_report": md_path}


def synth_module_static() -> tuple[dict, dict, dict]:
    """Load the saved A/B/C outputs from output/ (seeded fixture or prior run)."""
    from embroidery.agents.research.synthesizer import _load_static_research
    return _load_static_research()


def _prompt_catalog() -> list[dict]:
    from embroidery.agents.research import subagents, synthesizer
    return subagents.prompt_catalog() + synthesizer.prompt_catalog()


# Register this workflow in the team registry (import-time, idempotent).
from embroidery.core.workflow import Stage, WorkflowSpec, register   # noqa: E402

register(WorkflowSpec(
    id="research",
    label="Research",
    stages=[
        Stage(STAGE_SUBAGENTS, ["audience_researcher", "competitor_analyst", "social_media_analyst"]),
        Stage(STAGE_SYNTH, ["synthesizer_json", "synthesizer_md"]),
    ],
    entry_point=run_market_research,
    prompt_catalog=_prompt_catalog,
    inputs=[],
    outputs=["market_research_report.json", "brand_intelligence_report.md"],
    fixtures=[],
    config_schema={
        "audience_researcher": {"model": settings.agents.audience_researcher.model},
        "synthesizer": {"model": settings.agents.synthesizer.model},
    },
))


if __name__ == "__main__":
    if "--yes" in sys.argv:
        os.environ["EMBROIDERY_YES"] = "1"
    paths = asyncio.run(run_market_research())
    if not paths:
        print("Pipeline stopped (quit or stop-stage).")
    else:
        for name, path in paths.items():
            size = path.stat().st_size if path.exists() else 0
            print(f"{name}: {path} ({size:,} bytes)")
