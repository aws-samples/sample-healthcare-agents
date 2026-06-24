# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Property-based tests for CDS Hooks DTR link structure.

Feature: davinci-pas-alignment, Property 7: CDS Hooks DTR link structure
"""

import json
import sys
import os
from unittest.mock import patch

from hypothesis import given, settings
from hypothesis import strategies as st

# Ensure the parent package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cds_hooks_lambda import handle_order_select, _get_dtr_questionnaire_url
import cds_hooks_lambda


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Payer/procedure combos that exist in the DTR config
KNOWN_DTR_COMBOS = [
    ("Blue Cross Blue Shield", "72148"),
    ("Blue Cross Blue Shield", "72149"),
    ("Blue Cross Blue Shield", "27447"),
    ("UnitedHealthcare", "72148"),
    ("UnitedHealthcare", "27447"),
    ("Aetna", "72148"),
    ("Cigna", "72148"),
]

# Payer/procedure combos that do NOT exist in the DTR config
UNKNOWN_DTR_COMBOS = [
    ("Blue Cross Blue Shield", "99999"),
    ("UnknownPayer", "72148"),
    ("SomePayer", "00000"),
]


def order_select_event(patient_id, payer_name, procedure_code, order_desc):
    """Build a CDS Hooks order-select event dict."""
    return {
        "context": {
            "patientId": patient_id,
            "draftOrders": {
                "entry": [
                    {
                        "resource": {
                            "resourceType": "ServiceRequest",
                            "code": {
                                "text": order_desc,
                                "coding": [{"system": "http://www.ama-assn.org/go/cpt", "code": procedure_code}],
                            },
                        }
                    }
                ]
            },
        },
        "_test_payer_name": payer_name,
    }


def mock_fhir_search_factory(payer_name, coverage_id):
    """Create a mock fhir_search that returns coverage with the given payer."""
    def mock_fhir_search(resource_type, params):
        if resource_type == "Coverage":
            return {
                "entry": [
                    {
                        "resource": {
                            "resourceType": "Coverage",
                            "id": coverage_id,
                            "status": "active",
                            "payor": [{"display": payer_name}],
                        }
                    }
                ]
            }
        elif resource_type == "Claim":
            return {"entry": []}
        return {"entry": []}
    return mock_fhir_search


# ---------------------------------------------------------------------------
# Property 7: CDS Hooks DTR link structure
# ---------------------------------------------------------------------------

@given(
    combo=st.sampled_from(KNOWN_DTR_COMBOS),
    patient_id=st.uuids().map(str),
    coverage_id=st.uuids().map(str),
    order_desc=st.sampled_from(["MRI Lumbar Spine", "CT scan", "Surgery", "MRI Brain"]),
)
@settings(max_examples=100)
def test_dtr_link_present_when_config_exists(combo, patient_id, coverage_id, order_desc):
    """
    Property 7: CDS Hooks DTR link structure

    For any order-select event where prior auth is required and a DTR config
    exists for the payer/procedure, the CDS card shall contain a links array
    with type=smart, non-empty URL, and appContext with required fields.

    Validates: Requirements 4.1, 4.2
    """
    payer_name, procedure_code = combo
    event = order_select_event(patient_id, payer_name, procedure_code, order_desc)

    with patch("cds_hooks_lambda.fhir_search", side_effect=mock_fhir_search_factory(payer_name, coverage_id)), \
         patch("cds_hooks_lambda._requirement_from_policy", return_value=True):
        result = handle_order_select(event)

    cards = result.get("cards", [])
    assert len(cards) >= 1, "Expected at least one card"

    # Find the prior-auth-required card (the one with suggestions or links)
    pa_cards = [c for c in cards if "Prior Authorization Required" in c.get("summary", "")]
    assert len(pa_cards) >= 1, "Expected a prior auth required card"

    card = pa_cards[0]

    # Verify DTR link is present
    links = card.get("links", [])
    assert len(links) >= 1, f"Expected DTR link for {payer_name}/{procedure_code}"

    link = links[0]
    assert link["type"] == "smart", f"Expected link type 'smart', got '{link['type']}'"
    assert link["url"], "Link URL should be non-empty"
    assert link["label"], "Link label should be non-empty"

    # Verify appContext contains required fields
    app_context = json.loads(link["appContext"])
    assert "patientId" in app_context, "appContext missing patientId"
    assert "coverageId" in app_context, "appContext missing coverageId"
    assert "serviceCode" in app_context, "appContext missing serviceCode"
    assert app_context["patientId"] == patient_id
    assert app_context["coverageId"] == coverage_id
    assert app_context["serviceCode"] == procedure_code


@given(
    combo=st.sampled_from(UNKNOWN_DTR_COMBOS),
    patient_id=st.uuids().map(str),
    coverage_id=st.uuids().map(str),
    order_desc=st.sampled_from(["MRI Lumbar Spine", "CT scan", "Surgery"]),
)
@settings(max_examples=100)
def test_no_dtr_link_when_config_missing(combo, patient_id, coverage_id, order_desc):
    """
    When no DTR config exists for the payer/procedure, the card should have
    indicator=warning and no DTR link.

    Validates: Requirement 4.3
    """
    payer_name, procedure_code = combo
    event = order_select_event(patient_id, payer_name, procedure_code, order_desc)

    with patch("cds_hooks_lambda.fhir_search", side_effect=mock_fhir_search_factory(payer_name, coverage_id)), \
         patch("cds_hooks_lambda._requirement_from_policy", return_value=True):
        result = handle_order_select(event)

    cards = result.get("cards", [])
    pa_cards = [c for c in cards if "Prior Authorization Required" in c.get("summary", "")]

    if pa_cards:
        card = pa_cards[0]
        # Should NOT have DTR links
        links = card.get("links", [])
        assert len(links) == 0, f"Should not have DTR link for unknown combo {combo}"
        # Should have warning indicator
        assert card["indicator"] == "warning", "Expected warning indicator when no DTR config"
        assert "manual documentation" in card["detail"].lower(), "Should mention manual documentation"
