# Per-Agent Process Pipeline — Design

**Date:** 2026-06-13
**Status:** Approved design — ready for implementation plan
**Branch (spec):** `worktree-agent-process-pipeline-spec` (based on `origin/main` @ e2c3938)
**Depends on:** the whole-team dashboard work (`2026-06-13-web-team-dashboard-design.md`,
phases 1–4) — `reporter.py` lanes, `as_row()` SSE rows, `/output/{file}`, and the
`index.html` lane/`renderAgents` rendering. **Implement only after that work is merged.**

---

## 1. Goal & context

On the dashboard, each agent currently shows only *aggregate counters* in its lane row
(calls / tokens / $ / searches / elapsed). The final artifacts are reachable only as raw file
links in the "Campaign complete" panel, and a per-stage **digest** appears at each QC gate.

The user wants to inspect **how each agent worked**, not just its final output — and to see it
**as an easy-to-understand pipeline**. Primary purpose: **quality / correctness inspection**
(spot a bad search, a wrong intermediate step, an agent that produced nothing).

This design adds a **per-agent process pipeline**: clicking an agent row expands an ordered
sequence of *labeled step nodes* (LLM call, web search, web fetch, file write) ending in an
**output node** that shows the agent's produced file (formatted + copy). It is generic across
every workflow (Research now, Copy/QA/Feedback as they come online), driven entirely by the
reporter — no per-workflow code.

### Decisions locked during brainstorming

| Decision | Choice |
|---|---|
| Purpose | **Quality/correctness inspection** (not read-to-reuse, not compare) |
| Interaction | **Expand the agent row inline in its lane** — process appears directly under the row, keeping agent + metrics in context |
| Availability | **As soon as each agent finishes** (steps stream in live; viewable mid-run, not only at full completion) |
| Step depth | **Labeled steps, no per-step content drill-down** — each node names the action (call / search "query" / fetch / write) + its tokens/$/elapsed; the *final output file* is the only viewable content |
| Presentation | **Pipeline** — step nodes connected top-to-bottom with arrows, final node = output |
| Scope | Generic (all workflows). No side-by-side compare. No download button (raw link + copy suffice). |

---

## 2. Architecture

The reporter is already tapped by `agent_loop.run_agent()` at every meaningful moment
(`agent_start` / `agent_call` / `agent_search` / `agent_done`). Today those calls only
*increment counters*. The change: **also append an ordered step record** at each tap, carry the
list on `AgentRecord`, and let it ride the existing `as_row()` → SSE `agents` event to the
browser. The UI renders the list as a pipeline. The output node reuses the existing
`GET /output/{file}` endpoint.

```
agent_loop.run_agent()
  │  (existing taps — now also append a Step)
  ├─ agent_call(name, in, out)      → Step{type:"call",   in,out,cost,elapsed}
  ├─ agent_search(name, query, n)   → Step{type:"search", label:query, results:n, elapsed}
  ├─ agent_write(name, file)  [NEW tap in tool-exec path] → Step{type:"write", output_file:file}
  └─ agent_done(name)
        │
        ▼
core/reporter.py  AgentRecord.steps: list[Step]   ──as_row()──► SSE "agents" event
        ▲                                                            │
        └─ agents/research/pipeline.py calls reporter.agent_output(  │
             name, file) for sub-agents A/B/C (they return JSON,     ▼
             Python persists it — no write_file tool)        web/static/index.html
                                                             renderAgents(): per row →
                                                             expand → pipeline of steps,
                                                             output node → GET /output/{file}
```

No new endpoint. No data-contract change. No orchestrator change.

---

## 3. Components

### 3.1 `core/reporter.py` (extend)

- `AgentRecord` gains `steps: list[dict]` (default empty). A `Step` is a plain dict:
  `{seq:int, type:"call"|"search"|"fetch"|"write"|"output", label:str, in_tok?:int,
  out_tok?:int, cost_usd?:float, results?:int, output_file?:str, elapsed_s?:float}`.
- Existing methods append a step (in addition to their current counter updates):
  - `agent_call(name, in_tok, out_tok)` → append `type:"call"`.
  - `agent_search(name, query)` → **extend signature to `agent_search(name, query, results=None)`**;
    append `type:"search"`, `label=query`, `results`. (Caller in `agent_loop.py` passes the
    result count it already has.)
- New methods:
  - `agent_write(name, file)` → append `type:"write"`, `output_file=file`.
  - `agent_output(name, file)` → append (or upgrade the trailing write into) an `type:"output"`
    node carrying `output_file` — for agents whose file is persisted by Python, not `write_file`.
- `as_row()` includes `"steps": self.steps` so the list streams to the browser unchanged.
- Each appended step stamps `elapsed_s` relative to the agent's `t_start` for ordering display.

### 3.2 `core/agent_loop.py` (one new tap)

- In the tool-execution branch, when the tool is `write_file`, call
  `get_reporter().agent_write(agent_name, file)`.
- Where it already calls `agent_search(agent_name, query)`, pass the result count.

### 3.3 `agents/research/pipeline.py` (one call)

- After Python persists each sub-agent's `research_*.json`, call
  `reporter.agent_output(sub_agent_name, filename)` so A/B/C rows get an output node.
- The Synthesizer writes `market_research_report.json` + `brand_intelligence_report.md`; tag
  each via `agent_output` against the `synthesizer_json` / `synthesizer_md` agent names.

### 3.4 `web/static/index.html` (rendering only)

- In `renderAgents`, each agent row gets an expand/collapse control. The expanded panel renders
  `row.steps` as a vertical pipeline: one node per step (icon by `type`, label, and the step's
  tokens/$/results/elapsed), connected by `↓` arrows.
- The final `output`/`write` node with an `output_file` is clickable: fetch `GET /output/{file}`,
  pretty-print JSON (`JSON.stringify(obj, null, 2)`, foldable) or show `.md` as preformatted
  text, with a **📋 copy** button.
- A `done` agent with **no** output node renders "(no output)" so failures are visible.
- Steps stream in live via the existing `agents` SSE event — the pipeline grows in real time and
  remains viewable after the agent finishes.

---

## 4. Error handling

- **Agent crashed / produced nothing:** the pipeline shows the steps it completed; the output
  node is absent and the row shows "(no output)". No silent blank.
- **Output file missing when clicked** (overwritten/cleared between run and click):
  `/output/{file}` 404 → the node shows "file no longer available".
- **Large output:** the inline viewer caps height and scrolls (reuse the existing `t-preview`
  styling pattern); the raw `/output/{file}` link remains the unbounded fallback.
- **No subscriber / standalone CLI run:** unchanged — reporter is a no-op without subscribers;
  steps simply aren't streamed.

---

## 5. Testing strategy

House style — `main()` + `check()` + `✓/✗` + exit code, run as
`venv/bin/python -m tests.test_agent_steps`. **No live provider.** Stub by calling reporter
methods directly:

- `agent_call` / `agent_search(query, results)` / `agent_write` appended in order →
  `AgentRecord.steps` has the right length, types, order, labels, and token/result fields.
- A `write` (and `agent_output`) step carries the correct `output_file`.
- `as_row()` includes `steps` (so it will reach the browser over SSE).
- A `done` agent with no output-bearing step exposes none (drives the "(no output)" UI branch).

Manual check: run research (live, or via fixtures once the Test panel lands), expand a sub-agent
row, confirm the call/search nodes and the clickable output node render.

---

## 6. Coordination / sequencing (important)

This feature edits **`reporter.py`** and **`index.html`** — the same files the whole-team
dashboard work (phases 1–4) is actively changing. To avoid merge conflicts:

1. **Now:** spec only (this document) — committed on an isolated branch.
2. **Then:** writing-plans produces the implementation plan, which **must not start coding until
   phases 1–4 are merged**. Build on the stable `reporter.py` / `index.html`.
3. **At implementation:** work in a worktree, rebase on the latest dashboard branch first.

---

## 7. Out of scope (YAGNI)

- Per-step content drill-down (search-result text, per-call LLM output, tool args).
- Side-by-side comparison of agents.
- A download/export button beyond the existing raw link + copy.
- Persisting step history across runs (the reporter is per-run; history lives in `data/logs/`).

---

## 8. Documentation impact (per repo README rule)

- `core/README.md` — note `AgentRecord.steps` and the `agent_write` / `agent_output` taps; the
  `agent_search` signature gains `results`.
- `web/README.md` — note the agent row now expands to a process pipeline; output nodes reuse
  `GET /output/{file}`.
- `CLAUDE.md` — Monitor bullet: agent rows expand to a labeled step pipeline + inline output.
