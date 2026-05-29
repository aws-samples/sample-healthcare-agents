# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Property-based tests for DTR Questionnaire auto-fill evaluation.

Feature: davinci-pas-alignment, Property 10: Auto-fill evaluation and logging
"""

import json
import sys
import os
from unittest.mock import patch, MagicMock

from hypothesis import given, settings
from hypothesis import strategies as st

# Ensure the parent package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dtr_questionnaire_lambda import evaluate_questionnaire_expressions


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

FHIR_RESOURCE_TYPES = ["Patient", "Condition", "Observation", "MedicationRequest", "Coverage"]
EXPRESSION_TYPES = ["initialExpression", "calculatedExpression"]


def fhir_expression_extension(resource_type, expr_type):
    """Build a FHIR extension dict for an expression."""
    url_map = {
        "initialExpression": "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-initialExpression",
        "calculatedExpression": "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-calculatedExpression",
    }
    return {
        "url": url_map[expr_type],
        "valueExpression": {
            "language": "text/fhirpath",
            "expression": f"{resource_type}.id",
        },
    }


def questionnaire_item_with_expression():
    """Generate a Questionnaire item with an expression extension."""
    return st.fixed_dictionaries({
        "linkId": st.text(min_size=1, max_size=10, alphabet="abcdefghijklmnopqrstuvwxyz0123456789"),
        "text": st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("L", "N", "Zs"))),
        "type": st.sampled_from(["string", "integer", "boolean", "date", "decimal"]),
        "resource_type": st.sampled_from(FHIR_RESOURCE_TYPES),
        "expr_type": st.sampled_from(EXPRESSION_TYPES),
    }).map(lambda d: {
        "linkId": d["linkId"],
        "text": d["text"],
        "type": d["type"],
        "extension": [fhir_expression_extension(d["resource_type"], d["expr_type"])],
        "_meta": {"resource_type": d["resource_type"], "expr_type": d["expr_type"]},
    })


def questionnaire_item_without_expression():
    """Generate a Questionnaire item without an expression extension."""
    return st.fixed_dictionaries({
        "linkId": st.text(min_size=1, max_size=10, alphabet="abcdefghijklmnopqrstuvwxyz0123456789"),
        "text": st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("L", "N", "Zs"))),
        "type": st.sampled_from(["string", "integer", "boolean"]),
    })


def questionnaire_with_expressions():
    """Generate a FHIR Questionnaire with a mix of items with and without expressions."""
    return st.fixed_dictionaries({
        "resourceType": st.just("Questionnaire"),
        "id": st.uuids().map(str),
        "url": st.just("https://payer.example.com/fhir/Questionnaire/test"),
        "status": st.just("active"),
        "items_with_expr": st.lists(questionnaire_item_with_expression(), min_size=1, max_size=5),
        "items_without_expr": st.lists(questionnaire_item_without_expression(), min_size=0, max_size=3),
    }).map(lambda d: {
        "resourceType": d["resourceType"],
        "id": d["id"],
        "url": d["url"],
        "status": d["status"],
        "item": d["items_with_expr"] + d["items_without_expr"],
        "_expr_items": d["items_with_expr"],
    })


def mock_fhir_resource(resource_type, resource_id):
    """Create a mock FHIR resource dict."""
    return {
        "resourceType": resource_type,
        "id": resource_id,
        "name": [{"family": "Test", "given": ["Mock"]}],
        "code": {"coding": [{"system": "http://example.com", "code": "test"}]},
    }


# ---------------------------------------------------------------------------
# Property 10: Auto-fill evaluation and logging
# ---------------------------------------------------------------------------

@given(data=questionnaire_with_expressions(), patient_id=st.uuids().map(str))
@settings(max_examples=100)
def test_autofill_evaluation_produces_results_for_expression_items(data, patient_id):
    """
    Property 10: Auto-fill evaluation and logging

    For any FHIR Questionnaire item with an initialExpression or calculatedExpression
    extension, and any patient data set from HealthLake, the auto-fill evaluation shall
    produce a result containing the item's linkId, the source FHIR resource ID, and the
    resolved value.

    Validates: Requirements 6.1, 6.2, 6.4
    """
    questionnaire = {k: v for k, v in data.items() if not k.startswith("_")}
    expr_items = data["_expr_items"]

    # Build mock responses for each resource type referenced by expressions
    resource_types_used = set()
    for item in expr_items:
        meta = item.get("_meta", {})
        resource_types_used.add(meta.get("resource_type", "Patient"))

    # Clean _meta from items before passing to function
    clean_items = []
    for item in questionnaire.get("item", []):
        clean_item = {k: v for k, v in item.items() if not k.startswith("_")}
        clean_items.append(clean_item)
    questionnaire["item"] = clean_items

    def mock_fhir_search(resource_type, params):
        rid = f"mock-{resource_type.lower()}-001"
        return {
            "entry": [{"resource": mock_fhir_resource(resource_type, rid)}],
            "total": 1,
        }

    def mock_fhir_read(resource_type, rid):
        return mock_fhir_resource(resource_type, rid)

    with patch("dtr_questionnaire_lambda._fhir_search", side_effect=mock_fhir_search), \
         patch("dtr_questionnaire_lambda._fhir_read", side_effect=mock_fhir_read):
        results = evaluate_questionnaire_expressions(questionnaire, patient_id)

    # Verify: one result per expression item
    expr_link_ids = {item.get("linkId") for item in expr_items}
    result_link_ids = {r["linkId"] for r in results}

    # Every expression item should have a result
    assert expr_link_ids == result_link_ids, (
        f"Expected results for linkIds {expr_link_ids}, got {result_link_ids}"
    )

    # Verify each result has required fields
    for result in results:
        assert "linkId" in result, "Result missing linkId"
        assert "sourceResourceId" in result, "Result missing sourceResourceId"
        assert "resolvedValue" in result, "Result missing resolvedValue"
        assert "expressionType" in result, "Result missing expressionType"

        # sourceResourceId should be in format "ResourceType/id"
        src_id = result["sourceResourceId"]
        if src_id is not None:
            assert "/" in src_id, f"sourceResourceId should be 'Type/id' format, got: {src_id}"

        # expressionType should be one of the known types
        assert result["expressionType"] in EXPRESSION_TYPES, (
            f"Unexpected expressionType: {result['expressionType']}"
        )
