# HealthLake Tools

Lambda-based Gateway target providing 7 FHIR EHR tools for AWS HealthLake integration.

## Tools

1. **get_patient_conditions** - Medical conditions and diagnoses
2. **get_patient_medications** - Active medications
3. **get_patient_observations** - Lab results and vital signs
4. **get_patient_allergies** - Allergies and intolerances
5. **get_patient_appointments** - Scheduled appointments
6. **advanced_patient_search** - FHIR patient search with demographics/age filters
7. **get_patient_everything** - Comprehensive patient record via FHIR `$everything`

## Configuration

**Location:** `infra-cdk/config.yaml`

```yaml
backend:
  healthlake:
    read_only_mode: true          # Blocks write operations
    region: us-east-1             # HealthLake datastore region
    datastore_id: 'your-id-here'  # FHIR datastore ID
```

## Implementation

**Lambda:** `infra-cdk/lambdas/healthlake-tools/`
- `healthlake_lambda.py` - Handler with all 7 tools
- `tool_spec.json` - MCP tool specifications
- `requirements.txt` - Dependencies (boto3, requests)

**Key Features:**
- Direct FHIR API calls with SigV4 authentication
- Multi-tool Lambda (routes on tool name from context)
- Read-only mode safety for production

## Usage Examples

### From External MCP Client

```python
# Get patient conditions
response = gateway.call_tool(
    "healthlake-tools___get_patient_conditions",
    {"patient_id": "04c704c4-5d2d-4308-9c33-1690a6e47a6b"}
)

# Advanced search
response = gateway.call_tool(
    "healthlake-tools___advanced_patient_search",
    {
        "search_params": {
            "birthdate": "1950-01-01",
            "gender": "male"
        }
    }
)
```

### From AgentCore Runtime

Tools automatically available to agents via Gateway.

## IAM Permissions

Lambda has read-only HealthLake permissions:
```json
{
  "Action": [
    "healthlake:ListFHIRDatastores",
    "healthlake:DescribeFHIRDatastore",
    "healthlake:ReadResource",
    "healthlake:SearchWithGet",
    "healthlake:SearchWithPost"
  ]
}
```

Write permissions conditionally added when `read_only_mode: false`.

## Testing

```bash
# Direct Lambda test
aws lambda invoke \
  --function-name healthcare-agents-stack-healthlake-tools \
  --payload '{"action_name": "get_patient_conditions", "patient_id": "123"}' \
  output.json

# Via Gateway (requires OAuth token)
python3 test_gateway.py
```

## Troubleshooting

**"Tool name not provided"** - Handler expects tool name in `context.client_context.custom['bedrockAgentCoreToolName']`

**403 HealthLake errors** - Check Lambda IAM role has HealthLake permissions

**Empty results** - Verify datastore_id and patient_id are correct

## Related

- [Tools Overview](overview.md)
- [Gateway Architecture](../architecture/GATEWAY.md)
