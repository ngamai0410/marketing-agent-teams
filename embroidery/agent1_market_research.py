"""
Agent 1: Market Research — the full mini-pipeline (Day 4 wiring).

    brief → asyncio.gather(A, B, C) → Synthesizer → output files + BrandAI snapshot

Replaces the legacy single-prompt Agent 1: research is now done by three
parallel search-only sub-agents (agent1_subagents.py) whose JSON outputs are
merged by a no-tool Synthesizer (agent1_synthesizer.py). Produces the two
Stage 1 data-contract files consumed by Agents 2 and 3:

  output/market_research_report.json
  output/brand_intelligence_report.md

plus a timestamped history snapshot in brand_ai/embroidery_shop/.

Run:
    cd embroidery && venv/bin/python agent1_market_research.py
"""

import asyncio
import json
from pathlib import Path

from agent1_subagents import SHOP_BRIEF, run_subagent
from agent1_synthesizer import run_synthesizer
from agent_loop import reset_search_count
from brand_store import BrandAI
from config import settings
from logger import get_logger

log = get_logger(__name__)

SHOP_SLUG = "embroidery_shop"   # brand_ai/ subdirectory for this shop


async def run_market_research(brief: dict = SHOP_BRIEF) -> dict[str, Path]:
    """Run the full Agent 1 pipeline; returns paths to the two output files."""
    # One shared search budget for the whole run (search.max_searches), with a
    # per-agent cap (search.max_searches_per_agent) enforced inside agent_loop.
    reset_search_count()

    log.info("market_research pipeline starting — dispatching sub-agents A/B/C in parallel")
    research_a, research_b, research_c = await asyncio.gather(
        run_subagent("a", brief, reset_searches=False),
        run_subagent("b", brief, reset_searches=False),
        run_subagent("c", brief, reset_searches=False),
    )

    log.info("sub-agents complete — running synthesizer")
    report, markdown = await run_synthesizer(research_a, research_b, research_c, brief)

    out = Path(settings.paths.output)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "market_research_report.json"
    md_path = out / "brand_intelligence_report.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")

    BrandAI(SHOP_SLUG).save_research(report, markdown)

    log.info("market_research pipeline done json=%s md=%s", json_path, md_path)
    return {"market_research_report": json_path, "brand_intelligence_report": md_path}


if __name__ == "__main__":
    paths = asyncio.run(run_market_research())
    for name, path in paths.items():
        size = path.stat().st_size if path.exists() else 0
        print(f"{name}: {path} ({size:,} bytes)")
