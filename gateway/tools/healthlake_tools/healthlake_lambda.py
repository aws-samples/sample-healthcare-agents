# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Lambda handler for HealthLake EHR operations
"""

import json
import logging
import os
import urllib.parse

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.httpsession import URLLib3Session

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment configuration
aws_region = os.getenv("HEALTHLAKE_REGION", "us-east-1")
HEALTHLAKE_DATASTORE_ID = os.getenv("HEALTHLAKE_DATASTORE_ID")
HEALTHLAKE_ENDPOINT = f"https://healthlake.{aws_region}.amazonaws.com"

# AWS session and credentials
session = boto3.Session()
credentials = session.get_credentials()
http_session = URLLib3Session()


def fhir_search(resource_type, params):
    """Execute FHIR search query with SigV4 authentication"""
    if not HEALTHLAKE_DATASTORE_ID:
        raise Exception("HEALTHLAKE_DATASTORE_ID environment variable not set")

    query_string = urllib.parse.urlencode(params)
    url = f"{HEALTHLAKE_ENDPOINT}/datastore/{HEALTHLAKE_DATASTORE_ID}/r4/{resource_type}?{query_string}"

    request = AWSRequest(method="GET", url=url)
    SigV4Auth(credentials, "healthlake", aws_region).add_auth(request)

    response = http_session.send(request.prepare())

    if response.status_code != 200:
        raise Exception(
            f"HealthLake API error: {response.status_code} - {response.text}"
        )

    return json.loads(response.content)


def get_patient_conditions(patient_id):
    """Get patient's conditions (diagnoses, chronic diseases)"""
    result = fhir_search("Condition", {"patient": patient_id, "_sort": "-onset-date"})

    conditions = []
    for entry in result.get("entry", []):
        resource = entry.get("resource", {})
        conditions.append(
            {
                "id": resource.get("id"),
                "code": resource.get("code", {}).get("text"),
                "clinical_status": resource.get("clinicalStatus", {})
                .get("coding", [{}])[0]
                .get("code"),
                "onset_date": resource.get("onsetDateTime"),
                "severity": resource.get("severity", {}).get("text"),
            }
        )

    return conditions


def get_patient_medications(patient_id):
    """Get patient's current medications"""
    result = fhir_search(
        "MedicationRequest", {"patient": patient_id, "status": "active"}
    )

    medications = []
    for entry in result.get("entry", []):
        resource = entry.get("resource", {})
        medications.append(
            {
                "id": resource.get("id"),
                "medication": resource.get("medicationCodeableConcept", {}).get("text"),
                "dosage": resource.get("dosageInstruction", [{}])[0].get("text"),
                "status": resource.get("status"),
                "authored_on": resource.get("authoredOn"),
            }
        )

    return medications


def get_patient_observations(patient_id, category=None):
    """Get patient's observations (labs, vitals)"""
    params = {"patient": patient_id, "_sort": "-date", "_count": "20"}
    if category:
        params["category"] = category

    result = fhir_search("Observation", params)

    observations = []
    for entry in result.get("entry", []):
        resource = entry.get("resource", {})
        observations.append(
            {
                "id": resource.get("id"),
                "code": resource.get("code", {}).get("text"),
                "value": resource.get("valueQuantity", {}).get("value"),
                "unit": resource.get("valueQuantity", {}).get("unit"),
                "date": resource.get("effectiveDateTime"),
                "status": resource.get("status"),
            }
        )

    return observations


def get_patient_allergies(patient_id):
    """Get patient's allergies and intolerances"""
    result = fhir_search("AllergyIntolerance", {"patient": patient_id})

    allergies = []
    for entry in result.get("entry", []):
        resource = entry.get("resource", {})
        allergies.append(
            {
                "id": resource.get("id"),
                "substance": resource.get("code", {}).get("text"),
                "criticality": resource.get("criticality"),
                "type": resource.get("type"),
                "recorded_date": resource.get("recordedDate"),
            }
        )

    return allergies


def get_patient_appointments(patient_id):
    """Get patient's appointments"""
    result = fhir_search("Appointment", {"patient": patient_id, "_sort": "-date"})

    appointments = []
    for entry in result.get("entry", []):
        resource = entry.get("resource", {})
        appointments.append(
            {
                "id": resource.get("id"),
                "status": resource.get("status"),
                "start": resource.get("start"),
                "end": resource.get("end"),
                "description": resource.get("description"),
            }
        )

    return appointments


def _format_patient_name(name_field):
    """Build a human-readable patient name from a FHIR HumanName array.

    Falls back to given+family when the `text` field is absent (common for
    Synthea-generated data). Strips trailing digits Synthea appends to names.
    """
    import re as _re

    if not name_field:
        return None
    entry = name_field[0] if isinstance(name_field, list) else name_field
    if not isinstance(entry, dict):
        return None

    raw = entry.get("text")
    if not raw:
        given = " ".join(entry.get("given", []) or [])
        family = entry.get("family", "") or ""
        raw = f"{given} {family}".strip()

    if not raw:
        return None

    # Synthea appends digits to names (e.g. "Dexter530 Little434").
    cleaned = _re.sub(r"\d+", "", raw)
    cleaned = _re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or None


def advanced_patient_search(search_params, include_params=None, revinclude_params=None):
    """Advanced patient search with modifiers and includes"""
    params = search_params.copy()

    # Handle age category parameter
    age_category = params.pop("age_category", None)
    if age_category:
        from datetime import datetime, timedelta

        today = datetime.now()

        age_ranges = {
            "pediatric": (0, 12),
            "adolescent": (13, 17),
            "adult": (18, 64),
            "geriatric": (65, 120),
        }

        if age_category.lower() in age_ranges:
            min_age, max_age = age_ranges[age_category.lower()]

            if age_category.lower() == "geriatric":
                # For geriatric (65+): birthdate <= (today - 65 years)
                max_birthdate = (today - timedelta(days=min_age * 365)).strftime(
                    "%Y-%m-%d"
                )
                params["birthdate"] = f"le{max_birthdate}"
            else:
                # For other categories: min_age <= age <= max_age
                max_birthdate = (today - timedelta(days=min_age * 365)).strftime(
                    "%Y-%m-%d"
                )
                min_birthdate = (today - timedelta(days=max_age * 365)).strftime(
                    "%Y-%m-%d"
                )
                params["birthdate"] = f"ge{min_birthdate},le{max_birthdate}"

    # Handle location parameters (state, city, zipcode)
    location_params = []
    for loc_param in ["state", "city", "zipcode"]:
        if loc_param in params:
            location_params.append(params.pop(loc_param))

    if location_params:
        # Combine location parameters for FHIR address search
        params["address"] = ",".join(location_params)

    if include_params:
        params["_include"] = include_params
    if revinclude_params:
        params["_revinclude"] = revinclude_params

    result = fhir_search("Patient", params)

    patients = []
    for entry in result.get("entry", []):
        resource = entry.get("resource", {})
        if resource.get("resourceType") == "Patient":
            patients.append(
                {
                    "id": resource.get("id"),
                    "name": _format_patient_name(resource.get("name")),
                    "birthDate": resource.get("birthDate"),
                    "gender": resource.get("gender"),
                    "active": resource.get("active"),
                }
            )

    return {
        "patients": patients,
        "total": result.get("total", 0),
        "included_resources": [
            entry.get("resource")
            for entry in result.get("entry", [])
            if entry.get("resource", {}).get("resourceType") != "Patient"
        ],
    }


def get_patient_everything(patient_id, start_date=None, end_date=None):
    """Get all resources for a patient using $everything operation"""
    if not HEALTHLAKE_DATASTORE_ID:
        raise Exception("HEALTHLAKE_DATASTORE_ID environment variable not set")

    params = {}
    if start_date:
        params["start"] = start_date
    if end_date:
        params["end"] = end_date

    # Use FHIR $everything operation
    query_string = urllib.parse.urlencode(params)
    url = f"{HEALTHLAKE_ENDPOINT}/datastore/{HEALTHLAKE_DATASTORE_ID}/r4/Patient/{patient_id}/$everything"
    if query_string:
        url += f"?{query_string}"

    request = AWSRequest(method="GET", url=url)
    SigV4Auth(credentials, "healthlake", aws_region).add_auth(request)

    response = http_session.send(request.prepare())

    if response.status_code != 200:
        raise Exception(
            f"HealthLake API error: {response.status_code} - {response.text}"
        )

    result = json.loads(response.content)

    # Organize resources by type
    resources_by_type = {}
    for entry in result.get("entry", []):
        resource = entry.get("resource", {})
        resource_type = resource.get("resourceType")
        if resource_type not in resources_by_type:
            resources_by_type[resource_type] = []
        resources_by_type[resource_type].append(resource)

    return {
        "patient_id": patient_id,
        "total_resources": result.get("total", 0),
        "resources_by_type": resources_by_type,
        "date_range": {"start": start_date, "end": end_date}
        if start_date or end_date
        else None,
    }


def create_fhir_resource(resource_type, resource_data):
    """Create a new FHIR resource in HealthLake (CREATE-ONLY).

    Backed by the AWS Labs HealthLake MCP server's HealthLakeClient
    (awslabs.healthlake_mcp_server.fhir_operations), invoked behind the
    AgentCore Gateway. Used to persist a prior-authorization decision — e.g. a
    FHIR ClaimResponse or Task — onto the patient's record. Update/Delete are
    intentionally not exposed.
    """
    if not HEALTHLAKE_DATASTORE_ID:
        raise Exception("HEALTHLAKE_DATASTORE_ID environment variable not set")
    if not isinstance(resource_data, dict) or not resource_data:
        raise Exception("resource_data must be a non-empty FHIR resource object")

    import asyncio

    from awslabs.healthlake_mcp_server.fhir_operations import HealthLakeClient

    client = HealthLakeClient(region_name=aws_region)
    created = asyncio.run(
        client.create_resource(HEALTHLAKE_DATASTORE_ID, resource_type, resource_data)
    )
    return {
        "created": True,
        "resourceType": created.get("resourceType", resource_type),
        "id": created.get("id"),
        "meta": created.get("meta"),
    }


def handler(event, context):
    """Main Lambda handler for HealthLake MCP tools"""

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

        # Get tool name from context (Gateway passes it here for multi-tool Lambdas)
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

        # If no tool name found, cannot determine tool
        if not tool_name:
            print("Warning: No tool name in context or event, cannot determine tool")
            return {
                "content": [{"type": "text", "text": "Error: Tool name not provided"}],
                "isError": True,
            }

        print(f"Tool name: {tool_name}")

        # Route to appropriate tool handler
        if tool_name == "get_patient_conditions":
            result = get_patient_conditions(event["patient_id"])
        elif tool_name == "get_patient_medications":
            result = get_patient_medications(event["patient_id"])
        elif tool_name == "get_patient_observations":
            result = get_patient_observations(
                event["patient_id"], event.get("category")
            )
        elif tool_name == "get_patient_allergies":
            result = get_patient_allergies(event["patient_id"])
        elif tool_name == "get_patient_appointments":
            result = get_patient_appointments(event["patient_id"])
        elif tool_name == "advanced_patient_search":
            search_params = event.get("search_params", {})
            include_params = event.get("include_params")
            revinclude_params = event.get("revinclude_params")
            result = advanced_patient_search(
                search_params, include_params, revinclude_params
            )
        elif tool_name == "get_patient_everything":
            start_date = event.get("start_date")
            end_date = event.get("end_date")
            result = get_patient_everything(event["patient_id"], start_date, end_date)
        elif tool_name == "create_fhir_resource":
            result = create_fhir_resource(
                event["resource_type"], event.get("resource_data", {})
            )
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
