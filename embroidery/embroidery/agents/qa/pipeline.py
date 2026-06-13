"""
QA workflow (Agent 7) wired onto the WorkflowSpec registry.

The reviewer itself lives in qa_reviewer.py; this module gives it a registry
spec, an editable prompt catalog, and a gated entry_point so the dashboard can
monitor/test/edit it like any other workflow.
"""

import json
from pathlib import Path

from embroidery.agents.qa.qa_reviewer import SYSTEM_PROMPT, run_qa_review
from embroidery.core.checkpoint import Decision, checkpoint
from embroidery.core.config import settings
from embroidery.core.logger import get_logger
from embroidery.core.prompt_store import get_prompt_store
from embroidery.core.reporter import get_reporter
from embroidery.core.workflow import Stage, WorkflowSpec, register

log = get_logger(__name__)

QA_STAGE = "qa review"


def _digest(report: dict) -> dict:
    ads = report.get("ads", [])
    return {
        "overall": report.get("overall"),
        "ads_reviewed": len(ads),
        "fails": [a.get("ad_id") for a in ads if a.get("revision_required")],
    }


async def run_qa(brief: dict | None = None, *, start_stage=None, stop_stage=None, gate=checkpoint) -> dict | None:
    """Run Agent 7 and pause at one QC gate. Returns {'qa_report': path} or None on quit."""
    reporter = get_reporter()
    reporter.publish({"type": "stage", "workflow": "qa", "stage": QA_STAGE})
    path = await run_qa_review()
    report = json.loads(Path(path).read_text(encoding="utf-8"))
    res = await gate(QA_STAGE, _digest(report), workflow="qa", request=brief)
    if res.decision is Decision.QUIT:
        return None
    return {"qa_report": path}


def prompt_catalog() -> list[dict]:
    store = get_prompt_store()
    return [{
        "id": "qa.reviewer",
        "name": "Agent 7 — QA Reviewer",
        "stage": "QA — review",
        "placeholders": [],
        "default": SYSTEM_PROMPT,
        "text": store.text("qa.reviewer", SYSTEM_PROMPT),
        "overridden": store.is_overridden("qa.reviewer"),
    }]


register(WorkflowSpec(
    id="qa",
    label="QA",
    stages=[Stage(QA_STAGE, ["qa_reviewer"])],
    entry_point=run_qa,
    prompt_catalog=prompt_catalog,
    inputs=["positioning_matrix.json", "video_scripts.json", "static_ad_copy.json"],
    outputs=["qa_report.json"],
    fixtures=["positioning_matrix.json", "video_scripts.json", "static_ad_copy.json"],
    config_schema={"qa_reviewer": {"model": settings.agents.qa_reviewer.model}},
))
