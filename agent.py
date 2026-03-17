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
MAX_TOOL_CALLS = 15

# System prompt for the system agent
SYSTEM_PROMPT = """You are a documentation and system assistant with access to three tools:
- list_files: List files in a directory
- read_file: Read contents of a file
- query_api: Query the backend LMS API

To answer questions:

1. For wiki/documentation questions (e.g., "How do I protect a branch?"):
   - Use list_files to find relevant files in wiki/
   - Use read_file to read the contents
   - Cite the source (wiki/filename.md#section)

2. For source code questions (e.g., "What framework does the backend use?"):
   - Use list_files to explore the backend/ directory
   - Use read_file to read the main source code files (backend/app/main.py, backend/app/run.py)
   - Look at imports to identify frameworks
   - IMPORTANT: Read backend/app/main.py to find the framework - it contains the FastAPI app initialization

3. For "list all" questions (e.g., "List all API routers"):
   - Use list_files to find all files in the directory
   - Read EVERY file before answering - do not stop early
   - Summarize what each file handles

4. For data/API questions (e.g., "How many items are in the database?"):
   - Use query_api to fetch real data
   - Example: GET /items/ returns all items

5. For API behavior questions (e.g., "What status code for unauthenticated request?"):
   - Use query_api to test the endpoint
   - Note the status_code in the response

6. For bug diagnosis questions:
   - Use query_api to reproduce the error
   - Use read_file to examine the source code
   - Explain the bug and suggest a fix

Important:
- Use read_file to read actual file contents, not just list_files
- For code questions, read the main files (e.g., backend/app/main.py, backend/app/routers/*.py)
- When list_files returns entries, construct full paths by combining the directory path with the entry name (e.g., if you listed 'backend' and see 'app', use 'backend/app' for the next call)
- For questions asking about "all" or "list" items, make sure to examine ALL relevant files before answering
- For complex questions (e.g., "explain the journey", "trace the path"), read ALL relevant configuration files: docker-compose.yml, caddy/Caddyfile, Dockerfile (in project root), backend/app/main.py
- Note: Dockerfile is in the project root, not in backend/
- Include a source field when referencing wiki or code files (can list multiple sources)
- Stop calling tools once you have found the answer
- Maximum 15 tool calls allowed per question
- If you cannot find the answer, say so and provide the closest relevant information
"""

# Project root directory (parent of agent.py)
PROJECT_ROOT = Path(__file__).parent


def load_config() -> dict:
    """Load LLM and LMS configuration from environment files."""
    # Load LLM config from .env.agent.secret
    env_file = PROJECT_ROOT / ".env.agent.secret"
    if not env_file.exists():
        print(f"Error: Environment file not found: {env_file}", file=sys.stderr)
        sys.exit(1)

    load_dotenv(env_file)

    # Also load LMS_API_KEY from .env.docker.secret
    lms_env_file = PROJECT_ROOT / ".env.docker.secret"
    if lms_env_file.exists():
        load_dotenv(lms_env_file, override=False)

    config = {
        "llm_api_key": os.getenv("LLM_API_KEY"),
        "llm_api_base": os.getenv("LLM_API_BASE"),
        "llm_model": os.getenv("LLM_MODEL"),
        "lms_api_key": os.getenv("LMS_API_KEY"),
        "agent_api_base_url": os.getenv("AGENT_API_BASE_URL", "http://localhost:42002"),
    }

    if not config["llm_api_key"]:
        print("Error: LLM_API_KEY not set in .env.agent.secret", file=sys.stderr)
        sys.exit(1)
    if not config["llm_api_base"]:
        print("Error: LLM_API_BASE not set in .env.agent.secret", file=sys.stderr)
        sys.exit(1)
    if not config["llm_model"]:
        print("Error: LLM_MODEL not set in .env.agent.secret", file=sys.stderr)
        sys.exit(1)
    if not config["lms_api_key"]:
        print("Error: LMS_API_KEY not set in .env.docker.secret", file=sys.stderr)
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
        entries = []
        for entry in dir_path.iterdir():
            entry_type = "dir" if entry.is_dir() else "file"
            entries.append(f"{entry.name} ({entry_type})")
        entries = sorted(entries)
        return {"success": True, "entries": entries}
    except (IOError, OSError) as e:
        return {"success": False, "error": f"Error listing directory: {e}"}


def query_api(method: str, path: str, body: str = None, config: dict = None) -> dict:
    """
    Query the backend LMS API.

    Args:
        method: HTTP method (GET, POST, PUT, DELETE, etc.)
        path: API endpoint path (e.g., '/items/', '/analytics/completion-rate')
        body: Optional JSON request body for POST/PUT requests
        config: Configuration dict with lms_api_key and agent_api_base_url

    Returns:
        dict with 'success' bool and 'data' or 'error' string
    """
    if config is None:
        return {"success": False, "error": "Configuration not provided"}

    base_url = config["agent_api_base_url"].rstrip("/")
    url = f"{base_url}{path}"
    api_key = config["lms_api_key"]

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    try:
        with httpx.Client(timeout=60.0) as client:
            if method.upper() == "GET":
                response = client.get(url, headers=headers)
            elif method.upper() == "POST":
                json_body = json.loads(body) if body else {}
                response = client.post(url, headers=headers, json=json_body)
            elif method.upper() == "PUT":
                json_body = json.loads(body) if body else {}
                response = client.put(url, headers=headers, json=json_body)
            elif method.upper() == "DELETE":
                response = client.delete(url, headers=headers)
            else:
                return {"success": False, "error": f"Unsupported method: {method}"}

            result_data = {
                "status_code": response.status_code,
            }

            try:
                result_data["body"] = response.json()
            except json.JSONDecodeError:
                result_data["body"] = response.text

            return {"success": True, "data": result_data}

    except httpx.TimeoutException:
        return {"success": False, "error": "Request timed out (>60 seconds)"}
    except httpx.ConnectError as e:
        return {"success": False, "error": f"Connection error: {e}"}
    except httpx.HTTPError as e:
        return {"success": False, "error": f"HTTP error: {e}"}
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"Invalid JSON in request body: {e}"}
    except Exception as e:
        return {"success": False, "error": f"Unexpected error: {e}"}


def execute_tool(tool_name: str, args: dict, config: dict = None) -> str:
    """
    Execute a tool and return its result as a string.

    Args:
        tool_name: Name of the tool ('read_file', 'list_files', or 'query_api')
        args: Arguments for the tool
        config: Configuration dict (required for query_api)

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

    elif tool_name == "query_api":
        method = args.get("method", "GET")
        path = args.get("path", "")
        body = args.get("body")
        result = query_api(method, path, body, config)
        if result["success"]:
            return json.dumps(result["data"])
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
        {
            "type": "function",
            "function": {
                "name": "query_api",
                "description": "Query the backend LMS API. Use for questions about data in the database, API behavior, status codes, or analytics.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "method": {
                            "type": "string",
                            "description": "HTTP method (GET, POST, PUT, DELETE)",
                        },
                        "path": {
                            "type": "string",
                            "description": "API endpoint path (e.g., '/items/', '/analytics/completion-rate')",
                        },
                        "body": {
                            "type": "string",
                            "description": "Optional JSON request body for POST/PUT requests",
                        },
                    },
                    "required": ["method", "path"],
                },
            },
        },
    ]


def call_llm(messages: list, config: dict, tools: list = None) -> dict:
    """
    Call the LLM and return the parsed response.

    Args:
        messages: List of message dicts for the conversation
        config: LLM configuration dict (with llm_api_key, llm_api_base, llm_model)
        tools: Optional list of tool definitions

    Returns:
        Parsed response dict with 'content' and/or 'tool_calls'
    """
    url = f"{config['llm_api_base']}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config['llm_api_key']}",
    }

    payload = {
        "model": config["llm_model"],
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
                tool_id = tool_call["id"]
                
                # Parse tool arguments with error handling
                args_str = tool_call["function"].get("arguments", "{}")
                try:
                    tool_args = json.loads(args_str) if args_str else {}
                except json.JSONDecodeError:
                    tool_args = {}

                print(f"Executing tool: {tool_name}({tool_args})", file=sys.stderr)

                result = execute_tool(tool_name, tool_args, config)

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
