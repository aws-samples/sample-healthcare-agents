# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Appeals KB Lambda — denial codes, appeal regulations, and clinical guidelines."""

import json
import logging
import os
import traceback

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

aws_region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
APPEALS_KB_ID = os.getenv("APPEALS_KB_ID")
STACK_NAME = os.getenv("STACK_NAME")


def _get_kb_id():
    """Get KB ID from env or SSM (SSM wins if env is placeholder)."""
    kb_id = APPEALS_KB_ID
    if not kb_id or kb_id == "placeholder":
        ssm = boto3.client("ssm", region_name=aws_region)
        kb_id = ssm.get_parameter(Name=f"/{STACK_NAME}/appeals-kb-id")["Parameter"]["Value"]
    return kb_id


def _retrieve(query, max_results=5):
    kb_id = _get_kb_id()
    if not kb_id:
        return {"error": "APPEALS_KB_ID not configured"}
    client = boto3.client("bedrock-agent-runtime", region_name=aws_region)
    response = client.retrieve(
        knowledgeBaseId=kb_id,
        retrievalQuery={"text": query},
        retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": max_results}},
    )
    return [
        {"content": r.get("content", {}).get("text", ""), "score": r.get("score", 0)}
        for r in response.get("retrievalResults", [])
    ]


def search_denial_codes(query, max_results=5):
    results = _retrieve(f"denial code CARC RARC {query}", max_results)
    return json.dumps({"query": query, "results": results}, indent=2)


def search_appeal_regulations(query, payer_name=None, max_results=5):
    enhanced = f"{payer_name} {query}" if payer_name else query
    results = _retrieve(f"appeal regulation filing deadline {enhanced}", max_results)
    return json.dumps({"query": query, "payer_filter": payer_name, "results": results}, indent=2)


def search_clinical_guidelines(query, procedure_type=None, max_results=5):
    enhanced = f"{procedure_type} {query}" if procedure_type else query
    results = _retrieve(f"medical necessity clinical guideline {enhanced}", max_results)
    return json.dumps({"query": query, "procedure_type": procedure_type, "results": results}, indent=2)


def handler(event, context):
    try:
        tool_name = None
        if context and hasattr(context, "client_context") and context.client_context:
            custom = getattr(context.client_context, "custom", None)
            if custom and isinstance(custom, dict):
                tool_name = custom.get("bedrockAgentCoreToolName")
        if not tool_name:
            tool_name = event.get("action_name") or event.get("actionName", "")
        if tool_name and "___" in tool_name:
            tool_name = tool_name.split("___")[-1]

        if tool_name == "search_denial_codes":
            result = search_denial_codes(event.get("query", ""), event.get("max_results", 5))
        elif tool_name == "search_appeal_regulations":
            result = search_appeal_regulations(event.get("query", ""), event.get("payer_name"), event.get("max_results", 5))
        elif tool_name == "search_clinical_guidelines":
            result = search_clinical_guidelines(event.get("query", ""), event.get("procedure_type"), event.get("max_results", 5))
        else:
            return {"content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}], "isError": True}

        return {"content": [{"type": "text", "text": result}]}
    except Exception as e:
        traceback.print_exc()
        return {"content": [{"type": "text", "text": f"Error: {e}"}], "isError": True}
