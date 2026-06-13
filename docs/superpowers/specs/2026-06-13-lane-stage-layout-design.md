# Lane Stage Layout — Design

**Date:** 2026-06-13
**Status:** Approved design — ready for implementation plan
**Branch (spec):** `worktree-lane-stage-layout` (based on `main` @ 0949c2a)

---

## 1. Goal

In the dashboard, agents within a workflow lane are today rendered as one flat vertical table.
Reframe the lane to convey **execution shape**: a workflow is a sequence of stages (a pipeline),
and a stage may fan out into parallel agents. Show:

- **Stages stacked vertically** (declared order, with a `↓` between them) — the pipeline.
- **Agents within a stage laid out horizontally** (cards side by side, wrapping when narrow) —
  the parallel fan-out.

## 2. Decision locked during brainstorming

| Decision | Choice |
|---|---|
| Parallel-vs-sequential basis | **Workflow stage** — agents in the same `WorkflowSpec` stage render horizontally; stages render vertically. (Not runtime overlap — simpler and stable.) |
| Known trade-off | The `synthesis` stage's two agents (`synthesizer_json` → `synthesizer_md`) run sequentially but share one stage, so they render horizontally. Accepted. |

## 3. Approach

Pure front-end change in `embroidery/web/static/index.html` — `renderAgents()` lane body + CSS.
No backend, endpoint, or data-contract change. The stage→agents mapping already arrives via
`GET /workflows` (`workflowsMeta[].stages[] = {name, agents[]}`); agent rows arrive via the
`agents` SSE event (`reporter` `as_row()`), already tagged with `workflow`.

**Per lane:**
1. Group the lane's agent rows by stage, using `meta.stages` order. An agent maps to the first
   stage whose `agents` list contains its `name`.
2. Render each stage as a **stage block** (vertical flow, `↓` separator between blocks): a stage
   label + a horizontal **flex row** of agent **cards**.
3. Each agent card shows name (click to expand), model, status badge, calls/tokens/$/elapsed —
   the same fields as today's row, in card form.
4. Agents not in any declared stage (loose/untagged) collect into a trailing **"other"** block.

**Reused unchanged:**
- Clicking an agent name toggles `expandedAgents` and renders its **step pipeline**
  (`renderSteps`) below the card, spanning the stage block width.
- `(no output)` marker for a `done` agent that wrote nothing.
- Lane head (label · aggregate calls/$), gate bar, rail.

## 4. Components

- `index.html` `<style>` — add `.stage-block`, `.stage-label`, `.stage-sep`, `.agent-cards`
  (flex, wrap, gap), `.agent-card`, and an expanded-pipeline container style. Keep existing
  `.lane`, `.pipe*`, `.out*` rules.
- `index.html` `renderAgents()` — replace the per-lane `<table>` body with stage blocks. A new
  helper `renderStageBlocks(wfRows, meta)` builds the grouped markup; `renderSteps` is reused for
  the expansion. The lane head, gate bar, and `lastAgentsEv`/`expandedAgents` click handling are
  unchanged.

## 5. Error handling

- **Agent in no stage** (e.g. `meta` missing or name not listed): falls into the "other" block so
  it never disappears.
- **Empty lane / no rows:** unchanged — "No agents running yet."
- **Long agent name / many parallel agents:** cards wrap to the next line (flex-wrap); each card
  has a min-width so they stay readable.

## 6. Testing

The project does not unit-test the vanilla JS. Verify by `node --check` on the extracted script,
confirm the web app still imports, and manually load the dashboard: during a research run the
sub-agents A/B/C appear as three side-by-side cards under "sub-agents A/B/C", the synthesis stage
appears as a second block below, and clicking a card still expands its step pipeline.

## 7. Out of scope (YAGNI)

- Runtime-overlap-based parallelism detection.
- Collapsing/reordering stages, drag-to-rearrange.
- Any change to how steps inside a single agent render (that pipeline is unchanged).
