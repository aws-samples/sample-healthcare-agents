# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for B2B Data Interchange integration Lambda.
"""

import json
import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add gateway tools to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../gateway/tools/b2bi_integration'))

import lambda_handler


@pytest.fixture
def mock_context():
    """Create mock Lambda context."""
    context = Mock()
    context.client_context = Mock()
    context.client_context.custom = {}
    return context


@pytest.fixture
def mock_env(monkeypatch):
    """Set up mock environment variables."""
    monkeypatch.setenv('B2BI_TRANSFORMER_ID', 'test-transformer-id')
    monkeypatch.setenv('B2BI_INPUT_BUCKET', 'test-input-bucket')
    monkeypatch.setenv('B2BI_OUTPUT_BUCKET', 'test-output-bucket')
    monkeypatch.setenv('B2BI_ACKNOWLEDGMENT_BUCKET', 'test-ack-bucket')


class TestCheckSubmissionStatus:
    """Tests for check_submission_status function."""
    
    @patch('lambda_handler.b2bi')
    def test_check_submission_status_found(self, mock_b2bi, mock_env):
        """Test checking status for existing submission."""
        mock_b2bi.list_transformer_jobs.return_value = {
            'transformerJobs': [{
                'transformerJobId': 'job-123',
                'status': 'COMPLETED',
                'inputFileLocation': {'key': 'claims-to-submit/claim-456_20250212.json'},
                'startedAt': '2025-02-12T10:00:00Z',
                'endedAt': '2025-02-12T10:05:00Z',
                'message': 'Success'
            }]
        }
        
        result = lambda_handler.check_submission_status('claim-456')
        
        assert result['claim_id'] == 'claim-456'
        assert result['status'] == 'COMPLETED'
        assert result['job_id'] == 'job-123'
    
    @patch('lambda_handler.b2bi')
    def test_check_submission_status_not_found(self, mock_b2bi, mock_env):
        """Test checking status for non-existent submission."""
        mock_b2bi.list_transformer_jobs.return_value = {
            'transformerJobs': []
        }
        
        result = lambda_handler.check_submission_status('claim-999')
        
        assert result['claim_id'] == 'claim-999'
        assert result['status'] == 'NOT_FOUND'


class TestRetrieveAcknowledgments:
    """Tests for retrieve_acknowledgments function."""
    
    @patch('lambda_handler.s3')
    def test_retrieve_acknowledgments_found(self, mock_s3, mock_env):
        """Test retrieving acknowledgments for a claim."""
        mock_s3.list_objects_v2.return_value = {
            'Contents': [{
                'Key': 'acknowledgments/claim-456/997_response.txt',
                'LastModified': datetime(2025, 2, 12, 10, 10, 0, tzinfo=timezone.utc),
                'Size': 1024
            }]
        }
        
        mock_s3.get_object.return_value = {
            'Body': MagicMock(read=lambda: b'997 acknowledgment content')
        }
        
        result = lambda_handler.retrieve_acknowledgments('claim-456')
        
        assert len(result) == 1
        assert result[0]['file_name'] == 'acknowledgments/claim-456/997_response.txt'
        assert result[0]['content'] == '997 acknowledgment content'
    
    @patch('lambda_handler.s3')
    def test_retrieve_acknowledgments_empty(self, mock_s3, mock_env):
        """Test retrieving acknowledgments when none exist."""
        mock_s3.list_objects_v2.return_value = {}
        
        result = lambda_handler.retrieve_acknowledgments('claim-999')
        
        assert result == []


class TestSubmitClaim:
    """Tests for submit_claim function."""
    
    @patch('lambda_handler.s3')
    @patch('lambda_handler.datetime')
    def test_submit_claim_success(self, mock_datetime, mock_s3, mock_env):
        """Test successful claim submission."""
        mock_datetime.utcnow.return_value.strftime.return_value = '20250212_100000'
        
        claim_data = {
            'patient': {'name': 'John Doe'},
            'provider': {'npi': '1234567890'}
        }
        
        result = lambda_handler.submit_claim(claim_data, 'claim-789')
        
        assert result['claim_id'] == 'claim-789'
        assert result['status'] == 'SUBMITTED'
        assert result['bucket'] == 'test-input-bucket'
        assert 'claim-789_20250212_100000.json' in result['key']
        
        mock_s3.put_object.assert_called_once()


class TestListSubmissions:
    """Tests for list_submissions function."""
    
    @patch('lambda_handler.b2bi')
    def test_list_submissions(self, mock_b2bi, mock_env):
        """Test listing recent submissions."""
        mock_b2bi.list_transformer_jobs.return_value = {
            'transformerJobs': [
                {
                    'transformerJobId': 'job-1',
                    'status': 'COMPLETED',
                    'inputFileLocation': {'key': 'claims-to-submit/claim-1.json'},
                    'outputFileLocation': {'key': 'submitted-claims/claim-1.x12'},
                    'startedAt': '2025-02-12T10:00:00Z',
                    'endedAt': '2025-02-12T10:05:00Z'
                },
                {
                    'transformerJobId': 'job-2',
                    'status': 'IN_PROGRESS',
                    'inputFileLocation': {'key': 'claims-to-submit/claim-2.json'},
                    'outputFileLocation': {},
                    'startedAt': '2025-02-12T10:10:00Z'
                }
            ]
        }
        
        result = lambda_handler.list_submissions(limit=10)
        
        assert len(result) == 2
        assert result[0]['job_id'] == 'job-1'
        assert result[0]['status'] == 'COMPLETED'
        assert result[1]['status'] == 'IN_PROGRESS'


class TestLambdaHandler:
    """Tests for main lambda_handler function."""
    
    @patch('lambda_handler.check_submission_status')
    def test_lambda_handler_check_status(self, mock_check, mock_context, mock_env):
        """Test lambda handler routing to check_submission_status."""
        mock_context.client_context.custom['bedrockAgentCoreToolName'] = 'b2bi___check_submission_status'
        mock_check.return_value = {'claim_id': 'test', 'status': 'COMPLETED'}
        
        event = {'claim_id': 'test'}
        result = lambda_handler.lambda_handler(event, mock_context)
        
        assert 'content' in result
        assert result['content'][0]['type'] == 'text'
        mock_check.assert_called_once_with('test')
    
    @patch('lambda_handler.submit_claim')
    def test_lambda_handler_submit_claim(self, mock_submit, mock_context, mock_env):
        """Test lambda handler routing to submit_claim."""
        mock_context.client_context.custom['bedrockAgentCoreToolName'] = 'b2bi___submit_claim'
        mock_submit.return_value = {'claim_id': 'test', 'status': 'SUBMITTED'}
        
        event = {'claim_data': {'test': 'data'}, 'claim_id': 'test'}
        result = lambda_handler.lambda_handler(event, mock_context)
        
        assert 'content' in result
        mock_submit.assert_called_once()
    
    def test_lambda_handler_unknown_tool(self, mock_context, mock_env):
        """Test lambda handler with unknown tool name."""
        mock_context.client_context.custom['bedrockAgentCoreToolName'] = 'b2bi___unknown_tool'
        
        event = {}
        
        with pytest.raises(ValueError, match="Unknown tool"):
            lambda_handler.lambda_handler(event, mock_context)
    
    def test_lambda_handler_missing_parameter(self, mock_context, mock_env):
        """Test lambda handler with missing required parameter."""
        mock_context.client_context.custom['bedrockAgentCoreToolName'] = 'b2bi___check_submission_status'
        
        event = {}  # Missing claim_id
        
        with pytest.raises(ValueError, match="Missing required parameter"):
            lambda_handler.lambda_handler(event, mock_context)
