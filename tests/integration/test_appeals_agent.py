# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for Appeals (Denials) Agent."""

import json
import os

import boto3
import pytest

from scripts.utils import get_machine_client_token, get_ssm_parameter


@pytest.fixture
def stack_name():
    name = os.environ.get("STACK_NAME")
    if not name:
        pytest.skip("STACK_NAME not set")
    return name


@pytest.fixture
def gateway_config(stack_name):
    try:
        return {
            "gateway_url": get_ssm_parameter(f"/{stack_name}/gateway_url"),
            "token": get_machine_client_token(stack_name),
        }
    except SystemExit:
        pytest.skip("Could not fetch gateway config from SSM/Cognito")


@pytest.fixture
def appeals_kb_id(stack_name):
    ssm = boto3.client("ssm")
    try:
        return ssm.get_parameter(Name=f"/{stack_name}/appeals-kb-id")["Parameter"]["Value"]
    except Exception:
        pytest.skip("Appeals KB ID not found in SSM")


@pytest.fixture
def appeals_bucket(stack_name):
    ssm = boto3.client("ssm")
    try:
        return ssm.get_parameter(Name=f"/{stack_name}/appeals-bucket")["Parameter"]["Value"]
    except Exception:
        pytest.skip("Appeals bucket not found in SSM")


@pytest.fixture
def bedrock_agent_runtime():
    return boto3.client(
        "bedrock-agent-runtime",
        region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
    )


# ---------------------------------------------------------------------------
# Gateway tool tests
# ---------------------------------------------------------------------------


def test_gateway_appeals_tools_listed(gateway_config):
    """Appeals KB tools should be registered on the gateway."""
    import requests

    response = requests.post(
        gateway_config["gateway_url"],
        headers={
            "Authorization": f"Bearer {gateway_config['token']}",
            "Content-Type": "application/json",
        },
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        timeout=30,
    )

    assert response.status_code == 200
    tool_names = [t["name"] for t in response.json()["result"]["tools"]]
    has_appeals_tools = any("denial" in n or "appeal" in n for n in tool_names)
    if not has_appeals_tools:
        pytest.skip(f"Appeals/denial tools not deployed on this gateway. Available: {tool_names}")


def _get_gateway_tool(gateway_config, suffix):
    """Return the full tool name matching suffix, or None."""
    import requests
    resp = requests.post(
        gateway_config["gateway_url"],
        headers={"Authorization": f"Bearer {gateway_config['token']}", "Content-Type": "application/json"},
        json={"jsonrpc": "2.0", "id": 0, "method": "tools/list"},
        timeout=30,
    )
    return next((n for n in [t["name"] for t in resp.json()["result"]["tools"]] if suffix in n), None)


def test_search_denial_codes_via_gateway(gateway_config):
    """Look up a CARC denial code via the gateway tool."""
    import requests

    tool_name = _get_gateway_tool(gateway_config, "search_denial_codes")
    if not tool_name:
        pytest.skip("search_denial_codes tool not deployed on this gateway")

    response = requests.post(
        gateway_config["gateway_url"],
        headers={
            "Authorization": f"Bearer {gateway_config['token']}",
            "Content-Type": "application/json",
        },
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": {"query": "CO-4 procedure not covered"},
            },
        },
        timeout=30,
    )

    assert response.status_code == 200
    result = response.json()
    assert "result" in result
    content = json.loads(result["result"]["content"][0]["text"])
    assert content  # non-empty result


def test_search_appeal_regulations_via_gateway(gateway_config):
    """Retrieve appeal filing regulations from the gateway."""
    import requests

    tool_name = _get_gateway_tool(gateway_config, "search_appeal_regulations")
    if not tool_name:
        pytest.skip("search_appeal_regulations tool not deployed on this gateway")

    response = requests.post(
        gateway_config["gateway_url"],
        headers={
            "Authorization": f"Bearer {gateway_config['token']}",
            "Content-Type": "application/json",
        },
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": {"query": "Medicare appeal filing deadline timely filing"},
            },
        },
        timeout=30,
    )

    assert response.status_code == 200
    result = response.json()
    assert "result" in result


# ---------------------------------------------------------------------------
# Knowledge base direct retrieval tests
# ---------------------------------------------------------------------------


class TestAppealsKnowledgeBase:
    """Direct Bedrock KB retrieval tests for appeals data."""

    def test_search_denial_codes(self, bedrock_agent_runtime, appeals_kb_id):
        """KB should return denial code records."""
        response = bedrock_agent_runtime.retrieve(
            knowledgeBaseId=appeals_kb_id,
            retrievalQuery={"text": "CO-4 procedure not covered"},
            retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": 5}},
        )
        results = response.get("retrievalResults", [])
        assert len(results) > 0, "Should return denial code results"

    def test_search_appeal_regulations(self, bedrock_agent_runtime, appeals_kb_id):
        """KB should return appeal regulation records."""
        response = bedrock_agent_runtime.retrieve(
            knowledgeBaseId=appeals_kb_id,
            retrievalQuery={"text": "timely filing appeal deadline Medicare"},
            retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": 5}},
        )
        results = response.get("retrievalResults", [])
        assert len(results) > 0, "Should return appeal regulation results"

    def test_search_clinical_guidelines(self, bedrock_agent_runtime, appeals_kb_id):
        """KB should return clinical guidelines for medical necessity appeals."""
        response = bedrock_agent_runtime.retrieve(
            knowledgeBaseId=appeals_kb_id,
            retrievalQuery={"text": "MRI lumbar spine medical necessity criteria"},
            retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": 5}},
        )
        results = response.get("retrievalResults", [])
        assert len(results) > 0, "Should return clinical guideline results"


# ---------------------------------------------------------------------------
# Appeal letter S3 storage tests
# ---------------------------------------------------------------------------


class TestAppealLetterStorage:
    """Tests for appeal letter persistence in S3."""

    def test_list_appeal_letters(self, appeals_bucket):
        """Should be able to list appeal letters in S3."""
        s3 = boto3.client("s3")
        response = s3.list_objects_v2(Bucket=appeals_bucket, Prefix="appeal-letters/")
        assert "Contents" in response or response.get("KeyCount", 0) == 0  # bucket accessible

    def test_store_and_retrieve_appeal_letter(self, appeals_bucket):
        """Round-trip: store and retrieve a sample appeal letter."""
        import uuid

        s3 = boto3.client("s3")
        claim_id = f"TEST-APPEAL-{uuid.uuid4().hex[:8].upper()}"
        key = f"appeal-letters/{claim_id}.txt"
        body = (
            f"RE: Appeal for Claim {claim_id}\n\n"
            "To Whom It May Concern,\n\n"
            "We are writing to appeal the denial of the above-referenced claim...\n"
        )

        s3.put_object(Bucket=appeals_bucket, Key=key, Body=body, ContentType="text/plain")

        obj = s3.get_object(Bucket=appeals_bucket, Key=key)
        assert obj["Body"].read().decode() == body

        # Cleanup
        s3.delete_object(Bucket=appeals_bucket, Key=key)

    def test_presigned_url_generation(self, appeals_bucket):
        """Presigned URLs should be generated for letter download."""
        import uuid

        s3 = boto3.client("s3")
        key = f"appeal-letters/TEST-PRESIGN-{uuid.uuid4().hex[:8].upper()}.txt"
        s3.put_object(Bucket=appeals_bucket, Key=key, Body="test letter", ContentType="text/plain")

        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": appeals_bucket, "Key": key},
            ExpiresIn=3600,
        )

        assert url.startswith("https://")
        assert appeals_bucket in url

        # Cleanup
        s3.delete_object(Bucket=appeals_bucket, Key=key)
