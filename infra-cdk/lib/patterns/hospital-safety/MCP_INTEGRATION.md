# Hospital Safety Agent MCP Integration

## Overview

The Hospital Safety Agent is exposed as an MCP (Model Context Protocol) tool through AgentCore Gateway. This allows external AI agents to use the hospital safety agent as a tool for analyzing and routing healthcare safety events.

## Architecture

```
External Agent
    ↓
AgentCore Gateway (MCP Protocol)
    ↓
Hospital Safety Agent Runtime
    ↓
Multi-Agent System:
    - Orchestrator Agent
    - Medication Error Specialist
    - Patient Fall Specialist
    - Infection Control Specialist
```

## MCP Server Configuration

The MCP Server target is automatically created when deploying with the `hospital-safety-agent` pattern. The configuration is in `backend-stack.ts`:

```typescript
targetConfiguration: {
  mcp: {
    mcpServer: {
      endpoint: this.agentRuntime.agentRuntimeArn,
    },
  },
}
```

### Key Properties

- **Target Name**: `hospital-safety-agent`
- **Protocol**: MCP (Model Context Protocol)
- **Authentication**: Gateway IAM Role (Cognito JWT)
- **Endpoint**: AgentCore Runtime ARN

## Authentication

The Gateway uses Cognito JWT authentication with OAuth2 Client Credentials flow:

1. **Machine Client**: Configured in Cognito User Pool for M2M authentication
2. **Resource Server**: Defines scopes (`read`, `write`) for Gateway access
3. **JWT Token**: External agents must obtain a JWT token from Cognito

### Getting an Access Token

```bash
# Get token from Cognito
curl -X POST \
  https://${COGNITO_DOMAIN}.auth.${REGION}.amazoncognito.com/oauth2/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials" \
  -d "client_id=${MACHINE_CLIENT_ID}" \
  -d "client_secret=${MACHINE_CLIENT_SECRET}" \
  -d "scope=${STACK_NAME}-gateway/read ${STACK_NAME}-gateway/write"
```

The credentials are stored in:
- **Machine Client ID**: SSM Parameter `/${STACK_NAME}/machine_client_id`
- **Machine Client Secret**: Secrets Manager `/${STACK_NAME}/machine_client_secret`
- **Cognito Domain**: SSM Parameter `/${STACK_NAME}/cognito_provider`

## Using the MCP Tool

### Tool Schema

The hospital safety agent accepts a prompt describing a safety event:

```json
{
  "prompt": "Patient in room 401 received 50mg of Metoprolol instead of prescribed 25mg. Patient's heart rate dropped to 48 bpm."
}
```

### MCP Tool Invocation

External agents can invoke the tool through the Gateway:

```python
import boto3
import requests

# Get Gateway URL from SSM
ssm = boto3.client('ssm')
gateway_url = ssm.get_parameter(Name='/healthcare-agents-stack/gateway_url')['Parameter']['Value']

# Get JWT token (see authentication section)
jwt_token = get_cognito_token()

# Invoke the hospital-safety-agent tool
response = requests.post(
    f"{gateway_url}/tools/hospital-safety-agent/invoke",
    headers={
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json",
    },
    json={
        "prompt": "Patient fell while attempting to reach bathroom. Hip pain reported."
    }
)

result = response.json()
```

### Response Format

The agent returns structured analysis and routing information:

```json
{
  "event_type": "patient_fall",
  "severity": "high",
  "routing": {
    "to_physicians": true,
    "to_safety_officers": true
  },
  "analysis": {
    "summary": "High-risk patient fall with injury requiring immediate review",
    "recommendations": ["Assess fall prevention measures", "Review call bell accessibility"]
  }
}
```

## Benefits of MCP Integration

1. **Reusability**: Any AI agent can use the hospital safety agent as a tool
2. **Streaming Preserved**: MCP protocol maintains SSE streaming capabilities
3. **Authentication**: Secure OAuth2 authentication with Cognito
4. **No Lambda Wrapper**: Direct Runtime invocation reduces latency and complexity
5. **Type Safety**: MCP protocol enforces structured input/output

## IAM Permissions

The Gateway IAM role has the following permissions:

```typescript
// Runtime invocation
actions: ["bedrock-agentcore:InvokeRuntime"]
resources: ["arn:aws:bedrock-agentcore:${region}:${account}:runtime/*"]

// Bedrock model access (for underlying LLM calls)
actions: ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]

// Cognito authentication
actions: ["cognito-idp:DescribeUserPoolClient", "cognito-idp:InitiateAuth"]
```

## Deployment

The MCP Server target is automatically created when you deploy with:

```bash
# Deploy with hospital-safety-agent pattern
cdk deploy healthcare-agents-stack

# Outputs will include:
# - GatewayUrl: URL for MCP Gateway
# - SafetyAgentTargetId: ID of the MCP Server target
# - RuntimeArn: ARN of the hospital safety agent
```

## Testing

Test the MCP integration using the test scripts:

```bash
# Test individual events
cd patterns/hospital-safety-agent/tests
python3 test_hospital_safety.py

# Test threshold breach detection
python3 test_threshold_breach.py
```

## Limitations

- **Session Management**: Each invocation creates a new session (stateless)
- **Memory**: Short-term memory (conversation history) is per-session
- **Rate Limits**: Subject to Gateway and Runtime rate limits

## Troubleshooting

### Gateway Returns 401 Unauthorized

- Verify JWT token is valid and not expired
- Check machine client has correct scopes
- Ensure token was obtained with client credentials flow

### Gateway Returns 403 Forbidden

- Verify Gateway IAM role has `bedrock-agentcore:InvokeRuntime` permission
- Check Runtime ARN is correct in target configuration

### Runtime Returns 500 Error

- Check CloudWatch Logs: `/aws/bedrock-agentcore/runtimes/${RUNTIME_NAME}`
- Verify DynamoDB tables exist and have correct permissions
- Ensure SNS topic is configured for alerts

## References

- [AgentCore Gateway Documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore-gateway.html)
- [MCP Protocol Specification](https://spec.modelcontextprotocol.io/)
- [Hospital Safety Agent Pattern](../../../patterns/hospital-safety-agent/)
