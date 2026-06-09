# Agent Teams — EcomTalent Marketing Campaign System

AI agent teams that run end-to-end marketing campaigns using the EcomTalent direct-response framework. Configurable LLM backend (Anthropic Claude or OpenAI) and search engine (Brave or DuckDuckGo).

## Structure

```
embroidery/          Working implementation — Market Research agent (Stage 1)
CLAUDE.md            Development rules and architecture guidance for Claude Code
development-plan.md  4-week build plan with per-day tasks and cost estimates
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

| Workflow | Agents | Notes |
|---|---|---|
| Research | Market Research → Avatar Builder + Positioning (parallel) | Stage 1–2 |
| Copy | Hook Generator → Script Writer + Static Copy (parallel) | Stage 3 |
| QA & Feedback | QA gatekeeper → Feedback Analyst | Stage 4 |

Build in stages — validate each before adding the next. See `development-plan.md`.
