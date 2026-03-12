#!/usr/bin/env python3
"""Local evaluation runner for the agent benchmark.

Fetches questions one at a time from the autochecker API,
runs your agent, and checks the answer locally.
Stops at the first failure.

Usage:
    uv run run_eval.py

Reads from .env (same credentials as the autochecker):
    AUTOCHECKER_API_URL  — e.g. https://auche.namaz.live
    AUTOCHECKER_EMAIL    — your university email
    AUTOCHECKER_PASSWORD — your GitHub username + Telegram alias
"""

import base64
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def _load_env():
    """Load variables from .env file (simple key=value parser)."""
    for env_file in [".env", ".env.docker.secret"]:
        path = Path(env_file)
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def _get_credentials():
    """Return (api_url, email, password) from environment."""
    api_url = os.environ.get("AUTOCHECKER_API_URL", "")
    email = os.environ.get("AUTOCHECKER_EMAIL", "")
    password = os.environ.get("AUTOCHECKER_PASSWORD", "")
    if not all([api_url, email, password]):
        print(
            "Missing credentials. Set AUTOCHECKER_API_URL, AUTOCHECKER_EMAIL, "
            "and AUTOCHECKER_PASSWORD in your .env file.",
            file=sys.stderr,
        )
        sys.exit(1)
    return api_url.rstrip("/"), email, password


def _basic_auth_header(email: str, password: str) -> str:
    """Build HTTP Basic Auth header value."""
    encoded = base64.b64encode(f"{email}:{password}".encode()).decode()
    return f"Basic {encoded}"


def _fetch_question(api_url: str, auth: str, lab: str, index: int):
    """Fetch a question from the autochecker API. Returns dict or None on 404."""
    import urllib.request
    import urllib.error

    url = f"{api_url}/api/eval/question?lab={lab}&index={index}"
    req = urllib.request.Request(url, headers={"Authorization": auth})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        body = e.read().decode() if e.fp else ""
        print(f"API error {e.code}: {body}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Cannot reach API: {e.reason}", file=sys.stderr)
        sys.exit(1)


def _run_agent(question: str, timeout: int = 60):
    """Run agent.py with the question. Returns (answer_dict, error_msg)."""
    try:
        result = subprocess.run(
            [sys.executable, "agent.py", question],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return None, "Agent timed out (60s)"
    except FileNotFoundError:
        return None, "agent.py not found"

    if result.returncode != 0:
        stderr_preview = result.stderr.strip()[:200] if result.stderr else ""
        return None, f"Agent exited with code {result.returncode}: {stderr_preview}"

    stdout = result.stdout.strip()
    if not stdout:
        return None, "Agent produced no output"

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return None, f"Agent output is not valid JSON: {stdout[:200]}"

    if "answer" not in data:
        return None, f"Missing 'answer' field in output: {stdout[:200]}"

    return data, None


# ---------------------------------------------------------------------------
# Matching logic (mirrors autochecker evaluation)
# ---------------------------------------------------------------------------

def _match(answer: str, expected: dict) -> bool:
    """Check if the answer satisfies the expected matching rule."""
    answer_lower = answer.lower()

    if "contains" in expected:
        return expected["contains"].lower() in answer_lower

    if "contains_all" in expected:
        return all(kw.lower() in answer_lower for kw in expected["contains_all"])

    if "any_of" in expected:
        return any(kw.lower() in answer_lower for kw in expected["any_of"])

    if "regex" in expected:
        return bool(re.search(expected["regex"], answer, re.IGNORECASE))

    if "numeric_gt" in expected:
        numbers = re.findall(r"[\d.]+", answer)
        return any(float(n) > expected["numeric_gt"] for n in numbers if n)

    if "numeric_range" in expected:
        lo, hi = expected["numeric_range"]
        numbers = re.findall(r"[\d.]+", answer)
        return any(lo <= float(n) <= hi for n in numbers if n)

    return False


def _format_expected(expected: dict) -> str:
    """Human-readable description of the expected match."""
    if "contains" in expected:
        return f"answer should contain: \"{expected['contains']}\""
    if "contains_all" in expected:
        return f"answer should contain all of: {expected['contains_all']}"
    if "any_of" in expected:
        return f"answer should contain any of: {expected['any_of']}"
    if "regex" in expected:
        return f"answer should match pattern: {expected['regex']}"
    if "numeric_gt" in expected:
        return f"answer should contain a number > {expected['numeric_gt']}"
    if "numeric_range" in expected:
        return f"answer should contain a number in range {expected['numeric_range']}"
    return str(expected)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

GREEN = "\033[92m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"

LAB = "lab-06"


def main():
    _load_env()
    api_url, email, password = _get_credentials()
    auth = _basic_auth_header(email, password)

    index = 0
    passed = 0

    while True:
        q = _fetch_question(api_url, auth, LAB, index)
        if q is None:
            # All questions done
            print(f"\n{BOLD}{GREEN}{passed}/{index} PASSED{RESET}")
            break

        total = q["total"]
        question = q["question"]
        expected = q["expected"]

        # Run the agent
        data, error = _run_agent(question)

        if error:
            print(f"\n  {RED}x [{index + 1}/{total}] {question}{RESET}")
            print(f"    Error: {error}")
            print(f"\n{BOLD}{passed}/{total} passed{RESET}")
            sys.exit(1)

        answer = data.get("answer", "")

        if _match(answer, expected):
            print(f"  {GREEN}+ [{index + 1}/{total}] {question}{RESET}")
            passed += 1
            index += 1
        else:
            print(f"\n  {RED}x [{index + 1}/{total}] {question}{RESET}")
            print(f"    Your answer: {answer[:200]}")
            print(f"    Expected: {_format_expected(expected)}")
            print(f"\n{BOLD}{passed}/{total} passed{RESET}")
            sys.exit(1)


if __name__ == "__main__":
    main()
