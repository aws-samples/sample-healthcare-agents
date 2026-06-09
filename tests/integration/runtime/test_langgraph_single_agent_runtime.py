#!/usr/bin/env python3
"""
Integration Test: LangGraph Single Agent via Runtime (Direct Invocation)

Usage:
    cd /path/to/healthcare-agents
    AWS_PROFILE=quicksuite uv run python3 tests/integration/runtime/test_langgraph_single_agent_runtime.py

    # Custom prompt
    AWS_PROFILE=quicksuite uv run python3 tests/integration/runtime/test_langgraph_single_agent_runtime.py \
        "What tools do you have available?"
"""

import argparse
import json
import sys
import urllib.parse
import uuid

import boto3
import requests


STACK_NAME = "healthcare-agents-stack-langgraph-single-agent"
REGION = "us-east-1"
SSM_STACK_BASE = "healthcare-agents-stack"

SAMPLE_PROMPT = "What tools do you have available? Please list them."


def get_machine_token() -> str:
    ssm = boto3.client("ssm", region_name=REGION)
    secrets = boto3.client("secretsmanager", region_name=REGION)

    client_id = ssm.get_parameter(Name=f"/{SSM_STACK_BASE}/machine_client_id")["Parameter"]["Value"]
    domain = ssm.get_parameter(Name=f"/{SSM_STACK_BASE}/cognito_provider")["Parameter"]["Value"]
    client_secret = secrets.get_secret_value(
        SecretId=f"/{SSM_STACK_BASE}/machine_client_secret"
    )["SecretString"]

    resp = requests.post(
        f"https://{domain}/oauth2/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": f"{SSM_STACK_BASE}-api/invoke",
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def get_runtime_arn() -> str:
    cfn = boto3.client("cloudformation", region_name=REGION)
    outputs = cfn.describe_stacks(StackName=STACK_NAME)["Stacks"][0]["Outputs"]
    for o in outputs:
        if o["OutputKey"] == "AgentRuntimeArn":
            return o["OutputValue"]
    raise ValueError(f"AgentRuntimeArn not found in {STACK_NAME} outputs")


def invoke_runtime(prompt: str, token: str, runtime_arn: str) -> bool:
    session_id = f"test-{uuid.uuid4()}"
    user_id = "test-user"
    escaped_arn = urllib.parse.quote(runtime_arn, safe="")
    url = f"https://bedrock-agentcore.{REGION}.amazonaws.com/runtimes/{escaped_arn}/invocations?qualifier=DEFAULT"

    print(f"Runtime ARN : {runtime_arn}")
    print(f"Session ID  : {session_id}")
    print(f"\nPrompt: {prompt}\n")
    print("-" * 80)

    resp = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": session_id,
        },
        json={"prompt": prompt, "userId": user_id, "runtimeSessionId": session_id},
        timeout=300,
        stream=True,
    )
    resp.raise_for_status()

    for line in resp.iter_lines():
        if not line:
            continue
        text = line.decode("utf-8")
        if not text.startswith("data: "):
            continue
        data = text[6:]
        try:
            event = json.loads(data)
            # LangGraph streams AIMessageChunk objects serialized as dicts
            if isinstance(event, dict):
                content = event.get("content", "")
                if isinstance(content, str) and content:
                    print(content, end="", flush=True)
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            print(block.get("text", ""), end="", flush=True)
                # Print error events
                if event.get("status") == "error":
                    print(f"\n[ERROR] {event.get('error')}")
        except json.JSONDecodeError:
            print(data, end="", flush=True)

    print("\n" + "-" * 80)
    return True


def test_langgraph_single_agent_runtime(prompt: str = None):
    print("=" * 80)
    print("LANGGRAPH SINGLE AGENT — Runtime Integration Test")
    print("=" * 80)
    print()

    print("Authenticating with Cognito (machine client)...")
    try:
        token = get_machine_token()
        print("Token obtained\n")
    except Exception as e:
        print(f"FAIL: Authentication error: {e}")
        return False

    print("Getting Runtime ARN from CloudFormation...")
    try:
        runtime_arn = get_runtime_arn()
        print("Runtime ARN found\n")
    except Exception as e:
        print(f"FAIL: {e}")
        return False

    try:
        return invoke_runtime(prompt or SAMPLE_PROMPT, token, runtime_arn)
    except requests.HTTPError as e:
        print(f"FAIL: HTTP {e.response.status_code} — {e.response.text[:300]}")
        return False
    except Exception as e:
        print(f"FAIL: {e}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test LangGraph Single Agent runtime directly")
    parser.add_argument("prompt", nargs="?", default=None, help="Prompt to send (defaults to tool listing)")
    args = parser.parse_args()

    success = test_langgraph_single_agent_runtime(args.prompt)
    sys.exit(0 if success else 1)
