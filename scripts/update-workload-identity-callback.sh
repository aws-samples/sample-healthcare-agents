#!/bin/bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

# Update AgentCore Workload Identity with OAuth callback URL
# This allows Epic FHIR OAuth 3LO flow to redirect to the frontend

set -e

PROFILE="${AWS_PROFILE:-quicksuite}"
REGION="${AWS_REGION:-us-east-1}"
STACK_NAME="${STACK_NAME:-healthcare-agents-stack}"

echo "Updating Workload Identity for Epic FHIR OAuth 3LO..."
echo "Profile: $PROFILE"
echo "Region: $REGION"
echo "Stack: $STACK_NAME"

# Get the runtime ID for the clinical decision agent
echo ""
echo "Getting clinical decision agent runtime ID..."
RUNTIME_ARN=$(aws --profile $PROFILE cloudformation describe-stacks \
  --stack-name "${STACK_NAME}-clinical-decision-agent-langgraph" \
  --region $REGION \
  --query "Stacks[0].Outputs[?OutputKey=='AgentRuntimeArn'].OutputValue" \
  --output text 2>/dev/null || echo "")

if [ -z "$RUNTIME_ARN" ]; then
  echo "ERROR: Could not find ClinicalDecisionAgentLanggraphRuntimeArn in stack outputs"
  echo "Make sure the agent is deployed first"
  exit 1
fi

echo "Runtime ARN: $RUNTIME_ARN"

# Extract runtime ID from ARN
# Format: arn:aws:bedrock-agentcore:region:account:runtime/NAME-ID
RUNTIME_ID=$(echo $RUNTIME_ARN | awk -F'/' '{print $2}')
echo "Runtime ID (Workload Identity Name): $RUNTIME_ID"

# Get Amplify URL
echo ""
echo "Getting Amplify URL for OAuth callback..."
AMPLIFY_URL=$(aws --profile $PROFILE ssm get-parameter \
  --name "/$STACK_NAME/amplify-url" \
  --region $REGION \
  --query "Parameter.Value" \
  --output text 2>/dev/null || echo "")

if [ -z "$AMPLIFY_URL" ]; then
  echo "ERROR: Could not find Amplify URL in SSM"
  echo "Deploy the CDK stack first to create the SSM parameter"
  exit 1
fi

CALLBACK_URL="${AMPLIFY_URL}/oauth/callback"
echo "OAuth Callback URL: $CALLBACK_URL"

# Update workload identity
echo ""
echo "Updating workload identity with callback URL..."
aws --profile $PROFILE bedrock-agentcore-control update-workload-identity \
  --name "$RUNTIME_ID" \
  --allowed-resource-oauth2-return-urls "$CALLBACK_URL" \
  --region $REGION

if [ $? -eq 0 ]; then
  echo ""
  echo "✅ Successfully updated workload identity!"
  echo ""
  echo "Workload Identity: $RUNTIME_ID"
  echo "Allowed Callback URL: $CALLBACK_URL"
  echo ""
  echo "The agent can now use Epic FHIR OAuth 3LO with user authorization."
else
  echo ""
  echo "❌ Failed to update workload identity"
  exit 1
fi
