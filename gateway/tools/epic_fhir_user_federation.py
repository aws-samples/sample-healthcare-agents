# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Epic FHIR Gateway Tools - User Federation (3-Legged OAuth)

Provides MCP tools for querying Epic FHIR API with user-authorized access tokens.
Uses AgentCore Identity for USER_FEDERATION OAuth 2.0 flow.

This approach requires user consent and provides access to only the patients
the user is authorized to see (user-scoped access).
"""

from typing import Dict, Any, Optional, List
import requests
from bedrock_agentcore.identity import requires_access_token


class EpicFHIRUserFederationClient:
    """Client for Epic FHIR API with user federation authentication"""

    def __init__(self, fhir_base_url: str):
        self.fhir_base_url = fhir_base_url

    def _make_fhir_request(
        self,
        endpoint: str,
        access_token: str,
        params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Make authenticated request to Epic FHIR API"""
        url = f"{self.fhir_base_url}/{endpoint}"

        headers = {
            'Authorization': f'Bearer {access_token}',
            'Accept': 'application/fhir+json',
            'Content-Type': 'application/fhir+json'
        }

        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        return response.json()

    def get_patient(self, patient_id: str, access_token: str) -> Dict[str, Any]:
        """
        Retrieve patient demographics and identifiers

        Args:
            patient_id: FHIR Patient resource ID
            access_token: User-authorized OAuth token

        Returns:
            FHIR Patient resource
        """
        return self._make_fhir_request(f"Patient/{patient_id}", access_token)

    def get_medications(self, patient_id: str, access_token: str) -> Dict[str, Any]:
        """
        Retrieve active medication orders for a patient

        Args:
            patient_id: FHIR Patient resource ID
            access_token: User-authorized OAuth token

        Returns:
            FHIR Bundle containing MedicationRequest resources
        """
        params = {
            'patient': patient_id,
            'status': 'active'
        }
        return self._make_fhir_request('MedicationRequest', access_token, params)

    def get_allergies(self, patient_id: str, access_token: str) -> Dict[str, Any]:
        """
        Retrieve allergy and intolerance information for a patient

        Args:
            patient_id: FHIR Patient resource ID
            access_token: User-authorized OAuth token

        Returns:
            FHIR Bundle containing AllergyIntolerance resources
        """
        params = {'patient': patient_id}
        return self._make_fhir_request('AllergyIntolerance', access_token, params)

    def get_observations(
        self,
        patient_id: str,
        access_token: str,
        category: str = 'vital-signs'
    ) -> Dict[str, Any]:
        """
        Retrieve observations (vitals, labs) for a patient

        Args:
            patient_id: FHIR Patient resource ID
            access_token: User-authorized OAuth token
            category: Observation category (vital-signs, laboratory, etc.)

        Returns:
            FHIR Bundle containing Observation resources
        """
        params = {
            'patient': patient_id,
            'category': category,
            '_sort': '-date'
        }
        return self._make_fhir_request('Observation', access_token, params)


# Initialize client (base URL would come from environment or config)
FHIR_BASE_URL = "https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4"
client = EpicFHIRUserFederationClient(FHIR_BASE_URL)


# AgentCore Identity decorator for USER_FEDERATION flow
# This handles the 3-legged OAuth process automatically
@requires_access_token(
    provider_name="EpicFHIRProvider",  # Must be created in AgentCore Identity
    scopes=["user/Patient.read", "user/MedicationRequest.read",
            "user/AllergyIntolerance.read", "user/Observation.read"],
    auth_flow="USER_FEDERATION",  # 3-legged OAuth
    force_authentication=False  # Reuse cached tokens when available
)
def get_patient_with_user_auth(patient_id: str, *, access_token: str) -> Dict[str, Any]:
    """
    Get patient demographics with user authorization

    The access_token is automatically injected by AgentCore Identity
    after user completes the OAuth flow.

    Args:
        patient_id: FHIR Patient resource ID
        access_token: User-authorized OAuth token (injected by decorator)

    Returns:
        dict: Patient demographics and identifiers
    """
    try:
        patient = client.get_patient(patient_id, access_token)

        # Extract key fields
        result = {
            'id': patient.get('id'),
            'name': _extract_name(patient),
            'birthDate': patient.get('birthDate'),
            'gender': patient.get('gender'),
            'identifiers': _extract_identifiers(patient),
            'telecom': _extract_telecom(patient)
        }

        return {
            'status': 'success',
            'data': result
        }
    except Exception as e:
        return {
            'status': 'error',
            'message': str(e)
        }


@requires_access_token(
    provider_name="EpicFHIRProvider",
    scopes=["user/MedicationRequest.read"],
    auth_flow="USER_FEDERATION"
)
def get_medications_with_user_auth(patient_id: str, *, access_token: str) -> Dict[str, Any]:
    """
    Get active medications with user authorization

    Args:
        patient_id: FHIR Patient resource ID
        access_token: User-authorized OAuth token (injected by decorator)

    Returns:
        dict: List of active medications
    """
    try:
        bundle = client.get_medications(patient_id, access_token)

        medications = []
        if 'entry' in bundle:
            for entry in bundle['entry']:
                med_request = entry.get('resource', {})
                medications.append({
                    'id': med_request.get('id'),
                    'status': med_request.get('status'),
                    'medication': _extract_medication(med_request),
                    'dosage': _extract_dosage(med_request),
                    'authoredOn': med_request.get('authoredOn')
                })

        return {
            'status': 'success',
            'data': {
                'count': len(medications),
                'medications': medications
            }
        }
    except Exception as e:
        return {
            'status': 'error',
            'message': str(e)
        }


@requires_access_token(
    provider_name="EpicFHIRProvider",
    scopes=["user/AllergyIntolerance.read"],
    auth_flow="USER_FEDERATION"
)
def get_allergies_with_user_auth(patient_id: str, *, access_token: str) -> Dict[str, Any]:
    """
    Get allergies and intolerances with user authorization

    Args:
        patient_id: FHIR Patient resource ID
        access_token: User-authorized OAuth token (injected by decorator)

    Returns:
        dict: List of allergies and intolerances
    """
    try:
        bundle = client.get_allergies(patient_id, access_token)

        allergies = []
        if 'entry' in bundle:
            for entry in bundle['entry']:
                allergy = entry.get('resource', {})
                allergies.append({
                    'id': allergy.get('id'),
                    'clinicalStatus': _extract_codeable_concept(
                        allergy.get('clinicalStatus', {})
                    ),
                    'verificationStatus': _extract_codeable_concept(
                        allergy.get('verificationStatus', {})
                    ),
                    'type': allergy.get('type'),
                    'category': allergy.get('category', []),
                    'criticality': allergy.get('criticality'),
                    'code': _extract_codeable_concept(allergy.get('code', {})),
                    'reaction': _extract_reactions(allergy)
                })

        return {
            'status': 'success',
            'data': {
                'count': len(allergies),
                'allergies': allergies
            }
        }
    except Exception as e:
        return {
            'status': 'error',
            'message': str(e)
        }


@requires_access_token(
    provider_name="EpicFHIRProvider",
    scopes=["user/Observation.read"],
    auth_flow="USER_FEDERATION"
)
def get_observations_with_user_auth(
    patient_id: str,
    category: str = 'vital-signs',
    *,
    access_token: str
) -> Dict[str, Any]:
    """
    Get observations (vitals, labs) with user authorization

    Args:
        patient_id: FHIR Patient resource ID
        category: Observation category (vital-signs, laboratory, etc.)
        access_token: User-authorized OAuth token (injected by decorator)

    Returns:
        dict: List of observations
    """
    try:
        bundle = client.get_observations(patient_id, access_token, category)

        observations = []
        if 'entry' in bundle:
            for entry in bundle['entry']:
                obs = entry.get('resource', {})
                observations.append({
                    'id': obs.get('id'),
                    'status': obs.get('status'),
                    'category': [_extract_codeable_concept(cat)
                                for cat in obs.get('category', [])],
                    'code': _extract_codeable_concept(obs.get('code', {})),
                    'effectiveDateTime': obs.get('effectiveDateTime'),
                    'value': _extract_value(obs),
                    'interpretation': [_extract_codeable_concept(interp)
                                     for interp in obs.get('interpretation', [])]
                })

        return {
            'status': 'success',
            'data': {
                'count': len(observations),
                'category': category,
                'observations': observations
            }
        }
    except Exception as e:
        return {
            'status': 'error',
            'message': str(e)
        }


# Helper functions for extracting FHIR data
def _extract_name(patient: Dict) -> str:
    """Extract patient name from FHIR Patient resource"""
    if 'name' not in patient or not patient['name']:
        return 'Unknown'

    name = patient['name'][0]
    given = ' '.join(name.get('given', []))
    family = name.get('family', '')
    return f"{given} {family}".strip()


def _extract_identifiers(patient: Dict) -> List[Dict]:
    """Extract identifiers from FHIR Patient resource"""
    if 'identifier' not in patient:
        return []

    return [
        {
            'system': id.get('system'),
            'value': id.get('value'),
            'type': _extract_codeable_concept(id.get('type', {}))
        }
        for id in patient['identifier']
    ]


def _extract_telecom(patient: Dict) -> List[Dict]:
    """Extract contact information from FHIR Patient resource"""
    if 'telecom' not in patient:
        return []

    return [
        {
            'system': tc.get('system'),
            'value': tc.get('value'),
            'use': tc.get('use')
        }
        for tc in patient['telecom']
    ]


def _extract_medication(med_request: Dict) -> str:
    """Extract medication name from MedicationRequest"""
    if 'medicationCodeableConcept' in med_request:
        return _extract_codeable_concept(med_request['medicationCodeableConcept'])
    elif 'medicationReference' in med_request:
        return med_request['medicationReference'].get('display', 'Unknown medication')
    return 'Unknown medication'


def _extract_dosage(med_request: Dict) -> List[str]:
    """Extract dosage instructions from MedicationRequest"""
    if 'dosageInstruction' not in med_request:
        return []

    return [
        dosage.get('text', '')
        for dosage in med_request['dosageInstruction']
        if 'text' in dosage
    ]


def _extract_codeable_concept(codeable: Dict) -> str:
    """Extract text from CodeableConcept"""
    if 'text' in codeable:
        return codeable['text']
    if 'coding' in codeable and codeable['coding']:
        return codeable['coding'][0].get('display', '')
    return ''


def _extract_reactions(allergy: Dict) -> List[Dict]:
    """Extract reaction information from AllergyIntolerance"""
    if 'reaction' not in allergy:
        return []

    return [
        {
            'substance': _extract_codeable_concept(r.get('substance', {})),
            'manifestation': [_extract_codeable_concept(m)
                            for m in r.get('manifestation', [])],
            'severity': r.get('severity')
        }
        for r in allergy['reaction']
    ]


def _extract_value(observation: Dict) -> Dict:
    """Extract value from Observation resource"""
    if 'valueQuantity' in observation:
        val = observation['valueQuantity']
        return {
            'value': val.get('value'),
            'unit': val.get('unit'),
            'system': val.get('system')
        }
    elif 'valueString' in observation:
        return {'value': observation['valueString']}
    elif 'valueCodeableConcept' in observation:
        return {'value': _extract_codeable_concept(observation['valueCodeableConcept'])}
    return {}
