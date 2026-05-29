# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for Knowledge Base retrieval."""

import os
import pytest
import boto3


@pytest.fixture
def kb_config():
    """Get knowledge base configuration."""
    kb_id = os.environ.get('KNOWLEDGE_BASE_ID')
    if not kb_id:
        pytest.skip("KNOWLEDGE_BASE_ID not set")
    
    return {
        'kb_id': kb_id,
        'region': os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')
    }


def test_kb_retrieve_icd10(kb_config):
    """Test retrieving ICD-10 codes from knowledge base."""
    client = boto3.client('bedrock-agent-runtime', region_name=kb_config['region'])
    
    response = client.retrieve(
        knowledgeBaseId=kb_config['kb_id'],
        retrievalQuery={'text': 'hypertension ICD-10'},
        retrievalConfiguration={
            'vectorSearchConfiguration': {
                'numberOfResults': 5
            }
        }
    )
    
    assert 'retrievalResults' in response
    assert len(response['retrievalResults']) > 0
    
    results_text = ' '.join([
        r['content']['text'] for r in response['retrievalResults']
    ])
    assert 'I10' in results_text or 'hypertension' in results_text.lower()


def test_kb_retrieve_cpt(kb_config):
    """Test retrieving CPT codes from knowledge base."""
    client = boto3.client('bedrock-agent-runtime', region_name=kb_config['region'])
    
    response = client.retrieve(
        knowledgeBaseId=kb_config['kb_id'],
        retrievalQuery={'text': 'office visit established patient CPT'},
        retrievalConfiguration={
            'vectorSearchConfiguration': {
                'numberOfResults': 5
            }
        }
    )
    
    assert 'retrievalResults' in response
    assert len(response['retrievalResults']) > 0
    
    results_text = ' '.join([
        r['content']['text'] for r in response['retrievalResults']
    ])
    assert '99213' in results_text or '99214' in results_text


def test_kb_retrieve_snomed(kb_config):
    """Test retrieving SNOMED CT codes from knowledge base."""
    client = boto3.client('bedrock-agent-runtime', region_name=kb_config['region'])
    
    response = client.retrieve(
        knowledgeBaseId=kb_config['kb_id'],
        retrievalQuery={'text': 'diabetes mellitus SNOMED'},
        retrievalConfiguration={
            'vectorSearchConfiguration': {
                'numberOfResults': 5
            }
        }
    )
    
    assert 'retrievalResults' in response
    assert len(response['retrievalResults']) > 0
