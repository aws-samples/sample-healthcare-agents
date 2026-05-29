# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Property-based tests for ClaimResponseGenerator.

Feature: davinci-pas-alignment, Property 12: ClaimResponse decision mapping
"""

import sys
import os

from hypothesis import given, settings
from hypothesis import strategies as st

# Ensure the parent package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from claim_response_generator import (
    ClaimResponseGenerator,
    REVIEW_ACTION_EXTENSION_URL,
    X12_CLAIM_ADJUSTMENT_REASON_SYSTEM,
)


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

def decision_strategy():
    """Generate a random decision from the valid set."""
    return st.sampled_from(["approved", "denied", "pended"])


def disposition_strategy():
    """Generate a random non-empty disposition string."""
    return st.text(
        min_size=1,
        max_size=200,
        alphabet=st.characters(whitelist_categories=("L", "N", "Zs")),
    ).filter(lambda s: s.strip())


def fhir_reference():
    """Generate a random FHIR reference string like 'ResourceType/<uuid>'."""
    return st.uuids().map(lambda u: str(u))


def pre_auth_ref_strategy():
    """Generate a random pre-authorization reference string."""
    return st.text(
        min_size=1,
        max_size=30,
        alphabet=st.characters(whitelist_categories=("L", "N")),
    ).filter(lambda s: s.strip())


def error_code_strategy():
    """Generate a random X12 claim adjustment reason code."""
    return st.sampled_from(["1", "2", "3", "4", "50", "96", "97", "197", "198"])


def review_action_strategy():
    """Generate a random review action code."""
    return st.sampled_from(["pend", "request-info", "additional-review"])


# ---------------------------------------------------------------------------
# Property 12: ClaimResponse decision mapping
# ---------------------------------------------------------------------------
# **Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5, 8.6**


@settings(max_examples=100)
@given(
    decision=decision_strategy(),
    disposition=disposition_strategy(),
    claim_ref=fhir_reference(),
    patient_ref=fhir_reference(),
    insurer_ref=fhir_reference(),
    pre_auth_ref=pre_auth_ref_strategy(),
    error_code=error_code_strategy(),
    review_action=review_action_strategy(),
)
def test_claim_response_decision_mapping(
    decision,
    disposition,
    claim_ref,
    patient_ref,
    insurer_ref,
    pre_auth_ref,
    error_code,
    review_action,
):
    """
    Property 12: ClaimResponse decision mapping

    For any authorization decision (approved, denied, or pended) with a
    disposition string, the generated ClaimResponse shall have `use` equal
    to "preauthorization" and:
      (a) if approved, outcome == "complete" and preAuthRef is a non-empty string
      (b) if denied, outcome == "complete" and error contains at least one
          entry with a coded reason
      (c) if pended, outcome == "queued" and an extension with URL
          "http://hl7.org/fhir/us/davinci-pas/StructureDefinition/extension-reviewAction"
          is present
    In all cases, disposition shall be a non-empty string.

    **Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5, 8.6**
    """
    generator = ClaimResponseGenerator()

    # Build kwargs based on decision type
    kwargs = {
        "claim_reference": f"Claim/{claim_ref}",
        "patient_reference": f"Patient/{patient_ref}",
        "insurer_reference": f"Organization/{insurer_ref}",
        "decision": decision,
        "disposition": disposition,
    }

    if decision == "approved":
        kwargs["pre_auth_ref"] = pre_auth_ref
    elif decision == "denied":
        kwargs["error_code"] = error_code
    elif decision == "pended":
        kwargs["review_action"] = review_action

    response = generator.generate(**kwargs)

    # Requirement 8.1: use == "preauthorization"
    assert response["use"] == "preauthorization", (
        f"Expected use='preauthorization', got '{response['use']}'"
    )

    # Requirement 8.3: disposition is a non-empty string
    assert isinstance(response["disposition"], str), (
        "disposition must be a string"
    )
    assert len(response["disposition"]) > 0, (
        "disposition must be a non-empty string"
    )

    if decision == "approved":
        # Requirement 8.2: outcome == "complete" for approved
        assert response["outcome"] == "complete", (
            f"Expected outcome='complete' for approved, got '{response['outcome']}'"
        )
        # Requirement 8.4: preAuthRef is a non-empty string
        assert "preAuthRef" in response, (
            "Approved ClaimResponse must include preAuthRef"
        )
        assert isinstance(response["preAuthRef"], str), (
            "preAuthRef must be a string"
        )
        assert len(response["preAuthRef"]) > 0, (
            "preAuthRef must be a non-empty string"
        )

    elif decision == "denied":
        # Requirement 8.2: outcome == "complete" for denied
        assert response["outcome"] == "complete", (
            f"Expected outcome='complete' for denied, got '{response['outcome']}'"
        )
        # Requirement 8.5: error contains at least one entry with coded reason
        assert "error" in response, (
            "Denied ClaimResponse must include error array"
        )
        assert len(response["error"]) >= 1, (
            "Denied ClaimResponse error array must have at least one entry"
        )
        # Verify the error entry has a coded reason
        error_entry = response["error"][0]
        assert "code" in error_entry, (
            "Error entry must have a 'code' field"
        )
        coding = error_entry["code"].get("coding", [])
        assert len(coding) >= 1, (
            "Error entry code must have at least one coding"
        )
        assert coding[0]["system"] == X12_CLAIM_ADJUSTMENT_REASON_SYSTEM, (
            f"Error coding system must be '{X12_CLAIM_ADJUSTMENT_REASON_SYSTEM}', "
            f"got '{coding[0]['system']}'"
        )
        assert len(coding[0].get("code", "")) > 0, (
            "Error coding must have a non-empty code"
        )

    elif decision == "pended":
        # Requirement 8.2: outcome == "queued" for pended
        assert response["outcome"] == "queued", (
            f"Expected outcome='queued' for pended, got '{response['outcome']}'"
        )
        # Requirement 8.6: extension with reviewAction URL is present
        assert "extension" in response, (
            "Pended ClaimResponse must include extension array"
        )
        review_action_urls = [
            ext["url"] for ext in response["extension"]
        ]
        assert REVIEW_ACTION_EXTENSION_URL in review_action_urls, (
            f"Pended ClaimResponse must have extension with URL "
            f"'{REVIEW_ACTION_EXTENSION_URL}', got URLs: {review_action_urls}"
        )
