"""
WorkflowSpec registry — the single source of truth for the agent team.

Each campaign workflow (research, copy, qa, feedback) registers ONE WorkflowSpec
describing its shape: its ordered stages (each naming the agents it runs), an
async entry point that supports start/stop-stage slicing, its editable prompt
catalog, and its data-contract inputs/outputs/fixtures. The web layer
(embroidery/web/) and the orchestrator (core/orchestrator.py) are fully generic:
they iterate this registry and gain no per-workflow code. Adding a workflow =
write its pipeline module + call register(...) at import — nothing else.

load_workflows() imports the workflow modules in canonical team order so the
registry is populated deterministically regardless of who triggers it first.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from embroidery.core.logger import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class Stage:
    name: str                 # short stage label, e.g. "sub-agents A/B/C"
    agents: list[str]         # agent_name values this stage runs (maps rows -> lane stage)
    digest: Callable[..., dict] | None = None   # builds this stage's gate-card digest


@dataclass(frozen=True)
class WorkflowSpec:
    id: str                                       # "research", "copy", "qa", "feedback"
    label: str                                    # "Research"
    stages: list[Stage]
    entry_point: Callable[..., Awaitable[Any]]    # async run(brief, *, start_stage, stop_stage, gate)
    prompt_catalog: Callable[[], list[dict]] = lambda: []
    inputs: list[str] = field(default_factory=list)    # data-contract files read (under data/output)
    outputs: list[str] = field(default_factory=list)   # data-contract files written
    fixtures: list[str] = field(default_factory=list)  # committed samples (under fixtures/) that seed inputs
    config_schema: dict = field(default_factory=dict)

    def stage_names(self) -> list[str]:
        return [s.name for s in self.stages]


_REGISTRY: dict[str, WorkflowSpec] = {}


def register(spec: WorkflowSpec) -> None:
    """Add or replace a spec by id. Idempotent — safe on module re-import."""
    _REGISTRY[spec.id] = spec
    log.debug("workflow registered id=%s stages=%d", spec.id, len(spec.stages))


def get_registry() -> list[WorkflowSpec]:
    """All specs in registration (canonical team) order."""
    return list(_REGISTRY.values())


def get_spec(spec_id: str) -> WorkflowSpec:
    return _REGISTRY[spec_id]


def clear_registry() -> None:
    """Test helper — drop all registered specs."""
    _REGISTRY.clear()


def load_workflows() -> list[WorkflowSpec]:
    """Import every workflow module in canonical order so each registers itself.

    Lazy + tolerant: a workflow whose agents aren't built yet simply isn't
    imported. The web layer / orchestrator call this once at startup.
    """
    import importlib
    for module in (
        "embroidery.agents.research.pipeline",
        "embroidery.agents.qa.pipeline",
    ):
        try:
            importlib.import_module(module)
        except ImportError as exc:           # workflow not built yet — skip
            log.debug("workflow module not loadable (%s): %s", module, exc)
    return get_registry()
