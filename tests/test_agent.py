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


class TestSystemAgent:
    """Test suite for system agent with query_api tool."""

    def test_backend_framework_question_uses_read_file(self):
        """
        Test that asking about backend framework triggers read_file tool.

        This test verifies:
        - Agent reads source code to identify the framework
        - Answer contains 'FastAPI'
        - source field contains backend path
        """
        question = "What Python web framework does this project's backend use?"

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

        # Check that answer mentions FastAPI
        assert "FastAPI" in data["answer"], "Answer should mention FastAPI"

        assert "tool_calls" in data, "Missing 'tool_calls' field"
        assert isinstance(data["tool_calls"], list), "'tool_calls' must be an array"

        # Check that read_file was used
        tool_names = [call.get("tool") for call in data["tool_calls"]]
        assert "read_file" in tool_names, "Expected read_file to be called"

        # Check that source field contains backend path
        assert "source" in data, "Missing 'source' field"
        assert isinstance(data["source"], str), "'source' must be a string"
        assert "backend" in data["source"], "Source should reference backend directory"

    def test_database_count_question_uses_query_api(self):
        """
        Test that asking about database count triggers query_api tool.

        This test verifies:
        - Agent queries the API to get data
        - Answer contains a number
        - tool_calls contains query_api with correct args
        """
        question = "How many items are in the database?"

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

        # Check that query_api was used
        tool_names = [call.get("tool") for call in data["tool_calls"]]
        assert "query_api" in tool_names, "Expected query_api to be called"

        # Check that query_api was called with correct method and path
        query_api_calls = [
            call for call in data["tool_calls"] if call.get("tool") == "query_api"
        ]
        assert len(query_api_calls) > 0, "Expected at least one query_api call"
        
        api_call = query_api_calls[0]
        assert api_call.get("args", {}).get("method") == "GET", "Expected GET method"
        assert "/items" in api_call.get("args", {}).get("path", ""), "Expected /items path"

        # Check that answer contains a number
        import re
        numbers = re.findall(r'\d+', data["answer"])
        assert len(numbers) > 0, "Answer should contain a number"
