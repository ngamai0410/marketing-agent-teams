"""
Editable prompt store — lets the end user view, edit, and save each agent's
system prompt before a run (from the web dashboard).

Why `string.Template` and not `str.format`:
The original prompts are `.format()` templates whose JSON-schema examples escape
every literal brace as `{{`/`}}` and inject context via `{shop_context}` etc. That
is hostile to hand-editing — a user typing normal JSON `{}` would crash `.format()`.
So we convert each template once (`to_dollar`) to a `$placeholder` form with plain
single braces, store/edit *that*, and render with `Template.safe_substitute` — which
treats braces as literal text and never raises on an unknown/removed placeholder.

`to_dollar()` reproduces `.format()` output exactly for the known keys (verified in
tests): `{{`→`{`, `}}`→`}`, and `{name}`→`${name}` for the injected placeholders.

Overrides persist to data/prompts/overrides.json (keyed by prompt id) so edits
survive restarts. A missing/blank override falls back to the converted default.
"""

import json
import string

from embroidery.core.config import settings
from embroidery.core.logger import get_logger

log = get_logger(__name__)

# Placeholder names converted to $-form by to_dollar(). This is an explicit
# allow-list ON PURPOSE: a generic "convert every {word}" rule would corrupt
# escaped literal braces like {{rank}}. Any NEW context key used in an agent
# system template (e.g. {priority_avatars}) MUST be added here, or it will not
# substitute and will render literally.
PLACEHOLDERS = ("shop_context", "shared_rules", "research_date", "shop_name",
                "priority_avatars", "priority_count")


def to_dollar(format_template: str) -> str:
    """Convert a `str.format` template (with `{{}}`-escaped braces) to a
    `string.Template` `$placeholder` template with plain single braces.

    Equivalent to `.format()` for the known PLACEHOLDERS — see test_prompt_store.
    """
    t = format_template.replace("{{", "{").replace("}}", "}")
    for name in PLACEHOLDERS:
        t = t.replace("{" + name + "}", "${" + name + "}")
    return t


class PromptStore:
    """Persisted per-prompt overrides + safe rendering."""

    def __init__(self) -> None:
        self._file = settings.paths.prompts / "overrides.json"
        self._overrides: dict[str, str] = {}
        if self._file.exists():
            try:
                self._overrides = json.loads(self._file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                log.warning("prompt overrides unreadable (%s) — ignoring", exc)

    def text(self, prompt_id: str, default: str) -> str:
        """Current prompt text — the override if a non-blank one is set, else default."""
        override = self._overrides.get(prompt_id)
        return override if (override and override.strip()) else default

    def is_overridden(self, prompt_id: str) -> bool:
        return bool(self._overrides.get(prompt_id, "").strip())

    def set(self, prompt_id: str, text: str) -> None:
        self._overrides[prompt_id] = text
        self._save()
        log.info("prompt override saved id=%s chars=%d", prompt_id, len(text))

    def reset(self, prompt_id: str) -> None:
        if self._overrides.pop(prompt_id, None) is not None:
            self._save()
            log.info("prompt override reset id=%s", prompt_id)

    def render(self, prompt_id: str, default: str, **values: str) -> str:
        """Render the current prompt, substituting `$placeholders` safely."""
        return string.Template(self.text(prompt_id, default)).safe_substitute(**values)

    def _save(self) -> None:
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._file.write_text(
            json.dumps(self._overrides, indent=2, ensure_ascii=False), encoding="utf-8"
        )


_store: PromptStore | None = None


def get_prompt_store() -> PromptStore:
    global _store
    if _store is None:
        _store = PromptStore()
    return _store
