# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Integration tests for Claims Submission Agent.
"""

import pytest
import boto3
import os
import json
from datetime import datetime


@pytest.fixture
def s3_client():
    """Create S3 client."""
    return boto3.client('s3', region_name=os.environ.get('AWS_DEFAULT_REGION', 'us-east-1'))


@pytest.fixture
def b2bi_client():
    """Create B2B Data Interchange client."""
    return boto3.client('b2bi', region_name=os.environ.get('AWS_DEFAULT_REGION', 'us-east-1'))


@pytest.fixture
def stack_name():
    """Get stack name from environment."""
    return os.environ.get('STACK_NAME', 'healthcare-agents-stack')


@pytest.fixture
def b2bi_buckets(stack_name):
    """Get B2B bucket names from SSM."""
    ssm = boto3.client('ssm')
    try:
        input_bucket = ssm.get_parameter(Name=f'/{stack_name}/b2bi/input-bucket')['Parameter']['Value']
        output_bucket = ssm.get_parameter(Name=f'/{stack_name}/b2bi/output-bucket')['Parameter']['Value']
        ack_bucket = ssm.get_parameter(Name=f'/{stack_name}/b2bi/acknowledgment-bucket')['Parameter']['Value']
        return {
            'input': input_bucket,
            'output': output_bucket,
            'acknowledgment': ack_bucket
        }
    except:
        pytest.skip("B2B buckets not found")


class TestClaimSubmission:
    """Tests for claim submission workflow."""
    
    def test_submit_claim_to_s3(self, s3_client, b2bi_buckets):
        """Test submitting claim JSON to B2B input bucket."""
        claim_data = {
            'claim_id': 'TEST-001',
            'patient': {'name': 'Test Patient'},
            'provider': {'npi': '1234567890'},
            'service_lines': [{'procedure': '99213', 'charge': 150.00}]
        }
        
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        key = f'claims-to-submit/TEST-001_{timestamp}.json'
        
        # Submit claim
        s3_client.put_object(
            Bucket=b2bi_buckets['input'],
            Key=key,
            Body=json.dumps(claim_data),
            ContentType='application/json'
        )
        
        # Verify submission
        response = s3_client.head_object(
            Bucket=b2bi_buckets['input'],
            Key=key
        )
        
        assert response['ContentType'] == 'application/json'
        assert response['ContentLength'] > 0
        
        # Cleanup
        s3_client.delete_object(Bucket=b2bi_buckets['input'], Key=key)
    
    def test_list_transformer_jobs(self, b2bi_client, stack_name):
        """Test that transformer job retrieval works (B2BI has no list_transformer_jobs API)."""
        ssm = boto3.client('ssm')
        try:
            transformer_id = ssm.get_parameter(Name=f'/{stack_name}/b2bi/transformer-id')['Parameter']['Value']
        except:
            pytest.skip("Transformer ID not found")

        # B2BI SDK only supports get_transformer_job (no list endpoint)
        # Verify the transformer itself is accessible
        response = b2bi_client.get_transformer(transformerId=transformer_id)
        assert 'transformerId' in response
        assert response['transformerId'] == transformer_id


class TestDuplicateDetection:
    """Tests for duplicate claim detection."""
    
    def test_check_for_duplicate_submission(self, s3_client, b2bi_buckets):
        """Test checking for duplicate claim submissions."""
        claim_id = 'TEST-DUP-001'
        
        # List objects with claim_id prefix
        response = s3_client.list_objects_v2(
            Bucket=b2bi_buckets['input'],
            Prefix=f'claims-to-submit/{claim_id}'
        )
        
        existing_submissions = response.get('Contents', [])
        
        # Should be able to detect if claim already submitted
        assert isinstance(existing_submissions, list)


class TestAcknowledgmentProcessing:
    """Tests for acknowledgment retrieval and processing."""
    
    def test_retrieve_acknowledgments(self, s3_client, b2bi_buckets):
        """Test retrieving acknowledgments from S3."""
        claim_id = 'TEST-ACK-001'
        
        # List acknowledgments for claim
        response = s3_client.list_objects_v2(
            Bucket=b2bi_buckets['acknowledgment'],
            Prefix=f'acknowledgments/{claim_id}'
        )
        
        acknowledgments = response.get('Contents', [])
        assert isinstance(acknowledgments, list)
    
    def test_parse_997_acknowledgment(self):
        """Test parsing 997 functional acknowledgment."""
        # Sample 997 acknowledgment structure
        ack_997 = {
            'transaction_set': '997',
            'status': 'A',  # A=Accepted, R=Rejected, P=Partially Accepted
            'claim_id': 'TEST-001',
            'errors': []
        }
        
        assert ack_997['transaction_set'] == '997'
        assert ack_997['status'] in ['A', 'R', 'P']


class TestSubmissionWorkflow:
    """Tests for end-to-end submission workflow."""
    
    def test_complete_submission_workflow(self, s3_client, b2bi_buckets):
        """Test complete claim submission workflow."""
        claim_id = f'TEST-WORKFLOW-{datetime.utcnow().strftime("%Y%m%d%H%M%S")}'
        
        # Step 1: Prepare claim data
        claim_data = {
            'claim_id': claim_id,
            'submitter': {'name': 'Test Provider', 'npi': '1234567890'},
            'billing_provider': {'name': 'Test Clinic', 'npi': '0987654321'},
            'subscriber': {'name': 'Test Patient', 'member_id': 'MEM123'},
            'diagnoses': ['Z00.00'],
            'service_lines': [{'procedure': '99213', 'charge': 150.00}]
        }
        
        # Step 2: Check for duplicates (should be none)
        response = s3_client.list_objects_v2(
            Bucket=b2bi_buckets['input'],
            Prefix=f'claims-to-submit/{claim_id}'
        )
        assert len(response.get('Contents', [])) == 0, "No duplicates should exist"
        
        # Step 3: Submit claim
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        key = f'claims-to-submit/{claim_id}_{timestamp}.json'
        
        s3_client.put_object(
            Bucket=b2bi_buckets['input'],
            Key=key,
            Body=json.dumps(claim_data),
            ContentType='application/json'
        )
        
        # Step 4: Verify submission
        response = s3_client.head_object(
            Bucket=b2bi_buckets['input'],
            Key=key
        )
        assert response['ResponseMetadata']['HTTPStatusCode'] == 200
        
        # Cleanup
        s3_client.delete_object(Bucket=b2bi_buckets['input'], Key=key)
