# Lane Stage Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render each workflow lane as stage blocks stacked vertically (the pipeline) with the agents of each stage laid out horizontally as cards (the parallel fan-out), replacing today's flat per-lane table.

**Architecture:** Pure front-end change in `embroidery/web/static/index.html` — `renderAgents()` lane body + CSS. Group each lane's `agents`-event rows by `WorkflowSpec` stage (`workflowsMeta[].stages[].agents`, arriving via `GET /workflows`); unstaged rows fall into a trailing "other" block. The existing `renderSteps` expansion, `expandedAgents` click handling, lane head, gate bar, and rail are reused unchanged.

**Tech Stack:** Vanilla HTML/CSS/JS (`web/static/index.html`), served by FastAPI `FileResponse`. No build step. No backend change. Verify with `node --check` + manual dashboard load (the project does not unit-test the JS).

**Spec:** `docs/superpowers/specs/2026-06-13-lane-stage-layout-design.md`. Branch: `worktree-lane-stage-layout` (based on `main` @ 0949c2a).

---

## File Structure

**Modified (only):**
- `embroidery/embroidery/web/static/index.html` — add stage-layout CSS; add `agentCard()` + `renderStageBlocks()` JS helpers; replace the `<table>…</table>` lane body in `renderAgents()` with a `.stages` container.

No new files. No other files change.

---

# Task 1: Lane stage layout

**Files:**
- Modify: `embroidery/embroidery/web/static/index.html`

- [ ] **Step 1: Add the CSS**

In the `<style>` block, immediately after the `.noout { … }` rule (the last rule of the
"per-agent process pipeline" group, just before `</style>`), add:

```css
  /* lane stage layout */
  .stages { padding: 10px 14px; }
  .stage-label { font-size: 11px; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); margin: 0 0 6px; }
  .stage-sep { text-align: center; color: var(--line); margin: 2px 0 8px; }
  .agent-cards { display: flex; flex-wrap: wrap; gap: 10px; }
  .agent-card { flex: 1 1 220px; min-width: 220px; border: 1px solid var(--line); border-radius: 10px; padding: 10px 12px; background: var(--bg); }
  .agent-card.expanded { flex-basis: 100%; }
  .ac-head { display: flex; align-items: center; gap: 8px; justify-content: space-between; }
  .ac-meta { color: var(--muted); font-size: 11px; margin-top: 4px; }
  .card-steps { margin-top: 8px; }
```

- [ ] **Step 2: Add the `agentCard` + `renderStageBlocks` helpers**

In the `<script>`, immediately after the `renderSteps(steps) { … }` function (and before
`function renderAgents(ev) {`), add:

```javascript
function agentCard(r) {
  const open = expandedAgents.has(r.name);
  const noOut = r.status === "done" && !(r.steps || []).some(s => s.output_file);
  return `<div class="agent-card ${open ? 'expanded' : ''}">
    <div class="ac-head">
      <span class="agent-name" data-agent="${esc(r.name)}">${esc(r.name)}</span>
      <span class="badge ${r.status}">${esc(r.status)}</span>
    </div>
    <div class="ac-meta mono">${esc(r.model || "")} · ${r.calls}c · ${num(r.in_tokens)}/${num(r.out_tokens)} tok · ${money(r.cost_usd)} · ${r.elapsed_s}s</div>
    ${noOut ? '<div class="noout">(no output)</div>' : ''}
    ${open ? `<div class="card-steps">${renderSteps(r.steps)}</div>` : ''}
  </div>`;
}

function renderStageBlocks(wfRows, meta) {
  const stages = (meta && meta.stages) || [];
  const placed = new Set();
  const blocks = stages.map(st => {
    const agents = wfRows.filter(r => st.agents.includes(r.name));
    agents.forEach(r => placed.add(r.name));
    if (!agents.length) return "";
    return `<div class="stage-block">
      <div class="stage-label">${esc(st.name)}</div>
      <div class="agent-cards">${agents.map(agentCard).join("")}</div>
    </div>`;
  }).filter(Boolean);
  const others = wfRows.filter(r => !placed.has(r.name));
  if (others.length) {
    blocks.push(`<div class="stage-block">
      <div class="stage-label">other</div>
      <div class="agent-cards">${others.map(agentCard).join("")}</div>
    </div>`);
  }
  return blocks.join(`<div class="stage-sep">↓</div>`);
}
```

- [ ] **Step 3: Replace the lane body table with stage blocks**

In `renderAgents`, replace the entire `<table><tbody> … </tbody></table>` block (the part that
maps `wfRows` into `<tr>` rows) with a single `.stages` container call. Change:

```javascript
        <table><tbody>
          ${wfRows.map(r => {
            const isSub = !(r.name.includes('synthesizer') || (meta && meta.stages[0] && meta.stages[0].agents.includes(r.name)));
            const open = expandedAgents.has(r.name);
            const noOut = r.status === "done" && !(r.steps || []).some(s => s.output_file);
            return `
            <tr class="${isSub ? 'sub' : ''} ${open ? 'expanded' : ''}">
              <td><span class="agent-name" data-agent="${esc(r.name)}">${esc(r.name)}</span>${noOut ? ' <span class="noout">(no output)</span>' : ''}</td>
              <td class="mono" style="color:var(--muted)">${r.model || ""}</td>
              <td><span class="badge ${r.status}">${r.status}</span></td>
              <td style="text-align:right">${r.calls}</td>
              <td class="mono" style="text-align:right">${num(r.in_tokens)}/${num(r.out_tokens)}</td>
              <td>${r.searches}</td>
              <td class="mono" style="text-align:right">${money(r.cost_usd)}</td>
              <td class="mono" style="text-align:right">${r.elapsed_s}s</td>
            </tr>` + (open ? `<tr class="steprow"><td colspan="8">${renderSteps(r.steps)}</td></tr>` : "");
          }).join("")}
        </tbody></table>
```

to:

```javascript
        <div class="stages">${renderStageBlocks(wfRows, meta)}</div>
```

(The lane head `<div class="lane-head">…</div>` above it and `${gbar}` below it are unchanged.)

- [ ] **Step 4: Syntax-check the JS**

Run (from the worktree root):

```bash
python3 - <<'PY'
import re, pathlib
h = pathlib.Path("embroidery/embroidery/web/static/index.html").read_text()
pathlib.Path("/tmp/lane.js").write_text(re.search(r"<script>(.*)</script>", h, re.S).group(1))
print("extracted")
PY
node --check /tmp/lane.js && echo "JS OK"
```
Expected: `extracted` then `JS OK`.

- [ ] **Step 5: Confirm the web app still imports (server would start)**

Run (use the repo venv interpreter; run from the worktree's `embroidery/` dir):

```bash
cd embroidery && /Users/nga.mai/04.Agents/agent-teams/embroidery/venv/bin/python -c "from embroidery.web.server import app; print('web app OK')"
```
Expected: `web app OK`.

- [ ] **Step 6: Manual verification**

Run `cd embroidery && /Users/nga.mai/04.Agents/agent-teams/embroidery/venv/bin/python -m embroidery.web --no-browser`,
open `http://127.0.0.1:8765/`, run a research workflow (or seed + run via the Test panel). Confirm:
the **sub-agents A/B/C** stage shows three cards **side by side**; the **synthesis** stage appears
as a **second block below** with a `↓` between; clicking an agent name expands its **step pipeline**
inside the card (card widens to full row); a `done` agent with no file shows "(no output)".

- [ ] **Step 7: Commit**

```bash
git add embroidery/embroidery/web/static/index.html
git commit -m "Dashboard: lane stage layout — stages vertical, parallel agents horizontal"
```

---

## Notes for the implementer

- **Reused unchanged:** `renderSteps` (step pipeline), the `#lanes` click handler (toggles
  `expandedAgents` via `.agent-name`, opens output via `.out-link` → `.pipe-node .out-view`),
  `lastAgentsEv`, lane head, gate bar, rail. Do not touch them.
- **Dead CSS left in place (harmless):** `.lane table`, `.lane .sub`, `.steprow` rules are no
  longer used once the table is gone — leave them rather than risk a wider edit (YAGNI).
- **No backend / endpoint / data-contract change.** `meta.stages[].agents` and the `agents` SSE
  rows already exist.
- **Out of scope:** runtime-overlap parallelism detection, stage collapse/reorder, changes to the
  intra-agent step rendering.
