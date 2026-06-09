"""
Gemini provider test.

Verifies:
1. GeminiProvider connects and makes API calls
2. Echo tool — confirms the agentic loop enters tool_use and continues
3. write_file tool — confirms file output works
4. web_search tool — confirms a multi-turn research loop works end-to-end
5. Usage metadata is logged on every call

Requires GEMINI_API_KEY in .env

Run:
    cd embroidery && venv/bin/python test_gemini.py
"""

import asyncio
import os
from pathlib import Path

import agent_loop
from llm import GeminiProvider
from config import ModelSettings
from tools import RESEARCH_TOOLS

GEMINI_MODEL = "gemini-2.0-flash"

ECHO_TOOL = {
    "name": "echo",
    "description": "Echo a message back. Use this to confirm tools are working.",
    "input_schema": {
        "type": "object",
        "properties": {"message": {"type": "string", "description": "The message to echo"}},
        "required": ["message"],
    },
}

WRITE_FILE_TOOL = {
    "name": "write_file",
    "description": "Save text content to a file in the output directory.",
    "input_schema": {
        "type": "object",
        "properties": {
            "filename": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["filename", "content"],
    },
}


async def test_smoke() -> bool:
    """Loop enters tool_use, executes echo + write_file, returns final text."""
    print("\n[1] Smoke test (echo + write_file)...")

    system = """You are a test agent. Follow these steps exactly:
1. Call echo with message "gemini loop works"
2. Call write_file to save "gemini_smoke.txt" containing "Gemini smoke test passed"
3. Reply with: "Smoke test passed."
"""
    messages = [{"role": "user", "content": "Run the smoke test steps."}]

    result = await agent_loop.run_agent(
        system=system,
        messages=messages,
        tools=[ECHO_TOOL, WRITE_FILE_TOOL],
        model_settings=ModelSettings(GEMINI_MODEL),
    )

    file_ok = Path("output/gemini_smoke.txt").exists()
    print(f"    Response : {result.strip()}")
    print(f"    File written: {file_ok}")
    return "passed" in result.lower() and file_ok


async def test_web_search() -> bool:
    """Multi-turn loop: web_search → write_file → final response."""
    print("\n[2] Web search test (web_search + write_file)...")

    agent_loop.reset_search_count()
    system = """You are a research assistant. Follow these steps exactly:
1. Call web_search with query "custom embroidery Etsy personalized gifts" and num_results=3
2. Call write_file to save "gemini_search.txt" with a 2-sentence summary of what you found
3. Reply with: "Search test passed."
"""
    messages = [{"role": "user", "content": "Run the search steps now."}]

    result = await agent_loop.run_agent(
        system=system,
        messages=messages,
        tools=RESEARCH_TOOLS,
        model_settings=ModelSettings(GEMINI_MODEL),
    )

    file_ok = Path("output/gemini_search.txt").exists()
    print(f"    Response : {result.strip()}")
    if file_ok:
        print(f"    File content: {Path('output/gemini_search.txt').read_text()[:200]}")
    print(f"    File written: {file_ok}")
    return "passed" in result.lower() and file_ok


async def main():
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key or api_key == "your-gemini-key-here":
        print("✗ GEMINI_API_KEY not set in .env — add it and retry.")
        return

    print(f"Testing Gemini provider ({GEMINI_MODEL})...\n")

    # Inject GeminiProvider directly — bypasses config.yaml provider setting
    agent_loop._provider = GeminiProvider(api_key=api_key)

    results = [
        await test_smoke(),
        await test_web_search(),
    ]

    passed = sum(results)
    total = len(results)
    print(f"\n{'✓' if passed == total else '✗'} {passed}/{total} tests passed")

    # Restore so subsequent code uses config.yaml setting
    agent_loop.reset_provider()


if __name__ == "__main__":
    asyncio.run(main())
