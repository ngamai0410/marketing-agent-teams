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


def test_reframe():
    from embroidery.agents.avatar import reframe
    ids = {c["id"] for c in reframe.prompt_catalog()}
    check(ids == {"avatar.awareness_mapper", "avatar.competitor_teardown", "avatar.mechanism_builder"},
          "reframe exposes awareness + competitor + mechanism prompts")


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


def test_shop_context_editable():
    from embroidery.core.prompt_store import get_prompt_store
    from embroidery.agents.research.subagents import (
        SHOP_CONTEXT_PROMPT_ID, effective_shop_context, shop_context_catalog_item)
    from embroidery.agents.avatar import _common as C
    from embroidery.agents.avatar.framing import ONBOARDER

    item = shop_context_catalog_item()
    check(item["id"] == "shared.shop_context", "shop_context catalog item has the shared id")
    check("SHOP CONTEXT" in item["default"], "shop_context default is the rendered brief")

    store = get_prompt_store()
    # save any pre-existing override so the test never clobbers a real one
    prior = store.text(SHOP_CONTEXT_PROMPT_ID, None) if store.is_overridden(SHOP_CONTEXT_PROMPT_ID) else None
    store.reset(SHOP_CONTEXT_PROMPT_ID)
    try:
        check(effective_shop_context("DEFAULT") == "DEFAULT", "no override -> default value used")
        store.set(SHOP_CONTEXT_PROMPT_ID, "MY CUSTOM SHOP CONTEXT")
        check(effective_shop_context("DEFAULT") == "MY CUSTOM SHOP CONTEXT",
              "override -> override value used")
        rendered = C.build_system(ONBOARDER, shop_context="ORIGINAL")
        check("MY CUSTOM SHOP CONTEXT" in rendered and "ORIGINAL" not in rendered,
              "avatar build_system applies the shop_context override")
    finally:
        if prior is not None:
            store.set(SHOP_CONTEXT_PROMPT_ID, prior)
        else:
            store.reset(SHOP_CONTEXT_PROMPT_ID)


def main() -> int:
    test_config()
    test_common()
    test_framing()
    test_discovery()
    test_voc()
    test_reframe()
    test_synthesizer_writes_two_files()
    test_shop_context_editable()
    if failures:
        print(f"\n✗ test_avatar_common FAILED ({len(failures)})")
        return 1
    print("\n✓ test_avatar_common passed")
    return 0

if __name__ == "__main__":
    sys.exit(main())
