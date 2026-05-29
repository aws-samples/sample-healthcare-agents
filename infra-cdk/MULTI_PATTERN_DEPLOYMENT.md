# Multi-Pattern Deployment Guide

## Overview

The Healthcare Agents infrastructure now supports deploying **multiple agent patterns simultaneously** as separate backend stacks. This allows you to run different types of agents (hospital-safety, medical-coding, etc.) in the same environment, sharing common infrastructure like Cognito authentication and Amplify frontend.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  healthcare-agents-stack (Shared Infrastructure)            │
│  - Amplify Hosting (Frontend)                               │
│  - Cognito User Pool (Authentication)                       │
└─────────────────────────────────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ Pattern 1    │  │ Pattern 2    │  │ Pattern 3    │
│ Backend      │  │ Backend      │  │ Backend      │
│              │  │              │  │              │
│ - Runtime    │  │ - Runtime    │  │ - Runtime    │
│ - Memory     │  │ - Memory     │  │ - Memory     │
│ - Gateway    │  │ - Gateway    │  │ - Gateway    │
│ - Tools      │  │ - Tools      │  │ - Tools      │
└──────────────┘  └──────────────┘  └──────────────┘
```

## Configuration

Edit `infra-cdk/config.yaml` to enable multiple patterns:

```yaml
stack_name_base: healthcare-agents-stack

backend:
  # Multiple pattern deployment
  patterns:
    - pattern: hospital-safety-agent
      deployment_type: docker
      enabled: true

    - pattern: medical-coding-agent
      deployment_type: docker
      enabled: true

    # Add more patterns as needed
    - pattern: strands-single-agent
      deployment_type: zip
      enabled: false  # Disabled - won't be deployed

  # Shared configuration for all patterns
  healthlake:
    read_only_mode: true
    region: us-east-1
    datastore_id: '3aec3833b094687baabc7def9b85976b'
```

### Configuration Options

- **`pattern`**: The agent pattern directory name from `patterns/` folder
  - Available: `hospital-safety-agent`, `medical-coding-agent`, `strands-single-agent`, `langgraph-single-agent`

- **`deployment_type`**: How to package the agent code
  - `docker`: Container-based deployment (recommended for production)
  - `zip`: ZIP package deployment (faster for development)

- **`enabled`**: Set to `false` to temporarily disable a pattern without removing it

## Deployed Resources

### Shared Resources (1 set)
- **Main Stack**: `healthcare-agents-stack`
  - Amplify App (Frontend)
  - Cognito User Pool
  - Cognito User Pool Client

### Per-Pattern Resources
Each enabled pattern gets its own:
- **Backend Stack**: `healthcare-agents-stack-{pattern-name}`
  - AgentCore Runtime (separate runtime per pattern)
  - AgentCore Memory (isolated memory per pattern)
  - AgentCore Gateway + Tools
  - Pattern-specific infrastructure (DynamoDB tables, SNS topics, etc.)
  - Feedback API

### Analytics Stack (Optional)
- **Safety Analysis Stack**: `healthcare-agents-stack-safety-analysis`
  - Aurora Serverless PostgreSQL
  - DynamoDB to Aurora replication lambdas

## Deployment

### Deploy All Patterns

```bash
# Get AWS credentials
./creds-qs.sh

# Deploy everything
cd infra-cdk
export AWS_PROFILE=quicksuite
npm run cdk deploy -- --all
```

### Deploy Specific Pattern

```bash
# Deploy only the hospital safety agent
npm run cdk deploy -- healthcare-agents-stack-hospital-safety-agent

# Deploy only the medical coding agent
npm run cdk deploy -- healthcare-agents-stack-medical-coding-agent
```

### List All Stacks

```bash
npm run cdk list
```

Expected output:
```
Deploying 2 agent pattern(s):
  - hospital-safety-agent (docker)
  - medical-coding-agent (docker)
Creating backend stack: healthcare-agents-stack-hospital-safety-agent
Creating backend stack: healthcare-agents-stack-medical-coding-agent

healthcare-agents-stack
healthcare-agents-stack-hospital-safety-agent
healthcare-agents-stack-medical-coding-agent
healthcare-agents-stack-safety-analysis
```

## Stack Outputs

Each backend stack provides its own outputs:

```bash
# View outputs for a specific pattern
aws cloudformation describe-stacks \
  --stack-name healthcare-agents-stack-hospital-safety-agent \
  --query 'Stacks[0].Outputs' \
  --profile quicksuite
```

Key outputs per pattern:
- **AgentRuntimeArn**: Runtime ARN for invoking this agent
- **MemoryArn**: Memory ARN for this agent's memory
- **FeedbackApiUrl**: Feedback API endpoint for this agent
- **GatewayUrl**: MCP Gateway URL for this agent's tools

## Benefits

1. **Isolation**: Each pattern runs in its own runtime with isolated memory
2. **Independent Scaling**: Scale each agent pattern based on its usage
3. **Cost Optimization**: Deploy only the patterns you need
4. **Easy Testing**: Enable/disable patterns for testing without code changes
5. **Shared Authentication**: All patterns use the same Cognito user pool
6. **Single Frontend**: One Amplify app can interface with multiple agent backends

## Use Cases

### Development Environment
```yaml
patterns:
  - pattern: strands-single-agent
    deployment_type: zip  # Faster deployment
    enabled: true
```

### Production Environment
```yaml
patterns:
  - pattern: hospital-safety-agent
    deployment_type: docker
    enabled: true
  - pattern: medical-coding-agent
    deployment_type: docker
    enabled: true
```

### Testing New Pattern
```yaml
patterns:
  - pattern: existing-production-agent
    deployment_type: docker
    enabled: true
  - pattern: new-experimental-agent
    deployment_type: docker
    enabled: true  # Deploy alongside existing
```

## Migration from Single Pattern

If you have existing configuration:

```yaml
# Old format (still supported for backward compatibility)
backend:
  pattern: medical-coding-agent
  deployment_type: docker
```

This automatically converts to:

```yaml
# New format (recommended)
backend:
  patterns:
    - pattern: medical-coding-agent
      deployment_type: docker
      enabled: true
```

The system automatically handles both formats, so existing deployments continue to work.

## Troubleshooting

### Stack Already Exists
If you're migrating from single-pattern to multi-pattern and get conflicts:

```bash
# The old backend stack was named: healthcare-agents-stack
# New pattern stacks are: healthcare-agents-stack-{pattern-name}

# You may need to destroy the old nested backend stack first
aws cloudformation delete-stack \
  --stack-name healthcare-agents-stack-healthcareagentsstackbackendNestedStack... \
  --profile quicksuite
```

### Pattern Not Deploying
1. Check `enabled: true` in config.yaml
2. Verify pattern directory exists: `patterns/{pattern-name}/`
3. Check logs: `npm run cdk list` shows which patterns are being processed

### Resource Limit Issues
Each pattern creates separate resources. If hitting AWS limits:
- Reduce number of enabled patterns
- Use CloudFormation quotas to check limits
- Consider consolidating patterns into a single routing agent

## Cost Considerations

**Per-Pattern Costs:**
- AgentCore Runtime: Pay per invocation
- AgentCore Memory: Pay per event stored
- Gateway: Pay per API call
- Lambda functions: Pay per execution
- DynamoDB (if used): Pay per request

**Shared Costs (fixed):**
- Cognito: First 50k users free
- Amplify: Pay per build + hosting
- S3: Pay per GB stored

💡 **Tip**: Start with one pattern in production, add more as needed based on actual usage.

## Advanced: Custom Pattern Configuration

You can add pattern-specific configuration by extending the `PatternConfig` interface in `config-manager.ts`:

```typescript
export interface PatternConfig {
  pattern: string
  deployment_type: DeploymentType
  enabled?: boolean
  // Add custom fields here
  memoryTTL?: number
  concurrencyLimit?: number
}
```

Then access in backend-stack.ts:
```typescript
const patternConfig = props.config.backend.patterns?.find(
  p => p.pattern === pattern
)
if (patternConfig?.memoryTTL) {
  // Use custom configuration
}
```
