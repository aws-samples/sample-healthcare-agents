# Adding New Agent Patterns to Healthcare Agents

This guide explains how to add new agent patterns to the healthcare agents system, including when to create dedicated infrastructure stacks and how to connect the AgentCore Runtime to pattern-specific resources.

## Architecture Overview

The healthcare agents system uses a layered architecture:

1. **Main Stack** (`main-stack.ts`): Creates shared resources used by all patterns
   - Cognito User Pool for authentication
   - KMS encryption keys
   - Amplify frontend hosting
   - Machine client credentials

2. **Backend Stack** (`backend-stack.ts`): Creates the AgentCore Runtime and Memory for each pattern
   - AgentCore Runtime (execution environment for agent code)
   - AgentCore Memory (persistent storage for agent conversations)
   - AgentCore Gateway tools (HealthLake, custom tools)
   - Docker image build and ECR repository

3. **Nested Pattern Stacks** (optional): Create pattern-specific infrastructure
   - DynamoDB tables
   - SNS topics
   - S3 buckets
   - OpenSearch Serverless collections
   - Bedrock Knowledge Bases

## Decision Tree: When to Create a Nested Stack

**Create a nested stack when your pattern needs:**
- DynamoDB tables for data storage
- SNS topics for notifications
- S3 buckets for file storage
- OpenSearch Serverless collections for vector search
- Bedrock Knowledge Bases for RAG
- Any AWS resources that are specific to your pattern

**Use backend stack only when your pattern:**
- Only needs the AgentCore Runtime and Memory
- Only uses shared Gateway tools (HealthLake)
- Doesn't need dedicated AWS resources

**Examples:**
- ✅ `hospital-safety-agent`: Needs DynamoDB tables (events, analysis) and SNS topic (alerts) → **Create nested stack**
- ✅ `medical-coding-agent`: Needs S3 bucket and OpenSearch collection for Knowledge Base → **Create nested stack**
- ✅ `clinical-decision-support`: Only needs Runtime and Gateway tools → **No nested stack**

## The 3-Part Handshake Pattern

When a pattern needs dedicated infrastructure, the Runtime connects to nested stack resources through a 3-part handshake:

### Part 1: IAM Permissions (Nested Stack → Runtime Role)

The nested stack grants IAM permissions to the Runtime's execution role:

```typescript
// In your nested stack constructor (e.g., hospital-safety-stack.ts)
if (props.agentCoreRoleArn) {
  // Import the Runtime's role by ARN
  const agentCoreRole = iam.Role.fromRoleArn(
    this,
    'AgentCoreRole',
    props.agentCoreRoleArn
  );

  // Grant permissions to access your resources
  this.eventsTable.grantReadWriteData(agentCoreRole);
  this.analysisTable.grantReadWriteData(agentCoreRole);
  this.alertTopic.grantPublish(agentCoreRole);
}
```

### Part 2: Resource Discovery (Nested Stack → Environment Variables)

The backend stack reads resource names/ARNs from the nested stack and passes them as environment variables:

```typescript
// In backend-stack.ts, after creating nested stack
if (this.hospitalSafetyStack) {
  envVars.EVENTS_TABLE_NAME = this.hospitalSafetyStack.eventsTable.tableName;
  envVars.ANALYSIS_TABLE_NAME = this.hospitalSafetyStack.analysisTable.tableName;
  envVars.ALERT_SNS_TOPIC_ARN = this.hospitalSafetyStack.alertTopic.topicArn;
}

// Later, create Runtime with these environment variables
this.agentRuntime = new agentcore.Runtime(this, "Runtime", {
  environmentVariables: envVars,
  executionRole: agentRole,  // This is the role that has permissions
  // ...
});
```

### Part 3: Runtime Execution (Agent Code → AWS Resources)

The agent code reads environment variables and uses the Runtime's IAM role to access resources:

```python
# In your agent code (e.g., hospital_safety_agent.py)
import os
import boto3

# Read resource names from environment variables
EVENTS_TABLE_NAME = os.environ.get("EVENTS_TABLE_NAME")
ALERT_TOPIC_ARN = os.environ.get("ALERT_SNS_TOPIC_ARN")

# Use boto3 clients - they automatically use the Runtime's IAM role
dynamodb = boto3.resource('dynamodb')
sns = boto3.client('sns')

# Access resources - permissions were granted in Part 1
events_table = dynamodb.Table(EVENTS_TABLE_NAME)
events_table.put_item(Item={...})

sns.publish(TopicArn=ALERT_TOPIC_ARN, Message="Alert!")
```

**Key insight:** The Runtime's IAM role is created in backend-stack, passed to nested stack for permission grants, and used by the Runtime container at execution time. No credentials need to be hardcoded - IAM handles everything.

## Step-by-Step Guide: Adding a New Pattern with Nested Stack

### Step 1: Create Your Agent Code

Create your pattern directory and agent code:

```bash
mkdir -p patterns/my-new-agent
touch patterns/my-new-agent/my_agent.py
touch patterns/my-new-agent/requirements.txt
touch patterns/my-new-agent/Dockerfile
```

**Important:** Your Dockerfile must use the project root as build context:

```dockerfile
FROM public.ecr.aws/docker/library/python:3.12-slim

WORKDIR /app

# Copy requirements from YOUR pattern directory
COPY patterns/my-new-agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared code from project root
COPY gateway/ gateway/
COPY tools/ tools/

# Copy YOUR agent code
COPY patterns/my-new-agent/my_agent.py .

EXPOSE 8080
ENV PYTHONUNBUFFERED=1
CMD ["python", "my_agent.py"]
```

### Step 2: Create Your Nested Stack

Create a new file `infra-cdk/lib/patterns/my-new-agent/my-new-agent-stack.ts`:

```typescript
import * as cdk from 'aws-cdk-lib';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as sns from 'aws-cdk-lib/aws-sns';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as kms from 'aws-cdk-lib/aws-kms';
import { Construct } from 'constructs';

export interface MyNewAgentStackProps extends cdk.NestedStackProps {
  /**
   * Base name for the stack (e.g., "healthcare-agents-stack")
   */
  readonly stackNameBase: string;

  /**
   * IAM role ARN that the AgentCore Runtime uses
   * This role will be granted permissions to access resources
   */
  readonly agentCoreRoleArn?: string;

  /**
   * KMS key for customer-managed encryption
   */
  readonly dataEncryptionKey: kms.IKey;
}

export class MyNewAgentStack extends cdk.NestedStack {
  // Expose resources as public properties so backend-stack can read them
  public readonly myTable: dynamodb.Table;
  public readonly myTopic: sns.Topic;

  constructor(scope: Construct, id: string, props: MyNewAgentStackProps) {
    const description = "My New Agent Infrastructure - DynamoDB tables and SNS topics";
    super(scope, id, { ...props, description });

    // Create your DynamoDB table
    this.myTable = new dynamodb.Table(this, 'MyTable', {
      tableName: `${props.stackNameBase}-my-table`,
      partitionKey: { name: 'id', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      encryption: dynamodb.TableEncryption.CUSTOMER_MANAGED,
      encryptionKey: props.dataEncryptionKey,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      pointInTimeRecovery: true,
    });

    // Create your SNS topic
    this.myTopic = new sns.Topic(this, 'MyTopic', {
      topicName: `${props.stackNameBase}-my-topic`,
      masterKey: props.dataEncryptionKey,
    });

    // CRITICAL: Grant permissions to the Runtime's role (Part 1 of handshake)
    if (props.agentCoreRoleArn) {
      const agentCoreRole = iam.Role.fromRoleArn(
        this,
        'AgentCoreRole',
        props.agentCoreRoleArn
      );

      // Grant read/write access to DynamoDB
      this.myTable.grantReadWriteData(agentCoreRole);

      // Grant publish access to SNS
      this.myTopic.grantPublish(agentCoreRole);
    }

    // Create SSM parameters for easy discovery
    new cdk.aws_ssm.StringParameter(this, 'MyTableNameParam', {
      parameterName: `/${props.stackNameBase}/my-new-agent/table_name`,
      stringValue: this.myTable.tableName,
      description: 'DynamoDB table name for my new agent',
    });

    // Stack outputs for visibility
    new cdk.CfnOutput(this, 'MyTableName', {
      value: this.myTable.tableName,
      description: 'DynamoDB table for my new agent',
      exportName: `${props.stackNameBase}-MyAgentTable`,
    });

    new cdk.CfnOutput(this, 'MyTopicArn', {
      value: this.myTopic.topicArn,
      description: 'SNS topic for my new agent',
    });
  }
}
```

### Step 3: Update Backend Stack

Add your nested stack to `backend-stack.ts`:

```typescript
// At the top, add import
import { MyNewAgentStack } from './patterns/my-new-agent/my-new-agent-stack';

export class BackendStack extends cdk.Stack {
  // Add property for your nested stack
  public myNewAgentStack?: MyNewAgentStack;

  constructor(scope: Construct, id: string, props: BackendStackProps) {
    // ... existing code ...

    // STEP 3A: Create nested stack BEFORE Runtime (around line 300)
    // This happens in the pattern loop
    if (pattern === "my-new-agent") {
      this.myNewAgentStack = new MyNewAgentStack(this, "MyNewAgent", {
        stackNameBase: config.stack_name_base,
        agentCoreRoleArn: agentRole.roleArn,  // Pass Runtime's role
        dataEncryptionKey: this.dataEncryptionKey,
      });
    }

    // ... build Docker image, create Memory ...

    // STEP 3B: Set environment variables from nested stack (around line 461)
    if (this.myNewAgentStack) {
      envVars.MY_TABLE_NAME = this.myNewAgentStack.myTable.tableName;
      envVars.MY_TOPIC_ARN = this.myNewAgentStack.myTopic.topicArn;
      // Add any other config your agent needs
      envVars.MY_CUSTOM_SETTING = "some-value";
    }

    // STEP 3C: Create Runtime with environment variables (around line 473)
    this.agentRuntime = new agentcore.Runtime(this, "Runtime", {
      runtimeName: `${config.stack_name_base.replace(/-/g, "_")}_${this.agentName.valueAsString}`,
      agentRuntimeArtifact: agentRuntimeArtifact,
      executionRole: agentRole,  // This role has permissions from Step 3A
      environmentVariables: envVars,  // This has resource names from Step 3B
      // ...
    });
  }
}
```

### Step 4: Enable Your Pattern in Configuration

Add your pattern to `infra-cdk/config.yaml`:

```yaml
backend:
  patterns:
    - pattern: hospital-safety-agent
      deployment_type: docker
      enabled: true
    - pattern: my-new-agent  # Add your pattern here
      deployment_type: docker
      enabled: true
```

### Step 5: Deploy Your Pattern

```bash
# Set AWS profile
export AWS_PROFILE=quicksuite

# Navigate to CDK directory
cd infra-cdk

# Deploy
npm run deploy
```

The deployment will:
1. Create your nested stack with DynamoDB tables and SNS topics
2. Grant IAM permissions to the Runtime's role
3. Build your Docker image
4. Create AgentCore Runtime with environment variables
5. Connect everything together

### Step 6: Verify Deployment

Check the CloudFormation console to see your nested stack:

```bash
aws cloudformation describe-stacks \
  --stack-name healthcare-agents-stack-my-new-agent \
  --profile quicksuite
```

Test your agent by invoking it through the frontend or API.

## Real-World Examples

### Example 1: Hospital Safety Agent (DynamoDB + SNS)

**Pattern**: Multi-agent system with shared data storage and alerting

**Infrastructure** (`hospital-safety-stack.ts`):
- 2 DynamoDB tables: `eventsTable` (incident reports), `analysisTable` (analysis results)
- 1 SNS topic: `alertTopic` (physician/safety officer notifications)

**Key Code:**
```typescript
// Grant permissions
this.eventsTable.grantReadWriteData(agentCoreRole);
this.analysisTable.grantReadWriteData(agentCoreRole);
this.alertTopic.grantPublish(agentCoreRole);

// Expose resources
public readonly eventsTable: dynamodb.Table;
public readonly analysisTable: dynamodb.Table;
public readonly alertTopic: sns.Topic;
```

**Environment Variables:**
```typescript
envVars.EVENTS_TABLE_NAME = this.hospitalSafetyStack.eventsTable.tableName;
envVars.ANALYSIS_TABLE_NAME = this.hospitalSafetyStack.analysisTable.tableName;
envVars.ALERT_SNS_TOPIC_ARN = this.hospitalSafetyStack.alertTopic.topicArn;
```

### Example 2: Medical Coding Agent (S3 + OpenSearch + Knowledge Base)

**Pattern**: RAG system with semantic search over medical codes

**Infrastructure** (`medical-coding-stack.ts`):
- S3 bucket: `knowledgeBaseBucket` (ICD-10, CPT, HCPCS codes)
- OpenSearch Serverless collection: `opensearchCollection` (vector search)
- IAM role for Bedrock Knowledge Base
- Security policies (encryption, network, data access)

**Key Code:**
```typescript
// S3 bucket with unique name (account ID suffix)
this.knowledgeBaseBucket = new s3.Bucket(this, 'KnowledgeBaseBucket', {
  bucketName: `${props.stackNameBase}-medical-kb-${cdk.Aws.ACCOUNT_ID}`,
  encryptionKey: props.dataEncryptionKey,
  encryption: s3.BucketEncryption.KMS,
});

// OpenSearch collection with short name (≤32 chars)
this.opensearchCollection = new opensearchserverless.CfnCollection(
  this, 'KBCollection',
  { name: `medical-kb`, type: 'VECTORSEARCH' }
);

// Grant S3 read access
this.knowledgeBaseBucket.grantRead(agentCoreRole);
```

**Environment Variables:**
```typescript
// Knowledge Base ID passed via CDK context
const manualKbId = this.node.tryGetContext("knowledgeBaseId");
if (manualKbId) {
  envVars.KNOWLEDGE_BASE_ID = manualKbId;
}
```

**Note:** Knowledge Base must be created manually via AWS Console due to OpenSearch Serverless policy propagation timing issues with CloudFormation. See `MANUAL_KB_SETUP.md`.

### Example 3: Clinical Decision Support (No Nested Stack)

**Pattern**: Agent that only uses AgentCore Gateway tools

**Infrastructure**: None - uses backend stack only

**Key Code:**
```typescript
// No nested stack created
// Only Runtime + Memory + Gateway tools

// In config.yaml:
patterns:
  - pattern: clinical-decision-support
    deployment_type: docker
    enabled: true
```

This pattern demonstrates that not every agent needs dedicated infrastructure.

## Troubleshooting Common Issues

### Issue 1: OpenSearch Serverless Name Too Long

**Error:**
```
expected maxLength: 32, actual: 37
Resource: healthcare-agents-stack-medical-kb-enc
```

**Cause:** OpenSearch Serverless has a 32-character limit for collection and policy names.

**Fix:** Use short names without the stack name prefix:
```typescript
// ❌ Wrong - too long
name: `${props.stackNameBase}-medical-kb-enc`

// ✅ Correct - under 32 chars
name: `medical-kb-enc`
```

### Issue 2: S3 Bucket Already Exists

**Error:**
```
healthcare-agents-stack-medical-codes-kb already exists (Service: S3)
```

**Cause:** S3 bucket names are globally unique across all AWS accounts.

**Fix:** Add account ID suffix to make bucket name unique:
```typescript
bucketName: `${props.stackNameBase}-medical-kb-${cdk.Aws.ACCOUNT_ID}`
```

### Issue 3: Wrong AWS Account Deployment

**Error:** Stacks deploying to account 000000000000 instead of 000000000000

**Cause:** Environment variable `AWS_PROFILE` overrides CLI `--profile` flag.

**Fix:** Explicitly set AWS_PROFILE before deployment:
```bash
export AWS_PROFILE=quicksuite
npm run deploy
```

### Issue 4: Dockerfile COPY Paths Incorrect

**Error:**
```
COPY failed: file not found in build context
```

**Cause:** Dockerfile expects pattern directory as build context, but backend-stack uses project root.

**Fix:** Use paths relative to project root:
```dockerfile
# ❌ Wrong - expects pattern directory as context
COPY requirements.txt .
COPY ../../gateway/ gateway/

# ✅ Correct - project root as context
COPY patterns/my-agent/requirements.txt .
COPY gateway/ gateway/
```

### Issue 5: Runtime Can't Access Resources

**Error:** Agent code throws permission denied errors

**Cause:** IAM permissions not granted in nested stack.

**Fix:** Ensure you grant permissions to agentCoreRole:
```typescript
if (props.agentCoreRoleArn) {
  const agentCoreRole = iam.Role.fromRoleArn(
    this,
    'AgentCoreRole',
    props.agentCoreRoleArn
  );

  // Must grant permissions!
  this.myTable.grantReadWriteData(agentCoreRole);
}
```

### Issue 6: Environment Variables Not Set

**Error:** Agent code throws KeyError: 'MY_TABLE_NAME'

**Cause:** Environment variables not set in backend-stack.

**Fix:** Check that you're setting env vars from nested stack:
```typescript
// In backend-stack.ts
if (this.myNewAgentStack) {
  envVars.MY_TABLE_NAME = this.myNewAgentStack.myTable.tableName;
}
```

## Best Practices

1. **Resource Naming:**
   - Keep OpenSearch names ≤32 characters
   - Add account ID to S3 bucket names for uniqueness
   - Use descriptive prefixes (e.g., `medical-kb`, `claims-kb`)

2. **Security:**
   - Always use customer-managed KMS keys for encryption
   - Enable point-in-time recovery for DynamoDB tables
   - Set retention policies (RETAIN for production data)
   - Block all public access for S3 buckets

3. **IAM Permissions:**
   - Grant least-privilege permissions
   - Use `.grant*()` methods instead of custom policies
   - Always check if `agentCoreRoleArn` is provided before granting

4. **Docker:**
   - Use project root as build context
   - Copy shared code (gateway/, tools/) for all patterns
   - Keep Dockerfile patterns consistent across agents

5. **Testing:**
   - Deploy to dev account first
   - Verify CloudFormation stacks created successfully
   - Test agent invocations with sample data
   - Check CloudWatch logs for errors

6. **Documentation:**
   - Add comments explaining complex IAM grants
   - Document manual setup steps (like Knowledge Base creation)
   - Update this README when adding new patterns

## Summary

To add a new agent pattern with dedicated infrastructure:

1. ✅ Create agent code and Dockerfile (use project root context)
2. ✅ Create nested stack with your AWS resources
3. ✅ Grant IAM permissions to `agentCoreRoleArn`
4. ✅ Expose resources as public properties
5. ✅ Update backend-stack to create nested stack and set env vars
6. ✅ Enable pattern in config.yaml
7. ✅ Deploy and verify

The 3-part handshake (IAM permissions → env vars → runtime execution) ensures your agent can securely access the resources it needs without hardcoding credentials.
```

