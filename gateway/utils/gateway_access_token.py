"""
Access token management for AgentCore Gateway authentication.
This module handles OAuth2 client credentials flow to authenticate with Cognito,
which is required for agents to access tools through the AgentCore Gateway.
"""

import base64
import os

import boto3
import requests


def get_ssm_parameter(parameter_name: str) -> str:
    """
    Fetch parameter from SSM Parameter Store.

    SSM Parameter Store securely stores configuration values like client IDs and secrets.
    This function retrieves these values at runtime instead of hardcoding them.
    """
    region = os.environ.get(
        "AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
    )
    ssm = boto3.client("ssm", region_name=region)
    response = ssm.get_parameter(Name=parameter_name, WithDecryption=True)
    return response["Parameter"]["Value"]


def get_secret(secret_name: str) -> str:
    """
    Fetch secret from AWS Secrets Manager.

    Secrets Manager is designed for storing sensitive information like passwords,
    API keys, and other secrets with automatic rotation capabilities.

    Args:
        secret_name: The name or ARN of the secret to retrieve

    Returns:
        The secret value as a string

    Raises:
        ValueError: If the secret is not found or cannot be accessed
        RuntimeError: If there's an AWS service error
    """
    region = os.environ.get(
        "AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
    )
    secrets_client = boto3.client("secretsmanager", region_name=region)

    try:
        response = secrets_client.get_secret_value(SecretId=secret_name)
        return response["SecretString"]
    except secrets_client.exceptions.ResourceNotFoundException:
        raise ValueError(f"Secret not found: {secret_name}")
    except secrets_client.exceptions.InvalidParameterException:
        raise ValueError(f"Invalid secret parameter: {secret_name}")
    except secrets_client.exceptions.InvalidRequestException:
        raise ValueError(f"Invalid request for secret: {secret_name}")
    except secrets_client.exceptions.DecryptionFailureException:
        raise RuntimeError(f"Failed to decrypt secret: {secret_name}")
    except secrets_client.exceptions.InternalServiceErrorException:
        raise RuntimeError(
            f"AWS Secrets Manager service error for secret: {secret_name}"
        )
    except Exception as e:
        raise RuntimeError(
            f"Unexpected error retrieving secret {secret_name}: {str(e)}"
        )


def get_gateway_access_token() -> str:
    """
    Get OAuth2 access token using client credentials flow.

    This implements machine-to-machine authentication where the agent acts as a client
    that needs to authenticate with Cognito to get permission to call the Gateway.
    The client credentials flow is used for server-to-server communication without user login.

    Returns:
        Valid OAuth2 access token for Gateway authentication
    """
    stack_name = os.environ["STACK_NAME"]
    region = os.environ.get(
        "AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
    )

    print(f"[AUTH] Getting access token for stack: {stack_name}, region: {region}")

    # Get Cognito configuration from SSM and Secrets Manager
    cognito_domain = get_ssm_parameter(f"/{stack_name}/cognito_provider")
    client_id = get_ssm_parameter(f"/{stack_name}/machine_client_id")
    client_secret = get_secret(f"/{stack_name}/machine_client_secret")

    print(f"[AUTH] Cognito domain: {cognito_domain}")
    print(f"[AUTH] Client ID: {client_id[:10]}...")

    # Prepare OAuth2 token request
    token_url = f"https://{cognito_domain}/oauth2/token"

    # Create Basic Auth header
    credentials = f"{client_id}:{client_secret}"
    b64_credentials = base64.b64encode(credentials.encode()).decode()

    headers = {
        "Authorization": f"Basic {b64_credentials}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    data = {
        "grant_type": "client_credentials",
        "scope": f"{stack_name}-api/invoke",
    }

    print(f"[AUTH] Requesting token from: {token_url}")
    print(f"[AUTH] Scopes: {data['scope']}")

    # Request access token
    response = requests.post(token_url, headers=headers, data=data, timeout=30)

    if response.status_code != 200:
        # Do not log response.text — it may contain server-side secrets or
        # partial token material in error envelopes (Threat T11).
        print(f"[AUTH ERROR] Token request failed with HTTP {response.status_code}")
        raise Exception(
            f"Failed to get access token: HTTP {response.status_code}"
        )

    token_data = response.json()
    access_token = token_data.get("access_token")

    if not access_token:
        # Mitigates Threat T11 — do not log the response body, which
        # may include client_id, client_secret hashes, or partial tokens.
        print("[AUTH ERROR] Cognito response missing access_token")
        raise Exception("No access_token in Cognito response")

    # Mitigates Threat T11 — never log even a prefix of the token.
    # Even 20 chars of a JWT can disclose the header (alg / kid) and aid replay
    # attacks if logs are exfiltrated.
    print("[AUTH] Successfully obtained access token")
    return access_token
