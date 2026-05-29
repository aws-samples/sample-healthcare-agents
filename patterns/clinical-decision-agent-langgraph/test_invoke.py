#!/usr/bin/env python3
"""Test direct invoke (non-streaming)"""

import asyncio
import os
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(Path(__file__).parent))

os.environ['STACK_NAME'] = 'healthcare-agents-stack'
os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'
os.environ['AWS_REGION'] = 'us-east-1'
os.environ['AWS_PROFILE'] = 'quicksuite'
os.environ['MEMORY_ID'] = 'healthcareagentsstaccisionagentlanggraph8D377B5B-2TnPwfATix'

from clinical_decision_agent import create_clinical_decision_agent, create_epic_fhir_tools, create_gateway_mcp_client, get_ssm_parameter, get_gateway_access_token


async def test_invoke():
    print("\n=== Testing Direct Invoke ===\n")

    # Create tools
    callback_url = "https://main.***REMOVED_AMPLIFY_APP_ID***.amplifyapp.com/oauth/callback"
    epic_tools = create_epic_fhir_tools(callback_url)
    print(f"Created {len(epic_tools)} Epic tools")

    access_token = get_gateway_access_token()
    gateway_client = await create_gateway_mcp_client(access_token)
    gateway_tools = await gateway_client.get_tools()
    print(f"Loaded {len(gateway_tools)} Gateway tools")

    all_tools = epic_tools + [t for t in gateway_tools if not any(e in str(t.name).lower() for e in ['epic', 'fhir', 'patient', 'medication'])]
    print(f"Total tools: {len(all_tools)}")

    # Create agent
    graph = await create_clinical_decision_agent("test-user", "test-session", all_tools)
    print("Agent created")

    # Test invoke
    config = {
        "configurable": {
            "thread_id": "test-session-invoke",
            "actor_id": "test-user-invoke"
        }
    }

    print("\nInvoking with: 'Hello'")
    result = await graph.ainvoke({"messages": [("user", "Hello")]}, config=config)

    print(f"\nResult type: {type(result)}")
    print(f"Result keys: {result.keys() if isinstance(result, dict) else 'N/A'}")

    if isinstance(result, dict) and "messages" in result:
        messages = result["messages"]
        print(f"\nGot {len(messages)} messages:")
        for i, msg in enumerate(messages):
            print(f"  {i+1}. {type(msg).__name__}: {str(msg)[:100]}")
    else:
        print(f"\nResult: {result}")


if __name__ == "__main__":
    asyncio.run(test_invoke())
