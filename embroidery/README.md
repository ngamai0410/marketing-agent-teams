# embroidery/ — Market Research Agent (Stage 1)

Provider-agnostic agentic loop for the custom embroidery shop campaign. LLM engine and search engine are configured in `config.yaml` — no code changes needed to switch.

## Setup

```bash
# Python 3.11 required (system Python 3.14 has a broken pip on this machine)
~/.pyenv/versions/3.11.9/bin/python3 -m venv venv
venv/bin/pip install "anthropic>=0.40" aiohttp python-dotenv rich pyyaml openai duckduckgo-search

# API keys
cp .env.example .env
# edit .env and add your keys
```

## Running

```bash
# Smoke test — verifies agentic loop, tool execution, and file write
venv/bin/python smoke_test.py
```

## Configuration — `config.yaml`

All settings live here. No other file needs to change.

```yaml
llm:
  provider: anthropic     # or: openai

search:
  provider: duckduckgo    # or: brave (requires BRAVE_API_KEY)
  max_searches: 20        # per-run cap to control costs

agents:
  audience_researcher:
    model: claude-haiku-4-5   # change to sonnet/opus after prompt is validated
    max_tokens: 8096
```

## Files

| File | Purpose |
|---|---|
| `config.yaml` | All settings — provider, model per agent, search engine, paths |
| `config.py` | Loads `config.yaml` + env vars into typed `Config` / `ModelSettings` objects |
| `llm.py` | `AnthropicProvider` and `OpenAIProvider` — both implement `LLMProvider` |
| `search.py` | `BraveSearch` and `DuckDuckGoSearch` — both implement `SearchProvider` |
| `agent_loop.py` | `run_agent()` — the single agentic loop used by every agent |
| `smoke_test.py` | Verifies the full stack end-to-end with two tool calls |
| `.env` | API keys (gitignored) |
| `.env.example` | Key names with placeholder values (committed) |

## Adding a new agent

1. Write a system prompt string.
2. Define tool schemas in Anthropic JSON format.
3. Add an entry under `agents:` in `config.yaml` with the target model.
4. Call `run_agent(system, messages, tools, settings.agents.<your_agent>)`.

The loop, tool execution, usage logging, and search limits are all handled automatically.

## Env keys

| Key | Required when |
|---|---|
| `ANTHROPIC_API_KEY` | `llm.provider: anthropic` |
| `OPENAI_API_KEY` | `llm.provider: openai` |
| `BRAVE_API_KEY` | `search.provider: brave` |
