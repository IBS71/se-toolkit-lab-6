# Task 3: The System Agent — Implementation Plan

## Overview

This task extends the Task 2 agent with a `query_api` tool that can query the deployed backend API. The agent will answer both static system questions (framework, ports, status codes) and data-dependent queries (item count, scores, analytics).

## New Tool: `query_api`

### Purpose

Call the deployed backend LMS API to fetch real-time data or test endpoint behavior.

### Parameters

- `method` (string, required): HTTP method (GET, POST, PUT, DELETE, etc.)
- `path` (string, required): API endpoint path (e.g., `/items/`, `/analytics/completion-rate`)
- `body` (string, optional): JSON request body for POST/PUT requests

### Returns

JSON string with:

- `status_code`: HTTP status code (e.g., 200, 401, 404)
- `body`: Response body (parsed JSON or raw text)

### Authentication

The tool must authenticate using `LMS_API_KEY` from `.env.docker.secret`:

- Header: `Authorization: Bearer {LMS_API_KEY}`

### Function Schema (for LLM)

```json
{
  "name": "query_api",
  "description": "Query the backend LMS API. Use for questions about data in the database, API behavior, status codes, or analytics.",
  "parameters": {
    "type": "object",
    "properties": {
      "method": {
        "type": "string",
        "description": "HTTP method (GET, POST, PUT, DELETE)"
      },
      "path": {
        "type": "string",
        "description": "API endpoint path (e.g., '/items/', '/analytics/completion-rate')"
      },
      "body": {
        "type": "string",
        "description": "Optional JSON request body for POST/PUT requests"
      }
    },
    "required": ["method", "path"]
  }
}
```

## Environment Variables

The agent must read all configuration from environment variables:

| Variable | Purpose | Source | Required |
|----------|---------|--------|----------|
| `LLM_API_KEY` | LLM provider API key | `.env.agent.secret` | Yes |
| `LLM_API_BASE` | LLM API endpoint URL | `.env.agent.secret` | Yes |
| `LLM_MODEL` | Model name | `.env.agent.secret` | Yes |
| `LMS_API_KEY` | Backend API key for query_api | `.env.docker.secret` | Yes |
| `AGENT_API_BASE_URL` | Base URL for backend API | Env or default | No (default: `http://localhost:42002`) |

### Loading Strategy

```python
def load_config():
    # Load LLM config from .env.agent.secret
    load_dotenv(".env.agent.secret")
    
    # Load LMS_API_KEY from .env.docker.secret
    load_dotenv(".env.docker.secret", override=False)
    
    config = {
        "llm_api_key": os.getenv("LLM_API_KEY"),
        "llm_api_base": os.getenv("LLM_API_BASE"),
        "llm_model": os.getenv("LLM_MODEL"),
        "lms_api_key": os.getenv("LMS_API_KEY"),
        "agent_api_base_url": os.getenv("AGENT_API_BASE_URL", "http://localhost:42002"),
    }
```

> **Important:** The autochecker injects different credentials at evaluation time. Never hardcode any of these values.

## Updated System Prompt

The system prompt must guide the LLM to choose the right tool:

```
You are a documentation and system assistant with access to three tools:
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
   - Use read_file to read the code

3. For data/API questions (e.g., "How many items are in the database?"):
   - Use query_api to fetch real data
   - Example: GET /items/ returns all items

4. For API behavior questions (e.g., "What status code for unauthenticated request?"):
   - Use query_api to test the endpoint
   - Note the status_code in the response

5. For bug diagnosis questions:
   - Use query_api to reproduce the error
   - Use read_file to examine the source code
   - Explain the bug and suggest a fix

Maximum 10 tool calls allowed.
```

## Implementation Steps

1. Create `plans/task-3.md` (this plan)
2. Update `agent.py`:
   - Add `query_api()` function with authentication
   - Add `query_api` tool schema
   - Update `load_config()` to read `LMS_API_KEY` and `AGENT_API_BASE_URL`
   - Update system prompt with tool selection guidance
3. Update `AGENT.md`:
   - Document `query_api` tool
   - Explain authentication with `LMS_API_KEY`
   - Document environment variable loading
   - Add lessons learned from benchmark
4. Add 2 regression tests:
   - Test backend framework question (expects `read_file`)
   - Test database item count question (expects `query_api`)
5. Run `uv run run_eval.py` and iterate until all 10 questions pass
6. Document benchmark results in `plans/task-3.md`

## Benchmark Questions

| # | Question | Expected Tool | Answer Type |
|---|----------|---------------|-------------|
| 0 | Protect branch steps (wiki) | `read_file` | Keyword: branch, protect |
| 1 | SSH connection steps (wiki) | `read_file` | Keyword: ssh, key, connect |
| 2 | Backend framework | `read_file` | Keyword: FastAPI |
| 3 | API router modules | `list_files` | Keyword: items, interactions, analytics, pipeline |
| 4 | Items in database | `query_api` | Number > 0 |
| 5 | Status code without auth | `query_api` | Keyword: 401, 403 |
| 6 | Completion-rate error (lab-99) | `query_api`, `read_file` | Keyword: ZeroDivisionError |
| 7 | Top-learners error | `query_api`, `read_file` | Keyword: TypeError, None |
| 8 | Request lifecycle (docker-compose + Dockerfile) | `read_file` | LLM judge (≥4 hops) |
| 9 | ETL idempotency | `read_file` | LLM judge (external_id check) |

## Error Handling

The `query_api` tool must handle:

- Connection errors (backend not running)
- HTTP errors (4xx, 5xx)
- Invalid JSON responses
- Timeout (>60 seconds)

All errors should be returned as descriptive strings, not raise exceptions.

## Files to Modify/Create

- `plans/task-3.md` — new (implementation plan + benchmark results)
- `agent.py` — modify (add `query_api` tool, update config loading)
- `AGENT.md` — modify (update documentation)
- `tests/test_agent.py` — modify (add 2 more tests)

## Dependencies

No new dependencies needed — `httpx` already available.

## Testing Strategy

1. Manual testing with each benchmark question
2. Run `uv run run_eval.py` after each fix
3. Add regression tests for representative questions
4. Verify tool calls match expected tools

## Benchmark Results

### Initial Run

```
  + [1/10] According to the project wiki, what steps are needed to protect a branch on GitHub?
  + [2/10] What does the project wiki say about connecting to your VM via SSH?
  x [3/10] What Python web framework does this project's backend use?
```

**Issue:** Agent was calling `list_files` repeatedly but not reading actual source files.

**Fix:** Updated system prompt to explicitly instruct reading source code files and looking at imports.

### Second Run

```
  + [1/10] Protect branch (wiki)
  + [2/10] SSH connection (wiki)
  + [3/10] Backend framework (FastAPI) ✓
  x [4/10] List API routers
```

**Issue:** Agent stops after reading only 2 routers instead of all 6.

**Analysis:** The LLM model decides when to stop calling tools. For "list all" questions, it may prematurely conclude it has enough information.

**Fix attempt:** Updated system prompt to explicitly state "For questions asking about 'all' or 'list' items, make sure to examine ALL relevant files before answering."

**Result:** Partial improvement - the LLM still sometimes stops early due to model limitations.

### Current Status

- **Questions 1-3:** ✓ Passing consistently
- **Question 4:** Partially passing (depends on LLM behavior)
- **Questions 5-7:** Need verification (API queries)
- **Questions 8-9:** LLM judge questions (require manual verification)

### Lessons Learned

1. **Path construction is critical:** The LLM needs explicit instructions to combine directory paths (e.g., `backend/app` not just `app`).

2. **File type indicators help:** Adding `(file)` and `(dir)` to `list_files` output helps the LLM understand what it can read.

3. **LLM limitations:** The model sometimes stops exploring prematurely. More explicit prompting helps but doesn't fully solve this for complex "list all" questions.

4. **Two API keys:** Essential to keep `LLM_API_KEY` (for LLM provider) separate from `LMS_API_KEY` (for backend API).

5. **Error handling matters:** The `query_api` tool must gracefully handle connection errors, timeouts, and invalid JSON.

### Iteration Strategy

1. Test each question individually with `uv run run_eval.py --index N`
2. For failing questions, run manually to see full agent output
3. Adjust system prompt based on observed behavior
4. Re-run full eval after each fix
