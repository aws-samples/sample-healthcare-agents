#!/bin/bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

set -e

#############################################################################
# Epic FHIR User Federation (3LO) Setup Script
#
# This script sets up AgentCore Identity resources for Epic FHIR
# User Federation (3-legged OAuth) authentication.
#
# This is a ONE-TIME setup per AWS account, not per stack deployment.
#
# Usage:
#   ./scripts/setup-epic-3lo.sh [--profile PROFILE] [--region REGION]
#
# Examples:
#   ./scripts/setup-epic-3lo.sh --profile quicksuite
#   ./scripts/setup-epic-3lo.sh --profile quicksuite --region us-east-1
#############################################################################

# Default values
AWS_PROFILE="${AWS_PROFILE:-quicksuite}"
AWS_REGION="${AWS_REGION:-us-east-1}"
PROVIDER_NAME="EpicFHIRProvider"
EPIC_DISCOVERY_URL="https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4/.well-known/openid-configuration"

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --profile)
      AWS_PROFILE="$2"
      shift 2
      ;;
    --region)
      AWS_REGION="$2"
      shift 2
      ;;
    --help)
      echo "Usage: $0 [--profile PROFILE] [--region REGION]"
      echo ""
      echo "Options:"
      echo "  --profile PROFILE    AWS profile to use (default: quicksuite)"
      echo "  --region REGION      AWS region (default: us-east-1)"
      echo "  --help               Show this help message"
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      echo "Use --help for usage information"
      exit 1
      ;;
  esac
done

echo "============================================================"
echo "Epic FHIR User Federation (3LO) Setup"
echo "============================================================"
echo "AWS Profile: $AWS_PROFILE"
echo "AWS Region:  $AWS_REGION"
echo "Provider:    $PROVIDER_NAME"
echo "============================================================"
echo ""

# Check if provider already exists
echo "📋 Checking if OAuth2 Credential Provider already exists..."
if aws bedrock-agentcore-control get-oauth2-credential-provider \
    --name "$PROVIDER_NAME" \
    --profile "$AWS_PROFILE" \
    --region "$AWS_REGION" \
    --output json > /dev/null 2>&1; then

    echo "⚠️  OAuth2 Credential Provider '$PROVIDER_NAME' already exists!"
    echo ""

    # Get existing callback URL
    CALLBACK_URL=$(aws bedrock-agentcore-control get-oauth2-credential-provider \
        --name "$PROVIDER_NAME" \
        --profile "$AWS_PROFILE" \
        --region "$AWS_REGION" \
        --query 'callbackUrl' \
        --output text)

    echo "📋 Existing Callback URL: $CALLBACK_URL"
    echo ""
    echo "Options:"
    echo "  1. Use existing provider (recommended)"
    echo "  2. Delete and recreate"
    echo ""
    read -p "Enter choice (1 or 2): " choice

    if [ "$choice" == "2" ]; then
        echo ""
        echo "🗑️  Deleting existing provider..."
        aws bedrock-agentcore-control delete-oauth2-credential-provider \
            --name "$PROVIDER_NAME" \
            --profile "$AWS_PROFILE" \
            --region "$AWS_REGION"
        echo "✅ Deleted"
        echo ""
    else
        echo ""
        echo "✅ Using existing provider"
        echo ""
        echo "To update credentials, use:"
        echo ""
        echo "  ./scripts/update-epic-3lo-credentials.sh --client-id <YOUR_CLIENT_ID> --client-secret <YOUR_CLIENT_SECRET>"
        echo ""
        exit 0
    fi
fi

# Create OAuth2 Credential Provider with placeholder credentials
echo "🔧 Creating OAuth2 Credential Provider..."
echo "   (with placeholder credentials - you'll update these after Epic app creation)"
echo ""

PROVIDER_RESPONSE=$(aws bedrock-agentcore-control create-oauth2-credential-provider \
    --name "$PROVIDER_NAME" \
    --credential-provider-vendor "CustomOauth2" \
    --oauth2-provider-config-input '{
        "customOauth2ProviderConfig": {
            "oauthDiscovery": {
                "discoveryUrl": "'"$EPIC_DISCOVERY_URL"'"
            },
            "clientId": "placeholder-will-update-after-epic-app-creation",
            "clientSecret": "placeholder-will-update-after-epic-app-creation"
        }
    }' \
    --profile "$AWS_PROFILE" \
    --region "$AWS_REGION" \
    --output json)

if [ $? -ne 0 ]; then
    echo "❌ Failed to create OAuth2 Credential Provider"
    exit 1
fi

# Extract callback URL
CALLBACK_URL=$(echo "$PROVIDER_RESPONSE" | jq -r '.callbackUrl')

echo "✅ OAuth2 Credential Provider created successfully!"
echo ""
echo "============================================================"
echo "IMPORTANT: Save this Callback URL"
echo "============================================================"
echo ""
echo "📋 Callback URL:"
echo "   $CALLBACK_URL"
echo ""
echo "============================================================"
echo "Next Steps"
echo "============================================================"
echo ""
echo "1️⃣  Register Epic App (if not already done):"
echo ""
echo "   • Go to: https://fhir.epic.com/Developer/Apps"
echo "   • Click 'Create' → 'Backend System'"
echo "   • Application Name: MCP Connector - 3LO"
echo "   • Application Audience: Backend Systems ✓"
echo "   • Public Documentation URL: http://www.example.com"
echo "   • Incoming APIs: FHIR"
echo "   • Endpoint URI: $CALLBACK_URL"
echo "   • Can Register Dynamic Clients: ☐ UNCHECKED"
echo "   • Is Confidential Client: ☑ CHECKED"
echo "   • Click 'Save'"
echo ""
echo "2️⃣  Get Epic App Credentials:"
echo ""
echo "   After saving, Epic will provide:"
echo "   • Client ID (e.g., f6e6a266-31e2-43e0-afec-358de041181a)"
echo "   • Client Secret (click to reveal)"
echo ""
echo "3️⃣  Update Credential Provider with Real Credentials:"
echo ""
echo "   Run this command with your Epic credentials:"
echo ""
echo "   ./scripts/update-epic-3lo-credentials.sh \\"
echo "     --client-id <YOUR_CLIENT_ID> \\"
echo "     --client-secret <YOUR_CLIENT_SECRET>"
echo ""
echo "4️⃣  Configure Epic App SMART Scopes:"
echo ""
echo "   In your Epic app, select these scopes:"
echo "   • user/Patient.read"
echo "   • user/MedicationRequest.read"
echo "   • user/AllergyIntolerance.read"
echo "   • user/Observation.read"
echo ""
echo "5️⃣  Deploy Your Agent:"
echo ""
echo "   Your agent code will reference this provider:"
echo ""
echo "   @requires_access_token("
echo "       provider_name='$PROVIDER_NAME',"
echo "       scopes=['user/Patient.read'],"
echo "       auth_flow='USER_FEDERATION'"
echo "   )"
echo ""
echo "============================================================"
echo "Setup Complete!"
echo "============================================================"
echo ""

# Save callback URL to file for reference
echo "$CALLBACK_URL" > .epic-3lo-callback-url
echo "📝 Callback URL saved to: .epic-3lo-callback-url"
echo ""
