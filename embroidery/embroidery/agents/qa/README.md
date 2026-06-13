# agents/qa/ — Workflow 3: QA & Feedback (Agents 7, 8)

The pipeline's quality gate. Agent 7 reviews every ad concept before production; nothing
ships until it returns `overall: PASS`. Agent 8 (post-launch feedback) is future work.

## Workflow

```
   positioning_matrix.json  (Agent 3)  ┐
   video_scripts.json       (Agent 5)  ├─► read_file (FILE_TOOLS)
   static_ad_copy.json      (Agent 6)  ┘
                                         │
                                         ▼  qa_reviewer.run_qa_review()   gemini-2.5-pro
                          EcomTalent 8-question diagnostic
                          + buying-psychology checklist, per ad
                                         │
                                         ▼  write_file
                          data/output/qa_report.json
                                         │
                                         ▼
                  Orchestrator gate:  overall PASS → ship
                                      overall FAIL → re-run Agents 5/6 with per-ad revision_notes
```

## Files

| File | Role | Key symbols |
|---|---|---|
| `qa_reviewer.py` | Agent 7 — reads the positioning matrix + scripts/copy, runs the 8-question diagnostic and buying-psychology checklist on every ad, writes `qa_report.json`. | `run_qa_review()`, `SYSTEM_PROMPT` |
| *(future)* `feedback.py` | Agent 8 — post-launch feedback analyst; reads ad-performance CSV, writes `weekly_learnings.json` / `next_week_brief.json`. | — |

## Data contracts

| Direction | File(s) |
|---|---|
| **In** | `data/output/positioning_matrix.json`, `data/output/video_scripts.json`, `data/output/static_ad_copy.json` |
| **Out → Orchestrator** | `data/output/qa_report.json` (`overall` PASS/FAIL + per-ad `revision_notes`) |

Tools: `FILE_TOOLS` (`read_file` + `write_file`). Model: `gemini-2.5-pro` — flash emits
`MALFORMED_FUNCTION_CALL` here even on small `read_file` contexts.

## Gate behaviour

`overall: FAIL` if **any** ad needs revision. The reviewer is intentionally strict: a false
PASS wastes real ad budget, a false FAIL costs only one revision cycle — so when in doubt it
FAILs with specific `revision_notes` telling Agents 5/6 exactly what to fix.

## Run

```bash
# from embroidery/ (project root)
venv/bin/python -m embroidery.agents.qa.qa_reviewer   # reads positioning_matrix + scripts/copy from data/output/
venv/bin/python -m tests.test_agent7                  # gate test against fixtures/ (one strong ad PASS, one corporate ad FAIL)
```

`test_agent7` copies `fixtures/{positioning_matrix,video_scripts,static_ad_copy}.json` into
`data/output/`, runs the agent, then asserts the gate discriminates (strong ad PASS, corporate
ad FAIL, `overall` FAIL with revision notes) — built before Agents 3/5/6 exist.
