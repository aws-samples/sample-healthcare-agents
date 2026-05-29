# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Lambda handler for DTR (Documentation Templates and Rules) Questionnaire operations.

Provides tools for fetching payer-specific FHIR Questionnaires, evaluating
auto-fill expressions against HealthLake patient data, and looking up DTR
configuration for payer/procedure combinations.

Follows the Da Vinci DTR Implementation Guide for Questionnaire retrieval
and expression evaluation.
"""

import json
import logging
import os
from pathlib import Path
from urllib.parse import urlparse

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.httpsession import URLLib3Session
import urllib.parse
import requests

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment configuration
aws_region = os.getenv("HEALTHLAKE_REGION", "us-east-1")
HEALTHLAKE_DATASTORE_ID = os.getenv("HEALTHLAKE_DATASTORE_ID")
HEALTHLAKE_ENDPOINT = f"https://healthlake.{aws_region}.amazonaws.com"

# Path to payer questionnaire config
DTR_CONFIG_PATH = os.getenv(
    "DTR_CONFIG_PATH",
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "dtr-config", "payer-questionnaires.json"),
)

# AWS session and credentials for HealthLake access
session = boto3.Session()
credentials = session.get_credentials()
http_session = URLLib3Session()


# ---------------------------------------------------------------------------
# HealthLake helper (mirrors healthlake_lambda.py pattern)
# ---------------------------------------------------------------------------

def _fhir_search(resource_type, params):
    """Execute FHIR search query against HealthLake with SigV4 authentication."""
    if not HEALTHLAKE_DATASTORE_ID:
        raise Exception("HEALTHLAKE_DATASTORE_ID environment variable not set")

    query_string = urllib.parse.urlencode(params)
    url = f"{HEALTHLAKE_ENDPOINT}/datastore/{HEALTHLAKE_DATASTORE_ID}/r4/{resource_type}?{query_string}"

    request = AWSRequest(method="GET", url=url)
    SigV4Auth(credentials, "healthlake", aws_region).add_auth(request)

    response = http_session.send(request.prepare())
    if response.status_code != 200:
        raise Exception(f"HealthLake API error: {response.status_code} - {response.text}")

    return json.loads(response.content)


def _fhir_read(resource_type, resource_id):
    """Read a single FHIR resource from HealthLake by type and ID."""
    if not HEALTHLAKE_DATASTORE_ID:
        raise Exception("HEALTHLAKE_DATASTORE_ID environment variable not set")

    url = f"{HEALTHLAKE_ENDPOINT}/datastore/{HEALTHLAKE_DATASTORE_ID}/r4/{resource_type}/{resource_id}"

    request = AWSRequest(method="GET", url=url)
    SigV4Auth(credentials, "healthlake", aws_region).add_auth(request)

    response = http_session.send(request.prepare())
    if response.status_code != 200:
        raise Exception(f"HealthLake API error: {response.status_code} - {response.text}")

    return json.loads(response.content)


# ---------------------------------------------------------------------------
# DTR Config loader
# ---------------------------------------------------------------------------

_dtr_config_cache = None


def _load_dtr_config():
    """Load and cache the payer DTR questionnaire configuration."""
    global _dtr_config_cache
    if _dtr_config_cache is not None:
        return _dtr_config_cache

    config_path = Path(DTR_CONFIG_PATH).resolve()
    if not config_path.exists():
        logger.warning("DTR config file not found at %s", config_path)
        _dtr_config_cache = {"payers": []}
        return _dtr_config_cache

    with open(config_path, "r", encoding="utf-8") as f:
        _dtr_config_cache = json.load(f)

    return _dtr_config_cache


# ---------------------------------------------------------------------------
# Tool: fetch_dtr_questionnaire
# ---------------------------------------------------------------------------

def fetch_dtr_questionnaire(questionnaire_url):
    """
    Fetch a FHIR Questionnaire resource from a payer endpoint via HTTP GET.

    Args:
        questionnaire_url: The full URL of the FHIR Questionnaire resource
            on the payer's server.

    Returns:
        dict: The FHIR Questionnaire resource, or an error dict on failure.
    """
    if not questionnaire_url:
        return {"error": "questionnaire_url is required"}

    # Validate URL format
    parsed = urlparse(questionnaire_url)
    if not parsed.scheme or not parsed.netloc:
        return {"error": f"Invalid questionnaire URL: {questionnaire_url}"}

    logger.info("Fetching DTR Questionnaire from %s", questionnaire_url)

    try:
        response = requests.get(
            questionnaire_url,
            headers={
                "Accept": "application/fhir+json",
                "Content-Type": "application/fhir+json",
            },
            timeout=30,
        )
        response.raise_for_status()
        questionnaire = response.json()

        # Basic validation: ensure it's a Questionnaire resource
        if questionnaire.get("resourceType") != "Questionnaire":
            return {
                "error": f"Expected Questionnaire resource, got {questionnaire.get('resourceType', 'unknown')}",
                "resource": questionnaire,
            }

        logger.info(
            "Successfully fetched Questionnaire: %s (%d items)",
            questionnaire.get("url", questionnaire.get("id", "unknown")),
            len(questionnaire.get("item", [])),
        )

        return questionnaire

    except requests.exceptions.Timeout:
        logger.error("Timeout fetching Questionnaire from %s", questionnaire_url)
        return {"error": f"Timeout fetching Questionnaire from {questionnaire_url}"}
    except requests.exceptions.ConnectionError as e:
        logger.error("Connection error fetching Questionnaire: %s", str(e))
        return {"error": f"Connection error: {str(e)}"}
    except requests.exceptions.HTTPError as e:
        logger.error("HTTP error fetching Questionnaire: %s", str(e))
        return {"error": f"HTTP error: {e.response.status_code} - {e.response.text}"}
    except json.JSONDecodeError:
        logger.error("Invalid JSON response from %s", questionnaire_url)
        return {"error": "Invalid JSON response from payer endpoint"}


# ---------------------------------------------------------------------------
# Tool: evaluate_questionnaire_expressions
# ---------------------------------------------------------------------------

# Mapping from simplified FHIRPath resource references to HealthLake
# resource types and search parameters.
_EXPRESSION_RESOURCE_MAP = {
    "Patient": {"resource_type": "Patient", "search_by_patient": False},
    "Condition": {"resource_type": "Condition", "search_by_patient": True},
    "Observation": {"resource_type": "Observation", "search_by_patient": True},
    "MedicationRequest": {"resource_type": "MedicationRequest", "search_by_patient": True},
    "Coverage": {"resource_type": "Coverage", "search_by_patient": True},
    "AllergyIntolerance": {"resource_type": "AllergyIntolerance", "search_by_patient": True},
    "Procedure": {"resource_type": "Procedure", "search_by_patient": True},
}


def _extract_expression_from_item(item):
    """
    Extract initialExpression or calculatedExpression from a Questionnaire item.

    Returns (expression_type, expression_language, expression_value) or None.
    """
    for ext in item.get("extension", []):
        ext_url = ext.get("url", "")
        if "initialExpression" in ext_url or "calculatedExpression" in ext_url:
            value_expr = ext.get("valueExpression", {})
            expr_type = "initialExpression" if "initialExpression" in ext_url else "calculatedExpression"
            return (
                expr_type,
                value_expr.get("language", "text/fhirpath"),
                value_expr.get("expression", ""),
            )
    return None


def _resolve_expression(expression, patient_id):
    """
    Resolve a simplified FHIRPath-like expression against HealthLake patient data.

    Supports expressions like:
      - "Patient.name.given.first()"
      - "Patient.birthDate"
      - "Condition.where(code.coding.code='M54.5').code.text"
      - "Observation.where(category='laboratory').valueQuantity.value"
      - "%resource.name.given.first()"

    Returns (resolved_value, source_resource_id) or (None, None).
    """
    if not expression:
        return None, None

    # Normalize %resource references to Patient
    expr = expression.replace("%resource", "Patient")

    # Determine the root resource type
    root_type = None
    for rtype in _EXPRESSION_RESOURCE_MAP:
        if expr.startswith(rtype):
            root_type = rtype
            break

    if not root_type:
        logger.warning("Unsupported expression root: %s", expression)
        return None, None

    config = _EXPRESSION_RESOURCE_MAP[root_type]

    try:
        # Fetch the resource(s) from HealthLake
        if config["search_by_patient"]:
            bundle = _fhir_search(config["resource_type"], {"patient": patient_id, "_count": "10"})
            entries = bundle.get("entry", [])
            if not entries:
                return None, None
            resource = entries[0].get("resource", {})
        else:
            # Direct read (e.g., Patient)
            resource = _fhir_read(config["resource_type"], patient_id)

        source_id = resource.get("id", "")

        # Navigate the resource using the remaining path segments
        remaining_path = expr[len(root_type):]
        if remaining_path.startswith("."):
            remaining_path = remaining_path[1:]

        value = _navigate_fhir_path(resource, remaining_path)

        return value, f"{root_type}/{source_id}" if source_id else None

    except Exception as e:
        logger.error("Error resolving expression '%s': %s", expression, str(e))
        return None, None


def _navigate_fhir_path(resource, path):
    """
    Navigate a simplified FHIRPath through a FHIR resource dict.

    Handles:
      - Simple property access: "name.given"
      - first() function: "name.given.first()"
      - where() filter: "where(code='xyz')" (simplified)
      - Array traversal: automatically picks first element of arrays
    """
    if not path:
        return resource

    current = resource
    segments = _split_path_segments(path)

    for segment in segments:
        if current is None:
            return None

        # Handle first() function
        if segment == "first()":
            if isinstance(current, list) and len(current) > 0:
                current = current[0]
            continue

        # Handle where() filter (simplified)
        if segment.startswith("where(") and segment.endswith(")"):
            # Skip where filters — just use the first available resource
            continue

        # Navigate into the property
        if isinstance(current, list):
            # Auto-pick first element for array traversal
            if len(current) > 0:
                current = current[0]
            else:
                return None

        if isinstance(current, dict):
            current = current.get(segment)
        else:
            return None

    return current


def _split_path_segments(path):
    """Split a FHIRPath into segments, respecting parentheses."""
    segments = []
    current = ""
    paren_depth = 0

    for char in path:
        if char == "(":
            paren_depth += 1
            current += char
        elif char == ")":
            paren_depth -= 1
            current += char
        elif char == "." and paren_depth == 0:
            if current:
                segments.append(current)
            current = ""
        else:
            current += char

    if current:
        segments.append(current)

    return segments


def evaluate_questionnaire_expressions(questionnaire, patient_id):
    """
    Evaluate initialExpression and calculatedExpression extensions in a
    FHIR Questionnaire against HealthLake patient data.

    For each Questionnaire item that has an initialExpression or
    calculatedExpression extension, queries HealthLake for the relevant
    patient data and resolves the expression value.

    Args:
        questionnaire: A FHIR Questionnaire resource dict.
        patient_id: The FHIR Patient ID to evaluate expressions against.

    Returns:
        list[dict]: A list of AutoFillResult dicts, each containing:
            - linkId: The Questionnaire item linkId
            - sourceResourceId: The FHIR resource ID that provided the value
            - resolvedValue: The resolved value from the expression
            - expressionType: "initialExpression" or "calculatedExpression"
    """
    if not questionnaire or not patient_id:
        return []

    items = questionnaire.get("item", [])
    results = []

    def _process_items(item_list):
        for item in item_list:
            link_id = item.get("linkId")
            if not link_id:
                continue

            expr_info = _extract_expression_from_item(item)
            if expr_info:
                expr_type, _language, expression = expr_info
                resolved_value, source_resource_id = _resolve_expression(expression, patient_id)

                auto_fill_result = {
                    "linkId": link_id,
                    "sourceResourceId": source_resource_id,
                    "resolvedValue": resolved_value,
                    "expressionType": expr_type,
                }

                results.append(auto_fill_result)

                # Audit log per Requirement 6.4
                logger.info(
                    "Auto-fill: linkId=%s, sourceResourceId=%s, resolvedValue=%s",
                    link_id,
                    source_resource_id,
                    resolved_value,
                )

            # Recurse into nested items
            nested = item.get("item", [])
            if nested:
                _process_items(nested)

    _process_items(items)
    return results


# ---------------------------------------------------------------------------
# Tool: get_payer_dtr_config
# ---------------------------------------------------------------------------

def get_payer_dtr_config(payer_name, procedure_code):
    """
    Look up DTR Questionnaire configuration for a given payer and procedure code.

    Searches the payer-questionnaires.json config file for a matching payer
    (by name or alias) and procedure code.

    Args:
        payer_name: The payer/insurer name (e.g., "Blue Cross Blue Shield", "BCBS").
        procedure_code: The CPT/HCPCS procedure code (e.g., "72148").

    Returns:
        dict or None: The matching DTR config entry with questionnaire_url,
            questionnaire_id, procedure_display, payer_name, or None if no
            match is found.
    """
    if not payer_name or not procedure_code:
        return None

    config = _load_dtr_config()
    payer_name_lower = payer_name.strip().lower()

    for payer in config.get("payers", []):
        # Match by payer name or aliases
        names_to_check = [payer["payer_name"].lower()] + [
            alias.lower() for alias in payer.get("aliases", [])
        ]

        if payer_name_lower not in names_to_check:
            continue

        # Search for matching procedure code
        for q_config in payer.get("questionnaires", []):
            if q_config.get("procedure_code") == procedure_code:
                return {
                    "payer_name": payer["payer_name"],
                    "procedure_code": q_config["procedure_code"],
                    "procedure_display": q_config.get("procedure_display", ""),
                    "questionnaire_url": q_config["questionnaire_url"],
                    "questionnaire_id": q_config.get("questionnaire_id", ""),
                }

    logger.info(
        "No DTR config found for payer=%s, procedure=%s", payer_name, procedure_code
    )
    return None


# ---------------------------------------------------------------------------
# Lambda handler — MCP tool routing (matches healthlake_lambda.py pattern)
# ---------------------------------------------------------------------------

def handler(event, context):
    """Main Lambda handler for DTR Questionnaire MCP tools."""
    try:
        # PHI-safe event logging (mitigates Threat T11).
        logger.info(
            "event_summary=%s",
            json.dumps({
                "top_level_keys": sorted(event.keys()) if isinstance(event, dict) else [],
                "size_bytes": len(json.dumps(event, default=str)) if event else 0,
                "invocation": "mcp",
                "action_name": (event.get("action_name") or event.get("actionName")) if isinstance(event, dict) else None,
            }, default=str),
        )

        # Get tool name from context (Gateway passes it for multi-tool Lambdas)
        tool_name = None
        if context and hasattr(context, "client_context") and context.client_context:
            custom = getattr(context.client_context, "custom", None)
            if custom and isinstance(custom, dict):
                tool_name = custom.get("bedrockAgentCoreToolName")

        # Fallback to action_name in event for direct Lambda invocations
        if not tool_name:
            tool_name = event.get("action_name")

        # Strip target prefix if present (format: "target-name___tool-name")
        if tool_name and "___" in tool_name:
            tool_name = tool_name.split("___")[-1]

        if not tool_name:
            print("Warning: No tool name in context or event, cannot determine tool")
            return {
                "content": [{"type": "text", "text": "Error: Tool name not provided"}],
                "isError": True,
            }

        print(f"Tool name: {tool_name}")

        # Route to appropriate tool handler
        if tool_name == "fetch_questionnaire" or tool_name == "fetch_dtr_questionnaire":
            result = fetch_dtr_questionnaire(event.get("questionnaire_url", ""))

        elif tool_name == "eval_expressions" or tool_name == "evaluate_questionnaire_expressions":
            questionnaire = event.get("questionnaire")
            patient_id = event.get("patient_id")
            if not questionnaire or not patient_id:
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": "Error: questionnaire and patient_id are required",
                        }
                    ],
                    "isError": True,
                }
            result = evaluate_questionnaire_expressions(questionnaire, patient_id)

        elif tool_name == "get_dtr_config" or tool_name == "get_payer_dtr_config":
            payer_name = event.get("payer_name", "")
            procedure_code = event.get("procedure_code", "")
            result = get_payer_dtr_config(payer_name, procedure_code)
            if result is None:
                result = {
                    "message": f"No DTR questionnaire configured for payer '{payer_name}' and procedure '{procedure_code}'"
                }

        else:
            return {
                "content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}],
                "isError": True,
            }

        return {"content": [{"type": "text", "text": json.dumps(result)}]}

    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            "content": [{"type": "text", "text": f"Error: {str(e)}"}],
            "isError": True,
        }
