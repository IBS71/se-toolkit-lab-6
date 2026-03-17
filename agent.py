#!/usr/bin/env python3
"""
Agent CLI — Call an LLM with tools and return a structured JSON answer.

Usage:
    uv run agent.py "Your question here"

Output:
    JSON line to stdout: {"answer": "...", "source": "...", "tool_calls": [...]}
    All debug output goes to stderr.
"""

import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

# Maximum number of tool calls allowed per question
MAX_TOOL_CALLS = 10

# System prompt for the documentation agent
SYSTEM_PROMPT = """You are a documentation assistant with access to two tools:
- list_files: List files and directories at a given path
- read_file: Read the contents of a file

To answer questions about the project:
1. Use list_files to discover relevant files in the wiki/ directory
2. Use read_file to read the contents of relevant files
3. Find the specific section that answers the question
4. Provide your answer with a source reference in the format: wiki/filename.md#section-anchor

Rules:
- Always include a source field pointing to the relevant wiki section
- Use section anchors that match the heading text (lowercase, hyphens instead of spaces)
- Stop calling tools once you have found the answer
- Maximum 10 tool calls allowed per question
- If you cannot find the answer, say so and provide the closest relevant information
"""

# Project root directory (parent of agent.py)
PROJECT_ROOT = Path(__file__).parent


def load_config() -> dict:
    """Load LLM configuration from .env.agent.secret."""
    env_file = PROJECT_ROOT / ".env.agent.secret"
    if not env_file.exists():
        print(f"Error: Environment file not found: {env_file}", file=sys.stderr)
        sys.exit(1)

    load_dotenv(env_file)

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


def validate_path(path: str) -> bool:
    """
    Validate that a path is safe and within the project root.

    Security checks:
    - No directory traversal (..)
    - No absolute paths
    - Must resolve to within PROJECT_ROOT
    """
    # Reject paths with ..
    if ".." in path:
        return False
    # Reject absolute paths
    if path.startswith("/"):
        return False
    # Reject paths with null bytes or other dangerous characters
    if "\x00" in path:
        return False

    # Resolve and check it's within project root
    try:
        full_path = (PROJECT_ROOT / path).resolve()
        return str(full_path).startswith(str(PROJECT_ROOT.resolve()))
    except (ValueError, OSError):
        return False


def read_file(path: str) -> dict:
    """
    Read the contents of a file at the specified path.

    Args:
        path: Relative path from project root (e.g., 'wiki/git.md')

    Returns:
        dict with 'success' bool and 'content' or 'error' string
    """
    if not validate_path(path):
        return {"success": False, "error": f"Invalid path: {path}"}

    file_path = PROJECT_ROOT / path

    if not file_path.exists():
        return {"success": False, "error": f"File not found: {path}"}

    if not file_path.is_file():
        return {"success": False, "error": f"Not a file: {path}"}

    try:
        content = file_path.read_text()
        return {"success": True, "content": content}
    except (IOError, OSError) as e:
        return {"success": False, "error": f"Error reading file: {e}"}


def list_files(path: str) -> dict:
    """
    List files and directories at the specified path.

    Args:
        path: Relative directory path from project root (e.g., 'wiki')

    Returns:
        dict with 'success' bool and 'entries' list or 'error' string
    """
    if not validate_path(path):
        return {"success": False, "error": f"Invalid path: {path}"}

    dir_path = PROJECT_ROOT / path

    if not dir_path.exists():
        return {"success": False, "error": f"Directory not found: {path}"}

    if not dir_path.is_dir():
        return {"success": False, "error": f"Not a directory: {path}"}

    try:
        entries = sorted([entry.name for entry in dir_path.iterdir()])
        return {"success": True, "entries": entries}
    except (IOError, OSError) as e:
        return {"success": False, "error": f"Error listing directory: {e}"}


def execute_tool(tool_name: str, args: dict) -> str:
    """
    Execute a tool and return its result as a string.

    Args:
        tool_name: Name of the tool ('read_file' or 'list_files')
        args: Arguments for the tool

    Returns:
        String representation of the tool result
    """
    if tool_name == "read_file":
        path = args.get("path", "")
        result = read_file(path)
        if result["success"]:
            return result["content"]
        return f"Error: {result['error']}"

    elif tool_name == "list_files":
        path = args.get("path", "")
        result = list_files(path)
        if result["success"]:
            return "\n".join(result["entries"])
        return f"Error: {result['error']}"

    else:
        return f"Error: Unknown tool: {tool_name}"


def get_tool_definitions() -> list:
    """Return the tool definitions for the LLM function calling schema."""
    return [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read the contents of a file at the specified path",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative path from project root (e.g., 'wiki/git.md')",
                        }
                    },
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_files",
                "description": "List files and directories at the specified path",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative directory path from project root (e.g., 'wiki')",
                        }
                    },
                    "required": ["path"],
                },
            },
        },
    ]


def call_llm(messages: list, config: dict, tools: list = None) -> dict:
    """
    Call the LLM and return the parsed response.

    Args:
        messages: List of message dicts for the conversation
        config: LLM configuration dict
        tools: Optional list of tool definitions

    Returns:
        Parsed response dict with 'content' and/or 'tool_calls'
    """
    url = f"{config['api_base']}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config['api_key']}",
    }

    payload = {
        "model": config["model"],
        "messages": messages,
    }

    if tools:
        payload["tools"] = tools

    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

            choice = data["choices"][0]["message"]
            result = {
                "content": choice.get("content"),
                "tool_calls": choice.get("tool_calls"),
            }
            return result

    except httpx.TimeoutException:
        print("Error: LLM request timed out (>60 seconds)", file=sys.stderr)
        sys.exit(1)
    except httpx.HTTPError as e:
        print(f"Error: HTTP request failed: {e}", file=sys.stderr)
        sys.exit(1)
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        print(f"Error: Failed to parse LLM response: {e}", file=sys.stderr)
        sys.exit(1)


def run_agentic_loop(question: str, config: dict) -> dict:
    """
    Run the agentic loop to answer the question using tools.

    Args:
        question: User's question
        config: LLM configuration

    Returns:
        dict with 'answer', 'source', and 'tool_calls' fields
    """
    # Initialize conversation
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    tools = get_tool_definitions()
    all_tool_calls = []
    tool_call_count = 0

    print(f"Starting agentic loop for question: {question}", file=sys.stderr)

    while tool_call_count < MAX_TOOL_CALLS:
        print(f"Calling LLM (iteration {tool_call_count + 1})...", file=sys.stderr)

        response = call_llm(messages, config, tools)

        # Check if LLM returned tool calls
        if response["tool_calls"]:
            tool_calls = response["tool_calls"]

            # Add assistant message with tool calls to history
            messages.append(
                {
                    "role": "assistant",
                    "content": response["content"],
                    "tool_calls": tool_calls,
                }
            )

            # Execute each tool call
            for tool_call in tool_calls:
                tool_name = tool_call["function"]["name"]
                tool_args = json.loads(tool_call["function"]["arguments"])
                tool_id = tool_call["id"]

                print(f"Executing tool: {tool_name}({tool_args})", file=sys.stderr)

                result = execute_tool(tool_name, tool_args)

                # Record the tool call for output
                all_tool_calls.append(
                    {
                        "tool": tool_name,
                        "args": tool_args,
                        "result": result,
                    }
                )

                # Add tool result to messages
                messages.append(
                    {
                        "role": "tool",
                        "content": result,
                        "tool_call_id": tool_id,
                    }
                )

                tool_call_count += 1

                if tool_call_count >= MAX_TOOL_CALLS:
                    print(
                        f"Reached maximum tool calls ({MAX_TOOL_CALLS})", file=sys.stderr
                    )
                    break

            if tool_call_count >= MAX_TOOL_CALLS:
                break
        else:
            # LLM returned a final answer
            print(f"LLM returned final answer", file=sys.stderr)

            answer = response["content"] or ""
            source = extract_source(answer, all_tool_calls)

            return {
                "answer": answer,
                "source": source,
                "tool_calls": all_tool_calls,
            }

    # Reached max tool calls without final answer
    print("Ending loop: max tool calls reached", file=sys.stderr)

    # Try to extract an answer from the last response
    answer = response.get("content") or "Unable to provide a complete answer."
    source = extract_source(answer, all_tool_calls)

    return {
        "answer": answer,
        "source": source,
        "tool_calls": all_tool_calls,
    }


def extract_source(answer: str, tool_calls: list) -> str:
    """
    Extract or generate a source reference from the tool calls.

    Looks for the last read_file call and uses its path.
    """
    # Find the last read_file call
    for tool_call in reversed(tool_calls):
        if tool_call["tool"] == "read_file":
            path = tool_call["args"].get("path", "")
            if path:
                # Try to extract a section from the answer
                section = extract_section_anchor(answer)
                if section:
                    return f"{path}#{section}"
                return path

    return ""


def extract_section_anchor(text: str) -> str:
    """
    Try to extract a section anchor from the answer text.

    Looks for patterns like '## Section Name' or references to sections.
    """
    # Look for markdown headers in the text
    import re

    # Pattern for markdown headers
    header_pattern = r"##\s+([A-Za-z0-9\s\-]+)"
    matches = re.findall(header_pattern, text)

    if matches:
        # Convert header to anchor format
        header = matches[0].strip()
        return header.lower().replace(" ", "-")

    return ""


def main() -> None:
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: uv run agent.py \"<question>\"", file=sys.stderr)
        sys.exit(1)

    question = sys.argv[1]

    config = load_config()
    result = run_agentic_loop(question, config)

    print(json.dumps(result))


if __name__ == "__main__":
    main()
