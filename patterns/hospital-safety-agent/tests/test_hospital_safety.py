#!/usr/bin/env python3
"""
Test script for Hospital Safety Agent

Invokes the AgentCore Runtime directly with sample safety events.
"""

import json
import boto3
import os
import requests
from pathlib import Path
from dotenv import load_dotenv

# Load credentials from .env file
env_path = Path(__file__).parent.parent.parent.parent / "infra-cdk" / ".env"
if env_path.exists():
    load_dotenv(env_path)
    print("✓ Loaded credentials from .env file")
else:
    print("⚠ Warning: .env file not found, using environment variables")

# Initialize AWS clients
cloudformation = boto3.client("cloudformation")
bedrock_agentcore = boto3.client("bedrock-agentcore")
dynamodb = boto3.resource("dynamodb")


def get_cognito_token():
    """
    Get Cognito JWT token using credentials from .env file.

    Returns:
        str: JWT access token
    """
    # Get Cognito configuration from environment (try multiple naming conventions)
    user_pool_id = os.environ.get("COGNITO_USER_POOL_ID") or os.environ.get("COGNITOUSERPOOLID")
    client_id = os.environ.get("COGNITO_CLIENT_ID") or os.environ.get("COGNITOCLIENTID")
    username = os.environ.get("TEST_USER_USERNAME") or os.environ.get("TEST_USERNAME") or os.environ.get("TEST_USER_EMAIL")
    password = os.environ.get("TEST_USER_PASSWORD") or os.environ.get("TEST_PASSWORD")

    if not all([user_pool_id, client_id, username, password]):
        print(f"\nFound variables:")
        print(f"  user_pool_id: {user_pool_id}")
        print(f"  client_id: {client_id}")
        print(f"  username: {username}")
        print(f"  password: {'***' if password else None}")
        raise ValueError(
            "Missing required Cognito credentials in .env file. "
            "Need: COGNITO_USER_POOL_ID (or COGNITOUSERPOOLID), COGNITO_CLIENT_ID (or COGNITOCLIENTID), "
            "TEST_USER_USERNAME (or TEST_USERNAME), TEST_USER_PASSWORD (or TEST_PASSWORD)"
        )

    # Initialize Cognito client
    cognito = boto3.client("cognito-idp")

    try:
        # Initiate auth with username and password
        response = cognito.initiate_auth(
            ClientId=client_id,
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={
                "USERNAME": username,
                "PASSWORD": password,
            },
        )

        access_token = response["AuthenticationResult"]["AccessToken"]

        print(f"✓ Successfully authenticated as {username}")
        # Return access token (has client_id claim required by AgentCore)
        return access_token

    except Exception as e:
        raise RuntimeError(f"Failed to get Cognito token: {e}")


def get_runtime_arn():
    """Get the Runtime ARN from CloudFormation stack outputs."""
    response = cloudformation.describe_stacks(StackName="healthcare-agents-stack")
    outputs = response["Stacks"][0]["Outputs"]

    for output in outputs:
        if output["OutputKey"] == "RuntimeArn":
            return output["OutputValue"]

    raise ValueError("RuntimeArn not found in stack outputs")


def invoke_safety_agent(event_text: str, user_id: str = "test-user", jwt_token: str = None):
    """
    Invoke the Hospital Safety Agent with a safety event.

    Args:
        event_text: Description of the safety event
        user_id: User ID for tracking
        jwt_token: JWT token for authentication (if None, will get new token)

    Returns:
        Response from the agent
    """
    # Get JWT token if not provided
    if jwt_token is None:
        jwt_token = get_cognito_token()

    import uuid

    runtime_arn = get_runtime_arn()
    # Generate session ID with at least 33 characters (use UUID)
    session_id = f"test-session-{uuid.uuid4()}"

    # Extract region from ARN
    region = runtime_arn.split(":")[3]

    # URL encode the agent ARN
    import urllib.parse
    escaped_agent_arn = urllib.parse.quote(runtime_arn, safe='')

    # Create payload (send directly as JSON, not base64 encoded)
    payload = {
        "prompt": event_text,
    }

    print(f"\n{'='*70}")
    print(f"Invoking Hospital Safety Agent")
    print(f"{'='*70}")
    print(f"Runtime: {runtime_arn}")
    print(f"Session: {session_id}")
    print(f"\nEvent Text:\n{event_text}\n")

    # Use HTTP API with JWT authentication (per AWS documentation)
    url = f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{escaped_agent_arn}/invocations?qualifier=DEFAULT"

    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json",
        "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": session_id,
    }

    request_body = payload  # Send payload directly as JSON

    try:
        response = requests.post(url, headers=headers, json=request_body, timeout=300)
        response.raise_for_status()

        # Parse response - AgentCore returns JSON directly
        print("Response:")
        try:
            result = response.json()
            print(json.dumps(result, indent=2))
            return result
        except json.JSONDecodeError:
            # If not JSON, print raw response
            print(f"Raw response text: {response.text[:1000]}")
            return {"raw_response": response.text}

    except requests.exceptions.RequestException as e:
        print(f"\n❌ Error invoking agent: {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"Response status: {e.response.status_code}")
            print(f"Response body: {e.response.text}")
        raise


def view_dynamodb_events(table_name: str, limit: int = 5):
    """View recent events from DynamoDB."""
    table = dynamodb.Table(table_name)

    print(f"\n{'='*70}")
    print(f"Recent Events from {table_name}")
    print(f"{'='*70}\n")

    response = table.scan(Limit=limit)

    if not response.get("Items"):
        print("No events found")
        return

    for item in response["Items"]:
        print(json.dumps(item, indent=2, default=str))
        print("-" * 70)


# Sample safety events for testing
SAMPLE_EVENTS = {
    "medication_error_high": """
A nurse administered 20mg of Lasix instead of the prescribed 10mg to patient
in room 302. Patient experienced no immediate adverse effects but blood pressure
dropped to 90/60. Medication error discovered during shift change.
""".strip(),

    "infection_control": """
Patient in ICU bed 5 developed CAUTI on day 4 of catheterization. Temperature
spiked to 101.5F. Urine culture positive for E. coli. Two other patients in
the ICU also have catheter-associated infections this week.
""".strip(),

    "patient_fall": """
86-year-old patient fell while attempting to reach the bathroom unassisted.
Found on floor by nursing staff. Patient reports hip pain. Call bell was
within reach but patient did not use it. Fall risk assessment was marked as high.
""".strip(),

    "medication_low_severity": """
Morning medications for patient in room 215 were administered 45 minutes late
due to staffing delays. No adverse patient impact noted. Patient was informed of delay.
""".strip(),

    "device_malfunction": """
Infusion pump in room 408 alarmed repeatedly showing occlusion error. Nurse
discovered kinked IV line. Pump was temporarily malfunctioning and not detecting
line pressure correctly. Patient's medication delivery was interrupted for
approximately 30 minutes.
""".strip(),
}


def main():
    """Run all test cases."""
    print("\n" + "="*70)
    print("Hospital Safety Agent Test Suite")
    print("="*70)

    # Get JWT token once for all tests
    try:
        jwt_token = get_cognito_token()
    except Exception as e:
        print(f"\n❌ Failed to authenticate: {e}")
        print("\nPlease ensure:")
        print("1. .env file exists in the project root")
        print("2. Contains: COGNITO_USER_POOL_ID, COGNITO_CLIENT_ID, TEST_USER_USERNAME, TEST_USER_PASSWORD")
        print("3. Test user exists in Cognito User Pool")
        return

    # Test 1: Medication Error (High Severity)
    print("\n\n### TEST 1: Medication Error (High Severity) ###")
    invoke_safety_agent(SAMPLE_EVENTS["medication_error_high"], jwt_token=jwt_token)

    # Test 2: Infection Control Event
    print("\n\n### TEST 2: Healthcare-Associated Infection ###")
    invoke_safety_agent(SAMPLE_EVENTS["infection_control"], jwt_token=jwt_token)

    # Test 3: Patient Fall
    print("\n\n### TEST 3: Patient Fall with Injury ###")
    invoke_safety_agent(SAMPLE_EVENTS["patient_fall"], jwt_token=jwt_token)

    # Test 4: Low Severity Event
    print("\n\n### TEST 4: Minor Medication Timing Issue ###")
    invoke_safety_agent(SAMPLE_EVENTS["medication_low_severity"], jwt_token=jwt_token)

    # Test 5: Device Malfunction
    print("\n\n### TEST 5: Device Malfunction ###")
    invoke_safety_agent(SAMPLE_EVENTS["device_malfunction"], jwt_token=jwt_token)

    # View stored events
    print("\n\n### Viewing Stored Events ###")
    view_dynamodb_events("healthcare-agents-stack-safety-events")

    print("\n\n### Viewing Stored Analysis ###")
    view_dynamodb_events("healthcare-agents-stack-safety-analysis")

    print("\n" + "="*70)
    print("Testing Complete!")
    print("="*70)
    print("\nNext Steps:")
    print("1. Check your email (safety@example.com) for SNS alerts")
    print("2. View CloudWatch Logs: /aws/bedrock-agentcore/runtime/FAST_stack_StrandsAgent")
    print("3. Query DynamoDB tables for detailed analysis results")
    print()


if __name__ == "__main__":
    main()
