# Agent Documentation

## Overview

This agent is a Python CLI that connects to an LLM (Large Language Model) with **tools** and an **agentic loop**. It can navigate the project wiki, read files, and provide answers with source references.

## Architecture

```
User (CLI) → agent.py → Agentic Loop → Qwen Code API (VM) → Qwen 3 Coder (Cloud)
                ↓
         Tools: read_file, list_files
                ↓
         Project Wiki Files
```

### Components

1. **agent.py** — Main CLI script that:
   - Parses command-line arguments
   - Loads LLM configuration from `.env.agent.secret`
   - Runs an agentic loop with tool execution
   - Returns structured JSON output with answer, source, and tool calls

2. **Tools** — Functions the agent can call:
   - `read_file`: Read contents of a file
   - `list_files`: List files in a directory

3. **Agentic Loop** — Multi-turn conversation:
   - Sends question + tool definitions to LLM
   - Executes tool calls returned by LLM
   - Feeds results back to LLM
   - Repeats until LLM provides final answer

4. **Qwen Code API** — OpenAI-compatible API proxy on the VM

5. **Qwen 3 Coder** — The LLM model in the cloud

## LLM Provider

**Provider:** Qwen Code API

**Model:** `qwen3-coder-plus`

**Endpoint:** `http://79.137.184.118:42005/v1`

## Configuration

Create `.env.agent.secret` in the project root:

```bash
cp .env.agent.example .env.agent.secret
```

Required environment variables:

| Variable | Description | Example |
|----------|-------------|---------|
| `LLM_API_KEY` | API key for Qwen Code API | `my-secret-qwen-key` |
| `LLM_API_BASE` | Base URL of the LLM API | `http://79.137.184.118:42005/v1` |
| `LLM_MODEL` | Model name to use | `qwen3-coder-plus` |

> **Note:** `.env.agent.secret` is gitignored. Never commit secrets.

## Tools

The agent has two tools that allow it to interact with the project file system.

### `read_file`

Read the contents of a file at the specified path.

**Parameters:**

- `path` (string, required): Relative path from project root

**Example:**

```json
{"tool": "read_file", "args": {"path": "wiki/git.md"}}
```

**Returns:** File contents as a string, or an error message.

**Security:**

- Rejects paths containing `..` (directory traversal)
- Rejects absolute paths
- Only allows files within the project root

### `list_files`

List files and directories at the specified path.

**Parameters:**

- `path` (string, required): Relative directory path from project root

**Example:**

```json
{"tool": "list_files", "args": {"path": "wiki"}}
```

**Returns:** Newline-separated list of file/directory names.

**Security:**

- Same path validation as `read_file`
- Only lists directories within the project root

## Agentic Loop

The agentic loop enables multi-turn reasoning with tool execution:

### Flow

1. **Initial Request:** Send user question + system prompt + tool definitions to LLM
2. **Parse Response:** Check if LLM returned `tool_calls` or a text answer
3. **If tool_calls:**
   - Execute each tool locally
   - Append results as `tool` role messages
   - Send back to LLM for next iteration
4. **If text answer:**
   - Extract answer and source
   - Output JSON and exit
5. **Termination:**
   - LLM returns answer without tool calls → success
   - 10 tool calls reached → stop and return best answer

### Message History Format

```python
messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": "How do you resolve a merge conflict?"},
    # After tool calls:
    {"role": "assistant", "content": None, "tool_calls": [...]},
    {"role": "tool", "content": "file contents...", "tool_call_id": "..."},
    # Continue until final answer...
]
```

### System Prompt

The system prompt instructs the LLM to:

1. Use `list_files` to discover relevant wiki files
2. Use `read_file` to read contents and find answers
3. Always include a `source` reference (file path + section anchor)
4. Stop calling tools once the answer is found
5. Maximum 10 tool calls allowed

## Usage

### Basic Usage

```bash
uv run agent.py "How do you resolve a merge conflict?"
```

### Output

The agent outputs a single JSON line to stdout:

```json
{
  "answer": "To resolve a merge conflict, open the conflicting file in VS Code, look for conflict markers (<<<<<<<, =======, >>>>>>>), choose which changes to keep, delete the markers, then stage and commit the file.",
  "source": "wiki/git-vscode.md#resolve-a-merge-conflict",
  "tool_calls": [
    {
      "tool": "list_files",
      "args": {"path": "wiki"},
      "result": "git.md\ngit-vscode.md\ngit-workflow.md\n..."
    },
    {
      "tool": "read_file",
      "args": {"path": "wiki/git-vscode.md"},
      "result": "# Git in VS Code\n\n## Resolve a Merge Conflict\n..."
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `answer` | string | The LLM's response to the question |
| `source` | string | Wiki file path with section anchor (e.g., `wiki/git.md#merge-conflict`) |
| `tool_calls` | array | List of all tool calls made during the agentic loop |

### Tool Call Entry

Each entry in `tool_calls` contains:

| Field | Type | Description |
|-------|------|-------------|
| `tool` | string | Name of the tool used |
| `args` | object | Arguments passed to the tool |
| `result` | string | Result returned by the tool |

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success — JSON output printed |
| 1 | Error — missing argument, config, or API failure |

### Debug Output

All debug and progress messages are written to stderr:

```bash
$ uv run agent.py "What is REST?"
Starting agentic loop for question: What is REST?
Calling LLM (iteration 1)...
Executing tool: list_files({'path': 'wiki'})
Calling LLM (iteration 2)...
Executing tool: read_file({'path': 'wiki/rest-api.md'})
LLM returned final answer
{"answer": "...", "source": "wiki/rest-api.md", "tool_calls": [...]}
```

## Error Handling

The agent handles the following error cases:

| Error | Behavior |
|-------|----------|
| Missing CLI argument | Print usage to stderr, exit 1 |
| Missing `.env.agent.secret` | Print error to stderr, exit 1 |
| Missing environment variables | Print error to stderr, exit 1 |
| HTTP request timeout (>60s) | Print error to stderr, exit 1 |
| HTTP request failure | Print error to stderr, exit 1 |
| Invalid JSON response | Print error to stderr, exit 1 |
| Path traversal attempt | Return error message, continue loop |
| File not found | Return error message, continue loop |

## Testing

Run all tests:

```bash
uv run pytest tests/test_agent.py -v
```

Tests verify:

1. Basic LLM call returns valid JSON with `answer` and `tool_calls`
2. Documentation questions trigger `read_file` tool usage
3. Directory listing questions trigger `list_files` tool usage
4. `source` field is populated with wiki path

## File Structure

```
se-toolkit-lab-6/
├── agent.py              # Main CLI script with agentic loop
├── AGENT.md              # This documentation
├── .env.agent.secret     # LLM configuration (gitignored)
├── .env.agent.example    # Example configuration
├── plans/
│   ├── task-1.md         # Task 1 implementation plan
│   └── task-2.md         # Task 2 implementation plan
├── wiki/                 # Project documentation (agent's knowledge base)
│   ├── git.md
│   ├── git-vscode.md
│   └── ...
└── tests/
    └── test_agent.py     # Regression tests
```

## Extending the Agent

### Task 3: Additional Tools

In Task 3, the agent will be extended with:

- `query_api`: Query the backend LMS API
- `search_wiki`: Search for keywords in wiki files
- Domain-specific tools for the LMS domain

## Troubleshooting

### "Environment file not found"

Ensure `.env.agent.secret` exists in the project root:

```bash
ls -la .env.agent.secret
```

### "LLM_API_KEY not set"

Check that `.env.agent.secret` contains valid values:

```bash
cat .env.agent.secret | grep LLM_API_KEY
```

### "HTTP request failed"

Verify the Qwen Code API is running on your VM:

```bash
ssh root@79.137.184.118 "cd ~/qwen-code-oai-proxy && docker compose ps"
```

### "Invalid path" errors from tools

The agent enforces path security:

- Paths must be relative (no `/` at start)
- No directory traversal (`..` not allowed)
- Files must exist within the project root

### Agent doesn't find the answer

The agent can only access files in the project repository. If the wiki doesn't contain the answer, the agent will report that it couldn't find the information.
