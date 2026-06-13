"""
Human-in-the-loop checkpoint — the QC gate a stage calls between hand-offs.

A stage calls `await checkpoint(stage, digest, request=brief)`; this publishes a
`gate` event (the web dashboard renders it as an Approve / Edit / Quit card) and
blocks until the user resolves it via POST /gate. The decision (and any edited
`request`) flows back so the pipeline can re-run a stage with adjustments.

Headless guard: if EMBROIDERY_YES=1 or nobody is watching the dashboard (no SSE
subscriber), the gate auto-approves immediately and logs it — so standalone runs
(`python -m embroidery.agents.research.pipeline`) and tests never block.

This module is UI-agnostic: it only knows about the reporter's event bus and a
pending-gate registry. embroidery/web/server.py resolves gates by gate_id.
"""

import asyncio
import os
from dataclasses import dataclass
from enum import Enum

from embroidery.core.logger import get_logger
from embroidery.core.reporter import get_reporter

log = get_logger(__name__)


class Decision(str, Enum):
    APPROVE = "approve"
    EDIT = "edit"
    QUIT = "quit"


@dataclass
class CheckpointResult:
    decision: Decision
    request: dict | None = None


@dataclass
class _PendingGate:
    gate_id: str
    stage: str
    workflow: str
    digest: dict
    request: dict | None
    future: asyncio.Future


# gate_id -> pending gate, resolved by the web layer (POST /gate)
_pending: dict[str, _PendingGate] = {}
_counter = 0


def open_gates() -> list[dict]:
    """Gates currently awaiting a decision — replayed to late-joining clients."""
    return [
        {"type": "gate", "gate_id": g.gate_id, "stage": g.stage,
         "workflow": g.workflow, "digest": g.digest, "request": g.request}
        for g in _pending.values()
    ]


def resolve_gate(gate_id: str, decision: str, request: dict | None = None) -> bool:
    """Called by the web layer when the user clicks a gate button.

    Returns True if a matching pending gate was resolved.
    """
    gate = _pending.pop(gate_id, None)
    if gate is None or gate.future.done():
        return False
    gate.future.set_result(CheckpointResult(Decision(decision), request))
    return True


def _auto_approve() -> bool:
    return os.getenv("EMBROIDERY_YES") == "1" or not get_reporter().has_subscribers


async def checkpoint(stage: str, digest: dict, *, workflow: str = "",
                     request: dict | None = None) -> CheckpointResult:
    """Pause the pipeline for human QC. See module docstring."""
    global _counter

    if _auto_approve():
        log.info("checkpoint=%s auto-approved (no dashboard / EMBROIDERY_YES)", stage)
        return CheckpointResult(Decision.APPROVE, request)

    _counter += 1
    gate_id = f"gate-{_counter}"
    loop = asyncio.get_running_loop()
    future: asyncio.Future = loop.create_future()
    _pending[gate_id] = _PendingGate(gate_id, stage, workflow, digest, request, future)

    log.info("checkpoint=%s gate_id=%s workflow=%s awaiting user decision", stage, gate_id, workflow)
    get_reporter().publish({
        "type": "gate", "gate_id": gate_id, "stage": stage,
        "workflow": workflow, "digest": digest, "request": request,
    })

    try:
        result = await future
    finally:
        _pending.pop(gate_id, None)

    log.info("checkpoint=%s gate_id=%s decision=%s", stage, gate_id, result.decision.value)
    get_reporter().publish({"type": "gate_closed", "gate_id": gate_id})
    return result
