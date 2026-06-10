# Agent Teams — EcomTalent Marketing Campaign System

AI agent teams that run end-to-end marketing campaigns using the EcomTalent direct-response framework. Configurable LLM backend (Anthropic Claude, OpenAI, or Gemini) and search engine (Brave or DuckDuckGo).

## Workflow

```
Product brief
     │
     ▼
┌─────────────────────────────────────────────────────────┐
│  Workflow 1 — Research                                  │
│                                                         │
│  Agent 1: Market Research ──► brand_intelligence_report │
│      │                        market_research_report    │
│      ├──► Agent 2: Avatar Builder ──► customer_avatars  │
│      └──► Agent 3: Positioning   ──► positioning_matrix │
└─────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────┐
│  Workflow 2 — Copy Production                           │
│                                                         │
│  Agent 4: Hook Generator ──► hooks_library              │
│      ├──► Agent 5: Script Writer  ──► video_scripts     │
│      └──► Agent 6: Static Copy   ──► static_ad_copy     │
└─────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────┐
│  Workflow 3 — QA & Feedback                             │
│                                                         │
│  Agent 7: QA (blocking gate) ──┐                        │
│      PASS ──► client           │ FAIL ──► back to 5/6  │
│                                                         │
│  Agent 8: Feedback Analyst (post-launch)                │
│      ad_performance.csv ──► weekly_learnings            │
│                          ──► next_week_brief            │
└─────────────────────────────────────────────────────────┘
```

## Structure

```
embroidery/          Working implementation — Agent 1 (Market Research) + Agent 7 (QA)
CLAUDE.md            Development rules and architecture guidance for Claude Code
development-plan.md  4-week build plan with per-day tasks, cost estimates, and a
                     status header — updated at the end of every working day (CLAUDE.md rule)
ai-agent-team-embroidery-marketing.md   Canonical 8-agent architecture reference
market-research-agent-embroidery.html   Detailed Market Research agent build plan
```

## Quick start

```bash
cd embroidery
# Add your API key
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env

# Run smoke test (verifies loop + tools)
/path/to/embroidery/venv/bin/python smoke_test.py
```

See `embroidery/README.md` for full setup and configuration.

## System overview

8 specialist agents organized in 3 workflows:

| Workflow | Agents |
|---|---|
| Research | Market Research → Avatar Builder + Positioning (parallel) |
| Copy | Hook Generator → Script Writer + Static Copy (parallel) |
| QA & Feedback | QA gatekeeper → Feedback Analyst |

See `development-plan.md` for the build schedule and stage gates.
