"""
FastAPI app behind the local monitoring dashboard.

Endpoints
  GET  /              -> the single-page dashboard (static/index.html)
  GET  /events        -> Server-Sent Events stream of reporter + gate events
  POST /start         -> kick off the research pipeline (idempotent)
  POST /gate          -> resolve a pending QC gate (Approve / Edit / Quit)
  GET  /report        -> data/output/run_report.md (raw markdown)
  GET  /output/{file} -> a whitelisted output artifact for inspection during QC

Everything runs in one asyncio loop: uvicorn serves while run_market_research()
runs as a task. The reporter (core/reporter.py) is the pub/sub bus; gates
(core/checkpoint.py) are resolved by gate_id from POST /gate.
"""

import asyncio
import json
import shutil
import string
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel

from embroidery.core.checkpoint import open_gates, resolve_gate
from embroidery.core.config import settings
from embroidery.core.logger import get_logger
from embroidery.core.prompt_store import get_prompt_store
from embroidery.core.reporter import get_reporter
from embroidery.agents.research.subagents import SHOP_BRIEF, shop_context
from embroidery.core.workflow import get_registry, load_workflows

# Populate the workflow registry once at import (lazy per-module imports inside).
load_workflows()

log = get_logger(__name__)

app = FastAPI(title="Embroidery agent monitor")

_STATIC = Path(__file__).parent / "static"

# Single in-flight pipeline run per server process.
_run_task: asyncio.Task | None = None


def _run_in_progress() -> bool:
    return _run_task is not None and not _run_task.done()


def _prompt_catalog() -> list[dict]:
    items: list[dict] = []
    for spec in get_registry():
        items.extend(spec.prompt_catalog())
    return items


# ─────────────────────────────────────────────
# Page
# ─────────────────────────────────────────────

@app.get("/")
async def index() -> FileResponse:
    return FileResponse(_STATIC / "index.html")


# ─────────────────────────────────────────────
# Workflow registry
# ─────────────────────────────────────────────

@app.get("/workflows")
async def list_workflows():
    return {"workflows": [
        {
            "id": s.id,
            "label": s.label,
            "stages": [{"name": st.name, "agents": st.agents} for st in s.stages],
            "inputs": s.inputs,
            "outputs": s.outputs,
            "fixtures": s.fixtures,
            "config_schema": s.config_schema,
        }
        for s in get_registry()
    ]}


# ─────────────────────────────────────────────
# Live event stream (SSE)
# ─────────────────────────────────────────────

@app.get("/events")
async def events() -> StreamingResponse:
    reporter = get_reporter()

    async def stream():
        q = reporter.subscribe()
        try:
            # Replay current state + any gate awaiting a decision to late joiners.
            yield _sse(reporter.snapshot())
            for g in open_gates():
                yield _sse(g)
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=15)
                    yield _sse(event)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"   # keep-alive comment
        finally:
            reporter.unsubscribe(q)

    return StreamingResponse(stream(), media_type="text/event-stream")


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


# ─────────────────────────────────────────────
# Control
# ─────────────────────────────────────────────

class StartBody(BaseModel):
    brief: dict | None = None


@app.post("/start")
async def start(body: StartBody | None = None):
    global _run_task
    if _run_in_progress():
        raise HTTPException(409, "a run is already in progress")

    # Imported lazily so core/agents never import the web layer.
    from embroidery.agents.research.pipeline import run_market_research

    brief = body.brief if body else None
    _run_task = asyncio.create_task(_guarded_run(run_market_research, brief))
    return {"status": "started"}


async def _guarded_run(runner, brief):
    try:
        await runner(brief)
    except Exception as exc:  # surface crashes to the dashboard instead of dying silently
        log.exception("pipeline run failed")
        get_reporter().publish({"type": "done", "status": "error", "reason": str(exc)})


# ─────────────────────────────────────────────
# Prompts — view / edit / save each agent's system prompt before a run
# ─────────────────────────────────────────────

@app.get("/prompts")
async def list_prompts():
    return {"prompts": _prompt_catalog(), "editable": not _run_in_progress()}


class PromptBody(BaseModel):
    id: str
    text: str


@app.post("/prompts")
async def save_prompt(body: PromptBody):
    if _run_in_progress():
        raise HTTPException(409, "stop the current run before editing prompts")
    if body.id not in {p["id"] for p in _prompt_catalog()}:
        raise HTTPException(404, f"unknown prompt {body.id}")
    get_prompt_store().set(body.id, body.text)
    return {"status": "saved", "id": body.id}


class PromptResetBody(BaseModel):
    id: str


@app.post("/prompts/reset")
async def reset_prompt(body: PromptResetBody):
    if _run_in_progress():
        raise HTTPException(409, "stop the current run before editing prompts")
    get_prompt_store().reset(body.id)
    item = next((p for p in _prompt_catalog() if p["id"] == body.id), None)
    if item is None:
        raise HTTPException(404, f"unknown prompt {body.id}")
    return item


class GateBody(BaseModel):
    gate_id: str
    decision: str               # approve | edit | quit
    request: dict | None = None


@app.post("/gate")
async def gate(body: GateBody):
    if not resolve_gate(body.gate_id, body.decision, body.request):
        raise HTTPException(404, f"no pending gate {body.gate_id}")
    return {"status": "ok"}


# ─────────────────────────────────────────────
# Artifacts
# ─────────────────────────────────────────────

@app.get("/report")
async def report() -> PlainTextResponse:
    path = Path(settings.paths.output) / "run_report.md"
    if not path.exists():
        return PlainTextResponse("No run report yet.", status_code=404)
    return PlainTextResponse(path.read_text(encoding="utf-8"))


@app.get("/output/{filename}")
async def output_file(filename: str) -> FileResponse:
    # Whitelist: no path traversal, only .json/.md artifacts under data/output.
    if "/" in filename or ".." in filename or not filename.endswith((".json", ".md")):
        raise HTTPException(400, "invalid filename")
    path = Path(settings.paths.output) / filename
    if not path.exists():
        raise HTTPException(404, f"{filename} not found")
    return FileResponse(path)


# ─────────────────────────────────────────────
# Test pillar — artifacts, prompt preview, fixture seeding
# ─────────────────────────────────────────────

@app.get("/artifacts")
async def list_artifacts():
    out = Path(settings.paths.output)
    files = sorted(p.name for p in out.glob("*") if p.suffix in (".json", ".md")) if out.exists() else []
    return {"files": files}


class PreviewBody(BaseModel):
    id: str
    text: str | None = None     # if omitted, preview the currently-saved prompt

_SAMPLE_CTX = None

def _sample_ctx() -> dict:
    global _SAMPLE_CTX
    if _SAMPLE_CTX is None:
        _SAMPLE_CTX = {
            "shop_context": shop_context(SHOP_BRIEF),
            "shared_rules": "(shared research rules)",
            "research_date": "2026-06-13",
            "shop_name": SHOP_BRIEF["name"],
        }
    return _SAMPLE_CTX

@app.post("/prompts/preview")
async def preview_prompt(body: PreviewBody):
    item = next((p for p in _prompt_catalog() if p["id"] == body.id), None)
    if item is None:
        raise HTTPException(404, f"unknown prompt {body.id}")
    text = body.text if body.text is not None else item["text"]
    rendered = string.Template(text).safe_substitute(**_sample_ctx())
    return {"id": body.id, "rendered": rendered}


def _seed_fixtures(files: list[str]) -> list[str]:
    """Copy committed fixtures/<file> -> data/output/<file>. Returns copied names."""
    src_dir = Path(settings.paths.fixtures)
    out = Path(settings.paths.output)
    out.mkdir(parents=True, exist_ok=True)
    copied = []
    for name in files:
        if "/" in name or ".." in name:
            raise HTTPException(400, f"invalid fixture name {name}")
        src = src_dir / name
        if not src.exists():
            raise HTTPException(404, f"no fixture {name}")
        shutil.copy(src, out / name)
        copied.append(name)
    log.info("seeded fixtures into output: %s", copied)
    return copied
