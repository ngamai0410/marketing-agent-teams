# evaluate-agents skill

Claude Code skill that grades each market-research pipeline agent (sub-agents A/B/C and the two Synthesizer calls) after a `agent1_market_research.py` run.

## How to run

In Claude Code, from the repo root:

```
/evaluate-agents          # grade all four agents
/evaluate-agents c        # grade only Agent C
```

Prerequisite: a completed pipeline run — `embroidery/output/research_{a,b,c}.json`, `market_research_report.json`, `brand_intelligence_report.md`, and a log in `embroidery/logs/` containing `market_research pipeline done`.

## Files

- `SKILL.md` — the skill definition: artifact discovery, per-agent rubrics (targets copied from the agents' own system prompts in `agent1_subagents.py` / `agent1_synthesizer.py`), scorecard format, synthesis instructions.

## Workflow chart

```
main thread (small context)
  │ Step 1: grep log → per-agent summary lines only (never Reads big files)
  │
  ├─► evaluator subagent A ── reads research_a_audience.json ──┐
  ├─► evaluator subagent B ── reads research_b_competitor.json │  fresh context each,
  ├─► evaluator subagent C ── reads research_c_social.json     │  run concurrently
  └─► evaluator subagent S ── reads market_research_report.json│
                              + brand_intelligence_report.md ──┘
  │        each returns a ≤25-line scorecard (raw JSON stays in the subagent)
  ▼
  Step 3: main thread merges scorecards → comparison table,
          weakest link, prioritized fixes, go/no-go for Agents 2/3
```

Context truncation contract: the main conversation only ever holds grep'd log lines and the four scorecards. Each pipeline agent's raw output is read inside its own throwaway evaluator subagent, so evaluating agent N never carries agent N-1's bulk forward.

## Maintenance

The rubrics duplicate the numeric targets from the agent system prompts. If you change targets in `agent1_subagents.py` or `agent1_synthesizer.py` (section counts, search budgets, schema fields), update the matching rubric in `SKILL.md`.
