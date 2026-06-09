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

_CONFIG_FILE = Path(__file__).parent / "config.yaml"


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
    max_searches: int = 20


@dataclass
class PathSettings:
    output: str = "output"
    brand_ai: str = "brand_ai"


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
        ),
        agents=agents,
        paths=PathSettings(
            output=paths_raw.get("output", "output"),
            brand_ai=paths_raw.get("brand_ai", "brand_ai"),
        ),
    )


# Module-level singleton — import this everywhere
settings = load_config()
