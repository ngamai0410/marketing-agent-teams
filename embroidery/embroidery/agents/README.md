# embroidery/agents/ — campaign agents, grouped by workflow

One subpackage per workflow stage from `../../../CLAUDE.md`. Agent numbers live in docs and
`config.yaml`, not in filenames (role-based naming). **Each subpackage has its own README**
with that workflow's full data contracts, models, run commands, and chart:

- [`research/README.md`](research/README.md) — Workflow 1: Market Research (Agent 1)
- `copy/README.md` — Workflow 2: Copy (Agents 4–6) *(future)*
- [`qa/README.md`](qa/README.md) — Workflow 3: QA & Feedback (Agents 7–8)

```
research/   Workflow 1 — Market Research
  pipeline.py     Agent 1 entry: gather(A,B,C) → Synthesizer → reports + BrandAI snapshot
  subagents.py    Agent 1 sub-agents A/B/C (search-only; return JSON as text). Holds SHOP_BRIEF.
  synthesizer.py  Agent 1 Synthesizer (no tools; merges A/B/C → master JSON + markdown)
  (avatar.py, positioning.py = Agents 2,3 — future)

copy/       Workflow 2 — Copy  [future]
  (hooks.py, scripts.py, static_copy.py = Agents 4,5,6)

qa/         Workflow 3 — QA & Feedback
  qa_reviewer.py  Agent 7: 8-question diagnostic + psychology checklist → qa_report.json (gatekeeper)
  (feedback.py = Agent 8 — future)

orchestrator.py   wired last — enforces pipeline invariants  [future]
```

Data contracts (who writes/reads which file in `data/output/`) are tabulated in `../../../CLAUDE.md`.
Every agent calls `run_agent(..., agent_name="<key>")` from `embroidery.core.agent_loop`, using
the model assigned to its key under `agents:` in `config.yaml`.
