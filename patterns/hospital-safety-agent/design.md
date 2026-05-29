# Hospital Safety Agent System - Design Document

## Executive Summary

Multi-agent system for processing hospital safety events using Strands framework on AWS AgentCore. Events uploaded to S3 trigger classification and routing to specialized safety agents for analysis and action.

---

## System Architecture

```
S3 Upload → Lambda Trigger → Orchestrator Agent → Specialized Agents → DynamoDB Storage
                                     ↓
                              (Classification)
                                     ↓
                    ┌────────────────┼────────────────┐
                    ↓                ↓                ↓
            Medication Agent  Infection Agent  Falls Agent
                    ↓                ↓                ↓
              Alert/Queue      Alert/Queue     Alert/Queue
```

---

## Agent Design

### **1. Orchestrator Agent (Supervisor)**
**Role**: Receives safety event, classifies type, routes to specialist

**Tools**:
- `classify_event` - Extract event type and entities
- `route_to_specialist` - Invoke appropriate specialist agent
- `store_event` - Save to DynamoDB

**Input**: Raw safety event text from S3
**Output**: Routed event with classification metadata

---

### **2. Medication Safety Agent**
**Specialization**: Medication errors, drug interactions, dosing issues

**Tools**:
- `check_drug_database` - Verify medication details
- `assess_severity` - Rate error criticality (1-5)
- `create_alert` - Generate alerts for critical events

**Output**: Analysis + severity + recommended actions

---

### **3. Infection Control Agent**
**Specialization**: HAIs, contamination, hygiene violations

**Tools**:
- `check_infection_patterns` - Query historical data
- `assess_outbreak_risk` - Calculate risk score
- `notify_infection_team` - Alert infection control

**Output**: Risk assessment + outbreak indicators

---

### **4. Patient Falls Agent**
**Specialization**: Fall events, injury assessment, prevention

**Tools**:
- `assess_injury` - Determine injury severity
- `check_prevention_protocol` - Verify protocols followed
- `update_fall_risk` - Update patient risk profile

**Output**: Injury assessment + protocol compliance

---

## Data Flow

### **Phase 1: Event Ingestion**
1. Safety report uploaded to S3 bucket
2. S3 event notification triggers Lambda
3. Lambda reads file, extracts text
4. Invokes Orchestrator Agent via AgentCore Runtime

### **Phase 2: Classification & Routing**
1. Orchestrator classifies event type
2. Extracts key entities (patient ID, location, time)
3. Routes to appropriate specialist agent
4. Stores classification in DynamoDB

### **Phase 3: Specialist Analysis**
1. Specialist agent analyzes event details
2. Queries relevant tools/databases
3. Generates severity score and recommendations
4. Creates alerts if needed

### **Phase 4: Storage & Action**
1. Store analysis results in DynamoDB
2. Send critical alerts to SNS topic
3. Add to review queue (if needed)
4. Update analytics dashboard

---

## Technology Stack

### **Core Infrastructure**
- **Agent Framework**: Strands (multi-agent orchestration)
- **Runtime**: AWS Bedrock AgentCore Runtime
- **Model**: Claude Sonnet 4.5
- **Memory**: AgentCore Memory (conversation history)

### **AWS Services**
- **S3**: Safety event document storage
- **Lambda**: Event processing trigger
- **DynamoDB**: Event and analysis storage
- **SNS**: Critical alert notifications
- **API Gateway**: Optional REST API for queries

### **Integration**
- **MCP Gateway**: Tools via Lambda targets
- **Code Interpreter**: Data analysis/calculations

---

## Implementation Phases

### **Phase 1: Foundation**
- [ ] Create `patterns/hospital-safety-agent/` directory
- [ ] Build Orchestrator Agent with classification
- [ ] Set up S3 bucket and Lambda trigger
- [ ] Create DynamoDB tables (events, analysis)

### **Phase 2: Specialist Agents**
- [ ] Implement Medication Safety Agent
- [ ] Implement Infection Control Agent
- [ ] Implement Patient Falls Agent
- [ ] Create Gateway tools for each agent

### **Phase 3: Integration**
- [ ] Connect agents via Strands orchestration
- [ ] Build routing logic in Orchestrator
- [ ] Set up SNS alerting
- [ ] Add DynamoDB storage handlers

### **Phase 4: Testing & UI**
- [ ] End-to-end testing with sample events
- [ ] Build frontend dashboard for event review
- [ ] Add analytics queries
- [ ] Deploy to production

---

## Data Models

### **Event Record (DynamoDB)**
```json
{
  "event_id": "evt_123",
  "timestamp": "2026-01-16T18:30:00Z",
  "event_type": "medication_error",
  "raw_text": "...",
  "classification": {
    "type": "medication",
    "severity": "high",
    "entities": {...}
  },
  "status": "pending_review"
}
```

### **Analysis Record (DynamoDB)**
```json
{
  "analysis_id": "anl_456",
  "event_id": "evt_123",
  "agent": "medication_safety",
  "severity_score": 4,
  "findings": "...",
  "recommendations": [...],
  "alerts_sent": true,
  "timestamp": "2026-01-16T18:31:00Z"
}
```

---

## Success Metrics

- **Event Processing Time**: < 30 seconds from upload to analysis
- **Classification Accuracy**: > 95%
- **Alert Response Time**: < 5 minutes for critical events
- **Agent Availability**: 99.9% uptime

---

## Security & Compliance

- **PHI Protection**: All data encrypted at rest (S3, DynamoDB)
- **Access Control**: IAM roles with least privilege
- **Audit Logging**: CloudWatch logs for all agent actions
- **HIPAA Compliance**: Enable encryption, audit trails, access logs

---

## Next Steps

1. Review and approve this design
2. Create detailed implementation plan for Phase 1
3. Set up development environment
4. Begin building Orchestrator Agent

---

## Questions to Resolve

- What database/API contains drug information?
Use FDA's drug API - OpenAPI schema is at  drug-api.json

- How should critical alerts be delivered? (SNS → Email/PagerDuty?)
SNS -> email (setup safety@example.com)
- What severity thresholds trigger alerts?
High
- Should we integrate with existing hospital systems?
Not now
