"""
Manual test for Agent 7 (QA Reviewer) — run before any content agents exist.

Copies fixture inputs (positioning matrix + one strong script, one
deliberately corporate/product-first script, one strong static ad) into
output/, runs the QA agent, then asserts:
  1. qa_report.json exists and is valid JSON with the contract fields
  2. the gatekeeper discriminates: vid_giftgiver_01 PASS,
     vid_corporate_02 FAIL (with revision notes), overall FAIL

Run:
    cd embroidery && venv/bin/python test_agent7.py
"""

import asyncio
import json
import shutil
import sys
from pathlib import Path

from agent7_qa_reviewer import run_qa_review
from config import settings

FIXTURES = Path("fixtures")
OUTPUT = Path(settings.paths.output)


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name in ("positioning_matrix.json", "video_scripts.json", "static_ad_copy.json"):
        shutil.copy(FIXTURES / name, OUTPUT / name)

    report_path = asyncio.run(run_qa_review())

    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    ads = {ad["ad_id"]: ad for ad in report["ads"]}
    failures: list[str] = []

    def check(cond: bool, msg: str):
        print(("✓ " if cond else "✗ ") + msg)
        if not cond:
            failures.append(msg)

    check(report.get("overall") in ("PASS", "FAIL"), "overall is PASS or FAIL")
    check(len(ads) == 3, f"all 3 ads reviewed (got {len(ads)}: {sorted(ads)})")

    for ad in report["ads"]:
        qs = ad.get("question_scores", {})
        check(len(qs) == 8, f"{ad['ad_id']}: all 8 question scores present")
        check("revision_required" in ad, f"{ad['ad_id']}: revision_required present")

    good = ads.get("vid_giftgiver_01", {})
    bad = ads.get("vid_corporate_02", {})
    check(good.get("revision_required") is False, "strong script passes (no revision)")
    check(bad.get("revision_required") is True, "corporate script fails (revision required)")
    check(bool(bad.get("revision_notes")), "failing ad has revision notes")
    check(report.get("overall") == "FAIL", "overall FAIL when any ad fails")

    print()
    for ad in report["ads"]:
        verdict = "FAIL" if ad.get("revision_required") else "PASS"
        print(f"  {ad['ad_id']}: {verdict}")
    print(f"  OVERALL: {report.get('overall')}")

    if failures:
        print(f"\n✗ test_agent7 FAILED ({len(failures)} assertion(s))")
        return 1
    print("\n✓ test_agent7 passed — QA gatekeeper discriminates correctly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
