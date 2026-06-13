# Avatar Builder Workflow (Agent 2) — Design

**Date:** 2026-06-13
**Status:** Approved design — ready for implementation plan
**Replaces:** Agent 2 "Customer Avatar Builder" (currently a placeholder in the architecture)
**Source methodology:** Evolve Course — Customer & Market Research System (p74470) +
Market Awareness & Sophistication (p140605); the 7-stage (0–7) avatar research spec the user provided.
**Depends on:** the `research` workflow (Agent 1) being able to produce
`market_research_report.json` + `brand_intelligence_report.md` — the avatar engine's inputs.

---

## 1. Goal & context

The custom-embroidery campaign team needs a **deep customer-avatar engine** as Agent 2. Today
Agent 2 is only a name in the architecture (`customer_avatars.md`, written by 2, read by 3–6).
This design builds it for real, automating the Evolve 8-stage avatar-research methodology, and
wiring it into the existing dashboard (Monitor / Test / Edit) like every other workflow.

It is **not** a thin avatar summariser. It discovers and *qualifies* real sub-avatars from live
research, mines verbatim voice-of-customer, maps each priority avatar onto the awareness ×
sophistication matrix, and synthesises an ad-ready Avatar Deep Dive — the ammunition Agents 3–6
(Positioning, Hooks, Scripts, Static Copy) consume.

### Decisions locked during brainstorming

| Decision | Choice |
|---|---|
| **Placement** | Replace **Agent 2 (Customer Avatar Builder)**. Implemented as its own workflow module + **its own dashboard lane** `WorkflowSpec(id="avatar", label="Avatar Builder")`, inserted between `research` and `qa` in `load_workflows()`. |
| **Tooling** | **`web_search` + `web_fetch` only** — no Apify/Browserbase/Firecrawl. Reproduce the Evolve methodology with `site:reddit.com` / `site:amazon.com` / `facebook.com/ads/library` search+fetch (the proven pattern the research sub-agents already use). Scraper-only depth (per-profile Reddit inference, exhaustive ad-library scans) is best-effort. |
| **Scope** | **Lean on the research report.** Live search only for the genuinely new stages (0 onboarding, 1 product, 2 discovery+qualify, 3 VOC). Stages 4/5/6 (awareness, competitor, mechanism) are **re-framed per chosen avatar** from `market_research_report.json` — cheap no-tool reasoning, no duplicate searches, no contradicting the research report. |
| **Control / exposure** | **Every Evolve sub-stage is its own registry `Stage`**, with a **QC gate at every boundary** and **every agent a distinct, individually-testable, prompt-editable row**. The user can pause, edit, quit, or test-slice *any* single step or agent. No coarse 4-gate grouping. |
| **Priority avatars** | Qualifier picks the top **N** (config `avatar.priority_count`, default **2**) for deep-dive. The `qualify` gate is the human override point for *which* avatars proceed. |

> **Deviation note (for `development-plan.md`):** CLAUDE.md's agent hierarchy lists Agent 2
> inside "Workflow 1 — Research". This design makes it a **separate registry workflow / dashboard
> lane** rather than extra stages on the Research lane — cleaner monitoring, and the orchestrator's
> data-contract gate enforces "no research report → avatar blocked" for free. Recorded as a
> deliberate deviation.

---

## 2. Architecture

```
research workflow ──writes──► market_research_report.json + brand_intelligence_report.md
                                          │ (orchestrator data-contract gate: avatar.inputs)
                                          ▼
        ┌──────────────────────── avatar workflow (own lane) ────────────────────────┐
        │  STAGE          AGENT(S)                         TOOLS            GATE       │
        │  onboarding     avatar_onboarder                 fetch URL         ✓         │
        │  product        product_analyst                  fetch + search    ✓         │
        │  discovery      reddit_scout ∥ amazon_voc                                    │
        │                 ∥ fb_ad_scout                    search-only       ✓         │
        │  qualify        avatar_qualifier   ◄── pick top-N priority avatars  ✓ (key)  │
        │  voc            voc_miner                         search-only       ✓         │
        │  awareness      awareness_mapper                  no-tool (reads research) ✓  │
        │  competitor     competitor_teardown              no-tool + light fetch     ✓  │
        │  mechanism      mechanism_builder                 no-tool (reads research) ✓  │
        │  synthesis      avatar_synthesizer                no-tool                  ✓  │
        └──────────────────────────────────────────────────────────────────────────────┘
                                          │
                                          ▼
                       customer_avatars.md  +  avatar_deep_dive.json   (read by Agents 3–6)
```

Like the research workflow, every **search/discovery sub-agent returns a single JSON object as
its final text message** and Python persists it (the gemini-flash `MALFORMED_FUNCTION_CALL`
lesson — flash cannot emit large `write_file` payloads). The **synthesizer is tool-less** and
returns the markdown doc as text; Python writes `customer_avatars.md`. Reframer agents
(awareness/competitor/mechanism) are tool-less and read the research report passed in as context.

The dashboard, gates, Test panel, prompt editor, and per-agent step pipelines all work
**generically off the registry** — no new endpoints, no per-workflow UI code.

---

## 3. Stage-by-stage specification

Each stage runs inside `reporter.workflow_context("avatar")`, publishes a `stage` event, runs
its agent(s), then `await gate(stage, digest, workflow="avatar", request=brief)`. `EDIT` re-runs
the stage with an adjusted brief/request; `QUIT` returns `None`; `APPROVE` advances. Standalone
runs auto-approve (`EMBROIDERY_YES=1` / no subscriber). `start_stage`/`stop_stage` slice the run
(same `_active()` helper as `research`); skipped upstream stages load their outputs from disk
(prior run or seeded fixture).

### Stage 0 — `onboarding` · agent `avatar_onboarder`
First-time-visitor onboarding. Fetches the product URL with "fresh eyes" and answers the 11
onboarding questions (Q1–Q11 from the source spec) as the *before-research baseline* — never
updated later.
**Tools:** `web_fetch` (the product/shop URL from the brief).
**Output (Python writes):** `avatar_onboarding.json` — `{ "Q1": "...", ..., "Q11": "..." }`.

### Stage 1 — `product` · agent `product_analyst`
Product Understanding Map: Feature→Benefit→Emotional-payoff table, Claims audit
(Believable/Unique/Provable 1–5, flag <3), Objections log (price/trust/fit/urgency/skepticism/
comparison), Competitive advantages.
**Tools:** `web_fetch` + light `web_search` (spec sheets, comparisons).
**Output:** `avatar_product.json` — `{ features_map, claims_audit, objections, advantages }`.

### Stage 2a — `discovery` · agents `reddit_scout` ∥ `amazon_voc` ∥ `fb_ad_scout` (parallel)
Three search-only sub-agents run concurrently (`asyncio.gather`), sharing the per-run search
budget (`reset_searches=False`), each adapted to the embroidery shop's **four segments**
(A Team Pride · B Gift Giver · C Brand Builder · D Aesthetic Buyer):

- **`reddit_scout`** — `site:reddit.com` searches for embroidery/personalised-gift/custom-apparel
  communities; clusters people by *shared struggle*, extracts verbatim quotes, infers
  who/occasion/emotion. Output `avatar_discovery_reddit.json` — list of cluster objects
  `{ cluster_name, who_they_are, their_occasion, verbatim_quotes[], dominant_emotion, estimated_size }`.
- **`amazon_voc`** — Amazon/Etsy review mining (top products by review count); buyer types,
  purchase triggers, verbatim emotional language, recurring buzzwords, competitor failure modes
  from 1–2★, price-sensitivity signals. Output `avatar_discovery_amazon.json`.
- **`fb_ad_scout`** — fetches `facebook.com/ads/library` result pages (best-effort without a
  scraper); for each ad: creative description, verbatim headline/text, targeted avatar, run-length
  proxy, sophistication S1–S5; then avatar-gap analysis (heavily-targeted vs under-served avatars,
  dominant sophistication). Output `avatar_discovery_fb.json`.

### Stage 2b — `qualify` · agent `avatar_qualifier` (no-tool) · **key human gate**
Reads the three discovery files + research report. Scores every candidate on the Evolve 4-gate
framework (Desire magnitude / Competition-inverted / Economic ability / Scalability, 1–5 each);
PASS if all ≥3, FAIL if any <2; ranks them. Selects the top `priority_count` (default 2).
**Gate:** the user reviews the ranked table and may `EDIT` to override the selection (e.g. force
a specific avatar through, or change `priority_count`). This is the most important
human-in-the-loop decision in the workflow.
**Output:** `avatar_qualification.json` — `{ candidates: [ {…scores, total, verdict} ], priority_avatars: [name, …] }`.

### Stage 3 — `voc` · agent `voc_miner` (search-only)
For each priority avatar: mine verbatim quotes across YouTube comments, TikTok comments, Facebook
groups (+ import the Reddit/Amazon quotes already collected in Stage 2). Codes each quote into
`[PAIN] [DESIRE] [BELIEF] [TRIGGER] [OBJECTION] [VICTORY] [IDENTITY]`, with source, insight, and
`ad_potential`. Flags **self-identification** quotes ("as a grandma of twins…") as gold. Target
≥50 coded quotes total.
**Output:** `avatar_voc.json` — `{ priority_avatar: [ { quote, source, category[], insight, ad_potential } ] }`.

### Stage 4 — `awareness` · agent `awareness_mapper` (no-tool, reads research report)
Per priority avatar: diagnose **awareness stage** (Unaware→Most Aware) from the VOC evidence, and
**sophistication stage** (S1–S5) from the research report's `sophistication_assessment` +
`awareness_levels_by_segment` (no new searches — the research report already established the
market level). Prescribe the ad entry point, the "carry-the-conversation-forward" arc, the
differentiation lever (claim / mechanism / identity), and 3 hook formulas. Returns the mapping as
JSON (carried in-memory to synthesis; optionally persisted as `avatar_awareness.json`).

### Stage 5 — `competitor` · agent `competitor_teardown` (no-tool + light fetch)
Reuses the research report's `competitors` list; tears down the top 3 vs the priority avatars —
offer-stack audit, claims audit (proof yes/no), messaging weaknesses from negative reviews,
opportunity gaps, alternative-solutions audit (what the avatar does *instead* + each alternative's
flaw = the competitive angle). Light `web_fetch` only to fill a specific gap.

### Stage 6 — `mechanism` · agent `mechanism_builder` (no-tool, reads research report)
Reuses the research report's `unique_mechanism_candidates`; builds **objection reframes**
(analogy / category / belief-breaking / authority) and the **solution-mechanism map**
(core problem → root cause → how product addresses it → why alternatives fail → feature that
makes it real). Runs the NEW/OBVIOUS/COMPLETE 1–5 credibility check; flags <3 for revision.

### Stage 7 — `synthesis` · agent `avatar_synthesizer` (no-tool, large context)
Merges Stages 0–6 into the **Avatar Deep Dive** per priority avatar. Non-negotiables from the
source spec: include **every** verbatim quote (no sampling/dedup), preserve original customer
language, every quote gets an insight. Emits two artifacts:
- **`customer_avatars.md`** — the human-readable deep-dive doc (the data contract Agents 3–6 read),
  following the source template (snapshot, demographics, occasion map, desire chain, awareness/
  sophistication, full VOC by code, competitor-gap map, solution mechanism, objection reframes,
  ad angles, hooks).
- **`avatar_deep_dive.json`** — structured mirror for the future Positioning agent
  (one object per priority avatar).

---

## 4. Module layout (mirrors `agents/research/`)

```
embroidery/agents/avatar/
  __init__.py
  framing.py       # Stage 0 onboarder + Stage 1 product_analyst (search/fetch → JSON-as-text)
  discovery.py     # Stage 2: reddit_scout / amazon_voc / fb_ad_scout (search-only) + avatar_qualifier (no-tool)
  voc.py           # Stage 3 voc_miner (search-only)
  reframe.py       # Stages 4/5/6: awareness_mapper / competitor_teardown / mechanism_builder (no-tool)
  synthesizer.py   # Stage 7 avatar_synthesizer (no-tool) → customer_avatars.md + avatar_deep_dive.json
  pipeline.py      # run_avatar_builder(): stages + gates + start/stop slicing; register(WorkflowSpec); __main__
  README.md        # per-workflow README (CLAUDE.md README rule) — what it does, run cmd, files, workflow chart
```

Shared helpers reused from `core/` and `agents/research/`: `run_agent`, `reset_search_count`,
`SEARCH_TOOLS`, `parse_json_output` (lift to a shared util or re-import), `get_prompt_store` /
`to_dollar` / `render`, `checkpoint` / `Decision`, `get_reporter` / `workflow_context`.

Each sub-agent follows the `SubAgentSpec` pattern (key, name, system_template, kickoff, model_key,
output_file) so prompts are uniform and `prompt_catalog()` is mechanical.

---

## 5. Data contracts

| File | Direction | Notes |
|---|---|---|
| `market_research_report.json` | **read** (input) | from Agent 1; feeds qualify/awareness/competitor/mechanism |
| `brand_intelligence_report.md` | **read** (input) | from Agent 1; product/market narrative context |
| `customer_avatars.md` | **write** (output) | the contract Agents 3–6 consume |
| `avatar_deep_dive.json` | **write** (output) | structured mirror for the future Positioning agent |
| `avatar_onboarding.json`, `avatar_product.json`, `avatar_discovery_{reddit,amazon,fb}.json`, `avatar_qualification.json`, `avatar_voc.json` | write (intermediate) | under `data/output/`; enable per-stage Test slicing |

`WorkflowSpec` declares `inputs=[market_research_report.json, brand_intelligence_report.md]`,
`outputs=[customer_avatars.md, avatar_deep_dive.json]`. The orchestrator asserts inputs exist
before the workflow starts → **no research report ⇒ avatar blocked** (publishes a `blocked` event),
exactly like the existing Copy gate.

---

## 6. Model allocation (new `config.yaml` keys under `agents:`)

| Agent(s) | Model | Why |
|---|---|---|
| `avatar_onboarder`, `product_analyst`, `reddit_scout`, `amazon_voc`, `fb_ad_scout`, `voc_miner` | `gemini-2.5-flash` | search-only, JSON-as-text — flash-safe & cheap |
| `avatar_qualifier`, `awareness_mapper`, `competitor_teardown`, `mechanism_builder`, `avatar_synthesizer` | `gemini-2.5-pro` | reasoning / long-context, no tools (CLAUDE.md target tier for Avatar = Sonnet-equivalent) |

New config block: `avatar: { priority_count: 2 }`. Search budget reuses existing
`search.max_searches` / `search.max_searches_per_agent` code caps — no new cap logic.

---

## 7. Monitor / Test / Edit (the three pillars)

- **Monitor** — all ~11 agent rows stream into the `avatar` lane the moment each starts, grouped by
  the 9 stages; the parallel `discovery` trio shows as 3 horizontal rows; each row expands into its
  step pipeline (call/search/fetch/write) → inline output viewer. Crashes surface as `done`/`error`.
- **Test** — `start_stage`/`stop_stage` slice to **any single stage or agent**; committed fixtures
  `fixtures/market_research_report.json` + `fixtures/brand_intelligence_report.md` seed the inputs
  via `seed_fixtures` so the workflow (or one stage) runs in isolation; `target="avatar"` in
  `POST /start` runs it standalone; prompt edits dry-run via `POST /prompts/preview`.
- **Edit** — every agent system prompt is in `prompt_catalog()` (⚙ Agent prompts); the brief/request
  is editable at **every** gate via the `EDIT` decision; `priority_count` overridable at the
  `qualify` gate.

---

## 8. Testing

- `tests/test_avatar_stages.py` — `_active()` stage slicing (each stage individually), JSON parsing
  of each sub-agent output, qualifier scoring math (PASS/FAIL gates), synthesizer artifact shape.
- `tests/test_workflow.py` (extend) — assert `avatar` registers with the correct
  `inputs`/`outputs`/`stages`, and that `load_workflows()` includes it in research→avatar→qa order.
- `tests/test_orchestrator.py` (extend) — assert the data-contract gate blocks `avatar` when
  `market_research_report.json` is absent.
- Fixtures committed under `fixtures/` (research outputs) so every avatar test is offline/deterministic.

---

## 9. Docs to update (per CLAUDE.md README + plan-status rules)

- **New:** `embroidery/agents/avatar/README.md` (what it does, run command, per-file purpose, workflow chart).
- **Update:** `embroidery/agents/README.md` (index — add the avatar workflow), `embroidery/README.md`
  (top-level, if it lists workflows).
- **Update CLAUDE.md:** architecture diagram (add avatar lane), agent-hierarchy block, the
  data-contract table (avatar inputs/outputs + intermediates), the tool-access list, build order,
  and `load_workflows()` reference.
- **Update `development-plan.md`:** check off Agent 2, record the "separate lane" deviation.

---

## 10. Out of scope (YAGNI)

- No Apify/Browserbase/Firecrawl integration (revisit only if search+fetch depth proves insufficient).
- No new web endpoints — the generic registry surface is sufficient.
- No changes to Agents 1, 3–8 beyond reading the new `customer_avatars.md` contract (already their
  declared input).
- No per-quote content drill-down in the dashboard beyond the existing step-pipeline output viewer.
