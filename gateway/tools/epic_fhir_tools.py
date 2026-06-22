# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Epic FHIR Gateway Tools

Provides MCP tools for querying Epic FHIR API via AgentCore Gateway.
Supports backend service authentication with JWT.
"""

import os
import time
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

import jwt  # PyJWT
import boto3  # AWS SDK
import requests  # HTTP client


class EpicFHIRClient:
    """Client for Epic FHIR API with backend service authentication"""

    def __init__(self):
        self.client_id = os.environ.get('EPIC_CLIENT_ID')
        self.jwks_kid = os.environ.get('EPIC_JWKS_KID')
        self.private_key_secret_name = os.environ.get('EPIC_PRIVATE_KEY_SECRET')
        self.fhir_base_url = os.environ.get('EPIC_FHIR_BASE_URL',
                                            'https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4')
        self.token_url = os.environ.get('EPIC_TOKEN_URL',
                                       'https://fhir.epic.com/interconnect-fhir-oauth/oauth2/token')
        self.audience = os.environ.get('EPIC_AUDIENCE',
                                      'https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4')

        self._access_token = None
        self._token_expires_at = None
        self._private_key = None

    def _get_private_key(self) -> str:
        """Retrieve private key from Secrets Manager"""
        if self._private_key:
            return self._private_key

        if not self.private_key_secret_name:
            raise ValueError("EPIC_PRIVATE_KEY_SECRET environment variable not set")

        secrets_client = boto3.client('secretsmanager')
        response = secrets_client.get_secret_value(SecretId=self.private_key_secret_name)
        self._private_key = response['SecretString']
        return self._private_key

    def _create_jwt_assertion(self) -> str:
        """Create JWT assertion for client authentication"""
        if not self.jwks_kid:
            raise ValueError("EPIC_JWKS_KID environment variable not set")

        now = int(time.time())

        headers = {
            'kid': self.jwks_kid,
            'alg': 'RS256',
            'typ': 'JWT'
        }

        payload = {
            'iss': self.client_id,  # Issuer (your client ID)
            'sub': self.client_id,  # Subject (your client ID)
            'aud': self.token_url,  # Audience (token endpoint)
            'jti': f"{self.client_id}-{now}",  # Unique token ID
            'exp': now + 300,  # Expires in 5 minutes
            'iat': now  # Issued at
        }

        private_key = self._get_private_key()
        return jwt.encode(payload, private_key, algorithm='RS256', headers=headers)

    def _get_access_token(self) -> str:
        """Get or refresh access token"""
        # Return cached token if still valid
        if self._access_token and self._token_expires_at:
            if datetime.now() < self._token_expires_at - timedelta(minutes=5):
                return self._access_token

        # Request new token
        jwt_assertion = self._create_jwt_assertion()

        data = {
            'grant_type': 'client_credentials',
            'client_assertion_type': 'urn:ietf:params:oauth:client-assertion-type:jwt-bearer',
            'client_assertion': jwt_assertion,
            'scope': 'system/Patient.read system/MedicationRequest.read system/AllergyIntolerance.read system/Observation.read'
        }

        response = requests.post(self.token_url, data=data, timeout=30)
        response.raise_for_status()

        token_data = response.json()
        self._access_token = token_data['access_token']
        expires_in = token_data.get('expires_in', 3600)
        self._token_expires_at = datetime.now() + timedelta(seconds=expires_in)

        return self._access_token

    def _make_fhir_request(self, endpoint: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Make authenticated request to Epic FHIR API"""
        access_token = self._get_access_token()

        headers = {
            'Authorization': f'Bearer {access_token}',
            'Accept': 'application/fhir+json',
            'Epic-Client-ID': self.client_id
        }

        url = f"{self.fhir_base_url}/{endpoint}"
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()

        return response.json()


# Initialize client
epic_client = EpicFHIRClient()


def get_patient(patient_id: str) -> Dict[str, Any]:
    """
    Get patient demographics from Epic FHIR.

    Args:
        patient_id: Epic FHIR patient ID

    Returns:
        FHIR Patient resource with demographics
    """
    try:
        result = epic_client._make_fhir_request(f"Patient/{patient_id}")

        # Extract key demographics
        patient_data = {
            'id': result.get('id'),
            'name': _format_name(result.get('name', [])),
            'gender': result.get('gender'),
            'birthDate': result.get('birthDate'),
            'identifiers': _extract_identifiers(result.get('identifier', [])),
            'raw': result
        }

        return {
            'status': 'success',
            'patient': patient_data
        }
    except Exception as e:
        return {
            'status': 'error',
            'error': str(e)
        }


def get_medications(patient_id: str) -> Dict[str, Any]:
    """
    Get active medications for a patient from Epic FHIR.

    Args:
        patient_id: Epic FHIR patient ID

    Returns:
        List of active MedicationRequest resources
    """
    try:
        params = {
            'patient': patient_id,
            'status': 'active'
        }
        result = epic_client._make_fhir_request("MedicationRequest", params)

        medications = []
        for entry in result.get('entry', []):
            resource = entry.get('resource', {})
            medications.append({
                'id': resource.get('id'),
                'status': resource.get('status'),
                'medication': _extract_medication_name(resource),
                'dosage': _extract_dosage(resource),
                'authoredOn': resource.get('authoredOn'),
                'raw': resource
            })

        return {
            'status': 'success',
            'total': result.get('total', len(medications)),
            'medications': medications
        }
    except Exception as e:
        return {
            'status': 'error',
            'error': str(e)
        }


def get_allergies(patient_id: str) -> Dict[str, Any]:
    """
    Get patient allergies from Epic FHIR.

    Args:
        patient_id: Epic FHIR patient ID

    Returns:
        List of AllergyIntolerance resources
    """
    try:
        params = {
            'patient': patient_id
        }
        result = epic_client._make_fhir_request("AllergyIntolerance", params)

        allergies = []
        for entry in result.get('entry', []):
            resource = entry.get('resource', {})
            allergies.append({
                'id': resource.get('id'),
                'clinicalStatus': resource.get('clinicalStatus', {}).get('coding', [{}])[0].get('code'),
                'type': resource.get('type'),
                'substance': _extract_substance_name(resource),
                'reaction': _extract_reaction(resource),
                'recordedDate': resource.get('recordedDate'),
                'raw': resource
            })

        return {
            'status': 'success',
            'total': result.get('total', len(allergies)),
            'allergies': allergies
        }
    except Exception as e:
        return {
            'status': 'error',
            'error': str(e)
        }


def get_observations(patient_id: str, category: Optional[str] = None) -> Dict[str, Any]:
    """
    Get patient observations (vitals, labs) from Epic FHIR.

    Args:
        patient_id: Epic FHIR patient ID
        category: Optional category filter (e.g., 'vital-signs', 'laboratory')

    Returns:
        List of Observation resources
    """
    try:
        params = {
            'patient': patient_id,
            '_sort': '-date',
            '_count': '20'
        }
        if category:
            params['category'] = category

        result = epic_client._make_fhir_request("Observation", params)

        observations = []
        for entry in result.get('entry', []):
            resource = entry.get('resource', {})
            observations.append({
                'id': resource.get('id'),
                'status': resource.get('status'),
                'category': _extract_category(resource),
                'code': _extract_code(resource),
                'value': _extract_value(resource),
                'effectiveDateTime': resource.get('effectiveDateTime'),
                'raw': resource
            })

        return {
            'status': 'success',
            'total': result.get('total', len(observations)),
            'observations': observations
        }
    except Exception as e:
        return {
            'status': 'error',
            'error': str(e)
        }


# Helper functions for data extraction
def _format_name(names: List[Dict]) -> str:
    """Extract formatted name from FHIR name array"""
    if not names:
        return ""
    name = names[0]
    given = " ".join(name.get('given', []))
    family = name.get('family', '')
    return f"{given} {family}".strip()


def _extract_identifiers(identifiers: List[Dict]) -> Dict[str, str]:
    """Extract key identifiers (MRN, etc.)"""
    result = {}
    for identifier in identifiers:
        system = identifier.get('system', '')
        if 'mrn' in system.lower():
            result['MRN'] = identifier.get('value')
        elif 'ssn' in system.lower():
            result['SSN'] = identifier.get('value')
    return result


def _extract_medication_name(resource: Dict) -> str:
    """Extract medication name from MedicationRequest"""
    med = resource.get('medicationCodeableConcept', {})
    codings = med.get('coding', [])
    if codings:
        return codings[0].get('display', 'Unknown')
    return med.get('text', 'Unknown')


def _extract_dosage(resource: Dict) -> str:
    """Extract dosage instructions"""
    dosage_instructions = resource.get('dosageInstruction', [])
    if dosage_instructions:
        return dosage_instructions[0].get('text', 'See prescription')
    return 'Not specified'


def _extract_substance_name(resource: Dict) -> str:
    """Extract allergen substance name"""
    code = resource.get('code', {})
    codings = code.get('coding', [])
    if codings:
        return codings[0].get('display', 'Unknown')
    return code.get('text', 'Unknown')


def _extract_reaction(resource: Dict) -> List[str]:
    """Extract reaction manifestations"""
    reactions = []
    for reaction in resource.get('reaction', []):
        for manifestation in reaction.get('manifestation', []):
            codings = manifestation.get('coding', [])
            if codings:
                reactions.append(codings[0].get('display', 'Unknown'))
    return reactions


def _extract_category(resource: Dict) -> str:
    """Extract observation category"""
    categories = resource.get('category', [])
    if categories:
        codings = categories[0].get('coding', [])
        if codings:
            return codings[0].get('code', 'Unknown')
    return 'Unknown'


def _extract_code(resource: Dict) -> Dict[str, str]:
    """Extract observation code and display"""
    code = resource.get('code', {})
    codings = code.get('coding', [])
    if codings:
        return {
            'code': codings[0].get('code', ''),
            'display': codings[0].get('display', ''),
            'system': codings[0].get('system', '')
        }
    return {'code': '', 'display': code.get('text', 'Unknown'), 'system': ''}


def _extract_value(resource: Dict) -> Dict[str, Any]:
    """Extract observation value"""
    if 'valueQuantity' in resource:
        value = resource['valueQuantity']
        return {
            'type': 'Quantity',
            'value': value.get('value'),
            'unit': value.get('unit'),
            'display': f"{value.get('value')} {value.get('unit', '')}"
        }
    elif 'valueString' in resource:
        return {
            'type': 'String',
            'value': resource['valueString'],
            'display': resource['valueString']
        }
    elif 'valueCodeableConcept' in resource:
        code = resource['valueCodeableConcept']
        codings = code.get('coding', [])
        if codings:
            return {
                'type': 'CodeableConcept',
                'value': codings[0].get('code'),
                'display': codings[0].get('display', code.get('text', 'Unknown'))
            }
    return {'type': 'Unknown', 'value': None, 'display': 'Not available'}
