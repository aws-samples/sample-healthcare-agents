# Clinical Decision Agent Setup Guide

## Quick Start

### 1. Enable the Pattern

Edit `infra-cdk/config.yaml` and add the pattern:

```yaml
backend:
  patterns:
    - pattern: clinical-decision-agent-langgraph
      deployment_type: docker
      enabled: true
```

### 2. Deploy

```bash
# Set AWS profile
export AWS_PROFILE=quicksuite

# Navigate to CDK directory
cd infra-cdk

# Deploy
npm run deploy
```

### 3. Test the Agent

After deployment completes:

```bash
cd ../patterns/clinical-decision-agent-langgraph
./test_invocation.sh
```

## What Gets Deployed

### Infrastructure Components

1. **AgentCore Runtime**
   - Runtime name: `healthcare_agents_stack_clinical_decision_agent_langgraph`
   - Container: Docker image with LangGraph agent
   - Environment: Connects to Epic FHIR Gateway

2. **AgentCore Memory**
   - Memory ID stored in `MEMORY_ID` environment variable
   - Conversation history persistence
   - User-scoped sessions

3. **Epic FHIR Gateway Connection**
   - Gateway URL stored in SSM: `/<stack>/epic_gateway_url`
   - OAuth2 authentication for gateway access
   - MCP protocol for tool communication

### Epic 3LO Configuration (Already Set Up)

The following are already configured in your account:

1. **AgentCore Identity - OAuth2 Credential Provider**
   - Provider Name: `EpicFHIRProvider`
   - Epic Client ID: *(from Secrets Manager; see `EPIC_CLIENT_ID` env var)*
   - Epic Discovery URL: Configured
   - Callback URL: AgentCore Identity callback

2. **Epic App Registration**
   - Registered at https://fhir.epic.com/Developer/Apps
   - SMART Scopes: `user/Patient.read`, `user/MedicationRequest.read`, etc.
   - Confidential client with client secret

## Usage from Frontend

### Frontend Integration

Your frontend should send requests like this:

```javascript
const response = await fetch('/api/agent/clinical-decision', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${userAuthToken}`
  },
  body: JSON.stringify({
    prompt: "Check if Metformin is safe for patient 8MsEzCJO3BA3",
    userId: currentUser.id,
    runtimeSessionId: sessionId,
    patientId: "8MsEzCJO3BA3",
    medication: "Metformin"
  })
});
```

### Handling Epic Authorization Flow

**First-time user experience**:

1. User submits query
2. Agent returns authorization URL
3. Frontend displays: "Epic authorization required"
4. User clicks "Authorize" button
5. Opens Epic OAuth URL in new window/tab
6. User logs into Epic, grants permission
7. Epic redirects to success page
8. User closes window, resubmits query
9. Agent retrieves data successfully

**Subsequent requests**: Transparent (token stored, auto-refreshed)

## Environment Variables

These are automatically set by CDK:

```bash
STACK_NAME=healthcare-agents-stack
MEMORY_ID=<memory-id>
AWS_REGION=us-east-1
AWS_DEFAULT_REGION=us-east-1
```

## Epic Test Patient

Use Epic's sandbox test patient for development:

- **Patient ID**: `8MsEzCJO3BA3`
- **Name**: Amy V Shaw
- **DOB**: 2007-03-20
- **Has**: Active medications, allergies, lab results

## Verifying Deployment

```bash
# Check runtime exists
aws bedrock-agentcore list-agent-runtimes \
  --profile quicksuite \
  --query "runtimeSummaries[?contains(runtimeName, 'clinical_decision')]"

# Check Epic Gateway URL
aws ssm get-parameter \
  --name "/healthcare-agents-stack/epic_gateway_url" \
  --profile quicksuite

# Check memory
aws bedrock-agentcore list-memories \
  --profile quicksuite
```

## Troubleshooting

### Runtime Not Found
- Check deployment logs: `npm run deploy`
- Verify pattern is enabled in `config.yaml`
- Check CloudFormation stack status

### Gateway Connection Failed
- Verify Epic Gateway is deployed
- Check SSM parameter: `/healthcare-agents-stack/epic_gateway_url`
- Verify OAuth2 credentials in Secrets Manager

### Authorization Loop
- Ensure same `runtimeSessionId` used across invocations
- Check AgentCore Identity provider configuration
- Verify Epic callback URL matches AgentCore Identity callback

## Next Steps

1. **Frontend Integration**: Add UI for Epic authorization flow
2. **Custom Prompts**: Modify system prompt for specific use cases
3. **Additional Tools**: Add more clinical decision support tools
4. **Testing**: Test with various Epic sandbox patients
5. **Monitoring**: Set up CloudWatch alerts for errors

## Security Checklist

- [ ] User authentication enforced on frontend
- [ ] Epic tokens never exposed to client
- [ ] Audit logging enabled for all requests
- [ ] HIPAA compliance review completed
- [ ] Rate limiting configured
- [ ] Error messages don't leak PHI

## Support

For issues or questions:
- Check logs in CloudWatch
- Test with Epic sandbox patient first
