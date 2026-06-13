# Avatar Builder (Agent 2)

Deep customer-avatar engine — the Evolve 9-stage methodology. Consumes Agent 1's research report
and produces the avatar deep-dive that Agents 3–6 (Positioning, Hooks, Scripts, Static Copy) read.

## Run
```bash
# standalone (auto-approves gates; needs the research outputs or seeded fixtures in data/output/)
cd embroidery && venv/bin/python -m embroidery.agents.avatar.pipeline --yes
# with the live dashboard + interactive gates
cd embroidery && venv/bin/python -m embroidery.web   # target="avatar" in the Test/Run panel
```

## Files
| File | Purpose |
|---|---|
| `_common.py` | `AvatarAgent` + `run_json_agent` + prompt-catalog helpers shared by every stage |
| `framing.py` | Stage 0 onboarder + Stage 1 product analyst |
| `discovery.py` | Stage 2 parallel scouts (Reddit/Amazon/FB) + 4-gate qualifier |
| `voc.py` | Stage 3 voice-of-customer miner |
| `reframe.py` | Stages 4/5/6 reframers (awareness / competitor / mechanism), no tools |
| `synthesizer.py` | Stage 7 — writes `customer_avatars.md` + `avatar_deep_dive.json` |
| `pipeline.py` | 9-stage gated orchestration + `WorkflowSpec` registration |

## Data contracts
- **Reads:** `market_research_report.json`, `brand_intelligence_report.md` (Agent 1)
- **Writes:** `customer_avatars.md`, `avatar_deep_dive.json` (read by Agents 3–6)
- **Intermediate (per stage, for Test slicing + the dashboard output viewer):**
  `avatar_onboarding.json`, `avatar_product.json`, `avatar_discovery_{reddit,amazon,fb}.json`,
  `avatar_qualification.json`, `avatar_voc.json`, `avatar_awareness.json`, `avatar_competitor.json`,
  `avatar_mechanism.json`

## Workflow chart
```
market_research_report.json + brand_intelligence_report.md   (orchestrator data-contract gate)
        │
        ▼  [gate after every stage: Approve / Edit / Quit]
 onboarding ─► product ─► discovery (reddit ∥ amazon ∥ fb) ─► qualify ◄─ pick top-N avatars
        │
        ▼
   voc ─► awareness ─► competitor ─► mechanism ─► synthesis
        │
        ▼
 customer_avatars.md + avatar_deep_dive.json   ─►  Agents 3–6
```
