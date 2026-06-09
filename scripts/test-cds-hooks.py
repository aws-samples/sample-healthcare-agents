#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Local test script for CDS Hooks service.

Tests the CDS Hooks Lambda handler locally without deploying to AWS.
Simulates EHR hook calls (patient-view, order-select) to verify
prior authorization determination logic.

Usage:
    python scripts/test-cds-hooks.py
"""

import json
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_service_discovery():
    """Test CDS Hooks service discovery endpoint."""
    print("=" * 60)
    print("TEST: CDS Hooks Service Discovery")
    print("=" * 60)

    from gateway.tools.cds_hooks.cds_hooks_lambda import get_cds_services

    result = get_cds_services()
    print(f"   Response received: {len(result.get('cards', [])) if isinstance(result, dict) else 0} card(s)")  # full response not logged (may contain PHI)
    print()

    assert "services" in result
    assert len(result["services"]) == 2
    print("✅ Service discovery: PASSED\n")


def test_patient_view():
    """Test patient-view CDS Hook."""
    print("=" * 60)
    print("TEST: patient-view Hook")
    print("=" * 60)

    from gateway.tools.cds_hooks.cds_hooks_lambda import handle_patient_view

    # Test with a patient ID (will fail HealthLake call locally, but tests the logic)
    event = {
        "hook": "patient-view",
        "hookInstance": "test-001",
        "context": {
            "patientId": "test-patient-001",
            "userId": "Practitioner/test",
        },
    }

    result = handle_patient_view(event)
    print(f"   Response received: {len(result.get('cards', [])) if isinstance(result, dict) else 0} card(s)")  # full response not logged (may contain PHI)
    print()

    assert "cards" in result
    print("✅ patient-view hook: PASSED (returned cards structure)\n")


def test_order_select_mri():
    """Test order-select CDS Hook with MRI order (should require prior auth)."""
    print("=" * 60)
    print("TEST: order-select Hook - MRI Order")
    print("=" * 60)

    from gateway.tools.cds_hooks.cds_hooks_lambda import handle_order_select

    event = {
        "hook": "order-select",
        "hookInstance": "test-002",
        "context": {
            "patientId": "test-patient-001",
            "userId": "Practitioner/test",
            "draftOrders": {
                "resourceType": "Bundle",
                "entry": [
                    {
                        "resource": {
                            "resourceType": "ServiceRequest",
                            "status": "draft",
                            "intent": "order",
                            "code": {
                                "coding": [
                                    {
                                        "system": "http://www.ama-assn.org/go/cpt",
                                        "code": "72148",
                                    }
                                ],
                                "text": "MRI Lumbar Spine without contrast",
                            },
                            "subject": {
                                "reference": "Patient/test-patient-001"
                            },
                        }
                    }
                ],
            },
        },
    }

    result = handle_order_select(event)
    print(f"   Response received: {len(result.get('cards', [])) if isinstance(result, dict) else 0} card(s)")  # full response not logged (may contain PHI)
    print()

    assert "cards" in result
    assert len(result["cards"]) > 0
    # MRI should trigger prior auth requirement
    assert result["cards"][0]["indicator"] == "critical"
    assert "Prior Authorization Required" in result["cards"][0]["summary"]
    print("✅ order-select (MRI): PASSED - Prior auth correctly required\n")


def test_order_select_office_visit():
    """Test order-select CDS Hook with office visit (should NOT require prior auth)."""
    print("=" * 60)
    print("TEST: order-select Hook - Office Visit")
    print("=" * 60)

    from gateway.tools.cds_hooks.cds_hooks_lambda import handle_order_select

    event = {
        "hook": "order-select",
        "hookInstance": "test-003",
        "context": {
            "patientId": "test-patient-001",
            "userId": "Practitioner/test",
            "draftOrders": {
                "resourceType": "Bundle",
                "entry": [
                    {
                        "resource": {
                            "resourceType": "ServiceRequest",
                            "status": "draft",
                            "intent": "order",
                            "code": {
                                "coding": [
                                    {
                                        "system": "http://www.ama-assn.org/go/cpt",
                                        "code": "99213",
                                    }
                                ],
                                "text": "Office Visit Level 3",
                            },
                            "subject": {
                                "reference": "Patient/test-patient-001"
                            },
                        }
                    }
                ],
            },
        },
    }

    result = handle_order_select(event)
    print(f"   Response received: {len(result.get('cards', [])) if isinstance(result, dict) else 0} card(s)")  # full response not logged (may contain PHI)
    print()

    assert "cards" in result
    assert len(result["cards"]) > 0
    assert result["cards"][0]["indicator"] == "info"
    assert "No Prior Authorization Required" in result["cards"][0]["summary"]
    print("✅ order-select (Office Visit): PASSED - No prior auth correctly\n")


def test_order_select_medication():
    """Test order-select CDS Hook with specialty medication."""
    print("=" * 60)
    print("TEST: order-select Hook - Specialty Medication")
    print("=" * 60)

    from gateway.tools.cds_hooks.cds_hooks_lambda import handle_order_select

    event = {
        "hook": "order-select",
        "hookInstance": "test-004",
        "context": {
            "patientId": "test-patient-001",
            "userId": "Practitioner/test",
            "draftOrders": {
                "resourceType": "Bundle",
                "entry": [
                    {
                        "resource": {
                            "resourceType": "MedicationRequest",
                            "status": "draft",
                            "intent": "order",
                            "medicationCodeableConcept": {
                                "text": "Biologics Infusion - Humira"
                            },
                            "subject": {
                                "reference": "Patient/test-patient-001"
                            },
                        }
                    }
                ],
            },
        },
    }

    result = handle_order_select(event)
    print(f"   Response received: {len(result.get('cards', [])) if isinstance(result, dict) else 0} card(s)")  # full response not logged (may contain PHI)
    print()

    assert "cards" in result
    assert len(result["cards"]) > 0
    print("✅ order-select (Biologics): PASSED\n")


def test_payor_policy_lookup():
    """Test payor policy requirement lookup."""
    print("=" * 60)
    print("TEST: Payor Policy - Prior Auth Requirements Lookup")
    print("=" * 60)

    from gateway.tools.payor_policy.payor_policy_lambda import lookup_prior_auth_requirements

    # Test MRI lumbar spine
    result = json.loads(lookup_prior_auth_requirements("72148", "Blue Cross Blue Shield"))
    print(f"   Response received: {len(result.get('cards', [])) if isinstance(result, dict) else 0} card(s)")  # full response not logged (may contain PHI)
    print()

    assert result["procedure_code"] == "72148"
    assert result["typically_requires_prior_auth"] is True
    print("✅ Policy lookup (MRI 72148): PASSED\n")

    # Test office visit
    result = json.loads(lookup_prior_auth_requirements("99213"))
    print(f"   Response received: {len(result.get('cards', [])) if isinstance(result, dict) else 0} card(s)")  # full response not logged (may contain PHI)
    print()

    assert result["procedure_code"] == "99213"
    assert result["typically_requires_prior_auth"] is False
    print("✅ Policy lookup (Office Visit 99213): PASSED\n")


if __name__ == "__main__":
    print("\n🏥 Healthcare Prior Authorization - CDS Hooks & Policy Tests\n")

    tests = [
        test_service_discovery,
        test_order_select_mri,
        test_order_select_office_visit,
        test_order_select_medication,
        test_payor_policy_lookup,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"❌ {test.__name__}: FAILED - {e}\n")
            failed += 1

    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    print("=" * 60)

    # Note about patient-view test
    print("\nNote: patient-view hook test skipped (requires HealthLake connection).")
    print("To test patient-view, deploy the stack and use a real patient ID.\n")

    sys.exit(1 if failed > 0 else 0)
