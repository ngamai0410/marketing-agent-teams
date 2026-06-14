"""
Per-agent model overrides chosen from the dashboard.

Mirrors `core/prompt_store.py`: a user picks a model for an agent in the UI; the
choice is persisted to `data/prompts/model_overrides.json` and applied to the
in-memory `settings.agents.<key>` (its `.model`, keeping `max_tokens`) so
`run_agent()` — which reads `getattr(settings.agents, key)` at call time — uses
it. `reset()` restores the config.yaml default snapshotted at construction.

Single-user/local only: this mutates the process-wide settings singleton.
"""

import json
from dataclasses import fields

from embroidery.core.config import settings
from embroidery.core.logger import get_logger

log = get_logger(__name__)


def _agent_keys() -> list[str]:
    return [f.name for f in fields(settings.agents)]


class ModelStore:
    def __init__(self) -> None:
        self._file = settings.paths.prompts / "model_overrides.json"
        # snapshot config defaults BEFORE applying any override (for reset)
        self._defaults: dict[str, str] = {k: getattr(settings.agents, k).model for k in _agent_keys()}
        self._overrides: dict[str, str] = {}
        if self._file.exists():
            try:
                self._overrides = json.loads(self._file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                log.warning("model overrides unreadable (%s) — ignoring", exc)
        self.apply_all()

    # -- queries --
    def keys(self) -> list[str]:
        return _agent_keys()

    def default(self, key: str) -> str | None:
        return self._defaults.get(key)

    def current(self, key: str) -> str | None:
        ms = getattr(settings.agents, key, None)
        return ms.model if ms else None

    def is_overridden(self, key: str) -> bool:
        return key in self._overrides

    # -- mutations --
    def set(self, key: str, model: str) -> None:
        if key not in self._defaults:
            raise KeyError(f"unknown agent {key!r}")
        self._overrides[key] = model
        self._apply(key, model)
        self._save()
        log.info("model override saved agent=%s model=%s", key, model)

    def reset(self, key: str) -> None:
        if self._overrides.pop(key, None) is not None:
            self._apply(key, self._defaults[key])
            self._save()
            log.info("model override reset agent=%s -> %s", key, self._defaults[key])

    # -- internals --
    def apply_all(self) -> None:
        for key, model in self._overrides.items():
            self._apply(key, model)

    def _apply(self, key: str, model: str) -> None:
        ms = getattr(settings.agents, key, None)
        if ms is not None:
            ms.model = model   # ModelSettings is a mutable dataclass; keep max_tokens

    def _save(self) -> None:
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._file.write_text(json.dumps(self._overrides, indent=2, ensure_ascii=False), encoding="utf-8")


_STORE: ModelStore | None = None


def get_model_store() -> ModelStore:
    global _STORE
    if _STORE is None:
        _STORE = ModelStore()
    return _STORE
