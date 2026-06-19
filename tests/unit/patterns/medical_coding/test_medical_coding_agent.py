# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for medical_coding_agent.py

Covers:
- get_ssm_parameter (happy path + not-found)
- get_system_prompt (SSM + Bedrock prompt lookup)
- query_knowledge_base (happy path + empty results + exception)
- create_kb_tool / search_medical_codes (result formatting + no-results branch)
- agent_stream entrypoint (missing fields, happy-path streaming, error propagation)
"""

import importlib
import json
import sys
import os
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

# ---------------------------------------------------------------------------
# Path setup — add agent dir so "medical_coding_agent" resolves to the module
# ---------------------------------------------------------------------------
AGENT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../../../patterns/medical-coding-agent")
)
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)

# Also add the repo root so gateway/ sub-package can be found when the module
# is imported during tests (BedrockAgentCoreApp + gateway.utils imports).
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ssm_client(value: str = "ssm-value"):
    client = MagicMock()
    client.get_parameter.return_value = {"Parameter": {"Value": value}}
    return client


def _make_bedrock_agent_client(prompt_text: str = "You are a medical coder."):
    client = MagicMock()
    client.get_prompt.return_value = {
        "variants": [{"templateConfiguration": {"text": {"text": prompt_text}}}]
    }
    return client


def _make_bedrock_agent_runtime_client(results=None):
    client = MagicMock()
    client.retrieve.return_value = {"retrievalResults": results or []}
    return client


def _import_agent():
    """Import (or reload) the medical_coding_agent module."""
    # Remove cached copy so patches applied via boto3.client work correctly
    if "medical_coding_agent" in sys.modules:
        del sys.modules["medical_coding_agent"]
    import medical_coding_agent as m
    return m


# ---------------------------------------------------------------------------
# get_ssm_parameter
# ---------------------------------------------------------------------------

class TestGetSsmParameter:
    def test_happy_path(self):
        ssm = _make_ssm_client("my-value")
        with patch("boto3.client", return_value=ssm):
            m = _import_agent()
            assert m.get_ssm_parameter("/some/param") == "my-value"

    def test_not_found_raises_value_error(self):
        ssm = MagicMock()
        not_found_exc = type("ParameterNotFound", (Exception,), {})
        ssm.exceptions.ParameterNotFound = not_found_exc
        ssm.get_parameter.side_effect = not_found_exc("not found")
        with patch("boto3.client", return_value=ssm):
            m = _import_agent()
            with pytest.raises(ValueError, match="not found"):
                m.get_ssm_parameter("/missing/param")

    def test_generic_exception_raises_value_error(self):
        ssm = MagicMock()
        ssm.exceptions.ParameterNotFound = type("ParameterNotFound", (Exception,), {})
        ssm.get_parameter.side_effect = RuntimeError("network error")
        with patch("boto3.client", return_value=ssm):
            m = _import_agent()
            with pytest.raises(ValueError, match="network error"):
                m.get_ssm_parameter("/broken/param")


# ---------------------------------------------------------------------------
# get_system_prompt
# ---------------------------------------------------------------------------

class TestGetSystemPrompt:
    def test_returns_prompt_text(self):
        ssm = _make_ssm_client(
            "arn:aws:bedrock:us-east-1:123456789012:prompt/ABCDE12345:1"
        )
        bedrock_agent = _make_bedrock_agent_client("Extract ICD-10 codes.")

        def boto_client(service, **kwargs):
            return ssm if service == "ssm" else bedrock_agent

        with patch("boto3.client", side_effect=boto_client):
            m = _import_agent()
            result = m.get_system_prompt("/stack/prompts/medical-coding-agent")

        assert result == "Extract ICD-10 codes."

    def test_parses_arn_parts_correctly(self):
        """Ensures prompt_id and version are extracted from versioned ARN."""
        ssm = _make_ssm_client(
            "arn:aws:bedrock:us-east-1:123456789012:prompt/MYPROMPTID:7"
        )
        bedrock_agent = _make_bedrock_agent_client("prompt text")

        def boto_client(service, **kwargs):
            return ssm if service == "ssm" else bedrock_agent

        with patch("boto3.client", side_effect=boto_client):
            m = _import_agent()
            m.get_system_prompt("/stack/prompt-path")

        bedrock_agent.get_prompt.assert_called_once_with(
            promptIdentifier="MYPROMPTID", promptVersion="7"
        )


# ---------------------------------------------------------------------------
# query_knowledge_base
# ---------------------------------------------------------------------------

class TestQueryKnowledgeBase:
    def test_returns_formatted_results(self):
        raw = [
            {
                "content": {"text": "J44.1 COPD with acute exacerbation"},
                "score": 0.92,
                "metadata": {"source": "icd10"},
            }
        ]
        runtime = _make_bedrock_agent_runtime_client(raw)
        with patch("boto3.client", return_value=runtime):
            m = _import_agent()
            results = m.query_knowledge_base("COPD exacerbation", "KB123")

        assert len(results) == 1
        assert results[0]["content"] == "J44.1 COPD with acute exacerbation"
        assert results[0]["score"] == 0.92
        assert results[0]["metadata"] == {"source": "icd10"}

    def test_returns_empty_list_when_no_results(self):
        runtime = _make_bedrock_agent_runtime_client([])
        with patch("boto3.client", return_value=runtime):
            m = _import_agent()
            assert m.query_knowledge_base("unknown term", "KB123") == []

    def test_returns_empty_list_on_exception(self):
        runtime = MagicMock()
        runtime.retrieve.side_effect = RuntimeError("service error")
        with patch("boto3.client", return_value=runtime):
            m = _import_agent()
            assert m.query_knowledge_base("query", "KB123") == []

    def test_passes_max_results_to_retrieve(self):
        runtime = _make_bedrock_agent_runtime_client([])
        with patch("boto3.client", return_value=runtime):
            m = _import_agent()
            m.query_knowledge_base("query", "KB123", max_results=3)

        call_kwargs = runtime.retrieve.call_args[1]
        assert (
            call_kwargs["retrievalConfiguration"]["vectorSearchConfiguration"][
                "numberOfResults"
            ]
            == 3
        )


# ---------------------------------------------------------------------------
# create_kb_tool / search_medical_codes
# ---------------------------------------------------------------------------

class TestKbTool:
    def test_no_results_returns_message_json(self):
        m = _import_agent()
        with patch.object(m, "query_knowledge_base", return_value=[]):
            tool = m.create_kb_tool("KB123")
            result = json.loads(tool("COPD"))
        assert result["message"] == "No relevant codes found"
        assert result["query"] == "COPD"

    def test_results_are_formatted(self):
        raw = [{"content": "J44.1 COPD", "score": 0.9, "metadata": {}}]
        m = _import_agent()
        with patch.object(m, "query_knowledge_base", return_value=raw):
            tool = m.create_kb_tool("KB123")
            result = json.loads(tool("COPD", "icd10"))

        assert result["query"] == "COPD"
        assert result["code_type"] == "icd10"
        assert len(result["results"]) == 1
        assert result["results"][0]["content"] == "J44.1 COPD"
        assert result["results"][0]["relevance_score"] == 0.9

    def test_code_type_all_passes_query_unchanged(self):
        """When code_type is 'all', the query is not modified."""
        m = _import_agent()
        with patch.object(m, "query_knowledge_base", return_value=[]) as mock_kb:
            tool = m.create_kb_tool("KB123")
            tool("diabetes", "all")
        mock_kb.assert_called_once_with("diabetes", "KB123", max_results=5)

    def test_specific_code_type_appended_to_query(self):
        m = _import_agent()
        with patch.object(m, "query_knowledge_base", return_value=[]) as mock_kb:
            tool = m.create_kb_tool("KB123")
            tool("diabetes", "cpt")
        mock_kb.assert_called_once_with("diabetes cpt", "KB123", max_results=5)


# ---------------------------------------------------------------------------
# agent_stream entrypoint (async, using anyio via pytest-anyio plugin)
# ---------------------------------------------------------------------------

async def _collect(coro_gen):
    """Drain an async generator into a list."""
    events = []
    async for event in coro_gen:
        events.append(event)
    return events


@pytest.mark.anyio
async def test_stream_missing_prompt_yields_error():
    m = _import_agent()
    events = await _collect(
        m.agent_stream({"userId": "u1", "runtimeSessionId": "s1"})
    )
    assert len(events) == 1
    assert events[0]["status"] == "error"
    assert "prompt" in events[0]["error"]


@pytest.mark.anyio
async def test_stream_missing_user_id_yields_error():
    m = _import_agent()
    events = await _collect(
        m.agent_stream({"prompt": "code this", "runtimeSessionId": "s1"})
    )
    assert events[0]["status"] == "error"


@pytest.mark.anyio
async def test_stream_missing_session_id_yields_error():
    m = _import_agent()
    events = await _collect(
        m.agent_stream({"prompt": "code this", "userId": "u1"})
    )
    assert events[0]["status"] == "error"


@pytest.mark.anyio
async def test_stream_agent_creation_error_yields_error_event():
    m = _import_agent()
    with patch.object(
        m,
        "create_medical_coding_agent",
        side_effect=ValueError("MEMORY_ID not set"),
    ):
        events = await _collect(
            m.agent_stream({"prompt": "code this", "userId": "u1", "runtimeSessionId": "s1"})
        )
    assert events[0]["status"] == "error"
    assert "MEMORY_ID" in events[0]["error"]


@pytest.mark.anyio
async def test_stream_happy_path_yields_agent_events():
    """Agent events are forwarded unchanged to the caller."""
    mock_agent = MagicMock()

    async def _fake_stream(_query):
        yield {"type": "text", "text": "ICD-10: J44.1"}
        yield {"type": "done"}

    mock_agent.stream_async = _fake_stream

    m = _import_agent()
    with patch.object(m, "create_medical_coding_agent", return_value=mock_agent):
        events = await _collect(
            m.agent_stream(
                {"prompt": "code COPD note", "userId": "u1", "runtimeSessionId": "s1"}
            )
        )

    assert {"type": "text", "text": "ICD-10: J44.1"} in events
    assert {"type": "done"} in events
