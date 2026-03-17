"""
Regression tests for agent.py

Tests verify that:
1. agent.py runs successfully with a question
2. Output is valid JSON
3. 'answer' field exists and is a non-empty string
4. 'tool_calls' field exists and is an array
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest


AGENT_PATH = Path(__file__).parent.parent / "agent.py"


def run_agent(question: str) -> subprocess.CompletedProcess:
    """Run agent.py with the given question and return the result."""
    result = subprocess.run(
        [sys.executable, str(AGENT_PATH), question],
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result


class TestAgentOutput:
    """Test suite for agent.py output validation."""

    def test_agent_returns_valid_json_with_answer_and_tool_calls(self):
        """
        Test that agent.py outputs valid JSON with required fields.

        This is the main regression test that verifies:
        - agent.py runs successfully (exit code 0)
        - stdout contains valid JSON
        - 'answer' field exists and is a non-empty string
        - 'tool_calls' field exists and is an array
        """
        question = "What is the capital of France?"

        result = run_agent(question)

        # Check exit code
        assert result.returncode == 0, f"Agent failed: {result.stderr}"

        # Parse JSON output (last line of stdout)
        output_lines = result.stdout.strip().split("\n")
        json_output = output_lines[-1]  # JSON should be on the last line

        try:
            data = json.loads(json_output)
        except json.JSONDecodeError as e:
            pytest.fail(f"Invalid JSON output: {e}\nOutput: {json_output}")

        # Check required fields
        assert "answer" in data, "Missing 'answer' field in output"
        assert isinstance(data["answer"], str), "'answer' must be a string"
        assert len(data["answer"].strip()) > 0, "'answer' must not be empty"

        assert "tool_calls" in data, "Missing 'tool_calls' field in output"
        assert isinstance(data["tool_calls"], list), "'tool_calls' must be an array"


class TestDocumentationAgent:
    """Test suite for documentation agent with tool calling."""

    def test_merge_conflict_question_uses_read_file(self):
        """
        Test that asking about merge conflicts triggers read_file tool.

        This test verifies:
        - Agent uses tools to find answers in the wiki
        - read_file is called when looking for specific information
        - source field contains wiki path
        """
        question = "How do you resolve a merge conflict?"

        result = run_agent(question)

        # Check exit code
        assert result.returncode == 0, f"Agent failed: {result.stderr}"

        # Parse JSON output
        output_lines = result.stdout.strip().split("\n")
        json_output = output_lines[-1]

        try:
            data = json.loads(json_output)
        except json.JSONDecodeError as e:
            pytest.fail(f"Invalid JSON output: {e}\nOutput: {json_output}")

        # Check required fields
        assert "answer" in data, "Missing 'answer' field"
        assert isinstance(data["answer"], str), "'answer' must be a string"
        assert len(data["answer"].strip()) > 0, "'answer' must not be empty"

        assert "tool_calls" in data, "Missing 'tool_calls' field"
        assert isinstance(data["tool_calls"], list), "'tool_calls' must be an array"

        # Check that read_file was used
        tool_names = [call.get("tool") for call in data["tool_calls"]]
        assert "read_file" in tool_names, "Expected read_file to be called"

        # Check that source field exists and contains wiki path
        assert "source" in data, "Missing 'source' field"
        assert isinstance(data["source"], str), "'source' must be a string"
        assert "wiki/" in data["source"], "Source should contain wiki path"

    def test_wiki_listing_question_uses_list_files(self):
        """
        Test that asking about wiki files triggers list_files tool.

        This test verifies:
        - Agent uses list_files to discover directory contents
        - Tool calls are recorded with args and results
        """
        question = "What files are in the wiki directory?"

        result = run_agent(question)

        # Check exit code
        assert result.returncode == 0, f"Agent failed: {result.stderr}"

        # Parse JSON output
        output_lines = result.stdout.strip().split("\n")
        json_output = output_lines[-1]

        try:
            data = json.loads(json_output)
        except json.JSONDecodeError as e:
            pytest.fail(f"Invalid JSON output: {e}\nOutput: {json_output}")

        # Check required fields
        assert "answer" in data, "Missing 'answer' field"
        assert isinstance(data["answer"], str), "'answer' must be a string"
        assert len(data["answer"].strip()) > 0, "'answer' must not be empty"

        assert "tool_calls" in data, "Missing 'tool_calls' field"
        assert isinstance(data["tool_calls"], list), "'tool_calls' must be an array"

        # Check that list_files was used
        tool_names = [call.get("tool") for call in data["tool_calls"]]
        assert "list_files" in tool_names, "Expected list_files to be called"

        # Check that source field exists
        assert "source" in data, "Missing 'source' field"
        assert isinstance(data["source"], str), "'source' must be a string"
