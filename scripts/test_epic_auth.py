#!/usr/bin/env python3
"""
Test Epic FHIR Backend OAuth 2.0 Authentication
"""

import os
import sys
import time
import jwt
import requests
import boto3

def get_private_key():
    """Retrieve private key from Secrets Manager"""
    session = boto3.Session(profile_name='quicksuite')
    secrets_client = session.client('secretsmanager')
    response = secrets_client.get_secret_value(
        SecretId='/healthcare-agents/epic/private-key'
    )
    return response['SecretString']

def create_jwt_assertion(client_id, token_url):
    """Create JWT assertion for client authentication"""
    now = int(time.time())

    # JWT header with kid
    headers = {
        'kid': 'd6442e4fb9469893',
        'alg': 'RS256',
        'typ': 'JWT'
    }

    payload = {
        'iss': client_id,
        'sub': client_id,
        'aud': token_url,
        'jti': f"{client_id}-{now}",
        'exp': now + 300,
        'iat': now
    }

    private_key = get_private_key()
    return jwt.encode(payload, private_key, algorithm='RS256', headers=headers)

def get_access_token(client_id, token_url):
    """Get access token from Epic"""
    jwt_assertion = create_jwt_assertion(client_id, token_url)

    data = {
        'grant_type': 'client_credentials',
        'client_assertion_type': 'urn:ietf:params:oauth:client-assertion-type:jwt-bearer',
        'client_assertion': jwt_assertion,
        'scope': 'system/Patient.read system/MedicationRequest.read system/AllergyIntolerance.read system/Observation.read'
    }

    print(f"🔑 Requesting access token from: {token_url}")
    response = requests.post(token_url, data=data, timeout=30)

    print(f"📡 Response status: {response.status_code}")

    if response.status_code == 200:
        token_data = response.json()
        print(f"✅ Access token obtained!")
        print(f"   Token type: {token_data.get('token_type')}")
        print(f"   Expires in: {token_data.get('expires_in')} seconds")
        print(f"   Scope: {token_data.get('scope')}")
        return token_data['access_token']
    else:
        print(f"❌ Authentication failed!")
        print(f"   Response: {response.text}")
        return None

def test_patient_read(access_token, fhir_base_url, patient_id):
    """Test reading patient data"""
    url = f"{fhir_base_url}/Patient/{patient_id}"

    headers = {
        'Authorization': f'Bearer {access_token}',
        'Accept': 'application/fhir+json'
    }

    print(f"\n👤 Testing Patient read: {url}")
    response = requests.get(url, headers=headers, timeout=30)

    print(f"📡 Response status: {response.status_code}")

    if response.status_code == 200:
        patient = response.json()
        print(f"✅ Patient data retrieved!")
        if 'name' in patient and len(patient['name']) > 0:
            name = patient['name'][0]
            given = ' '.join(name.get('given', []))
            family = name.get('family', '')
            print(f"   Name: {given} {family}")
        print(f"   ID: {patient.get('id')}")
        return True
    else:
        print(f"❌ Patient read failed!")
        print(f"   Response: {response.text}")
        return False

if __name__ == "__main__":
    # Sandbox configuration — override via environment variables.
    # Do NOT hardcode real client IDs; use env vars or a secrets store.
    CLIENT_ID = os.environ.get("EPIC_CLIENT_ID")
    if not CLIENT_ID:
        raise SystemExit("Set EPIC_CLIENT_ID (your Epic app client ID) before running.")
    TOKEN_URL = os.environ.get(
        "EPIC_TOKEN_URL",
        "https://fhir.epic.com/interconnect-fhir-oauth/oauth2/token",
    )
    FHIR_BASE_URL = os.environ.get(
        "EPIC_FHIR_BASE_URL",
        "https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4",
    )

    # Test patient (Epic public sandbox example)
    TEST_PATIENT_ID = os.environ.get(
        "EPIC_TEST_PATIENT_ID", "<SANDBOX_PATIENT_ID>"
    )

    if CLIENT_ID.startswith("<"):
        print(
            "ERROR: Set EPIC_CLIENT_ID (and optionally EPIC_TOKEN_URL, "
            "EPIC_FHIR_BASE_URL, EPIC_TEST_PATIENT_ID) before running this script."
        )
        sys.exit(1)

    print("=" * 60)
    print("Epic FHIR Backend OAuth 2.0 Authentication Test")
    print("=" * 60)
    print(f"Client ID: {CLIENT_ID}")
    print(f"Token URL: {TOKEN_URL}")
    print(f"FHIR Base: {FHIR_BASE_URL}")
    print(f"Test Patient: {TEST_PATIENT_ID}")
    print("=" * 60)

    # Step 1: Get access token
    access_token = get_access_token(CLIENT_ID, TOKEN_URL)

    if access_token:
        # Step 2: Test patient read
        test_patient_read(access_token, FHIR_BASE_URL, TEST_PATIENT_ID)

    print("\n" + "=" * 60)
    print("Test complete!")
    print("=" * 60)
