# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Direct Epic FHIR API calls with AgentCore Identity OAuth

This module provides functions to call Epic FHIR API directly with user authorization
via AgentCore Identity's USER_FEDERATION OAuth flow (3LO).
"""

import httpx
import asyncio
from typing import Dict, Any, Optional
from bedrock_agentcore.identity import requires_access_token

# Epic FHIR base URL
EPIC_FHIR_BASE_URL = "https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4"

# AgentCore OAuth2 callback URL (provider-specific)
# This is the callback URL that AgentCore Identity uses for OAuth session binding
# Generated when the EpicFHIRProvider OAuth2 credential provider was created
AGENTCORE_OAUTH_CALLBACK_URL = "https://bedrock-agentcore.us-east-1.amazonaws.com/identities/oauth2/callback/2749ca33-fda3-45e1-8bb3-78f463e99645"

# Application callback URL for frontend (will be set from environment)
OAUTH_CALLBACK_URL = None  # Set by agent at runtime

# Global queue for authorization URLs (will be set by agent)
AUTH_URL_QUEUE = None


def get_callback_url():
    """Get callback URL at runtime (for decorator evaluation)"""
    return OAUTH_CALLBACK_URL


async def stream_auth_url(url: str):
    """
    Callback to stream authorization URL to the agent.
    The agent will yield this to the frontend for user to authorize.
    """
    print(f"[EPIC-AUTH] Authorization URL: {url}")

    # Format message as elicitation for frontend compatibility
    elicitation_message = {
        "type": "elicitation",
        "elicitation": {
            "authorizationUrl": url,
            "url": url,  # Include both for compatibility
            "resourceType": "Epic FHIR",
            "scopes": ["user/Patient.read", "user/MedicationRequest.read", "user/AllergyIntolerance.read", "user/Observation.read"]
        }
    }

    # If queue is available, put the message in it
    if AUTH_URL_QUEUE is not None:
        try:
            await AUTH_URL_QUEUE.put(elicitation_message)
            print(f"[EPIC-AUTH] Authorization URL queued for frontend")
        except Exception as e:
            print(f"[EPIC-AUTH] Failed to queue URL: {e}")

    return elicitation_message


@requires_access_token(
    provider_name="EpicFHIRProvider",
    scopes=[
        "user/Patient.read",
        "user/MedicationRequest.read",
        "user/AllergyIntolerance.read",
        "user/Observation.read"
    ],
    auth_flow="USER_FEDERATION",
    on_auth_url=stream_auth_url,
    force_authentication=False,
    callback_url=AGENTCORE_OAUTH_CALLBACK_URL
)
async def get_patient(patient_id: str, *, access_token: str) -> Dict[str, Any]:
    """
    Get patient demographics from Epic FHIR with user authorization.

    Args:
        patient_id: Epic FHIR patient ID
        access_token: OAuth access token (injected by decorator)

    Returns:
        Patient resource with demographics
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{EPIC_FHIR_BASE_URL}/Patient/{patient_id}",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/fhir+json"
                },
                timeout=30.0
            )
            response.raise_for_status()

            patient_data = response.json()

            # Extract key information
            return {
                "status": "success",
                "data": {
                    "id": patient_data.get("id"),
                    "name": _extract_name(patient_data),
                    "gender": patient_data.get("gender"),
                    "birthDate": patient_data.get("birthDate"),
                    "raw": patient_data
                }
            }
        except httpx.HTTPError as e:
            return {
                "status": "error",
                "error": f"HTTP error: {str(e)}"
            }
        except Exception as e:
            return {
                "status": "error",
                "error": f"Error retrieving patient: {str(e)}"
            }


@requires_access_token(
    provider_name="EpicFHIRProvider",
    scopes=["user/MedicationRequest.read"],
    auth_flow="USER_FEDERATION",
    on_auth_url=stream_auth_url,
    force_authentication=False,
    callback_url=AGENTCORE_OAUTH_CALLBACK_URL
)
async def get_medications(patient_id: str, *, access_token: str) -> Dict[str, Any]:
    """
    Get active medications for a patient from Epic FHIR.

    Args:
        patient_id: Epic FHIR patient ID
        access_token: OAuth access token (injected by decorator)

    Returns:
        List of active MedicationRequest resources
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{EPIC_FHIR_BASE_URL}/MedicationRequest",
                params={
                    "patient": patient_id,
                    "status": "active"
                },
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/fhir+json"
                },
                timeout=30.0
            )
            response.raise_for_status()

            bundle = response.json()
            medications = []

            for entry in bundle.get("entry", []):
                resource = entry.get("resource", {})
                medications.append({
                    "id": resource.get("id"),
                    "status": resource.get("status"),
                    "medication": _extract_medication_name(resource),
                    "dosage": _extract_dosage(resource),
                    "authoredOn": resource.get("authoredOn")
                })

            return {
                "status": "success",
                "total": len(medications),
                "data": medications
            }
        except httpx.HTTPError as e:
            return {
                "status": "error",
                "error": f"HTTP error: {str(e)}"
            }
        except Exception as e:
            return {
                "status": "error",
                "error": f"Error retrieving medications: {str(e)}"
            }


@requires_access_token(
    provider_name="EpicFHIRProvider",
    scopes=["user/AllergyIntolerance.read"],
    auth_flow="USER_FEDERATION",
    on_auth_url=stream_auth_url,
    force_authentication=False,
    callback_url=AGENTCORE_OAUTH_CALLBACK_URL
)
async def get_allergies(patient_id: str, *, access_token: str) -> Dict[str, Any]:
    """
    Get patient allergies from Epic FHIR.

    Args:
        patient_id: Epic FHIR patient ID
        access_token: OAuth access token (injected by decorator)

    Returns:
        List of AllergyIntolerance resources
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{EPIC_FHIR_BASE_URL}/AllergyIntolerance",
                params={"patient": patient_id},
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/fhir+json"
                },
                timeout=30.0
            )
            response.raise_for_status()

            bundle = response.json()
            allergies = []

            for entry in bundle.get("entry", []):
                resource = entry.get("resource", {})
                allergies.append({
                    "id": resource.get("id"),
                    "clinicalStatus": _extract_clinical_status(resource),
                    "type": resource.get("type"),
                    "substance": _extract_substance_name(resource),
                    "reaction": _extract_reaction(resource),
                    "recordedDate": resource.get("recordedDate")
                })

            return {
                "status": "success",
                "total": len(allergies),
                "data": allergies
            }
        except httpx.HTTPError as e:
            return {
                "status": "error",
                "error": f"HTTP error: {str(e)}"
            }
        except Exception as e:
            return {
                "status": "error",
                "error": f"Error retrieving allergies: {str(e)}"
            }


@requires_access_token(
    provider_name="EpicFHIRProvider",
    scopes=["user/Observation.read"],
    auth_flow="USER_FEDERATION",
    on_auth_url=stream_auth_url,
    force_authentication=False,
    callback_url=AGENTCORE_OAUTH_CALLBACK_URL
)
async def get_observations(
    patient_id: str,
    category: Optional[str] = None,
    *,
    access_token: str
) -> Dict[str, Any]:
    """
    Get patient observations (vitals, labs) from Epic FHIR.

    Args:
        patient_id: Epic FHIR patient ID
        category: Optional category filter (e.g., 'vital-signs', 'laboratory')
        access_token: OAuth access token (injected by decorator)

    Returns:
        List of Observation resources
    """
    async with httpx.AsyncClient() as client:
        try:
            params = {
                "patient": patient_id,
                "_sort": "-date",
                "_count": "20"
            }
            if category:
                params["category"] = category

            response = await client.get(
                f"{EPIC_FHIR_BASE_URL}/Observation",
                params=params,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/fhir+json"
                },
                timeout=30.0
            )
            response.raise_for_status()

            bundle = response.json()
            observations = []

            for entry in bundle.get("entry", []):
                resource = entry.get("resource", {})
                observations.append({
                    "id": resource.get("id"),
                    "status": resource.get("status"),
                    "category": _extract_category(resource),
                    "code": _extract_code(resource),
                    "value": _extract_value(resource),
                    "effectiveDateTime": resource.get("effectiveDateTime")
                })

            return {
                "status": "success",
                "total": len(observations),
                "data": observations
            }
        except httpx.HTTPError as e:
            return {
                "status": "error",
                "error": f"HTTP error: {str(e)}"
            }
        except Exception as e:
            return {
                "status": "error",
                "error": f"Error retrieving observations: {str(e)}"
            }


# Helper functions for data extraction
def _extract_name(patient_data: Dict) -> str:
    """Extract formatted name from FHIR Patient resource"""
    names = patient_data.get("name", [])
    if not names:
        return "Unknown"
    name = names[0]
    given = " ".join(name.get("given", []))
    family = name.get("family", "")
    return f"{given} {family}".strip()


def _extract_medication_name(resource: Dict) -> str:
    """Extract medication name from MedicationRequest"""
    med = resource.get("medicationCodeableConcept", {})
    codings = med.get("coding", [])
    if codings:
        return codings[0].get("display", "Unknown")
    return med.get("text", "Unknown")


def _extract_dosage(resource: Dict) -> str:
    """Extract dosage instructions"""
    dosage_instructions = resource.get("dosageInstruction", [])
    if dosage_instructions:
        return dosage_instructions[0].get("text", "See prescription")
    return "Not specified"


def _extract_clinical_status(resource: Dict) -> str:
    """Extract clinical status from AllergyIntolerance"""
    status = resource.get("clinicalStatus", {})
    codings = status.get("coding", [])
    if codings:
        return codings[0].get("code", "unknown")
    return "unknown"


def _extract_substance_name(resource: Dict) -> str:
    """Extract allergen substance name"""
    code = resource.get("code", {})
    codings = code.get("coding", [])
    if codings:
        return codings[0].get("display", "Unknown")
    return code.get("text", "Unknown")


def _extract_reaction(resource: Dict) -> list:
    """Extract reaction manifestations"""
    reactions = []
    for reaction in resource.get("reaction", []):
        for manifestation in reaction.get("manifestation", []):
            codings = manifestation.get("coding", [])
            if codings:
                reactions.append(codings[0].get("display", "Unknown"))
    return reactions


def _extract_category(resource: Dict) -> str:
    """Extract observation category"""
    categories = resource.get("category", [])
    if categories:
        codings = categories[0].get("coding", [])
        if codings:
            return codings[0].get("code", "Unknown")
    return "Unknown"


def _extract_code(resource: Dict) -> Dict[str, str]:
    """Extract observation code and display"""
    code = resource.get("code", {})
    codings = code.get("coding", [])
    if codings:
        return {
            "code": codings[0].get("code", ""),
            "display": codings[0].get("display", ""),
            "system": codings[0].get("system", "")
        }
    return {"code": "", "display": code.get("text", "Unknown"), "system": ""}


def _extract_value(resource: Dict) -> Dict[str, Any]:
    """Extract observation value"""
    if "valueQuantity" in resource:
        value = resource["valueQuantity"]
        return {
            "type": "Quantity",
            "value": value.get("value"),
            "unit": value.get("unit"),
            "display": f"{value.get('value')} {value.get('unit', '')}"
        }
    elif "valueString" in resource:
        return {
            "type": "String",
            "value": resource["valueString"],
            "display": resource["valueString"]
        }
    elif "valueCodeableConcept" in resource:
        code = resource["valueCodeableConcept"]
        codings = code.get("coding", [])
        if codings:
            return {
                "type": "CodeableConcept",
                "value": codings[0].get("code"),
                "display": codings[0].get("display", code.get("text", "Unknown"))
            }
    return {"type": "Unknown", "value": None, "display": "Not available"}
