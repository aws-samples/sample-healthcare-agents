#!/bin/bash

# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

# Test script for Hospital Safety Agent
# Invokes the AgentCore Runtime directly with sample safety events

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get runtime ARN from environment or CloudFormation
RUNTIME_ARN="${RUNTIME_ARN:-$(aws cloudformation describe-stacks \
    --stack-name healthcare-agents-stack \
    --query 'Stacks[0].Outputs[?OutputKey==`RuntimeArn`].OutputValue' \
    --output text)}"

if [ -z "$RUNTIME_ARN" ]; then
    echo -e "${RED}ERROR: Could not determine Runtime ARN${NC}"
    echo "Set RUNTIME_ARN environment variable or ensure healthcare-agents-stack is deployed"
    exit 1
fi

echo -e "${BLUE}Hospital Safety Agent Tester${NC}"
echo -e "${BLUE}=============================${NC}"
echo -e "Runtime ARN: ${GREEN}${RUNTIME_ARN}${NC}\n"

# Function to invoke agent with a safety event
test_safety_event() {
    local test_name="$1"
    local event_text="$2"

    echo -e "${YELLOW}Test: ${test_name}${NC}"
    echo -e "${YELLOW}$(printf '=%.0s' {1..60})${NC}"
    echo -e "Event: ${event_text}\n"

    # Create payload
    PAYLOAD=$(cat <<EOF | jq -c '.' | base64
{
  "prompt": "${event_text}",
  "userId": "test-user",
  "runtimeSessionId": "test-session-$(date +%s)"
}
EOF
)

    # Invoke runtime
    echo -e "${BLUE}Invoking runtime...${NC}"
    aws bedrock-agentcore invoke-agent-runtime \
        --agent-runtime-arn "${RUNTIME_ARN}" \
        --qualifier DEFAULT \
        --payload "${PAYLOAD}" \
        --region us-east-1 \
        response.json

    # Display results
    if [ -f response.json ]; then
        echo -e "\n${GREEN}Response:${NC}"
        cat response.json | jq '.'
        echo -e "\n"
    else
        echo -e "${RED}No response file generated${NC}\n"
    fi

    echo -e "${YELLOW}$(printf '=%.0s' {1..60})${NC}\n"
}

# Test 1: Medication Error (High Severity)
test_safety_event \
    "Medication Error - Wrong Dosage" \
    "A nurse administered 20mg of Lasix instead of the prescribed 10mg to patient in room 302. Patient experienced no immediate adverse effects but blood pressure dropped to 90/60. Medication error discovered during shift change."

# Test 2: Infection Control Event
test_safety_event \
    "Healthcare-Associated Infection" \
    "Patient in ICU bed 5 developed CAUTI on day 4 of catheterization. Temperature spiked to 101.5F. Urine culture positive for E. coli. Two other patients in the ICU also have catheter-associated infections this week."

# Test 3: Patient Fall
test_safety_event \
    "Patient Fall with Injury" \
    "86-year-old patient fell while attempting to reach the bathroom unassisted. Found on floor by nursing staff. Patient reports hip pain. Call bell was within reach but patient did not use it. Fall risk assessment was marked as high."

# Test 4: Low Severity Event
test_safety_event \
    "Minor Medication Timing Issue" \
    "Morning medications for patient in room 215 were administered 45 minutes late due to staffing delays. No adverse patient impact noted. Patient was informed of delay."

echo -e "${GREEN}Testing complete!${NC}\n"

# Show how to check DynamoDB
echo -e "${BLUE}View Results in DynamoDB:${NC}"
echo -e "aws dynamodb scan --table-name healthcare-agents-stack-safety-events --max-items 5"
echo -e "aws dynamodb scan --table-name healthcare-agents-stack-safety-analysis --max-items 5\n"

# Show how to check CloudWatch Logs
echo -e "${BLUE}View Agent Logs:${NC}"
echo -e "aws logs tail /aws/bedrock-agentcore/runtime/FAST_stack_StrandsAgent --follow\n"

# Show SNS subscription status
echo -e "${BLUE}Check SNS Subscription:${NC}"
echo -e "aws sns list-subscriptions-by-topic --topic-arn \$(aws sns list-topics --query 'Topics[?contains(TopicArn, \`safety-alerts\`)].TopicArn' --output text)\n"
