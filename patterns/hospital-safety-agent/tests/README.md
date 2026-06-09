# Hospital Safety Agent Tests

This directory contains integration tests for the Hospital Safety Agent system.

## Test Files

### `test_hospital_safety.py`
Main test utility that provides:
- `get_cognito_token()` - Authenticates and returns JWT token
- `invoke_safety_agent()` - Invokes the agent runtime with an event
- Comprehensive test suite for all event types

### `test_single_fall.py`
Tests patient fall event classification and routing to the Fall Prevention Specialist.

### `test_single_infection.py`
Tests infection control event classification and routing to the Infection Control Specialist.

### `test_threshold_breach.py`
Tests threshold-based alerting by submitting 3 medication errors to trigger:
- Individual high-severity alerts (physicians + safety officers)
- Threshold breach alert after 3rd event (safety officers only)

### `test_structured_output.py`
Tests the Pydantic-based structured output classification:
- Type-safe event_type and severity (no keyword matching)
- Automatic entity extraction (patient_id, location, staff_involved)
- Brief summary generation

## Prerequisites

1. **Environment Configuration**: Create a `.env` file in the `patterns/hospital-safety-agent/` directory with:
   ```
   COGNITO_CLIENT_ID=your_client_id
   COGNITO_USERNAME=your_username
   COGNITO_PASSWORD=your_password
   COGNITO_USER_POOL_ID=your_pool_id
   COGNITO_REGION=us-east-1
   RUNTIME_ARN=arn:aws:bedrock-agentcore:us-east-1:ACCOUNT:runtime/RUNTIME_ID
   ```

2. **AWS Credentials**: Ensure you have valid AWS credentials configured

3. **Deployed Stack**: The Hospital Safety Stack must be deployed

## Running Tests

Run individual tests:
```bash
cd /path/to/healthcare-agents/patterns/hospital-safety-agent/tests

# Test structured output classification
python test_structured_output.py

# Test threshold breach detection
python test_threshold_breach.py

# Test patient fall events
python test_single_fall.py

# Test infection control events
python test_single_infection.py

# Run comprehensive test suite (all event types)
python test_hospital_safety.py
```

## Expected Behavior

### Individual Event Tests
- Event is classified by orchestrator using structured output
- Routed to appropriate specialist agent (Medication, Fall, or Infection)
- High/critical severity alerts sent to both physicians and safety officers
- Event stored in DynamoDB with extracted entities

### Threshold Breach Test
- Submits 3 medication errors with 10-second delays
- First 2 events: Individual alerts sent to both recipients
- 3rd event: Individual alert + threshold breach alert to safety officers
- Threshold breach email includes event count and recent events list

## Viewing Results

### CloudWatch Logs
```bash
# View orchestrator logs with structured classification
aws logs tail /aws/bedrock-agentcore/runtimes/RUNTIME_ID-DEFAULT --since 5m | grep ORCHESTRATOR

# View threshold detection logs
aws logs tail /aws/bedrock-agentcore/runtimes/RUNTIME_ID-DEFAULT --since 5m | grep THRESHOLD
```

### Email Alerts
Check the configured email addresses:
- `physician@example.com` - Receives high/critical severity alerts
- `safety@example.com` - Receives all alerts including threshold breaches

### DynamoDB
Events are stored in the `FAST-hospital-safety-events` table with:
- event_id (partition key)
- event_type (GSI partition key for threshold queries)
- timestamp
- severity
- Extracted entities: patient_id, location, staff_involved
- Full classification and analysis

## Troubleshooting

### Authentication Errors
- Verify `.env` file exists in repository root
- Confirm Cognito credentials are valid
- Check IAM permissions for Bedrock AgentCore

### Timeout Errors
- AgentCore has 120-second timeout for responses
- Timeouts during event submission usually complete server-side
- Check CloudWatch logs and DynamoDB to verify event processing

### No Email Received
- Verify email addresses are confirmed in SNS topic subscriptions
- Check SNS topic has correct email subscriptions
- Review CloudWatch logs for send_alert calls
