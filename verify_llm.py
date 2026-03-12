#!/usr/bin/env python3
"""Verify LLM connection and tool calling support.

Run this script to check that your LLM provider is configured correctly
and supports tool calling (function calling) before starting the agent tasks.

Usage:
    uv run verify_llm.py
"""

import json
import os
import sys
from pathlib import Path

def _load_env():
    """Load environment variables from .env.agent.secret."""
    env_path = Path(__file__).resolve().parent / ".env.agent.secret"
    if not env_path.exists():
        print("✗ .env.agent.secret not found", file=sys.stderr)
        print("  Run: cp .env.agent.example .env.agent.secret", file=sys.stderr)
        print("  Then fill in your LLM credentials.", file=sys.stderr)
        sys.exit(1)
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


def _check_env():
    """Check required environment variables are set."""
    missing = []
    for var in ("LLM_API_KEY", "LLM_API_BASE", "LLM_MODEL"):
        if not os.environ.get(var):
            missing.append(var)
    if missing:
        print(f"✗ Missing environment variables: {', '.join(missing)}", file=sys.stderr)
        print("  Edit .env.agent.secret and set these values.", file=sys.stderr)
        sys.exit(1)


def _test_connection():
    """Test basic LLM connection with a simple prompt."""
    import httpx

    api_base = os.environ["LLM_API_BASE"].rstrip("/")
    response = httpx.post(
        f"{api_base}/chat/completions",
        headers={
            "Authorization": f"Bearer {os.environ['LLM_API_KEY']}",
            "Content-Type": "application/json",
        },
        json={
            "model": os.environ["LLM_MODEL"],
            "messages": [{"role": "user", "content": "Say 'hello' and nothing else."}],
            "max_tokens": 10,
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    content = data["choices"][0]["message"].get("content", "")
    if not content:
        raise ValueError("LLM returned empty content")
    return content


def _test_tool_calling():
    """Test that the LLM supports tool calling."""
    import httpx

    api_base = os.environ["LLM_API_BASE"].rstrip("/")
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get the current weather for a location.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "City name",
                        }
                    },
                    "required": ["location"],
                },
            },
        }
    ]
    response = httpx.post(
        f"{api_base}/chat/completions",
        headers={
            "Authorization": f"Bearer {os.environ['LLM_API_KEY']}",
            "Content-Type": "application/json",
        },
        json={
            "model": os.environ["LLM_MODEL"],
            "messages": [
                {"role": "user", "content": "What is the weather in Paris?"}
            ],
            "tools": tools,
            "max_tokens": 100,
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    message = data["choices"][0]["message"]
    tool_calls = message.get("tool_calls", [])
    if not tool_calls:
        raise ValueError(
            "LLM did not return tool_calls. "
            "This model may not support tool calling. "
            "Try a different model (see recommended models in the setup guide)."
        )
    call = tool_calls[0]
    if call["function"]["name"] != "get_weather":
        raise ValueError(f"Expected get_weather call, got {call['function']['name']}")
    return call


def main():
    _load_env()
    _check_env()

    model = os.environ["LLM_MODEL"]
    api_base = os.environ["LLM_API_BASE"]
    print(f"  Model: {model}", file=sys.stderr)
    print(f"  API:   {api_base}", file=sys.stderr)
    print(file=sys.stderr)

    # Test 1: Basic connection
    try:
        _test_connection()
        print("✓ LLM connection works")
    except Exception as e:
        print(f"✗ LLM connection failed: {e}", file=sys.stderr)
        sys.exit(1)

    # Test 2: Tool calling
    try:
        _test_tool_calling()
        print("✓ Tool calling works")
    except Exception as e:
        print(f"✗ Tool calling failed: {e}", file=sys.stderr)
        sys.exit(1)

    print()
    print("Your LLM is ready. You can start building the agent.")


if __name__ == "__main__":
    main()
