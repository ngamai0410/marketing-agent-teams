"""
Model catalog + per-agent model override store. No providers, no tokens.

Run: cd embroidery && venv/bin/python -m tests.test_model_store
"""
import sys

failures: list[str] = []

def check(cond, msg):
    print(("✓ " if cond else "✗ ") + msg)
    if not cond:
        failures.append(msg)


def test_catalog():
    from embroidery.core import model_catalog as M
    opts = M.options_for("gemini")
    ids = [o.id for o in opts]
    check(ids == ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite"],
          "gemini catalog offers pro / flash / flash-lite in that order")
    lite = next(o for o in opts if o.id == "gemini-2.5-flash-lite")
    check((lite.price_in, lite.price_out) == (0.10, 0.40), "flash-lite price is $0.10/$0.40")
    check(all(o.pros and o.cons for o in opts), "every option has pros + cons text")
    check(M.options_for("unknown") == [], "unknown provider -> no options")
    pm = M.price_map()
    check(pm["gemini-2.5-pro"] == (1.25, 10.0), "price_map carries pro pricing")


def test_reporter_prices_merged():
    from embroidery.core.reporter import PRICES
    check(PRICES.get("gemini-2.5-flash-lite") == (0.10, 0.40),
          "reporter PRICES merged flash-lite from the catalog")
    check(PRICES.get("claude-opus-4-8") == (5.0, 25.0), "reporter still has Anthropic prices")


def test_store_set_reset():
    from embroidery.core.config import settings
    from embroidery.core.model_store import get_model_store
    store = get_model_store()
    key = "audience_researcher"
    check(key in store.keys(), "store enumerates agent keys")
    default = store.default(key)
    check(default is not None, "store snapshots a config default")

    prior = store.current(key) if store.is_overridden(key) else None
    try:
        store.set(key, "gemini-2.5-flash-lite")
        check(getattr(settings.agents, key).model == "gemini-2.5-flash-lite",
              "set() applies the override onto settings.agents")
        check(store.is_overridden(key) and store.current(key) == "gemini-2.5-flash-lite",
              "set() marks overridden + reports current")
        check(getattr(settings.agents, key).max_tokens > 0, "set() keeps max_tokens intact")
        store.reset(key)
        check(getattr(settings.agents, key).model == default and not store.is_overridden(key),
              "reset() restores the config default")
    finally:
        if prior is not None:
            store.set(key, prior)
        else:
            store.reset(key)


def test_catalog_items_carry_model_key():
    import embroidery.agents.avatar.pipeline  # ensure registered/imported
    from embroidery.agents.research import subagents
    cat = subagents.prompt_catalog()
    by_id = {c["id"]: c for c in cat}
    check(by_id["research.audience_researcher"]["model_key"] == "audience_researcher",
          "agent prompt item carries its model_key")
    check(by_id["research.shared_rules"]["model_key"] is None, "shared block has no model_key")
    check(by_id["shared.shop_context"]["model_key"] is None, "shop context has no model_key")


def main() -> int:
    test_catalog()
    test_reporter_prices_merged()
    test_store_set_reset()
    test_catalog_items_carry_model_key()
    if failures:
        print(f"\n✗ test_model_store FAILED ({len(failures)})")
        return 1
    print("\n✓ test_model_store passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
