# embroidery/core/ — reusable framework kernel

Provider-agnostic infrastructure shared by every agent. Nothing here is campaign-specific;
this is the layer you would keep when starting a non-embroidery campaign.

```
config.yaml ─► config.py ─► settings (typed Config/ModelSettings; PROJECT_ROOT-anchored paths)
                  │
   ┌──────────────┼───────────────┐
   ▼              ▼                ▼
 llm.py        search.py        logger.py
 Anthropic|    Brave|           INFO→stdout
 OpenAI|       DuckDuckGo       DEBUG→data/logs/<run_id>.log
 Gemini            │                │
   └──────┬────────┴────────────────┘
          ▼
      agent_loop.py  run_agent()  ──uses──►  tools.py  (RESEARCH/SEARCH/FILE_TOOLS schemas)
          │                                  brand_store.py  BrandAI (timestamped history)
          ▼
      data/output/   (write_file/read_file tool target)
```

| File | Purpose |
|---|---|
| `config.py` | Loads `config.yaml` + env into typed `Config`/`ModelSettings`; exposes `settings`, `PROJECT_ROOT`. **Import settings from here — never read env directly.** |
| `llm.py` | `AnthropicProvider`, `OpenAIProvider`, `GeminiProvider` — all implement `LLMProvider`. Tool schemas are authored in Anthropic format; converted to OpenAI/Gemini internally. |
| `search.py` | `BraveSearch`, `DuckDuckGoSearch` — both implement `SearchProvider`. |
| `logger.py` | `get_logger(name)` — shared sink: INFO→stdout, DEBUG→`data/logs/<run_id>.log`. |
| `agent_loop.py` | `run_agent()` — the single agentic loop used by every agent; tool execution + search caps live here. |
| `tools.py` | Tool schemas: `RESEARCH_TOOLS`, `SEARCH_TOOLS` (no write), `FILE_TOOLS`. |
| `brand_store.py` | `BrandAI` — timestamped research history per shop under `data/brand_ai/<shop>/`. |

All cross-imports use the package path, e.g. `from embroidery.core.config import settings`.
