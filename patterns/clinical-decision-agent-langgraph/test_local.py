#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Local test script for the clinical decision agent.
Run this to test the agent locally without deploying to AgentCore.

Usage:
    python test_local.py "your query here"
"""

import asyncio
import sys
import os
from pathlib import Path

# Add parent directories to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(Path(__file__).parent))

# Set required environment variables for local testing
os.environ['STACK_NAME'] = 'healthcare-agents-stack'
os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'
os.environ['AWS_REGION'] = 'us-east-1'
os.environ['AWS_PROFILE'] = 'quicksuite'  # Use the correct AWS profile
# Get MEMORY_ID from CloudFormation outputs
os.environ['MEMORY_ID'] = 'healthcareagentsstaccisionagentlanggraph8D377B5B-2TnPwfATix'

# Import the agent module
from clinical_decision_agent import agent_stream


async def test_agent(query: str):
    """Test the agent with a query"""
    print(f"\n{'='*80}")
    print(f"Testing agent with query: {query}")
    print(f"{'='*80}\n")

    # Create test payload
    payload = {
        "prompt": query,
        "userId": "test-user-local",
        "runtimeSessionId": "test-session-local"
    }

    try:
        # Stream responses
        response_count = 0
        async for response in agent_stream(payload):
            response_count += 1
            print(f"\n--- Response #{response_count} ---")
            print(f"Type: {type(response).__name__}")

            # Handle different response types
            if isinstance(response, dict):
                # JSON response (like auth URLs or errors)
                print(f"Content: {response}")
            else:
                # Message chunk
                print(f"Content: {response}")

        print(f"\n{'='*80}")
        print(f"Test completed. Received {response_count} responses.")
        print(f"{'='*80}\n")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_local.py 'your query here'")
        print("\nExamples:")
        print("  python test_local.py 'Hello, what tools do you have?'")
        print("  python test_local.py 'Get patient information for ID 12345'")
        sys.exit(1)

    query = " ".join(sys.argv[1:])
    asyncio.run(test_agent(query))
