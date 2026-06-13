"""
Run reporter — live performance metrics for every agent in a pipeline run.

The agent loop already computes per-agent calls / token usage / search counts;
this module taps those points (see core/agent_loop.py) into one place so a
front-end (the web dashboard in embroidery/web/) can stream them live, and so
every run leaves a persisted digest at data/output/run_report.md.

Two roles:
  1. State accumulator  — AgentRecord per agent_name (calls, tokens, $, elapsed).
  2. Async pub/sub bus   — subscribers (SSE connections) receive snapshot/stage/
                            gate/done events as they happen.

When nothing subscribes (standalone CLI runs, tests) the reporter is purely a
state accumulator — _publish() is a cheap no-op, so importing this has zero
behavioural effect on existing code paths.

Usage:
    from embroidery.core.reporter import get_reporter
    r = get_reporter()
    r.reset()
    r.agent_start("audience_researcher", "gemini-2.5-flash", 16000)
    ...
    md = r.render_markdown()          # -> write to data/output/run_report.md
    q = r.subscribe()                 # SSE: await q.get() in a loop
"""

import asyncio
import contextlib
import contextvars
import time
from dataclasses import dataclass, field

from embroidery.core.logger import get_logger

log = get_logger(__name__)


# ─────────────────────────────────────────────
# Pricing — the single source of cost truth.
# (in $/1M tokens, out $/1M tokens). Edit here if provider pricing changes.
# Unlisted models -> cost is None (tokens still tracked/shown).
# ─────────────────────────────────────────────
PRICES: dict[str, tuple[float, float]] = {
    # Anthropic (from CLAUDE.md model-allocation table)
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-8": (5.0, 25.0),
    # Google Gemini (best-effort public list pricing for the ≤200k context tier)
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-pro": (1.25, 10.0),
}


def _cost(model: str, in_tok: int, out_tok: int) -> float | None:
    price = PRICES.get(model)
    if price is None:
        return None
    in_per_m, out_per_m = price
    return in_tok / 1_000_000 * in_per_m + out_tok / 1_000_000 * out_per_m


# The workflow whose agents are currently running — set via
# RunReporter.workflow_context() so each AgentRecord knows its lane without
# threading a parameter through every run_agent() call site.
_current_workflow: contextvars.ContextVar[str] = contextvars.ContextVar("workflow", default="")


@dataclass
class AgentRecord:
    name: str
    workflow: str = ""
    model: str = ""
    status: str = "running"          # running | done
    calls: int = 0
    in_tokens: int = 0
    out_tokens: int = 0
    searches: int = 0
    t_start: float = field(default_factory=time.monotonic)
    t_end: float | None = None
    steps: list = field(default_factory=list)

    @property
    def elapsed(self) -> float:
        return (self.t_end if self.t_end is not None else time.monotonic()) - self.t_start

    @property
    def cost_usd(self) -> float | None:
        return _cost(self.model, self.in_tokens, self.out_tokens)

    def as_row(self) -> dict:
        return {
            "workflow": self.workflow,
            "name": self.name,
            "model": self.model,
            "status": self.status,
            "calls": self.calls,
            "in_tokens": self.in_tokens,
            "out_tokens": self.out_tokens,
            "searches": self.searches,
            "cost_usd": self.cost_usd,
            "elapsed_s": round(self.elapsed, 1),
            "steps": self.steps,
        }


class RunReporter:
    """Singleton accumulator + async event bus for one pipeline run."""

    def __init__(self) -> None:
        self._agents: dict[str, AgentRecord] = {}
        self._subscribers: set[asyncio.Queue] = set()
        self.run_id: int = 0

    # ---- lifecycle -------------------------------------------------

    def reset(self) -> None:
        """Clear all agent records and start a fresh run."""
        self._agents.clear()
        self.run_id += 1

    @contextlib.contextmanager
    def workflow_context(self, workflow_id: str):
        """Within this block, agent_start() tags rows with workflow_id."""
        token = _current_workflow.set(workflow_id)
        try:
            yield
        finally:
            _current_workflow.reset(token)

    # ---- pub/sub ---------------------------------------------------

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    @property
    def has_subscribers(self) -> bool:
        return bool(self._subscribers)

    def publish(self, event: dict) -> None:
        """Fan an event out to every subscriber. No-op when nobody listens.

        Subscriber queues are unbounded, so put_nowait never blocks; a dead
        queue (shouldn't happen) is simply skipped.
        """
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:  # pragma: no cover - unbounded queues
                pass

    def _publish_agents(self) -> None:
        if self._subscribers:
            self.publish(self.snapshot())

    # ---- emit points (called from agent_loop.py) ------------------

    def agent_start(self, name: str, model: str, max_tokens: int) -> None:
        wf = _current_workflow.get()
        rec = self._agents.get(name)
        if rec is None:
            rec = AgentRecord(name=name, workflow=wf, model=model)
            self._agents[name] = rec
        else:  # re-run of the same agent within a run — reset its counters
            rec.workflow = wf
            rec.model = model
            rec.status = "running"
            rec.calls = rec.in_tokens = rec.out_tokens = rec.searches = 0
            rec.steps = []
            rec.t_start = time.monotonic()
            rec.t_end = None
        self._publish_agents()

    def agent_call(self, name: str, in_tok: int, out_tok: int) -> None:
        rec = self._agents.get(name) or self._ensure(name)
        rec.calls += 1
        rec.in_tokens += in_tok
        rec.out_tokens += out_tok
        rec.steps.append({
            "seq": len(rec.steps) + 1, "type": "call",
            "label": f"LLM call #{rec.calls}",
            "in_tok": in_tok, "out_tok": out_tok,
            "cost_usd": _cost(rec.model, in_tok, out_tok),
            "elapsed_s": round(rec.elapsed, 1),
        })
        self._publish_agents()

    def agent_search(self, name: str, query: str, results: int | None = None) -> None:
        rec = self._agents.get(name) or self._ensure(name)
        rec.searches += 1
        rec.steps.append({
            "seq": len(rec.steps) + 1, "type": "search",
            "label": query, "results": results,
            "elapsed_s": round(rec.elapsed, 1),
        })
        self._publish_agents()

    def agent_write(self, name: str, file: str) -> None:
        rec = self._agents.get(name) or self._ensure(name)
        rec.steps.append({
            "seq": len(rec.steps) + 1, "type": "write",
            "label": file, "output_file": file,
            "elapsed_s": round(rec.elapsed, 1),
        })
        self._publish_agents()

    def agent_fetch(self, name: str, url: str) -> None:
        rec = self._agents.get(name) or self._ensure(name)
        rec.steps.append({
            "seq": len(rec.steps) + 1, "type": "fetch",
            "label": url, "elapsed_s": round(rec.elapsed, 1),
        })
        self._publish_agents()

    def agent_output(self, name: str, file: str) -> None:
        rec = self._agents.get(name) or self._ensure(name)
        rec.steps.append({
            "seq": len(rec.steps) + 1, "type": "output",
            "label": file, "output_file": file,
            "elapsed_s": round(rec.elapsed, 1),
        })
        self._publish_agents()

    def agent_done(self, name: str) -> None:
        rec = self._agents.get(name) or self._ensure(name)
        rec.status = "done"
        rec.t_end = time.monotonic()
        self._publish_agents()

    def _ensure(self, name: str) -> AgentRecord:
        rec = AgentRecord(name=name)
        self._agents[name] = rec
        return rec

    # ---- views -----------------------------------------------------

    def snapshot(self) -> dict:
        rows = [rec.as_row() for rec in self._agents.values()]
        return {"type": "agents", "rows": rows, "totals": self._totals(rows)}

    def _totals(self, rows: list[dict]) -> dict:
        total_in = sum(r["in_tokens"] for r in rows)
        total_out = sum(r["out_tokens"] for r in rows)
        costs = [r["cost_usd"] for r in rows if r["cost_usd"] is not None]
        total_cost = round(sum(costs), 4) if costs else None
        if self._agents:
            start = min(r.t_start for r in self._agents.values())
            end = max(
                (r.t_end if r.t_end is not None else time.monotonic())
                for r in self._agents.values()
            )
            wall = round(end - start, 1)
        else:
            wall = 0.0
        return {
            "calls": sum(r["calls"] for r in rows),
            "in_tokens": total_in,
            "out_tokens": total_out,
            "cost_usd": total_cost,
            "elapsed_s": wall,
        }

    def render_markdown(self) -> str:
        """A persisted digest table — written to data/output/run_report.md."""
        rows = [rec.as_row() for rec in self._agents.values()]
        totals = self._totals(rows)

        def money(v) -> str:
            return f"${v:.4f}" if v is not None else "—"

        lines = [
            "# Run report",
            "",
            "| Agent | Model | Status | Calls | In | Out | Searches | Cost | Elapsed |",
            "|---|---|---|--:|--:|--:|--:|--:|--:|",
        ]
        for r in rows:
            lines.append(
                f"| {r['name']} | {r['model']} | {r['status']} | {r['calls']} | "
                f"{r['in_tokens']:,} | {r['out_tokens']:,} | {r['searches']} | "
                f"{money(r['cost_usd'])} | {r['elapsed_s']}s |"
            )
        lines.append(
            f"| **Total** | | | {totals['calls']} | {totals['in_tokens']:,} | "
            f"{totals['out_tokens']:,} | | {money(totals['cost_usd'])} | "
            f"{totals['elapsed_s']}s |"
        )
        lines.append("")
        return "\n".join(lines)


# Module-level singleton — import get_reporter() everywhere.
_reporter: RunReporter | None = None


def get_reporter() -> RunReporter:
    global _reporter
    if _reporter is None:
        _reporter = RunReporter()
    return _reporter
