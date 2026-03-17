#!/usr/bin/env python3
"""
Agent CLI — Call an LLM and return a structured JSON answer.

Usage:
    uv run agent.py "Your question here"

Output:
    JSON line to stdout: {"answer": "...", "tool_calls": []}
    All debug output goes to stderr.
"""

import json
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv


def load_config() -> dict:
    """Load LLM configuration from .env.agent.secret."""
    env_file = Path(__file__).parent / ".env.agent.secret"
    if not env_file.exists():
        print(f"Error: Environment file not found: {env_file}", file=sys.stderr)
        sys.exit(1)

    load_dotenv(env_file)

    import os

    config = {
        "api_key": os.getenv("LLM_API_KEY"),
        "api_base": os.getenv("LLM_API_BASE"),
        "model": os.getenv("LLM_MODEL"),
    }

    if not config["api_key"]:
        print("Error: LLM_API_KEY not set in .env.agent.secret", file=sys.stderr)
        sys.exit(1)
    if not config["api_base"]:
        print("Error: LLM_API_BASE not set in .env.agent.secret", file=sys.stderr)
        sys.exit(1)
    if not config["model"]:
        print("Error: LLM_MODEL not set in .env.agent.secret", file=sys.stderr)
        sys.exit(1)

    return config


def call_lllm(question: str, config: dict) -> str:
    """Call the LLM and return the answer content."""
    url = f"{config['api_base']}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config['api_key']}",
    }
    payload = {
        "model": config["model"],
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": question},
        ],
    }

    print(f"Calling LLM at {url}...", file=sys.stderr)

    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

            answer = data["choices"][0]["message"]["content"]
            print(f"LLM response received.", file=sys.stderr)
            return answer

    except httpx.TimeoutException:
        print("Error: LLM request timed out (>60 seconds)", file=sys.stderr)
        sys.exit(1)
    except httpx.HTTPError as e:
        print(f"Error: HTTP request failed: {e}", file=sys.stderr)
        sys.exit(1)
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        print(f"Error: Failed to parse LLM response: {e}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: uv run agent.py \"<question>\"", file=sys.stderr)
        sys.exit(1)

    question = sys.argv[1]

    config = load_config()
    answer = call_lllm(question, config)

    result = {
        "answer": answer,
        "tool_calls": [],
    }

    print(json.dumps(result))


if __name__ == "__main__":
    main()
