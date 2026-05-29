# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Lambda handler for Comprehend Medical MCP tools.

Provides two tools:
1. extract_medical_entities - Extract medical entities from clinical text
2. detect_phi - Detect Protected Health Information in text
"""

import json
import logging
import boto3
from typing import Dict, Any, List

logger = logging.getLogger()
logger.setLevel(logging.INFO)

comprehend_medical = boto3.client('comprehendmedical')


def extract_medical_entities(text: str) -> Dict[str, Any]:
    """
    Extract medical entities from clinical text using Comprehend Medical.
    
    Args:
        text: Clinical text to analyze
        
    Returns:
        Dictionary containing extracted entities organized by type
    """
    try:
        response = comprehend_medical.detect_entities_v2(Text=text)
        
        entities_by_category = {
            'MEDICATION': [],
            'MEDICAL_CONDITION': [],
            'ANATOMY': [],
            'TEST_TREATMENT_PROCEDURE': [],
            'PROTECTED_HEALTH_INFORMATION': []
        }
        
        for entity in response.get('Entities', []):
            category = entity.get('Category')
            if category in entities_by_category:
                entities_by_category[category].append({
                    'text': entity.get('Text'),
                    'type': entity.get('Type'),
                    'score': entity.get('Score'),
                    'traits': entity.get('Traits', [])
                })
        
        return {
            'entities': entities_by_category,
            'unmapped_attributes': response.get('UnmappedAttributes', [])
        }
        
    except Exception as e:
        logger.error(f"Error extracting entities: {str(e)}")
        raise


def detect_phi(text: str) -> List[Dict[str, Any]]:
    """
    Detect Protected Health Information in text.
    
    Args:
        text: Text to analyze for PHI
        
    Returns:
        List of detected PHI entities
    """
    try:
        response = comprehend_medical.detect_phi(Text=text)
        
        phi_entities = []
        for entity in response.get('Entities', []):
            phi_entities.append({
                'text': entity.get('Text'),
                'category': entity.get('Category'),
                'type': entity.get('Type'),
                'score': entity.get('Score')
            })
        
        return phi_entities
        
    except Exception as e:
        logger.error(f"Error detecting PHI: {str(e)}")
        raise


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for Comprehend Medical MCP tools.
    
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
        if tool_name == "extract_medical_entities":
            text = event.get('text')
            if not text:
                raise ValueError("Missing required parameter: text")
            
            result = extract_medical_entities(text)
            return {
                'content': [{
                    'type': 'text',
                    'text': json.dumps(result, indent=2)
                }]
            }
            
        elif tool_name == "detect_phi":
            text = event.get('text')
            if not text:
                raise ValueError("Missing required parameter: text")
            
            result = detect_phi(text)
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
