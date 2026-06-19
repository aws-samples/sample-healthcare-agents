# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for edi_837p_builder — validation and assembly logic."""

import sys, os
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../../../patterns/claims-assembly-agent")
))

import pytest
from edi_837p_builder import (
    Address, BillingProvider, ClaimData, DiagnosisCode,
    Payer, ServiceLine, Subscriber, ValidationIssue,
    validate_claim, validate_and_assemble,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _provider(**kw):
    defaults = dict(name="Test Clinic", npi="1234567890", tax_id="123456789", taxonomy_code="207Q00000X")
    return BillingProvider(**{**defaults, **kw})

def _subscriber(**kw):
    defaults = dict(first_name="Jane", last_name="Smith", member_id="MEM001",
                    date_of_birth="19800115", gender="F")
    return Subscriber(**{**defaults, **kw})

def _claim(**kw):
    defaults = dict(
        claim_id="CLM-001",
        billing_provider=_provider(),
        subscriber=_subscriber(),
        payer=Payer(name="BlueCross", payer_id="BCBS01"),
        diagnosis_codes=[DiagnosisCode(code="I10")],
        service_lines=[ServiceLine(procedure_code="99213", charge_amount=150.0,
                                   units=1, date_of_service="20260601")],
        total_charge=150.0,
    )
    return ClaimData(**{**defaults, **kw})

def _errors(issues): return [i for i in issues if i.severity == "error"]


# ---------------------------------------------------------------------------
# NPI validation
# ---------------------------------------------------------------------------

def test_valid_npi_passes():
    assert _errors(validate_claim(_claim())) == []

def test_npi_too_short_is_error():
    issues = validate_claim(_claim(billing_provider=_provider(npi="12345")))
    assert any("NPI" in i.message for i in _errors(issues))

def test_npi_non_numeric_is_error():
    issues = validate_claim(_claim(billing_provider=_provider(npi="12345ABCDE")))
    assert any("NPI" in i.message for i in _errors(issues))

def test_npi_11_digits_is_error():
    issues = validate_claim(_claim(billing_provider=_provider(npi="12345678901")))
    assert any("NPI" in i.message for i in _errors(issues))


# ---------------------------------------------------------------------------
# Diagnosis code validation
# ---------------------------------------------------------------------------

def test_missing_diagnosis_is_error():
    issues = validate_claim(_claim(diagnosis_codes=[]))
    assert any("diagnosis" in i.message.lower() for i in _errors(issues))

def test_valid_icd10_passes():
    c = _claim(diagnosis_codes=[DiagnosisCode(code="E11.22"), DiagnosisCode(code="N18.3")])
    assert _errors(validate_claim(c)) == []

def test_invalid_icd10_format_is_error():
    issues = validate_claim(_claim(diagnosis_codes=[DiagnosisCode(code="BAD")]))
    assert any("diagnosis" in i.field.lower() for i in _errors(issues))

def test_too_many_diagnosis_codes_is_error():
    codes = [DiagnosisCode(code=f"I{i:02d}") for i in range(13)]
    issues = validate_claim(_claim(diagnosis_codes=codes))
    assert any("12" in i.message for i in _errors(issues))


# ---------------------------------------------------------------------------
# Procedure code validation
# ---------------------------------------------------------------------------

def test_valid_cpt_passes():
    sl = ServiceLine(procedure_code="99214", charge_amount=200.0, units=1, date_of_service="20260601")
    assert _errors(validate_claim(_claim(service_lines=[sl]))) == []

def test_invalid_cpt_4_digits_is_error():
    sl = ServiceLine(procedure_code="9921", charge_amount=150.0, units=1, date_of_service="20260601")
    issues = validate_claim(_claim(service_lines=[sl]))
    assert any("procedure" in i.field.lower() for i in _errors(issues))

def test_no_service_lines_is_error():
    issues = validate_claim(_claim(service_lines=[]))
    assert any("service" in i.message.lower() for i in _errors(issues))

def test_negative_charge_is_error():
    sl = ServiceLine(procedure_code="99213", charge_amount=-1.0, units=1, date_of_service="20260601")
    issues = validate_claim(_claim(service_lines=[sl]))
    assert any("charge" in i.message.lower() for i in _errors(issues))


# ---------------------------------------------------------------------------
# Subscriber validation
# ---------------------------------------------------------------------------

def test_invalid_dob_format_is_error():
    issues = validate_claim(_claim(subscriber=_subscriber(date_of_birth="1980-01-15")))
    assert any("DOB" in i.message or "date_of_birth" in i.field for i in _errors(issues))

def test_invalid_gender_is_error():
    issues = validate_claim(_claim(subscriber=_subscriber(gender="X")))
    assert any("gender" in i.message.lower() for i in _errors(issues))

def test_missing_member_id_is_error():
    issues = validate_claim(_claim(subscriber=_subscriber(member_id="")))
    assert any("member" in i.message.lower() for i in _errors(issues))


# ---------------------------------------------------------------------------
# EDI 837P assembly
# ---------------------------------------------------------------------------

def test_valid_claim_assembles_without_error():
    result = validate_and_assemble(_claim())
    assert result["valid"] is True
    assert result["edi_837p"] is not None

def test_assembled_claim_has_required_segments():
    result = validate_and_assemble(_claim())
    edi = result["edi_837p"]
    assert "CLM" in edi or "claim" in str(edi).lower()
    assert "NM1" in edi or "billing_provider" in str(edi).lower()

def test_invalid_claim_returns_error_status():
    bad = _claim(billing_provider=_provider(npi="12345"), diagnosis_codes=[])
    result = validate_and_assemble(bad)
    assert result["valid"] is False
    assert result["error_count"] >= 2

def test_multi_service_line_claim_assembles():
    lines = [
        ServiceLine(procedure_code="99214", charge_amount=200.0, units=1, date_of_service="20260610"),
        ServiceLine(procedure_code="93000", charge_amount=75.0, units=1, date_of_service="20260610"),
    ]
    result = validate_and_assemble(_claim(service_lines=lines, total_charge=275.0))
    assert result["valid"] is True
