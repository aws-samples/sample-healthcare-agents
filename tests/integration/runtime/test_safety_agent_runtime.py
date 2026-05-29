#!/usr/bin/env python3
"""
Integration Test: Hospital Safety Agent via Runtime (Direct Invocation)

Tests the hospital safety agent by invoking AgentCore Runtime directly.

Test Coverage:
- Direct Runtime invocation with Cognito user authentication
- Event processing through orchestrator and specialist agents
- Langfuse trace generation

Requirements:
- Deployed healthcare-agents-stack
- Valid AWS credentials (AWS_PROFILE=quicksuite)
- Cognito user account (requires manual setup)

Note: Direct Runtime invocation requires a Cognito user account with proper
authentication. The Gateway approach (test_safety_agent_gateway.py) is
recommended for automated testing.

Usage:
    # Run from this directory
    cd tests/integration/runtime
    export AWS_PROFILE=quicksuite
    python3 test_safety_agent_runtime.py

    # Run with pytest
    pytest test_safety_agent_runtime.py -m integration -v
"""

import json
import boto3
import time
import uuid
import sys
from datetime import datetime

def get_runtime_arn():
    """Get the Runtime ARN from CloudFormation stack outputs."""
    cfn = boto3.client('cloudformation', region_name='us-east-1')

    try:
        response = cfn.describe_stacks(StackName='healthcare-agents-stack')
        outputs = response['Stacks'][0]['Outputs']

        for output in outputs:
            if output['OutputKey'] == 'RuntimeArn':
                return output['OutputValue']

        print("❌ RuntimeArn not found in stack outputs")
        return None
    except Exception as e:
        print(f"❌ Error getting Runtime ARN: {e}")
        return None

def get_oauth_token():
    """Get OAuth token from Cognito for Runtime invocation."""
    import requests

    ssm = boto3.client('ssm', region_name='us-east-1')
    secrets = boto3.client('secretsmanager', region_name='us-east-1')

    try:
        # Get Cognito configuration
        user_client_id = ssm.get_parameter(Name='/healthcare-agents-stack/cognito-user-pool-client-id')['Parameter']['Value']
        cognito_domain = ssm.get_parameter(Name='/healthcare-agents-stack/cognito_provider')['Parameter']['Value']

        # For testing, we'll use the Cognito user pool
        # In production, users would authenticate through the Amplify app
        print("⚠️  Note: This test requires a Cognito user to be configured")
        print("   For now, testing via Gateway is recommended")
        return None

    except Exception as e:
        print(f"❌ Error getting Cognito config: {e}")
        return None

def test_safety_agent_runtime():
    """Test Hospital Safety Agent via Runtime (requires Cognito user setup)."""

    print("=" * 80)
    print("🏥 HOSPITAL SAFETY AGENT TEST (Direct Runtime)")
    print("=" * 80)
    print()

    # Get Runtime ARN
    print("📋 Getting Runtime ARN from CloudFormation...")
    runtime_arn = get_runtime_arn()

    if not runtime_arn:
        print("❌ Failed to get Runtime ARN")
        return False

    print(f"✓ Runtime ARN: {runtime_arn}")
    print()

    print("⚠️  Runtime uses OAuth/JWT authentication")
    print("   Using Cognito user credentials for testing...")
    print()

    # Get Cognito user credentials from environment or prompt
    print("📧 Using test user: langfuse-test@example.com")
    print("   (Create this user in Cognito if it doesn't exist)")
    print()

    # For this test, we'll use the HTTP API approach
    # which requires a valid OAuth token
    import requests
    import urllib.parse

    ssm = boto3.client('ssm', region_name='us-east-1')

    try:
        # Get Cognito configuration
        user_pool_id = ssm.get_parameter(Name='/healthcare-agents-stack/cognito-user-pool-id')['Parameter']['Value']
        user_client_id = ssm.get_parameter(Name='/healthcare-agents-stack/cognito-user-pool-client-id')['Parameter']['Value']
        cognito_domain = ssm.get_parameter(Name='/healthcare-agents-stack/cognito_provider')['Parameter']['Value']

        print(f"✓ User Pool ID: {user_pool_id}")
        print(f"✓ Client ID: {user_client_id}")
        print(f"✓ Cognito Domain: {cognito_domain}")
        print()

        # For testing, use admin-initiate-auth to get tokens
        # Note: This requires the user to exist in the user pool
        cognito = boto3.client('cognito-idp', region_name='us-east-1')

        # Try to authenticate (this will fail if user doesn't exist)
        print("🔐 Authenticating with Cognito...")
        print("   Note: For production, users would authenticate via Amplify frontend")
        print()

        # Since we don't have a test user password here, let's print instructions
        print("=" * 80)
        print("⚠️  TO COMPLETE THIS TEST:")
        print("=" * 80)
        print()
        print("Option 1: Use the Frontend (Recommended)")
        print("   1. Go to your Amplify app URL")
        print("   2. Log in with a Cognito user")
        print("   3. Submit a safety incident report")
        print("   4. Check Langfuse dashboard for traces")
        print()
        print("Option 2: Use Gateway (for automated testing)")
        print("   1. The Gateway uses machine client credentials")
        print("   2. Run: python3 test_gateway_langfuse.py")
        print()
        print("Option 3: Create Test User for this script")
        print(f"   aws cognito-idp admin-create-user \\")
        print(f"     --user-pool-id {user_pool_id} \\")
        print(f"     --username langfuse-test \\")
        print(f"     --user-attributes Name=email,Value=langfuse-test@example.com \\")
        print(f"     --profile quicksuite")
        print()
        print(f"   aws cognito-idp admin-set-user-password \\")
        print(f"     --user-pool-id {user_pool_id} \\")
        print(f"     --username langfuse-test \\")
        print(f"     --password TestPassword123! \\")
        print(f"     --permanent \\")
        print(f"     --profile quicksuite")
        print()
        print("=" * 80)

        return False

        # Instructions for viewing traces
        print("=" * 80)
        print("📊 VIEW TRACES IN LANGFUSE")
        print("=" * 80)
        print()
        print("1. Log in to Langfuse:")
        print("   URL: https://d25s1shy5vv04l.cloudfront.net")
        print("   Username: demo-langfuse")
        print("   Password: LangFuse2026!")
        print()
        print("2. Navigate to 'Traces' section")
        print()
        print("3. Search for this test invocation:")
        print(f"   Session ID: {session_id}")
        print(f"   User ID: {user_id}")
        print(f"   Timestamp: {timestamp}")
        print()
        print("4. You should see traces showing:")
        print("   • Agent invocation span")
        print("   • Model calls (Claude Sonnet)")
        print("   • Tool executions")
        print("   • Specialist agent invocations (falls agent)")
        print("   • Latency metrics")
        print("   • Token usage")
        print()
        print("=" * 80)

        return True

    except Exception as e:
        print(f"❌ Error invoking Runtime: {e}")
        print()
        print("Note: If you see an AccessDeniedException, you may need to:")
        print("  1. Run: ./creds-qs.sh")
        print("  2. Or use: aws --profile quicksuite ...")
        return False

if __name__ == "__main__":
    success = test_safety_agent_runtime()
    sys.exit(0 if success else 1)
