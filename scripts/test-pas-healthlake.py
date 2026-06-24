#!/usr/bin/env python3
"""
Test script for HealthLake native $submit and $inquire PAS operations.

Usage:
  AWS_PROFILE=healthcare-deploy HEALTHLAKE_DATASTORE_ID=<your-datastore-id> \
    python3 scripts/test-pas-healthlake.py
"""

import json
import os
import sys
import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.httpsession import URLLib3Session

REGION = os.getenv("HEALTHLAKE_REGION", "us-east-1")
DATASTORE_ID = os.getenv("HEALTHLAKE_DATASTORE_ID")
if not DATASTORE_ID:
    sys.exit(
        "Set the HEALTHLAKE_DATASTORE_ID environment variable to your "
        "HealthLake FHIR datastore ID before running this script."
    )
ENDPOINT = f"https://healthlake.{REGION}.amazonaws.com"

session = boto3.Session()
credentials = session.get_credentials()
http = URLLib3Session()


def healthlake_post(operation: str, body: dict) -> dict:
    url = f"{ENDPOINT}/datastore/{DATASTORE_ID}/r4/{operation}"
    req = AWSRequest(method="POST", url=url, data=json.dumps(body),
                     headers={"Content-Type": "application/fhir+json"})
    SigV4Auth(credentials, "healthlake", REGION).add_auth(req)
    resp = http.send(req.prepare())
    return {"status": resp.status_code, "body": json.loads(resp.content) if resp.content else {}}


# ── Build a minimal PAS Bundle ──
PAS_BUNDLE = {
    "resourceType": "Bundle",
    "meta": {
        "profile": ["http://hl7.org/fhir/us/davinci-pas/StructureDefinition/profile-pas-request-bundle"]
    },
    "identifier": {
        "system": "http://example.org/SUBMITTER_TRANSACTION_IDENTIFIER",
        "value": "TEST-PA-001"
    },
    "type": "collection",
    "timestamp": "2026-04-15T12:00:00Z",
    "entry": [
        {
            "fullUrl": "http://example.org/fhir/Claim/TestPAClaim",
            "resource": {
                "resourceType": "Claim",
                "id": "TestPAClaim",
                "meta": {"profile": ["http://hl7.org/fhir/us/davinci-pas/StructureDefinition/profile-claim"]},
                "identifier": [{"system": "http://example.org/PATIENT_EVENT_TRACE_NUMBER", "value": "TEST-001"}],
                "status": "active",
                "type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/claim-type", "code": "professional"}]},
                "use": "preauthorization",
                "patient": {"reference": "Patient/TestPatient"},
                "created": "2026-04-15T12:00:00Z",
                "insurer": {"reference": "Organization/TestInsurer"},
                "provider": {"reference": "Organization/TestProvider"},
                "priority": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/processpriority", "code": "normal"}]},
                "insurance": [{"sequence": 1, "focal": True, "coverage": {"reference": "Coverage/TestCoverage"}}],
                "item": [{
                    "extension": [
                        {
                            "url": "http://hl7.org/fhir/us/davinci-pas/StructureDefinition/extension-serviceItemRequestType",
                            "valueCodeableConcept": {"coding": [{"system": "https://codesystem.x12.org/005010/1525", "code": "IN", "display": "Initial Medical Services Reservation"}]}
                        },
                        {
                            "url": "http://hl7.org/fhir/us/davinci-pas/StructureDefinition/extension-certificationType",
                            "valueCodeableConcept": {"coding": [{"system": "https://codesystem.x12.org/005010/1322", "code": "I", "display": "Initial"}]}
                        }
                    ],
                    "sequence": 1,
                    "category": {"coding": [{"system": "https://codesystem.x12.org/005010/1365", "code": "1", "display": "Medical Care"}]},
                    "productOrService": {"coding": [{"system": "http://www.ama-assn.org/go/cpt", "code": "72148", "display": "MRI Lumbar Spine without contrast"}]},
                    "servicedDate": "2026-04-20",
                    "locationCodeableConcept": {
                        "coding": [{"system": "https://www.cms.gov/Medicare/Coding/place-of-service-codes/Place_of_Service_Code_Set", "code": "11"}]
                    }
                }]
            }
        },
        {
            "fullUrl": "http://example.org/fhir/Patient/TestPatient",
            "resource": {
                "resourceType": "Patient",
                "id": "TestPatient",
                "meta": {"profile": ["http://hl7.org/fhir/us/davinci-pas/StructureDefinition/profile-subscriber"]},
                "identifier": [{"type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v2-0203", "code": "MB"}]}, "system": "http://example.org/MIN", "value": "MEM-445566"}],
                "name": [{"family": "Feil", "given": ["Bart"]}],
                "gender": "male",
                "birthDate": "1991-08-13"
            }
        },
        {
            "fullUrl": "http://example.org/fhir/Organization/TestInsurer",
            "resource": {
                "resourceType": "Organization",
                "id": "TestInsurer",
                "meta": {"profile": ["http://hl7.org/fhir/us/davinci-pas/StructureDefinition/profile-insurer"]},
                "identifier": [{"system": "http://hl7.org/fhir/sid/us-npi", "value": "1234567893"}],
                "active": True,
                "type": [{"coding": [{"system": "https://codesystem.x12.org/005010/98", "code": "PR"}]}],
                "name": "Blue Cross Blue Shield"
            }
        },
        {
            "fullUrl": "http://example.org/fhir/Organization/TestProvider",
            "resource": {
                "resourceType": "Organization",
                "id": "TestProvider",
                "meta": {"profile": ["http://hl7.org/fhir/us/davinci-pas/StructureDefinition/profile-requestor"]},
                "identifier": [{"system": "http://hl7.org/fhir/sid/us-npi", "value": "8189991234"}],
                "active": True,
                "type": [{"coding": [{"system": "https://codesystem.x12.org/005010/98", "code": "X3"}]}],
                "name": "Test Healthcare Provider"
            }
        },
        {
            "fullUrl": "http://example.org/fhir/Coverage/TestCoverage",
            "resource": {
                "resourceType": "Coverage",
                "id": "TestCoverage",
                "meta": {"profile": ["http://hl7.org/fhir/us/davinci-pas/StructureDefinition/profile-coverage"]},
                "status": "active",
                "subscriberId": "MEM-445566",
                "beneficiary": {"reference": "Patient/TestPatient"},
                "relationship": {"coding": [
                    {"system": "http://terminology.hl7.org/CodeSystem/subscriber-relationship", "code": "self"},
                    {"system": "https://codesystem.x12.org/005010/1069", "code": "18"}
                ]},
                "payor": [{"reference": "Organization/TestInsurer"}]
            }
        }
    ]
}


def test_submit():
    print("=" * 60)
    print("TEST 1: Claim/$submit")
    print("=" * 60)
    result = healthlake_post("Claim/$submit", PAS_BUNDLE)
    print(f"Status: {result['status']}")
    print(f"Response:\n{json.dumps(result['body'], indent=2)[:2000]}")

    if result["status"] == 200:
        # Extract ClaimResponse
        entries = result["body"].get("entry", [])
        for e in entries:
            r = e.get("resource", {})
            if r.get("resourceType") == "ClaimResponse":
                print(f"\n✅ ClaimResponse outcome: {r.get('outcome')}")
                print(f"   Status: {r.get('status')}")
                return True
    elif result["status"] == 412:
        print("\n⚠️  412 = Duplicate submission (already submitted). Use $inquire to check status.")
        return True  # Still a valid response
    else:
        print(f"\n❌ Submit failed with status {result['status']}")
        return False


def test_inquire():
    print("\n" + "=" * 60)
    print("TEST 2: Claim/$inquire")
    print("=" * 60)

    inquiry_bundle = {
        "resourceType": "Bundle",
        "meta": {"profile": ["http://hl7.org/fhir/us/davinci-pas/StructureDefinition/profile-pas-inquiry-request-bundle"]},
        "identifier": {"system": "http://example.org/SUBMITTER_TRANSACTION_IDENTIFIER", "value": "TEST-INQ-001"},
        "type": "collection",
        "timestamp": "2026-04-15T12:30:00Z",
        "entry": [
            {
                "fullUrl": "http://example.org/fhir/Claim/TestPAClaim",
                "resource": {
                    "resourceType": "Claim",
                    "id": "TestPAClaim",
                    "meta": {"profile": ["http://hl7.org/fhir/us/davinci-pas/StructureDefinition/profile-claim-inquiry"]},
                    "status": "active",
                    "type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/claim-type", "code": "professional"}]},
                    "use": "preauthorization",
                    "patient": {"reference": "Patient/TestPatient"},
                    "created": "2026-04-15T12:00:00Z",
                    "insurer": {"reference": "Organization/TestInsurer"},
                    "provider": {"reference": "Organization/TestProvider"}
                }
            },
            {
                "fullUrl": "http://example.org/fhir/Patient/TestPatient",
                "resource": {
                    "resourceType": "Patient",
                    "id": "TestPatient",
                    "meta": {"profile": ["http://hl7.org/fhir/us/davinci-pas/StructureDefinition/profile-beneficiary"]},
                    "name": [{"family": "Feil", "given": ["Bart"]}],
                    "gender": "male"
                }
            },
            {
                "fullUrl": "http://example.org/fhir/Organization/TestInsurer",
                "resource": {
                    "resourceType": "Organization",
                    "id": "TestInsurer",
                    "meta": {"profile": ["http://hl7.org/fhir/us/davinci-pas/StructureDefinition/profile-insurer"]},
                    "name": "Blue Cross Blue Shield"
                }
            },
            {
                "fullUrl": "http://example.org/fhir/Organization/TestProvider",
                "resource": {
                    "resourceType": "Organization",
                    "id": "TestProvider",
                    "meta": {"profile": ["http://hl7.org/fhir/us/davinci-pas/StructureDefinition/profile-requestor"]},
                    "name": "Test Healthcare Provider"
                }
            }
        ]
    }

    result = healthlake_post("Claim/$inquire", inquiry_bundle)
    print(f"Status: {result['status']}")
    print(f"Response:\n{json.dumps(result['body'], indent=2)[:2000]}")

    if result["status"] == 200:
        entries = result["body"].get("entry", [])
        for e in entries:
            r = e.get("resource", {})
            if r.get("resourceType") == "ClaimResponse":
                print(f"\n✅ ClaimResponse outcome: {r.get('outcome')}")
                print(f"   Disposition: {r.get('disposition', 'N/A')}")
                return True
    elif result["status"] == 400 and "not-found" in json.dumps(result["body"]):
        print("\n⚠️  No matching ClaimResponse found (expected if $submit hasn't been called yet)")
        return True
    else:
        print(f"\n❌ Inquire failed with status {result['status']}")
        return False


if __name__ == "__main__":
    print("Testing HealthLake native PAS operations")
    print(f"Datastore: {DATASTORE_ID}")
    print(f"Region: {REGION}\n")

    submit_ok = test_submit()
    inquire_ok = test_inquire()

    print("\n" + "=" * 60)
    print(f"Results: $submit={'✅' if submit_ok else '❌'}  $inquire={'✅' if inquire_ok else '❌'}")
    print("=" * 60)

    sys.exit(0 if submit_ok and inquire_ok else 1)
