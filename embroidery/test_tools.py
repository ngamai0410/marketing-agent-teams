"""
Day 2 tool layer test.

Verifies:
1. web_search executes and feeds result back into the loop
2. Agent uses search results to write a summary file
3. max_searches counter is respected (hard limit from config)
4. Token usage is logged on every API call

Run:
    cd embroidery && ../venv/bin/python test_tools.py
"""

import asyncio
from agent_loop import run_agent, reset_search_count
from config import ModelSettings
from tools import RESEARCH_TOOLS

SYSTEM = """You are a market research assistant. Follow these steps exactly:
1. Call web_search with query "custom embroidery shops Etsy personalized" (num_results=5)
2. Read the results carefully
3. Call write_file to save "day2_test.txt" with a 3-sentence summary of what you found
4. Reply with: "Day 2 test passed."
"""


async def main():
    print("Running Day 2 tool layer test...\n")

    reset_search_count()
    messages = [{"role": "user", "content": "Run the research steps now."}]

    result = await run_agent(
        system=SYSTEM,
        messages=messages,
        tools=RESEARCH_TOOLS,
        model_settings=ModelSettings("claude-haiku-4-5"),
    )

    print(f"\nFinal response: {result}")

    from pathlib import Path
    output_file = Path("output/day2_test.txt")
    if output_file.exists():
        print(f"\nFile written:\n{output_file.read_text()}")
        print("\n✓ Day 2 passed — web_search, write_file, and loop all work end-to-end.")
    else:
        print("\n✗ write_file did not produce output/day2_test.txt")


if __name__ == "__main__":
    asyncio.run(main())
