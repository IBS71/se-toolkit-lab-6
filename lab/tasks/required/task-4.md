# Pass the Benchmark

Iterate on your agent until it passes the evaluation benchmark.

## What you will do

Run the evaluation benchmark, examine failures, fix your agent, and repeat. The benchmark tests your agent with questions about the course material and your deployed system.

You cannot see the questions upfront — you discover them by running the eval. Each failed question shows you what went wrong. Fix it, re-run, and move on to the next one.

```
run eval → see failure → diagnose → fix agent → re-run → next failure → ...
```

> **Note:** The autochecker bot tests your agent with additional hidden questions not present in `run_eval.py`. These include multi-step challenges that require chaining tools: finding errors in application logs, tracing them to source files, and suggesting fixes. You need a genuinely working agent — not hard-coded answers.

## How to run the benchmark

Run `run_eval.py` from the project root:

```bash
uv run run_eval.py
```

It reads your autochecker credentials from `.env` / `.env.docker.secret` (`AUTOCHECKER_API_URL`, `AUTOCHECKER_EMAIL`, `AUTOCHECKER_PASSWORD`) — same ones you configured during setup.

The script:

1. Fetches one question at a time from the autochecker API.
2. Runs `uv run agent.py "question"` locally.
3. Checks the answer against the expected result.
4. On pass: prints green, moves to the next question.
5. On fail: prints red with a feedback hint, stops.

```
  ✓ [1/26] How do you resolve a merge conflict?
  ✓ [2/26] What is a Docker volume used for?
  ✓ [3/26] What framework does the backend use?

  ✗ [4/26] You change your Python code and run 'docker compose up -d'...
    feedback: Think about when Docker rebuilds the image vs reuses the old one.

3/26 passed
```

Fix the failing question, then run `uv run run_eval.py` again.

## Debugging workflow

When a question fails, diagnose the root cause:

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Wrong factual answer | System prompt missing this topic | Add the topic to your system prompt |
| Agent doesn't use a tool when it should | Tool description too vague for the LLM | Improve the tool's description in the schema |
| Tool called but returns an error | Bug in tool implementation | Fix the tool code, test it in isolation |
| Tool called with wrong arguments | LLM misunderstands the schema | Clarify parameter descriptions |
| Agent times out | Too many tool calls or slow LLM | Reduce max iterations, try a faster model |
| Answer is close but doesn't match | Phrasing doesn't contain expected keyword | Adjust system prompt to be more precise |

## Deliverables

### 1. Plan (`plans/task-4.md`)

Before iterating, create `plans/task-4.md`. Run the benchmark once and document:

- Your current score (e.g., "12/26 passed").
- The first few failures and your diagnosis of each.
- Your strategy for improving the agent.

Commit:

```text
docs: add benchmark iteration plan
```

### 2. Agent improvements (update `agent.py`)

Iterate on your agent until `run_eval.py` passes all local questions. Common improvements:

- Expand or refine the system prompt.
- Improve tool descriptions so the LLM calls the right tool.
- Fix tool implementations (path handling, error cases, response parsing).
- Handle edge cases (empty responses, timeout, malformed data).

Commit as you go. Example:

```text
fix: improve system prompt for Docker questions
fix: handle empty file in read_file tool
feat: add retry logic for LLM API rate limits
```

### 3. Documentation (update `AGENT.md`)

Update `AGENT.md` with:

- **Final architecture**: any changes made during iteration.
- **Lessons learned**: what failed and why, what you changed.
- **Eval score**: your final `run_eval.py` result.

Commit:

```text
docs: update agent documentation with benchmark results
```

### 4. Tests

Update your regression tests to cover any new edge cases you discovered during iteration.

Commit:

```text
test: update regression tests with benchmark edge cases
```

### 5. Deployment

Deploy the final agent to your VM. The autochecker bot will run the full benchmark including hidden questions.

You need at least **75%** of all questions (shared + hidden) to pass.

## Acceptance criteria

- [ ] `plans/task-4.md` exists with the initial diagnosis and strategy.
- [ ] `run_eval.py` passes all local questions.
- [ ] `AGENT.md` documents the final architecture and lessons learned (at least 200 words).
- [ ] Regression tests are updated.
- [ ] The agent passes the autochecker bot benchmark (≥75%).
- [ ] [Git workflow](../../../wiki/git-workflow.md): issue `[Task] Pass the Benchmark`, branch, PR with `Closes #...`, partner approval, merge.
