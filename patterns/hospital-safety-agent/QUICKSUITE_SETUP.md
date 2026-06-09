# QuickSuite Setup Guide - Hospital Safety Agent

> **⚠️ Security note:** This guide uses placeholder values (e.g. `<YOUR_COGNITO_CLIENT_ID>`). **Never commit real client IDs, client secrets, or stack-specific URLs to version control.** Retrieve these values from your deployed CloudFormation stack outputs or AWS Secrets Manager at runtime, and inject them via environment variables or secret references when configuring QuickSuite.

This guide provides all configuration details for setting up the Hospital Safety Agent MCP tool in QuickSuite.

## Quick Reference

**MCP Endpoint:**
```
https://bedrock-agentcore.us-east-1.amazonaws.com/gateways/{GATEWAY_ID}/mcp
```

**OAuth2 Token URL:**
```
https://<YOUR-STACK-NAME>-<AWS-ACCOUNT-ID>-<REGION>.auth.us-east-1.amazoncognito.com/oauth2/token
```

**Client Credentials:**
- Client ID: *(from Secrets Manager)*
- Client Secret: *(from Secrets Manager)*
- Grant Type: `client_credentials`
- Scope: (optional - auto-granted)

**Tool Name:**
```
analyze_safety_event
```

**Get Gateway ID:**
```bash
aws cloudformation describe-stacks \
  --stack-name healthcare-agents-stack \
  --region us-east-1 \
  --query 'Stacks[0].Outputs[?OutputKey==`GatewayId`].OutputValue' \
  --output text
```

**Or use the helper script:**
```bash
# Bash
cd patterns/hospital-safety-agent/tests
./get_mcp_url.sh

# Python
./get_mcp_url.py
```

---

## Table of Contents
- [Quick Reference](#quick-reference)
- [Authentication Configuration](#authentication-configuration)
- [Tool Configuration](#tool-configuration)
- [Quick Test with curl](#quick-test-with-curl)
- [Expected Response](#expected-response)

## Authentication Configuration

### OAuth2 Settings

Configure the OAuth2 authentication in QuickSuite with these values:

```
Authentication Type: OAuth 2.0
Grant Type: Client Credentials
Token URL: https://<YOUR-STACK-NAME>-<AWS-ACCOUNT-ID>-<REGION>.auth.us-east-1.amazoncognito.com/oauth2/token
Client ID: (from Secrets Manager)
Client Secret: (from Secrets Manager)
Scope: (optional - leave blank, Cognito auto-grants configured scopes)
```

**Notes:**
- The `scope` parameter is optional. Cognito automatically includes all configured scopes in the JWT token.
- If you want to be explicit, use: `healthcare-agents-stack-gateway/read healthcare-agents-stack-gateway/write`
- Tokens expire after 3600 seconds (1 hour)

## Tool Configuration

### MCP URL

The complete MCP endpoint URL for QuickSuite:

```
MCP URL: https://bedrock-agentcore.us-east-1.amazonaws.com/gateways/{GATEWAY_ID}/mcp
```

**Get your Gateway ID:**
```bash
aws cloudformation describe-stacks \
  --stack-name healthcare-agents-stack \
  --region us-east-1 \
  --query 'Stacks[0].Outputs[?OutputKey==`GatewayId`].OutputValue' \
  --output text
```

**Example MCP URL** (replace `{GATEWAY_ID}` with your actual Gateway ID):
```
https://bedrock-agentcore.us-east-1.amazonaws.com/gateways/abc123xyz/mcp
```

### MCP Server Configuration

```
Server Type: MCP Gateway
Protocol: HTTP/HTTPS
Method: POST
MCP URL: https://bedrock-agentcore.us-east-1.amazonaws.com/gateways/{GATEWAY_ID}/mcp
Authentication: OAuth 2.0 Bearer Token (configured above)
Region: us-east-1
```

**Configuration Steps:**
1. Get your Gateway ID using the AWS CLI command above (or use `get_mcp_url.sh`/`get_mcp_url.py` helper scripts)
2. Replace `{GATEWAY_ID}` in the MCP URL with your actual Gateway ID
3. Configure OAuth2 authentication (see Authentication Configuration section)
4. Use the complete MCP URL as your server endpoint in QuickSuite

**Helper Scripts:**
- `tests/get_mcp_url.sh` - Bash script to get the complete MCP URL
- `tests/get_mcp_url.py` - Python script to get the complete MCP URL

### Tool Details

```yaml
Tool Name: analyze_safety_event
Protocol: MCP (Model Context Protocol)
Method: POST
Target: hospital-safety-agent
```

### Tool Description

**Short Description:**
```
Analyzes healthcare safety events using multi-agent AI to identify root causes, recommend corrective actions, and generate regulatory reports.
```

**Full Description:**
```
The Hospital Safety Agent analyzes patient safety events in healthcare settings using a multi-agent AI system. It processes incident descriptions and provides:

• Root cause analysis using industry frameworks (5 Whys, Fishbone, FMEA)
• Immediate and long-term corrective action recommendations
• Risk severity assessment and prioritization
• Regulatory compliance guidance (Joint Commission, CMS, state requirements)
• Complete incident documentation for reporting

Supports all major safety event types:
- Medication errors (wrong drug, dose, patient, route, time)
- Patient falls and injury events
- Healthcare-associated infections (HAIs)
- Medical device malfunctions
- Surgical/procedural complications
- Communication failures
- Security incidents

Input: Detailed description of the safety event including what happened, patient impact, location, staff involved, and immediate actions taken.

Output: Structured analysis with root causes, corrective actions, risk assessment, regulatory guidance, and full incident report.

Response time: 20-30 seconds for complete analysis.
```

### Input Schema

```json
{
  "type": "object",
  "properties": {
    "prompt": {
      "type": "string",
      "description": "Description of the safety event including: what happened, patient impact, location, staff involved, immediate actions taken"
    }
  },
  "required": ["prompt"]
}
```

### Tags/Categories

```
healthcare, patient-safety, risk-management, compliance, incident-analysis, root-cause-analysis, regulatory-reporting
```

## Quick Test with curl

### Step 1: Get OAuth2 Token

```bash
# Get access token
TOKEN_RESPONSE=$(curl -s -X POST \
  "https://<YOUR-STACK-NAME>-<AWS-ACCOUNT-ID>-<REGION>.auth.us-east-1.amazoncognito.com/oauth2/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials" \
  -d "client_id=$COGNITO_CLIENT_ID" \
  -d "client_secret=$COGNITO_CLIENT_SECRET")

# Extract access token
ACCESS_TOKEN=$(echo $TOKEN_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

echo "Access Token: ${ACCESS_TOKEN:0:50}..."
```

### Step 2: Get Gateway ID

```bash
# Get Gateway ID from CloudFormation
GATEWAY_ID=$(aws cloudformation describe-stacks \
  --stack-name healthcare-agents-stack \
  --query 'Stacks[0].Outputs[?OutputKey==`GatewayId`].OutputValue' \
  --output text)

echo "Gateway ID: $GATEWAY_ID"
```

### Step 3: Invoke MCP Tool

```bash
# Invoke the hospital-safety-agent tool
curl -X POST \
  "https://bedrock-agentcore.us-east-1.amazonaws.com/gateways/$GATEWAY_ID/mcp" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "method": "tools/call",
    "params": {
      "name": "analyze_safety_event",
      "arguments": {
        "prompt": "A 72-year-old patient fell while attempting to use the bathroom without assistance at 2:30 AM. The patient sustained a hip fracture. The call button was out of reach and the bed alarm was not activated. Patient had been assessed as high fall risk. Immediate actions: patient stabilized, physician notified, incident report initiated."
      }
    }
  }'
```

### All-in-One Test Script

```bash
#!/bin/bash

# Hospital Safety Agent - Quick Test Script

echo "=== Step 1: Getting OAuth2 Token ==="
TOKEN_RESPONSE=$(curl -s -X POST \
  "https://<YOUR-STACK-NAME>-<AWS-ACCOUNT-ID>-<REGION>.auth.us-east-1.amazoncognito.com/oauth2/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials" \
  -d "client_id=$COGNITO_CLIENT_ID" \
  -d "client_secret=$COGNITO_CLIENT_SECRET")

ACCESS_TOKEN=$(echo $TOKEN_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")
echo "✓ Token acquired: ${ACCESS_TOKEN:0:50}..."

echo -e "\n=== Step 2: Getting Gateway ID ==="
GATEWAY_ID=$(aws cloudformation describe-stacks \
  --stack-name healthcare-agents-stack \
  --query 'Stacks[0].Outputs[?OutputKey==`GatewayId`].OutputValue' \
  --output text)
echo "✓ Gateway ID: $GATEWAY_ID"

echo -e "\n=== Step 3: Invoking Hospital Safety Agent ==="
echo "This may take 20-30 seconds..."

curl -X POST \
  "https://bedrock-agentcore.us-east-1.amazonaws.com/gateways/$GATEWAY_ID/mcp" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "method": "tools/call",
    "params": {
      "name": "analyze_safety_event",
      "arguments": {
        "prompt": "A 72-year-old patient fell while attempting to use the bathroom without assistance at 2:30 AM. The patient sustained a hip fracture. The call button was out of reach and the bed alarm was not activated. Patient had been assessed as high fall risk. Immediate actions: patient stabilized, physician notified, incident report initiated."
      }
    }
  }'

echo -e "\n\n✓ Test complete"
```

### Python Test Script

```python
#!/usr/bin/env python3
"""Quick test script for Hospital Safety Agent via QuickSuite/Gateway."""

import requests
import json
import os

# Configuration
TOKEN_URL = "https://<YOUR-STACK-NAME>-<AWS-ACCOUNT-ID>-<REGION>.auth.us-east-1.amazoncognito.com/oauth2/token"
CLIENT_ID = os.environ["COGNITO_CLIENT_ID"]
CLIENT_SECRET = os.environ["COGNITO_CLIENT_SECRET"]
REGION = "us-east-1"

def get_token():
    """Get OAuth2 token."""
    print("=== Step 1: Getting OAuth2 Token ===")
    response = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        },
        timeout=10,
    )
    response.raise_for_status()
    token = response.json()["access_token"]
    print(f"✓ Token acquired: {token[:50]}...")
    return token

def get_gateway_id():
    """Get Gateway ID from CloudFormation."""
    print("\n=== Step 2: Getting Gateway ID ===")
    import boto3
    cfn = boto3.client("cloudformation", region_name=REGION)
    response = cfn.describe_stacks(StackName="healthcare-agents-stack")
    outputs = response["Stacks"][0]["Outputs"]
    gateway_id = next(o["OutputValue"] for o in outputs if o["OutputKey"] == "GatewayId")
    print(f"✓ Gateway ID: {gateway_id}")
    return gateway_id

def invoke_tool(token, gateway_id):
    """Invoke the Hospital Safety Agent tool."""
    print("\n=== Step 3: Invoking Hospital Safety Agent ===")
    print("This may take 20-30 seconds...")

    url = f"https://bedrock-agentcore.{REGION}.amazonaws.com/gateways/{gateway_id}/mcp"

    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={
            "method": "tools/call",
            "params": {
                "name": "analyze_safety_event",
                "arguments": {
                    "prompt": "A 72-year-old patient fell while attempting to use the bathroom without assistance at 2:30 AM. The patient sustained a hip fracture. The call button was out of reach and the bed alarm was not activated. Patient had been assessed as high fall risk. Immediate actions: patient stabilized, physician notified, incident report initiated."
                }
            }
        },
        timeout=60,
    )
    response.raise_for_status()

    result = response.json()
    print("\n✓ Response received:")
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    token = get_token()
    gateway_id = get_gateway_id()
    invoke_tool(token, gateway_id)
    print("\n✓ Test complete")
```

## Expected Response

The tool returns a structured JSON response with the following format:

```json
{
  "result": {
    "analysis": {
      "incident_classification": "Patient Fall with Injury",
      "severity": "High",
      "root_causes": [
        "Call button out of reach - environmental factor",
        "Bed alarm not activated - process failure",
        "Patient attempted bathroom without assistance - behavioral factor"
      ],
      "contributing_factors": [
        "Time of incident (2:30 AM) - reduced staffing",
        "High fall risk not adequately addressed",
        "Communication gap in fall prevention protocol"
      ]
    },
    "corrective_actions": {
      "immediate": [
        "Ensure all high fall risk patients have call buttons within reach",
        "Verify bed alarm activation for all high-risk patients",
        "Increase rounding frequency during night shift"
      ],
      "long_term": [
        "Implement automated bed alarm system",
        "Enhanced fall prevention training",
        "Review and update fall prevention protocols"
      ]
    },
    "regulatory_guidance": {
      "reporting_required": true,
      "agencies": ["State Department of Health", "CMS"],
      "timeline": "Within 24 hours",
      "documentation": "Complete incident report with witness statements"
    },
    "risk_assessment": {
      "likelihood": "Medium",
      "severity": "High",
      "overall_risk": "High",
      "priority": "Immediate action required"
    }
  },
  "metadata": {
    "agent": "hospital-safety-agent",
    "version": "1.0"
  }
}
```

### Response Size

- **Typical size**: 100-150 KB
- **Response time**: 20-30 seconds
- **Format**: JSON with structured analysis

## Troubleshooting

### Issue: 401 Unauthorized

**Solution**: Check token expiration. Tokens expire after 1 hour. Get a new token.

```bash
# Check token expiration
echo $TOKEN_RESPONSE | python3 -c "import sys, json; print('Expires in:', json.load(sys.stdin)['expires_in'], 'seconds')"
```

### Issue: 403 Forbidden

**Solution**: Verify Gateway ID is correct and your machine client has permissions.

### Issue: 404 Not Found

**Solution**: Check that the tool name is exactly `analyze_safety_event` and Gateway ID is correct.

### Issue: 500 Internal Server Error

**Solution**: Check CloudWatch logs for Lambda function:
```bash
aws logs tail "/aws/lambda/healthcare-agents-stack-hospital-safety-agent" --follow
```

## Additional Resources

- **MCP Integration Guide**: `infra-cdk/lib/patterns/hospital-safety/MCP_INTEGRATION.md`
- **Agent Code**: `patterns/hospital-safety-agent/`
- **Lambda Wrapper**: `gateway/tools/hospital_safety_agent/safety_agent_lambda.py`
- **Test Scripts**: `patterns/hospital-safety-agent/tests/`

## Security Notes

- **Credentials**: Never commit credentials to version control
- **Token Storage**: Tokens should be stored securely and refreshed before expiration
- **HTTPS Only**: All communications use HTTPS/TLS encryption
- **IAM Permissions**: Lambda uses IAM role, not JWT, to invoke Runtime
- **Audit Logging**: All tool invocations are logged in CloudWatch

---

**Last Updated**: January 2026
**Stack Name**: healthcare-agents-stack
**Region**: us-east-1
**Gateway Version**: AgentCore Gateway v1.0
