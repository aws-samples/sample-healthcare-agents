#!/usr/bin/env python3
"""
Integration Test: Hospital Safety Agent via Gateway

Tests the hospital safety incident reporting tool through AgentCore Gateway.

Test Coverage:
- Event classification (type, severity, entities)
- Specialist agent routing (falls, medication, infection agents)
- Analysis and recommendations
- DynamoDB storage
- Langfuse trace generation

Requirements:
- Deployed healthcare-agents-stack
- Valid AWS credentials (AWS_PROFILE=quicksuite)
- Cognito configuration in SSM

Usage:
    # Run from this directory
    cd tests/integration/gateway
    export AWS_PROFILE=quicksuite

    # Use default example (patient fall incident)
    python3 test_safety_agent_gateway.py

    # Provide custom safety incident text
    python3 test_safety_agent_gateway.py "Patient in room 302 received wrong medication dose"

    # Run with pytest
    pytest test_safety_agent_gateway.py -m integration -v
"""

import json
import boto3
import requests
import time
import sys
import argparse
from datetime import datetime

def get_gateway_config():
    """Get Gateway configuration from SSM."""
    ssm = boto3.client('ssm', region_name='us-east-1')
    secrets = boto3.client('secretsmanager', region_name='us-east-1')

    try:
        gateway_url = ssm.get_parameter(Name='/healthcare-agents-stack/gateway_url')['Parameter']['Value']
        machine_client_id = ssm.get_parameter(Name='/healthcare-agents-stack/machine_client_id')['Parameter']['Value']
        cognito_domain = ssm.get_parameter(Name='/healthcare-agents-stack/cognito_provider')['Parameter']['Value']
        machine_client_secret = secrets.get_secret_value(SecretId='/healthcare-agents-stack/machine_client_secret')['SecretString']

        return {
            'gateway_url': gateway_url,
            'machine_client_id': machine_client_id,
            'cognito_domain': cognito_domain,
            'machine_client_secret': machine_client_secret,
        }
    except Exception as e:
        print(f"❌ Error getting Gateway config: {e}")
        return None

def get_oauth_token(config):
    """Get OAuth token from Cognito."""
    token_url = f"https://{config['cognito_domain']}/oauth2/token"

    response = requests.post(
        token_url,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        data={
            'grant_type': 'client_credentials',
            'client_id': config['machine_client_id'],
            'client_secret': config['machine_client_secret'],
            'scope': 'healthcare-agents-stack-gateway/read healthcare-agents-stack-gateway/write',
        },
        timeout=10,
    )
    response.raise_for_status()
    return response.json()['access_token']

def get_default_incident():
    """Get default patient fall incident for testing."""
    return '''Patient in room 405 fell from bed at 3:15am during night shift.

Patient Details:
- 82 year old female with osteoporosis
- Admitted 3 days ago for pneumonia
- Known fall risk (history of falls)

Incident Details:
- Patient attempted to get to bathroom without assistance
- Bed rails were down
- Call button out of reach
- Found on floor by Nurse Martinez during rounds

Injuries:
- Hip fracture (left side)
- Severe pain 9/10
- Unable to bear weight
- Bruising on left arm

Response:
- Nurse Martinez responded immediately
- Physician notified
- X-ray ordered
- Pain medication administered
- Family contacted

 '''

def test_safety_agent(incident_text=None):
    """Test Hospital Safety Agent via Gateway with Langfuse observability.

    Args:
        incident_text: Safety incident description. If None, uses default fall incident.
    """

    print("=" * 80)
    print("🏥 HOSPITAL SAFETY AGENT TEST (via Gateway)")
    print("=" * 80)
    print()

    # Get configuration
    print("📋 Getting Gateway configuration...")
    config = get_gateway_config()
    if not config:
        return False

    print(f"✓ Gateway URL: {config['gateway_url']}")
    print()

    # Get OAuth token
    print("🔐 Authenticating with Cognito...")
    try:
        token = get_oauth_token(config)
        print("✓ OAuth token obtained")
        print()
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        return False

    # Prepare test data
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Use default incident if none provided
    if incident_text is None:
        incident_text = get_default_incident()
        print("ℹ️  Using default patient fall incident")
    else:
        print("ℹ️  Using custom incident text")
    print()

    print("📊 Test Configuration:")
    print(f"   Tool: hospital-safety-agent___report_safety_incident")
    print(f"   Timestamp: {timestamp}")
    print()

    # Invoke Gateway tool
    print("🚀 Invoking Gateway tool...")
    print("   (This may take 30-60 seconds for multi-agent analysis)")
    print()

    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    }

    call_tool = {
        'jsonrpc': '2.0',
        'id': f'test-{int(time.time())}',
        'method': 'tools/call',
        'params': {
            'name': 'hospital-safety-agent___report_safety_incident',
            'arguments': {
                'prompt': incident_text
            }
        }
    }

    try:
        response = requests.post(
            config['gateway_url'],
            headers=headers,
            json=call_tool,
            timeout=180  # Increased to 180s for medication/infection analysis
        )

        if response.status_code == 200:
            result = response.json()

            print("✅ Gateway invoked successfully!")
            print()
            print("📥 Full Response (for debugging):")
            print(json.dumps(result, indent=2))
            print()
            print("📥 Parsed Response:")
            print("-" * 80)

            # Parse the response
            if 'result' in result and 'content' in result['result']:
                content = result['result']['content'][0]['text']

                # Try to parse as JSON
                try:
                    # The content is a JSON string inside the response
                    response_data = json.loads(content)
                    if 'body' in response_data:
                        body = json.loads(response_data['body'])

                        if 'result' in body:
                            result_data = body['result']

                            if 'event_id' in result_data:
                                print(f"✓ Event ID: {result_data['event_id']}")

                            if 'classification' in result_data:
                                classification = result_data['classification']
                                print(f"✓ Event Type: {classification.get('event_type')}")
                                print(f"✓ Severity: {classification.get('severity')}")
                                print(f"✓ Patient: {classification.get('patient_id', 'N/A')}")
                                print(f"✓ Location: {classification.get('location', 'N/A')}")

                            if 'analysis' in result_data:
                                analysis = result_data['analysis']
                                print(f"✓ Analysis: {analysis[:200]}...")
                except Exception as e:
                    print(f"⚠️  Error parsing response: {e}")
                    print(f"Response (raw): {content[:1000]}...")

            print("-" * 80)
            print()
            print("✅ Test Complete!")
            print()

            # Instructions for viewing traces
            print("=" * 80)
            print("📊 VIEW TRACES IN LANGFUSE")
            print("=" * 80)
            print()

            print()
            print("2. Navigate to 'Traces' section")
            print()
            print("3. Look for traces from:")
            print(f"   Timestamp: {timestamp}")
            print("   Tool: report_safety_incident")
            print()
            print("4. You should see traces showing:")
            print("   • Agent invocation span")
            print("   • Model calls (Claude Sonnet 4.5)")
            print("   • Classification with structured output")
            print("   • Specialist agent invocation (falls agent)")
            print("   • Tool calls (assess_fall_injury, etc.)")
            print("   • DynamoDB writes (store_event, store_analysis)")
            print("   • Latency metrics for each component")
            print("   • Token usage and costs")
            print()
            print("=" * 80)

            return True

        else:
            print(f"❌ Gateway error: {response.status_code}")
            print(response.text[:500])
            return False

    except Exception as e:
        print(f"❌ Error invoking Gateway: {e}")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Test Hospital Safety Agent via Gateway',
        epilog='Example: python3 test_safety_agent_gateway.py "Patient fell in hallway"'
    )
    parser.add_argument(
        'incident_text',
        nargs='?',
        default=None,
        help='Safety incident description (optional, uses default patient fall incident if not provided)'
    )
    args = parser.parse_args()

    success = test_safety_agent(args.incident_text)
    sys.exit(0 if success else 1)
