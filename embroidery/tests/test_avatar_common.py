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

def test_common():
    import asyncio
    from embroidery.agents.avatar import _common as C

    agent = C.AvatarAgent(
        name="probe_agent", label="Probe", model_key="avatar_onboarder",
        system_template="Hello {priority_count}. Schema: {{\"k\": 1}}", output_file=None,
    )
    rendered = C.build_system(agent, priority_count="world")
    check("Hello world" in rendered, "build_system substitutes context placeholders")
    check('{"k": 1}' in rendered, "build_system preserves literal JSON braces")

    # run_json_agent: stub run_agent, assert it parses + (here) does not write
    captured = {}
    async def fake_run_agent(*, system, messages, tools, model_settings, max_tool_calls, agent_name):
        captured["agent_name"] = agent_name
        return '{"ok": true}'
    C.run_agent = fake_run_agent
    out = asyncio.run(C.run_json_agent(agent, "go", tools=[], ctx={"priority_count": "x"}))
    check(out == {"ok": True}, "run_json_agent parses JSON-as-text final message")
    check(captured["agent_name"] == "probe_agent", "run_json_agent passes agent_name through")

    items = C.catalog_items([agent], {"probe_agent": ["priority_count"]}, "Avatar — probe")
    check(items[0]["id"] == "avatar.probe_agent", "catalog_items builds prefixed prompt id")
    check(items[0]["placeholders"] == ["priority_count"], "catalog_items carries placeholders")


def test_framing():
    from embroidery.agents.avatar import framing
    cat = framing.prompt_catalog()
    ids = {c["id"] for c in cat}
    check(ids == {"avatar.avatar_onboarder", "avatar.product_analyst"},
          "framing exposes onboarder + product_analyst prompts")
    check(framing.ONBOARDER.output_file == "avatar_onboarding.json", "onboarder writes avatar_onboarding.json")


def test_discovery():
    from embroidery.agents.avatar import discovery
    ids = {c["id"] for c in discovery.prompt_catalog()}
    check(ids == {"avatar.reddit_scout", "avatar.amazon_voc", "avatar.fb_ad_scout", "avatar.avatar_qualifier"},
          "discovery exposes 3 scouts + qualifier prompts")
    check(discovery.QUALIFIER.output_file == "avatar_qualification.json", "qualifier writes avatar_qualification.json")


def test_voc():
    from embroidery.agents.avatar import voc
    ids = {c["id"] for c in voc.prompt_catalog()}
    check(ids == {"avatar.voc_miner"}, "voc exposes the voc_miner prompt")


def main() -> int:
    test_config()
    test_common()
    test_framing()
    test_discovery()
    test_voc()
    if failures:
        print(f"\n✗ test_avatar_common FAILED ({len(failures)})")
        return 1
    print("\n✓ test_avatar_common passed")
    return 0

if __name__ == "__main__":
    sys.exit(main())
