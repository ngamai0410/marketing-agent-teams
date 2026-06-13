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
    check(settings.avatar.priority_count == 2, "avatar.priority_count loaded from config.yaml")
    # proves config.yaml was actually read: 16000 differs from the Python default (8096)
    check(settings.agents.reddit_scout.max_tokens == 16000, "reddit_scout max_tokens loaded from config.yaml")
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
