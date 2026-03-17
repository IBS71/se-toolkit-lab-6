# Task 2: The Documentation Agent — Implementation Plan

## Overview

This task extends the Task 1 agent with two tools (`read_file`, `list_files`) and an agentic loop. The agent will be able to navigate the project wiki, read files, and provide answers with source references.

## Tool Definitions

### 1. `read_file`

**Purpose:** Read contents of a file from the project repository.

**Parameters:**
- `path` (string, required): Relative path from project root (e.g., `wiki/git.md`)

**Returns:** File contents as a string, or error message if file doesn't exist.

**Security:**
- Reject paths containing `../` (directory traversal)
- Reject absolute paths
- Only allow paths within project root

**Function Schema (for LLM):**
```json
{
  "name": "read_file",
  "description": "Read the contents of a file at the specified path",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "Relative path from project root (e.g., 'wiki/git.md')"
      }
    },
    "required": ["path"]
  }
}
```

### 2. `list_files`

**Purpose:** List files and directories at a given path.

**Parameters:**
- `path` (string, required): Relative directory path from project root (e.g., `wiki`)

**Returns:** Newline-separated list of file/directory names.

**Security:**
- Same path validation as `read_file`
- Only list directories, not arbitrary paths

**Function Schema (for LLM):**
```json
{
  "name": "list_files",
  "description": "List files and directories at the specified path",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "Relative directory path from project root (e.g., 'wiki')"
      }
    },
    "required": ["path"]
  }
}
```

## Agentic Loop

### Flow

1. **Initial Request:** Send user question + system prompt + tool definitions to LLM
2. **Parse Response:** Check if LLM returned `tool_calls` or a text answer
3. **If tool_calls:**
   - Execute each tool call locally
   - Append tool results as `tool` role messages
   - Send results back to LLM
   - Repeat from step 2
4. **If text answer:**
   - Extract answer and source from response
   - Output JSON and exit
5. **Termination conditions:**
   - LLM returns answer without tool calls → success
   - 10 tool calls reached → stop and return best answer

### Message History Format

```python
messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": question},
    # After tool calls:
    {"role": "assistant", "content": None, "tool_calls": [...]},
    {"role": "tool", "content": result, "tool_call_id": "..."},
    # Continue until final answer...
]
```

## System Prompt

The system prompt will instruct the LLM to:

1. Use `list_files` to discover relevant wiki files
2. Use `read_file` to read contents and find answers
3. Always include a `source` reference (file path + section anchor) in the final answer
4. Stop calling tools once the answer is found
5. Maximum 10 tool calls per question

Example:
```
You are a documentation assistant. You have access to two tools:
- list_files: List files in a directory
- read_file: Read contents of a file

To answer questions:
1. First use list_files to find relevant files in the wiki/ directory
2. Use read_file to read the contents of relevant files
3. Find the section that answers the question
4. Provide the answer with a source reference like: wiki/filename.md#section-anchor

Always include the source field in your final answer.
Maximum 10 tool calls allowed.
```

## Output Format

```json
{
  "answer": "Explanation text...",
  "source": "wiki/git-workflow.md#resolving-merge-conflicts",
  "tool_calls": [
    {
      "tool": "list_files",
      "args": {"path": "wiki"},
      "result": "git-workflow.md\ngit.md\n..."
    },
    {
      "tool": "read_file",
      "args": {"path": "wiki/git-workflow.md"},
      "result": "# Git Workflow\n\n## Resolving Merge Conflicts..."
    }
  ]
}
```

## Path Security

To prevent directory traversal attacks:

```python
def validate_path(path: str) -> bool:
    # Reject paths with ..
    if ".." in path:
        return False
    # Reject absolute paths
    if path.startswith("/"):
        return False
    # Resolve and check it's within project root
    full_path = (PROJECT_ROOT / path).resolve()
    return str(full_path).startswith(str(PROJECT_ROOT))
```

## Implementation Steps

1. Create `plans/task-2.md` (this plan)
2. Update `agent.py`:
   - Add `read_file()` and `list_files()` functions
   - Add path validation helper
   - Define tool schemas for LLM
   - Implement agentic loop with max 10 iterations
   - Track all tool calls with args and results
   - Extract source from LLM response
3. Update `AGENT.md`:
   - Document tools and their parameters
   - Explain agentic loop flow
   - Show example output
4. Add 2 regression tests:
   - Test merge conflict question (expects `read_file`, source in wiki)
   - Test wiki listing question (expects `list_files`)
5. Test manually with wiki questions
6. Run pytest to verify all tests pass

## Dependencies

- `httpx` — already available for HTTP requests
- `python-dotenv` — already available for env loading
- `pytest` — already available for testing
- No new dependencies needed

## Files to Modify/Create

- `plans/task-2.md` — new (implementation plan)
- `agent.py` — modify (add tools and loop)
- `AGENT.md` — modify (update documentation)
- `tests/test_agent.py` — modify (add 2 more tests)
