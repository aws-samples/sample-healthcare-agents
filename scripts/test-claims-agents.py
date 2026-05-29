#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Manual test script for Claims Assembly and Submission Agents.

Usage:
    export STACK_NAME=your-stack-name
    python scripts/test-claims-agents.py
"""

import os
import sys
import json
import boto3
from datetime import datetime

# Colors for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'


def print_success(message):
    """Print success message in green."""
    print(f"{GREEN}✓ {message}{RESET}")


def print_error(message):
    """Print error message in red."""
    print(f"{RED}✗ {message}{RESET}")


def print_info(message):
    """Print info message in yellow."""
    print(f"{YELLOW}ℹ {message}{RESET}")


def get_stack_name():
    """Get stack name from environment."""
    stack_name = os.environ.get('STACK_NAME')
    if not stack_name:
        print_error("STACK_NAME environment variable not set")
        sys.exit(1)
    return stack_name


def test_validation_kb(stack_name):
    """Test validation KB retrieval."""
    print_info("Testing Validation Knowledge Base...")
    
    ssm = boto3.client('ssm')
    bedrock_agent_runtime = boto3.client('bedrock-agent-runtime')
    
    try:
        # Get KB ID
        kb_id = ssm.get_parameter(Name=f'/{stack_name}/validation-kb-id')['Parameter']['Value']
        print_success(f"Found validation KB: {kb_id}")
        
        # Query KB
        response = bedrock_agent_runtime.retrieve(
            knowledgeBaseId=kb_id,
            retrievalQuery={'text': 'Medicare NPI requirements'},
            retrievalConfiguration={
                'vectorSearchConfiguration': {
                    'numberOfResults': 3
                }
            }
        )
        
        results = response.get('retrievalResults', [])
        if results:
            print_success(f"Retrieved {len(results)} validation rules")
            print(f"  Sample: {results[0]['content']['text'][:100]}...")
        else:
            print_error("No validation rules retrieved")
            
    except Exception as e:
        print_error(f"Validation KB test failed: {e}")


def test_b2bi_buckets(stack_name):
    """Test B2B Data Interchange buckets."""
    print_info("Testing B2B Data Interchange buckets...")
    
    ssm = boto3.client('ssm')
    s3 = boto3.client('s3')
    
    try:
        # Get bucket names
        input_bucket = ssm.get_parameter(Name=f'/{stack_name}/b2bi/input-bucket')['Parameter']['Value']
        output_bucket = ssm.get_parameter(Name=f'/{stack_name}/b2bi/output-bucket')['Parameter']['Value']
        ack_bucket = ssm.get_parameter(Name=f'/{stack_name}/b2bi/acknowledgment-bucket')['Parameter']['Value']
        
        print_success(f"Input bucket: {input_bucket}")
        print_success(f"Output bucket: {output_bucket}")
        print_success(f"Acknowledgment bucket: {ack_bucket}")
        
        # Test write to input bucket
        test_key = f'test/test-{datetime.utcnow().strftime("%Y%m%d%H%M%S")}.json'
        test_data = {'test': 'data'}
        
        s3.put_object(
            Bucket=input_bucket,
            Key=test_key,
            Body=json.dumps(test_data)
        )
        print_success(f"Successfully wrote test file to input bucket")
        
        # Cleanup
        s3.delete_object(Bucket=input_bucket, Key=test_key)
        print_success("Cleaned up test file")
        
    except Exception as e:
        print_error(f"B2B buckets test failed: {e}")


def test_b2bi_resources(stack_name):
    """Test B2B Data Interchange resources."""
    print_info("Testing B2B Data Interchange resources...")
    
    ssm = boto3.client('ssm')
    b2bi = boto3.client('b2bi')
    
    try:
        # Get resource IDs
        profile_id = ssm.get_parameter(Name=f'/{stack_name}/b2bi/profile-id')['Parameter']['Value']
        transformer_id = ssm.get_parameter(Name=f'/{stack_name}/b2bi/transformer-id')['Parameter']['Value']
        capability_id = ssm.get_parameter(Name=f'/{stack_name}/b2bi/capability-id')['Parameter']['Value']
        
        print_success(f"Profile ID: {profile_id}")
        print_success(f"Transformer ID: {transformer_id}")
        print_success(f"Capability ID: {capability_id}")
        
        # List transformer jobs
        response = b2bi.list_transformer_jobs(
            transformerId=transformer_id,
            maxResults=5
        )
        
        jobs = response.get('transformerJobs', [])
        print_success(f"Found {len(jobs)} transformer jobs")
        
    except Exception as e:
        print_error(f"B2B resources test failed: {e}")


def test_gateway_tools(stack_name):
    """Test Gateway B2B integration tools."""
    print_info("Testing Gateway B2B integration tools...")
    
    ssm = boto3.client('ssm')
    
    try:
        # Get Gateway URL
        gateway_url = ssm.get_parameter(Name=f'/{stack_name}/gateway_url')['Parameter']['Value']
        print_success(f"Gateway URL: {gateway_url}")
        
        # Note: Actual tool invocation requires authentication
        print_info("Gateway tools available:")
        print("  - check_submission_status")
        print("  - retrieve_acknowledgments")
        print("  - submit_claim")
        print("  - list_submissions")
        
    except Exception as e:
        print_error(f"Gateway tools test failed: {e}")


def test_sample_claim_submission(stack_name):
    """Test submitting a sample claim."""
    print_info("Testing sample claim submission...")
    
    ssm = boto3.client('ssm')
    s3 = boto3.client('s3')
    
    try:
        input_bucket = ssm.get_parameter(Name=f'/{stack_name}/b2bi/input-bucket')['Parameter']['Value']
        
        # Create sample claim
        claim_id = f'TEST-{datetime.utcnow().strftime("%Y%m%d%H%M%S")}'
        claim_data = {
            'claim_id': claim_id,
            'submitter': {'name': 'Test Provider', 'npi': '1234567890'},
            'billing_provider': {'name': 'Test Clinic', 'npi': '0987654321'},
            'subscriber': {'name': 'Test Patient', 'member_id': 'MEM123'},
            'diagnoses': ['Z00.00'],
            'service_lines': [{'procedure': '99213', 'charge': 150.00}]
        }
        
        # Submit to B2B input bucket
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        key = f'claims-to-submit/{claim_id}_{timestamp}.json'
        
        s3.put_object(
            Bucket=input_bucket,
            Key=key,
            Body=json.dumps(claim_data, indent=2),
            ContentType='application/json'
        )
        
        print_success(f"Submitted test claim: {claim_id}")
        print_info(f"Location: s3://{input_bucket}/{key}")
        print_info("B2B Data Interchange will process this claim automatically")
        
        # Note: Don't cleanup - let B2B process it
        
    except Exception as e:
        print_error(f"Sample claim submission failed: {e}")


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("Claims Assembly and Submission Agents - Test Suite")
    print("="*60 + "\n")
    
    stack_name = get_stack_name()
    print_info(f"Testing stack: {stack_name}\n")
    
    # Run tests
    test_validation_kb(stack_name)
    print()
    
    test_b2bi_buckets(stack_name)
    print()
    
    test_b2bi_resources(stack_name)
    print()
    
    test_gateway_tools(stack_name)
    print()
    
    test_sample_claim_submission(stack_name)
    print()
    
    print("="*60)
    print_success("Test suite completed!")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
