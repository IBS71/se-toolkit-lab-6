# The Documentation Agent

An **agent** is a program that uses an LLM with **tools** — functions it can call to interact with the real world. Unlike a chatbot that answers from training data alone, an agent can read files, query APIs, and reason about real information. The difference is the **agentic loop**: the LLM decides which tool to call, your code executes it, feeds the result back, and the LLM decides what to do next — call another tool or give the final answer.

In this task you will build a CLI agent that reads the project wiki, finds the section that answers a question, and returns both the answer and the source reference.

## [Git workflow](../../../wiki/git-workflow.md)

1. Create an issue titled `[Task] The Documentation Agent`.
2. Pull latest `main` from `origin` and `upstream`.
3. Create a branch from `main` (e.g., `task/documentation-agent`).
4. Work on the branch. Commit as you go using [conventional commits](https://www.conventionalcommits.org/) (e.g., `feat:`, `docs:`, `test:`).
5. Push, create a PR to `main` in **your fork** (not upstream). Link the issue using a keyword (e.g., `Closes #1`).
6. Get a review from your partner, merge (this closes the issue automatically), delete the branch.

## What you will build

An agentic loop: the LLM navigates the project wiki using tools, finds the section that answers the question, and returns the answer with a source reference.

```mermaid
sequenceDiagram
    actor User
    participant CLI as agent.py
    participant LLM as LLM API<br/>(OpenRouter)
    participant Tools as Tools<br/>(files)

    User->>CLI: python agent.py "..."
    CLI->>LLM: messages + tool definitions
    LLM-->>CLI: tool_calls: [{list_files, ...}]
    CLI->>Tools: execute list_files("wiki")
    Tools-->>CLI: file listing
    CLI->>LLM: tool result
    LLM-->>CLI: tool_calls: [{read_file, ...}]
    CLI->>Tools: execute read_file("wiki/git-workflow.md")
    Tools-->>CLI: file contents
    CLI->>LLM: tool result
    LLM-->>CLI: final answer + source
    CLI->>User: {"answer": "...", "source": "...", "tool_calls": [...]}
```

## LLM access

Your agent uses the LLM you configured during [lab setup](../setup-simple.md#19-set-up-llm-access). The credentials in `.env.agent.secret` (`LLM_API_KEY`, `LLM_API_BASE`, `LLM_MODEL`) are read by `agent.py` at runtime.

> **Tip:** Run `python verify_llm.py` to confirm your LLM connection and tool calling still work before you start coding.

## CLI interface

**Input:**

```bash
python agent.py "How do you resolve a merge conflict?"
```

**Output:**

```json
{
  "answer": "Edit the conflicting file, choose which changes to keep, then stage and commit.",
  "source": "wiki/git-workflow.md#resolving-merge-conflicts",
  "tool_calls": [
    {"tool": "list_files", "args": {"path": "wiki"}, "result": "git-workflow.md\n..."},
    {"tool": "read_file", "args": {"path": "wiki/git-workflow.md"}, "result": "..."}
  ]
}
```

**Fields:**

- `answer` (string, required) — the agent's answer to the question.
- `source` (string, required) — the wiki section reference (e.g., `wiki/git-workflow.md#resolving-merge-conflicts`).
- `tool_calls` (array, required) — all tool calls made. Each entry has `tool`, `args`, and `result`.

**Rules:**

- Only valid JSON goes to stdout. All debug/progress output goes to **stderr**.
- The agent must respond within 60 seconds.
- Maximum 10 tool calls per question.
- Exit code 0 on success.

## Required tools

You must implement two tools and register them as function-calling schemas in your LLM request.

### `read_file`

Read a file from the project repository.

- **Parameters:** `path` (string) — relative path from project root.
- **Returns:** file contents as a string, or an error message if the file doesn't exist.
- **Security:** must not read files outside the project directory (no `../` traversal).

### `list_files`

List files and directories at a given path.

- **Parameters:** `path` (string) — relative directory path from project root.
- **Returns:** newline-separated listing of entries.
- **Security:** must not list directories outside the project directory.

## The agentic loop

Your agent should follow this pattern:

1. Send the user's question + tool definitions to the LLM.
2. If the LLM responds with `tool_calls` → execute each tool, append results as `tool` role messages, go to step 1.
3. If the LLM responds with a text message (no tool calls) → that's the final answer. Extract the answer and source, output JSON and exit.
4. If you hit 10 tool calls → stop looping, use whatever answer you have.

Your system prompt should tell the LLM:

- It is a documentation agent that answers questions using the project wiki.
- It should use `list_files` to discover wiki files, then `read_file` to find the answer.
- It must include the source reference (file path + section anchor) in its response.

## Deliverables

### 1. Plan (`plans/task-1.md`)

Before writing code, create `plans/task-1.md`. Describe:

- Which LLM provider and model you will use, and why.
- How you will structure the agent (argument parsing, LLM call, output formatting).
- How you will implement the tools and the agentic loop.
- What your system prompt strategy will be.

Commit:

```text
docs: add implementation plan for documentation agent
```

### 2. Agent (`agent.py`)

Create `agent.py` in the project root. The agent must:

- Define `read_file` and `list_files` as function-calling schemas.
- Implement the agentic loop (tool call → execute → feed result → repeat).
- Navigate the `wiki/` directory to find answers.
- Return JSON with `answer`, `source`, and `tool_calls` fields.

Commit:

```text
feat: implement documentation agent with wiki tools
```

### 3. Documentation (`AGENT.md`)

Create `AGENT.md` in the project root documenting:

- **Architecture**: how the agent works (input parsing, agentic loop, output formatting).
- **LLM provider**: which provider and model you chose, and why.
- **Tools**: what each tool does, its parameters, and security constraints.
- **System prompt strategy**: how you guide the LLM to navigate the wiki.
- **How to run**: the command and required environment variables.

Commit:

```text
docs: add agent architecture documentation
```

### 4. Tests (5 tests)

Create 5 regression tests that verify the agent works. Each test should:

- Run `agent.py` as a subprocess with a known question.
- Parse the stdout JSON.
- Check that `answer`, `source`, and `tool_calls` are present.
- Check that `tool_calls` is non-empty and contains the expected tool name.
- Check that the `source` field points to a reasonable wiki section.

Example test questions:

- `"How do you resolve a merge conflict?"` → expects `read_file` in tool_calls, `wiki/git-workflow.md` in source.
- `"What files are in the wiki?"` → expects `list_files` in tool_calls.
- `"What is a Docker volume?"` → expects `read_file` in tool_calls, `wiki/docker` in source.

Commit:

```text
test: add regression tests for documentation agent
```

### 5. Deployment

Deploy the agent to your VM. The autochecker will SSH in and run questions that require tools.

Make sure:

- The project repo is cloned on the VM.
- `.env.agent.secret` is configured on the VM (same LLM credentials as your local setup).

### 6. Benchmark

Run `python run_eval.py` to test your agent against wiki questions. Iterate until all Task 1 questions pass.

## Acceptance criteria

- [ ] Issue has the correct title.
- [ ] `plans/task-1.md` exists with the implementation plan (committed before code).
- [ ] `agent.py` exists in the project root.
- [ ] `python agent.py "..."` outputs valid JSON with `answer`, `source`, and `tool_calls`.
- [ ] The agent uses `read_file` and `list_files` tools to navigate the wiki.
- [ ] The `source` field correctly identifies the wiki section that answers the question.
- [ ] Tools do not access files outside the project directory.
- [ ] `AGENT.md` documents the agent architecture.
- [ ] 5 regression tests exist and pass.
- [ ] The agent works on the VM via SSH.
- [ ] The benchmark passes all Task 1 questions locally.
- [ ] PR is approved and merged.
- [ ] Issue is closed by the PR.
