# Testing the Hospital Safety Agent

Since the frontend doesn't have a custom UI for hospital safety events yet, you can test the agent directly via the AgentCore Runtime API.

## Prerequisites

- AWS CLI configured with credentials
- healthcare-agents-stack deployed (CDK deploy completed successfully)
- Python 3.x with boto3 (for Python test script)

## Option 1: Bash Test Script (Recommended)

The bash script tests multiple safety event scenarios and displays results:

```bash
./test-hospital-safety.sh
```

**What it does:**
- Tests 4 different safety event types:
  - Medication error (high severity)
  - Healthcare-associated infection
  - Patient fall with injury
  - Minor medication timing issue
- Invokes the AgentCore Runtime for each event
- Displays agent responses
- Shows commands to view results in DynamoDB and CloudWatch

## Option 2: Python Test Script

More flexible for custom testing:

```bash
python3 test_hospital_safety.py
```

**What it includes:**
- 5 sample safety events (medication, infection, falls, device malfunction)
- Automatic Runtime ARN discovery
- DynamoDB result viewing
- Easy to modify for custom events

### Test a Custom Event

```python
from test_hospital_safety import invoke_safety_agent

# Your custom safety event
custom_event = """
Describe your safety event here...
"""

result = invoke_safety_agent(custom_event, user_id="your-user-id")
```

## Option 3: Direct AWS CLI

For manual testing with custom payloads:

```bash
# Get Runtime ARN
RUNTIME_ARN=$(aws cloudformation describe-stacks \
    --stack-name healthcare-agents-stack \
    --query 'Stacks[0].Outputs[?OutputKey==`RuntimeArn`].OutputValue' \
    --output text)

# Create payload
PAYLOAD=$(cat <<EOF | jq -c '.' | base64
{
  "prompt": "A nurse administered wrong medication to patient in room 302",
  "userId": "test-user",
  "runtimeSessionId": "test-session-123"
}
EOF
)

# Invoke runtime
aws bedrock-agentcore invoke-agent-runtime \
    --agent-runtime-arn "${RUNTIME_ARN}" \
    --qualifier DEFAULT \
    --payload "${PAYLOAD}" \
    --region us-east-1 \
    response.json

# View response
cat response.json | jq '.'
```

## Viewing Results

### 1. Agent Response (Immediate)

The agent returns a JSON response with:
```json
{
  "status": "success",
  "event_id": "evt_abc123",
  "classification": {
    "event_type": "medication_error",
    "severity": "high"
  },
  "analysis": {
    "findings": "...",
    "recommendations": [...]
  }
}
```

### 2. DynamoDB Tables

View stored events:
```bash
# Events table
aws dynamodb scan --table-name healthcare-agents-stack-safety-events --max-items 5

# Analysis table
aws dynamodb scan --table-name healthcare-agents-stack-safety-analysis --max-items 5
```

Or query specific events:
```bash
aws dynamodb query \
    --table-name healthcare-agents-stack-safety-events \
    --index-name event-type-index \
    --key-condition-expression "event_type = :type" \
    --expression-attribute-values '{":type":{"S":"medication_error"}}'
```

### 3. CloudWatch Logs

View agent execution logs in real-time:
```bash
aws logs tail /aws/bedrock-agentcore/runtime/FAST_stack_StrandsAgent --follow
```

Search for specific patterns:
```bash
# Orchestrator logs
aws logs filter-log-events \
    --log-group-name /aws/bedrock-agentcore/runtime/FAST_stack_StrandsAgent \
    --filter-pattern "[ORCHESTRATOR]"

# Medication agent logs
aws logs filter-log-events \
    --log-group-name /aws/bedrock-agentcore/runtime/FAST_stack_StrandsAgent \
    --filter-pattern "[MEDICATION]"

# Errors
aws logs filter-log-events \
    --log-group-name /aws/bedrock-agentcore/runtime/FAST_stack_StrandsAgent \
    --filter-pattern "ERROR"
```

### 4. SNS Alerts (Email)

High and critical severity events trigger email alerts to:
- **Email**: safety@example.com

**First time setup:**
1. Check your email for "AWS Notification - Subscription Confirmation"
2. Click the confirmation link
3. Future alerts will be delivered automatically

Check subscription status:
```bash
TOPIC_ARN=$(aws sns list-topics --query 'Topics[?contains(TopicArn, `safety-alerts`)].TopicArn' --output text)
aws sns list-subscriptions-by-topic --topic-arn $TOPIC_ARN
```

## Sample Test Events

### Medication Error (High Severity)
```
A nurse administered 20mg of Lasix instead of the prescribed 10mg to patient
in room 302. Patient experienced no immediate adverse effects but blood pressure
dropped to 90/60. Medication error discovered during shift change.
```

**Expected Behavior:**
- Classified as: `medication_error`, severity `high`
- Routed to: Medication Safety Agent
- FDA API queried for drug information
- SNS alert sent to email

### Healthcare-Associated Infection
```
Patient in ICU bed 5 developed CAUTI on day 4 of catheterization. Temperature
spiked to 101.5F. Urine culture positive for E. coli. Two other patients in
the ICU also have catheter-associated infections this week.
```

**Expected Behavior:**
- Classified as: `infection_control`, severity `high`
- Routed to: Infection Control Agent
- DynamoDB queried for historical patterns
- Outbreak risk assessment performed
- SNS alert sent

### Patient Fall
```
86-year-old patient fell while attempting to reach the bathroom unassisted.
Found on floor by nursing staff. Patient reports hip pain. Call bell was
within reach but patient did not use it. Fall risk assessment was marked as high.
```

**Expected Behavior:**
- Classified as: `patient_fall`, severity `high`
- Routed to: Patient Falls Agent
- Injury severity assessed
- Fall prevention protocol checked
- SNS alert sent

## Troubleshooting

### Agent not responding
- Check Runtime status: `aws bedrock-agentcore describe-runtime --runtime-identifier <runtime-id>`
- Check CloudWatch logs for errors
- Verify environment variables are set correctly

### No SNS alerts
- Confirm email subscription (check spam folder)
- Verify topic ARN is set: `echo $ALERT_SNS_TOPIC_ARN`
- Check CloudWatch logs for `[ALERT]` messages

### DynamoDB not storing events
- Verify IAM permissions for AgentCore Runtime role
- Check environment variables: `EVENTS_TABLE_NAME`, `ANALYSIS_TABLE_NAME`
- Review CloudWatch logs for DynamoDB errors

### Runtime errors
```bash
# View recent errors
aws logs filter-log-events \
    --log-group-name /aws/bedrock-agentcore/runtime/FAST_stack_StrandsAgent \
    --filter-pattern "ERROR" \
    --start-time $(date -u -d '5 minutes ago' +%s)000
```

## Expected Log Output

Successful processing shows this flow in CloudWatch:
```
[MAIN] Processing safety event for user test-user
[ORCHESTRATOR] Processing event evt_abc123
[ORCHESTRATOR] Classification: medication_error, severity: high
[ORCHESTRATOR] Routing to Medication Safety Agent
[MEDICATION] Analyzing medication error event
[MEDICATION] Querying FDA API for drug: Lasix
[MEDICATION] Severity score: 4
[ORCHESTRATOR] Storing analysis results
[ALERT] Sent alert for event evt_abc123
```

## Next Steps

After successful testing:
1. Integrate with frontend UI (add safety event submission form)
2. Configure additional alert channels (PagerDuty, Slack)
3. Set up QuickSight dashboard for analytics
4. Add more specialist agents (device malfunction, surgical events)
