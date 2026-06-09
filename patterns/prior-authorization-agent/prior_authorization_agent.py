# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Prior Authorization Agent using Strands SDK.

Automates healthcare prior authorization workflows by:
1. Gathering clinical data from HealthLake (FHIR R4)
2. Checking payor-specific requirements and medical necessity criteria
3. Assembling authorization requests with supporting documentation
4. Submitting to payor systems and tracking status
5. Notifying stakeholders of decisions

Uses AgentCore Gateway for HealthLake tools and AgentCore Memory for
conversation/workflow state persistence.
"""

import os
import json
import traceback

import boto3
from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig
from bedrock_agentcore.memory.integrations.strands.session_manager import (
    AgentCoreMemorySessionManager,
)
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from gateway.utils.gateway_access_token import get_gateway_access_token
from mcp.client.streamable_http import streamablehttp_client
from strands import Agent, tool
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient

from claim_bundle_builder import ClaimBundleBuilder, Coding, ServiceItem
from claim_response_generator import ClaimResponseGenerator

app = BedrockAgentCoreApp()

# Module-level instances for FHIR resource generation
_claim_bundle_builder = ClaimBundleBuilder()
_claim_response_generator = ClaimResponseGenerator()


@tool
def build_pas_claim_bundle(
    patient: dict,
    practitioner: dict,
    coverage: dict | None,
    insurer: dict,
    service_items_data: list[dict],
    supporting_info: list[dict],
    priority: str,
    questionnaire_response: dict | None = None,
) -> dict:
    """Build a FHIR PAS Bundle containing a Claim (use=preauthorization) and all referenced resources.

    Call this tool after assembling clinical data (Step 5) to produce a standards-compliant
    Da Vinci PAS Bundle. The Bundle includes the Claim and all supporting FHIR resources.

    Args:
        patient: FHIR Patient resource dict from HealthLake.
        practitioner: FHIR Practitioner resource dict.
        coverage: FHIR Coverage resource dict, or None if missing.
        insurer: FHIR Organization resource dict (the payer).
        service_items_data: List of dicts, each with keys:
            - product_or_service: dict with "system", "code", and optional "display"
            - diagnosis_link_ids: list of int (1-based indices into supporting_info Conditions)
            - quantity: optional float
            - unit_price: optional float
        supporting_info: List of FHIR resources (Condition, MedicationRequest, Observation).
        priority: One of "normal", "urgent", "emergency".
        questionnaire_response: Optional FHIR QuestionnaireResponse dict.

    Returns:
        dict with keys "claim", "bundle", and "validation_issues". If coverage is missing,
        returns the error dict from build_claim instead.
    """
    # Convert service_items_data dicts to ServiceItem dataclass instances
    items = []
    for si in service_items_data:
        pos = si.get("product_or_service", {})
        coding = Coding(
            system=pos.get("system", ""),
            code=pos.get("code", ""),
            display=pos.get("display"),
        )
        items.append(
            ServiceItem(
                product_or_service=coding,
                diagnosis_link_ids=si.get("diagnosis_link_ids", []),
                quantity=si.get("quantity"),
                unit_price=si.get("unit_price"),
            )
        )

    claim = _claim_bundle_builder.build_claim(
        patient=patient,
        practitioner=practitioner,
        coverage=coverage,
        insurer=insurer,
        service_items=items,
        supporting_info=supporting_info,
        priority=priority,
    )

    # If build_claim returned an error (e.g. missing coverage), return it directly
    if "error_type" in claim:
        return claim

    # Collect all referenced resources for the bundle
    referenced_resources = [patient, practitioner, insurer]
    if coverage is not None:
        referenced_resources.append(coverage)
    referenced_resources.extend(supporting_info)

    bundle = _claim_bundle_builder.build_pas_bundle(
        claim=claim,
        referenced_resources=referenced_resources,
        questionnaire_response=questionnaire_response,
    )

    validation_issues = _claim_bundle_builder.validate_bundle(bundle)
    issues_list = [
        {"severity": issue.severity, "code": issue.code, "diagnostics": issue.diagnostics}
        for issue in validation_issues
    ]

    return {"claim": claim, "bundle": bundle, "validation_issues": issues_list}


@tool
def generate_claim_response(
    claim_reference: str,
    patient_reference: str,
    insurer_reference: str,
    decision: str,
    disposition: str,
    pre_auth_ref: str | None = None,
    error_code: str | None = None,
    review_action: str | None = None,
) -> dict:
    """Generate a FHIR ClaimResponse resource from an authorization decision.

    Call this tool after making the authorization decision (Step 6) to produce a
    standards-compliant Da Vinci PAS ClaimResponse.

    Args:
        claim_reference: Reference to the original Claim (e.g. "Claim/<id>").
        patient_reference: Reference to the Patient (e.g. "Patient/<id>").
        insurer_reference: Reference to the insurer Organization (e.g. "Organization/<id>").
        decision: One of "approved", "denied", "pended".
        disposition: Human-readable rationale for the decision.
        pre_auth_ref: Authorization reference number (for approved decisions; auto-generated if omitted).
        error_code: X12 claim adjustment reason code (for denied decisions).
        review_action: Review action code (for pended decisions).

    Returns:
        FHIR ClaimResponse resource dict.
    """
    return _claim_response_generator.generate(
        claim_reference=claim_reference,
        patient_reference=patient_reference,
        insurer_reference=insurer_reference,
        decision=decision,
        disposition=disposition,
        pre_auth_ref=pre_auth_ref,
        error_code=error_code,
        review_action=review_action,
    )


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

    Looks up the versioned prompt ARN from SSM, then retrieves
    the prompt text from Bedrock Prompt Management.
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

    Provides access to HealthLake tools (patient data, conditions, medications,
    observations, allergies) exposed through the Gateway.
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


# Default system prompt (used when Bedrock Prompt Management is not configured)
DEFAULT_SYSTEM_PROMPT = """You are a Prior Authorization Agent specializing in healthcare prior authorization workflows.

Your role is to help healthcare providers submit and manage prior authorization requests efficiently.
You can be triggered automatically via CDS Hooks when a provider places an order in the EHR, or
invoked directly through the chat interface.

## Capabilities

### HealthLake Tools (Patient Clinical Data via Gateway)
- **get_patient_conditions**: Retrieve patient diagnoses and conditions (ICD-10 codes)
- **get_patient_medications**: Get current and historical medications
- **get_patient_observations**: Access lab results, vitals, and other clinical observations
- **get_patient_allergies**: Check patient allergy and intolerance records
- **get_patient_appointments**: View scheduled and past appointments
- **get_patient_everything**: Comprehensive patient data retrieval
- **advanced_patient_search**: Search patients by demographics, conditions, etc.

### Payor Policy Tools (Prior Auth Rules via Gateway)
- **search_payor_policies**: Search uploaded payor policy documents for coverage criteria, medical necessity requirements, and documentation requirements
- **lookup_prior_auth_requirements**: Look up whether a specific CPT/HCPCS procedure code requires prior authorization for a given payor
- **list_policy_documents**: List available payor policy documents
- **upload_policy_document**: Upload new payor policy documents for indexing

### CDS Hooks Tools (EHR Integration via Gateway)
- **get_cds_services**: List available CDS Hook services
- **handle_patient_view**: Process patient-view hook from EHR
- **handle_order_select**: Process order-select hook — determines if prior auth is required

### FHIR Resource Generation Tools (Da Vinci PAS Alignment)
- **build_pas_claim_bundle**: Build a FHIR PAS Bundle containing a Claim (use=preauthorization) and all referenced supporting resources. Call after clinical data assembly.
- **generate_claim_response**: Generate a FHIR ClaimResponse from the authorization decision. Call after making the approval/denial/pend decision.

## Prior Authorization Workflow

When processing a prior authorization request, follow these steps:

### Step 1: Order Detection & Initiation
- Identify the requested procedure/service and its CPT/HCPCS code
- Identify the patient and retrieve their record from HealthLake
- Determine the patient's insurance payor from coverage data

### Step 2: Eligibility & Prior Auth Requirement Check
- Use **lookup_prior_auth_requirements** to check if the procedure requires prior auth
- Use **search_payor_policies** to find the payor's specific requirements for this procedure
- If prior auth is NOT required, inform the provider and stop

### Step 3: Clinical Documentation Assembly
- Retrieve the patient's relevant conditions, medications, and observations from HealthLake
- Identify the primary diagnosis (ICD-10) supporting the requested procedure
- Collect supporting clinical documentation (lab results, imaging, prior treatments)
- Check if conservative treatments have been attempted (as required by payor policy)
- Gather all documentation items required by the payor's policy

### Step 4: Medical Necessity Assessment
- Evaluate whether the clinical evidence meets the payor's medical necessity criteria
- Cross-reference the patient's clinical data against the payor's coverage criteria
- Verify the diagnosis supports the requested procedure
- Flag any gaps in documentation or clinical evidence

### Step 5: Authorization Request Assembly
- Compile all required clinical documentation per payor requirements
- Generate a clinical summary with medical necessity justification
- Include relevant diagnosis codes (ICD-10), procedure codes (CPT/HCPCS)
- Attach supporting lab results, imaging reports, and clinical notes
- Format the request according to payor submission requirements
- **Call build_pas_claim_bundle** with the patient, practitioner, coverage, insurer, service items (CPT/HCPCS codes with diagnosis links), supporting FHIR resources (Conditions, Observations, MedicationRequests), and priority level to produce the FHIR PAS Bundle
- If the bundle has validation issues, report them to the provider

### Step 6: Recommendation & Next Steps
- Summarize the authorization request
- Indicate likelihood of approval based on clinical evidence vs payor criteria
- Flag any missing documentation or potential issues
- **Call generate_claim_response** with the Claim reference, patient reference, insurer reference, decision ("approved", "denied", or "pended"), and a human-readable disposition summarizing the rationale
- Include the generated FHIR ClaimResponse in your response
- Provide the complete prior auth submission package (PAS Bundle + ClaimResponse)
- Suggest next steps (submit electronically, fax, peer-to-peer review)

## Important Guidelines
- Always retrieve actual patient data from HealthLake before making recommendations
- Always check payor-specific policies using the policy tools before assembling the request
- Be thorough in gathering clinical evidence to support medical necessity
- Follow HIPAA guidelines — do not expose PHI unnecessarily
- If clinical data is insufficient, clearly state what additional information is needed
- Provide structured, actionable responses with clear next steps

## Response Format

You MUST structure your response with these exact section headers:

### Eligibility & Coverage
Summarize the patient's insurance status and coverage details.

### Clinical Evidence
List the relevant clinical data gathered (conditions, medications, labs, imaging).

### Payor Policy Requirements
What the payor requires for this procedure and whether the patient meets the criteria.

### Medical Necessity Assessment
Your assessment of whether the clinical evidence supports medical necessity.

### Authorization Decision
State ONE of these clearly:
- "Authorization is recommended" — if clinical evidence meets payor criteria
- "Authorization is denied" — if clinical evidence does not meet criteria
- "Additional documentation required" — if more info is needed before a decision

Include the specific reason for your decision.

### Next Steps
Concrete actions the provider should take.

### FHIR Resources Generated
Include the PAS Bundle summary (resource count, Claim ID) and ClaimResponse details (outcome, preAuthRef if approved, error if denied).
Present the full JSON of the ClaimResponse for the provider to review.
"""


def create_prior_auth_agent(user_id: str, session_id: str) -> Agent:
    """
    Create a prior authorization agent with Gateway MCP tools and memory.

    Sets up an agent that can access HealthLake patient data through the
    AgentCore Gateway and maintains conversation state via AgentCore Memory.
    """
    # Try to load system prompt from Bedrock Prompt Management
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

    # Threat T6 — Bedrock Guardrails defense-in-depth.
    # The guardrail policy must include: PROMPT_ATTACK filter at HIGH on input,
    # healthcare denied-topics, and a PII output filter for the 18 HIPAA
    # identifiers. Configure once in the AWS console / CDK and pass the IDs.
    guardrail_id = os.environ.get("BEDROCK_GUARDRAIL_ID")
    guardrail_version = os.environ.get("BEDROCK_GUARDRAIL_VERSION", "DRAFT")

    bedrock_kwargs = dict(
        model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        temperature=0.1,  # Low temperature for clinical accuracy
    )
    if guardrail_id:
        bedrock_kwargs["guardrail_id"] = guardrail_id
        bedrock_kwargs["guardrail_version"] = guardrail_version
        bedrock_kwargs["guardrail_trace"] = "enabled"
        print(
            f"[AGENT] Bedrock Guardrails enabled (id={guardrail_id}, version={guardrail_version})"
        )
    else:
        print(
            "[AGENT] WARNING: BEDROCK_GUARDRAIL_ID not set — running without "
            "Guardrails. Threat T6 mitigation requires Guardrails "
            "in production."
        )

    bedrock_model = BedrockModel(**bedrock_kwargs)

    memory_id = os.environ.get("MEMORY_ID")
    if not memory_id:
        raise ValueError("MEMORY_ID environment variable is required")

    # Configure AgentCore Memory
    agentcore_memory_config = AgentCoreMemoryConfig(
        memory_id=memory_id, session_id=session_id, actor_id=user_id
    )

    session_manager = AgentCoreMemorySessionManager(
        agentcore_memory_config=agentcore_memory_config,
        region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
    )

    try:
        print("[AGENT] Starting prior authorization agent creation...")

        # Get OAuth2 access token and create Gateway MCP client
        print("[AGENT] Step 1: Getting OAuth2 access token...")
        access_token = get_gateway_access_token()
        print(f"[AGENT] Got access token (length={len(access_token)})")  # T11: do not log token prefix

        print("[AGENT] Step 2: Creating Gateway MCP client...")
        gateway_client = create_gateway_mcp_client(access_token)
        print("[AGENT] Gateway MCP client created successfully")

        print("[AGENT] Step 3: Creating Agent with Gateway tools...")
        agent = Agent(
            name="PriorAuthorizationAgent",
            system_prompt=system_prompt,
            tools=[gateway_client, build_pas_claim_bundle, generate_claim_response],
            model=bedrock_model,
            session_manager=session_manager,
            trace_attributes={
                "user.id": user_id,
                "session.id": session_id,
                "agent.type": "prior-authorization",
            },
        )
        print("[AGENT] Prior authorization agent created successfully")
        return agent

    except Exception as e:
        print(f"[AGENT ERROR] Error creating agent: {e}")
        print(f"[AGENT ERROR] Exception type: {type(e).__name__}")
        traceback.print_exc()
        raise


# Threat T6 — defense-in-depth input sanitation. Implementation in
# the standalone ``prompt_sanitizer`` module so it can be unit tested without
# loading the rest of the agent.
from prompt_sanitizer import sanitize_user_prompt as _sanitize_user_prompt


@app.entrypoint
async def agent_stream(payload):
    """
    Main entrypoint for the prior authorization agent with streaming.

    Expected payload:
    {
        "prompt": "Submit prior auth for patient P001 for MRI lumbar spine",
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
            f"[STREAM] Starting prior auth agent for user: {user_id}, session: {session_id}"
        )
        # Mitigates Threat T11 — do not log the verbatim user query
        # (may contain PHI in supplemental notes).
        print(f"[STREAM] Query length: {len(user_query)} chars")

        # T6 — sanitize and fence user input before passing to the model.
        sanitized_query = _sanitize_user_prompt(user_query)

        agent = create_prior_auth_agent(user_id, session_id)

        async for event in agent.stream_async(sanitized_query):
            yield event

    except Exception as e:
        print(f"[STREAM ERROR] Error in agent_stream: {e}")
        traceback.print_exc()
        yield {"status": "error", "error": str(e)}


if __name__ == "__main__":
    app.run()
