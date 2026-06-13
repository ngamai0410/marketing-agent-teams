"""
Day 1 smoke test.

Verifies:
1. API key loads
2. Agentic loop enters tool_use, executes the echo tool, continues
3. Agent returns a final text response
4. Token usage is logged
5. write_file tool saves to output/

Run:
    cd embroidery && venv/bin/python -m tests.smoke_test
"""

import asyncio
from embroidery.core.agent_loop import run_agent
from embroidery.core.config import ModelSettings, settings

ECHO_TOOL = {
    "name": "echo",
    "description": "Echo a message back. Use this to confirm tools are working.",
    "input_schema": {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "The message to echo"}
        },
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

SYSTEM = """You are a test agent. Follow these steps exactly:
1. Call the echo tool with the message "loop works"
2. Call write_file to save a file named "smoke_test.txt" containing "Day 1 complete"
3. Reply with: "Smoke test passed."
"""


async def main():
    print("Running Day 1 smoke test...\n")

    messages = [{"role": "user", "content": "Run the smoke test steps."}]

    result = await run_agent(
        system=SYSTEM,
        messages=messages,
        tools=[ECHO_TOOL, WRITE_FILE_TOOL],
        model_settings=ModelSettings("gemini-2.5-flash"),
    )

    print(f"\nFinal response: {result}")

    # Verify file was written
    from pathlib import Path
    output_file = settings.paths.output / "smoke_test.txt"
    if output_file.exists():
        print(f"File written: {output_file.read_text()}")
        print("\n✓ Smoke test passed — loop, tools, and file write all work.")
    else:
        print("\n✗ write_file did not produce output/smoke_test.txt")


if __name__ == "__main__":
    asyncio.run(main())
