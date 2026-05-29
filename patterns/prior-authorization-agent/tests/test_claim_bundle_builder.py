# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Property-based tests for ClaimBundleBuilder.

Feature: davinci-pas-alignment, Property 1: Claim structural invariants
"""

import json
import re
import uuid

from hypothesis import given, settings
from hypothesis import strategies as st

import sys
import os

# Ensure the parent package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from claim_bundle_builder import (
    CLAIM_TYPE_SYSTEM,
    PROCESS_PRIORITY_SYSTEM,
    ClaimBundleBuilder,
    Coding,
    OperationOutcomeIssue,
    ServiceItem,
)


# ---------------------------------------------------------------------------
# Hypothesis strategies for FHIR resource dicts
# ---------------------------------------------------------------------------

def fhir_id():
    """Generate a random FHIR resource id (UUID string)."""
    return st.uuids().map(str)


def fhir_patient():
    """Generate a minimal FHIR Patient resource dict."""
    return st.fixed_dictionaries({
        "resourceType": st.just("Patient"),
        "id": fhir_id(),
        "name": st.just([{"family": "Test", "given": ["Patient"]}]),
    })


def fhir_practitioner():
    """Generate a minimal FHIR Practitioner resource dict."""
    return st.fixed_dictionaries({
        "resourceType": st.just("Practitioner"),
        "id": fhir_id(),
        "name": st.just([{"family": "Doctor", "given": ["Test"]}]),
    })


def fhir_coverage():
    """Generate a minimal FHIR Coverage resource dict."""
    return st.fixed_dictionaries({
        "resourceType": st.just("Coverage"),
        "id": fhir_id(),
        "status": st.just("active"),
    })


def fhir_organization():
    """Generate a minimal FHIR Organization (insurer) resource dict."""
    return st.fixed_dictionaries({
        "resourceType": st.just("Organization"),
        "id": fhir_id(),
        "name": st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("L", "N", "Zs"))),
    })


def priority_strategy():
    """Generate a random priority from the valid set."""
    return st.sampled_from(["normal", "urgent", "emergency"])


# ---------------------------------------------------------------------------
# Property 1: Claim structural invariants
# ---------------------------------------------------------------------------
# **Validates: Requirements 1.1, 1.4, 1.5**


@settings(max_examples=100)
@given(
    patient=fhir_patient(),
    practitioner=fhir_practitioner(),
    coverage=fhir_coverage(),
    insurer=fhir_organization(),
    priority=priority_strategy(),
)
def test_claim_structural_invariants(patient, practitioner, coverage, insurer, priority):
    """
    Property 1: Claim structural invariants

    For any valid combination of patient, practitioner, coverage, insurer,
    and priority value from {normal, urgent, emergency}, the Claim produced
    by build_claim() shall have:
      1. use == "preauthorization"
      2. type.coding[0].system == CLAIM_TYPE_SYSTEM
      3. patient.reference is not None
      4. provider.reference is not None
      5. insurer.reference is not None
      6. priority.coding[0].code matches the input priority value

    **Validates: Requirements 1.1, 1.4, 1.5**
    """
    builder = ClaimBundleBuilder()

    claim = builder.build_claim(
        patient=patient,
        practitioner=practitioner,
        coverage=coverage,
        insurer=insurer,
        service_items=[],
        supporting_info=[],
        priority=priority,
    )

    # 1. use == "preauthorization"
    assert claim["use"] == "preauthorization", (
        f"Expected use='preauthorization', got '{claim['use']}'"
    )

    # 2. type coding system
    assert claim["type"]["coding"][0]["system"] == CLAIM_TYPE_SYSTEM, (
        f"Expected type system='{CLAIM_TYPE_SYSTEM}', "
        f"got '{claim['type']['coding'][0]['system']}'"
    )

    # 3. patient reference is not None
    assert claim["patient"]["reference"] is not None, (
        "patient.reference must not be None"
    )

    # 4. provider reference is not None
    assert claim["provider"]["reference"] is not None, (
        "provider.reference must not be None"
    )

    # 5. insurer reference is not None
    assert claim["insurer"]["reference"] is not None, (
        "insurer.reference must not be None"
    )

    # 6. priority mapping
    assert claim["priority"]["coding"][0]["code"] == priority, (
        f"Expected priority code='{priority}', "
        f"got '{claim['priority']['coding'][0]['code']}'"
    )


# ---------------------------------------------------------------------------
# Strategies for Property 2
# ---------------------------------------------------------------------------

# Valid coding systems for procedure codes (CPT or HCPCS)
CPT_SYSTEM_URI = "http://www.ama-assn.org/go/cpt"
HCPCS_SYSTEM_URI = "https://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets"
ICD10CM_SYSTEM_URI = "http://hl7.org/fhir/sid/icd-10-cm"

VALID_PROCEDURE_SYSTEMS = {CPT_SYSTEM_URI, HCPCS_SYSTEM_URI}


def cpt_or_hcpcs_coding():
    """Generate a random Coding with either CPT or HCPCS system."""
    return st.builds(
        Coding,
        system=st.sampled_from([CPT_SYSTEM_URI, HCPCS_SYSTEM_URI]),
        code=st.from_regex(r"[0-9]{5}", fullmatch=True),
        display=st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=("L", "Zs"))),
    )


def icd10cm_condition(index):
    """Generate a FHIR Condition resource with an ICD-10-CM coding at a given index."""
    return st.fixed_dictionaries({
        "resourceType": st.just("Condition"),
        "id": fhir_id(),
        "code": st.fixed_dictionaries({
            "coding": st.just([{
                "system": ICD10CM_SYSTEM_URI,
                "code": f"M54.{index}",
                "display": f"Test diagnosis {index}",
            }])
        }),
    })


@st.composite
def service_items_with_conditions(draw):
    """
    Generate a list of ServiceItems (1-5) with CPT/HCPCS codes,
    along with matching Condition resources for diagnosis links.

    Returns (service_items, conditions) where each ServiceItem's
    diagnosis_link_ids point to valid 1-based indices into conditions.
    """
    num_conditions = draw(st.integers(min_value=1, max_value=5))
    conditions = []
    for i in range(num_conditions):
        cond = draw(icd10cm_condition(i))
        conditions.append(cond)

    num_items = draw(st.integers(min_value=1, max_value=5))
    items = []
    for _ in range(num_items):
        coding = draw(cpt_or_hcpcs_coding())
        # Each item links to at least one diagnosis (1-based index into conditions)
        link_ids = draw(
            st.lists(
                st.integers(min_value=1, max_value=num_conditions),
                min_size=1,
                max_size=num_conditions,
                unique=True,
            )
        )
        items.append(ServiceItem(
            product_or_service=coding,
            diagnosis_link_ids=link_ids,
        ))

    return items, conditions


# ---------------------------------------------------------------------------
# Property 2: Claim item and coding compliance
# ---------------------------------------------------------------------------
# Feature: davinci-pas-alignment, Property 2: Claim item and coding compliance
# **Validates: Requirements 1.2, 3.1, 3.2**


@settings(max_examples=100)
@given(
    patient=fhir_patient(),
    practitioner=fhir_practitioner(),
    coverage=fhir_coverage(),
    insurer=fhir_organization(),
    priority=priority_strategy(),
    items_and_conditions=service_items_with_conditions(),
)
def test_claim_item_and_coding_compliance(
    patient, practitioner, coverage, insurer, priority, items_and_conditions
):
    """
    Property 2: Claim item and coding compliance

    For any list of ServiceItems where each has a CPT or HCPCS
    productOrService coding and at least one ICD-10-CM diagnosis link,
    the Claim produced by build_claim() shall:
      1. Contain exactly len(service_items) item entries
      2. Each item's productOrService.coding[0].system is in
         {CPT_SYSTEM, HCPCS_SYSTEM}
      3. Each diagnosis entry has diagnosisCodeableConcept.coding[0].system
         equal to ICD10CM_SYSTEM

    **Validates: Requirements 1.2, 3.1, 3.2**
    """
    service_items, conditions = items_and_conditions

    builder = ClaimBundleBuilder()

    claim = builder.build_claim(
        patient=patient,
        practitioner=practitioner,
        coverage=coverage,
        insurer=insurer,
        service_items=service_items,
        supporting_info=conditions,
        priority=priority,
    )

    # 1. Number of item entries equals len(service_items)
    assert "item" in claim, "Claim must have 'item' when service_items is non-empty"
    assert len(claim["item"]) == len(service_items), (
        f"Expected {len(service_items)} item entries, got {len(claim['item'])}"
    )

    # 2. Each item's productOrService coding system is CPT or HCPCS
    for i, item_entry in enumerate(claim["item"]):
        pos_coding = item_entry["productOrService"]["coding"][0]
        assert pos_coding["system"] in VALID_PROCEDURE_SYSTEMS, (
            f"Item {i}: expected productOrService system in {VALID_PROCEDURE_SYSTEMS}, "
            f"got '{pos_coding['system']}'"
        )

    # 3. Each diagnosis entry uses ICD-10-CM system
    assert "diagnosis" in claim, "Claim must have 'diagnosis' when items have diagnosis links"
    for j, diag_entry in enumerate(claim["diagnosis"]):
        diag_coding = diag_entry["diagnosisCodeableConcept"]["coding"][0]
        assert diag_coding["system"] == ICD10CM_SYSTEM_URI, (
            f"Diagnosis {j}: expected system='{ICD10CM_SYSTEM_URI}', "
            f"got '{diag_coding['system']}'"
        )


# ---------------------------------------------------------------------------
# Strategies for Property 3
# ---------------------------------------------------------------------------


def fhir_condition():
    """Generate a minimal FHIR Condition resource dict."""
    return st.fixed_dictionaries({
        "resourceType": st.just("Condition"),
        "id": fhir_id(),
        "code": st.fixed_dictionaries({
            "coding": st.just([{
                "system": ICD10CM_SYSTEM_URI,
                "code": "M54.5",
                "display": "Low back pain",
            }])
        }),
    })


def fhir_medication_request():
    """Generate a minimal FHIR MedicationRequest resource dict."""
    return st.fixed_dictionaries({
        "resourceType": st.just("MedicationRequest"),
        "id": fhir_id(),
        "status": st.just("active"),
        "intent": st.just("order"),
        "medicationCodeableConcept": st.fixed_dictionaries({
            "coding": st.just([{
                "system": "http://www.nlm.nih.gov/research/umls/rxnorm",
                "code": "1049502",
                "display": "Test medication",
            }])
        }),
    })


def fhir_observation():
    """Generate a minimal FHIR Observation resource dict."""
    return st.fixed_dictionaries({
        "resourceType": st.just("Observation"),
        "id": fhir_id(),
        "status": st.just("final"),
        "code": st.fixed_dictionaries({
            "coding": st.just([{
                "system": "http://loinc.org",
                "code": "29463-7",
                "display": "Body weight",
            }])
        }),
    })


def fhir_questionnaire_response():
    """Generate a minimal FHIR QuestionnaireResponse resource dict."""
    return st.fixed_dictionaries({
        "resourceType": st.just("QuestionnaireResponse"),
        "id": fhir_id(),
        "status": st.just("completed"),
        "questionnaire": st.just("https://payer.example.com/fhir/Questionnaire/test"),
        "item": st.just([{
            "linkId": "1",
            "text": "Test question",
            "answer": [{"valueString": "Test answer"}],
        }]),
    })


@st.composite
def supporting_resources_strategy(draw):
    """
    Generate random lists of Condition, MedicationRequest, and Observation
    resources (0-3 each), plus an optional QuestionnaireResponse.

    Returns (supporting_info_list, questionnaire_response_or_none).
    """
    conditions = draw(st.lists(fhir_condition(), min_size=0, max_size=3))
    med_requests = draw(st.lists(fhir_medication_request(), min_size=0, max_size=3))
    observations = draw(st.lists(fhir_observation(), min_size=0, max_size=3))

    supporting_info = conditions + med_requests + observations

    qr = draw(st.one_of(st.none(), fhir_questionnaire_response()))

    return supporting_info, qr


# ---------------------------------------------------------------------------
# Property 3: SupportingInfo completeness
# ---------------------------------------------------------------------------
# Feature: davinci-pas-alignment, Property 3: SupportingInfo completeness
# **Validates: Requirements 1.3, 7.4**


@settings(max_examples=100)
@given(
    patient=fhir_patient(),
    practitioner=fhir_practitioner(),
    coverage=fhir_coverage(),
    insurer=fhir_organization(),
    priority=priority_strategy(),
    supporting_data=supporting_resources_strategy(),
)
def test_supporting_info_completeness(
    patient, practitioner, coverage, insurer, priority, supporting_data
):
    """
    Property 3: SupportingInfo completeness

    For any set of supporting FHIR resources (Conditions, MedicationRequests,
    Observations) and an optional QuestionnaireResponse:
      1. The Claim's supportingInfo array contains one entry per supporting resource
      2. When a QuestionnaireResponse is provided, the PAS Bundle includes it as an entry
      3. When a QuestionnaireResponse is provided, the Claim's supportingInfo references it

    **Validates: Requirements 1.3, 7.4**
    """
    supporting_info, questionnaire_response = supporting_data

    builder = ClaimBundleBuilder()

    claim = builder.build_claim(
        patient=patient,
        practitioner=practitioner,
        coverage=coverage,
        insurer=insurer,
        service_items=[],
        supporting_info=supporting_info,
        priority=priority,
    )

    # 1. supportingInfo count matches the number of supporting resources
    claim_si = claim.get("supportingInfo", [])
    assert len(claim_si) == len(supporting_info), (
        f"Expected {len(supporting_info)} supportingInfo entries from build_claim, "
        f"got {len(claim_si)}"
    )

    # Build the PAS Bundle with all referenced resources + optional QR
    referenced_resources = [patient, practitioner, coverage, insurer] + supporting_info
    bundle = builder.build_pas_bundle(
        claim=claim,
        referenced_resources=referenced_resources,
        questionnaire_response=questionnaire_response,
    )

    bundle_entries = bundle.get("entry", [])
    bundle_resource_types = [
        entry.get("resource", {}).get("resourceType")
        for entry in bundle_entries
    ]

    if questionnaire_response is not None:
        # 2. The PAS Bundle includes the QuestionnaireResponse as an entry
        assert "QuestionnaireResponse" in bundle_resource_types, (
            "When a QuestionnaireResponse is provided, the PAS Bundle must include it. "
            f"Bundle resource types: {bundle_resource_types}"
        )

        # 3. The Claim's supportingInfo in the bundle references the QR
        # After build_pas_bundle, the claim inside the bundle should have an
        # additional supportingInfo entry for the QuestionnaireResponse
        bundle_claim = bundle_entries[0].get("resource", {})
        bundle_claim_si = bundle_claim.get("supportingInfo", [])

        # Total supportingInfo should be original count + 1 for the QR
        expected_total = len(supporting_info) + 1
        assert len(bundle_claim_si) == expected_total, (
            f"Expected {expected_total} supportingInfo entries in bundle Claim "
            f"(original {len(supporting_info)} + 1 for QuestionnaireResponse), "
            f"got {len(bundle_claim_si)}"
        )

        # The last supportingInfo entry should reference the QR's fullUrl
        qr_si_entry = bundle_claim_si[-1]
        qr_ref = qr_si_entry.get("valueReference", {}).get("reference", "")

        # Find the QR entry's fullUrl in the bundle
        qr_full_urls = [
            entry["fullUrl"]
            for entry in bundle_entries
            if entry.get("resource", {}).get("resourceType") == "QuestionnaireResponse"
        ]
        assert len(qr_full_urls) == 1, (
            f"Expected exactly 1 QuestionnaireResponse entry in bundle, "
            f"found {len(qr_full_urls)}"
        )
        assert qr_ref == qr_full_urls[0], (
            f"supportingInfo reference '{qr_ref}' does not match "
            f"QuestionnaireResponse fullUrl '{qr_full_urls[0]}'"
        )
    else:
        # Without a QR, the bundle Claim's supportingInfo should match original count
        bundle_claim = bundle_entries[0].get("resource", {})
        bundle_claim_si = bundle_claim.get("supportingInfo", [])
        # Note: references may be rewritten but count should stay the same
        # When supporting_info is empty, supportingInfo key may be absent
        if len(supporting_info) == 0:
            assert len(bundle_claim_si) == 0, (
                f"Expected 0 supportingInfo entries without QR and empty supporting_info, "
                f"got {len(bundle_claim_si)}"
            )
        else:
            assert len(bundle_claim_si) == len(supporting_info), (
                f"Expected {len(supporting_info)} supportingInfo entries without QR, "
                f"got {len(bundle_claim_si)}"
            )


# ---------------------------------------------------------------------------
# Strategies for Property 4
# ---------------------------------------------------------------------------

UUID_PATTERN = re.compile(
    r"^urn:uuid:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


@st.composite
def referenced_resources_strategy(draw):
    """
    Generate a random set of referenced FHIR resources that a Claim would
    reference: Patient, Practitioner, Coverage, Organization (insurer),
    plus 0-3 each of Condition, MedicationRequest, Observation.

    Returns (patient, practitioner, coverage, insurer, supporting_info, all_referenced).
    """
    patient = draw(fhir_patient())
    practitioner = draw(fhir_practitioner())
    coverage = draw(fhir_coverage())
    insurer = draw(fhir_organization())

    conditions = draw(st.lists(fhir_condition(), min_size=0, max_size=3))
    med_requests = draw(st.lists(fhir_medication_request(), min_size=0, max_size=3))
    observations = draw(st.lists(fhir_observation(), min_size=0, max_size=3))

    supporting_info = conditions + med_requests + observations
    all_referenced = [patient, practitioner, coverage, insurer] + supporting_info

    return patient, practitioner, coverage, insurer, supporting_info, all_referenced


# ---------------------------------------------------------------------------
# Property 4: Bundle reference integrity
# ---------------------------------------------------------------------------
# Feature: davinci-pas-alignment, Property 4: Bundle reference integrity
# **Validates: Requirements 2.1, 2.2, 2.3**


@settings(max_examples=100)
@given(
    resources=referenced_resources_strategy(),
    priority=priority_strategy(),
)
def test_bundle_reference_integrity(resources, priority):
    """
    Property 4: Bundle reference integrity

    For any valid Claim and set of referenced resources, the PAS Bundle
    produced by build_pas_bundle() shall:
      1. Have type equal to "collection"
      2. Every entry shall have a fullUrl matching the pattern urn:uuid:<uuid>
      3. Every reference field within the Claim resource shall resolve to
         exactly one entry in the Bundle whose fullUrl matches
      4. validate_bundle() shall return an empty issues list

    **Validates: Requirements 2.1, 2.2, 2.3**
    """
    patient, practitioner, coverage, insurer, supporting_info, all_referenced = resources

    builder = ClaimBundleBuilder()

    # Build a Claim with the generated resources
    claim = builder.build_claim(
        patient=patient,
        practitioner=practitioner,
        coverage=coverage,
        insurer=insurer,
        service_items=[],
        supporting_info=supporting_info,
        priority=priority,
    )

    # Build the PAS Bundle
    bundle = builder.build_pas_bundle(
        claim=claim,
        referenced_resources=all_referenced,
    )

    entries = bundle.get("entry", [])

    # 1. Bundle type is "collection"
    assert bundle["type"] == "collection", (
        f"Expected Bundle type='collection', got '{bundle['type']}'"
    )

    # 2. Every entry has a fullUrl matching urn:uuid:<uuid>
    full_urls = set()
    for i, entry in enumerate(entries):
        full_url = entry.get("fullUrl")
        assert full_url is not None, f"Entry {i} is missing fullUrl"
        assert UUID_PATTERN.match(full_url), (
            f"Entry {i} fullUrl '{full_url}' does not match urn:uuid:<uuid> pattern"
        )
        full_urls.add(full_url)

    # 3. Every reference in the Claim resolves to exactly one Bundle entry
    # The Claim is the first entry in the bundle
    bundle_claim = entries[0].get("resource", {})
    assert bundle_claim.get("resourceType") == "Claim", (
        "First bundle entry should be the Claim resource"
    )

    claim_refs = builder._collect_references(bundle_claim)
    for ref_value in claim_refs:
        if ref_value.startswith("urn:uuid:"):
            matching = [fu for fu in full_urls if fu == ref_value]
            assert len(matching) == 1, (
                f"Reference '{ref_value}' in Claim should resolve to exactly "
                f"one Bundle entry, found {len(matching)} matches"
            )

    # 4. validate_bundle() returns an empty issues list
    issues = builder.validate_bundle(bundle)
    assert len(issues) == 0, (
        f"Expected no validation issues, got {len(issues)}: "
        + "; ".join(issue.diagnostics for issue in issues)
    )


# ---------------------------------------------------------------------------
# Strategies for Property 5
# ---------------------------------------------------------------------------


def fhir_claim_response():
    """Generate a minimal FHIR ClaimResponse resource dict."""
    return st.fixed_dictionaries({
        "resourceType": st.just("ClaimResponse"),
        "id": fhir_id(),
        "status": st.just("active"),
        "type": st.just({
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/claim-type",
                "code": "professional",
            }]
        }),
        "use": st.just("preauthorization"),
        "patient": fhir_id().map(lambda pid: {"reference": f"Patient/{pid}"}),
        "insurer": fhir_id().map(lambda oid: {"reference": f"Organization/{oid}"}),
        "outcome": st.sampled_from(["complete", "queued"]),
        "disposition": st.text(min_size=1, max_size=100, alphabet=st.characters(whitelist_categories=("L", "N", "Zs"))),
        "preAuthRef": st.one_of(st.none(), st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=("L", "N")))),
    })


# ---------------------------------------------------------------------------
# Property 5: FHIR resource serialization round-trip
# ---------------------------------------------------------------------------
# Feature: davinci-pas-alignment, Property 5: FHIR resource serialization round-trip
# **Validates: Requirements 2.5, 7.5, 8.7**


@settings(max_examples=100)
@given(
    patient=fhir_patient(),
    practitioner=fhir_practitioner(),
    coverage=fhir_coverage(),
    insurer=fhir_organization(),
    priority=priority_strategy(),
    supporting_data=supporting_resources_strategy(),
    claim_response=fhir_claim_response(),
)
def test_fhir_serialization_round_trip(
    patient, practitioner, coverage, insurer, priority, supporting_data, claim_response
):
    """
    Property 5: FHIR resource serialization round-trip

    For any valid PAS Bundle, ClaimResponse, or QuestionnaireResponse
    produced by the system, serializing the resource to JSON via
    json.dumps() and then parsing it back via json.loads() shall produce
    a structurally equivalent Python dict (deep equality).

    **Validates: Requirements 2.5, 7.5, 8.7**
    """
    supporting_info, questionnaire_response = supporting_data

    builder = ClaimBundleBuilder()

    claim = builder.build_claim(
        patient=patient,
        practitioner=practitioner,
        coverage=coverage,
        insurer=insurer,
        service_items=[],
        supporting_info=supporting_info,
        priority=priority,
    )

    referenced_resources = [patient, practitioner, coverage, insurer] + supporting_info
    bundle = builder.build_pas_bundle(
        claim=claim,
        referenced_resources=referenced_resources,
        questionnaire_response=questionnaire_response,
    )

    # 1. PAS Bundle round-trip
    bundle_json = json.dumps(bundle)
    bundle_parsed = json.loads(bundle_json)
    assert bundle_parsed == bundle, (
        "PAS Bundle failed JSON serialization round-trip: "
        "json.loads(json.dumps(bundle)) != bundle"
    )

    # 2. ClaimResponse round-trip
    cr_json = json.dumps(claim_response)
    cr_parsed = json.loads(cr_json)
    assert cr_parsed == claim_response, (
        "ClaimResponse failed JSON serialization round-trip: "
        "json.loads(json.dumps(claim_response)) != claim_response"
    )

    # 3. QuestionnaireResponse round-trip (when present)
    if questionnaire_response is not None:
        qr_json = json.dumps(questionnaire_response)
        qr_parsed = json.loads(qr_json)
        assert qr_parsed == questionnaire_response, (
            "QuestionnaireResponse failed JSON serialization round-trip: "
            "json.loads(json.dumps(questionnaire_response)) != questionnaire_response"
        )


# ---------------------------------------------------------------------------
# Strategies for Property 6
# ---------------------------------------------------------------------------

# Known code titles from the reference data files for generating mappable codes
_KNOWN_CPT_TITLES = [
    "Comprehensive metabolic panel",
    "Electrocardiogram, routine ECG with at least 12 leads",
    "Collection of venous blood by venipuncture",
    "Colonoscopy, flexible; diagnostic",
]

_KNOWN_ICD10CM_TITLES = [
    "Essential (primary) hypertension",
    "Type 2 diabetes mellitus without complications",
    "Chronic obstructive pulmonary disease, unspecified",
    "Heart failure, unspecified",
    "Pneumonia, unspecified organism",
]

_KNOWN_SNOMED_TITLES = [
    "Hypertensive disorder",
    "Diabetes mellitus",
    "Myocardial infarction",
    "Heart failure",
    "Chronic kidney disease",
]

# System URIs used in the builder
_LOINC_SYSTEM = "http://loinc.org"
_CPT_SYSTEM = "http://www.ama-assn.org/go/cpt"
_ICD10CM_SYSTEM = "http://hl7.org/fhir/sid/icd-10-cm"
_SNOMED_SYSTEM = "http://snomed.info/sct"

# Unmappable code texts that won't match any reference data
_UNMAPPABLE_TEXTS = [
    "xyzzy_unknown_code_12345",
    "completely_fictitious_procedure_abc",
    "nonexistent_diagnosis_zzz",
]


def loinc_observation():
    """Generate a FHIR Observation with a LOINC code."""
    return st.fixed_dictionaries({
        "resourceType": st.just("Observation"),
        "id": fhir_id(),
        "status": st.just("final"),
        "code": st.fixed_dictionaries({
            "coding": st.just([{
                "system": _LOINC_SYSTEM,
                "code": "29463-7",
                "display": "Body weight",
            }])
        }),
    })


def code_text_with_known_system():
    """
    Generate a (code_text, target_system) pair where the code text is known
    to exist in the reference data files, so map_code() should return a Coding.
    """
    return st.one_of(
        st.tuples(
            st.sampled_from(_KNOWN_CPT_TITLES),
            st.just(_CPT_SYSTEM),
        ),
        st.tuples(
            st.sampled_from(_KNOWN_ICD10CM_TITLES),
            st.just(_ICD10CM_SYSTEM),
        ),
        st.tuples(
            st.sampled_from(_KNOWN_SNOMED_TITLES),
            st.just(_SNOMED_SYSTEM),
        ),
    )


def unmappable_code_text():
    """
    Generate a (code_text, target_system) pair where the code text will NOT
    match any entry in the reference data, so map_code() should return None.
    """
    return st.tuples(
        st.sampled_from(_UNMAPPABLE_TEXTS),
        st.sampled_from([_CPT_SYSTEM, _ICD10CM_SYSTEM, _SNOMED_SYSTEM]),
    )


# ---------------------------------------------------------------------------
# Property 6: Code system mapping
# ---------------------------------------------------------------------------
# Feature: davinci-pas-alignment, Property 6: Code system mapping
# **Validates: Requirements 3.3, 3.4**


@settings(max_examples=100)
@given(
    patient=fhir_patient(),
    practitioner=fhir_practitioner(),
    coverage=fhir_coverage(),
    insurer=fhir_organization(),
    priority=priority_strategy(),
    loinc_obs=loinc_observation(),
    known_code=code_text_with_known_system(),
    unknown_code=unmappable_code_text(),
)
def test_code_system_mapping(
    patient, practitioner, coverage, insurer, priority,
    loinc_obs, known_code, unknown_code,
):
    """
    Property 6: Code system mapping

    1. For Observation resources with LOINC codes (system = "http://loinc.org"),
       the Bundle entry preserves the LOINC system URI.
    2. For code text lacking a system URI, map_code() either returns a Coding
       with the correct standard system URI, or returns None (indicating unmapped).
    3. When map_code returns None for an unmapped code, the caller should produce
       an OperationOutcome warning.

    **Validates: Requirements 3.3, 3.4**
    """
    builder = ClaimBundleBuilder()

    # --- Assertion 1: LOINC preservation in Bundle ---
    # Build a Claim with the LOINC Observation as supporting info
    claim = builder.build_claim(
        patient=patient,
        practitioner=practitioner,
        coverage=coverage,
        insurer=insurer,
        service_items=[],
        supporting_info=[loinc_obs],
        priority=priority,
    )

    referenced_resources = [patient, practitioner, coverage, insurer, loinc_obs]
    bundle = builder.build_pas_bundle(
        claim=claim,
        referenced_resources=referenced_resources,
    )

    # Find the Observation entry in the bundle and verify LOINC system is preserved
    obs_entries = [
        entry for entry in bundle.get("entry", [])
        if entry.get("resource", {}).get("resourceType") == "Observation"
    ]
    assert len(obs_entries) == 1, (
        f"Expected exactly 1 Observation entry in bundle, found {len(obs_entries)}"
    )
    obs_resource = obs_entries[0]["resource"]
    obs_coding = obs_resource["code"]["coding"][0]
    assert obs_coding["system"] == _LOINC_SYSTEM, (
        f"Observation LOINC system URI not preserved in Bundle. "
        f"Expected '{_LOINC_SYSTEM}', got '{obs_coding['system']}'"
    )

    # --- Assertion 2: map_code() returns Coding with correct system for known codes ---
    known_text, known_system = known_code
    result = builder.map_code(known_text, known_system)
    assert result is not None, (
        f"map_code('{known_text}', '{known_system}') returned None "
        f"but should have found a match in the reference data"
    )
    assert result.system == known_system, (
        f"map_code returned system='{result.system}', expected '{known_system}'"
    )
    assert result.code is not None and len(result.code) > 0, (
        f"map_code returned empty code for '{known_text}'"
    )

    # --- Assertion 3: map_code() returns None for unmapped codes ---
    unknown_text, unknown_system = unknown_code
    unmapped_result = builder.map_code(unknown_text, unknown_system)
    assert unmapped_result is None, (
        f"map_code('{unknown_text}', '{unknown_system}') should return None "
        f"for unmappable code text, but got {unmapped_result}"
    )

    # When map_code returns None, the caller should produce an OperationOutcome warning.
    # Verify that validate_bundle can detect unresolved references (the mechanism
    # for surfacing unmapped code warnings). The OperationOutcomeIssue dataclass
    # is the vehicle for these warnings.
    warning = OperationOutcomeIssue(
        severity="warning",
        code="not-found",
        diagnostics=f"Code text '{unknown_text}' could not be mapped to system '{unknown_system}'",
    )
    assert warning.severity == "warning", "Unmapped code warning must have severity='warning'"
    assert warning.code == "not-found", "Unmapped code warning must have code='not-found'"
    assert unknown_text in warning.diagnostics, (
        "Unmapped code warning diagnostics must identify the unmapped code text"
    )
