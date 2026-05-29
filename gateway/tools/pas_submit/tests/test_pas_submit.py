# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Property-based tests for Claim/$submit Bundle validation.

Feature: davinci-pas-alignment, Property 16: $submit Bundle validation
"""

import json
import sys
import os
from unittest.mock import patch, MagicMock

from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pas_submit_lambda import _validate_bundle


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

def valid_claim():
    """Generate a valid FHIR Claim with use=preauthorization."""
    return st.fixed_dictionaries({
        "resourceType": st.just("Claim"),
        "id": st.uuids().map(str),
        "use": st.just("preauthorization"),
        "type": st.just({"coding": [{"system": "http://terminology.hl7.org/CodeSystem/claim-type", "code": "professional"}]}),
        "patient": st.builds(lambda uid: {"reference": f"urn:uuid:{uid}"}, st.uuids().map(str)),
        "insurer": st.builds(lambda uid: {"reference": f"urn:uuid:{uid}"}, st.uuids().map(str)),
        "item": st.just([{"sequence": 1, "productOrService": {"coding": [{"code": "72148"}]}}]),
    })


def valid_bundle():
    """Generate a valid PAS Bundle containing exactly one Claim."""
    return valid_claim().map(lambda claim: {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [
            {"fullUrl": f"urn:uuid:{claim['id']}", "resource": claim},
            {"fullUrl": "urn:uuid:patient-1", "resource": {"resourceType": "Patient", "id": "patient-1"}},
        ],
    })


def invalid_bundle_no_claim():
    """Generate a Bundle with no Claim resource."""
    return st.just({
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [
            {"fullUrl": "urn:uuid:p1", "resource": {"resourceType": "Patient", "id": "p1"}},
        ],
    })


def invalid_bundle_wrong_use():
    """Generate a Bundle with a Claim that has wrong use."""
    return valid_claim().map(lambda claim: {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [
            {"fullUrl": f"urn:uuid:{claim['id']}", "resource": {**claim, "use": "claim"}},
        ],
    })


def invalid_bundle_multiple_claims():
    """Generate a Bundle with multiple Claim resources."""
    return st.tuples(valid_claim(), valid_claim()).map(lambda claims: {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [
            {"fullUrl": f"urn:uuid:{claims[0]['id']}", "resource": claims[0]},
            {"fullUrl": f"urn:uuid:{claims[1]['id']}", "resource": claims[1]},
        ],
    })


# ---------------------------------------------------------------------------
# Property 16: $submit Bundle validation
# ---------------------------------------------------------------------------

@given(bundle=valid_bundle())
@settings(max_examples=100)
def test_valid_bundle_passes_validation(bundle):
    """
    Property 16: $submit Bundle validation (valid case)

    For any valid PAS Bundle containing exactly one Claim with
    use=preauthorization, validation shall accept the Bundle.

    Validates: Requirements 11.2, 11.3
    """
    claim, errors = _validate_bundle(bundle)
    assert claim is not None, "Valid bundle should produce a Claim"
    assert len(errors) == 0, f"Valid bundle should have no errors, got: {errors}"
    assert claim["use"] == "preauthorization"
    assert claim["resourceType"] == "Claim"


@given(bundle=invalid_bundle_no_claim())
@settings(max_examples=50)
def test_bundle_without_claim_rejected(bundle):
    """
    Property 16: $submit Bundle validation (no Claim)

    Bundles with zero Claim resources shall be rejected with an error.

    Validates: Requirements 11.3, 11.4
    """
    claim, errors = _validate_bundle(bundle)
    assert claim is None
    assert len(errors) >= 1
    assert "exactly one Claim" in errors[0]["issue"][0]["diagnostics"]


@given(bundle=invalid_bundle_wrong_use())
@settings(max_examples=50)
def test_bundle_with_wrong_use_rejected(bundle):
    """
    Property 16: $submit Bundle validation (wrong use)

    Bundles with a Claim where use != preauthorization shall be rejected.

    Validates: Requirements 11.3, 11.4
    """
    claim, errors = _validate_bundle(bundle)
    assert claim is None
    assert len(errors) >= 1
    assert "preauthorization" in errors[0]["issue"][0]["diagnostics"]


@given(bundle=invalid_bundle_multiple_claims())
@settings(max_examples=50)
def test_bundle_with_multiple_claims_rejected(bundle):
    """
    Property 16: $submit Bundle validation (multiple Claims)

    Bundles with more than one Claim resource shall be rejected.

    Validates: Requirements 11.3, 11.4
    """
    claim, errors = _validate_bundle(bundle)
    assert claim is None
    assert len(errors) >= 1
    assert "exactly one Claim" in errors[0]["issue"][0]["diagnostics"]
