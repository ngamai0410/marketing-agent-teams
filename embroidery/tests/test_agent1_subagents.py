"""
Day 3 test — run each Market Research sub-agent with the short shop brief
and verify its JSON output structure matches the schema contract.

Live test: makes real web_search (Brave) and LLM (gemini-2.5-flash) calls.
Each sub-agent is capped at 6 searches + 3 fetches by its prompt and 16 tool
calls by the loop; the three runs together stay well under $0.30.

Run all three (sequential — Brave free tier is rate-limited):
    cd embroidery && venv/bin/python -m tests.test_agent1_subagents
Run one:
    cd embroidery && venv/bin/python -m tests.test_agent1_subagents a
"""

import asyncio
import sys

from embroidery.agents.research.subagents import SUBAGENTS, run_subagent

HOOK_CATEGORIES = {"size-of-claim", "speed-of-claim", "curiosity-gap", "problem-first", "identity"}
SEGMENT_KEYS = {"A_team_pride", "B_gift_giver", "C_brand_builder", "D_aesthetic_buyer"}

failures: list[str] = []


def check(cond: bool, msg: str):
    print(("✓ " if cond else "✗ ") + msg)
    if not cond:
        failures.append(msg)


def non_empty_list(data: dict, key: str, minimum: int = 1) -> list:
    val = data.get(key)
    check(isinstance(val, list) and len(val) >= minimum,
          f"{key} is a list with ≥{minimum} items (got {len(val) if isinstance(val, list) else type(val).__name__})")
    return val if isinstance(val, list) else []


def validate_a(data: dict):
    desires = non_empty_list(data, "top_desires", 8)
    check(all("statement" in d and "lf8_tag" in d for d in desires),
          "every desire has statement + lf8_tag")
    check(any(str(d.get("lf8_tag", "")).upper().startswith("LF") for d in desires),
          "lf8_tag values use LF1–LF8 form")
    problems = non_empty_list(data, "top_problems", 5)
    check(all("when" in p and "why" in p for p in problems),
          "every problem uses WHEN+WHY format")
    check(all(isinstance(p.get("node_check"), dict) for p in problems),
          "every problem carries the Problem Node 3-check")
    vb = data.get("voice_bank", {})
    check(isinstance(vb, dict) and any(vb.get(k) for k in ("desire_phrases", "pain_phrases", "objection_phrases")),
          "voice_bank has verbatim phrases")
    non_empty_list(data, "objections", 5)
    check(isinstance(data.get("identity_markers"), dict) and data["identity_markers"],
          "identity_markers present")


def validate_b(data: dict):
    soph = data.get("sophistication_assessment", {})
    check(isinstance(soph.get("stage"), int) and 1 <= soph["stage"] <= 5,
          f"sophistication stage is 1–5 (got {soph.get('stage')})")
    alts = soph.get("alternatives_considered", [])
    check(isinstance(alts, list) and len(alts) >= 3,
          f"≥3 indirect alternatives considered (got {len(alts)})")
    awareness = data.get("awareness_levels_by_segment", {})
    check(SEGMENT_KEYS <= set(awareness),
          f"awareness covers all 4 segments (got {sorted(awareness)})")
    check(all(isinstance(v, dict) and 1 <= v.get("level", 0) <= 5 for v in awareness.values()),
          "every segment awareness level is 1–5 with evidence")
    ums = non_empty_list(data, "unique_mechanism_candidates", 2)
    check(all(um.get("type") in (1, 2, 3, "1", "2", "3") for um in ums),
          "every mechanism candidate has Type 1/2/3")
    non_empty_list(data, "competitors", 3)
    check(isinstance(data.get("5x5_matrix_cell"), dict), "5x5_matrix_cell present")


def validate_c(data: dict):
    patterns = non_empty_list(data, "hook_patterns", 5)
    check(all(p.get("category") in HOOK_CATEGORIES for p in patterns),
          "every hook pattern uses a valid category")
    hooks = non_empty_list(data, "top_hooks_to_adapt", 5)
    check(all("visual_hook" in h and "text_hook" in h for h in hooks),
          "every adaptable hook has BOTH visual_hook and text_hook")
    themes = data.get("comment_themes", {})
    check(isinstance(themes, dict) and any(themes.get(k) for k in ("positive", "negative", "questions")),
          "comment_themes populated")
    non_empty_list(data, "content_structure_patterns", 3)


VALIDATORS = {"a": validate_a, "b": validate_b, "c": validate_c}


def main() -> int:
    keys = [sys.argv[1].lower()] if len(sys.argv) > 1 else list(SUBAGENTS)
    if any(k not in SUBAGENTS for k in keys):
        print("Usage: python -m tests.test_agent1_subagents [a|b|c]")
        return 2

    for key in keys:
        spec = SUBAGENTS[key]
        print(f"\n── Agent {key.upper()} ({spec.name}) " + "─" * 30)
        try:
            data = asyncio.run(run_subagent(key))
        except Exception as e:
            check(False, f"agent {key} run failed: {e}")
            continue
        check(isinstance(data, dict), "final output parsed as JSON object")
        VALIDATORS[key](data)

    print()
    if failures:
        print(f"✗ test_agent1_subagents FAILED ({len(failures)} assertion(s))")
        return 1
    print("✓ test_agent1_subagents passed — all sub-agent schemas valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
