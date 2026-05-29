# Hospital Safety Agent System

Multi-agent system for processing and analyzing hospital safety events using Strands framework on AWS AgentCore.

## Overview

This pattern implements a supervisor-specialist multi-agent architecture for hospital safety event processing:

- **Orchestrator Agent**: Classifies events and routes to specialists
- **Medication Safety Agent**: Analyzes medication errors and drug safety
- **Infection Control Agent**: Analyzes HAIs and contamination events
- **Patient Falls Agent**: Analyzes fall events and injury prevention

## Architecture

```
Safety Event → Orchestrator → Classification → Specialist Agent → Analysis → Storage/Alerts
                    ↓                              ↓
              Store Event                    Store Analysis
                                                   ↓
                                            Alert if High Severity
```

## Agent Capabilities

### Orchestrator Agent (`orchestrator.py`)
**Role**: Event intake, classification, and routing

**Tools**:
- `classify_safety_event` - Determine event type and severity
- `store_event` - Save to DynamoDB
- `store_analysis` - Save specialist analysis

**Routing Logic**:
- Medication keywords → Medication Agent
- Infection keywords → Infection Agent
- Fall keywords → Falls Agent

---

### Medication Safety Agent (`agents/medication_agent.py`)
**Specialization**: Medication errors, drug interactions, dosing issues

**Tools**:
- `check_drug_database` - Query FDA OpenFDA API for drug info
- `assess_medication_severity` - Score error severity (1-5)

**Event Types Handled**:
- Wrong drug, dose, patient, time, route
- Drug interactions
- Adverse drug reactions

---

### Infection Control Agent (`agents/infection_agent.py`)
**Specialization**: Healthcare-associated infections, contamination

**Tools**:
- `check_infection_patterns` - Query historical data for clusters
- `assess_outbreak_risk` - Calculate outbreak risk score

**Event Types Handled**:
- CAUTI, CLABSI, SSI, VAP
- C.diff, MRSA, VRE outbreaks
- Contamination events

---

### Patient Falls Agent (`agents/falls_agent.py`)
**Specialization**: Patient falls, injury assessment, prevention

**Tools**:
- `assess_fall_injury` - Determine injury severity
- `check_fall_prevention_protocol` - Verify prevention compliance

**Event Types Handled**:
- Falls from bed, chair, standing
- Injury assessment
- Fall risk evaluation

## Deployment

### 1. CDK Configuration

The configuration has been set in `infra-cdk/config.yaml`:

```yaml
backend:
  pattern: hospital-safety-agent
  deployment_type: docker
```

The Hospital Safety infrastructure is automatically deployed as part of the FAST backend stack. The infrastructure stack is located at `infra-cdk/lib/patterns/hospital-safety/hospital-safety-stack.ts`.

### 2. Deploy

```bash
cd infra-cdk
cdk deploy --all
```

This will deploy:
- AgentCore Runtime with hospital safety agents (single container with orchestrator + specialists)
- DynamoDB tables for events and analysis
- SNS topic for critical alerts (email: safety@example.com)
- All IAM permissions and environment variables

### 3. Test the Agent

Access via the frontend at your Amplify URL or invoke directly via AgentCore Runtime.

**Example Safety Event**:
```
A nurse administered 20mg of Lasix instead of the prescribed 10mg to patient
in room 302. Patient experienced no immediate adverse effects but blood pressure
dropped to 90/60. Medication error discovered during shift change.
```

## Event Flow

### 1. Event Submission
Safety event text is submitted to the orchestrator agent

### 2. Classification
Orchestrator analyzes text and determines:
- Event type (medication/infection/fall)
- Initial severity (low/medium/high/critical)
- Key entities (patient, location, time)

### 3. Specialist Analysis
Event is routed to appropriate specialist who:
- Uses specialized tools to analyze
- Queries external APIs (FDA) or internal data
- Generates severity score and recommendations

### 4. Storage & Alerting
- Event and analysis stored in DynamoDB
- High/critical severity triggers SNS alert
- Results available for review and analytics

## Data Models

### Event Record (DynamoDB: `hospital-safety-events`)
```json
{
  "event_id": "evt_abc123",
  "timestamp": "2026-01-16T20:00:00Z",
  "event_type": "medication_error",
  "severity": "high",
  "raw_text": "...",
  "classification": {...},
  "status": "pending_analysis"
}
```

### Analysis Record (DynamoDB: `hospital-safety-analysis`)
```json
{
  "analysis_id": "anl_def456",
  "event_id": "evt_abc123",
  "agent": "medication_safety",
  "timestamp": "2026-01-16T20:01:00Z",
  "severity_score": 4,
  "analysis": {...},
  "recommendations": [...]
}
```

## Alert Configuration

High and critical severity events trigger SNS alerts sent to:
- **Email**: safety@example.com (configured in design.md)

To add more recipients, update the SNS topic subscription in CDK.

## Integration with FDA Drug API

The Medication Safety Agent integrates with FDA's OpenFDA API:
- **API**: https://api.fda.gov/drug/label.json
- **Schema**: See `drug-api.json` for OpenAPI specification
- **No authentication required** for basic queries
- **Rate limit**: 240 requests per minute

## Development

### Adding New Specialist Agents

1. Create new agent file in `agents/` directory
2. Implement agent with `@tool` decorated functions
3. Add routing logic in `orchestrator.py`
4. Update this README

### Testing Locally

```bash
# From repository root
cd patterns/hospital-safety-agent

# Run orchestrator directly
python orchestrator.py
```

## Future Enhancements

- [ ] S3 trigger for document upload
- [ ] Device malfunction specialist agent
- [ ] Analytics dashboard
- [ ] Historical trend analysis
- [ ] Integration with hospital EMR systems
- [ ] Real-time alerting via PagerDuty

## Security & Compliance

- **PHI Protection**: All data encrypted at rest and in transit
- **Access Control**: IAM roles with least privilege
- **Audit Logging**: CloudWatch logs for all agent actions
- **HIPAA Compliance**: Encryption, audit trails enabled

## References

- [Design Document](./design.md)
- [FAST Documentation](../../README.md)
- [Strands Framework](https://strandsagents.com)
- [AgentCore Documentation](https://docs.aws.amazon.com/bedrock-agentcore)
