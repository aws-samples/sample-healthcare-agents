# Claims Assembly and Submission Agents - Deployment Guide

This guide provides step-by-step instructions for deploying the Claims Assembly and Submission agents.

## Prerequisites

- AWS Account with appropriate permissions
- AWS CLI configured
- Node.js and npm installed
- Python 3.12+ installed
- CDK bootstrapped in your account

## Architecture Overview

The claims agents implement a healthcare revenue cycle management (RCM) workflow:

```
Claims Assembly Agent → Validation → EDI 837P Generation → Claims Submission Agent → B2B Data Interchange → Payer
```

### Components

1. **Claims Assembly Agent**: Validates claim data and generates EDI 837P JSON structures
2. **Claims Submission Agent**: Submits claims via AWS B2B Data Interchange and tracks acknowledgments
3. **Validation Knowledge Base**: Contains payer requirements, HIPAA 5010 rules, and EDI 837P schemas
4. **B2B Data Interchange**: Transforms JSON claims to X12 EDI format for payer submission
5. **Gateway Lambda**: Provides B2B integration tools (check status, submit, retrieve acknowledgments)

## Deployment Steps

### Step 1: Update Configuration

Edit `infra-cdk/config.yaml` to use the claims assembly or submission agent:

```yaml
backend:
  pattern: "claims-assembly-agent"  # or "claims-submission-agent"
  deployment_type: "zip"  # or "docker"
```

### Step 2: Deploy Infrastructure

```bash
cd infra-cdk
npm install
cdk deploy
```

This creates:
- B2B Data Interchange resources (profile, transformer, capability)
- S3 buckets (input, output, acknowledgment)
- Validation Knowledge Base S3 bucket
- B2B integration Gateway Lambda
- AgentCore Runtime with selected agent

**Deployment Time**: ~15-20 minutes

### Step 3: Upload Validation Rules

After deployment, upload validation rules to the Knowledge Base bucket:

```bash
# Get bucket name from CloudFormation output
BUCKET_NAME=$(aws cloudformation describe-stacks \
  --stack-name healthcare-agents-stack \
  --query 'Stacks[0].Outputs[?OutputKey==`ValidationKBBucket`].OutputValue' \
  --output text)

# Upload validation rules
aws s3 sync ./data/validation-rules-data/ s3://$BUCKET_NAME/

# Verify upload
aws s3 ls s3://$BUCKET_NAME/ --recursive
```

### Step 4: Create Validation Knowledge Base (Manual)

Due to OpenSearch Serverless policy propagation timing issues, the Knowledge Base must be created manually:

1. Go to AWS Console → Amazon Bedrock → Knowledge Bases
2. Click "Create knowledge base"
3. Configure:
   - **Name**: `healthcare-agents-validation-kb`
   - **IAM Role**: Create new role or use existing
   - **Data Source**: S3
   - **S3 URI**: `s3://BUCKET_NAME/` (from Step 3)
   - **Embeddings Model**: Titan Embeddings G1 - Text
   - **Vector Database**: OpenSearch Serverless (create new collection)

4. Start ingestion job
5. Wait for ingestion to complete (~5-10 minutes)

6. Store KB ID in SSM:
```bash
KB_ID="your-kb-id-here"
aws ssm put-parameter \
  --name /healthcare-agents-stack/validation-kb-id \
  --value $KB_ID \
  --type String \
  --overwrite
```

### Step 5: Configure B2B Data Interchange Transformer

The transformer mapping template is a placeholder. Customize it for your EDI 837P requirements:

1. Get transformer ID:
```bash
TRANSFORMER_ID=$(aws ssm get-parameter \
  --name /healthcare-agents-stack/b2bi/transformer-id \
  --query 'Parameter.Value' \
  --output text)
```

2. Update transformer mapping template via AWS Console or CLI
3. Test transformation with sample claim data

### Step 6: Test Deployment

Run the test script:

```bash
export STACK_NAME=healthcare-agents-stack
python scripts/test-claims-agents.py
```

This tests:
- Validation KB retrieval
- B2B buckets (read/write)
- B2B resources (profile, transformer, capability)
- Gateway tools availability
- Sample claim submission

### Step 7: Deploy Frontend (Optional)

If using the web UI:

```bash
python scripts/deploy-frontend.py
```

## Configuration

### Environment Variables

The agents use these environment variables (set automatically by CDK):

**Claims Assembly Agent**:
- `MEMORY_ID`: AgentCore Memory ID
- `VALIDATION_KB_ID`: Validation Knowledge Base ID
- `STACK_NAME`: Stack name for SSM parameter access

**Claims Submission Agent**:
- `MEMORY_ID`: AgentCore Memory ID
- `STACK_NAME`: Stack name for Gateway access
- B2B resource IDs (via SSM parameters)

### SSM Parameters

The deployment creates these SSM parameters:

```
/healthcare-agents-stack/b2bi/profile-id
/healthcare-agents-stack/b2bi/transformer-id
/healthcare-agents-stack/b2bi/capability-id
/healthcare-agents-stack/b2bi/input-bucket
/healthcare-agents-stack/b2bi/output-bucket
/healthcare-agents-stack/b2bi/acknowledgment-bucket
/healthcare-agents-stack/validation-kb-bucket
/healthcare-agents-stack/validation-kb-id (manual)
```

## Usage Examples

### Claims Assembly Agent

**Example Query**:
```
Validate this claim data:
- Patient: John Doe, DOB: 01/01/1980, Member ID: MEM123456
- Provider: Dr. Smith, NPI: 1234567890
- Diagnosis: Type 2 Diabetes (E11.9)
- Procedure: Office Visit (99213), $150
- Service Date: 02/12/2025
```

**Agent Response**:
- Validates all required fields
- Checks NPI format (10 digits)
- Verifies diagnosis code format (ICD-10-CM)
- Confirms procedure code format (CPT)
- Generates EDI 837P JSON structure

### Claims Submission Agent

**Example Query**:
```
Submit this claim:
{claim_data JSON from assembly agent}
```

**Agent Response**:
- Checks for duplicate submissions
- Submits to B2B Data Interchange
- Provides claim ID and submission timestamp
- Monitors transformation status
- Retrieves acknowledgments when available

## Monitoring

### CloudWatch Logs

Monitor agent execution:
```bash
aws logs tail /aws/lambda/healthcare-agents-stack-runtime --follow
```

Monitor B2B integration Lambda:
```bash
aws logs tail /aws/lambda/healthcare-agents-stack-b2bi-integration --follow
```

### B2B Data Interchange Jobs

List recent transformer jobs:
```bash
TRANSFORMER_ID=$(aws ssm get-parameter \
  --name /healthcare-agents-stack/b2bi/transformer-id \
  --query 'Parameter.Value' \
  --output text)

aws b2bi list-transformer-jobs \
  --transformer-id $TRANSFORMER_ID \
  --max-results 10
```

### S3 Buckets

Monitor claim submissions:
```bash
INPUT_BUCKET=$(aws ssm get-parameter \
  --name /healthcare-agents-stack/b2bi/input-bucket \
  --query 'Parameter.Value' \
  --output text)

aws s3 ls s3://$INPUT_BUCKET/claims-to-submit/ --recursive
```

## Troubleshooting

### Validation KB Returns No Results

**Issue**: KB queries return empty results

**Solution**:
1. Verify ingestion job completed successfully
2. Check S3 bucket has validation rules files
3. Ensure KB ID is stored in SSM parameter
4. Test KB directly via Bedrock console

### B2B Transformation Fails

**Issue**: Transformer jobs fail with errors

**Solution**:
1. Check transformer mapping template is valid
2. Verify claim JSON structure matches expected format
3. Review CloudWatch logs for transformer errors
4. Test with simplified claim data

### Gateway Tools Not Available

**Issue**: Agent cannot access B2B integration tools

**Solution**:
1. Verify Gateway Lambda deployed successfully
2. Check IAM permissions for Gateway role
3. Verify Gateway target configuration
4. Test Lambda directly via AWS Console

### Duplicate Claim Detection

**Issue**: Agent doesn't detect duplicate submissions

**Solution**:
1. Ensure claim_id is unique and consistent
2. Check S3 list permissions for input bucket
3. Verify list_submissions tool is working

## Security Considerations

### Data Encryption

- All S3 buckets use customer-managed KMS keys
- Data encrypted at rest and in transit
- Lifecycle policies delete old claims after 90 days

### Access Control

- Gateway uses OAuth2 authentication
- Lambda functions use least-privilege IAM roles
- B2B resources isolated per stack

### PHI Handling

- No PHI in CloudWatch logs
- Claim data encrypted in S3
- Audit trails maintained for all submissions

## Cost Optimization

### Expected Costs (per 1000 claims)

- **B2B Data Interchange**: ~$0.50 per transformation
- **S3 Storage**: ~$0.02 per GB per month
- **Lambda Invocations**: ~$0.20 per 1000 invocations
- **Bedrock KB Queries**: ~$0.10 per 1000 queries
- **AgentCore Runtime**: Based on model usage

**Total**: ~$1-2 per 1000 claims (excluding model costs)

### Cost Reduction Tips

1. Use lifecycle policies to delete old claims
2. Batch claim submissions when possible
3. Cache validation rules in agent memory
4. Use smaller embedding models for KB

## Next Steps

1. Customize transformer mapping template for your payers
2. Add payer-specific validation rules to KB
3. Integrate with your practice management system
4. Set up monitoring and alerting
5. Configure acknowledgment processing workflows

## Support

For issues or questions:
1. Check CloudWatch logs for errors
2. Review test script output
3. Consult AWS B2B Data Interchange documentation
4. Review HIPAA 5010 X12 837P specifications
