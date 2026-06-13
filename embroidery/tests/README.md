# tests/ — test & smoke scripts

Plain scripts with `__main__` guards (not pytest). Run as **modules** from the project root
(`embroidery/`) so the `embroidery` package and `tests` package both resolve:

```bash
venv/bin/python -m tests.smoke_test               # Day 1: loop + tools + write_file → data/output/
venv/bin/python -m tests.test_tools               # web_search + write_file end-to-end (live)
venv/bin/python -m tests.test_gemini              # Gemini provider: smoke + search (live)
venv/bin/python -m tests.test_agent1_subagents    # Agent 1 sub-agents A/B/C schema contract (live; or pass a|b|c)
venv/bin/python -m tests.test_market_research     # offline caps/storage + live Synthesizer (--full = whole pipeline)
venv/bin/python -m tests.test_agent7              # Agent 7 gate test against fixtures/ (one good ad, one bad)
```

All output/log/fixture paths come from `settings.paths.*` (anchored at `PROJECT_ROOT`), so the
tests check the same absolute locations the tools write to — no hardcoded relative paths.
`test_agent7` copies `fixtures/*.json` into `data/output/` before running the QA agent.
