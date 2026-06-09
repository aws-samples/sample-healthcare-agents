# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for medical coding gateway tools."""

import os
import json
import pytest
import requests
from scripts.utils import get_ssm_parameter, get_machine_client_token


@pytest.fixture
def gateway_config():
    """Get gateway configuration from SSM."""
    stack_name = os.environ.get('STACK_NAME')
    if not stack_name:
        pytest.skip("STACK_NAME not set")
    
    return {
        'gateway_url': get_ssm_parameter(f'/{stack_name}/gateway_url'),
        'token': get_machine_client_token(stack_name)
    }


def test_list_gateway_tools(gateway_config):
    """Test listing tools from gateway."""
    response = requests.post(
        gateway_config['gateway_url'],
        headers={
            'Authorization': f"Bearer {gateway_config['token']}",
            'Content-Type': 'application/json'
        },
        json={
            'jsonrpc': '2.0',
            'id': 1,
            'method': 'tools/list'
        },
        timeout=30
    )
    
    assert response.status_code == 200
    result = response.json()
    assert 'result' in result
    
    tool_names = [tool['name'] for tool in result['result']['tools']]
    assert 'gateway___extract_medical_entities' in tool_names
    assert 'gateway___detect_phi' in tool_names


def test_extract_entities_via_gateway(gateway_config):
    """Test entity extraction through gateway."""
    clinical_text = "Patient presents with acute myocardial infarction and hypertension"
    
    response = requests.post(
        gateway_config['gateway_url'],
        headers={
            'Authorization': f"Bearer {gateway_config['token']}",
            'Content-Type': 'application/json'
        },
        json={
            'jsonrpc': '2.0',
            'id': 2,
            'method': 'tools/call',
            'params': {
                'name': 'gateway___extract_medical_entities',
                'arguments': {'text': clinical_text}
            }
        },
        timeout=30
    )
    
    assert response.status_code == 200
    result = response.json()
    assert 'result' in result
    
    content = json.loads(result['result']['content'][0]['text'])
    assert 'entities' in content
    assert 'MEDICAL_CONDITION' in content['entities']


def test_detect_phi_via_gateway(gateway_config):
    """Test PHI detection through gateway."""
    text_with_phi = "Patient John Doe, DOB 01/15/1980, was admitted"
    
    response = requests.post(
        gateway_config['gateway_url'],
        headers={
            'Authorization': f"Bearer {gateway_config['token']}",
            'Content-Type': 'application/json'
        },
        json={
            'jsonrpc': '2.0',
            'id': 3,
            'method': 'tools/call',
            'params': {
                'name': 'gateway___detect_phi',
                'arguments': {'text': text_with_phi}
            }
        },
        timeout=30
    )
    
    assert response.status_code == 200
    result = response.json()
    assert 'result' in result
