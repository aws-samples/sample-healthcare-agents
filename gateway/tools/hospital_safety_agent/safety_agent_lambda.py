#!/usr/bin/env python3
"""
Lambda wrapper for Hospital Safety Agent.

This Lambda function acts as an MCP tool that invokes the Hospital Safety Agent
Runtime via AgentCore API with OAuth2 authentication.
"""

import json
import os
import boto3
import requests
from typing import Dict, Any

# AWS clients
ssm = boto3.client("ssm")
secrets = boto3.client("secretsmanager")

# Cache for credentials and URLs
_cache = {}


def get_cached_value(key: str, fetch_func):
    """Cache values to avoid repeated SSM/Secrets Manager calls."""
    if key not in _cache:
        _cache[key] = fetch_func()
    return _cache[key]


def get_cognito_token() -> str:
    """
    Get OAuth2 token from Cognito using machine client credentials.

    Returns:
        str: JWT access token
    """
    stack_name = os.environ.get("STACK_NAME", "healthcare-agents-stack")

    # Get Cognito configuration from SSM
    machine_client_id = get_cached_value(
        "machine_client_id",
        lambda: ssm.get_parameter(Name=f"/{stack_name}/machine_client_id")["Parameter"]["Value"]
    )

    cognito_domain = get_cached_value(
        "cognito_domain",
        lambda: ssm.get_parameter(Name=f"/{stack_name}/cognito_provider")["Parameter"]["Value"]
    )

    # Get machine client secret from Secrets Manager
    machine_client_secret = get_cached_value(
        "machine_client_secret",
        lambda: secrets.get_secret_value(SecretId=f"/{stack_name}/machine_client_secret")["SecretString"]
    )

    # Get OAuth token
    token_url = f"https://{cognito_domain}/oauth2/token"
    response = requests.post(
        token_url,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "client_credentials",
            "client_id": machine_client_id,
            "client_secret": machine_client_secret,
            "scope": f"{stack_name}-gateway/read {stack_name}-gateway/write",
        },
        timeout=10,
    )
    response.raise_for_status()

    return response.json()["access_token"]


def invoke_safety_agent(prompt: str) -> Dict[str, Any]:
    """
    Invoke the Hospital Safety Agent Runtime.

    Args:
        prompt: Description of the safety event

    Returns:
        dict: Response from the safety agent
    """
    stack_name = os.environ.get("STACK_NAME", "healthcare-agents-stack")
    region = os.environ.get("AWS_REGION", "us-east-1")

    # Get Runtime ARN from SSM
    runtime_arn = get_cached_value(
        "runtime_arn",
        lambda: ssm.get_parameter(Name=f"/{stack_name}/runtime-arn")["Parameter"]["Value"]
    )

    # Get OAuth token
    jwt_token = get_cognito_token()

    # URL encode the Runtime ARN
    import urllib.parse
    escaped_runtime_arn = urllib.parse.quote(runtime_arn, safe="")

    # Generate session ID
    import uuid
    session_id = f"lambda-session-{uuid.uuid4()}"

    # Invoke Runtime via HTTP API
    url = f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{escaped_runtime_arn}/invocations?qualifier=DEFAULT"

    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json",
        "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": session_id,
    }

    payload = {"prompt": prompt}

    response = requests.post(url, headers=headers, json=payload, timeout=300, stream=True)
    response.raise_for_status()

    # Runtime returns SSE (Server-Sent Events), collect all events
    result = {}
    for line in response.iter_lines():
        if line:
            line_str = line.decode('utf-8')
            if line_str.startswith('data: '):
                data_str = line_str[6:]  # Remove 'data: ' prefix
                try:
                    import json as json_module
                    event_data = json_module.loads(data_str)
                    # Merge all events into result
                    result.update(event_data)
                except (json.JSONDecodeError, ValueError):
                    # Skip invalid JSON lines in SSE stream (expected for keepalives)
                    continue

    return result


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for Hospital Safety Agent MCP tool.

    Args:
        event: Lambda event containing tool invocation request
        context: Lambda context

    Returns:
        dict: Tool response in MCP format
    """
    try:
        # PHI-safe event logging (mitigates Threat T11).
        print(json.dumps({
            "event_summary": {
                "top_level_keys": sorted(event.keys()) if isinstance(event, dict) else [],
                "has_prompt": bool(isinstance(event, dict) and (event.get("prompt") or event.get("event_description"))),
            }
        }))

        # Extract parameters from event
        # Gateway sends tool arguments in the event
        prompt = event.get("prompt") or event.get("event_description", "")

        if not prompt:
            return {
                "statusCode": 400,
                "body": json.dumps({
                    "error": "Missing required parameter: prompt or event_description"
                })
            }

        print(f"Invoking safety agent with prompt: {prompt[:100]}...")

        # Invoke the safety agent
        result = invoke_safety_agent(prompt)

        print(f"Safety agent response received")

        # Return in MCP format
        return {
            "statusCode": 200,
            "body": json.dumps({
                "result": result,
                "metadata": {
                    "agent": "hospital-safety-agent",
                    "version": "1.0"
                }
            })
        }

    except requests.exceptions.HTTPError as e:
        error_msg = f"HTTP error invoking safety agent: {e}"
        print(error_msg)
        if hasattr(e, "response") and e.response is not None:
            print(f"Response status: {e.response.status_code}")
            print(f"Response body: {e.response.text}")

        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": error_msg,
                "details": e.response.text if hasattr(e, "response") else str(e)
            })
        }

    except Exception as e:
        error_msg = f"Error invoking safety agent: {str(e)}"
        print(error_msg)

        return {
            "statusCode": 500,
            "body": json.dumps({"error": error_msg})
        }
