#!/usr/bin/env python3
"""
Local test runner for langgraph-single-agent.

Bypasses BedrockAgentCoreApp and calls the agent logic directly.

Usage:
    cd /path/to/healthcare-agents
    AWS_PROFILE=quicksuite uv run python3 patterns/langgraph-single-agent/test_local.py
    AWS_PROFILE=quicksuite uv run python3 patterns/langgraph-single-agent/test_local.py "Hello, what can you do?"
"""

import asyncio
import os
import sys

# Set required env vars before importing the agent module
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("STACK_NAME", "healthcare-agents-stack")

# Memory ID extracted from the deployed stack ARN
os.environ.setdefault(
    "MEMORY_ID",
    "healthcareagentsstacklanggraphsingleagent-7R0Vs38jOc"
)

# Add the agent directory and repo root to sys.path
agent_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.dirname(os.path.dirname(agent_dir))
sys.path.insert(0, agent_dir)
sys.path.insert(0, repo_root)

from langgraph_agent import create_gateway_mcp_client, create_langgraph_agent
from gateway.utils.gateway_access_token import get_gateway_access_token


async def run_local(prompt: str):
    print(f"Prompt: {prompt}\n" + "-" * 60)

    # Get access token
    print("Getting OAuth2 access token...")
    access_token = get_gateway_access_token()
    print(f"Token: <redacted>\n")

    # Load gateway tools (best-effort)
    tools = []
    try:
        print("Connecting to Gateway MCP...")
        mcp_client = await create_gateway_mcp_client(access_token)
        tools = await asyncio.wait_for(mcp_client.get_tools(), timeout=30.0)
        print(f"Loaded {len(tools)} tools: {[t.name for t in tools]}\n")
    except BaseException as e:
        print(f"Gateway tools unavailable ({type(e).__name__}: {e}), proceeding without tools\n")

    # Create agent
    graph = await create_langgraph_agent(
        user_id="local-test-user",
        session_id="local-test-session",
        tools=tools,
    )

    config = {
        "configurable": {
            "thread_id": "local-test-session",
            "actor_id": "local-test-user",
        }
    }

    print("Response:")
    async for event in graph.astream(
        {"messages": [("user", prompt)]},
        config=config,
        stream_mode="messages",
    ):
        message_chunk, metadata = event
        content = getattr(message_chunk, "content", "")
        if isinstance(content, str) and content:
            print(content, end="", flush=True)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    print(block.get("text", ""), end="", flush=True)

    print("\n" + "-" * 60)


if __name__ == "__main__":
    prompt = sys.argv[1] if len(sys.argv) > 1 else "What tools do you have available? Please list them."
    asyncio.run(run_local(prompt))
