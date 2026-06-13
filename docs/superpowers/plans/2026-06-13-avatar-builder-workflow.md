# Avatar Builder Workflow (Agent 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Agent 2 — the Customer Avatar Builder — as a 9-stage Evolve avatar engine on its own dashboard lane, consuming Agent 1's research report and producing `customer_avatars.md` + `avatar_deep_dive.json`.

**Architecture:** A new `embroidery/agents/avatar/` package registers `WorkflowSpec(id="avatar")` with 9 sequential stages (one parallel fan-out at `discovery`). Each stage runs one or more agents via the existing `run_agent()` loop; search/discovery agents return JSON as final text (Python persists it — the gemini-flash `MALFORMED_FUNCTION_CALL` workaround), reframe/synthesis agents are tool-less and read the research report. A QC gate (`core/checkpoint.py`) fires at every stage boundary; `start_stage`/`stop_stage` slice the run; skipped stages load their outputs from disk. The dashboard, Test panel, and prompt editor pick it up generically off the registry — no new endpoints.

**Tech Stack:** Python 3.11 (asyncio), Gemini (flash for search agents, pro for reasoning), the existing `core/` kernel (`agent_loop`, `checkpoint`, `reporter`, `workflow`, `prompt_store`, `config`). Tests are plain script-style (`def main() -> int`, `check()` asserts, run via `python -m tests.<name>`) — **no pytest**.

**Reference spec:** `docs/superpowers/specs/2026-06-13-avatar-builder-workflow-design.md`

**Conventions to follow exactly:**
- Run everything from `embroidery/` as modules: `cd embroidery && venv/bin/python -m ...`.
- Prompt templates are `.format` strings: `{placeholder}` for context, `{{` / `}}` for **literal JSON braces**. `to_dollar()` converts `{x}`→`$x` for the editor; `store.render(id, to_dollar(template), **ctx)` renders via `safe_substitute`.
- Always pass `agent_name=` to `run_agent()`.
- Commit after every task. We are on branch `spec-avatar-builder-workflow` (continue on it, or branch from it).

**Refinement over the spec (intentional):** every one of the 11 agents persists a JSON output file (the spec called reframer persistence "optional"). This makes `start_stage` slicing work for `synthesis` and makes every step inspectable in the dashboard output viewer.

**Full intermediate/output file list (all under `data/output/`):**
`avatar_onboarding.json`, `avatar_product.json`, `avatar_discovery_reddit.json`, `avatar_discovery_amazon.json`, `avatar_discovery_fb.json`, `avatar_qualification.json`, `avatar_voc.json`, `avatar_awareness.json`, `avatar_competitor.json`, `avatar_mechanism.json` (intermediate) · `avatar_deep_dive.json`, `customer_avatars.md` (data-contract outputs).

---

## File Structure

| File | Responsibility |
|---|---|
| `embroidery/embroidery/core/config.py` (modify) | add `AvatarSettings(priority_count)` + 11 new agent `ModelSettings` fields + parse `avatar:` block |
| `embroidery/config.yaml` (modify) | add the 11 avatar agent model rows + `avatar.priority_count` |
| `embroidery/embroidery/agents/avatar/__init__.py` (create) | package marker |
| `embroidery/embroidery/agents/avatar/_common.py` (create) | `AvatarAgent` dataclass, `build_system`, `run_json_agent`, `catalog_items` — shared agent plumbing |
| `embroidery/embroidery/agents/avatar/framing.py` (create) | Stage 0 `avatar_onboarder` + Stage 1 `product_analyst` |
| `embroidery/embroidery/agents/avatar/discovery.py` (create) | Stage 2 `reddit_scout`/`amazon_voc`/`fb_ad_scout` + `avatar_qualifier` |
| `embroidery/embroidery/agents/avatar/voc.py` (create) | Stage 3 `voc_miner` |
| `embroidery/embroidery/agents/avatar/reframe.py` (create) | Stages 4/5/6 `awareness_mapper`/`competitor_teardown`/`mechanism_builder` |
| `embroidery/embroidery/agents/avatar/synthesizer.py` (create) | Stage 7 `avatar_synthesizer` → 2 files |
| `embroidery/embroidery/agents/avatar/pipeline.py` (create) | orchestrate stages + gates + slicing; `register(WorkflowSpec)`; `__main__` |
| `embroidery/embroidery/agents/avatar/README.md` (create) | per-workflow README + workflow chart |
| `embroidery/embroidery/core/workflow.py` (modify) | add avatar module to `load_workflows()` order |
| `embroidery/fixtures/market_research_report.json` (create) | seed input for offline avatar runs |
| `embroidery/fixtures/brand_intelligence_report.md` (create) | seed input for offline avatar runs |
| `embroidery/tests/test_avatar_common.py` (create) | unit test for `_common.py` plumbing |
| `embroidery/tests/test_avatar_stages.py` (create) | behavioral test: registration + slicing + gate EDIT/QUIT |
| `embroidery/embroidery/agents/README.md` (modify) | index: add avatar workflow |
| `CLAUDE.md` (modify) | architecture diagram, agent hierarchy, data-contract table, tool access, build order |
| `development-plan.md` (modify) | check off Agent 2; record the "separate lane" deviation |

---

## Task 1: Config — avatar settings + agent models

**Files:**
- Modify: `embroidery/embroidery/core/config.py`
- Modify: `embroidery/config.yaml`
- Test: `embroidery/tests/test_avatar_common.py` (created here, extended in Task 2)

- [ ] **Step 1: Write the failing test**

Create `embroidery/tests/test_avatar_common.py`:

```python
"""
Unit tests for avatar config + _common.py plumbing. No providers, no tokens.

Run: cd embroidery && venv/bin/python -m tests.test_avatar_common
"""
import sys

failures: list[str] = []

def check(cond, msg):
    print(("✓ " if cond else "✗ ") + msg)
    if not cond:
        failures.append(msg)

def test_config():
    from embroidery.core.config import settings
    check(settings.avatar.priority_count == 2, "avatar.priority_count defaults to 2 from config.yaml")
    for name in ("avatar_onboarder", "product_analyst", "reddit_scout", "amazon_voc",
                 "fb_ad_scout", "avatar_qualifier", "voc_miner", "awareness_mapper",
                 "competitor_teardown", "mechanism_builder", "avatar_synthesizer"):
        check(hasattr(settings.agents, name), f"settings.agents has {name}")

def main() -> int:
    test_config()
    if failures:
        print(f"\n✗ test_avatar_common FAILED ({len(failures)})")
        return 1
    print("\n✓ test_avatar_common passed")
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd embroidery && venv/bin/python -m tests.test_avatar_common`
Expected: FAIL — `AttributeError: 'Config' object has no attribute 'avatar'` (or AgentSettings missing fields).

- [ ] **Step 3: Add the avatar agent fields to `AgentSettings`**

In `config.py`, inside `class AgentSettings`, after the `orchestrator` field (line ~46) add:

```python
    # --- Avatar Builder (Agent 2) sub-agents ---
    avatar_onboarder: ModelSettings = field(default_factory=lambda: ModelSettings("claude-haiku-4-5"))
    product_analyst: ModelSettings = field(default_factory=lambda: ModelSettings("claude-haiku-4-5"))
    reddit_scout: ModelSettings = field(default_factory=lambda: ModelSettings("claude-haiku-4-5"))
    amazon_voc: ModelSettings = field(default_factory=lambda: ModelSettings("claude-haiku-4-5"))
    fb_ad_scout: ModelSettings = field(default_factory=lambda: ModelSettings("claude-haiku-4-5"))
    avatar_qualifier: ModelSettings = field(default_factory=lambda: ModelSettings("claude-sonnet-4-6"))
    voc_miner: ModelSettings = field(default_factory=lambda: ModelSettings("claude-haiku-4-5"))
    awareness_mapper: ModelSettings = field(default_factory=lambda: ModelSettings("claude-sonnet-4-6"))
    competitor_teardown: ModelSettings = field(default_factory=lambda: ModelSettings("claude-sonnet-4-6"))
    mechanism_builder: ModelSettings = field(default_factory=lambda: ModelSettings("claude-sonnet-4-6"))
    avatar_synthesizer: ModelSettings = field(default_factory=lambda: ModelSettings("claude-sonnet-4-6", 16000))
```

- [ ] **Step 4: Add `AvatarSettings` + wire into `Config`**

In `config.py`, after `class WebSettings` (line ~61) add:

```python
@dataclass
class AvatarSettings:
    priority_count: int = 2   # how many qualified avatars get a deep-dive
```

In `class Config`, after the `web:` field add:

```python
    avatar: AvatarSettings = field(default_factory=AvatarSettings)
```

In `load_config()`, after `web_raw = raw.get("web", {})` add:

```python
    avatar_raw = raw.get("avatar", {})
```

and in the returned `Config(...)`, after the `web=WebSettings(...)` block add:

```python
        avatar=AvatarSettings(
            priority_count=avatar_raw.get("priority_count", 2),
        ),
```

- [ ] **Step 5: Add the config.yaml rows**

In `embroidery/config.yaml`, inside `agents:` after the `orchestrator:` block add:

```yaml
  # --- Avatar Builder (Agent 2) ---
  avatar_onboarder:    { model: gemini-2.5-flash, max_tokens: 8096 }
  product_analyst:     { model: gemini-2.5-flash, max_tokens: 8096 }
  reddit_scout:        { model: gemini-2.5-flash, max_tokens: 16000 }
  amazon_voc:          { model: gemini-2.5-flash, max_tokens: 16000 }
  fb_ad_scout:         { model: gemini-2.5-flash, max_tokens: 16000 }
  avatar_qualifier:    { model: gemini-2.5-pro,   max_tokens: 8096 }
  voc_miner:           { model: gemini-2.5-flash, max_tokens: 16000 }
  awareness_mapper:    { model: gemini-2.5-pro,   max_tokens: 8096 }
  competitor_teardown: { model: gemini-2.5-pro,   max_tokens: 8096 }
  mechanism_builder:   { model: gemini-2.5-pro,   max_tokens: 8096 }
  avatar_synthesizer:  { model: gemini-2.5-pro,   max_tokens: 16000 }
```

And after the `web:` block (top level) add:

```yaml
# ─────────────────────────────────────────────
# Avatar Builder (Agent 2)
# ─────────────────────────────────────────────
avatar:
  priority_count: 2     # number of qualified avatars to deep-dive
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd embroidery && venv/bin/python -m tests.test_avatar_common`
Expected: PASS — all config checks ✓.

- [ ] **Step 7: Commit**

```bash
git add embroidery/embroidery/core/config.py embroidery/config.yaml embroidery/tests/test_avatar_common.py
git commit -m "Avatar: config — priority_count + 11 agent model settings"
```

---

## Task 2: `_common.py` — shared agent plumbing

**Files:**
- Create: `embroidery/embroidery/agents/avatar/__init__.py`
- Create: `embroidery/embroidery/agents/avatar/_common.py`
- Test: `embroidery/tests/test_avatar_common.py` (extend)

- [ ] **Step 1: Create the package marker**

Create `embroidery/embroidery/agents/avatar/__init__.py` with a single line:

```python
"""Agent 2 — Customer Avatar Builder (Evolve 9-stage avatar engine)."""
```

- [ ] **Step 2: Write the failing test (extend test_avatar_common.py)**

Add to `test_avatar_common.py` above `main()`:

```python
def test_common():
    import asyncio
    from embroidery.agents.avatar import _common as C

    agent = C.AvatarAgent(
        name="probe_agent", label="Probe", model_key="avatar_onboarder",
        system_template="Hello {who}. Schema: {{\"k\": 1}}", output_file=None,
    )
    rendered = C.build_system(agent, who="world")
    check("Hello world" in rendered, "build_system substitutes context placeholders")
    check('{"k": 1}' in rendered, "build_system preserves literal JSON braces")

    # run_json_agent: stub run_agent, assert it parses + (here) does not write
    captured = {}
    async def fake_run_agent(*, system, messages, tools, model_settings, max_tool_calls, agent_name):
        captured["agent_name"] = agent_name
        return '{"ok": true}'
    C.run_agent = fake_run_agent
    out = asyncio.run(C.run_json_agent(agent, "go", tools=[], ctx={"who": "x"}))
    check(out == {"ok": True}, "run_json_agent parses JSON-as-text final message")
    check(captured["agent_name"] == "probe_agent", "run_json_agent passes agent_name through")

    items = C.catalog_items([agent], {"probe_agent": ["who"]}, "Avatar — probe")
    check(items[0]["id"] == "avatar.probe_agent", "catalog_items builds prefixed prompt id")
    check(items[0]["placeholders"] == ["who"], "catalog_items carries placeholders")
```

And call it from `main()`:

```python
    test_common()
```
(insert after `test_config()`).

- [ ] **Step 3: Run test to verify it fails**

Run: `cd embroidery && venv/bin/python -m tests.test_avatar_common`
Expected: FAIL — `ModuleNotFoundError: embroidery.agents.avatar._common`.

- [ ] **Step 4: Write `_common.py`**

Create `embroidery/embroidery/agents/avatar/_common.py`:

```python
"""
Shared plumbing for the Avatar Builder sub-agents.

Every avatar agent is an `AvatarAgent` (name + label + .format system template +
model_key + optional output_file). Search/discovery agents return a JSON object
as their final text message — `run_json_agent` parses it and (if output_file is
set) persists it under data/output/ so the next stage can read it and the
dashboard can show it. Prompts render through the prompt_store so they are
user-editable (avatar.<name>), with {placeholder} context and {{}} literal braces.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from embroidery.agents.research.subagents import parse_json_output  # reuse tolerant parser
from embroidery.core.agent_loop import run_agent
from embroidery.core.config import settings
from embroidery.core.logger import get_logger
from embroidery.core.prompt_store import get_prompt_store, to_dollar
from embroidery.core.reporter import get_reporter

log = get_logger(__name__)


@dataclass(frozen=True)
class AvatarAgent:
    name: str                 # agent_name + prompt-id stem + log name
    label: str                # human label for the ⚙ prompt editor
    model_key: str            # attribute on settings.agents
    system_template: str      # .format template ({placeholder}, {{}} literal braces)
    output_file: str | None = None   # if set, JSON output persisted under data/output/


def build_system(agent: AvatarAgent, **ctx) -> str:
    """Render an agent's system prompt, honouring any saved user override."""
    store = get_prompt_store()
    return store.render(f"avatar.{agent.name}", to_dollar(agent.system_template), **ctx)


async def run_json_agent(agent: AvatarAgent, kickoff: str, *, tools: list[dict],
                         ctx: dict, max_tool_calls: int = 16) -> dict:
    """Run one agent that returns a JSON object as final text; persist if output_file set."""
    raw = await run_agent(
        system=build_system(agent, **ctx),
        messages=[{"role": "user", "content": kickoff}],
        tools=tools,
        model_settings=getattr(settings.agents, agent.model_key),
        max_tool_calls=max_tool_calls,
        agent_name=agent.name,
    )
    result = parse_json_output(raw)
    if agent.output_file:
        path = Path(settings.paths.output) / agent.output_file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        get_reporter().agent_output(agent.name, agent.output_file)
        log.info("agent=%s output saved file=%s", agent.name, path)
    return result


def catalog_items(agents: list[AvatarAgent], placeholders: dict[str, list[str]],
                  stage_label: str) -> list[dict]:
    """Build prompt_catalog() entries for a group of avatar agents."""
    store = get_prompt_store()
    items: list[dict] = []
    for a in agents:
        pid = f"avatar.{a.name}"
        default = to_dollar(a.system_template)
        items.append({
            "id": pid,
            "name": a.label,
            "stage": stage_label,
            "placeholders": placeholders.get(a.name, []),
            "default": default,
            "text": store.text(pid, default),
            "overridden": store.is_overridden(pid),
        })
    return items


def load_json(name: str) -> dict:
    """Load a previously-saved stage output from data/output/ (for skipped stages)."""
    path = Path(settings.paths.output) / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
```

> Note: the test monkeypatches `C.run_agent`, so `run_json_agent` must call the module-level `run_agent` name (it does).

- [ ] **Step 5: Run test to verify it passes**

Run: `cd embroidery && venv/bin/python -m tests.test_avatar_common`
Expected: PASS — config + common checks ✓.

- [ ] **Step 6: Commit**

```bash
git add embroidery/embroidery/agents/avatar/__init__.py embroidery/embroidery/agents/avatar/_common.py embroidery/tests/test_avatar_common.py
git commit -m "Avatar: _common.py — AvatarAgent + run_json_agent + catalog helpers"
```

---

## Task 3: `framing.py` — Stage 0 onboarding + Stage 1 product understanding

**Files:**
- Create: `embroidery/embroidery/agents/avatar/framing.py`
- Test: `embroidery/tests/test_avatar_common.py` (extend with a structural check)

- [ ] **Step 1: Write `framing.py`**

Create `embroidery/embroidery/agents/avatar/framing.py`:

```python
"""
Avatar Stages 0–1 — product framing.

Stage 0 `avatar_onboarder`  — first-time-visitor onboarding; answers Q1–Q11 from
                              the product page (the immutable "before research" baseline).
Stage 1 `product_analyst`   — Feature→Benefit→Payoff map, claims audit, objections, advantages.

Both use web_fetch (+ light web_search) and return a JSON object as final text.
"""

from embroidery.agents.avatar._common import AvatarAgent, catalog_items, run_json_agent
from embroidery.agents.research.subagents import SHOP_BRIEF, shop_context
from embroidery.core.tools import SEARCH_TOOLS

ONBOARDER = AvatarAgent(
    name="avatar_onboarder",
    label="Stage 0 — Self-Onboarding (first-time visitor)",
    model_key="avatar_onboarder",
    output_file="avatar_onboarding.json",
    system_template="""You are a FIRST-TIME visitor to an ecommerce shop. You have never heard of this brand.
Visit the product page with fresh eyes — assume no prior knowledge.

{shop_context}

TASK:
1. Fetch the shop/product URL above.
2. Skim it for ~30 seconds like a real customer would (above the fold first).
3. Answer Q1–Q11 based ONLY on what a first-time visitor sees — your own words, NOT site copy.

ONBOARDING QUESTIONS:
Q1. What does this product do? (1 sentence, your words)
Q2. Who is this obviously for? (describe the person)
Q3. What problem does it claim to solve?
Q4. What's the price?
Q5. What's the main promise / claim?
Q6. What proof do they show? (reviews, certifications, before/afters)
Q7. What would make a first-time visitor NOT buy? (gut reaction)
Q8. What's the best thing about this product based on what you see?
Q9. What's confusing or missing from the page?
Q10. If this product were a person, describe them in 3 words.
Q11. One sentence you'd use to tell a friend about this product.

OUTPUT DISCIPLINE:
- Your FINAL message must be ONLY a single JSON object with keys Q1..Q11 (string values).
- These answers are the immutable BEFORE-research baseline — never revise them later.
- No markdown fences, no commentary.

OUTPUT SCHEMA:
{{"Q1": "...", "Q2": "...", "Q3": "...", "Q4": "...", "Q5": "...", "Q6": "...",
  "Q7": "...", "Q8": "...", "Q9": "...", "Q10": "...", "Q11": "..."}}""",
)

PRODUCT_ANALYST = AvatarAgent(
    name="product_analyst",
    label="Stage 1 — Product Understanding Map",
    model_key="product_analyst",
    output_file="avatar_product.json",
    system_template="""You are a direct-response copywriter who deeply understands a product BEFORE
writing any copy. Build the Product Understanding Map for this shop.

{shop_context}

Fetch the shop URL and run light searches for spec/feature/comparison detail. Then:

STEP 1 — FEATURE → BENEFIT: for every feature, give mechanism, functional benefit, emotional payoff.
STEP 2 — CLAIMS AUDIT: every marketing claim, rated Believable/Unique/Provable 1–5. Flag any <3 on Unique or Provable.
STEP 3 — OBJECTIONS: every reason NOT to buy, tagged price|trust|fit|urgency|skepticism|comparison.
STEP 4 — COMPETITIVE ADVANTAGES: what this genuinely does better, specifically (not "better quality").

OUTPUT DISCIPLINE:
- FINAL message = ONLY one JSON object matching the schema. No fences, no commentary. English.

OUTPUT SCHEMA:
{{
  "features_map": [
    {{"feature": "...", "mechanism": "...", "benefit": "...", "emotional_payoff": "..."}}
  ],
  "claims_audit": [
    {{"claim": "...", "believable": 1, "unique": 1, "provable": 1, "weak": true}}
  ],
  "objections": [
    {{"objection": "...", "category": "price|trust|fit|urgency|skepticism|comparison"}}
  ],
  "advantages": ["specific advantage 1", "..."]
}}""",
)

_AGENTS = [ONBOARDER, PRODUCT_ANALYST]
_PLACEHOLDERS = {"avatar_onboarder": ["shop_context"], "product_analyst": ["shop_context"]}


async def run_onboarding(brief: dict = SHOP_BRIEF) -> dict:
    return await run_json_agent(ONBOARDER, "Visit the page and answer Q1–Q11 as a first-time visitor.",
                                tools=SEARCH_TOOLS, ctx={"shop_context": shop_context(brief)})


async def run_product(brief: dict = SHOP_BRIEF) -> dict:
    return await run_json_agent(PRODUCT_ANALYST, "Build the Product Understanding Map. Fetch first, then output JSON.",
                                tools=SEARCH_TOOLS, ctx={"shop_context": shop_context(brief)})


def prompt_catalog() -> list[dict]:
    return catalog_items(_AGENTS, _PLACEHOLDERS, "Avatar — framing")
```

- [ ] **Step 2: Add a structural test (extend test_avatar_common.py)**

Add above `main()`:

```python
def test_framing():
    from embroidery.agents.avatar import framing
    cat = framing.prompt_catalog()
    ids = {c["id"] for c in cat}
    check(ids == {"avatar.avatar_onboarder", "avatar.product_analyst"},
          "framing exposes onboarder + product_analyst prompts")
    check(framing.ONBOARDER.output_file == "avatar_onboarding.json", "onboarder writes avatar_onboarding.json")
```

Call it in `main()` after `test_common()`:

```python
    test_framing()
```

- [ ] **Step 3: Run test to verify it passes**

Run: `cd embroidery && venv/bin/python -m tests.test_avatar_common`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add embroidery/embroidery/agents/avatar/framing.py embroidery/tests/test_avatar_common.py
git commit -m "Avatar: framing.py — Stage 0 onboarder + Stage 1 product analyst"
```

---

## Task 4: `discovery.py` — Stage 2 (3 parallel scouts + qualifier)

**Files:**
- Create: `embroidery/embroidery/agents/avatar/discovery.py`
- Test: `embroidery/tests/test_avatar_common.py` (extend)

- [ ] **Step 1: Write `discovery.py`**

Create `embroidery/embroidery/agents/avatar/discovery.py`:

```python
"""
Avatar Stage 2 — Avatar Discovery & Qualification.

Three SEARCH-ONLY scouts run in parallel, each adapted to the shop's four
segments (A Team Pride · B Gift Giver · C Brand Builder · D Aesthetic Buyer):
  reddit_scout — site:reddit.com clusters by shared struggle
  amazon_voc   — Amazon/Etsy review VOC + competitor failure modes
  fb_ad_scout  — facebook.com/ads/library: competitor ads + sophistication + avatar gaps
Then avatar_qualifier (NO TOOLS) scores candidates on the Evolve 4-gate framework
and selects the top `priority_count`.
"""

import asyncio

from embroidery.agents.avatar._common import AvatarAgent, catalog_items, run_json_agent
from embroidery.agents.research.subagents import SHOP_BRIEF, shop_context
from embroidery.core.config import settings
from embroidery.core.tools import SEARCH_TOOLS

_DISCOVERY_RULES = """RESEARCH DISCIPLINE:
- ALL findings must come from real search results — never invent quotes, reviews, names, or ads.
- Budget: at most 6 web_search + 3 web_fetch calls. Prefer site:reddit.com / site:amazon.com /
  facebook.com/ads/library queries that surface real customer language.
- Quotes are VERBATIM from snippets/fetched pages, each with its source URL.
- FINAL message = ONLY one JSON object matching the schema. No fences, no commentary. English."""

REDDIT_SCOUT = AvatarAgent(
    name="reddit_scout", label="Stage 2A — Reddit Avatar Scout", model_key="reddit_scout",
    output_file="avatar_discovery_reddit.json",
    system_template="""You are a market researcher finding real customer sub-avatars by how people
cluster themselves by SHARED STRUGGLE — not by guessing demographics.

{shop_context}

Search site:reddit.com for communities discussing custom embroidery, personalised gifts,
team/club apparel, small-business merch, and embroidery-as-fashion. For each relevant post/comment,
infer who the person is, their occasion, the struggle they share, and record verbatim quotes.
Group people into sub-avatar clusters (by occasion / role / emotional need), mapped to segments A–D.
{rules}

OUTPUT SCHEMA:
{{
  "clusters": [
    {{"cluster_name": "...", "segment": "A|B|C|D", "who_they_are": "...",
      "their_occasion": "...", "dominant_emotion": "...", "estimated_size": "large|medium|small",
      "verbatim_quotes": [{{"quote": "...", "source": "url"}}]}}
  ]
}}""".replace("{rules}", _DISCOVERY_RULES),
)

AMAZON_VOC = AvatarAgent(
    name="amazon_voc", label="Stage 2B — Amazon/Etsy VOC Scout", model_key="amazon_voc",
    output_file="avatar_discovery_amazon.json",
    system_template="""You are a voice-of-customer analyst mining Amazon/Etsy reviews for avatar signals.

{shop_context}

Search for the top custom-embroidery / personalised-apparel products by review count. From recent +
most-helpful reviews extract: WHO writes them, WHAT triggered the purchase (gift vs self, occasion),
VERBATIM emotional language, recurring buzzwords (3+ times), price-sensitivity signals, and
COMPETITOR FAILURE MODES from 1–2★ reviews (delivery, quality, wrong info, packaging).
{rules}

OUTPUT SCHEMA:
{{
  "buyer_types": ["..."],
  "top_occasions": ["..."],
  "emotional_language": [{{"quote": "...", "source": "url"}}],
  "buzzwords": ["..."],
  "competitor_gaps": [{{"complaint": "verbatim", "source": "url"}}],
  "price_sensitivity_signals": ["..."]
}}""".replace("{rules}", _DISCOVERY_RULES),
)

FB_AD_SCOUT = AvatarAgent(
    name="fb_ad_scout", label="Stage 2C — Facebook Ad Library Scout", model_key="fb_ad_scout",
    output_file="avatar_discovery_fb.json",
    system_template="""You are a competitive-intelligence analyst scanning the Facebook Ad Library
(https://www.facebook.com/ads/library/) for custom embroidery / personalised gift / custom apparel ads.

{shop_context}

Fetch ad-library result pages (best-effort). For each ad: describe the creative (who/emotion/setting),
copy the headline + primary text verbatim, identify the targeted avatar, estimate run-length (longer =
working), and rate sophistication S1–S5 (S1 plain claim → S2 bigger claim → S3 new mechanism →
S4 bigger mechanism → S5 identity/persona). Then do an AVATAR-GAP analysis.
{rules}

OUTPUT SCHEMA:
{{
  "active_ads_found": 0,
  "ads": [
    {{"creative": "...", "headline": "...", "primary_text": "...", "targeted_avatar": "...",
      "run_length_signal": "...", "sophistication": "S1|S2|S3|S4|S5", "source": "url"}}
  ],
  "avatars_being_targeted": ["..."],
  "under_served_avatars": ["..."],
  "dominant_sophistication_stage": "S1|S2|S3|S4|S5"
}}""".replace("{rules}", _DISCOVERY_RULES),
)

QUALIFIER = AvatarAgent(
    name="avatar_qualifier", label="Stage 2D — Avatar Qualification (4-gate)", model_key="avatar_qualifier",
    output_file="avatar_qualification.json",
    system_template="""You qualify sub-avatar candidates collected from Reddit, Amazon/Etsy, and the
Facebook Ad Library, using the Evolve 4-gate framework. You have NO tools — reason over the data given.

{shop_context}

You will receive the three discovery JSON blobs plus the market research report. Build a candidate
list (merge/dedupe clusters across sources) and score EACH candidate 1–5 on every gate:
  GATE 1 DESIRE MAGNITUDE — burning, identity-level desire = 5; nice-to-have = 1
  GATE 2 COMPETITION (inverted) — under-served (few ads) = 5; saturated = 1
  GATE 3 ECONOMIC ABILITY — price is trivial / gift-budget = 5; price is a barrier = 1
  GATE 4 SCALABILITY — millions enter the segment yearly = 5; <100k addressable = 1
total = sum (max 20). verdict = "PASS" if all four ≥3, "FAIL" if any <2, else "MAYBE".
Rank by total, then select the top {priority_count} PASS candidates as priority_avatars.

OUTPUT DISCIPLINE: FINAL message = ONLY one JSON object matching the schema. No fences. English.

OUTPUT SCHEMA:
{{
  "candidates": [
    {{"name": "...", "segment": "A|B|C|D", "desire": 1, "competition": 1, "economic": 1,
      "scalability": 1, "total": 4, "verdict": "PASS|FAIL|MAYBE",
      "rationale": "one line citing the evidence"}}
  ],
  "priority_avatars": ["candidate name 1", "candidate name 2"]
}}""",
)

_SCOUTS = [REDDIT_SCOUT, AMAZON_VOC, FB_AD_SCOUT]
_PLACEHOLDERS = {
    "reddit_scout": ["shop_context"], "amazon_voc": ["shop_context"], "fb_ad_scout": ["shop_context"],
    "avatar_qualifier": ["shop_context", "priority_count"],
}


async def run_discovery(brief: dict = SHOP_BRIEF) -> dict:
    """Run the three scouts in parallel (sharing the per-run search budget)."""
    ctx = {"shop_context": shop_context(brief)}
    reddit, amazon, fb = await asyncio.gather(
        run_json_agent(REDDIT_SCOUT, "Find Reddit sub-avatar clusters. Search first, then JSON.",
                       tools=SEARCH_TOOLS, ctx=ctx),
        run_json_agent(AMAZON_VOC, "Mine Amazon/Etsy reviews. Search first, then JSON.",
                       tools=SEARCH_TOOLS, ctx=ctx),
        run_json_agent(FB_AD_SCOUT, "Scan the FB Ad Library. Fetch first, then JSON.",
                       tools=SEARCH_TOOLS, ctx=ctx),
    )
    return {"reddit": reddit, "amazon": amazon, "fb": fb}


async def run_qualify(discovery: dict, research_report: dict, brief: dict = SHOP_BRIEF) -> dict:
    import json
    kickoff = (
        "Qualify these candidates and select the priority avatars.\n\n"
        f"=== REDDIT ===\n{json.dumps(discovery.get('reddit', {}), ensure_ascii=False)}\n\n"
        f"=== AMAZON/ETSY ===\n{json.dumps(discovery.get('amazon', {}), ensure_ascii=False)}\n\n"
        f"=== FB AD LIBRARY ===\n{json.dumps(discovery.get('fb', {}), ensure_ascii=False)}\n\n"
        f"=== MARKET RESEARCH REPORT (segments/awareness/sophistication) ===\n"
        f"{json.dumps(research_report, ensure_ascii=False)[:6000]}"
    )
    ctx = {"shop_context": shop_context(brief), "priority_count": str(settings.avatar.priority_count)}
    return await run_json_agent(QUALIFIER, kickoff, tools=[], ctx=ctx)


def prompt_catalog() -> list[dict]:
    return catalog_items(_SCOUTS + [QUALIFIER], _PLACEHOLDERS, "Avatar — discovery")
```

> Note: `_DISCOVERY_RULES` is plain text (no `{}`), so the `.replace("{rules}", ...)` injects it before `to_dollar()` runs — the rules text contains no braces, so it is safe.

- [ ] **Step 2: Add a structural test (extend test_avatar_common.py)**

Add above `main()`:

```python
def test_discovery():
    from embroidery.agents.avatar import discovery
    ids = {c["id"] for c in discovery.prompt_catalog()}
    check(ids == {"avatar.reddit_scout", "avatar.amazon_voc", "avatar.fb_ad_scout", "avatar.avatar_qualifier"},
          "discovery exposes 3 scouts + qualifier prompts")
    check(discovery.QUALIFIER.output_file == "avatar_qualification.json", "qualifier writes avatar_qualification.json")
```

Call `test_discovery()` in `main()`.

- [ ] **Step 3: Run test to verify it passes**

Run: `cd embroidery && venv/bin/python -m tests.test_avatar_common`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add embroidery/embroidery/agents/avatar/discovery.py embroidery/tests/test_avatar_common.py
git commit -m "Avatar: discovery.py — Stage 2 parallel scouts + 4-gate qualifier"
```

---

## Task 5: `voc.py` — Stage 3 voice-of-customer mining

**Files:**
- Create: `embroidery/embroidery/agents/avatar/voc.py`
- Test: `embroidery/tests/test_avatar_common.py` (extend)

- [ ] **Step 1: Write `voc.py`**

Create `embroidery/embroidery/agents/avatar/voc.py`:

```python
"""
Avatar Stage 3 — Voice-of-Customer mining (search-only).

For the priority avatars, collect VERBATIM customer language across YouTube,
TikTok, and Facebook groups (the Reddit/Amazon quotes from Stage 2 are imported
in the kickoff). Every quote is coded PAIN/DESIRE/BELIEF/TRIGGER/OBJECTION/
VICTORY/IDENTITY with an insight and ad-potential flag. Target ≥50 coded quotes.
"""

import json

from embroidery.agents.avatar._common import AvatarAgent, catalog_items, run_json_agent
from embroidery.agents.research.subagents import SHOP_BRIEF, shop_context
from embroidery.core.tools import SEARCH_TOOLS

VOC_MINER = AvatarAgent(
    name="voc_miner", label="Stage 3 — Voice-of-Customer Miner", model_key="voc_miner",
    output_file="avatar_voc.json",
    system_template="""You are a qualitative researcher collecting VERBATIM customer language — exact
words real people use, never your paraphrase. If you didn't read it in a review/post/comment, it does
not go in.

{shop_context}

PRIORITY AVATARS: {priority_avatars}

Mine YouTube comments, TikTok comments, and Facebook groups for these avatars (import the Reddit/Amazon
quotes already provided). Code EVERY quote into one or more of: PAIN, DESIRE, BELIEF, TRIGGER,
OBJECTION, VICTORY, IDENTITY. Flag self-identification quotes ("as a grandma of twins…") — these are
gold for ad headlines. Target at least 50 coded quotes total across the priority avatars.

RESEARCH DISCIPLINE: at most 6 web_search + 3 web_fetch. Verbatim quotes only, each with source URL.
OUTPUT DISCIPLINE: FINAL message = ONLY one JSON object matching the schema. No fences. English.

OUTPUT SCHEMA:
{{
  "coded_quotes": [
    {{"avatar": "priority avatar name", "quote": "verbatim", "source": "YouTube|TikTok|Facebook|Reddit|Amazon",
      "url": "...", "category": ["PAIN|DESIRE|BELIEF|TRIGGER|OBJECTION|VICTORY|IDENTITY"],
      "insight": "what this reveals about mindset", "ad_potential": "no|hook|headline",
      "self_identification": false}}
  ]
}}""",
)

_PLACEHOLDERS = {"voc_miner": ["shop_context", "priority_avatars"]}


async def run_voc(priority_avatars: list[str], discovery: dict, brief: dict = SHOP_BRIEF) -> dict:
    kickoff = (
        "Mine verbatim VOC for the priority avatars. Import these Stage-2 quotes, then search "
        "YouTube/TikTok/Facebook for more. Output the coded JSON.\n\n"
        f"=== STAGE 2 QUOTES ===\n{json.dumps(discovery, ensure_ascii=False)[:6000]}"
    )
    ctx = {"shop_context": shop_context(brief), "priority_avatars": ", ".join(priority_avatars) or "(all)"}
    return await run_json_agent(VOC_MINER, kickoff, tools=SEARCH_TOOLS, ctx=ctx)


def prompt_catalog() -> list[dict]:
    return catalog_items([VOC_MINER], _PLACEHOLDERS, "Avatar — VOC")
```

- [ ] **Step 2: Add a structural test (extend test_avatar_common.py)**

```python
def test_voc():
    from embroidery.agents.avatar import voc
    ids = {c["id"] for c in voc.prompt_catalog()}
    check(ids == {"avatar.voc_miner"}, "voc exposes the voc_miner prompt")
```

Call `test_voc()` in `main()`.

- [ ] **Step 3: Run test to verify it passes**

Run: `cd embroidery && venv/bin/python -m tests.test_avatar_common`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add embroidery/embroidery/agents/avatar/voc.py embroidery/tests/test_avatar_common.py
git commit -m "Avatar: voc.py — Stage 3 verbatim VOC miner"
```

---

## Task 6: `reframe.py` — Stages 4/5/6 (no-tool reframers over the research report)

**Files:**
- Create: `embroidery/embroidery/agents/avatar/reframe.py`
- Test: `embroidery/tests/test_avatar_common.py` (extend)

- [ ] **Step 1: Write `reframe.py`**

Create `embroidery/embroidery/agents/avatar/reframe.py`:

```python
"""
Avatar Stages 4/5/6 — reframers (NO TOOLS). Each leans on the Agent-1 research
report (market-level competitor/sophistication/mechanism) and reframes it for the
priority avatars + the VOC just collected — no new searches, so the avatar doc
never contradicts the research report.

  awareness_mapper     — Stage 4: awareness × sophistication entry point + arc + hooks
  competitor_teardown  — Stage 5: offer/claims/messaging teardown + opportunity gaps
  mechanism_builder    — Stage 6: objection reframes + solution-mechanism map + credibility check
"""

import json

from embroidery.agents.avatar._common import AvatarAgent, catalog_items, run_json_agent
from embroidery.agents.research.subagents import SHOP_BRIEF, shop_context

AWARENESS_MAPPER = AvatarAgent(
    name="awareness_mapper", label="Stage 4 — Awareness × Sophistication Mapping", model_key="awareness_mapper",
    output_file="avatar_awareness.json",
    system_template="""You are a strategic copywriter trained in Eugene Schwartz's framework. You have NO
tools — reason over the VOC and the market research report provided.

{shop_context}

For EACH priority avatar, diagnose its AWARENESS stage (Unaware→Problem→Solution→Product→Most Aware)
from the VOC evidence, and its SOPHISTICATION stage (S1–S5) from the research report's sophistication
+ per-segment awareness (do NOT search — the report already established the market level). Then
prescribe the ad entry point, the carry-the-conversation-forward arc (3 steps), the differentiation
lever (claim|mechanism|identity), and 3 hook formulas. Cite a VOC quote as evidence for each diagnosis.

OUTPUT DISCIPLINE: FINAL message = ONLY one JSON object matching the schema. No fences. English.

OUTPUT SCHEMA:
{{
  "avatars": [
    {{"avatar": "...", "awareness_stage": "Unaware|Problem|Solution|Product|Most Aware",
      "awareness_evidence": "verbatim VOC quote",
      "sophistication_stage": "S1|S2|S3|S4|S5", "sophistication_evidence": "what claim everyone makes",
      "ad_entry_point": "...", "arc": ["step 1", "step 2", "step 3"],
      "differentiation_lever": "claim|mechanism|identity",
      "hook_formulas": ["hook 1", "hook 2", "hook 3"]}}
  ]
}}""",
)

COMPETITOR_TEARDOWN = AvatarAgent(
    name="competitor_teardown", label="Stage 5 — Competitor Teardown", model_key="competitor_teardown",
    output_file="avatar_competitor.json",
    system_template="""You are a competitive-intelligence analyst. You have NO tools — tear down the
competitors already identified in the market research report (and the FB ad scout), facts only.

{shop_context}

For the top 3 competitors vs the priority avatars: audit the offer stack (shipping, guarantee,
installments, warranty, bonuses), audit the top 3 claims (backed by proof yes/no), list messaging
weaknesses from negative reviews, and the opportunity gaps we can own. Also audit ALTERNATIVE
solutions the avatar uses instead (DIY, generic store-bought, gift card) and each alternative's FLAW
(= our competitive angle).

OUTPUT DISCIPLINE: FINAL message = ONLY one JSON object matching the schema. No fences. English.

OUTPUT SCHEMA:
{{
  "competitors": [
    {{"name": "...", "offer_stack": ["..."], "claims": [{{"claim": "...", "proof": true}}],
      "weaknesses": ["..."], "opportunity_gaps": ["..."]}}
  ],
  "alternatives": [{{"alternative": "...", "flaw": "...", "our_angle": "..."}}]
}}""",
)

MECHANISM_BUILDER = AvatarAgent(
    name="mechanism_builder", label="Stage 6 — Objection Reframes + Solution Mechanism", model_key="mechanism_builder",
    output_file="avatar_mechanism.json",
    system_template="""You are a direct-response copywriter for skeptic-heavy markets. You have NO tools —
build from the research report's unique_mechanism_candidates + the objections collected so far.

{shop_context}

TASK 1 — OBJECTION REFRAMES: for each objection write a reframe (analogy | category | belief-breaking |
authority), in the customer's own language.
TASK 2 — SOLUTION MECHANISM MAP: core problem → root cause → how the product addresses the root cause →
why alternatives fail at the root cause → the specific feature that makes it real.
TASK 3 — CREDIBILITY CHECK: rate the mechanism NEW / OBVIOUS / COMPLETE 1–5; flag any <3 for revision.

OUTPUT DISCIPLINE: FINAL message = ONLY one JSON object matching the schema. No fences. English.

OUTPUT SCHEMA:
{{
  "objection_reframes": [{{"objection": "...", "technique": "analogy|category|belief|authority", "reframe": "..."}}],
  "solution_mechanism": {{"core_problem": "...", "root_cause": "...", "how_it_addresses": "...",
    "why_alternatives_fail": "...", "delivered_via": "..."}},
  "credibility_check": {{"new": 1, "obvious": 1, "complete": 1, "needs_revision": false}}
}}""",
)

_AGENTS = [AWARENESS_MAPPER, COMPETITOR_TEARDOWN, MECHANISM_BUILDER]
_PLACEHOLDERS = {a.name: ["shop_context"] for a in _AGENTS}


def _ctx_kickoff(label: str, voc: dict, research_report: dict) -> str:
    return (
        f"{label}\n\n"
        f"=== VOC (coded quotes) ===\n{json.dumps(voc, ensure_ascii=False)[:6000]}\n\n"
        f"=== MARKET RESEARCH REPORT ===\n{json.dumps(research_report, ensure_ascii=False)[:8000]}"
    )


async def run_awareness(voc: dict, research_report: dict, priority_avatars: list[str],
                        brief: dict = SHOP_BRIEF) -> dict:
    kickoff = _ctx_kickoff(
        f"Map awareness × sophistication for the priority avatars: {', '.join(priority_avatars) or '(all)'}.",
        voc, research_report)
    return await run_json_agent(AWARENESS_MAPPER, kickoff, tools=[], ctx={"shop_context": shop_context(brief)})


async def run_competitor(voc: dict, research_report: dict, brief: dict = SHOP_BRIEF) -> dict:
    kickoff = _ctx_kickoff("Tear down the top competitors and alternatives.", voc, research_report)
    return await run_json_agent(COMPETITOR_TEARDOWN, kickoff, tools=[], ctx={"shop_context": shop_context(brief)})


async def run_mechanism(voc: dict, research_report: dict, brief: dict = SHOP_BRIEF) -> dict:
    kickoff = _ctx_kickoff("Build objection reframes and the solution-mechanism map.", voc, research_report)
    return await run_json_agent(MECHANISM_BUILDER, kickoff, tools=[], ctx={"shop_context": shop_context(brief)})


def prompt_catalog() -> list[dict]:
    return catalog_items(_AGENTS, _PLACEHOLDERS, "Avatar — reframe")
```

- [ ] **Step 2: Add a structural test (extend test_avatar_common.py)**

```python
def test_reframe():
    from embroidery.agents.avatar import reframe
    ids = {c["id"] for c in reframe.prompt_catalog()}
    check(ids == {"avatar.awareness_mapper", "avatar.competitor_teardown", "avatar.mechanism_builder"},
          "reframe exposes awareness + competitor + mechanism prompts")
```

Call `test_reframe()` in `main()`.

- [ ] **Step 3: Run test to verify it passes**

Run: `cd embroidery && venv/bin/python -m tests.test_avatar_common`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add embroidery/embroidery/agents/avatar/reframe.py embroidery/tests/test_avatar_common.py
git commit -m "Avatar: reframe.py — Stages 4/5/6 no-tool reframers"
```

---

## Task 7: `synthesizer.py` — Stage 7 final Avatar Deep Dive

**Files:**
- Create: `embroidery/embroidery/agents/avatar/synthesizer.py`
- Test: `embroidery/tests/test_avatar_common.py` (extend — stub `run_agent`, assert both files written)

- [ ] **Step 1: Write the failing test (extend test_avatar_common.py)**

Add above `main()`:

```python
def test_synthesizer_writes_two_files():
    import asyncio, json
    from pathlib import Path
    from embroidery.core.config import settings
    from embroidery.agents.avatar import synthesizer as S

    out = Path(settings.paths.output); out.mkdir(parents=True, exist_ok=True)
    (out / "avatar_deep_dive.json").unlink(missing_ok=True)
    (out / "customer_avatars.md").unlink(missing_ok=True)

    calls = {"n": 0}
    async def fake_run_agent(*, system, messages, tools, model_settings, agent_name, max_tool_calls=50):
        calls["n"] += 1
        return '{"avatars": []}' if calls["n"] == 1 else "# Avatar Deep Dive\n\nbody"
    S.run_agent = fake_run_agent

    stages = {"onboarding": {}, "product": {}, "discovery": {}, "qualification": {},
              "voc": {}, "awareness": {}, "competitor": {}, "mechanism": {}}
    report, md = asyncio.run(S.run_synthesis(stages, {"segments": {}}, priority_avatars=["X"]))
    check((out / "avatar_deep_dive.json").exists(), "synthesizer writes avatar_deep_dive.json")
    check((out / "customer_avatars.md").exists(), "synthesizer writes customer_avatars.md")
    check(md.startswith("# Avatar Deep Dive"), "synthesizer returns the markdown doc")
```

Call `test_synthesizer_writes_two_files()` in `main()`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd embroidery && venv/bin/python -m tests.test_avatar_common`
Expected: FAIL — `ModuleNotFoundError: embroidery.agents.avatar.synthesizer`.

- [ ] **Step 3: Write `synthesizer.py`**

Create `embroidery/embroidery/agents/avatar/synthesizer.py`:

```python
"""
Avatar Stage 7 — Synthesizer (NO TOOLS). Merges Stages 0–6 into the Avatar Deep
Dive. Two calls (like the research synthesizer):
  call 1 → avatar_deep_dive.json  (structured, one object per priority avatar)
  call 2 → customer_avatars.md    (the human-readable doc — data contract for Agents 3–6)
Python writes both files; the model never emits a large tool payload.
"""

import json
from datetime import date
from pathlib import Path

from embroidery.agents.avatar._common import build_system, AvatarAgent
from embroidery.agents.research.subagents import SHOP_BRIEF, parse_json_output, shop_context
from embroidery.core.agent_loop import run_agent
from embroidery.core.config import settings
from embroidery.core.logger import get_logger
from embroidery.core.reporter import get_reporter

log = get_logger(__name__)

_SYNTH_JSON = AvatarAgent(
    name="avatar_synthesizer", label="Stage 7 — Avatar Synthesizer (JSON)", model_key="avatar_synthesizer",
    system_template="""You are a senior creative strategist merging 7 stages of avatar research into a
structured Avatar Deep Dive. NON-NEGOTIABLE: include EVERY verbatim quote (no sampling/dedup), preserve
original customer language, every quote gets an insight.

{shop_context}

Produce ONE JSON object: an array `avatars`, one entry per priority avatar, each carrying the snapshot,
demographics, occasion map, desire chain (surface→functional→emotional→identity→deepest), awareness +
sophistication, the FULL coded VOC, competitor-gap map, solution mechanism, objection reframes, ad angles,
and hooks. FINAL message = ONLY the JSON object. No fences. English.

OUTPUT SCHEMA:
{{
  "research_date": "{research_date}",
  "avatars": [
    {{"name": "...", "snapshot": "...",
      "demographics": {{"age": "...", "gender": "...", "role": "...", "occasion": "...", "income_signal": "..."}},
      "desire_chain": {{"surface": "...", "functional": "...", "emotional": "...", "identity": "...", "deepest": "..."}},
      "awareness_stage": "...", "sophistication_stage": "...",
      "voc": [{{"quote": "...", "category": ["..."], "insight": "...", "source": "url"}}],
      "competitor_gaps": [{{"gap": "...", "angle": "..."}}],
      "solution_mechanism": {{"root_cause": "...", "mechanism": "...", "why_others_fail": "...", "delivered_via": "..."}},
      "objection_reframes": [{{"objection": "...", "reframe": "..."}}],
      "ad_angles": [{{"name": "...", "awareness_entry": "...", "hook_idea": "...", "core_message": "...", "tactic": "claim|mechanism|identity"}}],
      "hooks_to_test": ["..."]}}
  ]
}}""",
)

_SYNTH_MD = AvatarAgent(
    name="avatar_synthesizer_md", label="Stage 7 — Avatar Synthesizer (Markdown)", model_key="avatar_synthesizer",
    system_template="""You are a senior creative strategist writing the AVATAR DEEP DIVE document a
copywriter will use to build ads. You receive the structured deep-dive JSON plus the raw stage outputs.

{shop_context}

Write a thorough markdown document. For EACH priority avatar include these sections:
one-line snapshot · demographics · occasion map · desire chain (surface→deepest) · awareness stage +
entry point · sophistication stage + what NOT to say · VOICE OF CUSTOMER (ALL coded quotes, grouped by
PAIN/DESIRE/TRIGGER/OBJECTION/BELIEF/IDENTITY, every quote with its insight) · competitor-gap map (table)
· solution mechanism · objection reframes (ready for copy) · ad angles (priority order) · hooks to test.
NON-NEGOTIABLE: every verbatim quote is preserved exactly, in "quotes", with its source. No filler.
Output ONLY the markdown document — no preamble, no fences around the whole document.""",
)


async def run_synthesis(stages: dict, research_report: dict, priority_avatars: list[str],
                        brief: dict = SHOP_BRIEF) -> tuple[dict, str]:
    """Two no-tool calls → (deep_dive dict, markdown). Writes both data-contract files."""
    ctx = {"shop_context": shop_context(brief)}
    blob = json.dumps(stages, ensure_ascii=False)

    raw = await run_agent(
        system=build_system(_SYNTH_JSON, shop_context=shop_context(brief), research_date=date.today().isoformat()),
        messages=[{"role": "user", "content":
                   f"Synthesize the structured Avatar Deep Dive for: {', '.join(priority_avatars) or '(all)'}.\n\n"
                   f"=== ALL STAGE OUTPUTS ===\n{blob[:24000]}"}],
        tools=[], model_settings=settings.agents.avatar_synthesizer, agent_name="avatar_synthesizer",
    )
    deep_dive = parse_json_output(raw)

    markdown = await run_agent(
        system=build_system(_SYNTH_MD, shop_context=shop_context(brief)),
        messages=[{"role": "user", "content":
                   "Write the Avatar Deep Dive document.\n\n"
                   f"=== DEEP DIVE JSON ===\n{json.dumps(deep_dive, ensure_ascii=False)}\n\n"
                   f"=== RAW STAGE OUTPUTS ===\n{blob[:16000]}"}],
        tools=[], model_settings=settings.agents.avatar_synthesizer, agent_name="avatar_synthesizer_md",
    )
    markdown = markdown.strip()
    if markdown.startswith("```"):
        markdown = markdown.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    out = Path(settings.paths.output); out.mkdir(parents=True, exist_ok=True)
    (out / "avatar_deep_dive.json").write_text(json.dumps(deep_dive, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "customer_avatars.md").write_text(markdown, encoding="utf-8")
    get_reporter().agent_output("avatar_synthesizer", "avatar_deep_dive.json")
    get_reporter().agent_output("avatar_synthesizer_md", "customer_avatars.md")
    log.info("avatar synthesis done deep_dive_avatars=%d md_chars=%d",
             len(deep_dive.get("avatars", [])), len(markdown))
    return deep_dive, markdown


def prompt_catalog() -> list[dict]:
    from embroidery.agents.avatar._common import catalog_items
    return catalog_items([_SYNTH_JSON, _SYNTH_MD],
                         {"avatar_synthesizer": ["shop_context", "research_date"],
                          "avatar_synthesizer_md": ["shop_context"]},
                         "Avatar — synthesis")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd embroidery && venv/bin/python -m tests.test_avatar_common`
Expected: PASS — both files written, markdown returned.

- [ ] **Step 5: Commit**

```bash
git add embroidery/embroidery/agents/avatar/synthesizer.py embroidery/tests/test_avatar_common.py
git commit -m "Avatar: synthesizer.py — Stage 7 deep-dive (JSON + customer_avatars.md)"
```

---

## Task 8: `pipeline.py` — orchestration, gates, slicing, registration

**Files:**
- Create: `embroidery/embroidery/agents/avatar/pipeline.py`
- Test: `embroidery/tests/test_avatar_stages.py` (create)

- [ ] **Step 1: Write the failing test**

Create `embroidery/tests/test_avatar_stages.py`:

```python
"""
The avatar pipeline registers a WorkflowSpec and honours start/stop-stage slicing
and gate decisions, with every stage runner stubbed. No providers, no tokens.

Run: cd embroidery && venv/bin/python -m tests.test_avatar_stages
"""
import asyncio
import sys

import embroidery.agents.avatar.pipeline as P
from embroidery.core.workflow import get_spec
from embroidery.core.checkpoint import Decision, CheckpointResult

failures: list[str] = []
calls: list[str] = []

def check(cond, msg):
    print(("✓ " if cond else "✗ ") + msg)
    if not cond:
        failures.append(msg)

async def _approve(stage, digest, *, workflow="", request=None):
    return CheckpointResult(Decision.APPROVE, request)

def _stub_all():
    calls.clear()
    # one stub per stage runner (each returns a coroutine via _rec)
    P.run_onboarding   = (lambda *a, **k: _rec("onboarding", {}))
    P.run_product      = (lambda *a, **k: _rec("product", {}))
    P.run_discovery    = (lambda *a, **k: _rec("discovery", {"reddit": {}, "amazon": {}, "fb": {}}))
    P.run_qualify      = (lambda *a, **k: _rec("qualify", {"priority_avatars": ["X"]}))
    P.run_voc          = (lambda *a, **k: _rec("voc", {}))
    P.run_awareness    = (lambda *a, **k: _rec("awareness", {}))
    P.run_competitor   = (lambda *a, **k: _rec("competitor", {}))
    P.run_mechanism    = (lambda *a, **k: _rec("mechanism", {}))
    P.run_synthesis    = (lambda *a, **k: _rec("synthesis", ({}, "# md")))
    P.load_research    = lambda: ({"segments": {}}, "")

async def _rec(name, ret):
    calls.append(name)
    return ret

def main() -> int:
    spec = get_spec("avatar")
    check(spec.label == "Avatar Builder", "avatar spec registered with label")
    check(spec.stage_names() == ["onboarding", "product", "discovery", "qualify", "voc",
                                 "awareness", "competitor", "mechanism", "synthesis"],
          "avatar declares 9 stages in order")
    check(spec.inputs == ["market_research_report.json", "brand_intelligence_report.md"],
          "avatar declares its research inputs")
    check(spec.outputs == ["customer_avatars.md", "avatar_deep_dive.json"],
          "avatar declares its data-contract outputs")

    # full run hits every stage in order
    _stub_all()
    asyncio.run(P.run_avatar_builder(gate=_approve))
    check(calls == ["onboarding", "product", "discovery", "qualify", "voc",
                    "awareness", "competitor", "mechanism", "synthesis"],
          "full run executes all 9 stages in order")

    # start at synthesis -> only synthesis runs (others load from disk)
    _stub_all()
    asyncio.run(P.run_avatar_builder(start_stage="synthesis", gate=_approve))
    check(calls == ["synthesis"], "start_stage=synthesis skips upstream stages")

    # stop at qualify -> stops after qualify
    _stub_all()
    asyncio.run(P.run_avatar_builder(stop_stage="qualify", gate=_approve))
    check(calls == ["onboarding", "product", "discovery", "qualify"],
          "stop_stage=qualify stops after the qualify stage")

    # QUIT at the first gate aborts immediately
    _stub_all()
    async def _quit_once(stage, digest, *, workflow="", request=None):
        return CheckpointResult(Decision.QUIT, request)
    res = asyncio.run(P.run_avatar_builder(gate=_quit_once))
    check(res is None and calls == ["onboarding"], "QUIT at first gate aborts the run")

    if failures:
        print(f"\n✗ test_avatar_stages FAILED ({len(failures)})")
        return 1
    print("\n✓ test_avatar_stages passed")
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd embroidery && venv/bin/python -m tests.test_avatar_stages`
Expected: FAIL — `ModuleNotFoundError: embroidery.agents.avatar.pipeline`.

- [ ] **Step 3: Write `pipeline.py`**

Create `embroidery/embroidery/agents/avatar/pipeline.py`:

```python
"""
Agent 2 — Customer Avatar Builder pipeline (Evolve 9-stage avatar engine).

  research report ─► onboarding ─► product ─► discovery ─► [qualify gate]
                  ─► voc ─► awareness ─► competitor ─► mechanism ─► synthesis
                  ─► customer_avatars.md + avatar_deep_dive.json

Reads Agent 1's market_research_report.json + brand_intelligence_report.md (the
orchestrator's data-contract gate blocks this workflow if they are absent). A QC
gate fires at every stage boundary (Approve / Edit / Quit); standalone runs
auto-approve. start_stage/stop_stage slice the run; skipped stages load their
saved JSON from data/output/.

Run (standalone, auto-approves; needs the research outputs or seeded fixtures on disk):
    cd embroidery && venv/bin/python -m embroidery.agents.avatar.pipeline [--yes]
"""

import asyncio
import json
import os
import sys
from pathlib import Path

from embroidery.agents.avatar._common import load_json
from embroidery.agents.avatar.discovery import run_discovery, run_qualify
from embroidery.agents.avatar.framing import run_onboarding, run_product
from embroidery.agents.avatar.reframe import run_awareness, run_competitor, run_mechanism
from embroidery.agents.avatar.synthesizer import run_synthesis
from embroidery.agents.avatar.voc import run_voc
from embroidery.agents.research.subagents import SHOP_BRIEF
from embroidery.core.agent_loop import reset_search_count
from embroidery.core.checkpoint import Decision, checkpoint
from embroidery.core.config import settings
from embroidery.core.logger import get_logger
from embroidery.core.reporter import get_reporter

log = get_logger(__name__)

_STAGES = ["onboarding", "product", "discovery", "qualify", "voc",
           "awareness", "competitor", "mechanism", "synthesis"]


def _active(start_stage: str | None, stop_stage: str | None) -> set[str]:
    si = _STAGES.index(start_stage) if start_stage else 0
    ei = _STAGES.index(stop_stage) if stop_stage else len(_STAGES) - 1
    if si > ei:
        raise ValueError(f"start_stage {start_stage!r} is after stop_stage {stop_stage!r}")
    return {s for i, s in enumerate(_STAGES) if si <= i <= ei}


def load_research() -> tuple[dict, str]:
    """Load Agent 1's outputs (monkeypatched in tests)."""
    out = Path(settings.paths.output)
    report_path = out / "market_research_report.json"
    md_path = out / "brand_intelligence_report.md"
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
    md = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
    return report, md


def _digest(stage: str, result) -> dict:
    """Compact gate card per stage."""
    if stage == "qualify":
        return {"priority_avatars": result.get("priority_avatars", []),
                "candidates": len(result.get("candidates", []) or [])}
    if stage == "discovery":
        return {"reddit_clusters": len((result.get("reddit") or {}).get("clusters", []) or []),
                "fb_ads": (result.get("fb") or {}).get("active_ads_found", 0)}
    if stage == "voc":
        return {"coded_quotes": len(result.get("coded_quotes", []) or [])}
    if stage == "synthesis":
        dd, md = result
        return {"avatars": len(dd.get("avatars", []) or []), "md_chars": len(md)}
    if isinstance(result, dict):
        return {"keys": sorted(result.keys())}
    return {}


async def run_avatar_builder(
    brief: dict | None = None,
    *,
    start_stage: str | None = None,
    stop_stage: str | None = None,
    gate=checkpoint,
):
    """Run the 9-stage avatar workflow with a QC gate at every boundary.

    Returns the output paths dict, or None if the user quit / stopped early.
    """
    brief = dict(brief) if brief else dict(SHOP_BRIEF)
    active = _active(start_stage, stop_stage)
    reporter = get_reporter()
    research_report, _brand_md = load_research()
    st: dict = {}   # accumulated stage results (run or loaded from disk)

    async def stage(name: str, runner, *, loader):
        """Run a gated stage if active, else load its output from disk.
        Returns (result, control) where control is 'quit' or None."""
        nonlocal brief
        if name not in active:
            return loader(), None
        while True:
            reset_search_count()
            reporter.publish({"type": "stage", "workflow": "avatar", "stage": name})
            result = await runner()
            res = await gate(name, _digest(name, result), workflow="avatar", request=brief)
            if res.decision is Decision.QUIT:
                return result, "quit"
            if res.decision is Decision.EDIT:
                brief = res.request or brief
                continue
            return result, None

    with reporter.workflow_context("avatar"):
        # Stage 0 — onboarding
        st["onboarding"], ctl = await stage(
            "onboarding", lambda: run_onboarding(brief),
            loader=lambda: load_json("avatar_onboarding.json"))
        if ctl == "quit":
            return None

        # Stage 1 — product
        st["product"], ctl = await stage(
            "product", lambda: run_product(brief),
            loader=lambda: load_json("avatar_product.json"))
        if ctl == "quit":
            return None

        # Stage 2a — discovery
        st["discovery"], ctl = await stage(
            "discovery", lambda: run_discovery(brief),
            loader=lambda: {"reddit": load_json("avatar_discovery_reddit.json"),
                            "amazon": load_json("avatar_discovery_amazon.json"),
                            "fb": load_json("avatar_discovery_fb.json")})
        if ctl == "quit":
            return None

        # Stage 2b — qualify (key human gate)
        st["qualification"], ctl = await stage(
            "qualify", lambda: run_qualify(st["discovery"], research_report, brief),
            loader=lambda: load_json("avatar_qualification.json"))
        if ctl == "quit":
            return None
        priority = st["qualification"].get("priority_avatars", [])

        # Stage 3 — voc
        st["voc"], ctl = await stage(
            "voc", lambda: run_voc(priority, st["discovery"], brief),
            loader=lambda: load_json("avatar_voc.json"))
        if ctl == "quit":
            return None

        # Stage 4 — awareness
        st["awareness"], ctl = await stage(
            "awareness", lambda: run_awareness(st["voc"], research_report, priority, brief),
            loader=lambda: load_json("avatar_awareness.json"))
        if ctl == "quit":
            return None

        # Stage 5 — competitor
        st["competitor"], ctl = await stage(
            "competitor", lambda: run_competitor(st["voc"], research_report, brief),
            loader=lambda: load_json("avatar_competitor.json"))
        if ctl == "quit":
            return None

        # Stage 6 — mechanism
        st["mechanism"], ctl = await stage(
            "mechanism", lambda: run_mechanism(st["voc"], research_report, brief),
            loader=lambda: load_json("avatar_mechanism.json"))
        if ctl == "quit":
            return None

        if "synthesis" not in active:
            log.info("avatar: stopping before synthesis (stop_stage)")
            return None

        # Stage 7 — synthesis
        result, ctl = await stage(
            "synthesis", lambda: run_synthesis(st, research_report, priority, brief),
            loader=lambda: (load_json("avatar_deep_dive.json"), ""))
        if ctl == "quit":
            return None

    out = Path(settings.paths.output)
    log.info("avatar workflow done -> customer_avatars.md + avatar_deep_dive.json")
    return {"customer_avatars": out / "customer_avatars.md",
            "avatar_deep_dive": out / "avatar_deep_dive.json"}


def _prompt_catalog() -> list[dict]:
    from embroidery.agents.avatar import discovery, framing, reframe, synthesizer, voc
    return (framing.prompt_catalog() + discovery.prompt_catalog() + voc.prompt_catalog()
            + reframe.prompt_catalog() + synthesizer.prompt_catalog())


# Register in the team registry (import-time, idempotent).
from embroidery.core.workflow import Stage, WorkflowSpec, register   # noqa: E402

register(WorkflowSpec(
    id="avatar",
    label="Avatar Builder",
    stages=[
        Stage("onboarding", ["avatar_onboarder"]),
        Stage("product", ["product_analyst"]),
        Stage("discovery", ["reddit_scout", "amazon_voc", "fb_ad_scout"]),
        Stage("qualify", ["avatar_qualifier"]),
        Stage("voc", ["voc_miner"]),
        Stage("awareness", ["awareness_mapper"]),
        Stage("competitor", ["competitor_teardown"]),
        Stage("mechanism", ["mechanism_builder"]),
        Stage("synthesis", ["avatar_synthesizer", "avatar_synthesizer_md"]),
    ],
    entry_point=run_avatar_builder,
    prompt_catalog=_prompt_catalog,
    inputs=["market_research_report.json", "brand_intelligence_report.md"],
    outputs=["customer_avatars.md", "avatar_deep_dive.json"],
    fixtures=["market_research_report.json", "brand_intelligence_report.md"],
    config_schema={
        "priority_count": settings.avatar.priority_count,
        "avatar_synthesizer": {"model": settings.agents.avatar_synthesizer.model},
    },
))


if __name__ == "__main__":
    if "--yes" in sys.argv:
        os.environ["EMBROIDERY_YES"] = "1"
    paths = asyncio.run(run_avatar_builder())
    if not paths:
        print("Avatar pipeline stopped (quit or stop-stage).")
    else:
        for name, path in paths.items():
            size = path.stat().st_size if path.exists() else 0
            print(f"{name}: {path} ({size:,} bytes)")
```

> The test stubs `run_synthesis` to return `({}, "# md")`, so `_digest("synthesis", ...)` unpacks the tuple — keep that contract.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd embroidery && venv/bin/python -m tests.test_avatar_stages`
Expected: PASS — registration + full/sliced/quit runs ✓.

- [ ] **Step 5: Re-run the common test (no regressions)**

Run: `cd embroidery && venv/bin/python -m tests.test_avatar_common`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add embroidery/embroidery/agents/avatar/pipeline.py embroidery/tests/test_avatar_stages.py
git commit -m "Avatar: pipeline.py — 9-stage gated orchestration + WorkflowSpec registration"
```

---

## Task 9: Register the workflow in `load_workflows()`

**Files:**
- Modify: `embroidery/embroidery/core/workflow.py:79-82`
- Test: `embroidery/tests/test_avatar_stages.py` (extend)

- [ ] **Step 1: Write the failing test (extend test_avatar_stages.py)**

Add this check inside `main()` after the `spec.outputs` check:

```python
    from embroidery.core.workflow import load_workflows
    order = [s.id for s in load_workflows()]
    check(order.index("research") < order.index("avatar") < order.index("qa"),
          "load_workflows orders research -> avatar -> qa")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd embroidery && venv/bin/python -m tests.test_avatar_stages`
Expected: FAIL — `avatar` not in `load_workflows()` order (ValueError from `.index`).

- [ ] **Step 3: Add the avatar module to `load_workflows()`**

In `workflow.py`, change the module tuple (currently lines ~79-82):

```python
    for module in (
        "embroidery.agents.research.pipeline",
        "embroidery.agents.avatar.pipeline",
        "embroidery.agents.qa.pipeline",
    ):
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd embroidery && venv/bin/python -m tests.test_avatar_stages`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add embroidery/embroidery/core/workflow.py embroidery/tests/test_avatar_stages.py
git commit -m "Avatar: wire into load_workflows() (research -> avatar -> qa)"
```

---

## Task 10: Commit research-output fixtures (offline avatar runs)

**Files:**
- Create: `embroidery/fixtures/market_research_report.json`
- Create: `embroidery/fixtures/brand_intelligence_report.md`

- [ ] **Step 1: Seed the fixtures from a real run if available, else minimal valid**

If a prior research run left `embroidery/data/output/market_research_report.json`, copy both files:

```bash
cd embroidery
[ -f data/output/market_research_report.json ] && cp data/output/market_research_report.json fixtures/market_research_report.json || echo "no prior run — create minimal fixture in Step 2"
[ -f data/output/brand_intelligence_report.md ] && cp data/output/brand_intelligence_report.md fixtures/brand_intelligence_report.md || echo "no prior run — create minimal fixture in Step 2"
```

- [ ] **Step 2: If no prior run, write minimal valid fixtures**

Only if the files were not copied above. Create `embroidery/fixtures/market_research_report.json`:

```json
{
  "shop": {"name": "Custom Embroidery Co", "research_date": "2026-06-13"},
  "segments": {
    "A_team_pride": {"awareness_level": 4, "sophistication_stage": 3, "size": "large", "evidence": "club apparel threads"},
    "B_gift_giver": {"awareness_level": 3, "sophistication_stage": 3, "size": "large", "evidence": "personalised baby gift reviews"},
    "C_brand_builder": {"awareness_level": 4, "sophistication_stage": 3, "size": "medium", "evidence": "small-business merch posts"},
    "D_aesthetic_buyer": {"awareness_level": 2, "sophistication_stage": 4, "size": "medium", "evidence": "quiet-luxury embroidery TikToks"}
  },
  "desires": [{"rank": 1, "statement": "give a gift that proves I paid attention", "lf8_tag": "LF8", "segment": "B", "intensity": "high", "sources_agreeing": 2, "evidence": {"quote": "she cried when she opened it", "source": "https://www.etsy.com/listing/example"}}],
  "problems": [{"rank": 1, "statement": "afraid the gift won't arrive in time", "when": "ordering close to the event", "emotion": "anxiety", "why": "the occasion can't be redone", "segment": "B", "urgency": "high", "evidence": {"quote": "needed it for the shower and cut it so close", "source": "https://www.reddit.com/r/example"}}],
  "hooks": [{"rank": 1, "visual_hook": "hands unwrapping an embroidered blanket", "text_hook": "the gift she'll keep for 20 years", "category": "identity", "segment": "B", "adapted_from": "gift-reveal reels"}],
  "objections": [{"objection": "too expensive for a blanket", "underlying_fear": "wasting money on a fad", "counter": "a keepsake used at every birthday", "segment": "B"}],
  "market_sophistication": {"stage": 3, "reasoning": "DTF/DTG shops already shout premium custom apparel", "observed_claims": [{"claim": "premium custom apparel", "source": "https://example.com", "stage_signal": 2}]},
  "unique_mechanism_candidates": [{"name": "hand-digitised stitch mapping", "type": 1, "description": "each design is hand-digitised, not auto-converted", "credibility": "visible stitch density", "copy_resistance": "POD shops use auto-digitising"}],
  "buzzwords": ["keepsake", "hand-stitched", "personalised"],
  "voice_bank": {"desire_phrases": ["she'll keep it forever"], "pain_phrases": ["cut it so close"], "objection_phrases": ["is it worth it"]},
  "coverage_gaps": []
}
```

Create `embroidery/fixtures/brand_intelligence_report.md`:

```markdown
# Brand Intelligence Report — Custom Embroidery Co

## Executive Summary
Minimal fixture for offline avatar-workflow tests. The gift-giver (B) and team-pride (A)
segments carry the strongest, most urgent desires; market sophistication is Stage 3, so the
hand-digitised stitch-mapping mechanism is the lead differentiation lever.

## Market Sophistication & Awareness
Stage 3. DTF/DTG/print-on-demand shops have already made the "premium custom apparel" claim,
so a plain claim won't land — lead with the mechanism for B/C and identity for D.
```

- [ ] **Step 2.5: Sanity-check the fixture parses**

Run: `cd embroidery && venv/bin/python -c "import json,pathlib; json.loads(pathlib.Path('fixtures/market_research_report.json').read_text())" && echo OK`
Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add embroidery/fixtures/market_research_report.json embroidery/fixtures/brand_intelligence_report.md
git commit -m "Avatar: commit research-output fixtures for offline avatar runs"
```

---

## Task 11: Documentation — READMEs, CLAUDE.md, development-plan.md

**Files:**
- Create: `embroidery/embroidery/agents/avatar/README.md`
- Modify: `embroidery/embroidery/agents/README.md`
- Modify: `CLAUDE.md`
- Modify: `development-plan.md`

- [ ] **Step 1: Write `embroidery/embroidery/agents/avatar/README.md`**

Create it with: what the workflow does, the run command, a per-file table (skip filename-derivable entries), and the workflow chart below:

```markdown
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
```

- [ ] **Step 2: Update `embroidery/embroidery/agents/README.md`**

Read it first (`Read embroidery/embroidery/agents/README.md`), then add an `avatar` row to its
workflow index/table (mirroring the existing `research` and `qa` entries): id `avatar`, label
"Avatar Builder", Agent 2, 9 stages, reads the research report, writes `customer_avatars.md` +
`avatar_deep_dive.json`, and link to `avatar/README.md`. Keep its workflow chart in sync if it has one.

- [ ] **Step 3: Update `CLAUDE.md`**

Make these edits (read each region first to match wording):
1. **Architecture diagram** (the big code block) — add the `avatar` lane between research and qa, noting "after Research ✅, after Avatar ✅" gates and the avatar inputs/outputs.
2. **Agent hierarchy** block — replace the `Agent 2: Customer Avatar Builder [parallel with 3]` line with a note that Agent 2 is now its own `avatar` workflow lane (9 stages), and add the deviation note.
3. **Data-contract table** — `customer_avatars.md` "Written by" stays `2`; add a row for `avatar_deep_dive.json` (written by 2, read by 3) and note the `avatar_*` intermediates; mark its inputs as `market_research_report.json` + `brand_intelligence_report.md`.
4. **Tool access per agent** — add: Avatar search agents (onboarder/product/scouts/voc) use `web_search`/`web_fetch` and return JSON-as-text; qualifier/reframers/synthesizer have no tools.
5. **Build order** — note Agent 2 is built as the `avatar` workflow and wired into the dashboard.
6. **README rule** paragraph — add `agents/avatar/` to the list of per-workflow README owners.

- [ ] **Step 4: Update `development-plan.md`**

Read it, check off the Agent 2 (Customer Avatar Builder) items, and add an inline deviation note:
"Agent 2 built as a standalone `avatar` workflow lane (9 Evolve stages) rather than as stages on
the Research lane — see `docs/superpowers/specs/2026-06-13-avatar-builder-workflow-design.md`."

- [ ] **Step 5: Verify docs reference real things**

Run: `cd embroidery && venv/bin/python -m tests.test_avatar_stages && venv/bin/python -m tests.test_avatar_common`
Expected: both PASS (sanity that nothing broke while editing docs).

- [ ] **Step 6: Commit**

```bash
git add embroidery/embroidery/agents/avatar/README.md embroidery/embroidery/agents/README.md CLAUDE.md development-plan.md
git commit -m "Avatar: docs — workflow README + agents index + CLAUDE.md + plan status"
```

---

## Task 12: Full-suite verification + optional live smoke

**Files:** none (verification only)

- [ ] **Step 1: Run the whole avatar + registry + orchestrator test set**

Run:
```bash
cd embroidery && for t in test_avatar_common test_avatar_stages test_workflow test_orchestrator test_research_stages; do venv/bin/python -m tests.$t || break; done
```
Expected: every test prints `✓ ... passed`.

- [ ] **Step 2 (optional, costs tokens): live single-stage smoke**

Only if you want to validate prompts against the live model. Ensure the fixtures are on disk first:
```bash
cd embroidery && cp fixtures/market_research_report.json data/output/ && cp fixtures/brand_intelligence_report.md data/output/
venv/bin/python -m embroidery.agents.avatar.pipeline --yes
```
Expected: `customer_avatars.md` + `avatar_deep_dive.json` appear in `data/output/`; inspect them for
quality. If a flash agent emits malformed output, confirm it returned JSON-as-text (no `write_file`)
and adjust the prompt wording (prompt-wording tweaks are not README-significant).

- [ ] **Step 3: Final commit (if Step 2 produced fixture copies you want to ignore)**

No commit needed unless you changed tracked files. `data/output/` is runtime output (gitignored).

---

## Self-Review notes (for the implementer)

- **Spec coverage:** all 8 Evolve sub-stages map to tasks (0→Task 3, 1→Task 3, 2A/B/C+2D→Task 4,
  3→Task 5, 4/5/6→Task 6, 7→Task 7); orchestration/gates/slicing→Task 8; registry order→Task 9;
  fixtures→Task 10; Monitor/Test/Edit surface is inherited from the generic registry (no code) and
  documented in Task 11.
- **Naming consistency:** `run_synthesis` returns a `(deep_dive, markdown)` tuple — the pipeline's
  `_digest("synthesis", ...)` and the Task-8 test both unpack it. Stage names match exactly between
  `_STAGES`, the `WorkflowSpec.stages`, and the Task-8 test. Agent `name=` values match the
  `config.py` field names and the `Stage(..., [agents])` lists.
- **Edit-gate semantics:** `EDIT` re-runs the current stage with the edited brief (does not rewind to
  an earlier stage) — the documented, intentional behaviour.
```
