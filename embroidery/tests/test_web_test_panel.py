"""
Test-pillar endpoints: /artifacts lists present output files; /prompts/preview
renders a template with sample context; seed-fixture copies a fixture into output.

Run: cd embroidery && venv/bin/python -m tests.test_web_test_panel
"""
import asyncio
import sys
from pathlib import Path

from embroidery.web import server
from embroidery.core.config import settings

failures: list[str] = []

def check(cond, msg):
    print(("✓ " if cond else "✗ ") + msg)
    if not cond:
        failures.append(msg)

def main() -> int:
    out = Path(settings.paths.output)
    out.mkdir(parents=True, exist_ok=True)
    (out / "_probe.json").write_text("{}", encoding="utf-8")

    arts = asyncio.run(server.list_artifacts())
    check("_probe.json" in arts["files"], "/artifacts lists present output files")

    pv = asyncio.run(server.preview_prompt(server.PreviewBody(
        id="research.audience_researcher",
        text="Shop is ${shop_context} end")))
    check("SHOP CONTEXT" in pv["rendered"], "/prompts/preview substitutes sample shop_context")

    # seed a known fixture into output and confirm the helper copies it
    seeded = server._seed_fixtures(["positioning_matrix.json"])
    check((out / "positioning_matrix.json").exists(), "_seed_fixtures copies fixture into output")
    check(seeded == ["positioning_matrix.json"], "_seed_fixtures returns the copied names")

    if failures:
        print(f"\n✗ test_web_test_panel FAILED ({len(failures)})")
        return 1
    print("\n✓ test_web_test_panel passed")
    return 0

if __name__ == "__main__":
    sys.exit(main())
