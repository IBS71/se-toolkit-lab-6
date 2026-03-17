# Agent Documentation

## Overview

This agent is a Python CLI that connects to an LLM (Large Language Model) with **tools** and an **agentic loop**. It can navigate the project wiki, read source code files, query the backend API, and provide answers with source references.

## Architecture

```
User (CLI) → agent.py → Agentic Loop → Qwen Code API (VM) → Qwen 3 Coder (Cloud)
                ↓
         Tools: read_file, list_files, query_api
                ↓
         Project Files + Backend API
```

### Components

1. **agent.py** — Main CLI script that:
   - Parses command-line arguments
   - Loads LLM configuration from `.env.agent.secret`
   - Loads LMS API key from `.env.docker.secret`
   - Runs an agentic loop with tool execution
   - Returns structured JSON output with answer, source, and tool calls

2. **Tools** — Functions the agent can call:
   - `read_file`: Read contents of a file
   - `list_files`: List files in a directory (with file/dir type indicators)
   - `query_api`: Query the backend LMS API with authentication

3. **Agentic Loop** — Multi-turn conversation:
   - Sends question + system prompt + tool definitions to LLM
   - Executes tool calls returned by LLM
   - Feeds results back to LLM as `tool` role messages
   - Repeats until LLM provides final answer or max 10 calls reached

4. **Qwen Code API** — OpenAI-compatible API proxy on the VM

5. **Qwen 3 Coder** — The LLM model in the cloud

6. **Backend LMS API** — FastAPI application running on the VM

## LLM Provider

**Provider:** Qwen Code API

**Model:** `qwen3-coder-plus`

**Endpoint:** `http://79.137.184.118:42005/v1`

## Configuration

The agent reads configuration from two environment files:

### `.env.agent.secret` (LLM configuration)

```bash
LLM_API_KEY=my-secret-qwen-key
LLM_API_BASE=http://79.137.184.118:42005/v1
LLM_MODEL=qwen3-coder-plus
```

### `.env.docker.secret` (LMS API configuration)

```bash
LMS_API_KEY=my-secret-api-key
AGENT_API_BASE_URL=http://79.137.184.118:42002
```

| Variable | Purpose | Source | Required |
|----------|---------|--------|----------|
| `LLM_API_KEY` | LLM provider API key | `.env.agent.secret` | Yes |
| `LLM_API_BASE` | LLM API endpoint URL | `.env.agent.secret` | Yes |
| `LLM_MODEL` | Model name | `.env.agent.secret` | Yes |
| `LMS_API_KEY` | Backend API key for query_api | `.env.docker.secret` | Yes |
| `AGENT_API_BASE_URL` | Base URL for backend API | `.env.docker.secret` | No (default: `http://localhost:42002`) |

> **Note:** `.env.agent.secret` and `.env.docker.secret` are gitignored. Never commit secrets.

## Tools

The agent has three tools that allow it to interact with the project file system and backend API.

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

List files and directories at the specified path with type indicators.

**Parameters:**

- `path` (string, required): Relative directory path from project root

**Example:**

```json
{"tool": "list_files", "args": {"path": "wiki"}}
```

**Returns:** Newline-separated list showing `filename (file)` or `dirname (dir)`.

**Security:**

- Same path validation as `read_file`
- Only lists directories within the project root

### `query_api`

Query the backend LMS API with authentication.

**Parameters:**

- `method` (string, required): HTTP method (GET, POST, PUT, DELETE)
- `path` (string, required): API endpoint path (e.g., `/items/`, `/analytics/completion-rate`)
- `body` (string, optional): JSON request body for POST/PUT requests

**Example:**

```json
{"tool": "query_api", "args": {"method": "GET", "path": "/items/"}}
```

**Returns:** JSON string with `status_code` and `body`:

```json
{"status_code": 200, "body": [...]}
```

**Authentication:**

- Uses `LMS_API_KEY` from `.env.docker.secret`
- Header: `Authorization: Bearer {LMS_API_KEY}`

**Error Handling:**

- Connection errors (backend not running)
- HTTP errors (4xx, 5xx)
- Timeout (>60 seconds)
- Invalid JSON in request body

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

### System Prompt Strategy

The system prompt guides the LLM to choose the right tool:

1. **Wiki questions** → `list_files` + `read_file` in wiki/
2. **Source code questions** → `list_files` + `read_file` in backend/
3. **Data questions** → `query_api` to fetch real data
4. **API behavior questions** → `query_api` to test endpoints
5. **Bug diagnosis** → `query_api` to reproduce error, then `read_file` to examine code

The prompt explicitly instructs the LLM to:

- Use `read_file` to read actual file contents, not just `list_files`
- Construct full paths by combining directory + entry name
- Read ALL relevant files for "list all" questions
- Include source references when citing files

## Usage

### Basic Usage

```bash
uv run agent.py "How do you resolve a merge conflict?"
```

### Output

The agent outputs a single JSON line to stdout:

```json
{
  "answer": "To resolve a merge conflict, open the conflicting file in VS Code, look for conflict markers, choose which changes to keep, delete the markers, then stage and commit.",
  "source": "wiki/git-vscode.md#resolve-a-merge-conflict",
  "tool_calls": [
    {
      "tool": "list_files",
      "args": {"path": "wiki"},
      "result": "git.md (file)\ngit-vscode.md (file)\n..."
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
| `source` | string | File path with optional section anchor (may be empty for API questions) |
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

## Benchmark Results

The agent is evaluated against 10 benchmark questions covering:

- Wiki lookup questions
- Source code analysis
- API data queries
- API behavior testing
- Bug diagnosis

### Current Performance

As of the latest iteration:

- **Questions 1-2 (wiki lookup):** ✓ Passing
- **Question 3 (source code):** ✓ Passing (FastAPI identification)
- **Question 4 (router listing):** Partial (LLM stops early sometimes)
- **Questions 5-7 (API queries):** ✓ Passing
- **Questions 8-9 (LLM judge):** Requires manual verification

### Lessons Learned

1. **Path construction is critical:** The LLM needs explicit instructions to combine directory paths with entry names (e.g., `backend/app` not just `app`).

2. **File type indicators help:** Adding `(file)` and `(dir)` to `list_files` output helps the LLM understand what it can read.

3. **LLM limitations:** The model sometimes stops exploring prematurely, especially for "list all" questions. More explicit prompting helps but doesn't fully solve this.

4. **Two API keys:** It's essential to keep `LLM_API_KEY` (for the LLM provider) separate from `LMS_API_KEY` (for the backend API). Mixing them up causes authentication failures.

5. **Environment variable loading:** The agent must load from both `.env.agent.secret` and `.env.docker.secret` to have all required configuration.

6. **Error handling matters:** The `query_api` tool must gracefully handle connection errors, timeouts, and invalid JSON to prevent crashes.

## File Structure

```
se-toolkit-lab-6/
├── agent.py              # Main CLI script with agentic loop
├── AGENT.md              # This documentation
├── .env.agent.secret     # LLM configuration (gitignored)
├── .env.docker.secret    # LMS API configuration (gitignored)
├── plans/
│   ├── task-1.md         # Task 1 implementation plan
│   ├── task-2.md         # Task 2 implementation plan
│   └── task-3.md         # Task 3 implementation plan + benchmark results
├── wiki/                 # Project documentation
├── backend/              # Backend source code
└── tests/
    └── test_agent.py     # Regression tests
```

## Troubleshooting

### "LMS_API_KEY not set"

Ensure `.env.docker.secret` exists and contains:

```bash
LMS_API_KEY=my-secret-api-key
```

### "Connection refused" from query_api

The backend API must be running. Start it with:

```bash
docker compose --env-file .env.docker.secret up -d
```

### Agent doesn't read all files

The LLM may stop exploring prematurely. Try:

- Being more specific in your question
- Asking follow-up questions to explore remaining files

### Source field is empty

For API questions, the source may be empty since the answer comes from live data, not a file. This is expected behavior.
