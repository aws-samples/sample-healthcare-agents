# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Eligibility Verification Agent using Strands SDK.

Verifies patient insurance eligibility and benefits by:
1. Retrieving patient demographics and coverage from HealthLake (FHIR R4)
2. Checking insurance plan active status and effective dates
3. Verifying coverage for specific procedures/services
4. Identifying copay, coinsurance, deductible, and out-of-pocket amounts
5. Determining if prior authorization is required for the service

Uses AgentCore Gateway for HealthLake tools and AgentCore Memory for
conversation state persistence.
"""

import os
import traceback

import boto3
from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig
from bedrock_agentcore.memory.integrations.strands.session_manager import (
    AgentCoreMemorySessionManager,
)
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from gateway.utils.gateway_access_token import get_gateway_access_token
from mcp.client.streamable_http import streamablehttp_client
from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient

app = BedrockAgentCoreApp()


def get_ssm_parameter(parameter_name: str) -> str:
    """Fetch parameter from SSM Parameter Store."""
    region = os.environ.get(
        "AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
    )
    ssm = boto3.client("ssm", region_name=region)
    try:
        response = ssm.get_parameter(Name=parameter_name)
        return response["Parameter"]["Value"]
    except ssm.exceptions.ParameterNotFound:
        raise ValueError(f"SSM parameter not found: {parameter_name}")
    except Exception as e:
        raise ValueError(f"Failed to retrieve SSM parameter {parameter_name}: {e}")


def get_system_prompt(ssm_path: str) -> str:
    """
    Fetch system prompt from Bedrock Prompt Management via SSM.
    """
    region = os.environ.get(
        "AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
    )
    ssm_client = boto3.client("ssm", region_name=region)
    prompt_arn = ssm_client.get_parameter(Name=ssm_path)["Parameter"]["Value"]

    bedrock_client = boto3.client("bedrock-agent", region_name=region)
    arn_parts = prompt_arn.split(":")
    prompt_id = arn_parts[-2].split("/")[-1]
    prompt_version = arn_parts[-1]
    response = bedrock_client.get_prompt(
        promptIdentifier=prompt_id,
        promptVersion=prompt_version,
    )
    return response["variants"][0]["templateConfiguration"]["text"]["text"]


def create_gateway_mcp_client(access_token: str) -> MCPClient:
    """
    Create MCP client for AgentCore Gateway with OAuth2 authentication.

    Provides access to HealthLake tools for patient demographics, coverage,
    and clinical data retrieval.
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


DEFAULT_SYSTEM_PROMPT = """You are an Eligibility Verification Agent specializing in healthcare insurance eligibility and benefits verification.

Your role is to help healthcare providers verify patient insurance coverage before delivering services.

## Capabilities

You have access to HealthLake tools via the Gateway to retrieve patient and coverage data:
- **get_patient_conditions**: Retrieve patient diagnoses and conditions
- **get_patient_medications**: Get current medications
- **get_patient_observations**: Access lab results and vitals
- **get_patient_allergies**: Check allergy records
- **get_patient_appointments**: View appointments
- **get_patient_everything**: Comprehensive patient data retrieval
- **advanced_patient_search**: Search patients by demographics

## Eligibility Verification Workflow

When verifying eligibility, follow these steps:

### 1. Patient Identification
- Retrieve patient demographics from HealthLake
- Verify patient identity (name, date of birth, member ID)
- Confirm the patient record matches the request

### 2. Coverage Verification
- Check if the patient has active insurance coverage
- Verify the coverage effective dates (start and end)
- Identify the insurance plan, payor, and group information
- Determine the type of coverage (commercial, Medicare, Medicaid, etc.)

### 3. Benefits Check
- Determine if the requested service/procedure is a covered benefit
- Identify any benefit limitations or exclusions
- Check remaining benefit amounts (visits, dollar limits)
- Verify network status of the requesting provider

### 4. Cost Sharing Details
- Identify the patient's copay amount for the service
- Determine coinsurance percentage
- Check deductible status (met vs. remaining)
- Calculate estimated out-of-pocket cost for the patient
- Check out-of-pocket maximum status

### 5. Prior Authorization Determination
- Determine if the requested service requires prior authorization
- Identify which services under the plan need prior auth
- Check if a prior authorization is already on file
- Provide the prior authorization requirements if needed

### 6. Provide Summary
- Present a clear eligibility verification summary
- Include coverage status, benefits, and cost sharing
- Flag any issues (inactive coverage, excluded services, etc.)
- Recommend next steps (proceed, obtain prior auth, contact payor)

## Important Guidelines
- Always retrieve actual patient data from HealthLake before making determinations
- Clearly distinguish between verified data and estimated/assumed information
- If coverage data is not available in HealthLake, state that a real-time eligibility check with the payor (270/271 transaction) is recommended
- Follow HIPAA guidelines — do not expose PHI unnecessarily
- Provide structured, actionable responses with clear next steps
"""


def create_eligibility_agent(user_id: str, session_id: str) -> Agent:
    """
    Create an eligibility verification agent with Gateway MCP tools and memory.
    """
    prompt_ssm_path = os.environ.get("SYSTEM_PROMPT_SSM_PATH")
    if prompt_ssm_path:
        try:
            print("[AGENT] Fetching system prompt from Bedrock Prompt Management...")
            system_prompt = get_system_prompt(prompt_ssm_path)
        except Exception as e:
            print(f"[AGENT] Failed to fetch prompt from Bedrock: {e}, using default")
            system_prompt = DEFAULT_SYSTEM_PROMPT
    else:
        system_prompt = DEFAULT_SYSTEM_PROMPT

    bedrock_model = BedrockModel(
        model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        temperature=0.1,
    )

    memory_id = os.environ.get("MEMORY_ID")
    if not memory_id:
        raise ValueError("MEMORY_ID environment variable is required")

    agentcore_memory_config = AgentCoreMemoryConfig(
        memory_id=memory_id, session_id=session_id, actor_id=user_id
    )

    session_manager = AgentCoreMemorySessionManager(
        agentcore_memory_config=agentcore_memory_config,
        region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
    )

    try:
        print("[AGENT] Starting eligibility verification agent creation...")

        print("[AGENT] Step 1: Getting OAuth2 access token...")
        access_token = get_gateway_access_token()
        print(f"[AGENT] Got access token (length={len(access_token)})")  # T11: do not log token prefix

        print("[AGENT] Step 2: Creating Gateway MCP client...")
        gateway_client = create_gateway_mcp_client(access_token)
        print("[AGENT] Gateway MCP client created successfully")

        print("[AGENT] Step 3: Creating Agent with Gateway tools...")
        agent = Agent(
            name="EligibilityVerificationAgent",
            system_prompt=system_prompt,
            tools=[gateway_client],
            model=bedrock_model,
            session_manager=session_manager,
            trace_attributes={
                "user.id": user_id,
                "session.id": session_id,
                "agent.type": "eligibility-verification",
            },
        )
        print("[AGENT] Eligibility verification agent created successfully")
        return agent

    except Exception as e:
        print(f"[AGENT ERROR] Error creating agent: {e}")
        print(f"[AGENT ERROR] Exception type: {type(e).__name__}")
        traceback.print_exc()
        raise


@app.entrypoint
async def agent_stream(payload):
    """
    Main entrypoint for the eligibility verification agent with streaming.

    Expected payload:
    {
        "prompt": "Verify eligibility for patient P001 for an MRI procedure",
        "userId": "provider-123",
        "runtimeSessionId": "session-abc"
    }
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
        print(
            f"[STREAM] Starting eligibility agent for user: {user_id}, session: {session_id}"
        )
        print(f"[STREAM] Query: {user_query}")

        agent = create_eligibility_agent(user_id, session_id)

        async for event in agent.stream_async(user_query):
            yield event

    except Exception as e:
        print(f"[STREAM ERROR] Error in agent_stream: {e}")
        traceback.print_exc()
        yield {"status": "error", "error": str(e)}


if __name__ == "__main__":
    app.run()
