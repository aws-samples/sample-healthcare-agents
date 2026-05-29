# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Medical Coding Agent using Strands SDK.

Extracts medical entities using Comprehend Medical and searches for
ICD-10-CM, CPT, and SNOMED CT codes using Bedrock Knowledge Base.
"""

import os
import json
import traceback
import boto3
from typing import Dict, Any, List
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig
from bedrock_agentcore.memory.integrations.strands.session_manager import (
    AgentCoreMemorySessionManager,
)
from gateway.utils.gateway_access_token import get_gateway_access_token
from mcp.client.streamable_http import streamablehttp_client
from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient

app = BedrockAgentCoreApp()


def get_system_prompt(ssm_path: str) -> str:
    """
    Fetch system prompt text from Bedrock Prompt Management.

    Looks up the versioned prompt ARN from SSM Parameter Store, then retrieves
    the prompt text from Bedrock Prompt Management.

    Args:
        ssm_path: SSM parameter path storing the versioned prompt ARN
                  (e.g. /my-stack/prompts/medical-coding-agent)

    Returns:
        The prompt text from the default variant
    """
    region = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
    ssm_client = boto3.client("ssm", region_name=region)
    prompt_arn = ssm_client.get_parameter(Name=ssm_path)["Parameter"]["Value"]

    bedrock_client = boto3.client("bedrock-agent", region_name=region)
    # Versioned ARN format: arn:aws:bedrock:region:account:prompt/promptId:version
    arn_parts = prompt_arn.split(":")
    prompt_id = arn_parts[-2].split("/")[-1]
    prompt_version = arn_parts[-1]
    response = bedrock_client.get_prompt(
        promptIdentifier=prompt_id,
        promptVersion=prompt_version,
    )
    return response["variants"][0]["templateConfiguration"]["text"]["text"]


def get_ssm_parameter(parameter_name: str) -> str:
    """
    Fetch parameter from SSM Parameter Store.
    
    Args:
        parameter_name: Name of the SSM parameter
        
    Returns:
        Parameter value as string
    """
    region = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
    ssm = boto3.client("ssm", region_name=region)
    try:
        response = ssm.get_parameter(Name=parameter_name)
        return response["Parameter"]["Value"]
    except ssm.exceptions.ParameterNotFound:
        raise ValueError(f"SSM parameter not found: {parameter_name}")
    except Exception as e:
        raise ValueError(f"Failed to retrieve SSM parameter {parameter_name}: {e}")


def create_gateway_mcp_client(access_token: str) -> MCPClient:
    """
    Create MCP client for AgentCore Gateway with OAuth2 authentication.
    
    Args:
        access_token: OAuth2 access token for Gateway authentication
        
    Returns:
        Configured MCPClient instance
    """
    stack_name = os.environ.get("STACK_NAME")
    if not stack_name:
        raise ValueError("STACK_NAME environment variable is required")

    if not stack_name.replace("-", "").replace("_", "").isalnum():
        raise ValueError("Invalid STACK_NAME format")

    print(f"[AGENT] Creating Gateway MCP client for stack: {stack_name}")

    gateway_url = get_ssm_parameter(f"/{stack_name}/gateway_url")
    print(f"[AGENT] Gateway URL from SSM: {gateway_url}")

    gateway_client = MCPClient(
        lambda: streamablehttp_client(
            url=gateway_url, headers={"Authorization": f"Bearer {access_token}"}
        ),
        prefix="gateway",
    )

    print("[AGENT] Gateway MCP client created successfully")
    return gateway_client


def query_knowledge_base(query: str, kb_id: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """
    Query Bedrock Knowledge Base for medical code information.
    
    Args:
        query: Search query for medical codes
        kb_id: Knowledge Base ID
        max_results: Maximum number of results to return
        
    Returns:
        List of relevant documents from knowledge base
    """
    region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
    bedrock_agent_runtime = boto3.client('bedrock-agent-runtime', region_name=region)
    
    try:
        response = bedrock_agent_runtime.retrieve(
            knowledgeBaseId=kb_id,
            retrievalQuery={'text': query},
            retrievalConfiguration={
                'vectorSearchConfiguration': {
                    'numberOfResults': max_results
                }
            }
        )
        
        results = []
        for result in response.get('retrievalResults', []):
            results.append({
                'content': result.get('content', {}).get('text', ''),
                'score': result.get('score', 0.0),
                'metadata': result.get('metadata', {})
            })
        
        return results
        
    except Exception as e:
        print(f"[KB ERROR] Error querying knowledge base: {e}")
        traceback.print_exc()
        return []


def create_kb_tool(kb_id: str):
    """
    Create a Strands tool for querying the medical codes knowledge base.
    
    Args:
        kb_id: Knowledge Base ID
        
    Returns:
        Callable tool function for Strands agent
    """
    def search_medical_codes(query: str, code_type: str = "all") -> str:
        """
        Search for medical codes in the knowledge base.
        
        Args:
            query: Description of the medical condition, procedure, or concept to find codes for
            code_type: Type of code to search for (icd10, cpt, snomed, or all)
            
        Returns:
            JSON string with relevant medical codes and their descriptions
        """
        # Enhance query with code type filter
        enhanced_query = f"{query} {code_type}" if code_type != "all" else query
        
        print(f"[KB TOOL] Searching knowledge base for: {enhanced_query}")
        results = query_knowledge_base(enhanced_query, kb_id, max_results=5)
        
        if not results:
            return json.dumps({
                "message": "No relevant codes found",
                "query": query,
                "code_type": code_type
            })
        
        formatted_results = {
            "query": query,
            "code_type": code_type,
            "results": []
        }
        
        for result in results:
            formatted_results["results"].append({
                "content": result["content"],
                "relevance_score": result["score"],
                "metadata": result["metadata"]
            })
        
        return json.dumps(formatted_results, indent=2)
    
    return search_medical_codes


def create_medical_coding_agent(user_id: str, session_id: str) -> Agent:
    """
    Create medical coding agent with Comprehend Medical and Knowledge Base tools.
    
    Args:
        user_id: User identifier
        session_id: Session identifier
        
    Returns:
        Configured Strands Agent instance
    """
    prompt_ssm_path = os.environ.get("SYSTEM_PROMPT_SSM_PATH")
    if not prompt_ssm_path:
        raise ValueError("SYSTEM_PROMPT_SSM_PATH environment variable is required")
    print("[AGENT] Fetching system prompt from Bedrock Prompt Management...")
    system_prompt = get_system_prompt(prompt_ssm_path)

    bedrock_model = BedrockModel(
        model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        temperature=0.1
    )

    # Get configuration from environment
    memory_id = os.environ.get("MEMORY_ID")
    kb_id = os.environ.get("KNOWLEDGE_BASE_ID")
    
    if not memory_id:
        raise ValueError("MEMORY_ID environment variable is required")
    if not kb_id:
        raise ValueError("KNOWLEDGE_BASE_ID environment variable is required")

    # Configure AgentCore Memory
    agentcore_memory_config = AgentCoreMemoryConfig(
        memory_id=memory_id,
        session_id=session_id,
        actor_id=user_id
    )

    session_manager = AgentCoreMemorySessionManager(
        agentcore_memory_config=agentcore_memory_config,
        region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
    )

    try:
        print("[AGENT] Creating medical coding agent...")

        # Get OAuth2 access token for Gateway
        print("[AGENT] Getting OAuth2 access token...")
        access_token = get_gateway_access_token()

        # Create Gateway MCP client (provides Comprehend Medical tools)
        print("[AGENT] Creating Gateway MCP client...")
        gateway_client = create_gateway_mcp_client(access_token)

        # Create Knowledge Base tool
        print("[AGENT] Creating Knowledge Base tool...")
        kb_tool = create_kb_tool(kb_id)

        # Create agent with all tools
        print("[AGENT] Creating Agent with Gateway and KB tools...")
        agent = Agent(
            name="MedicalCodingAgent",
            system_prompt=system_prompt,
            tools=[gateway_client, kb_tool],
            model=bedrock_model,
            session_manager=session_manager,
            trace_attributes={
                "user.id": user_id,
                "session.id": session_id,
            },
        )
        
        print("[AGENT] Medical coding agent created successfully")
        return agent

    except Exception as e:
        print(f"[AGENT ERROR] Error creating agent: {e}")
        traceback.print_exc()
        raise


@app.entrypoint
async def agent_stream(payload):
    """
    Main entrypoint for the medical coding agent with streaming.
    
    Args:
        payload: Request payload with prompt, userId, and runtimeSessionId
        
    Yields:
        Streaming response events
    """
    user_query = payload.get("prompt")
    user_id = payload.get("userId")
    session_id = payload.get("runtimeSessionId")

    if not all([user_query, user_id, session_id]):
        yield {
            "status": "error",
            "error": "Missing required fields: prompt, userId, or runtimeSessionId",
        }
        return

    try:
        print(f"[STREAM] Starting medical coding agent for user: {user_id}, session: {session_id}")
        print(f"[STREAM] Query: {user_query}")

        agent = create_medical_coding_agent(user_id, session_id)

        # Stream agent response
        async for event in agent.stream_async(user_query):
            yield event

    except Exception as e:
        print(f"[STREAM ERROR] Error in agent_stream: {e}")
        traceback.print_exc()
        yield {"status": "error", "error": str(e)}


if __name__ == "__main__":
    app.run()
