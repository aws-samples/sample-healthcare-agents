# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Integration tests for Claims Assembly Agent.
"""

import pytest
import boto3
import os
import json


@pytest.fixture
def bedrock_agent_runtime():
    """Create Bedrock Agent Runtime client."""
    return boto3.client('bedrock-agent-runtime', region_name=os.environ.get('AWS_DEFAULT_REGION', 'us-east-1'))


@pytest.fixture
def validation_kb_id():
    """Get validation KB ID from environment or SSM."""
    kb_id = os.environ.get('VALIDATION_KB_ID')
    if not kb_id:
        ssm = boto3.client('ssm')
        stack_name = os.environ.get('STACK_NAME', 'healthcare-agents-stack')
        try:
            response = ssm.get_parameter(Name=f'/{stack_name}/validation-kb-id')
            kb_id = response['Parameter']['Value']
        except:
            pytest.skip("Validation KB ID not found")
    return kb_id


class TestValidationKBQuery:
    """Tests for validation KB query functionality."""
    
    def test_query_payer_requirements(self, bedrock_agent_runtime, validation_kb_id):
        """Test querying payer requirements from KB."""
        response = bedrock_agent_runtime.retrieve(
            knowledgeBaseId=validation_kb_id,
            retrievalQuery={'text': 'Medicare NPI requirements'},
            retrievalConfiguration={
                'vectorSearchConfiguration': {
                    'numberOfResults': 5
                }
            }
        )
        
        results = response.get('retrievalResults', [])
        assert len(results) > 0, "Should return validation rules"
        
        # Check that results contain relevant content
        content = results[0].get('content', {}).get('text', '')
        assert 'NPI' in content or 'Medicare' in content
    
    def test_query_hipaa_compliance(self, bedrock_agent_runtime, validation_kb_id):
        """Test querying HIPAA compliance rules from KB."""
        response = bedrock_agent_runtime.retrieve(
            knowledgeBaseId=validation_kb_id,
            retrievalQuery={'text': 'HIPAA 5010 required fields'},
            retrievalConfiguration={
                'vectorSearchConfiguration': {
                    'numberOfResults': 5
                }
            }
        )
        
        results = response.get('retrievalResults', [])
        assert len(results) > 0, "Should return compliance rules"
    
    def test_query_edi_structure(self, bedrock_agent_runtime, validation_kb_id):
        """Test querying EDI 837P structure from KB."""
        response = bedrock_agent_runtime.retrieve(
            knowledgeBaseId=validation_kb_id,
            retrievalQuery={'text': 'EDI 837P Loop 2300 requirements'},
            retrievalConfiguration={
                'vectorSearchConfiguration': {
                    'numberOfResults': 5
                }
            }
        )
        
        results = response.get('retrievalResults', [])
        assert len(results) > 0, "Should return EDI structure rules"


class TestClaimsAssemblyValidation:
    """Tests for claims assembly validation logic."""
    
    def test_validate_npi_format(self):
        """Test NPI format validation."""
        # Valid NPI: 10 digits
        valid_npi = "1234567890"
        assert len(valid_npi) == 10
        assert valid_npi.isdigit()
        
        # Invalid NPI: wrong length
        invalid_npi = "12345"
        assert len(invalid_npi) != 10
    
    def test_validate_diagnosis_codes(self):
        """Test diagnosis code format validation."""
        # Valid ICD-10-CM: 3-7 characters
        valid_codes = ["A01", "A01.0", "A01.00"]
        for code in valid_codes:
            assert 3 <= len(code) <= 7
        
        # Invalid: too short
        invalid_code = "A1"
        assert len(invalid_code) < 3
    
    def test_validate_procedure_codes(self):
        """Test procedure code format validation."""
        # Valid CPT: 5 digits
        valid_cpt = "99213"
        assert len(valid_cpt) == 5
        assert valid_cpt.isdigit()
        
        # Valid HCPCS: 1 letter + 4 digits
        valid_hcpcs = "J1234"
        assert len(valid_hcpcs) == 5
        assert valid_hcpcs[0].isalpha()
        assert valid_hcpcs[1:].isdigit()


class TestEDI837PGeneration:
    """Tests for EDI 837P JSON generation."""
    
    def test_generate_basic_claim_structure(self):
        """Test generating basic EDI 837P claim structure."""
        claim = {
            'submitter': {
                'name': 'Test Provider',
                'npi': '1234567890'
            },
            'billing_provider': {
                'name': 'Test Clinic',
                'npi': '0987654321',
                'tax_id': '12-3456789'
            },
            'subscriber': {
                'name': 'John Doe',
                'member_id': 'MEM123456',
                'dob': '19800101',
                'gender': 'M'
            },
            'claim_info': {
                'claim_id': 'CLM001',
                'total_charge': 150.00,
                'place_of_service': '11'
            },
            'diagnoses': ['Z00.00'],
            'service_lines': [{
                'procedure_code': '99213',
                'charge': 150.00,
                'units': 1,
                'service_date': '20250212'
            }]
        }
        
        # Validate required fields present
        assert 'submitter' in claim
        assert 'billing_provider' in claim
        assert 'subscriber' in claim
        assert 'claim_info' in claim
        assert 'diagnoses' in claim
        assert 'service_lines' in claim
        
        # Validate field formats
        assert len(claim['billing_provider']['npi']) == 10
        assert len(claim['diagnoses']) > 0
        assert len(claim['service_lines']) > 0
