"""
web_fetch hardening: a browser-like header set (not a bot UA that gets 403),
and an actionable message when a site blocks direct fetching. No network.

Run: cd embroidery && venv/bin/python -m tests.test_fetch
"""
import sys

failures: list[str] = []

def check(cond, msg):
    print(("✓ " if cond else "✗ ") + msg)
    if not cond:
        failures.append(msg)


def main() -> int:
    from embroidery.core import search

    ua = search._FETCH_HEADERS.get("User-Agent", "")
    check("research-agent" not in ua, "fetch UA is not the bot-identifying 'research-agent' string")
    check("Mozilla" in ua and ("Chrome" in ua or "Safari" in ua), "fetch UA is browser-like")
    check("Accept-Language" in search._FETCH_HEADERS, "fetch sends Accept-Language")

    note = search._fetch_blocked_note(403, "https://www.etsy.com/shop/EverCherishStudio?ref=x")
    check("web_search" in note, "blocked note tells the agent to use web_search")
    check("403" in note, "blocked note names the HTTP status")
    check("etsy.com" in note, "blocked note names the host")

    if failures:
        print(f"\n✗ test_fetch FAILED ({len(failures)})")
        return 1
    print("\n✓ test_fetch passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
