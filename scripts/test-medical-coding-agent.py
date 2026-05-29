#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Manual test script for medical coding agent.
Usage: export STACK_NAME=your-stack-name && python scripts/test-medical-coding-agent.py
"""

import os
import sys
import json

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.utils import invoke_agent_streaming


def test_entity_extraction():
    """Test 1: Entity extraction from clinical text."""
    print("\n" + "=" * 70)
    print("TEST 1: Entity Extraction")
    print("=" * 70)
    
    query = """Extract medical entities from this clinical note:
    
Patient presents with acute myocardial infarction. 
Past medical history includes type 2 diabetes mellitus and essential hypertension.
Current medications: metformin 1000mg BID, lisinopril 10mg daily, aspirin 81mg daily.
"""
    
    print(f"\nQuery: {query}\n")
    print("Response:")
    print("-" * 70)
    
    for chunk in invoke_agent_streaming(query):
        if chunk.get('type') == 'content':
            print(chunk.get('text', ''), end='', flush=True)
    
    print("\n" + "=" * 70)


def test_code_search():
    """Test 2: Direct code search."""
    print("\n" + "=" * 70)
    print("TEST 2: Code Search")
    print("=" * 70)
    
    queries = [
        "What are the ICD-10 codes for type 2 diabetes mellitus?",
        "Find CPT codes for office visit, established patient",
        "Show me SNOMED CT codes for hypertension"
    ]
    
    for i, query in enumerate(queries, 1):
        print(f"\n{i}. Query: {query}")
        print("-" * 70)
        
        for chunk in invoke_agent_streaming(query):
            if chunk.get('type') == 'content':
                print(chunk.get('text', ''), end='', flush=True)
        
        print("\n")


def test_end_to_end_coding():
    """Test 3: Complete coding workflow."""
    print("\n" + "=" * 70)
    print("TEST 3: End-to-End Coding")
    print("=" * 70)
    
    query = """Analyze this clinical note and provide all relevant medical codes:
    
Chief Complaint: Chest pain

HPI: 65-year-old male presents to ED with acute onset chest pain radiating to left arm.
Pain started 2 hours ago, 8/10 severity. Associated with diaphoresis and shortness of breath.

PMH: Hypertension, hyperlipidemia, type 2 diabetes mellitus

Assessment: Acute ST-elevation myocardial infarction, anterior wall

Plan: Emergent cardiac catheterization, aspirin, heparin, nitroglycerin
"""
    
    print(f"\nQuery: {query}\n")
    print("Response:")
    print("-" * 70)
    
    for chunk in invoke_agent_streaming(query):
        if chunk.get('type') == 'content':
            print(chunk.get('text', ''), end='', flush=True)
    
    print("\n" + "=" * 70)


def test_multi_turn():
    """Test 4: Multi-turn conversation."""
    print("\n" + "=" * 70)
    print("TEST 4: Multi-Turn Conversation")
    print("=" * 70)
    
    conversation = [
        "What are the codes for diabetes?",
        "What about with complications?",
        "Show me the CPT codes for diabetes management visits"
    ]
    
    for i, query in enumerate(conversation, 1):
        print(f"\nTurn {i}: {query}")
        print("-" * 70)
        
        for chunk in invoke_agent_streaming(query):
            if chunk.get('type') == 'content':
                print(chunk.get('text', ''), end='', flush=True)
        
        print("\n")


if __name__ == "__main__":
    stack_name = os.environ.get('STACK_NAME')
    if not stack_name:
        print("Error: STACK_NAME environment variable not set")
        print("Usage: export STACK_NAME=your-stack-name && python scripts/test-medical-coding-agent.py")
        sys.exit(1)
    
    print("\n" + "=" * 70)
    print("MEDICAL CODING AGENT TEST SUITE")
    print("=" * 70)
    print(f"Stack: {stack_name}")
    
    try:
        test_entity_extraction()
        test_code_search()
        test_end_to_end_coding()
        test_multi_turn()
        
        print("\n" + "=" * 70)
        print("ALL TESTS COMPLETED!")
        print("=" * 70 + "\n")
        
    except Exception as e:
        print(f"\n\nError during testing: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
