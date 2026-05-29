# Safety Analysis Infrastructure - Aurora PostgreSQL Setup

This directory contains SQL schema definitions for the Aurora PostgreSQL safety_analysis database that receives replicated data from DynamoDB tables.

## Architecture Overview

```
DynamoDB Tables (Operational)          Aurora PostgreSQL (Safety Analysis)
┌─────────────────────────┐           ┌──────────────────────────┐
│  Feedback Table         │           │  Feedback Table          │
│  - feedbackId (PK)      │  Lambda   │  - feedback_id (PK)      │
│  - sessionId            │  ────────>│  - session_id            │
│  - feedbackType         │  Stream   │  - feedback_type         │
│  - timestamp            │           │  - timestamp             │
└─────────────────────────┘           └──────────────────────────┘

┌─────────────────────────┐           ┌──────────────────────────┐
│  SafetyEvents Table     │           │  SafetyEvents Table      │
│  - event_id (PK)        │  Lambda   │  - event_id (PK)         │
│  - timestamp (SK)       │  ────────>│  - timestamp (SK)        │
│  - event_type           │  Stream   │  - event_type            │
│  - location             │           │  - location              │
└─────────────────────────┘           └──────────────────────────┘

┌─────────────────────────┐           ┌──────────────────────────┐
│  SafetyAnalysis Table   │           │  SafetyAnalysis Table    │
│  - analysis_id (PK)     │  Lambda   │  - analysis_id (PK)      │
│  - timestamp (SK)       │  ────────>│  - timestamp (SK)        │
│  - event_id             │  Stream   │  - event_id              │
│  - findings             │           │  - findings              │
└─────────────────────────┘           └──────────────────────────┘
```

## Deployment Steps

### 1. Deploy CDK Stack

First, deploy the infrastructure:

```bash
cd infra-cdk
npm run deploy
```

This creates:
- Aurora Serverless v2 PostgreSQL cluster
- VPC and security groups
- Lambda functions for replication
- DynamoDB streams on all tables
- Event source mappings

### 2. Get Aurora Connection Details

After deployment, retrieve the database credentials:

```bash
# Get the secret ARN from CDK outputs
SECRET_ARN=$(aws cloudformation describe-stacks \
  --stack-name healthcare-agents-stack-safety_analysis \
  --query "Stacks[0].Outputs[?OutputKey=='SecretArn'].OutputValue" \
  --output text)

# Get database credentials
aws secretsmanager get-secret-value \
  --secret-id $SECRET_ARN \
  --query SecretString \
  --output text | jq -r
```

### 3. Initialize Database Schema

Connect to Aurora and run the initialization script:

```bash
# Get Aurora endpoint
AURORA_ENDPOINT=$(aws cloudformation describe-stacks \
  --stack-name healthcare-agents-stack-safety_analysis \
  --query "Stacks[0].Outputs[?OutputKey=='ClusterEndpoint'].OutputValue" \
  --output text)

# Get credentials from Secrets Manager
DB_USERNAME=$(aws secretsmanager get-secret-value \
  --secret-id $SECRET_ARN \
  --query SecretString \
  --output text | jq -r '.username')

DB_PASSWORD=$(aws secretsmanager get-secret-value \
  --secret-id $SECRET_ARN \
  --query SecretString \
  --output text | jq -r '.password')

# Run initialization script
PGPASSWORD=$DB_PASSWORD psql \
  -h $AURORA_ENDPOINT \
  -U $DB_USERNAME \
  -d safety_analysis \
  -f init-safety-analysis-schema.sql
```

### 4. Verify Replication

Test that data is flowing from DynamoDB to Aurora:

```bash
# Insert test feedback in DynamoDB
aws dynamodb put-item \
  --table-name healthcare-agents-stack-feedback \
  --item '{
    "feedbackId": {"S": "test-123"},
    "sessionId": {"S": "session-456"},
    "message": {"S": "Test message"},
    "feedbackType": {"S": "positive"},
    "timestamp": {"N": "'$(date +%s)000'"}
  }'

# Wait a few seconds, then query Aurora
PGPASSWORD=$DB_PASSWORD psql \
  -h $AURORA_ENDPOINT \
  -U $DB_USERNAME \
  -d safety_analysis \
  -c 'SELECT * FROM public."Feedback" ORDER BY "timestamp" DESC LIMIT 5;'
```

## Database Tables

### Feedback
Stores user feedback on agent responses.

**Columns:**
- `feedback_id` (PK): Unique identifier
- `session_id`: Conversation session
- `message`: Agent's response being rated
- `feedback_type`: 'positive' or 'negative'
- `comment`: User's explanation
- `timestamp`: Unix timestamp (milliseconds)

### SafetyEvents
Stores hospital safety events.

**Columns:**
- `event_id` (PK): Unique identifier
- `timestamp` (SK): ISO 8601 timestamp
- `event_type`: fall, infection, medication_error
- `location`: Hospital location
- `severity`: low, medium, high, critical
- `description`: Event details
- `patient_id`: Patient identifier

### SafetyAnalysis
Stores specialist agent analysis results.

**Columns:**
- `analysis_id` (PK): Unique identifier
- `timestamp` (SK): ISO 8601 timestamp
- `event_id`: Related safety event
- `analyst_type`: falls_prevention, infection_control, medication_safety
- `findings`: Analysis findings
- `recommendations`: Recommended actions
- `risk_score`: 0-100 risk score

## Materialized Views

The schema includes pre-built materialized views for common safety_analysis queries:

### FeedbackSummary
Daily summary of feedback by type.

```sql
SELECT * FROM public."FeedbackSummary"
WHERE date >= CURRENT_DATE - INTERVAL '30 days'
ORDER BY date DESC;
```

### SafetyEventsSummary
Daily summary of safety events by type, severity, and location.

```sql
SELECT * FROM public."SafetyEventsSummary"
WHERE date >= CURRENT_DATE - INTERVAL '7 days'
  AND severity IN ('high', 'critical')
ORDER BY event_count DESC;
```

### SafetyEventsWithAnalysis
Combined view of events and their analysis.

```sql
SELECT * FROM public."SafetyEventsWithAnalysis"
WHERE event_type = 'fall'
  AND risk_score > 70
ORDER BY event_timestamp DESC;
```

### Refresh Materialized Views

Materialized views should be refreshed periodically (e.g., daily):

```sql
SELECT refresh_all_materialized_views();
```

Or schedule with cron/EventBridge:

```sql
-- Refresh at 2 AM daily
SELECT cron.schedule('refresh-safety_analysis-views', '0 2 * * *', $$
  SELECT refresh_all_materialized_views();
$$);
```

## Example Safety Analysis Queries

### Feedback Analysis

```sql
-- Feedback trend over time
SELECT
  DATE_TRUNC('week', TO_TIMESTAMP("timestamp" / 1000)) AS week,
  "feedback_type",
  COUNT(*) AS count,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY DATE_TRUNC('week', TO_TIMESTAMP("timestamp" / 1000))), 2) AS percentage
FROM public."Feedback"
WHERE TO_TIMESTAMP("timestamp" / 1000) >= CURRENT_DATE - INTERVAL '90 days'
GROUP BY week, "feedback_type"
ORDER BY week DESC, "feedback_type";

-- Sessions with negative feedback
SELECT
  "session_id",
  COUNT(*) AS negative_count,
  STRING_AGG("comment", ' | ') AS comments
FROM public."Feedback"
WHERE "feedback_type" = 'negative'
  AND "comment" IS NOT NULL
GROUP BY "session_id"
HAVING COUNT(*) > 1
ORDER BY negative_count DESC;
```

### Safety Event Analysis

```sql
-- High-risk events needing immediate attention
SELECT
  e."event_id",
  e."event_type",
  e."location",
  e."severity",
  e."description",
  a."risk_score",
  a."recommendations"
FROM public."SafetyEvents" e
JOIN public."SafetyAnalysis" a ON e."event_id" = a."event_id"
WHERE e."severity" IN ('high', 'critical')
  AND a."risk_score" > 80
ORDER BY a."risk_score" DESC, e."timestamp" DESC;

-- Infection patterns by location
SELECT
  "location",
  COUNT(*) AS infection_count,
  AVG(a."risk_score") AS avg_risk_score
FROM public."SafetyEvents" e
LEFT JOIN public."SafetyAnalysis" a ON e."event_id" = a."event_id"
WHERE e."event_type" = 'infection'
  AND TO_TIMESTAMP(e."timestamp", 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY "location"
HAVING COUNT(*) > 2
ORDER BY infection_count DESC, avg_risk_score DESC;
```

## Monitoring

Monitor replication lag and Lambda function metrics:

```bash
# Check Lambda function logs
aws logs tail /aws/lambda/healthcare-agents-stack-feedback-replicator --follow

# Check DynamoDB stream metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/DynamoDB \
  --metric-name UserErrors \
  --dimensions Name=TableName,Value=healthcare-agents-stack-feedback \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Sum
```

## Troubleshooting

### Lambda function errors

Check CloudWatch Logs for the replicator Lambda:

```bash
aws logs filter-log-events \
  --log-group-name /aws/lambda/healthcare-agents-stack-feedback-replicator \
  --filter-pattern "ERROR" \
  --start-time $(date -d '1 hour ago' +%s)000
```

### Connection issues

Verify Lambda can connect to Aurora:

```bash
# Check security group rules
aws ec2 describe-security-groups \
  --filters "Name=tag:Name,Values=*Safety Analysis*" \
  --query "SecurityGroups[*].{ID:GroupId,Name:GroupName,Rules:IpPermissions}"
```

### Missing data

Check if DynamoDB streams are enabled:

```bash
aws dynamodb describe-table \
  --table-name healthcare-agents-stack-feedback \
  --query "Table.StreamSpecification"
```

## Cost Optimization

- Aurora Serverless v2: Min 0.5 ACU, Max 2 ACU (~$65/month at steady state)
- Lambda: Pay per invocation (~$0.001 per 1000 records)
- Data Transfer: Free within same region
- DynamoDB Streams: Free (included with DynamoDB pricing)

To reduce costs:
- Adjust Aurora ACU limits in safety_analysis-stack.ts
- Use Aurora data API instead of persistent connections
- Archive old data to S3 with Amazon Athena queries

## Security

- All data encrypted at rest with customer-managed KMS keys
- Database credentials stored in AWS Secrets Manager
- Aurora deployed in isolated VPC subnets
- Lambda functions run in VPC with minimal IAM permissions
- No public internet access to Aurora cluster
