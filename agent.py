#!/usr/bin/env python3
"""
Agent CLI - System agent with tool calling capabilities.

This agent answers questions about a software engineering project by using tools
to read files, list directories, and query the backend API.

Usage:
    uv run agent.py "Your question here"

Output:
    JSON to stdout: {"answer": "...", "source": "...", "tool_calls": [...]}
"""

import json
import os
import re
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

# Configuration
MAX_TOOL_CALLS = 15
PROJECT_ROOT = Path(__file__).parent


# ============================================================================
# Configuration Management
# ============================================================================

def load_config():
    """Load configuration from environment files."""
    # Load LLM config from .env.agent.secret
    env_file = PROJECT_ROOT / ".env.agent.secret"
    if not env_file.exists():
        print(f"Error: Environment file not found: {env_file}", file=sys.stderr)
        sys.exit(1)

    load_dotenv(env_file)

    # Load LMS_API_KEY from .env.docker.secret
    lms_env_file = PROJECT_ROOT / ".env.docker.secret"
    if lms_env_file.exists():
        load_dotenv(lms_env_file, override=False)

    config = {
        "llm_api_key": os.getenv("LLM_API_KEY"),
        "llm_api_base": os.getenv("LLM_API_BASE"),
        "llm_model": os.getenv("LLM_MODEL", "qwen3-coder-plus"),
        "lms_api_key": os.getenv("LMS_API_KEY"),
        "agent_api_base_url": os.getenv("AGENT_API_BASE_URL", "http://localhost:42002"),
    }

    # Validate required config
    if not config["llm_api_key"]:
        print("Error: LLM_API_KEY not set", file=sys.stderr)
        sys.exit(1)
    if not config["llm_api_base"]:
        print("Error: LLM_API_BASE not set", file=sys.stderr)
        sys.exit(1)
    if not config["lms_api_key"]:
        print("Error: LMS_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    return config


# ============================================================================
# Tool Implementations
# ============================================================================

def validate_path(path: str) -> Path:
    """Validate that a path is safe and within the project root."""
    if ".." in path or path.startswith("/"):
        raise ValueError(f"Invalid path: {path}")
    full_path = (PROJECT_ROOT / path).resolve()
    if not str(full_path).startswith(str(PROJECT_ROOT.resolve())):
        raise ValueError(f"Path traversal detected: {path}")
    return full_path


def tool_read_file(path: str) -> str:
    """Read the contents of a file."""
    try:
        full_path = validate_path(path)
        if not full_path.exists():
            return f"Error: File not found: {path}"
        if not full_path.is_file():
            return f"Error: Not a file: {path}"
        return full_path.read_text()
    except (ValueError, IOError, OSError) as e:
        return f"Error: {e}"


def tool_list_files(path: str) -> str:
    """List files and directories at a given path."""
    try:
        full_path = validate_path(path)
        if not full_path.exists():
            return f"Error: Path not found: {path}"
        if not full_path.is_dir():
            return f"Error: Not a directory: {path}"

        entries = []
        for entry in sorted(full_path.iterdir()):
            if entry.name.startswith(".") and entry.name not in [".qwen", ".vscode"]:
                continue
            if entry.name in ["__pycache__", ".venv", ".pytest_cache", ".ruff_cache"]:
                continue
            suffix = "/" if entry.is_dir() else ""
            entries.append(f"{entry.name}{suffix}")
        return "\n".join(entries)
    except (ValueError, IOError, OSError) as e:
        return f"Error: {e}"


def tool_query_api(method: str, path: str, body: str = None, use_auth: bool = True) -> str:
    """Query the backend API."""
    config = load_config()
    base_url = config["agent_api_base_url"].rstrip("/")
    url = f"{base_url}{path}"
    api_key = config["lms_api_key"]

    headers = {"Content-Type": "application/json"}
    if use_auth and api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    print(f"Querying API: {method} {url}", file=sys.stderr)

    try:
        with httpx.Client(timeout=30.0) as client:
            method = method.upper()
            if method == "GET":
                response = client.get(url, headers=headers)
            elif method == "POST":
                response = client.post(url, headers=headers, data=body or "{}")
            elif method == "PUT":
                response = client.put(url, headers=headers, data=body or "{}")
            elif method == "DELETE":
                response = client.delete(url, headers=headers)
            else:
                return json.dumps({"error": f"Unsupported method: {method}"})

        result = {"status_code": response.status_code}
        try:
            result["body"] = response.json()
        except (json.JSONDecodeError, ValueError):
            result["body"] = response.text

        print(f"API response: {response.status_code}", file=sys.stderr)
        return json.dumps(result)

    except httpx.HTTPStatusError as e:
        return json.dumps({"status_code": e.response.status_code, "error": str(e)})
    except httpx.RequestError as e:
        return json.dumps({"status_code": 0, "error": f"Request failed: {e}"})
    except Exception as e:
        return json.dumps({"status_code": 0, "error": f"Error: {e}"})


# Tool registry
TOOLS_REGISTRY = {
    "read_file": {"func": tool_read_file, "required_args": ["path"]},
    "list_files": {"func": tool_list_files, "required_args": ["path"]},
    "query_api": {"func": tool_query_api, "required_args": ["method", "path"]},
}


def execute_tool(tool_name: str, args: dict) -> str:
    """Execute a tool and return the result."""
    print(f"Executing tool: {tool_name} with args: {args}", file=sys.stderr)

    if tool_name not in TOOLS_REGISTRY:
        return f"Error: Unknown tool: {tool_name}"

    tool_info = TOOLS_REGISTRY[tool_name]
    func = tool_info["func"]

    try:
        return func(**args)
    except TypeError as e:
        return f"Error: Invalid arguments for {tool_name}: {e}"
    except Exception as e:
        return f"Error executing {tool_name}: {e}"


# ============================================================================
# LLM Client
# ============================================================================

class LLMClient:
    """Client for OpenAI-compatible LLM APIs with tool calling support."""

    def __init__(self, config: dict):
        self.api_key = config["llm_api_key"]
        self.api_base = config["llm_api_base"].rstrip("/")
        self.model = config["llm_model"]

    def chat_completion(self, messages: list, tools: list = None) -> dict:
        """Send a chat completion request with optional tool calling."""
        url = f"{self.api_base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {"model": self.model, "messages": messages}
        if tools:
            payload["tools"] = tools

        print(f"Sending request to {url} (model: {self.model})", file=sys.stderr)

        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()

            data = response.json()
            choice = data["choices"][0]["message"]

            result = {"content": choice.get("content", ""), "tool_calls": []}

            if "tool_calls" in choice and choice["tool_calls"]:
                for tc in choice["tool_calls"]:
                    if tc.get("type") == "function":
                        func = tc.get("function", {})
                        try:
                            arguments = json.loads(func.get("arguments", "{}"))
                        except json.JSONDecodeError:
                            arguments = {}

                        result["tool_calls"].append({
                            "id": tc.get("id", ""),
                            "name": func.get("name", ""),
                            "arguments": arguments,
                        })

            print(f"LLM response: {len(result['content'])} chars, {len(result['tool_calls'])} tool calls", file=sys.stderr)
            return result

        except httpx.HTTPStatusError as e:
            print(f"HTTP error from LLM: {e.response.status_code}", file=sys.stderr)
            raise
        except httpx.RequestError as e:
            print(f"Request failed: {e}", file=sys.stderr)
            raise


# ============================================================================
# Agent
# ============================================================================

class Agent:
    """Agent with tool calling capabilities."""

    def __init__(self, config: dict):
        self.config = config
        self.llm_client = LLMClient(config)
        self.tool_call_count = 0
        self.system_prompt = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        """Build the system prompt with instructions for tool usage."""
        return """You are a documentation and system agent for a software engineering project.

You have three tools:
- list_files: List files/directories at a path
- read_file: Read contents of a file
- query_api: Query the backend API (for data queries or checking system behavior)

Guidelines:

1. Wiki questions ("How do I...", "What steps..."):
   - Use list_files to find wiki files
   - Use read_file to read them
   - Cite sources like "wiki/git.md#section"

2. System questions ("What framework...", "What port..."):
   - Use read_file to check source code (backend/, docker-compose.yml, etc.)
   - Or use query_api to test actual behavior
   - Cite sources like "backend/app/main.py"

3. Data queries ("How many items...", "What score..."):
   - Use query_api with appropriate endpoints
   - Common: /items/, /analytics/...

4. Bug diagnosis ("What error...", "What bug..."):
   - FIRST use query_api to reproduce the error
   - THEN use read_file to find the buggy code
   - Explain the root cause and file path

5. "List all" questions:
   - Use list_files to find all files
   - Read EVERY file before answering - do not stop early
   - Summarize what each one does

Important:
- Mention file paths in your answers
- For API queries, mention the endpoint
- If you can't find the answer, say so honestly
"""

    def get_tool_definitions(self) -> list:
        """Get tool definitions for LLM function calling."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read contents of a file in the project repository.",
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
                    "description": "List files and directories at a path.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Relative directory path (e.g., 'wiki')",
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
                    "description": "Query the backend API for data or to check behavior.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "method": {"type": "string", "description": "HTTP method (GET, POST, etc.)"},
                            "path": {"type": "string", "description": "API endpoint (e.g., '/items/')"},
                            "body": {"type": "string", "description": "JSON request body (optional)"},
                            "use_auth": {"type": "boolean", "description": "Use auth header (default: true)"},
                        },
                        "required": ["method", "path"],
                    },
                },
            },
        ]

    def ask(self, question: str) -> dict:
        """Ask a question using the agentic loop."""
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": question},
        ]

        all_tool_calls = []
        tool_definitions = self.get_tool_definitions()

        print(f"Starting agentic loop for: {question}", file=sys.stderr)

        while self.tool_call_count < MAX_TOOL_CALLS:
            print(f"\n--- Iteration {self.tool_call_count + 1} ---", file=sys.stderr)

            # Get LLM response
            response = self.llm_client.chat_completion(messages, tools=tool_definitions)

            # No tool calls = final answer
            if not response["tool_calls"]:
                print("No tool calls, extracting final answer", file=sys.stderr)
                answer = response["content"].strip()
                source = self._extract_source(answer)

                return {
                    "answer": answer,
                    "source": source,
                    "tool_calls": all_tool_calls,
                }

            # Process tool calls
            for tool_call in response["tool_calls"]:
                print(f"Processing: {tool_call['name']}", file=sys.stderr)

                # Execute tool
                result = execute_tool(tool_call["name"], tool_call["arguments"])

                # Record tool call
                all_tool_calls.append({
                    "tool": tool_call["name"],
                    "args": tool_call["arguments"],
                    "result": result,
                })
                self.tool_call_count += 1

                # Add messages to history
                messages.append({
                    "role": "assistant",
                    "tool_calls": [{
                        "id": tool_call["id"],
                        "type": "function",
                        "function": {
                            "name": tool_call["name"],
                            "arguments": json.dumps(tool_call["arguments"]),
                        },
                    }],
                })

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": result,
                })

                print(f"Tool result: {result[:100]}...", file=sys.stderr)

            # Continue loop

        # Max tool calls reached
        print("Max tool calls reached", file=sys.stderr)
        return {
            "answer": "I reached the maximum number of tool calls (15) before finding a complete answer.",
            "source": "",
            "tool_calls": all_tool_calls,
        }

    def _extract_source(self, answer: str) -> str:
        """Extract source reference from the answer text."""
        # Wiki file with anchor
        match = re.search(r"wiki/[\w-]+\.md(?:#[\w-]+)?", answer)
        if match:
            return match.group()

        # Backend Python file
        match = re.search(r"backend/[\w/.-]+\.py", answer)
        if match:
            return match.group()

        # Any Python file
        match = re.search(r"[\w]+/[\w/.-]+\.py", answer)
        if match:
            return match.group()

        # Config files
        match = re.search(r"(?:docker-compose\.yml|Dockerfile|Caddyfile)", answer, re.IGNORECASE)
        if match:
            return match.group()

        return ""


# ============================================================================
# Main Entry Point
# ============================================================================

def main() -> int:
    """Main entry point."""
    if len(sys.argv) != 2:
        print('Usage: uv run agent.py "<question>"', file=sys.stderr)
        return 1

    question = sys.argv[1]

    # Load configuration
    config = load_config()
    print("Configuration loaded", file=sys.stderr)

    # Create agent and get answer
    try:
        agent = Agent(config)
        result = agent.ask(question)
    except httpx.HTTPStatusError as e:
        print(f"HTTP error from LLM API: {e.response.status_code}", file=sys.stderr)
        print(f"Response: {e.response.text}", file=sys.stderr)
        return 1
    except httpx.RequestError as e:
        print(f"Request failed: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1

    # Output JSON
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
