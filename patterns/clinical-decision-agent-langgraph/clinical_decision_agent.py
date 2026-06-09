# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Clinical Decision Support Agent with LangGraph and Epic 3LO Integration

This agent provides real-time clinical decision support by:
1. Retrieving patient data from Epic FHIR (with user authorization via 3LO)
2. Analyzing drug interactions, contraindications, and allergies
3. Providing safety recommendations and alternatives

Uses Epic 3LO (Three-Legged OAuth) for user-authorized access to patient data.
The OAuth flow is handled automatically by AgentCore Identity with the
@requires_access_token decorator on Epic FHIR tools.
"""

from langgraph.prebuilt import create_react_agent
from langchain_aws import ChatBedrock
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph_checkpoint_aws import AgentCoreMemorySaver
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from typing import Any, Dict
import os
import threading
import boto3
from bedrock_agentcore.runtime import BedrockAgentCoreApp
import traceback
import asyncio
from typing import Dict, Any, Optional

from gateway.utils.gateway_access_token import get_gateway_access_token
import epic_fhir_direct
from tools.observability import initialize_telemetry

app = BedrockAgentCoreApp()

initialize_telemetry(service_name="clinical-decision-langgraph")

# Store authorization URLs for streaming to frontend
auth_url_queue = asyncio.Queue()


def get_ssm_parameter(parameter_name: str) -> str:
    """
    Fetch parameter from SSM Parameter Store.

    SSM Parameter Store is AWS's service for storing configuration values securely.
    This function retrieves values like Gateway URLs that are set during deployment.
    """
    region = os.environ.get('AWS_REGION', os.environ.get('AWS_DEFAULT_REGION', 'us-east-1'))
    ssm = boto3.client('ssm', region_name=region)
    try:
        response = ssm.get_parameter(Name=parameter_name)
        return response['Parameter']['Value']
    except ssm.exceptions.ParameterNotFound:
        raise ValueError(f"SSM parameter not found: {parameter_name}")
    except Exception as e:
        raise ValueError(f"Failed to retrieve SSM parameter {parameter_name}: {e}")


def _load_tools_in_thread(gateway_url: str, access_token: str) -> list:
    """
    Load MCP tools in a separate thread with its own event loop.

    From within the AgentCore container, the V2 gateway URL DNS resolution hangs
    indefinitely (no VPC endpoint). Using a daemon thread with threading.join(timeout)
    gives us a hard wall-clock timeout that cannot be blocked by asyncio/anyio internals.
    """
    result: dict = {"tools": [], "error": None}

    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            client = MultiServerMCPClient({
                "shared-gateway": {
                    "transport": "streamable_http",
                    "url": gateway_url,
                    "headers": {"Authorization": f"Bearer {access_token}"}
                }
            })
            result["tools"] = loop.run_until_complete(client.get_tools())
        except Exception as e:
            result["error"] = e
        finally:
            loop.close()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=30.0)
    if t.is_alive():
        print("[CLINICAL-STREAM] Gateway tools timed out after 30s, proceeding without gateway tools")
        return []
    if result["error"]:
        raise result["error"]
    return result["tools"]


async def stream_auth_url_callback(url: str):
    """Callback to capture Epic OAuth authorization URL"""
    await auth_url_queue.put({
        "type": "elicitation",
        "elicitation": {
            "authorizationUrl": url,
            "url": url,  # Include both for compatibility
            "resourceType": "Epic FHIR",
            "scopes": ["user/Patient.read", "user/MedicationRequest.read", "user/AllergyIntolerance.read", "user/Observation.read"]
        }
    })
    print(f"[EPIC-AUTH] Authorization URL queued: {url}")


def create_epic_fhir_tools(callback_url: str):
    """
    Create LangChain tools for direct Epic FHIR API calls with AgentCore Identity.

    These tools bypass the Gateway and call Epic FHIR directly with user authorization.
    """
    # Set callback URL for OAuth
    epic_fhir_direct.OAUTH_CALLBACK_URL = callback_url
    # Set the auth URL queue so epic_fhir_direct can queue messages
    epic_fhir_direct.AUTH_URL_QUEUE = auth_url_queue

    @tool
    async def get_patient(patient_id: str) -> str:
        """Get patient demographics from Epic FHIR with user authorization.

        Args:
            patient_id: The Epic FHIR patient ID (required)
        """
        result = await epic_fhir_direct.get_patient(patient_id)
        return str(result)

    @tool
    async def get_medications(patient_id: str) -> str:
        """Get active medications for a patient from Epic FHIR.

        Args:
            patient_id: The Epic FHIR patient ID (required)
        """
        result = await epic_fhir_direct.get_medications(patient_id)
        return str(result)

    @tool
    async def get_allergies(patient_id: str) -> str:
        """Get patient allergies from Epic FHIR.

        Args:
            patient_id: The Epic FHIR patient ID (required)
        """
        result = await epic_fhir_direct.get_allergies(patient_id)
        return str(result)

    @tool
    async def get_observations(patient_id: str) -> str:
        """Get patient observations (labs, vitals) from Epic FHIR.

        Args:
            patient_id: The Epic FHIR patient ID (required)
        """
        result = await epic_fhir_direct.get_observations(patient_id, category=None)
        return str(result)

    return [get_patient, get_medications, get_allergies, get_observations]


async def create_gateway_mcp_client(access_token: str) -> MultiServerMCPClient:
    """
    Create an MCP client connected to the Shared Gateway for non-Epic tools.

    This client connects to the AgentCore Gateway that exposes HealthLake and
    Comprehend Medical tools. Epic FHIR tools are called directly via AgentCore Identity.
    """
    stack_name = os.environ.get('STACK_NAME')
    if not stack_name:
        raise ValueError("STACK_NAME environment variable is required")

    # Validate stack name format to prevent injection
    if not stack_name.replace('-', '').replace('_', '').isalnum():
        raise ValueError("Invalid STACK_NAME format")

    print(f"[CLINICAL-AGENT] Creating Shared Gateway MCP client for stack: {stack_name}")

    # Fetch Shared Gateway URL from SSM
    gateway_url = get_ssm_parameter(f'/{stack_name}/shared-gateway-url')
    print(f"[CLINICAL-AGENT] Shared Gateway URL from SSM: {gateway_url}")

    # Create MultiServerMCPClient with Gateway configuration
    gateway_client = MultiServerMCPClient({
        "shared-gateway": {
            "transport": "streamable_http",
            "url": gateway_url,
            "headers": {
                "Authorization": f"Bearer {access_token}"
            }
        }
    })

    print(f"[CLINICAL-AGENT] Shared Gateway MCP client created successfully")
    return gateway_client


class BedrockChatModelFixed(ChatBedrock):
    """ChatBedrock wrapper that prevents parallel_tool_calls parameter from being sent to Bedrock API."""

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        # Remove parallel_tool_calls parameter as Bedrock doesn't support it
        kwargs_clean = {k: v for k, v in kwargs.items() if k != "parallel_tool_calls"}
        return super().bind_tools(tools, **kwargs_clean)


async def create_clinical_decision_agent(user_id: str, session_id: str, tools: list):
    """
    Create a LangGraph agent for clinical decision support with Epic FHIR tools.

    This agent uses Epic 3LO (user federation) to access patient data with
    user authorization. On first invocation, the user will be prompted to
    authorize via Epic login.
    """
    system_prompt = """You are a clinical decision support agent that helps healthcare providers make safe medication decisions.

When analyzing a medication for a patient, you MUST:

1. **Retrieve Patient Data** (using Epic 3LO with user authorization):
   - Current medications - use get_medications tool
   - Allergies - use get_allergies tool
   - Recent lab results - use get_observations tool
   - Patient demographics - use get_patient tool

NOTE: On first use, these tools will trigger an Epic authorization flow. The user will need to:
- Click the authorization URL
- Log in to Epic
- Grant permission to access patient data
After authorization, subsequent calls will work automatically.

2. **Analyze Drug Safety**:
   - Check for drug-drug interactions
   - Identify contraindications based on patient conditions
   - Flag allergy concerns
   - Consider lab values (e.g., kidney function for renally-cleared drugs)

3. **Provide Recommendations**:
   - Rate safety level: SAFE, CAUTION, or CONTRAINDICATED
   - List specific concerns with severity ratings
   - Suggest alternatives if contraindicated
   - Include clinical guidance

4. **Be Accurate and Conservative**:
   - If unsure, recommend consulting pharmacy or references
   - Always prioritize patient safety
   - Use evidence-based guidelines

Available Epic FHIR tools (via 3LO user federation):
- get_patient: Get patient demographics
- get_medications: Get current active medications
- get_allergies: Get allergy history
- get_observations: Get lab results and vitals

All tools require Epic user authorization on first use.
"""

    # Create Bedrock model with fix for parallel_tool_calls parameter
    # Bedrock Converse API doesn't accept parallel_tool_calls parameter at all
    bedrock_model = BedrockChatModelFixed(
        model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        temperature=0.1,  # Low temperature for clinical accuracy
        streaming=True
    )

    print(f"[CLINICAL-AGENT] Bedrock model created (fixed): {bedrock_model.model_id}")
    print(f"[CLINICAL-AGENT] Streaming enabled: {bedrock_model.streaming}")
    print(f"[CLINICAL-AGENT] Using BedrockChatModelFixed to prevent parallel_tool_calls parameter")

    # Get and validate Memory ID
    memory_id = os.environ.get("MEMORY_ID")
    if not memory_id:
        raise ValueError("MEMORY_ID environment variable is required")

    # Configure AgentCore Memory using official LangGraph AWS integration
    checkpointer = AgentCoreMemorySaver(
        memory_id=memory_id,
        region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
    )

    try:
        print("[CLINICAL-AGENT] Creating LangGraph agent with Epic FHIR tools...")

        graph = create_react_agent(
            model=bedrock_model,
            tools=tools,
            checkpointer=checkpointer,
            prompt=system_prompt
        )

        print(f"[CLINICAL-AGENT] Agent created successfully with {len(tools)} Epic FHIR tools")
        return graph

    except Exception as e:
        print(f"[CLINICAL-AGENT ERROR] Error creating LangGraph agent: {e}")
        print(f"[CLINICAL-AGENT ERROR] Exception type: {type(e).__name__}")
        print(f"[CLINICAL-AGENT ERROR] Traceback:")
        traceback.print_exc()
        raise


@app.entrypoint
async def agent_stream(payload: Dict[str, Any]):
    """
    Main entrypoint for the clinical decision support agent with streaming.

    This function handles the complete request lifecycle:
    1. Extracts patient query and context
    2. Gets OAuth2 token for gateway access
    3. Creates MCP client for Epic FHIR Gateway
    4. Loads Epic FHIR tools (with 3LO support)
    5. Creates LangGraph agent with tools and memory
    6. Streams the response back

    Expected payload:
    {
        "prompt": "Check if Metformin is safe for patient 8MsEzCJO3BA3",
        "userId": "dr-john-smith",
        "runtimeSessionId": "session-123",
        "patientId": "8MsEzCJO3BA3",  # Optional - can be in prompt
        "medication": "Metformin"  # Optional - can be in prompt
    }
    """
    user_query = payload.get("prompt")
    user_id = payload.get("userId")
    session_id = payload.get("runtimeSessionId")
    patient_id = payload.get("patientId")
    medication = payload.get("medication")

    if not all([user_query, user_id, session_id]):
        yield {
            "status": "error",
            "error": "Missing required fields: prompt, userId, or runtimeSessionId"
        }
        return

    # Enhance query with context if provided
    if patient_id and medication and not (patient_id in user_query and medication in user_query):
        enhanced_query = f"{user_query}\n\nContext: Analyzing {medication} for patient {patient_id}"
    else:
        enhanced_query = user_query

    try:
        # Do not log PHI (patient queries, patient identifiers, medications) in
        # clear text. Log only non-sensitive metadata such as session presence.
        print(f"[CLINICAL-STREAM] Starting clinical decision support for session: {session_id}")
        print(f"[CLINICAL-STREAM] Query received (length={len(enhanced_query)} chars)")
        if patient_id:
            print("[CLINICAL-STREAM] Patient context provided")
        if medication:
            print("[CLINICAL-STREAM] Medication context provided")

        # Get callback URL from environment (Amplify URL)
        stack_name = os.environ.get('STACK_NAME', 'healthcare-agents-stack')
        callback_url_param = f'/{stack_name}/amplify-url'
        amplify_url = get_ssm_parameter(callback_url_param)
        oauth_callback_url = f"{amplify_url}/oauth/callback"
        print(f"[CLINICAL-STREAM] OAuth callback URL: {oauth_callback_url}")

        # Create Epic FHIR tools with direct AgentCore Identity calls
        print("[CLINICAL-STREAM] Creating Epic FHIR tools with AgentCore Identity (3LO)...")
        epic_tools = create_epic_fhir_tools(oauth_callback_url)
        print(f"[CLINICAL-STREAM] Created {len(epic_tools)} Epic FHIR tools")

        # Get OAuth2 access token for Gateway (HealthLake, Comprehend Medical)
        print("[CLINICAL-STREAM] Getting OAuth2 access token for Shared Gateway...")
        access_token = get_gateway_access_token()
        print(f"[CLINICAL-STREAM] Got access token: <redacted>")

        # Load Gateway tools (HealthLake, Comprehend Medical) via isolated thread.
        # Best-effort: if gateway is unreachable from container VPC, proceed with Epic tools only.
        filtered_gateway_tools = []
        try:
            stack_name = os.environ.get('STACK_NAME', 'healthcare-agents-stack')
            gateway_url = get_ssm_parameter(f'/{stack_name}/shared-gateway-url')
            print(f"[CLINICAL-STREAM] Loading Gateway tools from {gateway_url}...")
            gateway_tools = await asyncio.to_thread(_load_tools_in_thread, gateway_url, access_token)
            filtered_gateway_tools = [
                t for t in gateway_tools
                if not any(epic_name in str(t.name).lower()
                          for epic_name in ['epic', 'fhir', 'patient', 'medication', 'allergy', 'observation'])
            ]
            print(f"[CLINICAL-STREAM] Loaded {len(filtered_gateway_tools)} Gateway tools (non-Epic)")
        except BaseException as e:
            print(f"[CLINICAL-STREAM] Gateway tools unavailable ({type(e).__name__}: {e}), using Epic tools only")

        # Combine Epic FHIR tools with Gateway tools
        all_tools = epic_tools + filtered_gateway_tools
        print(f"[CLINICAL-STREAM] Total tools available: {len(all_tools)}")

        # Log available tools for debugging
        tool_names = [t.name if hasattr(t, 'name') else str(t) for t in all_tools]
        print(f"[CLINICAL-STREAM] Available tools: {', '.join(tool_names)}")

        # Create clinical decision agent with all tools
        graph = await create_clinical_decision_agent(user_id, session_id, all_tools)

        # Configure streaming with actor_id and thread_id for memory
        config = {
            "configurable": {
                "thread_id": session_id,
                "actor_id": user_id
            }
        }

        # Stream messages using LangGraph's astream with stream_mode="messages"
        # Match the exact working pattern from langgraph-single-agent
        print(f"[CLINICAL-STREAM] Starting streaming...")

        event_count = 0
        auth_url_count = 0

        # Check queue before starting stream (tools might have already queued URLs)
        print(f"[CLINICAL-STREAM] Pre-stream queue check: {auth_url_queue.qsize()} messages")
        while not auth_url_queue.empty():
            try:
                auth_msg = auth_url_queue.get_nowait()
                auth_url_count += 1
                print(f"[CLINICAL-STREAM] Pre-stream auth URL #{auth_url_count}: yielding")
                yield auth_msg
            except:
                break

        # Simple approach: stream graph events and check queue after each batch
        async for event in graph.astream(
            {"messages": [("user", enhanced_query)]},
            config=config,
            stream_mode="messages"
        ):
            event_count += 1
            if event_count % 10 == 0:
                print(f"[CLINICAL-STREAM] Event #{event_count}, queue: {auth_url_queue.qsize()}")

            # Yield graph event
            message_chunk, metadata = event
            yield message_chunk

            # Immediately check and yield ALL queued auth URLs
            while not auth_url_queue.empty():
                try:
                    auth_msg = auth_url_queue.get_nowait()
                    auth_url_count += 1
                    print(f"[CLINICAL-STREAM] !! YIELDING AUTH URL #{auth_url_count} !!")
                    yield auth_msg
                except Exception as e:
                    print(f"[CLINICAL-STREAM] Error yielding: {e}")
                    break

        # Post-stream: yield any remaining auth URLs
        print(f"[CLINICAL-STREAM] Stream done. Final queue check: {auth_url_queue.qsize()}")
        while not auth_url_queue.empty():
            auth_msg = auth_url_queue.get_nowait()
            auth_url_count += 1
            print(f"[CLINICAL-STREAM] !! POST-STREAM AUTH URL #{auth_url_count} !!")
            yield auth_msg

        print(f"[CLINICAL-STREAM] Complete: {event_count} events, {auth_url_count} auth URLs")

    except Exception as e:
        error_msg = str(e) if str(e) else f"{type(e).__name__}: {repr(e)}"
        print(f"[CLINICAL-STREAM ERROR] Error in agent_stream: {error_msg}")
        print(f"[CLINICAL-STREAM ERROR] Exception type: {type(e).__name__}")
        traceback.print_exc()

        # Check if this is an authorization error (Epic 3LO flow)
        if 'authorization' in error_msg.lower() or 'auth' in error_msg.lower():
            yield {
                "status": "authorization_required",
                "message": "Epic user authorization needed. Please complete the OAuth flow.",
                "error": error_msg
            }
        else:
            yield {
                "status": "error",
                "error": error_msg
            }


if __name__ == "__main__":
    app.run()
