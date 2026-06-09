"""
Tool definitions (JSON schema format) for all agent types.

Import the relevant set into each agent file.
agent_loop.py handles execution — these are just the schemas sent to the LLM.
"""

# ─────────────────────────────────────────────
# Individual tool schemas
# ─────────────────────────────────────────────

_WEB_SEARCH = {
    "name": "web_search",
    "description": (
        "Search the web for information. Returns titles, URLs, and snippets "
        "for the top results. Use for market research, competitor analysis, "
        "Reddit mining, Amazon review research, and social media trend discovery."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query. Be specific — include product names, subreddit names, or site: operators when useful.",
            },
            "num_results": {
                "type": "integer",
                "description": "Number of results to return (default 10, max 20).",
                "default": 10,
            },
        },
        "required": ["query"],
    },
}

_WEB_FETCH = {
    "name": "web_fetch",
    "description": (
        "Fetch the full text content of a web page. Use to read Reddit threads, "
        "Amazon review pages, competitor product pages, or blog articles. "
        "Returns up to 8000 characters of page text."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The full URL to fetch (must start with http:// or https://).",
            },
        },
        "required": ["url"],
    },
}

_WRITE_FILE = {
    "name": "write_file",
    "description": (
        "Save content to a file in the output directory. "
        "Use JSON format for structured data, Markdown for reports."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "Filename including extension (e.g. market_research_report.json, brand_intelligence_report.md).",
            },
            "content": {
                "type": "string",
                "description": "The full file content to write.",
            },
        },
        "required": ["filename", "content"],
    },
}

_READ_FILE = {
    "name": "read_file",
    "description": (
        "Read the contents of a file from the output directory. "
        "Use to load upstream agent outputs before generating your own."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "Filename to read (e.g. market_research_report.json).",
            },
        },
        "required": ["filename"],
    },
}


# ─────────────────────────────────────────────
# Tool sets per agent type
# ─────────────────────────────────────────────

# Agent 1 Market Research sub-agents: web access + file write
RESEARCH_TOOLS = [_WEB_SEARCH, _WEB_FETCH, _WRITE_FILE]

# Analysis and copy agents (2–6): file I/O only, no web access
FILE_TOOLS = [_READ_FILE, _WRITE_FILE]
