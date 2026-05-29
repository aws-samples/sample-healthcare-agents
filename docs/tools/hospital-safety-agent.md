# Hospital Safety Agent

Multi-agent AI system for analyzing healthcare safety events as a Lambda-based Gateway target.

## Tool

**analyze_safety_event** - Analyzes medication errors, patient falls, infections, and device malfunctions using specialized sub-agents.

## Architecture

**Pattern:** Multi-agent orchestration via Strands
- **Classifier Agent** - Categorizes event type and severity
- **Falls Prevention Agent** - Analyzes fall incidents
- **Infection Control Agent** - Evaluates infection risks
- **Medication Safety Agent** - Reviews medication errors
- **Orchestrator** - Routes to appropriate specialist and aggregates results

## Implementation

**Location:** `gateway/tools/hospital_safety_agent/`
- `safety_agent_lambda.py` - Lambda wrapper invoking AgentCore Runtime
- `tool_spec.json` - MCP tool specification
- Full agent code in `patterns/hospital-safety-agent/`

## Usage

```python
# External MCP client
response = gateway.call_tool(
    "hospital-safety-agent___analyze_safety_event",
    {
        "prompt": "Patient fell in room 204 at 3am. No injuries reported. Bed alarm was not activated."
    }
)

# Response includes:
# - Event classification (type, severity)
# - Detailed analysis from specialist agent
# - Recommended actions
# - Routing information for hospital staff
```

## Configuration

Set agent pattern in `infra-cdk/config.yaml`:
```yaml
backend:
  pattern: hospital-safety-agent
```

## Response Format

```json
{
  "status": "success",
  "event_id": "evt_abc123",
  "classification": {
    "event_type": "patient_fall",
    "severity": "moderate",
    "requires_immediate_action": true
  },
  "analysis": {
    "findings": "...",
    "risk_factors": [...],
    "recommendations": [...]
  }
}
```

## Related

- [Tools Overview](overview.md)
- Pattern code: `patterns/hospital-safety-agent/`
