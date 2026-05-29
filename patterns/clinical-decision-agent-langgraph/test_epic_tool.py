#!/usr/bin/env python3
"""Test Epic FHIR tool call locally"""

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

from clinical_decision_agent import create_clinical_decision_agent, create_epic_fhir_tools, create_gateway_mcp_client, get_gateway_access_token


async def test_epic_tool():
    print("\n=== Testing Epic FHIR Tool Call ===\n")

    # Create Epic tools
    callback_url = "https://main.***REMOVED_AMPLIFY_APP_ID***.amplifyapp.com/oauth/callback"
    epic_tools = create_epic_fhir_tools(callback_url)
    print(f"Created {len(epic_tools)} Epic FHIR tools")

    # Create Gateway tools
    access_token = get_gateway_access_token()
    gateway_client = await create_gateway_mcp_client(access_token)
    gateway_tools = await gateway_client.get_tools()

    # Filter out Epic tools from Gateway
    filtered_gateway_tools = [t for t in gateway_tools if not any(e in str(t.name).lower() for e in ['epic', 'fhir', 'patient', 'medication', 'allergy', 'observation'])]

    all_tools = epic_tools + filtered_gateway_tools
    print(f"Total tools: {len(all_tools)}")
    print(f"Epic tools: {[t.name for t in epic_tools]}")

    # Create agent
    graph = await create_clinical_decision_agent("test-user", "test-session", all_tools)
    print("Agent created\n")

    # Test with patient query - use fresh session to avoid memory issues
    import uuid
    session_id = f"test-session-{uuid.uuid4().hex[:8]}"
    config = {
        "configurable": {
            "thread_id": session_id,
            "actor_id": "test-user-epic-tool"
        }
    }
    print(f"Using fresh session: {session_id}")

    query = "Get patient information for patient ID 12345"
    print(f"Query: {query}\n")
    print("="*80)

    # Stream the response
    event_count = 0
    async for event in graph.astream(
        {"messages": [("user", query)]},
        config=config,
        stream_mode="messages"
    ):
        event_count += 1
        message_chunk, metadata = event

        # Print the content
        if hasattr(message_chunk, 'content'):
            content = message_chunk.content
            if isinstance(content, str):
                print(content, end='', flush=True)
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and 'text' in item:
                        print(item['text'], end='', flush=True)
                    elif isinstance(item, dict) and 'type' in item:
                        if item['type'] == 'tool_use':
                            print(f"\n[TOOL CALL: {item.get('name', 'unknown')}]", flush=True)
                            print(f"  Input: {item.get('input', {})}", flush=True)

        # Check for tool calls
        if hasattr(message_chunk, 'tool_calls') and message_chunk.tool_calls:
            print(f"\n[TOOL CALLS: {message_chunk.tool_calls}]")

    print(f"\n\n{'='*80}")
    print(f"Total events: {event_count}")


if __name__ == "__main__":
    asyncio.run(test_epic_tool())
