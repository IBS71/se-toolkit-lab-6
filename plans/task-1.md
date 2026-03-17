# Task 1: Call an LLM from Code — Implementation Plan

## LLM Provider and Model

**Provider:** Qwen Code API (deployed on VM)

**Model:** `qwen3-coder-plus`

**Reasoning:**
- 1000 free requests per day (sufficient for development and autochecker)
- Works from Russia without VPN
- No credit card required
- Already set up on VM at `http://79.137.184.118:42005/v1`
- Strong tool calling capabilities (needed for Task 2-3)

## Configuration

The agent reads LLM configuration from `.env.agent.secret`:

```
LLM_API_KEY=my-secret-qwen-key
LLM_API_BASE=http://79.137.184.118:42005/v1
LLM_MODEL=qwen3-coder-plus
```

## Agent Architecture

### Input
- Single command-line argument: the question string
- Example: `uv run agent.py "What is REST?"`

### Processing Flow
1. Parse command-line argument (question)
2. Load LLM configuration from `.env.agent.secret`
3. Build HTTP POST request to `{LLM_API_BASE}/chat/completions`
4. Include system message for consistent behavior
5. Send request with API key in Authorization header
6. Parse JSON response and extract answer content

### Output
- Single JSON line to stdout:
  ```json
  {"answer": "<llm response text>", "tool_calls": []}
  ```
- All debug/logging output goes to stderr
- Exit code 0 on success, non-zero on failure

## HTTP Request Format

```json
POST {LLM_API_BASE}/v1/chat/completions
Headers:
  Content-Type: application/json
  Authorization: Bearer {LLM_API_KEY}

Body:
{
  "model": "qwen3-coder-plus",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "<question from CLI>"}
  ]
}
```

## Error Handling

- Missing CLI argument → print error to stderr, exit 1
- Missing/invalid `.env.agent.secret` → print error to stderr, exit 1
- HTTP request failure → print error to stderr, exit 1
- Invalid JSON response → print error to stderr, exit 1
- Timeout (>60 seconds) → print error to stderr, exit 1

## Testing Strategy

Create `tests/test_agent.py` with one regression test:
1. Run `agent.py` as subprocess with a simple question
2. Parse stdout as JSON
3. Assert `answer` field exists and is non-empty string
4. Assert `tool_calls` field exists and is an array

## Files to Create

1. `plans/task-1.md` — this plan
2. `agent.py` — main CLI script
3. `AGENT.md` — documentation
4. `tests/test_agent.py` — regression test

## Dependencies

- `httpx` — already in `pyproject.toml` for async HTTP requests
- `python-dotenv` — for loading `.env.agent.secret`
- `pytest` — already available for testing
