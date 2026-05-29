#!/bin/bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

# Test script for Clinical Decision Support Agent with Epic 3LO
# This script demonstrates how to invoke the agent and handle the Epic OAuth flow

set -e

# Configuration
PROFILE="quicksuite"
RUNTIME_NAME="healthcare_agents_stack_clinical_decision_agent_langgraph"
SESSION_ID="test-session-$(date +%s)"
USER_ID="dr-test-user"

echo "=== Clinical Decision Support Agent Test ==="
echo "Profile: $PROFILE"
echo "Runtime: $RUNTIME_NAME"
echo "Session ID: $SESSION_ID"
echo "User ID: $USER_ID"
echo ""

# Get runtime ARN
echo "Fetching runtime ARN..."
RUNTIME_ARN=$(aws bedrock-agentcore list-agent-runtimes \
  --profile $PROFILE \
  --query "runtimeSummaries[?runtimeName=='$RUNTIME_NAME'].runtimeArn | [0]" \
  --output text)

if [ -z "$RUNTIME_ARN" ] || [ "$RUNTIME_ARN" == "None" ]; then
  echo "ERROR: Runtime not found: $RUNTIME_NAME"
  echo "Please deploy the agent first."
  exit 1
fi

echo "Runtime ARN: $RUNTIME_ARN"
echo ""

# Test payload
PAYLOAD='{
  "prompt": "Check if Metformin is safe for patient 8MsEzCJO3BA3. Review their current medications, allergies, and kidney function.",
  "userId": "'$USER_ID'",
  "runtimeSessionId": "'$SESSION_ID'",
  "patientId": "8MsEzCJO3BA3",
  "medication": "Metformin"
}'

echo "=== First Invocation (will trigger Epic OAuth) ==="
echo "Payload:"
echo "$PAYLOAD" | jq '.'
echo ""

# First invocation
echo "Invoking agent..."
aws bedrock-agentcore invoke-agent-runtime \
  --agent-runtime-arn "$RUNTIME_ARN" \
  --runtime-session-id "$SESSION_ID" \
  --runtime-user-id "$USER_ID" \
  --payload "$PAYLOAD" \
  --profile $PROFILE \
  first_output.json

echo ""
echo "=== Response ==="
cat first_output.json | jq '.'

# Check if authorization is needed
if grep -q "authorizationUrl" first_output.json; then
  echo ""
  echo "=== Epic Authorization Required ==="
  AUTH_URL=$(cat first_output.json | jq -r '.returnControl.invocationInputs[0].authorizationUrl')
  echo "Please open this URL in your browser:"
  echo ""
  echo "$AUTH_URL"
  echo ""
  echo "After authorizing:"
  echo "1. Log in to Epic sandbox"
  echo "2. Grant permission to access patient data"
  echo "3. Wait for success message"
  echo ""
  echo "Then run this command for the second invocation:"
  echo ""
  echo "aws bedrock-agentcore invoke-agent-runtime \\"
  echo "  --agent-runtime-arn \"$RUNTIME_ARN\" \\"
  echo "  --runtime-session-id \"$SESSION_ID\" \\"
  echo "  --runtime-user-id \"$USER_ID\" \\"
  echo "  --payload '$PAYLOAD' \\"
  echo "  --profile $PROFILE \\"
  echo "  second_output.json"
  echo ""
  echo "Session ID: $SESSION_ID (use the same session ID!)"
else
  echo ""
  echo "✓ Authorization already complete. Agent responded successfully."
fi

echo ""
echo "=== Test Complete ==="
