"""
Model options offered in the dashboard model picker — id, label, cost tier,
pricing ($/1M tokens), and a one-line pros/cons each. Grouped by provider; a run
uses a single provider (config.yaml `llm.provider`), so the picker only offers
that provider's models.

This module is also the single source of Gemini pricing — `core/reporter.py`
merges `price_map()` into its cost table so the dashboard's cost badges and the
run report never drift.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelOption:
    id: str
    label: str
    tier: str          # cost badge: "$" / "$$" / "$$$"
    price_in: float    # USD per 1M input tokens
    price_out: float   # USD per 1M output tokens
    pros: str
    cons: str

    def as_dict(self) -> dict:
        return {
            "id": self.id, "label": self.label, "tier": self.tier,
            "price_in": self.price_in, "price_out": self.price_out,
            "pros": self.pros, "cons": self.cons,
        }


# Verified against ai.google.dev/gemini-api/docs/pricing (paid tier, ≤200k context).
_GEMINI = [
    ModelOption(
        "gemini-2.5-pro", "Gemini 2.5 Pro", "$$$", 1.25, 10.00,
        pros="Best reasoning & long-form quality; reliable function/tool calling.",
        cons="~4× Flash cost and slower — overkill for extraction or formatting.",
    ),
    ModelOption(
        "gemini-2.5-flash", "Gemini 2.5 Flash", "$$", 0.30, 2.50,
        pros="Fast and cheap; strong for search, extraction and JSON-as-text output.",
        cons="Weaker deep reasoning/synthesis; unreliable for function calling "
             "(MALFORMED_FUNCTION_CALL) — avoid for tool-using agents.",
    ),
    ModelOption(
        "gemini-2.5-flash-lite", "Gemini 2.5 Flash-Lite", "$", 0.10, 0.40,
        pros="Cheapest & fastest (3× cheaper in / 6× cheaper out than Flash); "
             "fine for pure extraction or classification.",
        cons="Weakest reasoning — not for synthesis, judgment, or tool calling.",
    ),
]

OPTIONS_BY_PROVIDER: dict[str, list[ModelOption]] = {
    "gemini": _GEMINI,
    # anthropic / openai option lists can be added here when those providers are used.
}


def options_for(provider: str) -> list[ModelOption]:
    """The model options offered for the active provider (empty if unknown)."""
    return OPTIONS_BY_PROVIDER.get(provider, [])


def price_map() -> dict[str, tuple[float, float]]:
    """{model_id: (in $/1M, out $/1M)} across all catalogued models."""
    return {
        opt.id: (opt.price_in, opt.price_out)
        for opts in OPTIONS_BY_PROVIDER.values()
        for opt in opts
    }
