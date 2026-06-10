"""
Search engine abstraction.

Switching search providers: change `search.provider` in config.yaml.
Options: brave | duckduckgo
"""

import json
from abc import ABC, abstractmethod

import aiohttp

from config import settings


class SearchProvider(ABC):
    @abstractmethod
    async def search(self, query: str, num_results: int = 10) -> str:
        """Return search results as a formatted string."""
        ...

    @abstractmethod
    async def fetch(self, url: str) -> str:
        """Fetch and return page content from a URL."""
        ...


# ─────────────────────────────────────────────
# Brave Search
# ─────────────────────────────────────────────

class BraveSearch(SearchProvider):
    _BASE = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self, api_key: str):
        self._api_key = api_key

    async def search(self, query: str, num_results: int = 10) -> str:
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self._api_key,
        }
        params = {"q": query, "count": min(num_results, 20)}

        async with aiohttp.ClientSession() as session:
            async with session.get(self._BASE, headers=headers, params=params) as resp:
                if resp.status != 200:
                    return f"[Brave search error: HTTP {resp.status}]"
                data = await resp.json()

        results = data.get("web", {}).get("results", [])
        lines = []
        for r in results:
            lines.append(f"Title: {r.get('title', '')}")
            lines.append(f"URL: {r.get('url', '')}")
            lines.append(f"Snippet: {r.get('description', '')}")
            lines.append("")
        return "\n".join(lines) if lines else "[no results]"

    async def fetch(self, url: str) -> str:
        return await _fetch_url(url)


# ─────────────────────────────────────────────
# DuckDuckGo (free, no API key)
# ─────────────────────────────────────────────

class DuckDuckGoSearch(SearchProvider):
    async def search(self, query: str, num_results: int = 10) -> str:
        from ddgs import DDGS

        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=num_results):
                results.append(
                    f"Title: {r.get('title', '')}\n"
                    f"URL: {r.get('href', '')}\n"
                    f"Snippet: {r.get('body', '')}\n"
                )
        return "\n".join(results) if results else "[no results]"

    async def fetch(self, url: str) -> str:
        return await _fetch_url(url)


# ─────────────────────────────────────────────
# Shared URL fetcher
# ─────────────────────────────────────────────

async def _fetch_url(url: str) -> str:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; research-agent/1.0)"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return f"[fetch error: HTTP {resp.status}]"
                content_type = resp.content_type or ""
                if "html" in content_type or "text" in content_type:
                    text = await resp.text()
                    return text[:8000]  # cap to avoid flooding context
                return f"[non-text content: {content_type}]"
    except Exception as e:
        return f"[fetch error: {e}]"


# ─────────────────────────────────────────────
# Factory
# ─────────────────────────────────────────────

def get_search_provider() -> SearchProvider:
    provider = settings.search.provider
    if provider == "brave":
        if not settings.brave_api_key:
            raise ValueError("BRAVE_API_KEY not set. Add it to .env or switch to duckduckgo in config.yaml.")
        return BraveSearch(api_key=settings.brave_api_key)
    if provider == "duckduckgo":
        return DuckDuckGoSearch()
    raise ValueError(f"Unknown search.provider: '{provider}'. Options: brave | duckduckgo")
