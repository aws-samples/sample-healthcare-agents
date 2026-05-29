# Gateway Tools Overview

This document provides an overview of all tools available through the AgentCore Gateway in this healthcare agents solution.

## Architecture

All tools are deployed as **Lambda-based Gateway targets** using the MCP (Model Context Protocol). This architecture provides:

- **Independent Scaling**: Each tool scales based on its own usage
- **Separate Deployment**: Update tools without affecting others
- **Tool-Specific Permissions**: Each Lambda has only the IAM permissions it needs
- **Cost Optimization**: Pay only for actual tool execution time

## Available Tools

### 1. Sample Tool Target

**Target Name:** `sample-tool-target`
**Lambda:** `healthcare-agents-stack-h-SampleToolLambda`
**Status:** ✅ Deployed

**Tools:**
- `text_analysis_tool` - Analyzes text and returns word count and character frequency

**Documentation:** [sample-tool.md](sample-tool.md)

**Use Case:** Example implementation showing Lambda target pattern

---

### 2. Hospital Safety Agent

**Target Name:** `hospital-safety-agent`
**Lambda:** `healthcare-agents-stack-hospital-safety-agent`
**Status:** ✅ Deployed

**Tools:**
- `analyze_safety_event` - Multi-agent AI system for analyzing healthcare safety events

**Documentation:** [hospital-safety-agent.md](hospital-safety-agent.md)

**Use Case:** Production multi-agent system for hospital safety officers to analyze and triage safety events (medication errors, patient falls, infections, device malfunctions)

---

### 3. HealthLake Tools

**Target Name:** `healthlake-tools`
**Lambda:** `healthcare-agents-stack-healthlake-tools`
**Status:** ✅ Deployed (Read-Only Mode)

**Tools (7 FHIR EHR Tools):**
1. `get_patient_conditions` - Retrieve patient medical conditions and diagnoses
2. `get_patient_medications` - Get active medications and prescriptions
3. `get_patient_observations` - Query lab results, vital signs, and clinical observations
4. `get_patient_allergies` - Get documented allergies and intolerances
5. `get_patient_appointments` - Retrieve scheduled appointments
6. `advanced_patient_search` - Search patients with advanced FHIR parameters
7. `get_patient_everything` - Get comprehensive patient record using FHIR `$everything`

**Documentation:** [healthlake-tools.md](healthlake-tools.md)

**Use Case:** Production EHR integration for healthcare agents to access patient data from AWS HealthLake FHIR datastores

---

## Tool Naming Convention

Tools are named using the format:
```
{target-name}___{tool-name}
```

**Examples:**
- `sample-tool-target___text_analysis_tool`
- `hospital-safety-agent___analyze_safety_event`
- `healthlake-tools___get_patient_conditions`

## Authentication

All tools require OAuth2 authentication via Cognito:

**Token Endpoint:**
```
https://healthcare-agents-stack-{account-id}-{region}.auth.{region}.amazoncognito.com/oauth2/token
```

**Grant Type:** `client_credentials`

**Scopes:** `healthcare-agents-stack-gateway/read healthcare-agents-stack-gateway/write`

## Access Methods

### 1. From AgentCore Runtime

The AgentCore Runtime automatically discovers and provides tools to agents through the Gateway.

### 2. From External MCP Clients

External clients (Claude Desktop, Cursor, etc.) can connect to the Gateway using MCP protocol:

**Gateway URL:**
```
https://healthcare-agents-stack-gateway-{gateway-id}.gateway.bedrock-agentcore.{region}.amazonaws.com/mcp
```

**Authentication:** Bearer token via OAuth2

**Protocol:** MCP over HTTPS

### 3. Direct Lambda Invocation

For testing or internal services, tools can be invoked directly:

```bash
aws lambda invoke \
  --function-name {lambda-name} \
  --payload '{"action_name": "{tool-name}", "param1": "value1"}' \
  output.json
```

## Adding New Tools

To add a new tool to the Gateway:

1. **Create Lambda Function**
   - Implement handler following the Lambda target pattern (see [GATEWAY.md](../architecture/GATEWAY.md))
   - Parse tool name from `context.client_context.custom['bedrockAgentCoreToolName']`
   - Return response in MCP format

2. **Define Tool Schema**
   - Create `tool_spec.json` with tool definitions
   - Use `inputSchema` (camelCase) not `input_schema`
   - Format: Direct array `[{tool1}, {tool2}]`, not wrapped in object

3. **Update CDK Stack**
   - Add Lambda function in `backend-stack.ts`
   - Create `CfnGatewayTarget` with Lambda configuration
   - Grant necessary IAM permissions
   - Reference tool_spec.json via `inlinePayload`

4. **Deploy**
   ```bash
   cd infra-cdk
   npm run cdk deploy
   ```

5. **Test**
   - List tools via Gateway: `tools/list` MCP method
   - Invoke tool via Gateway: `tools/call` MCP method
   - Check CloudWatch logs for debugging

## Monitoring

### CloudWatch Logs

Each tool has dedicated log groups:

- `/aws/lambda/healthcare-agents-stack-h-SampleToolLambda`
- `/aws/lambda/healthcare-agents-stack-hospital-safety-agent`
- `/aws/lambda/healthcare-agents-stack-healthlake-tools`

### Metrics

Lambda metrics available in CloudWatch:
- Invocations
- Duration
- Errors
- Concurrent Executions
- Throttles

### Gateway Metrics

Gateway operations logged to:
- `/aws/bedrock-agentcore/gateway/*`

## Best Practices

### Lambda Development

1. **Single Responsibility**: Each Lambda should focus on related tools
2. **Error Handling**: Return errors in MCP format with `isError: true`
3. **Logging**: Log all events and tool invocations for debugging
4. **Timeouts**: Set appropriate timeout based on tool complexity
5. **Memory**: Right-size memory allocation for performance/cost

### Tool Design

1. **Clear Descriptions**: Write detailed tool and parameter descriptions
2. **Simple Schemas**: Keep input schemas focused and easy to understand
3. **Validation**: Validate inputs and return helpful error messages
4. **Idempotency**: Design tools to be safely retried
5. **Testing**: Test tools independently before Gateway integration

### Security

1. **Least Privilege**: Grant only required IAM permissions
2. **Input Validation**: Validate all inputs to prevent injection attacks
3. **PII Handling**: Follow HIPAA/PHI guidelines for healthcare data
4. **Audit Logging**: Log all data access for compliance
5. **Read-Only Mode**: Use read-only mode for production data access when possible

## Troubleshooting

### Tool Not Found

**Issue:** Gateway returns "Unknown tool" error

**Solutions:**
1. Verify tool name in Gateway: `tools/list` method
2. Check tool_spec.json format (should be array, not object)
3. Verify Lambda is deployed and accessible
4. Check CloudWatch logs for Lambda errors

### Authentication Failures

**Issue:** 401 Unauthorized errors

**Solutions:**
1. Verify OAuth2 credentials from SSM/Secrets Manager
2. Check token expiration (default: 1 hour)
3. Verify scope includes gateway read/write permissions
4. Test token generation independently

### Lambda Errors

**Issue:** Tool invocation fails with 500 error

**Solutions:**
1. Check Lambda CloudWatch logs for exceptions
2. Verify Lambda has required IAM permissions
3. Test Lambda directly with sample payload
4. Check Lambda timeout and memory configuration

### Performance Issues

**Issue:** Tool invocations are slow

**Solutions:**
1. Review Lambda execution duration in CloudWatch
2. Increase Lambda memory allocation
3. Optimize tool implementation
4. Consider caching for frequently accessed data
5. Use provisioned concurrency for consistent latency

## Related Documentation

- [Gateway Architecture](../architecture/GATEWAY.md) - Detailed Gateway implementation
- [Deployment Guide](../DEPLOYMENT.md) - How to deploy the infrastructure
- [Agent Configuration](../AGENT_CONFIGURATION.md) - Configuring agents to use tools
