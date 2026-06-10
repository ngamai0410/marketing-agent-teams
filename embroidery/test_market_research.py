"""
Day 4 test — parallel execution + Synthesizer wiring.

Default run (offline checks + live Synthesizer, ~2 gemini-2.5-pro calls,
NO new searches — uses the static Day 3 outputs in output/):
    cd embroidery && venv/bin/python test_market_research.py

Full pipeline (live: gather(A,B,C) with real searches, then Synthesizer;
~$0.30–0.50 + Brave usage):
    cd embroidery && venv/bin/python test_market_research.py --full
"""

import asyncio
import sys
import tempfile

failures: list[str] = []


def check(cond: bool, msg: str):
    print(("✓ " if cond else "✗ ") + msg)
    if not cond:
        failures.append(msg)


# ─────────────────────────────────────────────
# Offline — per-agent search cap (no API calls)
# ─────────────────────────────────────────────

class _StubSearch:
    async def search(self, query, num_results=10):
        return "[stub result]"

    async def fetch(self, url):
        return "[stub page]"


async def _offline_search_caps():
    import agent_loop
    from config import settings

    agent_loop._search = _StubSearch()
    settings.search.max_searches_per_agent = 3
    settings.search.max_searches = 5
    agent_loop.reset_search_count()

    # agent x: hits its per-agent cap of 3
    results_x = [await agent_loop._execute_tool("web_search", {"query": "q"}, "agent_x")
                 for _ in range(4)]
    check(all("[stub result]" in r for r in results_x[:3]), "agent_x gets its first 3 searches")
    check("your search limit" in results_x[3], "agent_x's 4th search blocked by per-agent cap")

    # agent y: only 2 left in the shared budget of 5
    results_y = [await agent_loop._execute_tool("web_search", {"query": "q"}, "agent_y")
                 for _ in range(3)]
    check(all("[stub result]" in r for r in results_y[:2]), "agent_y draws remaining shared budget")
    check("shared search limit" in results_y[2], "shared cap blocks agent_y after budget exhausted")

    # reset clears both counters
    agent_loop.reset_search_count()
    r = await agent_loop._execute_tool("web_search", {"query": "q"}, "agent_x")
    check("[stub result]" in r, "reset_search_count clears per-agent and shared counters")

    # restore real values + search singleton for any live phase that follows
    agent_loop._search = None
    from config import load_config
    fresh = load_config()
    settings.search.max_searches = fresh.search.max_searches
    settings.search.max_searches_per_agent = fresh.search.max_searches_per_agent
    agent_loop.reset_search_count()


def _offline_brand_store():
    from brand_store import BrandAI

    with tempfile.TemporaryDirectory() as tmp:
        store = BrandAI("test_shop", base_dir=tmp)
        check(store.latest_research() is None, "empty store returns None")
        report = {"shop": {"name": "Test"}, "desires": [{"rank": 1}]}
        paths = store.save_research(report, "# Report\n\nbody")
        check(all(p.exists() for p in paths.values()), "snapshot files written")
        loaded = store.latest_research()
        check(loaded is not None and loaded[0] == report and loaded[1].startswith("# Report"),
              "latest_research round-trips the newest snapshot")


# ─────────────────────────────────────────────
# Live — Synthesizer (and optionally full pipeline)
# ─────────────────────────────────────────────

REQUIRED_SECTIONS = [
    "shop", "segments", "desires", "problems", "hooks", "objections",
    "market_sophistication", "desire_map", "yes_stack", "bright_dark_side",
    "unique_mechanism_candidates", "belief_mechanisms", "buzzwords",
    "success_patterns", "voice_bank",
]
SEGMENT_KEYS = {"A_team_pride", "B_gift_giver", "C_brand_builder", "D_aesthetic_buyer"}

# Floors are deliberately below the prompt targets (30/20/20/15) — the prompt
# forbids fabricating evidence, so thin sources may yield fewer. Day 5 judges quality.
MIN_COUNTS = {"desires": 20, "problems": 12, "hooks": 12, "objections": 10,
              "buzzwords": 15, "success_patterns": 8}


def validate_report(report: dict, markdown: str):
    missing = [s for s in REQUIRED_SECTIONS if s not in report]
    check(not missing, f"all required sections present (missing: {missing})")

    for key, minimum in MIN_COUNTS.items():
        n = len(report.get(key, []))
        check(n >= minimum, f"{key}: {n} items (floor {minimum})")

    check(SEGMENT_KEYS <= set(report.get("segments", {})), "all 4 segments assessed")
    soph = report.get("market_sophistication", {})
    check(isinstance(soph, dict) and 1 <= soph.get("stage", 0) <= 5,
          f"sophistication stage 1–5 with reasoning (got {soph.get('stage')})")

    desires = report.get("desires", [])
    with_evidence = sum(1 for d in desires
                        if isinstance(d.get("evidence"), dict) and d["evidence"].get("quote"))
    check(with_evidence >= len(desires) * 0.5,
          f"≥50% of desires carry verbatim evidence ({with_evidence}/{len(desires)})")

    hooks = report.get("hooks", [])
    check(all("visual_hook" in h and "text_hook" in h for h in hooks),
          "every hook has BOTH visual_hook and text_hook")

    dmap = report.get("desire_map", [])
    check(isinstance(dmap, list) and len(dmap) >= 5
          and all("up" in d and "down" in d for d in dmap),
          f"desire_map has ≥5 UP/DOWN entries (got {len(dmap) if isinstance(dmap, list) else 0})")
    check(len(report.get("yes_stack", [])) >= 5, "yes_stack has ≥5 beliefs")
    check(len(report.get("bright_dark_side", [])) >= 4, "bright_dark_side has ≥4 entries")

    check(len(markdown) > 15000, f"markdown narrative is substantial ({len(markdown):,} chars)")
    check(markdown.lstrip().startswith("#"), "markdown starts with a heading")
    for heading in ("Executive Summary", "Desire Map", "Yes Stack", "Objection"):
        check(heading.lower() in markdown.lower(), f"markdown covers '{heading}'")


async def _live_synthesizer_from_static():
    from agent1_synthesizer import _load_static_research, run_synthesizer

    a, b, c = _load_static_research()
    report, markdown = await run_synthesizer(a, b, c)
    validate_report(report, markdown)
    return report, markdown


async def _live_full_pipeline():
    import json
    from agent1_market_research import run_market_research

    paths = await run_market_research()
    json_path = paths["market_research_report"]
    md_path = paths["brand_intelligence_report"]
    check(json_path.exists() and md_path.exists(), "both data-contract files written")
    report = json.loads(json_path.read_text(encoding="utf-8"))
    validate_report(report, md_path.read_text(encoding="utf-8"))

    from brand_store import BrandAI
    latest = BrandAI("embroidery_shop").latest_research()
    check(latest is not None and latest[0] == report, "BrandAI snapshot matches output files")


def main() -> int:
    full = "--full" in sys.argv

    print("── Offline: per-agent search cap " + "─" * 30)
    asyncio.run(_offline_search_caps())
    print("\n── Offline: BrandAI storage " + "─" * 35)
    _offline_brand_store()

    if full:
        print("\n── Live: FULL pipeline (gather A/B/C + Synthesizer) " + "─" * 10)
        asyncio.run(_live_full_pipeline())
    else:
        print("\n── Live: Synthesizer from static output/research_*.json " + "─" * 6)
        asyncio.run(_live_synthesizer_from_static())

    print()
    if failures:
        print(f"✗ test_market_research FAILED ({len(failures)} assertion(s))")
        return 1
    print("✓ test_market_research passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
