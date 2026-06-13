# Per-Agent Process Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the dashboard expand any agent row into an ordered pipeline of its work steps (LLM call / web search / web fetch / file write) ending in a clickable output node that shows the produced file.

**Architecture:** The reporter is already tapped by `agent_loop` at every call/search/done. Add an ordered `steps` list to `AgentRecord`, append a step at each tap, and let it ride the existing `as_row()` → SSE `agents` event. Sub-agents (whose JSON is persisted by Python) and the synthesizer get their output node via a new `agent_output()` call from the pipeline. The browser renders `steps` as a pipeline; the output node reuses `GET /output/{file}`. No new endpoint, no data-contract change, no orchestrator change.

**Tech Stack:** Python 3.11 (`embroidery` package), FastAPI + SSE, vanilla HTML/JS (`web/static/index.html`). Run from `embroidery/` as modules. Tests are house-style standalone modules (`main()` + `check()` + `✓/✗` + exit code), run via `venv/bin/python -m tests.<name>` — NOT pytest. Use `venv/bin/python` for every command.

**Spec:** `docs/superpowers/specs/2026-06-13-agent-process-pipeline-design.md`. Branch: `worktree-agent-process-pipeline-spec` (rebased on `web-team-dashboard`).

---

## File Structure

**New**
- `embroidery/tests/test_agent_steps.py` — house-style test for reporter step recording + the `write_file` tap.

**Modified**
- `embroidery/embroidery/core/reporter.py` — `AgentRecord.steps` + append in `agent_call`/`agent_search`; new `agent_write`/`agent_fetch`/`agent_output`; `as_row()` carries `steps`; `agent_start` clears steps on re-run.
- `embroidery/embroidery/core/agent_loop.py` — in `_execute_tool`: tap `agent_write` (write_file), `agent_fetch` (web_fetch); pass `num_results` to `agent_search`.
- `embroidery/embroidery/agents/research/subagents.py` — after persisting each sub-agent JSON, call `agent_output(spec.name, spec.output_file)`.
- `embroidery/embroidery/agents/research/pipeline.py` — after writing the report files, call `agent_output` for `synthesizer_json` / `synthesizer_md`.
- `embroidery/embroidery/web/static/index.html` — expandable agent rows rendering the step pipeline + output viewer.
- Docs: `embroidery/embroidery/core/README.md`, `embroidery/embroidery/web/README.md`, `CLAUDE.md`.

**Deviation from spec:** the search step records the *requested* `num_results` (cleanly available at the tap), not a parsed actual-result count — the search tool returns a formatted string, so an exact count isn't reliably available. The UI labels it accordingly.

---

# Task 1: Reporter records ordered steps

**Files:**
- Test: `embroidery/tests/test_agent_steps.py`
- Modify: `embroidery/embroidery/core/reporter.py`

- [ ] **Step 1: Write the failing test**

Create `embroidery/tests/test_agent_steps.py`:

```python
"""
The reporter records an ordered `steps` list per agent (call / search / write /
fetch / output), and as_row() carries it so the dashboard can render a pipeline.
Also covers the write_file tap in agent_loop._execute_tool. No providers.

Run: cd embroidery && venv/bin/python -m tests.test_agent_steps
"""
import asyncio
import sys
from pathlib import Path

from embroidery.core.reporter import get_reporter
from embroidery.core.agent_loop import _execute_tool
from embroidery.core.config import settings

failures: list[str] = []

def check(cond, msg):
    print(("✓ " if cond else "✗ ") + msg)
    if not cond:
        failures.append(msg)

def test_steps_recorded_in_order():
    r = get_reporter()
    r.reset()
    r.agent_start("ag", "claude-sonnet-4-6", 100)
    r.agent_call("ag", 100, 20)
    r.agent_search("ag", "embroidery gifts", 10)
    r.agent_write("ag", "out.json")
    r.agent_done("ag")
    rec = r.snapshot()["rows"][0]
    steps = rec["steps"]
    check([s["type"] for s in steps] == ["call", "search", "write"], "steps recorded in order")
    check(steps[0]["in_tok"] == 100 and steps[0]["out_tok"] == 20, "call step carries tokens")
    check(steps[1]["label"] == "embroidery gifts" and steps[1]["results"] == 10, "search step carries query + results")
    check(steps[2]["output_file"] == "out.json", "write step carries output_file")
    check([s["seq"] for s in steps] == [1, 2, 3], "steps numbered sequentially")

def test_output_step_and_rerun_clears():
    r = get_reporter()
    r.reset()
    r.agent_start("ag", "m", 100)
    r.agent_call("ag", 1, 1)
    r.agent_output("ag", "report.json")
    rec = r.snapshot()["rows"][0]
    check(rec["steps"][-1]["type"] == "output" and rec["steps"][-1]["output_file"] == "report.json",
          "agent_output appends an output node")
    r.agent_start("ag", "m", 100)  # re-run resets
    check(r.snapshot()["rows"][0]["steps"] == [], "re-run clears steps")

def test_write_file_tap():
    async def run():
        r = get_reporter()
        r.reset()
        r.agent_start("writer", "m", 100)
        await _execute_tool("write_file", {"filename": "_steptest.json", "content": "{}"}, "writer")
        steps = r.snapshot()["rows"][0]["steps"]
        check(any(s["type"] == "write" and s["output_file"] == "_steptest.json" for s in steps),
              "_execute_tool(write_file) records a write step")
        (Path(settings.paths.output) / "_steptest.json").unlink(missing_ok=True)
    asyncio.run(run())

def main() -> int:
    test_steps_recorded_in_order()
    test_output_step_and_rerun_clears()
    test_write_file_tap()
    if failures:
        print(f"\n✗ test_agent_steps FAILED ({len(failures)})")
        return 1
    print("\n✓ test_agent_steps passed")
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it — verify it fails**

Run: `cd embroidery && venv/bin/python -m tests.test_agent_steps`
Expected: FAIL — `AgentRecord` has no `steps`; `agent_write`/`agent_output` not defined; `as_row()` has no `"steps"`.

- [ ] **Step 3: Add the `steps` field + carry it in `as_row()`**

In `embroidery/embroidery/core/reporter.py`, in the `AgentRecord` dataclass, add `steps` after `t_end` (the dataclass already imports `field`):

```python
    t_end: float | None = None
    steps: list = field(default_factory=list)
```

In `AgentRecord.as_row()`, add the steps to the returned dict (after `"elapsed_s"`):

```python
            "elapsed_s": round(self.elapsed, 1),
            "steps": self.steps,
```

- [ ] **Step 4: Append steps in the existing emit points + clear on re-run**

In `reporter.py`, replace `agent_call` and `agent_search` with these, and add `agent_write` / `agent_fetch` / `agent_output` right after `agent_search`:

```python
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
```

In `agent_start`, the re-run branch resets counters — also clear steps. Change:

```python
            rec.calls = rec.in_tokens = rec.out_tokens = rec.searches = 0
            rec.t_start = time.monotonic()
            rec.t_end = None
```

to add a steps reset:

```python
            rec.calls = rec.in_tokens = rec.out_tokens = rec.searches = 0
            rec.steps = []
            rec.t_start = time.monotonic()
            rec.t_end = None
```

- [ ] **Step 5: Run it — verify it passes**

Run: `cd embroidery && venv/bin/python -m tests.test_agent_steps`
Expected: PASS (`✓ test_agent_steps passed`).

- [ ] **Step 6: Run the existing reporter test — verify no regression**

Run: `cd embroidery && venv/bin/python -m tests.test_reporter_workflow`
Expected: PASS (steps ride along harmlessly).

- [ ] **Step 7: Commit**

```bash
git add embroidery/tests/test_agent_steps.py embroidery/embroidery/core/reporter.py
git commit -m "Reporter: record ordered per-agent steps + carry in as_row()"
```

---

# Task 2: Wire the write/fetch taps in agent_loop

**Files:**
- Modify: `embroidery/embroidery/core/agent_loop.py` (the `_execute_tool` function)

The `test_write_file_tap` case in `test_agent_steps.py` (Task 1) already covers this — it
currently fails the write assertion until this task lands. (If running tasks out of order, that
test is the spec for this change.)

- [ ] **Step 1: Add the taps**

In `embroidery/embroidery/core/agent_loop.py`, in `_execute_tool`:

In the `write_file` branch, add the reporter tap after the write:

```python
    if name == "write_file":
        result = _tool_write_file(inputs["filename"], inputs["content"])
        _log.info("tool=write_file file=%s", inputs["filename"])
        get_reporter().agent_write(agent_name, inputs["filename"])
        return result
```

In the `web_search` branch, pass the requested result count to `agent_search`:

```python
        get_reporter().agent_search(agent_name, inputs["query"], inputs.get("num_results", 10))
```

In the `web_fetch` branch, add a fetch tap:

```python
    if name == "web_fetch":
        _log.info("tool=web_fetch url=%s", inputs["url"])
        get_reporter().agent_fetch(agent_name, inputs["url"])
        return await _get_search().fetch(inputs["url"])
```

- [ ] **Step 2: Run the step test — verify the write tap passes**

Run: `cd embroidery && venv/bin/python -m tests.test_agent_steps`
Expected: PASS — including `_execute_tool(write_file) records a write step`.

- [ ] **Step 3: Commit**

```bash
git add embroidery/embroidery/core/agent_loop.py
git commit -m "agent_loop: tap write_file/web_fetch into reporter steps; pass num_results to search"
```

---

# Task 3: Attach output nodes for sub-agents + synthesizer

**Files:**
- Modify: `embroidery/embroidery/agents/research/subagents.py` (in `run_subagent`, after the JSON is written ~line 414)
- Modify: `embroidery/embroidery/agents/research/pipeline.py` (after the report files are written ~lines 168-169)

These agents do not call `write_file` (sub-agents return JSON that Python persists; the
synthesizer has no tools), so their output node is attached explicitly via `agent_output`.

- [ ] **Step 1: Sub-agents A/B/C**

In `embroidery/embroidery/agents/research/subagents.py`, add the import near the other core imports (it already imports from `embroidery.core.agent_loop`):

```python
from embroidery.core.reporter import get_reporter
```

Then in `run_subagent`, right after the line that writes the file:

```python
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    get_reporter().agent_output(spec.name, spec.output_file)
```

(`spec.name` is the reporter agent name — `audience_researcher` / `competitor_analyst` /
`social_media_analyst`; `spec.output_file` is `research_a_audience.json` etc.)

- [ ] **Step 2: Synthesizer**

In `embroidery/embroidery/agents/research/pipeline.py`, add the import near the top with the other core imports:

```python
from embroidery.core.reporter import get_reporter
```

Then after the two report files are written (the `json_path.write_text(...)` /
`md_path.write_text(markdown, ...)` lines):

```python
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")
    get_reporter().agent_output("synthesizer_json", "market_research_report.json")
    get_reporter().agent_output("synthesizer_md", "brand_intelligence_report.md")
```

- [ ] **Step 3: Sanity import check (no provider call)**

Run: `cd embroidery && venv/bin/python -c "import embroidery.agents.research.subagents, embroidery.agents.research.pipeline; print('imports ok')"`
Expected: `imports ok` (no ImportError, no circular-import error).

- [ ] **Step 4: Commit**

```bash
git add embroidery/embroidery/agents/research/subagents.py embroidery/embroidery/agents/research/pipeline.py
git commit -m "Research: attach output-node steps for sub-agents A/B/C + synthesizer"
```

---

# Task 4: Render the step pipeline in the dashboard

**Files:**
- Modify: `embroidery/embroidery/web/static/index.html` (CSS, `renderAgents`, new helpers + click handlers)

This is UI; it is verified manually (the project does not unit-test the vanilla JS).

- [ ] **Step 1: Add CSS for the pipeline + viewer**

In the `<style>` block (near the `.lane` rules), add:

```css
  .agent-name { cursor: pointer; user-select: none; }
  .agent-name::before { content: "▸ "; color: var(--muted); }
  tr.expanded .agent-name::before { content: "▾ "; }
  .steprow > td { background: var(--bg); padding: 8px 14px 12px 30px; }
  .pipe { display: flex; flex-direction: column; gap: 0; }
  .pipe-node { border: 1px solid var(--line); border-radius: 8px; padding: 6px 10px; font-size: 12px; }
  .pipe-node .nt { font-weight: 600; margin-right: 6px; }
  .pipe-node.t-search .nt { color: var(--accent); }
  .pipe-node.t-write .nt, .pipe-node.t-output .nt { color: var(--ok); }
  .pipe-arrow { color: var(--line); text-align: center; line-height: 1.2; }
  .pipe-meta { color: var(--muted); margin-left: 8px; }
  .out-link { cursor: pointer; text-decoration: underline; color: var(--ok); }
  .out-view { margin-top: 6px; white-space: pre-wrap; max-height: 280px; overflow: auto;
              background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 10px; }
  .out-copy { margin-left: 8px; cursor: pointer; font-size: 11px; }
  .noout { color: var(--muted); font-style: italic; }
```

- [ ] **Step 2: Add expand state + step rendering helpers**

In the `<script>`, near the other top-level state (e.g. beside `let workflowsMeta = [];`), add:

```javascript
const expandedAgents = new Set();   // agent names whose pipeline is expanded

const STEP_LABEL = { call: "LLM call", search: "Search", fetch: "Fetch", write: "Write", output: "Output" };

function renderSteps(steps) {
  if (!steps || !steps.length) return `<div class="noout">(no steps recorded)</div>`;
  return `<div class="pipe">` + steps.map((s, i) => {
    const arrow = i ? `<div class="pipe-arrow">↓</div>` : "";
    let meta = "";
    if (s.type === "call") meta = `${num(s.in_tok)}/${num(s.out_tok)} tok · ${money(s.cost_usd)}`;
    else if (s.type === "search") meta = s.results != null ? `xin ${s.results} kết quả` : "";
    let body = esc(s.label || "");
    if (s.output_file) body = `<span class="out-link" data-file="${esc(s.output_file)}">📄 ${esc(s.output_file)}</span>`;
    return `${arrow}<div class="pipe-node t-${s.type}">`
         + `<span class="nt">${STEP_LABEL[s.type] || s.type}</span>${body}`
         + (meta ? `<span class="pipe-meta">${meta} · ${s.elapsed_s ?? 0}s</span>` : "")
         + `<div class="out-view hide" data-for="${esc(s.output_file || '')}"></div>`
         + `</div>`;
  }).join("") + `</div>`;
}
```

- [ ] **Step 3: Make agent rows expandable in `renderAgents`**

In `renderAgents`, replace the agent-row template (the `wfRows.map(r => ...)` block) with one that
makes the name clickable and appends a detail row when expanded:

```javascript
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
```

- [ ] **Step 4: Wire click handlers (delegation on `#lanes`)**

Add once, near where other listeners are registered (e.g. after `loadWorkflows()` is defined / called):

```javascript
$("lanes").addEventListener("click", async (e) => {
  const name = e.target.closest(".agent-name")?.dataset.agent;
  if (name) {
    expandedAgents.has(name) ? expandedAgents.delete(name) : expandedAgents.add(name);
    renderAgents(lastAgentsEv || { rows: [], totals: {} });
    return;
  }
  const link = e.target.closest(".out-link");
  if (link) {
    const file = link.dataset.file;
    const view = link.closest(".pipe-node").querySelector(".out-view");
    if (!view.classList.contains("hide")) { view.classList.add("hide"); return; }
    view.classList.remove("hide");
    view.textContent = "loading…";
    try {
      const res = await fetch("/output/" + encodeURIComponent(file));
      if (!res.ok) { view.textContent = "file no longer available"; return; }
      const text = await res.text();
      let pretty = text;
      if (file.endsWith(".json")) { try { pretty = JSON.stringify(JSON.parse(text), null, 2); } catch {} }
      view.innerHTML = `<button class="out-copy">📋 copy</button><pre style="margin:6px 0 0">${esc(pretty)}</pre>`;
      view.querySelector(".out-copy").onclick = () => navigator.clipboard.writeText(pretty);
    } catch { view.textContent = "load error"; }
  }
});
```

- [ ] **Step 5: Cache the last agents event for re-render on expand/collapse**

`renderAgents` is called from the SSE handler. To re-render on a click without a new event, store
the last event. At the top of `renderAgents(ev)` add:

```javascript
function renderAgents(ev) {
  lastAgentsEv = ev;
  const rows = ev.rows || [];
```

and declare `let lastAgentsEv = null;` beside the other top-level `let` state.

- [ ] **Step 6: Manual verification**

Run: `cd embroidery && venv/bin/python -m embroidery.web --no-browser`, open `http://127.0.0.1:8765/`.
With no run, lanes show "No agents running yet" (unchanged). Start a research run (or seed via the
Test panel + run a stage); when an agent appears, click its name → the row expands to a pipeline of
call/search nodes; click an `output` node → the file content loads formatted with a copy button.
Confirm a `done` agent that wrote nothing shows "(no output)".

- [ ] **Step 7: Commit**

```bash
git add embroidery/embroidery/web/static/index.html
git commit -m "Dashboard: expand agent row into a step pipeline + inline output viewer"
```

---

# Task 5: Documentation

**Files:**
- Modify: `embroidery/embroidery/core/README.md`, `embroidery/embroidery/web/README.md`, `CLAUDE.md`

Per the repo README rule, new public methods on the reporter and a changed UI capability are significant.

- [ ] **Step 1: `core/README.md`** — note that `AgentRecord` now carries an ordered `steps` list and `reporter` exposes `agent_write` / `agent_fetch` / `agent_output` (in addition to `agent_call` / `agent_search`); `agent_search` now takes an optional `results` count. Steps ride `as_row()` over SSE.

- [ ] **Step 2: `web/README.md`** — in the dashboard description, note each agent row expands into a **process pipeline** (ordered call/search/fetch/write step nodes) and that output nodes reuse `GET /output/{file}` for inline formatted viewing + copy. No new endpoint.

- [ ] **Step 3: `CLAUDE.md`** — in the **Monitor** bullet, add that an agent row expands to a labeled step pipeline ending in an inline output viewer.

- [ ] **Step 4: Commit**

```bash
git add embroidery/embroidery/core/README.md embroidery/embroidery/web/README.md CLAUDE.md
git commit -m "Docs: per-agent process pipeline (reporter steps + dashboard viewer)"
```

---

## Notes for the implementer

- **Run order:** Task 1 → 5 in sequence. Task 1's test also specs Task 2 (the `write_file` tap); both must be green before Task 3.
- **No provider tests:** every test stubs by calling reporter methods / `_execute_tool` directly. Do not add live-provider tests; the live check is manual via the dashboard.
- **House test style:** `main()` + `check()` + exit code, printing `✓/✗` (match `tests/test_reporter_workflow.py`). No pytest.
- **Rebase before merging:** this branch is rebased on `web-team-dashboard`; rebase again on its latest tip before integrating, since that branch may have advanced.
- **Out of scope:** per-step content drill-down, compare view, download button, cross-run step history (see spec §7).
