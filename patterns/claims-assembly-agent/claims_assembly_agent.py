# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Claims Assembly Agent using Strands SDK.

Validates claim data and assembles EDI 837P claim structures with
deterministic schema validation and payer-specific rules from
Bedrock Knowledge Base.
"""

import json
import os
import traceback

import boto3
from typing import Dict, Any, List
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig
from bedrock_agentcore.memory.integrations.strands.session_manager import (
    AgentCoreMemorySessionManager,
)
from strands import Agent, tool
from strands.models import BedrockModel

from edi_837p_builder import (
    Address,
    BillingProvider,
    ClaimData,
    DiagnosisCode,
    Payer,
    RenderingProvider,
    ServiceLine,
    Subscriber,
    validate_and_assemble,
)

app = BedrockAgentCoreApp()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_system_prompt(ssm_path: str) -> str:
    """Fetch system prompt text from Bedrock Prompt Management."""
    region = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
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


def get_ssm_parameter(parameter_name: str) -> str:
    """Fetch parameter from SSM Parameter Store."""
    region = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
    ssm = boto3.client("ssm", region_name=region)
    try:
        response = ssm.get_parameter(Name=parameter_name)
        return response["Parameter"]["Value"]
    except ssm.exceptions.ParameterNotFound:
        raise ValueError(f"SSM parameter not found: {parameter_name}")
    except Exception as e:
        raise ValueError(f"Failed to retrieve SSM parameter {parameter_name}: {e}")


def query_validation_kb(query: str, kb_id: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Query Bedrock Knowledge Base for validation rules."""
    region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
    bedrock_agent_runtime = boto3.client("bedrock-agent-runtime", region_name=region)

    try:
        response = bedrock_agent_runtime.retrieve(
            knowledgeBaseId=kb_id,
            retrievalQuery={"text": query},
            retrievalConfiguration={
                "vectorSearchConfiguration": {"numberOfResults": max_results}
            },
        )

        results = []
        for result in response.get("retrievalResults", []):
            results.append(
                {
                    "content": result.get("content", {}).get("text", ""),
                    "score": result.get("score", 0.0),
                    "metadata": result.get("metadata", {}),
                }
            )
        return results

    except Exception as e:
        print(f"[KB ERROR] Error querying knowledge base: {e}")
        traceback.print_exc()
        return []


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


def create_validation_kb_tool(kb_id: str):
    """Create a Strands tool for querying validation rules knowledge base."""

    def query_validation_rules(query: str, rule_type: str = "all") -> str:
        """
        Search for payer-specific validation rules, HIPAA compliance rules,
        and EDI schema requirements in the knowledge base.

        Use this tool to look up payer-specific requirements BEFORE assembling
        a claim. For example, check if a payer requires a referral number or
        specific modifiers.

        Args:
            query: Description of what to validate (e.g., "Medicare modifier requirements", "UHC timely filing")
            rule_type: Type of rules to search — payer, compliance, schema, or all

        Returns:
            JSON string with relevant validation rules
        """
        enhanced_query = f"{query} {rule_type}" if rule_type != "all" else query

        print(f"[KB TOOL] Searching validation rules for: {enhanced_query}")
        results = query_validation_kb(enhanced_query, kb_id, max_results=5)

        if not results:
            return json.dumps(
                {"message": "No relevant validation rules found", "query": query, "rule_type": rule_type}
            )

        formatted_results = {
            "query": query,
            "rule_type": rule_type,
            "validation_rules": [
                {"rule": r["content"], "relevance_score": r["score"], "metadata": r["metadata"]}
                for r in results
            ],
        }
        return json.dumps(formatted_results, indent=2)

    return query_validation_rules


@tool
def validate_and_assemble_claim(claim_json: str) -> str:
    """Validate claim data and assemble an EDI 837P JSON structure.

    Performs deterministic validation of all required fields against HIPAA 5010
    requirements including NPI format, ICD-10-CM codes, CPT/HCPCS codes, date
    formats, charge consistency, and cross-field rules. Only assembles the
    EDI 837P if all validations pass.

    The claim_json must contain these top-level keys:
    - claim_id: Unique claim identifier
    - billing_provider: {name, npi, tax_id, taxonomy_code, address?, contact_phone?}
    - subscriber: {first_name, last_name, member_id, date_of_birth (CCYYMMDD), gender (M/F/U), group_number?, address?, relationship_code?}
    - payer: {name, payer_id, address?}
    - diagnosis_codes: [{code, description?}, ...]  (ICD-10-CM, 1-12 codes)
    - service_lines: [{procedure_code, charge_amount, units, date_of_service (CCYYMMDD), place_of_service?, modifiers?, diagnosis_pointers?, description?}, ...]
    - total_charge?: Total charge (validated against sum of line charges)
    - prior_auth_number?: Prior authorization number
    - referral_number?: Referral number
    - rendering_provider?: {first_name, last_name, npi, taxonomy_code?}
    - facility_npi?: Service facility NPI
    - facility_name?: Service facility name

    Address format: {street, city, state (2-letter), zip_code}

    Args:
        claim_json: JSON string with claim data following the schema above

    Returns:
        JSON with 'valid' (bool), 'issues' (list), and 'edi_837p' (if valid)
    """
    try:
        data = json.loads(claim_json)
    except json.JSONDecodeError as e:
        return json.dumps({"valid": False, "issues": [{"severity": "error", "field": "claim_json", "message": f"Invalid JSON: {e}"}], "edi_837p": None})

    try:
        claim = _parse_claim_data(data)
    except (KeyError, TypeError, ValueError) as e:
        return json.dumps({"valid": False, "issues": [{"severity": "error", "field": "claim_data", "message": f"Failed to parse claim data: {e}"}], "edi_837p": None})

    result = validate_and_assemble(claim)
    return json.dumps(result, indent=2)


def _parse_claim_data(data: dict) -> ClaimData:
    """Parse raw dict into ClaimData dataclass."""
    bp = data.get("billing_provider", {})
    sub = data.get("subscriber", {})
    pay = data.get("payer", {})
    rp_data = data.get("rendering_provider")

    return ClaimData(
        claim_id=data.get("claim_id", ""),
        billing_provider=BillingProvider(
            name=bp.get("name", ""),
            npi=bp.get("npi", ""),
            tax_id=bp.get("tax_id", ""),
            taxonomy_code=bp.get("taxonomy_code", ""),
            address=_parse_address(bp.get("address")),
            contact_phone=bp.get("contact_phone", ""),
        ),
        subscriber=Subscriber(
            first_name=sub.get("first_name", ""),
            last_name=sub.get("last_name", ""),
            member_id=sub.get("member_id", ""),
            date_of_birth=sub.get("date_of_birth", ""),
            gender=sub.get("gender", ""),
            group_number=sub.get("group_number", ""),
            address=_parse_address(sub.get("address")),
            relationship_code=sub.get("relationship_code", "18"),
        ),
        payer=Payer(
            name=pay.get("name", ""),
            payer_id=pay.get("payer_id", ""),
            address=_parse_address(pay.get("address")),
        ),
        diagnosis_codes=[
            DiagnosisCode(code=dx.get("code", ""), description=dx.get("description", ""))
            for dx in data.get("diagnosis_codes", [])
        ],
        service_lines=[
            ServiceLine(
                procedure_code=sl.get("procedure_code", ""),
                charge_amount=float(sl.get("charge_amount", 0)),
                units=float(sl.get("units", 0)),
                date_of_service=sl.get("date_of_service", ""),
                place_of_service=sl.get("place_of_service", "11"),
                modifiers=sl.get("modifiers", []),
                diagnosis_pointers=sl.get("diagnosis_pointers", []),
                description=sl.get("description", ""),
            )
            for sl in data.get("service_lines", [])
        ],
        total_charge=float(data.get("total_charge", 0)),
        prior_auth_number=data.get("prior_auth_number", ""),
        referral_number=data.get("referral_number", ""),
        rendering_provider=RenderingProvider(
            first_name=rp_data.get("first_name", ""),
            last_name=rp_data.get("last_name", ""),
            npi=rp_data.get("npi", ""),
            taxonomy_code=rp_data.get("taxonomy_code", ""),
        ) if rp_data else None,
        facility_npi=data.get("facility_npi", ""),
        facility_name=data.get("facility_name", ""),
    )


def _parse_address(addr_data: dict | None) -> Address | None:
    if not addr_data:
        return None
    return Address(
        street=addr_data.get("street", ""),
        city=addr_data.get("city", ""),
        state=addr_data.get("state", ""),
        zip_code=addr_data.get("zip_code", ""),
    )


# ---------------------------------------------------------------------------
# Agent setup
# ---------------------------------------------------------------------------


def create_claims_assembly_agent(user_id: str, session_id: str) -> Agent:
    """Create claims assembly agent with validation KB and EDI builder tools."""
    prompt_ssm_path = os.environ.get("SYSTEM_PROMPT_SSM_PATH")
    if not prompt_ssm_path:
        raise ValueError("SYSTEM_PROMPT_SSM_PATH environment variable is required")
    print("[AGENT] Fetching system prompt from Bedrock Prompt Management...")
    system_prompt = get_system_prompt(prompt_ssm_path)

    bedrock_model = BedrockModel(
        model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        temperature=0.1,
    )

    memory_id = os.environ.get("MEMORY_ID")
    validation_kb_id = os.environ.get("VALIDATION_KB_ID")

    if not memory_id:
        raise ValueError("MEMORY_ID environment variable is required")
    if not validation_kb_id:
        raise ValueError("VALIDATION_KB_ID environment variable is required")

    agentcore_memory_config = AgentCoreMemoryConfig(
        memory_id=memory_id,
        session_id=session_id,
        actor_id=user_id,
    )

    session_manager = AgentCoreMemorySessionManager(
        agentcore_memory_config=agentcore_memory_config,
        region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
    )

    try:
        print("[AGENT] Creating claims assembly agent...")

        validation_tool = create_validation_kb_tool(validation_kb_id)

        agent = Agent(
            name="ClaimsAssemblyAgent",
            system_prompt=system_prompt,
            tools=[validation_tool, validate_and_assemble_claim],
            model=bedrock_model,
            session_manager=session_manager,
            trace_attributes={
                "user.id": user_id,
                "session.id": session_id,
            },
        )

        print("[AGENT] Claims assembly agent created successfully")
        return agent

    except Exception as e:
        print(f"[AGENT ERROR] Error creating agent: {e}")
        traceback.print_exc()
        raise


@app.entrypoint
async def agent_stream(payload):
    """Main entrypoint for the claims assembly agent with streaming."""
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
        print(f"[STREAM] Starting claims assembly agent for user: {user_id}, session: {session_id}")
        print(f"[STREAM] Query: {user_query}")

        agent = create_claims_assembly_agent(user_id, session_id)

        async for event in agent.stream_async(user_query):
            yield event

    except Exception as e:
        print(f"[STREAM ERROR] Error in agent_stream: {e}")
        traceback.print_exc()
        yield {"status": "error", "error": str(e)}


if __name__ == "__main__":
    app.run()
