# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Lambda handler for B2B Data Interchange integration tools.

Provides four tools:
1. check_submission_status - Query B2B transformation status
2. retrieve_acknowledgments - Get 997/999 from S3
3. submit_claim - Write JSON to B2B input bucket
4. list_submissions - Query submission history
"""

import json
import logging
import boto3
import os
from typing import Dict, Any, List
from datetime import datetime

logger = logging.getLogger()
logger.setLevel(logging.INFO)

b2bi = boto3.client('b2bi')
s3 = boto3.client('s3')


def check_submission_status(claim_id: str) -> Dict[str, Any]:
    """
    Check status of claim submission in B2B Data Interchange.
    
    Args:
        claim_id: Unique claim identifier
        
    Returns:
        Dictionary containing submission status and details
    """
    try:
        transformer_id = os.environ.get('B2BI_TRANSFORMER_ID')
        if not transformer_id:
            raise ValueError("B2BI_TRANSFORMER_ID environment variable not set")
        
        # List transformer jobs to find matching claim
        response = b2bi.list_transformer_jobs(
            transformerId=transformer_id,
            maxResults=50
        )
        
        for job in response.get('transformerJobs', []):
            # Check if job matches claim_id (stored in input file name)
            if claim_id in job.get('inputFileLocation', {}).get('key', ''):
                return {
                    'claim_id': claim_id,
                    'status': job.get('status'),
                    'job_id': job.get('transformerJobId'),
                    'started_at': job.get('startedAt'),
                    'ended_at': job.get('endedAt'),
                    'message': job.get('message', '')
                }
        
        return {
            'claim_id': claim_id,
            'status': 'NOT_FOUND',
            'message': 'No submission found for this claim ID'
        }
        
    except Exception as e:
        logger.error(f"Error checking submission status: {str(e)}")
        raise


def retrieve_acknowledgments(claim_id: str) -> List[Dict[str, Any]]:
    """
    Retrieve 997/999 acknowledgments from S3 for a claim.
    
    Args:
        claim_id: Unique claim identifier
        
    Returns:
        List of acknowledgment files and their contents
    """
    try:
        ack_bucket = os.environ.get('B2BI_ACKNOWLEDGMENT_BUCKET')
        if not ack_bucket:
            raise ValueError("B2BI_ACKNOWLEDGMENT_BUCKET environment variable not set")
        
        # List objects in acknowledgment bucket matching claim_id
        response = s3.list_objects_v2(
            Bucket=ack_bucket,
            Prefix=f'acknowledgments/{claim_id}'
        )
        
        acknowledgments = []
        for obj in response.get('Contents', []):
            # Get acknowledgment file content
            file_response = s3.get_object(
                Bucket=ack_bucket,
                Key=obj['Key']
            )
            
            content = file_response['Body'].read().decode('utf-8')
            
            acknowledgments.append({
                'file_name': obj['Key'],
                'last_modified': obj['LastModified'].isoformat(),
                'size': obj['Size'],
                'content': content
            })
        
        return acknowledgments
        
    except Exception as e:
        logger.error(f"Error retrieving acknowledgments: {str(e)}")
        raise


def submit_claim(claim_data: Dict[str, Any], claim_id: str) -> Dict[str, Any]:
    """
    Submit claim by writing JSON to B2B input bucket.
    
    Args:
        claim_data: Claim data in JSON format
        claim_id: Unique claim identifier
        
    Returns:
        Dictionary containing submission confirmation
    """
    try:
        input_bucket = os.environ.get('B2BI_INPUT_BUCKET')
        if not input_bucket:
            raise ValueError("B2BI_INPUT_BUCKET environment variable not set")
        
        # Generate file key with timestamp
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        file_key = f'claims-to-submit/{claim_id}_{timestamp}.json'
        
        # Write claim data to S3
        s3.put_object(
            Bucket=input_bucket,
            Key=file_key,
            Body=json.dumps(claim_data, indent=2),
            ContentType='application/json'
        )
        
        return {
            'claim_id': claim_id,
            'status': 'SUBMITTED',
            'bucket': input_bucket,
            'key': file_key,
            'timestamp': timestamp,
            'message': 'Claim submitted successfully to B2B Data Interchange'
        }
        
    except Exception as e:
        logger.error(f"Error submitting claim: {str(e)}")
        raise


def list_submissions(limit: int = 10) -> List[Dict[str, Any]]:
    """
    List recent claim submissions.
    
    Args:
        limit: Maximum number of submissions to return
        
    Returns:
        List of recent submissions with status
    """
    try:
        transformer_id = os.environ.get('B2BI_TRANSFORMER_ID')
        if not transformer_id:
            raise ValueError("B2BI_TRANSFORMER_ID environment variable not set")
        
        # List recent transformer jobs
        response = b2bi.list_transformer_jobs(
            transformerId=transformer_id,
            maxResults=min(limit, 50)
        )
        
        submissions = []
        for job in response.get('transformerJobs', []):
            submissions.append({
                'job_id': job.get('transformerJobId'),
                'status': job.get('status'),
                'input_file': job.get('inputFileLocation', {}).get('key', ''),
                'output_file': job.get('outputFileLocation', {}).get('key', ''),
                'started_at': job.get('startedAt'),
                'ended_at': job.get('endedAt')
            })
        
        return submissions
        
    except Exception as e:
        logger.error(f"Error listing submissions: {str(e)}")
        raise


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for B2B Data Interchange integration tools.
    
    Args:
        event: Tool invocation event with arguments
        context: Lambda context with tool name
        
    Returns:
        Tool response in MCP format
    """
    try:
        # Extract tool name from context
        original_tool_name = context.client_context.custom['bedrockAgentCoreToolName']
        logger.info(f"Received tool invocation: {original_tool_name}")
        # PHI-safe event logging (mitigates Threat T11).
        logger.info(
            "event_summary=%s",
            json.dumps({
                "top_level_keys": sorted(event.keys()) if isinstance(event, dict) else [],
                "size_bytes": len(json.dumps(event, default=str)) if event else 0,
            }, default=str),
        )
        
        # Strip target prefix
        delimiter = "___"
        if delimiter in original_tool_name:
            tool_name = original_tool_name[original_tool_name.index(delimiter) + len(delimiter):]
        else:
            tool_name = original_tool_name
        
        # Route to appropriate tool
        if tool_name == "check_submission_status":
            claim_id = event.get('claim_id')
            if not claim_id:
                raise ValueError("Missing required parameter: claim_id")
            
            result = check_submission_status(claim_id)
            return {
                'content': [{
                    'type': 'text',
                    'text': json.dumps(result, indent=2)
                }]
            }
            
        elif tool_name == "retrieve_acknowledgments":
            claim_id = event.get('claim_id')
            if not claim_id:
                raise ValueError("Missing required parameter: claim_id")
            
            result = retrieve_acknowledgments(claim_id)
            return {
                'content': [{
                    'type': 'text',
                    'text': json.dumps(result, indent=2)
                }]
            }
            
        elif tool_name == "submit_claim":
            claim_data = event.get('claim_data')
            claim_id = event.get('claim_id')
            if not claim_data or not claim_id:
                raise ValueError("Missing required parameters: claim_data and claim_id")
            
            result = submit_claim(claim_data, claim_id)
            return {
                'content': [{
                    'type': 'text',
                    'text': json.dumps(result, indent=2)
                }]
            }
            
        elif tool_name == "list_submissions":
            limit = event.get('limit', 10)
            
            result = list_submissions(limit)
            return {
                'content': [{
                    'type': 'text',
                    'text': json.dumps(result, indent=2)
                }]
            }
            
        else:
            raise ValueError(f"Unknown tool: {tool_name}")
            
    except Exception as e:
        logger.error(f"Error in lambda_handler: {str(e)}", exc_info=True)
        raise
