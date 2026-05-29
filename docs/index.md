# Healthcare Agents on AgentCore - Documentation

Production-ready healthcare AI agents solution using AWS Bedrock AgentCore.

## Quick Links

- **🚀 Getting Started:** [DEPLOYMENT.md](DEPLOYMENT.md) - Deploy your first agent
- **⚙️ Configuration:** [AGENT_CONFIGURATION.md](AGENT_CONFIGURATION.md) - Configure agents
- **🏗️ Architecture:** [architecture/GATEWAY.md](architecture/GATEWAY.md) - System architecture
- **🏥 Epic FHIR:** [epic/](epic/) - Production EHR integration

## Documentation Structure

### 📋 Core Guides

**Getting Started:**
- [DEPLOYMENT.md](DEPLOYMENT.md) - Complete deployment guide (CDK, frontend, backend)
- [AGENT_CONFIGURATION.md](AGENT_CONFIGURATION.md) - Agent configuration and patterns

**Healthcare Patterns:**
- [CLAIMS_AGENTS_SUMMARY.md](CLAIMS_AGENTS_SUMMARY.md) - Claims assembly & submission agents
- [CLAIMS_AGENTS_DEPLOYMENT.md](CLAIMS_AGENTS_DEPLOYMENT.md) - Claims agents deployment

### 🏗️ Architecture

**Core Components:**
- [GATEWAY.md](architecture/GATEWAY.md) - AgentCore Gateway, Lambda targets, MCP protocol
- [MEMORY_INTEGRATION.md](architecture/MEMORY_INTEGRATION.md) - AgentCore Memory integration
- [STREAMING.md](architecture/STREAMING.md) - Streaming responses and real-time updates

**Infrastructure:**
- [QUICKSIGHT_VPC_SETUP.md](QUICKSIGHT_VPC_SETUP.md) - QuickSight VPC configuration for analytics

### 🏥 Epic FHIR Integration

Complete production EHR integration guide:

- **📚 [Epic FHIR Overview](epic/EPIC_FHIR_INTEGRATION_README.md)** - Start here! Implementation summary
- **🔧 [Setup Guide](epic/EPIC_FHIR_SETUP.md)** - App registration and credentials
- **🚀 [Customer Deployment](epic/EPIC_FHIR_CUSTOMER_DEPLOYMENT.md)** - Production deployment (Epic Hosted vs Self-Hosted)
- **💻 [CDK Integration](epic/EPIC_FHIR_CDK_INTEGRATION.md)** - Infrastructure code and deployment

**Key Features:**
- OAuth 2.0 Backend Service authentication with JWT
- FHIR R4 API client for Epic sandbox and production
- Four main functions: Patient demographics, Medications, Allergies, Observations
- Supports both Epic-hosted (cloud) and self-hosted (on-premises) deployments
- Complete VPN, Direct Connect, and PrivateLink setup guides

### 🔧 Tools

**Available Tools:**
- [overview.md](tools/overview.md) - All available gateway tools
- [healthlake-tools.md](tools/healthlake-tools.md) - AWS HealthLake FHIR tools (7 tools)
- [hospital-safety-agent.md](tools/hospital-safety-agent.md) - Multi-agent safety analysis
- [sample-tool.md](tools/sample-tool.md) - Example tool implementation

**Epic FHIR Tools** (via Gateway):
- `get_patient()` - Patient demographics and identifiers
- `get_medications()` - Active medication orders
- `get_allergies()` - Allergy and intolerance records
- `get_observations()` - Vitals and laboratory results

### ⚙️ Operations

**Development:**
- [TOOL_AC_CODE_INTERPRETER.md](operations/TOOL_AC_CODE_INTERPRETER.md) - Code interpreter tool usage

## What's Deployed

### Gateway Targets (3)

1. **sample-tool-target** - Text analysis example
2. **hospital-safety-agent** - Multi-agent safety event analysis
3. **healthlake-tools** - 7 FHIR EHR tools (conditions, medications, observations, allergies, appointments, search, everything)

### Runtime

- **healthcare_agents_stack_StrandsAgent** - Strands-based agent runtime with memory integration

## Stack Configuration

Current setup (`infra-cdk/config.yaml`):

```yaml
stack_name_base: healthcare-agents-stack

backend:
  pattern: hospital-safety-agent
  deployment_type: docker

  healthlake:
    read_only_mode: true
    region: us-east-1
    datastore_id: '3aec3833b094687baabc7def9b85976b'
```

## Key Features

- ✅ Lambda-based Gateway targets with independent scaling
- ✅ OAuth2 authentication via Cognito
- ✅ External MCP client support (Claude Desktop, Cursor)
- ✅ AgentCore Memory integration
- ✅ Streaming support
- ✅ Read-only HealthLake mode for production safety
- ✅ Multi-agent orchestration (Strands)

## Getting Help

- Check specific documentation sections above
- Review [GATEWAY.md](architecture/GATEWAY.md) troubleshooting section
- Check CloudWatch logs for Lambda and Gateway operations
