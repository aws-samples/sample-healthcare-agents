# Clinical Decision Agent Deployment Guide

## Prerequisites

1. AWS credentials configured for QuickSuite account (000000000000)
2. Epic OAuth2 credential provider already created (`EpicFHIRProvider`)
3. CDK stack deployed with Amplify frontend

## Deployment Steps

### 1. Deploy Updated Backend

```bash
# Get fresh credentials
./creds-qs.sh

# Deploy CDK stack (includes new Amplify URL SSM parameter)
cd infra-cdk
npm run deploy

# Wait for deployment to complete
```

### 2. Update Workload Identity

The agent's workload identity needs to allow the frontend OAuth callback URL:

```bash
# Run from project root
./scripts/update-workload-identity-callback.sh
```

This script:
- Gets the clinical decision agent runtime ID
- Gets the Amplify URL from SSM
- Updates workload identity to allow `https://{amplify-url}/oauth/callback`

### 3. Verify Configuration

```bash
# Check runtime is deployed
aws --profile quicksuite cloudformation describe-stacks \
  --stack-name healthcare-agents-stack \
  --query "Stacks[0].Outputs[?OutputKey=='ClinicalDecisionAgentLanggraphRuntimeArn'].OutputValue" \
  --output text

# Check workload identity callback URL
RUNTIME_ID="clinical_decision_agent_langgraph_runtime-xuGu6aFE5u"
aws --profile quicksuite bedrock-agentcore-control get-workload-identity \
  --name $RUNTIME_ID \
  --region us-east-1 \
  --query "allowedResourceOauth2ReturnUrls"
```

### 4. Test OAuth Flow

1. Open the frontend at the Amplify URL
2. Navigate to Clinical Decision Support
3. Ask: "Get patient data for patient ID 12345"
4. Agent should return authorization URL
5. Click the URL to authorize via Epic
6. After authorization, you'll be redirected to `/oauth/callback`
7. The callback page will complete the OAuth flow
8. Return to agent - subsequent requests should work

## Architecture Changes

### Before (Broken)
```
Agent → Gateway MCP → Epic FHIR OpenAPI Target (OAuth)
                      ↓ (Returns generic error)
```

### After (Working)
```
Agent → AgentCore Identity (@requires_access_token)
        ↓
        Epic FHIR API directly
        ↓
        Authorization URL → Frontend → User clicks → Callback → Complete
```

## Key Files

### Backend
- `patterns/clinical-decision-agent-langgraph/clinical_decision_agent.py` - Main agent
- `patterns/clinical-decision-agent-langgraph/epic_fhir_direct.py` - Direct Epic FHIR calls
- `patterns/clinical-decision-agent-langgraph/requirements.txt` - Added httpx, pyjwt

### Frontend
- `frontend/src/app/oauth/callback/page.tsx` - OAuth callback handler (already existed)

### Infrastructure
- `infra-cdk/lib/healthcare-agents-main-stack.ts` - Added Amplify URL SSM parameter

### Scripts
- `scripts/update-workload-identity-callback.sh` - Update workload identity

## Troubleshooting

### "Workload identity not found"
- Make sure the agent is deployed first
- Check the runtime ARN in stack outputs

### "SSM parameter not found: amplify-url"
- Redeploy the CDK stack to create the parameter

### "Authorization URL not appearing"
- Check CloudWatch logs: `/aws/bedrock-agentcore/runtimes/clinical_decision_agent_langgraph_runtime-xuGu6aFE5u-DEFAULT`
- Verify the `@requires_access_token` decorator is being called

### "CompleteResourceTokenAuth failed"
- Verify callback URL is registered in workload identity
- Check that frontend user session is valid
- Verify Cognito authentication is working

## Monitoring

```bash
# Tail agent logs
aws --profile quicksuite logs tail \
  /aws/bedrock-agentcore/runtimes/clinical_decision_agent_langgraph_runtime-xuGu6aFE5u-DEFAULT \
  --follow --format short

# Check for authorization events
aws --profile quicksuite logs filter-log-events \
  --log-group-name /aws/bedrock-agentcore/runtimes/clinical_decision_agent_langgraph_runtime-xuGu6aFE5u-DEFAULT \
  --filter-pattern "EPIC-AUTH" \
  --start-time $(($(date +%s) - 3600))000
```
