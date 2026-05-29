# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Tests for EDI 837P Builder — validation and assembly.
"""

import json
import sys
import os

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from edi_837p_builder import (
    Address,
    BillingProvider,
    ClaimData,
    DiagnosisCode,
    Payer,
    RenderingProvider,
    ServiceLine,
    Subscriber,
    validate_claim,
    assemble_837p,
    validate_and_assemble,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_valid_claim(**overrides) -> ClaimData:
    """Build a minimal valid ClaimData, with optional overrides."""
    defaults = dict(
        claim_id="CLM-TEST-001",
        billing_provider=BillingProvider(
            name="Test Clinic", npi="1234567890", tax_id="123456789",
            taxonomy_code="207Q00000X",
            address=Address(street="123 Main St", city="Seattle", state="WA", zip_code="98101"),
        ),
        subscriber=Subscriber(
            first_name="John", last_name="Doe", member_id="MEM123456",
            date_of_birth="19800115", gender="M", group_number="GRP001",
            address=Address(street="456 Oak Ave", city="Seattle", state="WA", zip_code="98102"),
        ),
        payer=Payer(name="Blue Cross Blue Shield", payer_id="BCBS001"),
        diagnosis_codes=[DiagnosisCode(code="M54.5", description="Low back pain")],
        service_lines=[ServiceLine(
            procedure_code="72148", charge_amount=500.00, units=1,
            date_of_service="20260401", place_of_service="11",
            diagnosis_pointers=[1],
        )],
    )
    defaults.update(overrides)
    return ClaimData(**defaults)


# ---------------------------------------------------------------------------
# Validation: required fields
# ---------------------------------------------------------------------------

class TestRequiredFields:
    def test_valid_claim_passes(self):
        issues = validate_claim(make_valid_claim())
        errors = [i for i in issues if i.severity == "error"]
        assert errors == []

    def test_missing_claim_id(self):
        issues = validate_claim(make_valid_claim(claim_id=""))
        assert any(i.field == "claim_id" for i in issues)

    def test_missing_billing_provider_name(self):
        bp = BillingProvider(name="", npi="1234567890", tax_id="123456789")
        issues = validate_claim(make_valid_claim(billing_provider=bp))
        assert any(i.field == "billing_provider.name" for i in issues)

    def test_missing_subscriber_last_name(self):
        sub = Subscriber(first_name="John", last_name="", member_id="M1",
                         date_of_birth="19800101", gender="M")
        issues = validate_claim(make_valid_claim(subscriber=sub))
        assert any(i.field == "subscriber.last_name" for i in issues)

    def test_missing_diagnosis_codes(self):
        issues = validate_claim(make_valid_claim(diagnosis_codes=[]))
        assert any(i.field == "diagnosis_codes" for i in issues)

    def test_missing_service_lines(self):
        issues = validate_claim(make_valid_claim(service_lines=[]))
        assert any(i.field == "service_lines" for i in issues)

    def test_missing_payer_id(self):
        issues = validate_claim(make_valid_claim(payer=Payer(name="Test", payer_id="")))
        assert any(i.field == "payer.payer_id" for i in issues)


# ---------------------------------------------------------------------------
# Validation: format checks
# ---------------------------------------------------------------------------

class TestFormatValidation:
    def test_invalid_npi_format(self):
        bp = BillingProvider(name="Test", npi="123", tax_id="123456789")
        issues = validate_claim(make_valid_claim(billing_provider=bp))
        assert any("NPI" in i.message for i in issues)

    def test_invalid_tax_id_format(self):
        bp = BillingProvider(name="Test", npi="1234567890", tax_id="12-34")
        issues = validate_claim(make_valid_claim(billing_provider=bp))
        assert any("Tax ID" in i.message for i in issues)

    def test_invalid_date_of_birth(self):
        sub = Subscriber(first_name="J", last_name="D", member_id="M1",
                         date_of_birth="1980-01-15", gender="M")
        issues = validate_claim(make_valid_claim(subscriber=sub))
        assert any("DOB" in i.message for i in issues)

    def test_invalid_gender(self):
        sub = Subscriber(first_name="J", last_name="D", member_id="M1",
                         date_of_birth="19800115", gender="X")
        issues = validate_claim(make_valid_claim(subscriber=sub))
        assert any("gender" in i.message for i in issues)

    def test_invalid_icd10_code(self):
        issues = validate_claim(make_valid_claim(
            diagnosis_codes=[DiagnosisCode(code="INVALID")]
        ))
        assert any("ICD-10" in i.message for i in issues)

    def test_invalid_procedure_code(self):
        issues = validate_claim(make_valid_claim(
            service_lines=[ServiceLine(
                procedure_code="ABC", charge_amount=100, units=1,
                date_of_service="20260401",
            )]
        ))
        assert any("procedure code" in i.message for i in issues)

    def test_invalid_modifier(self):
        issues = validate_claim(make_valid_claim(
            service_lines=[ServiceLine(
                procedure_code="72148", charge_amount=100, units=1,
                date_of_service="20260401", modifiers=["TOOLONG"],
            )]
        ))
        assert any("modifier" in i.message.lower() for i in issues)

    def test_too_many_modifiers(self):
        issues = validate_claim(make_valid_claim(
            service_lines=[ServiceLine(
                procedure_code="72148", charge_amount=100, units=1,
                date_of_service="20260401", modifiers=["25", "59", "76", "77", "XE"],
            )]
        ))
        assert any("Maximum 4" in i.message for i in issues)

    def test_too_many_diagnosis_codes(self):
        codes = [DiagnosisCode(code=f"M54.{i}") for i in range(13)]
        issues = validate_claim(make_valid_claim(diagnosis_codes=codes))
        assert any("Maximum 12" in i.message for i in issues)

    def test_invalid_rendering_provider_npi(self):
        rp = RenderingProvider(first_name="J", last_name="D", npi="bad")
        issues = validate_claim(make_valid_claim(rendering_provider=rp))
        assert any("rendering provider NPI" in i.message for i in issues)

    def test_invalid_state_code(self):
        bp = BillingProvider(
            name="Test", npi="1234567890", tax_id="123456789",
            address=Address(street="123 Main", city="Seattle", state="Washington", zip_code="98101"),
        )
        issues = validate_claim(make_valid_claim(billing_provider=bp))
        assert any("state" in i.message.lower() for i in issues)


# ---------------------------------------------------------------------------
# Validation: business rules
# ---------------------------------------------------------------------------

class TestBusinessRules:
    def test_zero_charge_rejected(self):
        issues = validate_claim(make_valid_claim(
            service_lines=[ServiceLine(
                procedure_code="72148", charge_amount=0, units=1,
                date_of_service="20260401",
            )]
        ))
        assert any("Charge" in i.message for i in issues)

    def test_zero_units_rejected(self):
        issues = validate_claim(make_valid_claim(
            service_lines=[ServiceLine(
                procedure_code="72148", charge_amount=100, units=0,
                date_of_service="20260401",
            )]
        ))
        assert any("Units" in i.message for i in issues)

    def test_future_date_rejected(self):
        issues = validate_claim(make_valid_claim(
            service_lines=[ServiceLine(
                procedure_code="72148", charge_amount=100, units=1,
                date_of_service="20991231",
            )]
        ))
        assert any("future" in i.message for i in issues)

    def test_diagnosis_pointer_out_of_range(self):
        issues = validate_claim(make_valid_claim(
            diagnosis_codes=[DiagnosisCode(code="M54.5")],
            service_lines=[ServiceLine(
                procedure_code="72148", charge_amount=100, units=1,
                date_of_service="20260401", diagnosis_pointers=[5],
            )]
        ))
        assert any("pointer" in i.message.lower() for i in issues)

    def test_total_charge_mismatch_warning(self):
        issues = validate_claim(make_valid_claim(
            total_charge=999.99,
            service_lines=[ServiceLine(
                procedure_code="72148", charge_amount=500, units=1,
                date_of_service="20260401",
            )]
        ))
        warnings = [i for i in issues if i.severity == "warning"]
        assert any("Total charge" in i.message for i in warnings)


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

class TestAssembly:
    def test_valid_claim_assembles_837p(self):
        result = validate_and_assemble(make_valid_claim())
        assert result["valid"] is True
        assert result["edi_837p"] is not None
        assert result["edi_837p"]["transaction_type"] == "837P"

    def test_invalid_claim_blocks_assembly(self):
        result = validate_and_assemble(make_valid_claim(claim_id=""))
        assert result["valid"] is False
        assert result["edi_837p"] is None

    def test_837p_structure(self):
        result = validate_and_assemble(make_valid_claim())
        edi = result["edi_837p"]
        assert edi["billing_provider"]["npi"] == "1234567890"
        assert edi["subscriber"]["member_id"] == "MEM123456"
        assert edi["payer"]["name"] == "Blue Cross Blue Shield"
        assert len(edi["diagnosis_codes"]) == 1
        assert edi["diagnosis_codes"][0]["code"] == "M54.5"
        assert edi["diagnosis_codes"][0]["code_type"] == "ABK"  # principal
        assert len(edi["service_lines"]) == 1
        assert edi["service_lines"][0]["procedure_code"] == "72148"

    def test_total_charge_computed(self):
        claim = make_valid_claim(service_lines=[
            ServiceLine(procedure_code="72148", charge_amount=500, units=1, date_of_service="20260401"),
            ServiceLine(procedure_code="99213", charge_amount=150, units=1, date_of_service="20260401"),
        ])
        result = validate_and_assemble(claim)
        assert result["edi_837p"]["total_charge_amount"] == 650.00

    def test_optional_fields_included(self):
        claim = make_valid_claim(
            prior_auth_number="AUTH123",
            referral_number="REF456",
            rendering_provider=RenderingProvider(
                first_name="Jane", last_name="Smith", npi="0987654321",
            ),
            facility_npi="1111111111", facility_name="Test Hospital",
        )
        result = validate_and_assemble(claim)
        edi = result["edi_837p"]
        assert edi["prior_authorization_number"] == "AUTH123"
        assert edi["referral_number"] == "REF456"
        assert edi["rendering_provider"]["npi"] == "0987654321"
        assert edi["service_facility"]["npi"] == "1111111111"

    def test_json_round_trip(self):
        result = validate_and_assemble(make_valid_claim())
        edi_json = json.dumps(result["edi_837p"])
        parsed = json.loads(edi_json)
        assert parsed == result["edi_837p"]


# ---------------------------------------------------------------------------
# Hypothesis: valid claims always assemble
# ---------------------------------------------------------------------------

@st.composite
def valid_claim_data(draw):
    npi = draw(st.from_regex(r"\d{10}", fullmatch=True))
    tax_id = draw(st.from_regex(r"\d{9}", fullmatch=True))
    num_dx = draw(st.integers(min_value=1, max_value=12))
    dx_codes = [DiagnosisCode(code=f"M54.{i % 10}") for i in range(num_dx)]
    charge = draw(st.floats(min_value=0.01, max_value=99999, allow_nan=False, allow_infinity=False))
    units = draw(st.floats(min_value=0.5, max_value=100, allow_nan=False, allow_infinity=False))

    return ClaimData(
        claim_id=draw(st.text(min_size=1, max_size=20, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-")),
        billing_provider=BillingProvider(name="Test", npi=npi, tax_id=tax_id, taxonomy_code="207Q00000X"),
        subscriber=Subscriber(first_name="J", last_name="D", member_id="M1",
                              date_of_birth="19800101", gender="M"),
        payer=Payer(name="Test Payer", payer_id="P1"),
        diagnosis_codes=dx_codes,
        service_lines=[ServiceLine(
            procedure_code="72148", charge_amount=round(charge, 2),
            units=round(units, 1), date_of_service="20260401",
            diagnosis_pointers=[1],
        )],
    )


@settings(max_examples=50)
@given(claim=valid_claim_data())
def test_valid_claims_always_assemble(claim):
    """Any structurally valid claim should pass validation and produce EDI 837P."""
    result = validate_and_assemble(claim)
    errors = [i for i in result["issues"] if i["severity"] == "error"]
    assert len(errors) == 0, f"Unexpected errors: {errors}"
    assert result["edi_837p"] is not None
    assert result["edi_837p"]["claim_id"] == claim.claim_id
