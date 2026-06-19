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
    try:
        return {
            'gateway_url': get_ssm_parameter(f'/{stack_name}/gateway_url'),
            'token': get_machine_client_token(stack_name)
        }
    except SystemExit:
        pytest.skip("Could not fetch gateway config from SSM/Cognito")


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
    # Tool names are prefixed with the target name (e.g. comprehend-medical-target___)
    assert any('extract_medical_entities' in n for n in tool_names), \
        f"extract_medical_entities not found in: {tool_names}"
    assert any('detect_phi' in n for n in tool_names), \
        f"detect_phi not found in: {tool_names}"


def _get_tool_name(tool_names, suffix):
    """Find the full tool name matching a suffix."""
    for n in tool_names:
        if suffix in n:
            return n
    return None


def test_extract_entities_via_gateway(gateway_config):
    """Test entity extraction through gateway."""
    # Discover actual tool name from gateway
    list_resp = requests.post(
        gateway_config['gateway_url'],
        headers={'Authorization': f"Bearer {gateway_config['token']}", 'Content-Type': 'application/json'},
        json={'jsonrpc': '2.0', 'id': 0, 'method': 'tools/list'},
        timeout=30
    )
    tool_names = [t['name'] for t in list_resp.json()['result']['tools']]
    tool_name = _get_tool_name(tool_names, 'extract_medical_entities')
    if not tool_name:
        pytest.skip("extract_medical_entities tool not available on gateway")

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
                'name': tool_name,
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
    # Discover actual tool name from gateway
    list_resp = requests.post(
        gateway_config['gateway_url'],
        headers={'Authorization': f"Bearer {gateway_config['token']}", 'Content-Type': 'application/json'},
        json={'jsonrpc': '2.0', 'id': 0, 'method': 'tools/list'},
        timeout=30
    )
    tool_names = [t['name'] for t in list_resp.json()['result']['tools']]
    tool_name = _get_tool_name(tool_names, 'detect_phi')
    if not tool_name:
        pytest.skip("detect_phi tool not available on gateway")

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
                'name': tool_name,
                'arguments': {'text': text_with_phi}
            }
        },
        timeout=30
    )
    
    assert response.status_code == 200
    result = response.json()
    assert 'result' in result
