"""
BrandAI — persistent, timestamped store of research artifacts per shop.

output/ holds the *current* pipeline data-contract files (overwritten each run);
brand_ai/<shop_slug>/ accumulates a timestamped history so past research is
never lost and Agent 8's feedback loop can diff against earlier runs.

    store = BrandAI("embroidery_shop")
    paths = store.save_research(report_dict, markdown_str)
    report, md = store.latest_research()
"""

import json
from datetime import datetime
from pathlib import Path

from config import settings
from logger import get_logger

log = get_logger(__name__)

_JSON_SUFFIX = "market_research_report.json"
_MD_SUFFIX = "brand_intelligence_report.md"


class BrandAI:
    def __init__(self, shop_slug: str, base_dir: str | Path | None = None):
        self._dir = Path(base_dir or settings.paths.brand_ai) / shop_slug

    @property
    def directory(self) -> Path:
        return self._dir

    def save_research(self, report: dict, markdown: str) -> dict[str, Path]:
        """Save a timestamped snapshot; returns the two file paths."""
        self._dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_path = self._dir / f"{ts}_{_JSON_SUFFIX}"
        md_path = self._dir / f"{ts}_{_MD_SUFFIX}"
        json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        md_path.write_text(markdown, encoding="utf-8")
        log.info("brand_ai snapshot saved json=%s md=%s", json_path, md_path)
        return {"market_research_report": json_path, "brand_intelligence_report": md_path}

    def latest_research(self) -> tuple[dict, str] | None:
        """Load the most recent snapshot, or None if no research saved yet."""
        json_files = sorted(self._dir.glob(f"*_{_JSON_SUFFIX}"))
        if not json_files:
            return None
        json_path = json_files[-1]
        md_path = json_path.with_name(json_path.name.replace(_JSON_SUFFIX, _MD_SUFFIX))
        report = json.loads(json_path.read_text(encoding="utf-8"))
        markdown = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
        return report, markdown
