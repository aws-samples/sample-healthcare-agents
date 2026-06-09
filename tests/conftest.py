# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Pytest configuration and shared fixtures.

This file provides fixtures and configuration for both unit and integration tests.
"""

import pytest
import boto3
import os
from datetime import datetime
from typing import Dict, Any


# ===== Unit Test Fixtures =====


@pytest.fixture
def sample_fall_event() -> str:
    """Sample patient fall event text for testing."""
    return """
    Patient in room 405 fell from bed at 3:15am during night shift.

    Patient Details:
    - 82 year old female with osteoporosis
    - History of previous falls
    - Day 3 of hospitalization for pneumonia
    - Fall risk assessment: HIGH

    Incident Details:
    - Patient attempted to reach bathroom unassisted
    - Call button was out of reach
    - Bed rails were down
    - No bed alarm was activated

    Injuries:
    - Left hip fracture confirmed via X-ray
    - Left arm bruising
    - Pain level 9/10

    Immediate Actions:
    - Physician notified immediately
    - X-ray ordered
    - Pain medication administered
    - Family contacted
    """.strip()


@pytest.fixture
def sample_medication_error() -> str:
    """Sample medication error event text for testing."""
    return """
    Medication error in room 302. Patient received Warfarin 10mg instead of
    prescribed 5mg dose at 2pm. Nurse noticed error 30 minutes later during
    chart review. Patient is 75 year old male, admitted for atrial fibrillation.
    No bleeding noted at time of discovery. Patient has history of GI bleed.
    Attending physician Dr. Smith notified immediately.
    """.strip()


@pytest.fixture
def sample_infection_event() -> str:
    """Sample infection control event text for testing."""
    return """
    Infection control breach in ICU room 501. Healthcare worker observed entering
    room without proper PPE during care of patient with confirmed MRSA pneumonia.
    Staff member did not wear isolation gown or gloves during wound dressing change
    at 10am. Patient is 68 year old female, ventilated, multiple IV lines and Foley
    catheter in place. Charge nurse witnessed event and immediately intervened.
    """.strip()


@pytest.fixture
def sample_classification() -> Dict[str, Any]:
    """Sample event classification for testing."""
    return {
        "event_type": "medication_error",
        "severity": "high",
        "patient_id": "MRN-12345",
        "location": "Room 302",
        "staff_involved": "Nurse Johnson",
        "requires_immediate_action": True,
        "brief_summary": "Wrong dosage administered",
    }


@pytest.fixture
def sample_event_id() -> str:
    """Generate a sample event ID for testing."""
    import uuid

    return f"evt_{uuid.uuid4().hex[:12]}"


@pytest.fixture
def mock_dynamodb_table(monkeypatch):
    """Mock DynamoDB table for unit tests."""
    from unittest.mock import Mock

    mock_table = Mock()
    mock_table.put_item.return_value = {"ResponseMetadata": {"HTTPStatusCode": 200}}
    mock_table.query.return_value = {"Items": [], "Count": 0}

    return mock_table


# ===== Integration Test Fixtures =====


@pytest.fixture(scope="session")
def aws_region() -> str:
    """AWS region for integration tests."""
    return os.environ.get("AWS_DEFAULT_REGION", "us-east-1")


@pytest.fixture(scope="session")
def stack_name() -> str:
    """CloudFormation stack name."""
    return os.environ.get("STACK_NAME", "healthcare-agents-stack")


@pytest.fixture(scope="session")
def ssm_client(aws_region):
    """AWS SSM client for reading configuration."""
    return boto3.client("ssm", region_name=aws_region)


@pytest.fixture(scope="session")
def cfn_client(aws_region):
    """AWS CloudFormation client for reading stack outputs."""
    return boto3.client("cloudformation", region_name=aws_region)


@pytest.fixture(scope="session")
def gateway_url(ssm_client, stack_name):
    """Get Gateway URL from SSM Parameter Store."""
    try:
        response = ssm_client.get_parameter(Name=f"/{stack_name}/gateway_url")
        return response["Parameter"]["Value"]
    except Exception as e:
        pytest.skip(f"Could not get gateway URL from SSM: {e}")


@pytest.fixture(scope="session")
def runtime_arn(cfn_client, stack_name):
    """Get Runtime ARN from CloudFormation stack outputs."""
    try:
        response = cfn_client.describe_stacks(StackName=stack_name)
        outputs = response["Stacks"][0]["Outputs"]

        for output in outputs:
            if output["OutputKey"] == "RuntimeArn":
                return output["OutputValue"]

        pytest.skip(f"RuntimeArn not found in stack {stack_name} outputs")
    except Exception as e:
        pytest.skip(f"Could not get stack outputs: {e}")


@pytest.fixture(scope="session")
def cognito_config(ssm_client, stack_name):
    """Get Cognito configuration from SSM."""
    try:
        params = {
            "client_id": f"/{stack_name}/cognito/machine_client_id",
            "client_secret": f"/{stack_name}/cognito/machine_client_secret",
            "user_pool_id": f"/{stack_name}/cognito/user_pool_id",
            "domain": f"/{stack_name}/cognito/domain",
        }

        config = {}
        for key, param_name in params.items():
            response = ssm_client.get_parameter(Name=param_name, WithDecryption=True)
            config[key] = response["Parameter"]["Value"]

        return config
    except Exception as e:
        pytest.skip(f"Could not get Cognito config from SSM: {e}")


@pytest.fixture
def oauth_token(cognito_config, aws_region):
    """Get OAuth token for Gateway authentication."""
    import requests

    token_url = f"https://{cognito_config['domain']}.auth.{aws_region}.amazoncognito.com/oauth2/token"

    response = requests.post(
        token_url,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "client_credentials",
            "client_id": cognito_config["client_id"],
            "client_secret": cognito_config["client_secret"],
        },
        timeout=10,
    )

    if response.status_code != 200:
        pytest.skip(f"Could not obtain OAuth token: {response.text}")

    return response.json()["access_token"]


# ===== Test Markers Configuration =====


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "unit: Unit tests (fast, no AWS)")
    config.addinivalue_line(
        "markers", "integration: Integration tests (requires deployed stack)"
    )
    config.addinivalue_line("markers", "slow: Slow tests (> 30 seconds)")


# ===== Test Collection Hooks =====


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers automatically."""
    for item in items:
        # Auto-mark tests in unit/ directory
        if "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)

        # Auto-mark tests in integration/ directory
        if "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
