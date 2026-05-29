#!/bin/bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

set -e

#############################################################################
# Update Epic FHIR 3LO Credentials
#
# Updates the OAuth2 Credential Provider with real Epic app credentials
# after Epic app creation.
#
# Usage:
#   ./scripts/update-epic-3lo-credentials.sh \
#     --client-id <CLIENT_ID> \
#     --client-secret <CLIENT_SECRET> \
#     [--profile PROFILE] \
#     [--region REGION]
#
# Example:
#   ./scripts/update-epic-3lo-credentials.sh \
#     --client-id f6e6a266-31e2-43e0-afec-358de041181a \
#     --client-secret "your-secret-here" \
#     --profile quicksuite
#############################################################################

# Default values
AWS_PROFILE="${AWS_PROFILE:-quicksuite}"
AWS_REGION="${AWS_REGION:-us-east-1}"
PROVIDER_NAME="EpicFHIRProvider"
EPIC_DISCOVERY_URL="https://fhir.epic.com/interconnect-fhir-oauth/.well-known/openid-configuration"
CLIENT_ID=""
CLIENT_SECRET=""

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --client-id)
      CLIENT_ID="$2"
      shift 2
      ;;
    --client-secret)
      CLIENT_SECRET="$2"
      shift 2
      ;;
    --profile)
      AWS_PROFILE="$2"
      shift 2
      ;;
    --region)
      AWS_REGION="$2"
      shift 2
      ;;
    --help)
      echo "Usage: $0 --client-id ID --client-secret SECRET [OPTIONS]"
      echo ""
      echo "Required:"
      echo "  --client-id ID           Epic app client ID"
      echo "  --client-secret SECRET   Epic app client secret"
      echo ""
      echo "Options:"
      echo "  --profile PROFILE        AWS profile (default: quicksuite)"
      echo "  --region REGION          AWS region (default: us-east-1)"
      echo "  --help                   Show this help message"
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      echo "Use --help for usage information"
      exit 1
      ;;
  esac
done

# Validate required arguments
if [ -z "$CLIENT_ID" ] || [ -z "$CLIENT_SECRET" ]; then
    echo "❌ Error: Both --client-id and --client-secret are required"
    echo ""
    echo "Usage:"
    echo "  $0 --client-id <ID> --client-secret <SECRET>"
    echo ""
    echo "Example:"
    echo "  $0 \\"
    echo "    --client-id f6e6a266-31e2-43e0-afec-358de041181a \\"
    echo "    --client-secret 'your-secret-here' \\"
    echo "    --profile quicksuite"
    exit 1
fi

echo "============================================================"
echo "Updating Epic FHIR 3LO Credentials"
echo "============================================================"
echo "AWS Profile: $AWS_PROFILE"
echo "AWS Region:  $AWS_REGION"
echo "Provider:    $PROVIDER_NAME"
echo "Client ID:   $CLIENT_ID"
echo "============================================================"
echo ""

# Check if provider exists
echo "📋 Checking if OAuth2 Credential Provider exists..."
if ! aws bedrock-agentcore-control get-oauth2-credential-provider \
    --name "$PROVIDER_NAME" \
    --profile "$AWS_PROFILE" \
    --region "$AWS_REGION" \
    --output json > /dev/null 2>&1; then

    echo "❌ Error: OAuth2 Credential Provider '$PROVIDER_NAME' does not exist"
    echo ""
    echo "Run this first:"
    echo "  ./scripts/setup-epic-3lo.sh --profile $AWS_PROFILE"
    exit 1
fi

echo "✅ Provider exists"
echo ""

# Update credential provider with real credentials
echo "🔧 Updating OAuth2 Credential Provider with Epic credentials..."

aws bedrock-agentcore-control update-oauth2-credential-provider \
    --name "$PROVIDER_NAME" \
    --credential-provider-vendor "CustomOauth2" \
    --oauth2-provider-config-input '{
        "customOauth2ProviderConfig": {
            "oauthDiscovery": {
                "discoveryUrl": "'"$EPIC_DISCOVERY_URL"'"
            },
            "clientId": "'"$CLIENT_ID"'",
            "clientSecret": "'"$CLIENT_SECRET"'"
        }
    }' \
    --profile "$AWS_PROFILE" \
    --region "$AWS_REGION" \
    --output json > /dev/null

if [ $? -ne 0 ]; then
    echo "❌ Failed to update OAuth2 Credential Provider"
    exit 1
fi

echo "✅ Credentials updated successfully!"
echo ""

# Verify update
echo "🔍 Verifying configuration..."
PROVIDER_INFO=$(aws bedrock-agentcore-control get-oauth2-credential-provider \
    --name "$PROVIDER_NAME" \
    --profile "$AWS_PROFILE" \
    --region "$AWS_REGION" \
    --output json)

STORED_CLIENT_ID=$(echo "$PROVIDER_INFO" | jq -r '.oauth2ProviderConfigOutput.customOauth2ProviderConfig.clientId')
CALLBACK_URL=$(echo "$PROVIDER_INFO" | jq -r '.callbackUrl')

if [ "$STORED_CLIENT_ID" == "$CLIENT_ID" ]; then
    echo "✅ Client ID verified: $STORED_CLIENT_ID"
    echo "✅ Callback URL: $CALLBACK_URL"
else
    echo "⚠️  Warning: Client ID mismatch"
    echo "   Expected: $CLIENT_ID"
    echo "   Stored:   $STORED_CLIENT_ID"
fi

echo ""
echo "============================================================"
echo "Next Steps"
echo "============================================================"
echo ""
echo "1️⃣  Verify Epic App Configuration:"
echo ""
echo "   • Go to: https://fhir.epic.com/Developer/Apps"
echo "   • Open your app (Client ID: $CLIENT_ID)"
echo "   • Verify Redirect URI matches: $CALLBACK_URL"
echo "   • Verify SMART Scopes are selected:"
echo "     ☑ user/Patient.read"
echo "     ☑ user/MedicationRequest.read"
echo "     ☑ user/AllergyIntolerance.read"
echo "     ☑ user/Observation.read"
echo ""
echo "2️⃣  Deploy Your Agent:"
echo ""
echo "   cd infra-cdk"
echo "   npm run deploy -- --profile $AWS_PROFILE"
echo ""
echo "3️⃣  Test User Federation Flow:"
echo ""
echo "   agentcore invoke '{\"patientId\": \"test-id\"}' \\"
echo "     --agent your-agent-name \\"
echo "     --user-id test-user \\"
echo "     --session-id $(uuidgen | tr '[:upper:]' '[:lower:]' | tr -d '-')test123"
echo ""
echo "   You'll receive an authorization URL to open in your browser"
echo ""
echo "============================================================"
echo "Configuration Complete!"
echo "============================================================"
echo ""

# Store client ID for reference
echo "$CLIENT_ID" > .epic-3lo-client-id
echo "📝 Client ID saved to: .epic-3lo-client-id"
echo ""
