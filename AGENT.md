# Agent Documentation

## Overview

This agent is a Python CLI that connects to an LLM (Large Language Model) and returns structured JSON answers. It serves as the foundation for the agentic system that will be extended with tools and an agentic loop in subsequent tasks.

## Architecture

```
User (CLI) → agent.py → Qwen Code API (VM) → Qwen 3 Coder (Cloud) → agent.py → User (JSON)
```

### Components

1. **agent.py** — Main CLI script that:
   - Parses command-line arguments
   - Loads LLM configuration from `.env.agent.secret`
   - Sends HTTP POST requests to the LLM API
   - Returns structured JSON output

2. **Qwen Code API** — OpenAI-compatible API proxy deployed on the VM that:
   - Authenticates requests using API keys
   - Forwards requests to Qwen Cloud
   - Returns standardized chat completions responses

3. **Qwen 3 Coder** — The LLM model in the cloud that:
   - Processes natural language questions
   - Generates human-readable answers

## LLM Provider

**Provider:** Qwen Code API

**Model:** `qwen3-coder-plus`

**Endpoint:** `http://79.137.184.118:42005/v1`

**Why Qwen Code:**
- 1000 free requests per day
- Works from Russia without VPN
- No credit card required
- Strong tool calling capabilities (for Task 2-3)
- OpenAI-compatible API

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

## Usage

### Basic Usage

```bash
uv run agent.py "What is REST?"
```

### Output

The agent outputs a single JSON line to stdout:

```json
{"answer": "Representational State Transfer.", "tool_calls": []}
```

| Field | Type | Description |
|-------|------|-------------|
| `answer` | string | The LLM's response to the question |
| `tool_calls` | array | Empty for Task 1 (populated in Task 2) |

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success — JSON output printed |
| 1 | Error — missing argument, config, or API failure |

### Debug Output

All debug and progress messages are written to stderr:

```bash
$ uv run agent.py "What is 2+2?"
Calling LLM at http://79.137.184.118:42005/v1/chat/completions...
LLM response received.
{"answer": "2 + 2 = 4.", "tool_calls": []}
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

## Testing

Run the regression test:

```bash
uv run pytest tests/test_agent.py -v
```

The test verifies:
1. `agent.py` runs successfully with a question
2. Output is valid JSON
3. `answer` field exists and is non-empty
4. `tool_calls` field exists and is an array

## File Structure

```
se-toolkit-lab-6/
├── agent.py              # Main CLI script
├── AGENT.md              # This documentation
├── .env.agent.secret     # LLM configuration (gitignored)
├── .env.agent.example    # Example configuration
├── plans/
│   └── task-1.md         # Implementation plan
└── tests/
    └── test_agent.py     # Regression tests
```

## Extending the Agent

### Task 2: Adding Tools

In Task 2, the agent will be extended with:
- Tool definitions (functions the agent can call)
- Tool calling logic (parsing LLM responses for tool calls)
- Tool execution (running tools locally)

### Task 3: Agentic Loop

In Task 3, the agent will implement:
- Multi-turn conversation loop
- Tool result feedback to LLM
- Iterative problem solving

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

### "Request timed out"

The agent has a 60-second timeout. If the LLM takes longer, the request fails. Try again or check your network connection.
