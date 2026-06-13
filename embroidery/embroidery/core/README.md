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
          │   │                              brand_store.py  BrandAI (timestamped history)
          │   └──emit──► reporter.py  RunReporter (per-agent metrics + async pub/sub)
          ▼                              │ events  (workflow field on every row)
      data/output/   (write_file/        ▼
        read_file tool target)       checkpoint.py  await checkpoint(workflow=) ──► QC gate
                                      (Approve / Edit & re-run / Quit; auto-approve headless)
                                               │
              workflow.py  WorkflowSpec registry ◄── each pipeline module registers itself
                  │
              orchestrator.py  run_team()  ──► walks registry [start..stop]
                  │  data-contract input gate (blocked event if inputs missing)
                  │  QA FAIL re-loop (back to copy, bounded by max_qa_loops)
                  └──► owns run-level done/aborted/blocked event + run_report.md
```

The reporter + checkpoint pair is the **monitoring / human-in-the-loop layer** the web
dashboard (`embroidery/web/`) drives. `run_agent()` emits lifecycle events
(start / call / search / done) to the reporter; a stage calls `checkpoint()` between
hand-offs to pause for the user. Both are no-ops without a subscriber, so standalone CLI
runs and tests are unaffected.

`workflow.py` + `orchestrator.py` are the **team-level layer**: each pipeline module
registers a `WorkflowSpec` at import, and `run_team()` iterates the registry to drive
the whole campaign without per-workflow code.

| File | Purpose |
|---|---|
| `config.py` | Loads `config.yaml` + env into typed `Config`/`ModelSettings`; exposes `settings`, `PROJECT_ROOT`. **Import settings from here — never read env directly.** |
| `llm.py` | `AnthropicProvider`, `OpenAIProvider`, `GeminiProvider` — all implement `LLMProvider`. Tool schemas are authored in Anthropic format; converted to OpenAI/Gemini internally. |
| `search.py` | `BraveSearch`, `DuckDuckGoSearch` — both implement `SearchProvider`. |
| `logger.py` | `get_logger(name)` — shared sink: INFO→stdout, DEBUG→`data/logs/<run_id>.log`. |
| `agent_loop.py` | `run_agent()` — the single agentic loop used by every agent; tool execution + search caps live here. Emits metrics to `reporter.py`. |
| `tools.py` | Tool schemas: `RESEARCH_TOOLS`, `SEARCH_TOOLS` (no write), `FILE_TOOLS`. |
| `brand_store.py` | `BrandAI` — timestamped research history per shop under `data/brand_ai/<shop>/`. |
| `reporter.py` | `RunReporter` singleton (`get_reporter()`): per-agent metrics (calls/tokens/searches/$/elapsed), async pub/sub bus, `render_markdown()` → `data/output/run_report.md`. `PRICES` table is the single source of cost truth. `AgentRecord` carries a `workflow` field (first key in `as_row()`); `workflow_context(id)` contextmanager (contextvar) tags each row with its workflow lane so the dashboard can group agents. |
| `checkpoint.py` | `await checkpoint(stage, digest, *, workflow="", request=...)` — the QC gate. Carries `workflow` in the published `gate` event and in `open_gates()`. Blocks until `resolve_gate()` (POST /gate); returns a `Decision` (APPROVE/EDIT/QUIT). Auto-approves when `EMBROIDERY_YES=1` or no dashboard is attached. |
| `prompt_store.py` | `get_prompt_store()` + `to_dollar()`. Lets the user view/edit/save each agent's **system prompt** before a run. Converts `.format` templates (`{{}}`-escaped) to brace-safe `$placeholder` form, persists overrides to `data/prompts/overrides.json`, renders via `Template.safe_substitute` (a removed placeholder degrades gracefully). |
| `workflow.py` | `WorkflowSpec` registry — the single source of truth for the agent team. `Stage(name, agents, digest=None)` + `WorkflowSpec(id, label, stages, entry_point, prompt_catalog, inputs, outputs, fixtures, config_schema)`. `register(spec)` / `get_registry()` / `get_spec(id)` / `clear_registry()` (test helper). `load_workflows()` imports pipeline modules in canonical order (research → qa; tolerant of not-yet-built ones); called once at web startup and by `run_team`. |
| `orchestrator.py` | `run_team(brief, *, start, stop, start_stage, stop_stage, gate, max_qa_loops=2)` — generic team runner. Slices the registry to [start..stop]; before each workflow asserts its declared `inputs` exist under `data/output` (data-contract gate — publishes `blocked` done event if any file is missing); runs each `entry_point` inside `reporter.workflow_context(id)`; after `qa` reads `qa_report.json` and re-loops back to `copy` on overall FAIL (bounded by `max_qa_loops`). Owns the run-level `done`/`aborted`/`blocked` event and writes `data/output/run_report.md`. |

All cross-imports use the package path, e.g. `from embroidery.core.config import settings`.
Adding a new workflow = write its pipeline module, call `register(WorkflowSpec(...))` at
import, and ensure `load_workflows()` can find it (add to the import list in `workflow.py`
if it is not already there). The web layer and orchestrator need no changes.
