"""
Loads config.yaml and env vars into typed settings objects.
All other modules import from here — never read env vars directly.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
import yaml
from dotenv import load_dotenv

load_dotenv()

# Project root = the outer embroidery/ directory (holds config.yaml, venv, data/).
# config.py lives at embroidery/embroidery/core/config.py, so go up three levels.
PROJECT_ROOT = Path(__file__).resolve().parents[2]

_CONFIG_FILE = PROJECT_ROOT / "config.yaml"


def _resolve(p: str | Path) -> Path:
    """Resolve a config path against PROJECT_ROOT so it works from any CWD."""
    p = Path(p)
    return p if p.is_absolute() else PROJECT_ROOT / p


@dataclass
class ModelSettings:
    model: str
    max_tokens: int = 8096


@dataclass
class AgentSettings:
    audience_researcher: ModelSettings = field(default_factory=lambda: ModelSettings("claude-haiku-4-5"))
    competitor_analyst: ModelSettings = field(default_factory=lambda: ModelSettings("claude-haiku-4-5"))
    social_media_analyst: ModelSettings = field(default_factory=lambda: ModelSettings("claude-haiku-4-5"))
    synthesizer: ModelSettings = field(default_factory=lambda: ModelSettings("claude-haiku-4-5", 16000))
    avatar_builder: ModelSettings = field(default_factory=lambda: ModelSettings("claude-sonnet-4-6"))
    positioning_strategist: ModelSettings = field(default_factory=lambda: ModelSettings("claude-opus-4-8"))
    hook_generator: ModelSettings = field(default_factory=lambda: ModelSettings("claude-sonnet-4-6"))
    script_writer: ModelSettings = field(default_factory=lambda: ModelSettings("claude-opus-4-8", 16000))
    static_copy_writer: ModelSettings = field(default_factory=lambda: ModelSettings("claude-sonnet-4-6"))
    qa_reviewer: ModelSettings = field(default_factory=lambda: ModelSettings("claude-sonnet-4-6", 4096))
    feedback_analyst: ModelSettings = field(default_factory=lambda: ModelSettings("claude-sonnet-4-6"))
    orchestrator: ModelSettings = field(default_factory=lambda: ModelSettings("claude-opus-4-8"))


@dataclass
class SearchSettings:
    provider: str = "duckduckgo"
    max_searches: int = 20           # shared budget per pipeline run
    max_searches_per_agent: int = 8  # cap per agent_name within one run


@dataclass
class PathSettings:
    output: Path = field(default_factory=lambda: _resolve("data/output"))
    brand_ai: Path = field(default_factory=lambda: _resolve("data/brand_ai"))
    logs: Path = field(default_factory=lambda: _resolve("data/logs"))
    fixtures: Path = field(default_factory=lambda: _resolve("fixtures"))


@dataclass
class Config:
    llm_provider: str = "anthropic"
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    brave_api_key: str = field(default_factory=lambda: os.getenv("BRAVE_API_KEY", ""))
    search: SearchSettings = field(default_factory=SearchSettings)
    agents: AgentSettings = field(default_factory=AgentSettings)
    paths: PathSettings = field(default_factory=PathSettings)


def load_config(path: Path = _CONFIG_FILE) -> Config:
    with open(path) as f:
        raw = yaml.safe_load(f)

    search_raw = raw.get("search", {})
    agents_raw = raw.get("agents", {})
    paths_raw = raw.get("paths", {})

    agents = AgentSettings()
    for name, settings in agents_raw.items():
        if hasattr(agents, name):
            setattr(agents, name, ModelSettings(
                model=settings.get("model", "claude-haiku-4-5"),
                max_tokens=settings.get("max_tokens", 8096),
            ))

    return Config(
        llm_provider=raw.get("llm", {}).get("provider", "anthropic"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        brave_api_key=os.getenv("BRAVE_API_KEY", ""),
        search=SearchSettings(
            provider=search_raw.get("provider", "duckduckgo"),
            max_searches=search_raw.get("max_searches", 20),
            max_searches_per_agent=search_raw.get("max_searches_per_agent", 8),
        ),
        agents=agents,
        paths=PathSettings(
            output=_resolve(paths_raw.get("output", "data/output")),
            brand_ai=_resolve(paths_raw.get("brand_ai", "data/brand_ai")),
            logs=_resolve(paths_raw.get("logs", "data/logs")),
            fixtures=_resolve(paths_raw.get("fixtures", "fixtures")),
        ),
    )


# Module-level singleton — import this everywhere
settings = load_config()
