#!/bin/bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

# Post-Deployment Setup Script for Medical Coding Agent
# Run this after CDK deployment completes

set -e

STACK_NAME="healthcare-agents-stack"

echo "=========================================="
echo "Medical Coding Agent - Post-Deployment"
echo "=========================================="
echo ""

# Step 1: Get bucket name
echo "Step 1: Getting Knowledge Base bucket name..."
BUCKET_NAME=$(aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --query 'Stacks[0].Outputs[?OutputKey==`KnowledgeBaseBucket`].OutputValue' \
  --output text)

if [ -z "$BUCKET_NAME" ]; then
  echo "Error: Could not find KnowledgeBaseBucket output"
  exit 1
fi

echo "✓ Bucket: $BUCKET_NAME"
echo ""

# Step 2: Upload KB data
echo "Step 2: Uploading medical codes data to S3..."
aws s3 sync ./data/medical-codes-data/ s3://$BUCKET_NAME/
echo "✓ Data uploaded"
echo ""

# Step 3: Get KB and Data Source IDs
echo "Step 3: Getting Knowledge Base ID..."
KB_ID=$(aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --query 'Stacks[0].Outputs[?OutputKey==`KnowledgeBaseId`].OutputValue' \
  --output text)

if [ -z "$KB_ID" ]; then
  echo "Error: Could not find KnowledgeBaseId output"
  exit 1
fi

echo "✓ Knowledge Base ID: $KB_ID"
echo ""

echo "Step 4: Getting Data Source ID..."
DS_ID=$(aws bedrock-agent list-data-sources \
  --knowledge-base-id $KB_ID \
  --query 'dataSourceSummaries[0].dataSourceId' \
  --output text)

if [ -z "$DS_ID" ]; then
  echo "Error: Could not find data source"
  exit 1
fi

echo "✓ Data Source ID: $DS_ID"
echo ""

# Step 5: Start ingestion job
echo "Step 5: Starting Knowledge Base ingestion job..."
INGESTION_JOB=$(aws bedrock-agent start-ingestion-job \
  --knowledge-base-id $KB_ID \
  --data-source-id $DS_ID \
  --output json)

INGESTION_JOB_ID=$(echo $INGESTION_JOB | jq -r '.ingestionJob.ingestionJobId')
echo "✓ Ingestion job started: $INGESTION_JOB_ID"
echo ""

# Step 6: Wait for ingestion to complete
echo "Step 6: Waiting for ingestion to complete (this may take 5-10 minutes)..."
echo "Checking status every 30 seconds..."
echo ""

while true; do
  STATUS=$(aws bedrock-agent list-ingestion-jobs \
    --knowledge-base-id $KB_ID \
    --data-source-id $DS_ID \
    --max-results 1 \
    --query 'ingestionJobSummaries[0].status' \
    --output text)
  
  echo "Current status: $STATUS"
  
  if [ "$STATUS" = "COMPLETE" ]; then
    echo "✓ Ingestion completed successfully!"
    break
  elif [ "$STATUS" = "FAILED" ]; then
    echo "✗ Ingestion failed!"
    exit 1
  fi
  
  sleep 30
done

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Test Gateway tools:"
echo "   python scripts/test-gateway.py"
echo ""
echo "2. Test the agent:"
echo "   export STACK_NAME=$STACK_NAME"
echo "   python scripts/test-medical-coding-agent.py"
echo ""
echo "3. Deploy frontend:"
echo "   python scripts/deploy-frontend.py"
echo ""
