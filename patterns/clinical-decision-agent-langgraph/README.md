# Clinical Decision Support Agent (LangGraph + Epic 3LO)

Real-time clinical decision support using LangGraph with Epic FHIR data via 3-Legged OAuth (3LO).

## Overview

This agent helps healthcare providers make safe medication decisions by:

1. **Retrieving patient data** from Epic FHIR (with user authorization via 3LO)
2. **Analyzing drug safety** - interactions, contraindications, allergies
3. **Providing recommendations** - safety ratings, alternatives, clinical guidance

## Architecture

```
Frontend (User) → AgentCore Runtime → LangGraph Agent
                                         ↓
                          ┌──────────────┴───────────────┐
                          ↓                              ↓
              Epic FHIR (Direct)              Gateway (MCP)
              via AgentCore Identity          (HealthLake, Comprehend)
                     ↓
            Epic 3LO User Federation
                     ↓
            Epic FHIR API (with user token)
```

### Why Direct Epic FHIR Calls?

Epic FHIR tools are called **directly** using AgentCore Identity (`@requires_access_token`) instead of through Gateway because:

1. **Gateway OpenAPI OAuth doesn't stream authorization URLs** - When Gateway encounters OAuth 3LO authorization requirement, it returns a generic error instead of the authorization URL needed for user consent
2. **AgentCore Identity provides proper OAuth flow** - The `@requires_access_token` decorator handles authorization URL streaming to the agent, which can pass it to the frontend
3. **Gateway remains for other tools** - HealthLake and Comprehend Medical tools still use Gateway with Gateway IAM role authentication

## Epic 3LO (Three-Legged OAuth) Flow

### First Invocation
1. User sends query to agent
2. Agent calls Epic FHIR tool with `@requires_access_token` decorator
3. AgentCore Identity detects no token, generates authorization URL
4. Authorization URL streamed to agent → frontend
5. Frontend displays authorization URL for user to click
6. User opens URL, logs into Epic, grants permission
7. Epic redirects to frontend `/oauth/callback`
8. Frontend calls `CompleteResourceTokenAuth` API
9. Tokens stored in AgentCore Identity vault
10. Agent retrieves token and calls Epic FHIR API successfully

### Subsequent Invocations
- Token retrieved automatically from AgentCore Identity
- User authorization not required (until token expires)
- Transparent to user experience

## Features

- **LangGraph ReAct Agent**: Tool-calling with streaming responses
- **Memory Integration**: Conversation history with AgentCore Memory
- **Epic FHIR Tools**: Patient data, medications, allergies, lab results
- **User Authorization**: Secure 3LO flow for patient data access
- **Token Management**: Automatic refresh handled by AgentCore Identity

## Input Format

```json
{
  "prompt": "Check if Metformin is safe for patient 8MsEzCJO3BA3",
  "userId": "dr-john-smith",
  "runtimeSessionId": "session-123",
  "patientId": "8MsEzCJO3BA3",
  "medication": "Metformin"
}
```

## Epic FHIR Tools Available

The agent has access to these tools via the Epic FHIR Gateway:

1. **get_patient** - Patient demographics
2. **get_medications** - Current active medications
3. **get_allergies** - Allergy history
4. **get_observations** - Lab results and vitals

All tools use Epic 3LO with `@requires_access_token` decorator.

## Prerequisites

1. **Epic OAuth2 Credential Provider** configured in AgentCore Identity:
   - Name: `EpicFHIRProvider`
   - Provider: CustomOauth2
   - Discovery URL: Epic OIDC endpoint
   - Client ID and Secret from Epic app registration

2. **Epic App Registration** with:
   - SMART Scopes: `user/Patient.read`, `user/MedicationRequest.read`, etc.
   - Redirect URI: AgentCore Identity callback URL
   - Confidential client with client secret

3. **Epic FHIR Gateway** deployed with user federation tools

## Deployment

1. Add to `infra-cdk/config.yaml`:

```yaml
backend:
  patterns:
    - pattern: clinical-decision-agent-langgraph
      deployment_type: docker
      enabled: true
```

2. Deploy:

```bash
export AWS_PROFILE=quicksuite
cd infra-cdk
npm run deploy
```

## Testing

### Test with Epic Sandbox Patient

```bash
# Set variables
RUNTIME_ARN="arn:aws:bedrock-agentcore:us-east-1:000000000000:runtime/<RUNTIME_ID>"
SESSION_ID="test-$(date +%s)"

# First invocation - will return auth URL
aws bedrock-agentcore invoke-agent-runtime \
  --agent-runtime-arn $RUNTIME_ARN \
  --runtime-session-id $SESSION_ID \
  --runtime-user-id dr-test-user \
  --payload '{"prompt": "Check medications for patient 8MsEzCJO3BA3"}' \
  --profile quicksuite \
  output.json

# Check output for authorization URL
cat output.json
```

**Expected first-time response**:
```json
{
  "returnControl": {
    "invocationInputs": [{
      "authorizationUrl": "https://fhir.epic.com/interconnect-fhir-oauth/oauth2/authorize?..."
    }]
  }
}
```

**Action**: Open the URL, log in to Epic, authorize access.

**Second invocation** (same session_id): Agent will retrieve patient data and respond.

## Example Use Cases

### 1. Drug-Drug Interaction Check
```json
{
  "prompt": "Check for drug interactions with Warfarin for patient 8MsEzCJO3BA3",
  "patientId": "8MsEzCJO3BA3",
  "medication": "Warfarin"
}
```

### 2. Allergy Check
```json
{
  "prompt": "Is patient 8MsEzCJO3BA3 allergic to Penicillin?",
  "patientId": "8MsEzCJO3BA3"
}
```

### 3. Kidney Function Assessment
```json
{
  "prompt": "Check if Gabapentin dose adjustment needed for patient 8MsEzCJO3BA3 based on kidney function",
  "patientId": "8MsEzCJO3BA3",
  "medication": "Gabapentin"
}
```

## Environment Variables

Set by CDK during deployment:

- `STACK_NAME` - Stack name for SSM parameter lookups
- `MEMORY_ID` - AgentCore Memory ID
- `AWS_REGION` - AWS region
- `AWS_DEFAULT_REGION` - Default AWS region

## Security & Compliance

- **User Authorization**: Each clinician must authorize Epic access
- **Patient Context**: Only patients the user has Epic access to
- **Token Security**: Encrypted storage in AgentCore Identity
- **Audit Trail**: All access logged with user_id and session_id
- **HIPAA Compliant**: Meets minimum necessary access requirements

## Troubleshooting

### Authorization Loop
**Problem**: Agent keeps asking for authorization
**Solution**: Ensure session_id is consistent across invocations

### No Tools Available
**Problem**: Agent reports no Epic tools
**Solution**: Verify Epic Gateway URL in SSM Parameter Store

### Token Expired
**Problem**: Authorization error after long period
**Solution**: Re-authorize (tokens auto-refresh but may eventually expire)

## Clinical Safety Notes

⚠️ **This agent is for clinical decision support only**
- Not a replacement for clinical judgment
- Always verify recommendations with references
- Consult pharmacy for complex interactions
- Follow institutional protocols

## References

- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [AgentCore Memory Integration](../../docs/MEMORY_INTEGRATION.md)
