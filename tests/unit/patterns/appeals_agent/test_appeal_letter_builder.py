# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Tests for Appeal Letter Builder and Deadline Tracker.
"""

import json
import sys
import os
from datetime import datetime, timedelta, timezone

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../../patterns/appeals-agent"))

from appeal_letter_builder import (
    AppealLetterComponents,
    DenialInfo,
    PatientInfo,
    ProviderInfo,
    ValidationIssue,
    validate_components,
    build_appeal_letter_html,
    validate_and_build,
)
from deadline_tracker import (
    DeadlineStatus,
    check_filing_deadline,
    FILING_DEADLINES,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_valid_components(**overrides) -> AppealLetterComponents:
    """Build minimal valid appeal components, with optional overrides."""
    defaults = dict(
        patient=PatientInfo(name="John Doe", date_of_birth="1980-01-15", member_id="MEM123456"),
        provider=ProviderInfo(name="Dr. Jane Smith", npi="1234567890", contact="555-0100"),
        denial=DenialInfo(
            claim_id="CLM-TEST-001", denial_date="2026-04-01",
            denial_reason_code="50", payer_name="Blue Cross Blue Shield",
        ),
        date_of_service="2026-03-15",
        clinical_rationale="Patient presents with chronic low back pain radiating to left lower extremity. "
                           "Conservative treatment including physical therapy and NSAIDs for 12 weeks failed to provide relief.",
        requested_action="Approve prior authorization for MRI lumbar spine (CPT 72148)",
        supporting_documents=["Clinical notes", "Physical therapy records", "X-ray results"],
    )
    defaults.update(overrides)
    return AppealLetterComponents(**defaults)


# ---------------------------------------------------------------------------
# Validation: required fields
# ---------------------------------------------------------------------------

class TestRequiredFields:
    def test_valid_components_pass(self):
        issues = validate_components(make_valid_components())
        errors = [i for i in issues if i.severity == "error"]
        assert errors == []

    def test_missing_patient_name(self):
        c = make_valid_components(patient=PatientInfo(name="", date_of_birth="1980-01-15", member_id="M1"))
        issues = validate_components(c)
        assert any(i.field == "patient.name" for i in issues if i.severity == "error")

    def test_missing_member_id(self):
        c = make_valid_components(patient=PatientInfo(name="J", date_of_birth="1980-01-15", member_id=""))
        issues = validate_components(c)
        assert any(i.field == "patient.member_id" for i in issues if i.severity == "error")

    def test_missing_provider_npi(self):
        c = make_valid_components(provider=ProviderInfo(name="Dr. X", npi=""))
        issues = validate_components(c)
        assert any(i.field == "provider.npi" for i in issues if i.severity == "error")

    def test_missing_claim_id(self):
        c = make_valid_components(denial=DenialInfo(
            claim_id="", denial_date="2026-04-01", denial_reason_code="50", payer_name="BCBS",
        ))
        issues = validate_components(c)
        assert any(i.field == "denial.claim_id" for i in issues if i.severity == "error")

    def test_missing_clinical_rationale(self):
        c = make_valid_components(clinical_rationale="")
        issues = validate_components(c)
        assert any(i.field == "clinical_rationale" for i in issues if i.severity == "error")

    def test_missing_requested_action(self):
        c = make_valid_components(requested_action="")
        issues = validate_components(c)
        assert any(i.field == "requested_action" for i in issues if i.severity == "error")


# ---------------------------------------------------------------------------
# Validation: format checks
# ---------------------------------------------------------------------------

class TestFormatValidation:
    def test_invalid_npi_format(self):
        c = make_valid_components(provider=ProviderInfo(name="Dr. X", npi="123"))
        issues = validate_components(c)
        assert any("NPI" in i.message for i in issues if i.severity == "error")

    def test_valid_npi_passes(self):
        c = make_valid_components(provider=ProviderInfo(name="Dr. X", npi="1234567890"))
        issues = validate_components(c)
        assert not any("NPI" in i.message for i in issues if i.severity == "error")

    def test_unrecognized_carc_code_warns(self):
        c = make_valid_components(denial=DenialInfo(
            claim_id="C1", denial_date="2026-04-01",
            denial_reason_code="999", payer_name="BCBS",
        ))
        issues = validate_components(c)
        warnings = [i for i in issues if i.severity == "warning"]
        assert any("CARC" in i.message for i in warnings)

    def test_brief_rationale_warns(self):
        c = make_valid_components(clinical_rationale="Too short")
        issues = validate_components(c)
        warnings = [i for i in issues if i.severity == "warning"]
        assert any("brief" in i.message.lower() for i in warnings)

    def test_no_supporting_docs_warns(self):
        c = make_valid_components(supporting_documents=[])
        issues = validate_components(c)
        warnings = [i for i in issues if i.severity == "warning"]
        assert any("supporting" in i.message.lower() for i in warnings)


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

class TestAssembly:
    def test_valid_builds_html(self):
        result = validate_and_build(make_valid_components(), "<p>Appeal narrative</p>")
        assert result["valid"] is True
        assert result["html"] is not None
        assert "<!DOCTYPE html>" in result["html"]

    def test_invalid_blocks_html(self):
        c = make_valid_components(patient=PatientInfo(name="", date_of_birth="", member_id=""))
        result = validate_and_build(c, "<p>test</p>")
        assert result["valid"] is False
        assert result["html"] is None

    def test_html_contains_required_identifiers(self):
        c = make_valid_components()
        result = validate_and_build(c, "<p>Narrative body</p>")
        html = result["html"]
        assert "John Doe" in html
        assert "MEM123456" in html
        assert "CLM-TEST-001" in html
        assert "1234567890" in html
        assert "Blue Cross Blue Shield" in html
        assert "2026-03-15" in html
        assert "Approve prior authorization" in html

    def test_html_contains_supporting_docs(self):
        result = validate_and_build(make_valid_components(), "<p>body</p>")
        html = result["html"]
        assert "Clinical notes" in html
        assert "Physical therapy records" in html

    def test_html_contains_letter_body(self):
        body = "<p>This is the LLM-generated appeal narrative.</p>"
        result = validate_and_build(make_valid_components(), body)
        assert body in result["html"]

    def test_warnings_dont_block_assembly(self):
        c = make_valid_components(supporting_documents=[], clinical_rationale="Short but present rationale here for testing purposes only.")
        result = validate_and_build(c, "<p>body</p>")
        assert result["valid"] is True
        assert len(result["issues"]) > 0  # has warnings
        assert result["html"] is not None


# ---------------------------------------------------------------------------
# Deadline Tracker
# ---------------------------------------------------------------------------

class TestDeadlineTracker:
    def test_normal_deadline(self):
        denial_date = (datetime.now(timezone.utc) - timedelta(days=10)).strftime("%Y-%m-%d")
        status = check_filing_deadline("Blue Cross Blue Shield", denial_date, "first_level")
        assert status.is_expired is False
        assert status.urgency == "normal"
        assert status.days_remaining > 100

    def test_expired_deadline(self):
        denial_date = (datetime.now(timezone.utc) - timedelta(days=200)).strftime("%Y-%m-%d")
        status = check_filing_deadline("Blue Cross Blue Shield", denial_date, "first_level")
        assert status.is_expired is True
        assert status.urgency == "expired"

    def test_critical_deadline(self):
        # 180-day deadline, denied 175 days ago → 5 days left
        denial_date = (datetime.now(timezone.utc) - timedelta(days=175)).strftime("%Y-%m-%d")
        status = check_filing_deadline("Blue Cross Blue Shield", denial_date, "first_level")
        assert status.urgency == "critical"
        assert status.days_remaining <= 7

    def test_urgent_deadline(self):
        # 180-day deadline, denied 160 days ago → 20 days left
        denial_date = (datetime.now(timezone.utc) - timedelta(days=160)).strftime("%Y-%m-%d")
        status = check_filing_deadline("Blue Cross Blue Shield", denial_date, "first_level")
        assert status.urgency == "urgent"

    def test_medicare_shorter_deadline(self):
        # Medicare first_level is 120 days vs default 180
        denial_date = (datetime.now(timezone.utc) - timedelta(days=130)).strftime("%Y-%m-%d")
        status = check_filing_deadline("Medicare", denial_date, "first_level")
        assert status.is_expired is True

    def test_case_insensitive_payer_match(self):
        denial_date = (datetime.now(timezone.utc) - timedelta(days=10)).strftime("%Y-%m-%d")
        status = check_filing_deadline("UNITEDHEALTHCARE Plan", denial_date, "first_level")
        assert status.payer == "UNITEDHEALTHCARE Plan"
        assert status.is_expired is False

    def test_unknown_payer_uses_default(self):
        denial_date = (datetime.now(timezone.utc) - timedelta(days=10)).strftime("%Y-%m-%d")
        status = check_filing_deadline("Unknown Payer XYZ", denial_date, "first_level")
        assert status.is_expired is False
        # Default first_level is 180 days
        assert status.days_remaining > 100

    def test_second_level_shorter_window(self):
        # Second level is 60 days for most payers
        denial_date = (datetime.now(timezone.utc) - timedelta(days=65)).strftime("%Y-%m-%d")
        status = check_filing_deadline("Blue Cross Blue Shield", denial_date, "second_level")
        assert status.is_expired is True

    def test_peer_to_peer_very_short(self):
        # Peer-to-peer is 10 days
        denial_date = (datetime.now(timezone.utc) - timedelta(days=12)).strftime("%Y-%m-%d")
        status = check_filing_deadline("Aetna", denial_date, "peer_to_peer")
        assert status.is_expired is True


# ---------------------------------------------------------------------------
# Hypothesis: valid components always produce HTML
# ---------------------------------------------------------------------------

@st.composite
def valid_components(draw):
    # Helper to generate non-whitespace-only text for fields that get .strip() validated
    def non_blank_text(min_size, max_size, alphabet):
        text = draw(st.text(min_size=min_size, max_size=max_size, alphabet=alphabet))
        # Ensure at least one non-space character
        if not text.strip():
            text = "A" + text
        return text

    return AppealLetterComponents(
        patient=PatientInfo(
            name=non_blank_text(1, 30, "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz "),
            date_of_birth=draw(st.text(min_size=1, max_size=10, alphabet="0123456789-")),
            member_id=draw(st.text(min_size=1, max_size=20, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")),
        ),
        provider=ProviderInfo(
            name=non_blank_text(1, 30, "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz. "),
            npi=draw(st.from_regex(r"\d{10}", fullmatch=True)),
        ),
        denial=DenialInfo(
            claim_id=draw(st.text(min_size=1, max_size=20, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-")),
            denial_date=draw(st.text(min_size=1, max_size=10, alphabet="0123456789-")),
            denial_reason_code=draw(st.sampled_from(["1", "4", "16", "50", "96", "97", "197", "198"])),
            payer_name=non_blank_text(1, 30, "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz "),
        ),
        date_of_service=draw(st.text(min_size=1, max_size=10, alphabet="0123456789-")),
        clinical_rationale="Detailed clinical rationale with sufficient length to pass the minimum threshold for validation checks in the builder module.",
        requested_action=non_blank_text(1, 50, "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz 0123456789"),
    )


@settings(max_examples=50)
@given(components=valid_components())
def test_valid_components_always_produce_html(components):
    """Any structurally valid components should pass validation and produce HTML."""
    result = validate_and_build(components, "<p>Appeal narrative</p>")
    errors = [i for i in result["issues"] if i["severity"] == "error"]
    assert len(errors) == 0, f"Unexpected errors: {errors}"
    assert result["html"] is not None
    assert "<!DOCTYPE html>" in result["html"]
