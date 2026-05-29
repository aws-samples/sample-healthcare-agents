# Tests

This directory contains all tests for the healthcare agents project.

## Structure

```
tests/
├── unit/                          # Unit tests (no AWS dependencies)
│   ├── patterns/
│   │   └── hospital_safety/
│   │       ├── test_classification_model.py
│   │       ├── test_event_storage.py
│   │       └── test_severity_scoring.py
│   ├── test_comprehend_medical.py
│   └── test_b2bi_integration.py
├── integration/                   # Integration tests (require deployed stack)
│   ├── gateway/
│   │   └── test_safety_agent_gateway.py
│   ├── runtime/
│   │   ├── test_safety_agent_runtime.py
│   │   └── test_langgraph_single_agent_runtime.py
│   ├── test_claims_submission_agent.py
│   ├── test_claims_assembly_agent.py
│   ├── test_medical_coding_gateway.py
│   ├── test_b2bi_workflow.py
│   └── test_knowledge_base.py
├── evaluation/                    # LLM-as-judge evaluation pipeline (Langfuse)
│   ├── golden_sets/              # Curated test cases per agent
│   │   ├── hospital_safety.py        # 20 incidents
│   │   ├── prior_authorization.py    # 15 cases
│   │   ├── medical_coding.py         # 18 cases
│   │   ├── claims_assembly.py        # 12 cases
│   │   ├── eligibility_verification.py # 10 cases
│   │   ├── claims_submission.py      # 7 cases
│   │   └── appeals.py               # 10 cases
│   ├── run_experiment.py         # Run eval for any agent (--agent flag)
│   ├── run_e2e_workflow.py       # End-to-end 6-agent chained workflow test
│   ├── judge_prompt.py           # Per-agent LLM-as-judge rubrics
│   ├── setup_langfuse.py         # Create Langfuse score configs
│   ├── upload_golden_sets.py     # Upload golden sets to Langfuse
│   ├── check_gates.py            # Deployment gate checker (CI/CD)
│   ├── buildspec-eval.yml        # CodeBuild spec for eval stage
│   └── RCM_TEST_HARNESS_PLAN.md  # Implementation plan & status
├── conftest.py                    # Shared pytest fixtures
├── pytest.ini                     # Pytest configuration
└── requirements.txt               # Test dependencies
```

## Setup

### Install Test Dependencies

```bash
# From the tests directory
cd tests
pip install -r requirements.txt
```

Or install in a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Running Tests with Pytest

### All Tests
```bash
# From project root
pytest tests/

# With verbose output
pytest tests/ -v

# With coverage report
pytest tests/ --cov=patterns --cov-report=html
```

### Unit Tests Only (Fast - No AWS Required)
```bash
# Run all unit tests
pytest tests/unit -m unit -v

# Run specific test file
pytest tests/unit/patterns/hospital_safety/test_classification_model.py -v

# Run specific test class
pytest tests/unit/patterns/hospital_safety/test_classification_model.py::TestSafetyEventClassification -v

# Run specific test
pytest tests/unit/patterns/hospital_safety/test_severity_scoring.py::TestSeverityScoring::test_critical_severity_score -v
```

### Integration Tests Only (Requires Deployed Stack)
```bash
# Set AWS profile
export AWS_PROFILE=quicksuite

# Run all integration tests
pytest tests/integration -m integration -v

# Run Gateway tests only
pytest tests/integration/gateway -v

# Run Runtime tests only
pytest tests/integration/runtime -v
```

### Run Tests with Markers
```bash
# Run only unit tests
pytest -m unit

# Run only integration tests
pytest -m integration

# Run slow tests
pytest -m slow

# Exclude integration tests
pytest -m "not integration"
```

## Running Tests Without Pytest

You can still run integration tests directly as Python scripts:

```bash
cd tests/integration/gateway
export AWS_PROFILE=quicksuite
python3 test_safety_agent_gateway.py
```

## Test Types

### Unit Tests (`tests/unit/`)
**Characteristics:**
- Fast execution (< 100ms per test)
- No AWS dependencies
- Use mocks for external calls
- Test business logic in isolation

**Examples:**
- Pydantic model validation
- Severity scoring algorithms
- Data structure validation
- Risk assessment logic

**Run with:** `pytest tests/unit -m unit`

### Integration Tests (`tests/integration/`)
**Characteristics:**
- Test deployed system end-to-end
- Require AWS resources deployed
- Make real API calls
- Slower execution (seconds to minutes)

**Prerequisites:**
- Deployed healthcare-agents-stack
- Valid AWS credentials
- Cognito configuration in SSM

**Run with:** `pytest tests/integration -m integration`

## Pytest Fixtures

Shared fixtures are defined in `conftest.py`:

### Unit Test Fixtures
- `sample_fall_event` - Patient fall event text
- `sample_medication_error` - Medication error event text
- `sample_infection_event` - Infection control event text
- `sample_classification` - Event classification dict
- `sample_event_id` - Generated event ID
- `mock_dynamodb_table` - Mocked DynamoDB table

### Integration Test Fixtures
- `aws_region` - AWS region
- `stack_name` - CloudFormation stack name
- `gateway_url` - Gateway URL from SSM
- `runtime_arn` - Runtime ARN from CloudFormation
- `cognito_config` - Cognito configuration
- `oauth_token` - OAuth token for Gateway auth

## CI/CD Integration

### Pre-commit (Local Development)
```bash
# Run unit tests only (fast feedback)
pytest tests/unit -m unit
```

### Pull Request Pipeline
```bash
# Run all tests
pytest tests/ -m "unit or integration" --cov=patterns --cov-report=xml
```

### Main Branch (After Merge)
```bash
# Run full test suite with coverage
pytest tests/ --cov=patterns --cov-report=html --cov-report=term
```

## Pattern-Specific Tests

Pattern-specific tests remain in their pattern directories for co-location with the code:
- `/patterns/hospital-safety-agent/tests/` - Hospital safety agent tests

These are useful during pattern development for rapid iteration. The main `tests/` directory
contains standardized tests for CI/CD and cross-pattern validation.

## Troubleshooting

### pytest not found
```bash
pip install -r tests/requirements.txt
```

### AWS credentials error
```bash
export AWS_PROFILE=quicksuite
aws sts get-caller-identity  # Verify credentials
```

### Integration tests fail
Ensure the stack is deployed:
```bash
cd infra-cdk
npm run cdk deploy
```

### Import errors
Add project root to PYTHONPATH:
```bash
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```
