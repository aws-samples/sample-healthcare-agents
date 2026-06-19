# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for Comprehend Medical Lambda handler."""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock


@pytest.fixture
def mock_context():
    """Mock Lambda context with tool name."""
    context = Mock()
    context.client_context = Mock()
    context.client_context.custom = {
        'bedrockAgentCoreToolName': 'comprehend_medical_target___extract_medical_entities'
    }
    return context


@pytest.fixture
def mock_comprehend_response():
    """Mock Comprehend Medical API response."""
    return {
        'Entities': [
            {
                'Text': 'hypertension',
                'Category': 'MEDICAL_CONDITION',
                'Type': 'DX_NAME',
                'Score': 0.95,
                'Traits': []
            },
            {
                'Text': 'lisinopril',
                'Category': 'MEDICATION',
                'Type': 'GENERIC_NAME',
                'Score': 0.98,
                'Traits': []
            }
        ],
        'UnmappedAttributes': []
    }


def test_extract_medical_entities(mock_context, mock_comprehend_response):
    """Test entity extraction from clinical text."""
    with patch('boto3.client') as mock_boto:
        mock_client = MagicMock()
        mock_client.detect_entities_v2.return_value = mock_comprehend_response
        mock_boto.return_value = mock_client
        
        # Import after patching
        from gateway.tools.comprehend_medical.lambda_handler import lambda_handler
        
        event = {'text': 'Patient has hypertension, prescribed lisinopril'}
        result = lambda_handler(event, mock_context)
        
        assert 'content' in result
        assert len(result['content']) > 0
        content = json.loads(result['content'][0]['text'])
        assert 'entities' in content
        assert 'MEDICATION' in content['entities']
        assert 'MEDICAL_CONDITION' in content['entities']


def test_detect_phi(mock_context):
    """Test PHI detection."""
    mock_context.client_context.custom['bedrockAgentCoreToolName'] = \
        'comprehend_medical_target___detect_phi'

    mock_phi_response = {
        'Entities': [
            {
                'Text': 'John Doe',
                'Category': 'PROTECTED_HEALTH_INFORMATION',
                'Type': 'NAME',
                'Score': 0.99
            }
        ]
    }

    from gateway.tools.comprehend_medical import lambda_handler as lh_module
    mock_client = MagicMock()
    mock_client.detect_phi.return_value = mock_phi_response

    with patch.object(lh_module, 'comprehend_medical', mock_client):
        from gateway.tools.comprehend_medical.lambda_handler import lambda_handler

        event = {'text': 'Patient John Doe was admitted'}
        result = lambda_handler(event, mock_context)

        assert 'content' in result
        content = json.loads(result['content'][0]['text'])
        assert len(content) > 0
        assert content[0]['type'] == 'NAME'


def test_missing_text_parameter(mock_context):
    """Test error handling for missing text parameter."""
    with patch('boto3.client'):
        from gateway.tools.comprehend_medical.lambda_handler import lambda_handler
        
        event = {}  # Missing 'text' parameter
        
        with pytest.raises(ValueError, match="Missing required parameter: text"):
            lambda_handler(event, mock_context)
