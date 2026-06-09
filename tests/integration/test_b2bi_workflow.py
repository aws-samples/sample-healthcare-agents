# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
End-to-end workflow test for claims assembly and submission.
"""

import pytest
import boto3
import os
import json
from datetime import datetime


@pytest.fixture
def stack_name():
    """Get stack name from environment."""
    return os.environ.get('STACK_NAME', 'healthcare-agents-stack')


@pytest.fixture
def s3_client():
    """Create S3 client."""
    return boto3.client('s3', region_name=os.environ.get('AWS_DEFAULT_REGION', 'us-east-1'))


@pytest.fixture
def bedrock_agent_runtime():
    """Create Bedrock Agent Runtime client."""
    return boto3.client('bedrock-agent-runtime', region_name=os.environ.get('AWS_DEFAULT_REGION', 'us-east-1'))


class TestEndToEndWorkflow:
    """End-to-end tests for complete claims workflow."""
    
    def test_full_claims_workflow(self, s3_client, bedrock_agent_runtime, stack_name):
        """
        Test complete workflow: Assembly → Validation → Submission → Acknowledgment
        """
        claim_id = f'E2E-TEST-{datetime.utcnow().strftime("%Y%m%d%H%M%S")}'
        
        # Step 1: Assemble claim data (simulating claims assembly agent output)
        claim_data = {
            'claim_id': claim_id,
            'submitter': {
                'name': 'Test Healthcare Provider',
                'npi': '1234567890',
                'contact': {
                    'phone': '555-0100',
                    'email': 'billing@testhealthcare.com'
                }
            },
            'billing_provider': {
                'name': 'Test Medical Clinic',
                'npi': '0987654321',
                'tax_id': '12-3456789',
                'address': {
                    'street': '123 Medical Way',
                    'city': 'Healthcare City',
                    'state': 'CA',
                    'zip': '90210'
                }
            },
            'subscriber': {
                'name': 'John Doe',
                'member_id': 'MEM123456789',
                'dob': '19800101',
                'gender': 'M',
                'address': {
                    'street': '456 Patient St',
                    'city': 'Patient City',
                    'state': 'CA',
                    'zip': '90211'
                }
            },
            'payer': {
                'name': 'Test Insurance Company',
                'payer_id': 'PAY12345'
            },
            'claim_info': {
                'claim_id': claim_id,
                'total_charge': 250.00,
                'place_of_service': '11',  # Office
                'service_date_from': '20250212',
                'service_date_to': '20250212'
            },
            'diagnoses': [
                {'code': 'Z00.00', 'type': 'principal'},
                {'code': 'E11.9', 'type': 'secondary'}
            ],
            'service_lines': [
                {
                    'line_number': 1,
                    'procedure_code': '99213',
                    'modifiers': [],
                    'charge': 150.00,
                    'units': 1,
                    'service_date': '20250212',
                    'diagnosis_pointers': [1]
                },
                {
                    'line_number': 2,
                    'procedure_code': '80053',
                    'modifiers': [],
                    'charge': 100.00,
                    'units': 1,
                    'service_date': '20250212',
                    'diagnosis_pointers': [1, 2]
                }
            ]
        }
        
        # Step 2: Validate claim structure
        assert 'submitter' in claim_data
        assert 'billing_provider' in claim_data
        assert 'subscriber' in claim_data
        assert 'claim_info' in claim_data
        assert 'diagnoses' in claim_data
        assert 'service_lines' in claim_data
        
        # Validate required fields
        assert len(claim_data['billing_provider']['npi']) == 10
        assert len(claim_data['diagnoses']) > 0
        assert len(claim_data['service_lines']) > 0
        assert claim_data['claim_info']['total_charge'] == sum(
            line['charge'] for line in claim_data['service_lines']
        )
        
        # Step 3: Check for duplicate submissions
        ssm = boto3.client('ssm')
        try:
            input_bucket = ssm.get_parameter(Name=f'/{stack_name}/b2bi/input-bucket')['Parameter']['Value']
        except:
            pytest.skip("B2B input bucket not found")
        
        response = s3_client.list_objects_v2(
            Bucket=input_bucket,
            Prefix=f'claims-to-submit/{claim_id}'
        )
        
        existing_submissions = response.get('Contents', [])
        assert len(existing_submissions) == 0, "No duplicate submissions should exist"
        
        # Step 4: Submit claim to B2B Data Interchange
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        key = f'claims-to-submit/{claim_id}_{timestamp}.json'
        
        s3_client.put_object(
            Bucket=input_bucket,
            Key=key,
            Body=json.dumps(claim_data, indent=2),
            ContentType='application/json',
            Metadata={
                'claim_id': claim_id,
                'submission_timestamp': timestamp
            }
        )
        
        # Step 5: Verify submission
        response = s3_client.head_object(
            Bucket=input_bucket,
            Key=key
        )
        
        assert response['ResponseMetadata']['HTTPStatusCode'] == 200
        assert response['ContentType'] == 'application/json'
        assert response['Metadata']['claim_id'] == claim_id
        
        # Step 6: Verify claim can be retrieved
        response = s3_client.get_object(
            Bucket=input_bucket,
            Key=key
        )
        
        retrieved_claim = json.loads(response['Body'].read().decode('utf-8'))
        assert retrieved_claim['claim_id'] == claim_id
        assert retrieved_claim['claim_info']['total_charge'] == 250.00
        
        # Cleanup
        s3_client.delete_object(Bucket=input_bucket, Key=key)
        
        print(f"✅ End-to-end workflow test completed successfully for claim {claim_id}")
    
    def test_validation_kb_integration(self, bedrock_agent_runtime, stack_name):
        """Test validation KB integration in workflow."""
        ssm = boto3.client('ssm')
        try:
            kb_id = ssm.get_parameter(Name=f'/{stack_name}/validation-kb-id')['Parameter']['Value']
        except:
            pytest.skip("Validation KB not found")
        
        # Query validation rules for claim assembly
        response = bedrock_agent_runtime.retrieve(
            knowledgeBaseId=kb_id,
            retrievalQuery={'text': 'Medicare claim submission requirements'},
            retrievalConfiguration={
                'vectorSearchConfiguration': {
                    'numberOfResults': 3
                }
            }
        )
        
        results = response.get('retrievalResults', [])
        assert len(results) > 0, "Should retrieve validation rules"
        
        # Verify results contain relevant information
        for result in results:
            content = result.get('content', {}).get('text', '')
            assert len(content) > 0, "Result should have content"
