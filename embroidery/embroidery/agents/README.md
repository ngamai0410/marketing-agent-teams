# embroidery/agents/ — campaign agents, grouped by workflow

One subpackage per workflow stage from `../../../CLAUDE.md`. Agent numbers live in docs and
`config.yaml`, not in filenames (role-based naming). **Each subpackage has its own README**
with that workflow's full data contracts, models, run commands, and chart:

- [`research/README.md`](research/README.md) — Workflow 1: Market Research (Agent 1)
- [`avatar/README.md`](avatar/README.md) — Workflow 2: Avatar Builder (Agent 2, 9 Evolve stages)
- `copy/README.md` — Workflow 3: Copy (Agents 4–6) *(future)*
- [`qa/README.md`](qa/README.md) — Workflow 4: QA & Feedback (Agents 7–8)

```
research/   Workflow 1 — Market Research
  pipeline.py     Agent 1 entry: gather(A,B,C) → Synthesizer → reports + BrandAI snapshot
                  Registers WorkflowSpec(id="research") at import.
  subagents.py    Agent 1 sub-agents A/B/C (search-only; return JSON as text). Holds SHOP_BRIEF.
  synthesizer.py  Agent 1 Synthesizer (no tools; merges A/B/C → master JSON + markdown)

avatar/     Workflow 2 — Avatar Builder (Agent 2, 9 Evolve stages)
  pipeline.py     Avatar workflow entry: 9-stage gated orchestration; registers WorkflowSpec(id="avatar") at import.
                  Reads: market_research_report.json + brand_intelligence_report.md
                  Writes: customer_avatars.md + avatar_deep_dive.json  (read by Agents 3–6)
  _common.py      AvatarAgent + run_json_agent + prompt-catalog helpers (shared by every stage)
  framing.py      Stage 0 onboarder + Stage 1 product analyst
  discovery.py    Stage 2 parallel scouts (Reddit/Amazon/FB) + 4-gate qualifier
  voc.py          Stage 3 voice-of-customer miner
  reframe.py      Stages 4/5/6 reframers (awareness / competitor / mechanism), no tools
  synthesizer.py  Stage 7 synthesizer — writes customer_avatars.md + avatar_deep_dive.json

copy/       Workflow 3 — Copy  [future]
  (hooks.py, scripts.py, static_copy.py = Agents 4,5,6)

qa/         Workflow 4 — QA & Feedback
  pipeline.py     QA workflow entry: run_qa → QC gate; registers WorkflowSpec(id="qa") at import.
  qa_reviewer.py  Agent 7: 8-question diagnostic + psychology checklist → qa_report.json (gatekeeper)
                  Renders its system prompt via prompt_store (editable from the dashboard).
  (feedback.py = Agent 8 — future)
```

Data contracts (who writes/reads which file in `data/output/`) are tabulated in `../../../CLAUDE.md`.
Every agent calls `run_agent(..., agent_name="<key>")` from `embroidery.core.agent_loop`, using
the model assigned to its key under `agents:` in `config.yaml`.

## Registering a workflow — the contract

Each workflow module (`<workflow>/pipeline.py`) must:

1. Expose an **async entry point** with the exact signature:
   ```python
   async def run_<workflow>(brief: dict | None = None, *, start_stage=None, stop_stage=None, gate=checkpoint) -> dict | None:
       ...
   ```
   Returns a result dict on success, `None` if the user quit or the pipeline was stopped at a stage.

2. Expose a **`prompt_catalog()`** function returning a `list[dict]` — the same shape as
   `research/pipeline.py._prompt_catalog()`. Each item has `id`, `name`, `stage`,
   `placeholders`, `default`, `text`, `overridden`.

3. Call `register(WorkflowSpec(...))` at import (idempotent — safe on module re-import):
   ```python
   from embroidery.core.workflow import Stage, WorkflowSpec, register
   register(WorkflowSpec(
       id="copy",
       label="Copy",
       stages=[Stage("hooks", ["hook_generator"]), ...],
       entry_point=run_copy,
       prompt_catalog=prompt_catalog,
       inputs=["positioning_matrix.json", "customer_avatars.md"],  # data-contract guard
       outputs=["hooks_library.json", "video_scripts.json", "static_ad_copy.json"],
       fixtures=["positioning_matrix.json", "customer_avatars.md"],
   ))
   ```

4. Add the module path to the `load_workflows()` import list in `core/workflow.py` so the
   web layer and orchestrator pick it up automatically.

The web dashboard and `run_team` (orchestrator) are fully generic — adding a workflow
module is the only change required.

## Monitoring + QC pattern (adopt in every workflow)

`run_agent()` emits live metrics to `core/reporter.py` automatically — no per-agent wiring
needed. To make a workflow QC-able from the dashboard (`embroidery/web/`), a pipeline calls
`await checkpoint(stage, digest, workflow=<id>, request=...)` (`core/checkpoint.py`) between
hand-offs and branches on the returned `Decision` (APPROVE → continue, EDIT → re-run with
the adjusted request, QUIT → abort). Wrap the whole workflow body in
`with reporter.workflow_context(<id>)` so agent rows are tagged to their lane.
`research/pipeline.py` is the reference implementation. Gates auto-approve when run headless.
