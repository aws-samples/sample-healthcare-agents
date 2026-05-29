# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
EDI 837P Claim Builder module for deterministic validation and assembly.

Validates claim data elements against HIPAA 5010 requirements and assembles
a structured EDI 837P JSON representation. Pure-function module imported
by the Claims Assembly Agent.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Address:
    """Postal address."""
    street: str
    city: str
    state: str
    zip_code: str


@dataclass
class BillingProvider:
    """Loop 2010AA — Billing Provider."""
    name: str
    npi: str
    tax_id: str
    taxonomy_code: str = ""
    address: Optional[Address] = None
    contact_phone: str = ""


@dataclass
class Subscriber:
    """Loop 2010BA — Subscriber."""
    first_name: str
    last_name: str
    member_id: str
    date_of_birth: str  # CCYYMMDD
    gender: str  # M, F, U
    group_number: str = ""
    address: Optional[Address] = None
    relationship_code: str = "18"  # 18 = self


@dataclass
class Payer:
    """Loop 2010BB — Payer."""
    name: str
    payer_id: str
    address: Optional[Address] = None


@dataclass
class RenderingProvider:
    """Loop 2310B — Rendering Provider (if different from billing)."""
    first_name: str
    last_name: str
    npi: str
    taxonomy_code: str = ""


@dataclass
class DiagnosisCode:
    """ICD-10-CM diagnosis code."""
    code: str
    description: str = ""


@dataclass
class ServiceLine:
    """Loop 2400 — Service Line."""
    procedure_code: str  # CPT or HCPCS
    charge_amount: float
    units: float
    date_of_service: str  # CCYYMMDD
    place_of_service: str = "11"  # default: office
    modifiers: list[str] = field(default_factory=list)
    diagnosis_pointers: list[int] = field(default_factory=list)  # 1-based
    description: str = ""


@dataclass
class ClaimData:
    """Complete claim data for EDI 837P assembly."""
    claim_id: str
    billing_provider: BillingProvider
    subscriber: Subscriber
    payer: Payer
    diagnosis_codes: list[DiagnosisCode]
    service_lines: list[ServiceLine]
    total_charge: float = 0.0
    prior_auth_number: str = ""
    referral_number: str = ""
    rendering_provider: Optional[RenderingProvider] = None
    facility_npi: str = ""
    facility_name: str = ""


@dataclass
class ValidationIssue:
    """A validation problem found in the claim."""
    severity: str  # "error" | "warning"
    field: str
    message: str


# ---------------------------------------------------------------------------
# Format patterns
# ---------------------------------------------------------------------------

NPI_PATTERN = re.compile(r"^\d{10}$")
TAX_ID_PATTERN = re.compile(r"^\d{9}$")
DATE_PATTERN = re.compile(r"^\d{8}$")  # CCYYMMDD
ICD10_PATTERN = re.compile(r"^[A-Z]\d{2}(\.\d{1,4})?$", re.IGNORECASE)
CPT_PATTERN = re.compile(r"^\d{5}$")
HCPCS_PATTERN = re.compile(r"^[A-Z]\d{4}$", re.IGNORECASE)
MODIFIER_PATTERN = re.compile(r"^[A-Z0-9]{2}$", re.IGNORECASE)
POS_PATTERN = re.compile(r"^\d{2}$")
STATE_PATTERN = re.compile(r"^[A-Z]{2}$")
ZIP_PATTERN = re.compile(r"^\d{5}(-\d{4})?$")
VALID_GENDERS = {"M", "F", "U"}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_claim(claim: ClaimData) -> list[ValidationIssue]:
    """
    Validate all claim data elements against HIPAA 5010 requirements.

    Checks required fields, format validation, cross-field consistency,
    and business rules.

    Returns:
        List of ValidationIssue objects. Empty list means valid.
    """
    issues: list[ValidationIssue] = []

    # --- Claim-level ---
    if not claim.claim_id or not claim.claim_id.strip():
        issues.append(ValidationIssue("error", "claim_id", "Missing claim ID"))

    # --- Billing Provider (Loop 2010AA) ---
    bp = claim.billing_provider
    if not bp.name:
        issues.append(ValidationIssue("error", "billing_provider.name", "Missing billing provider name"))
    if not NPI_PATTERN.match(bp.npi or ""):
        issues.append(ValidationIssue("error", "billing_provider.npi", f"Invalid NPI: '{bp.npi}'. Must be 10 digits."))
    if not TAX_ID_PATTERN.match(bp.tax_id.replace("-", "") if bp.tax_id else ""):
        issues.append(ValidationIssue("error", "billing_provider.tax_id", f"Invalid Tax ID: '{bp.tax_id}'. Must be 9 digits."))
    if not bp.taxonomy_code:
        issues.append(ValidationIssue("warning", "billing_provider.taxonomy_code", "Missing taxonomy code"))
    if bp.address:
        issues.extend(_validate_address(bp.address, "billing_provider.address"))

    # --- Subscriber (Loop 2010BA) ---
    sub = claim.subscriber
    if not sub.last_name:
        issues.append(ValidationIssue("error", "subscriber.last_name", "Missing subscriber last name"))
    if not sub.first_name:
        issues.append(ValidationIssue("error", "subscriber.first_name", "Missing subscriber first name"))
    if not sub.member_id:
        issues.append(ValidationIssue("error", "subscriber.member_id", "Missing member ID"))
    if not DATE_PATTERN.match(sub.date_of_birth or ""):
        issues.append(ValidationIssue("error", "subscriber.date_of_birth", f"Invalid DOB format: '{sub.date_of_birth}'. Must be CCYYMMDD."))
    if sub.gender not in VALID_GENDERS:
        issues.append(ValidationIssue("error", "subscriber.gender", f"Invalid gender: '{sub.gender}'. Must be M, F, or U."))
    if sub.address:
        issues.extend(_validate_address(sub.address, "subscriber.address"))

    # --- Payer (Loop 2010BB) ---
    if not claim.payer.name:
        issues.append(ValidationIssue("error", "payer.name", "Missing payer name"))
    if not claim.payer.payer_id:
        issues.append(ValidationIssue("error", "payer.payer_id", "Missing payer ID"))

    # --- Rendering Provider (Loop 2310B) ---
    if claim.rendering_provider:
        rp = claim.rendering_provider
        if not NPI_PATTERN.match(rp.npi or ""):
            issues.append(ValidationIssue("error", "rendering_provider.npi", f"Invalid rendering provider NPI: '{rp.npi}'."))

    # --- Diagnosis Codes (HI segment) ---
    if not claim.diagnosis_codes:
        issues.append(ValidationIssue("error", "diagnosis_codes", "At least one diagnosis code is required"))
    elif len(claim.diagnosis_codes) > 12:
        issues.append(ValidationIssue("error", "diagnosis_codes", f"Maximum 12 diagnosis codes allowed, got {len(claim.diagnosis_codes)}"))
    for i, dx in enumerate(claim.diagnosis_codes):
        if not ICD10_PATTERN.match(dx.code or ""):
            issues.append(ValidationIssue("error", f"diagnosis_codes[{i}]", f"Invalid ICD-10-CM code: '{dx.code}'."))

    # --- Service Lines (Loop 2400) ---
    if not claim.service_lines:
        issues.append(ValidationIssue("error", "service_lines", "At least one service line is required"))

    computed_total = 0.0
    now_str = datetime.now(timezone.utc).strftime("%Y%m%d")

    for i, sl in enumerate(claim.service_lines):
        prefix = f"service_lines[{i}]"

        # Procedure code
        pc = sl.procedure_code or ""
        if not (CPT_PATTERN.match(pc) or HCPCS_PATTERN.match(pc)):
            issues.append(ValidationIssue("error", f"{prefix}.procedure_code", f"Invalid procedure code: '{pc}'. Must be 5-digit CPT or HCPCS."))

        # Charge
        if sl.charge_amount <= 0:
            issues.append(ValidationIssue("error", f"{prefix}.charge_amount", "Charge amount must be greater than zero"))

        # Units
        if sl.units <= 0:
            issues.append(ValidationIssue("error", f"{prefix}.units", "Units must be greater than zero"))

        # Date of service
        if not DATE_PATTERN.match(sl.date_of_service or ""):
            issues.append(ValidationIssue("error", f"{prefix}.date_of_service", f"Invalid date format: '{sl.date_of_service}'. Must be CCYYMMDD."))
        elif sl.date_of_service > now_str:
            issues.append(ValidationIssue("error", f"{prefix}.date_of_service", "Service date cannot be in the future"))

        # Place of service
        if not POS_PATTERN.match(sl.place_of_service or ""):
            issues.append(ValidationIssue("error", f"{prefix}.place_of_service", f"Invalid place of service: '{sl.place_of_service}'. Must be 2 digits."))

        # Modifiers
        for j, mod in enumerate(sl.modifiers):
            if not MODIFIER_PATTERN.match(mod or ""):
                issues.append(ValidationIssue("error", f"{prefix}.modifiers[{j}]", f"Invalid modifier: '{mod}'."))
        if len(sl.modifiers) > 4:
            issues.append(ValidationIssue("error", f"{prefix}.modifiers", "Maximum 4 modifiers per service line"))

        # Diagnosis pointers
        for ptr in sl.diagnosis_pointers:
            if ptr < 1 or ptr > len(claim.diagnosis_codes):
                issues.append(ValidationIssue("error", f"{prefix}.diagnosis_pointers", f"Diagnosis pointer {ptr} out of range (1-{len(claim.diagnosis_codes)})"))

        computed_total += sl.charge_amount

    # Total charge consistency
    if claim.total_charge > 0 and abs(claim.total_charge - computed_total) > 0.01:
        issues.append(ValidationIssue("warning", "total_charge", f"Total charge ({claim.total_charge}) does not match sum of line charges ({computed_total:.2f})"))

    return issues


def _validate_address(addr: Address, prefix: str) -> list[ValidationIssue]:
    """Validate address fields."""
    issues = []
    if not addr.street:
        issues.append(ValidationIssue("warning", f"{prefix}.street", "Missing street address"))
    if not addr.city:
        issues.append(ValidationIssue("warning", f"{prefix}.city", "Missing city"))
    if addr.state and not STATE_PATTERN.match(addr.state):
        issues.append(ValidationIssue("error", f"{prefix}.state", f"Invalid state code: '{addr.state}'. Must be 2-letter abbreviation."))
    if addr.zip_code and not ZIP_PATTERN.match(addr.zip_code):
        issues.append(ValidationIssue("error", f"{prefix}.zip_code", f"Invalid ZIP code: '{addr.zip_code}'."))
    return issues


# ---------------------------------------------------------------------------
# EDI 837P JSON Assembly
# ---------------------------------------------------------------------------

def assemble_837p(claim: ClaimData) -> dict:
    """
    Assemble a structured EDI 837P JSON representation from validated claim data.

    This produces a JSON structure that mirrors the EDI 837P loop/segment
    hierarchy, suitable for downstream EDI translation (e.g., via B2B Data
    Interchange).

    Args:
        claim: Validated ClaimData

    Returns:
        EDI 837P JSON structure
    """
    total = claim.total_charge if claim.total_charge > 0 else sum(sl.charge_amount for sl in claim.service_lines)

    # Loop 2010AA — Billing Provider
    billing_provider = {
        "name": claim.billing_provider.name,
        "npi": claim.billing_provider.npi,
        "tax_id": claim.billing_provider.tax_id,
        "taxonomy_code": claim.billing_provider.taxonomy_code,
    }
    if claim.billing_provider.address:
        billing_provider["address"] = _format_address(claim.billing_provider.address)
    if claim.billing_provider.contact_phone:
        billing_provider["contact_phone"] = claim.billing_provider.contact_phone

    # Loop 2010BA — Subscriber
    subscriber = {
        "last_name": claim.subscriber.last_name,
        "first_name": claim.subscriber.first_name,
        "member_id": claim.subscriber.member_id,
        "date_of_birth": claim.subscriber.date_of_birth,
        "gender": claim.subscriber.gender,
        "group_number": claim.subscriber.group_number,
        "relationship_code": claim.subscriber.relationship_code,
    }
    if claim.subscriber.address:
        subscriber["address"] = _format_address(claim.subscriber.address)

    # Loop 2010BB — Payer
    payer = {
        "name": claim.payer.name,
        "payer_id": claim.payer.payer_id,
    }
    if claim.payer.address:
        payer["address"] = _format_address(claim.payer.address)

    # HI segment — Diagnosis codes
    diagnoses = []
    for i, dx in enumerate(claim.diagnosis_codes):
        diagnoses.append({
            "sequence": i + 1,
            "code": dx.code,
            "code_type": "ABK" if i == 0 else "ABF",  # ABK = principal, ABF = additional
            "description": dx.description,
        })

    # Loop 2400 — Service lines
    service_lines = []
    for i, sl in enumerate(claim.service_lines):
        line = {
            "line_number": i + 1,
            "procedure_code": sl.procedure_code,
            "charge_amount": round(sl.charge_amount, 2),
            "units": sl.units,
            "date_of_service": sl.date_of_service,
            "place_of_service": sl.place_of_service,
            "diagnosis_pointers": sl.diagnosis_pointers,
        }
        if sl.modifiers:
            line["modifiers"] = sl.modifiers
        if sl.description:
            line["description"] = sl.description
        service_lines.append(line)

    # Assemble full 837P structure
    edi_837p: dict = {
        "transaction_type": "837P",
        "claim_id": claim.claim_id,
        "total_charge_amount": round(total, 2),
        "billing_provider": billing_provider,
        "subscriber": subscriber,
        "payer": payer,
        "diagnosis_codes": diagnoses,
        "service_lines": service_lines,
    }

    # Conditional segments
    if claim.rendering_provider:
        rp = claim.rendering_provider
        edi_837p["rendering_provider"] = {
            "last_name": rp.last_name,
            "first_name": rp.first_name,
            "npi": rp.npi,
            "taxonomy_code": rp.taxonomy_code,
        }

    if claim.prior_auth_number:
        edi_837p["prior_authorization_number"] = claim.prior_auth_number

    if claim.referral_number:
        edi_837p["referral_number"] = claim.referral_number

    if claim.facility_npi:
        edi_837p["service_facility"] = {
            "npi": claim.facility_npi,
            "name": claim.facility_name,
        }

    return edi_837p


def _format_address(addr: Address) -> dict:
    return {
        "street": addr.street,
        "city": addr.city,
        "state": addr.state,
        "zip_code": addr.zip_code,
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def validate_and_assemble(claim: ClaimData) -> dict:
    """
    Validate claim data and assemble EDI 837P if valid.

    This is the main entry point used by the agent tool.

    Returns:
        dict with 'valid', 'issues', and 'edi_837p' (if valid) keys.
    """
    issues = validate_claim(claim)
    errors = [i for i in issues if i.severity == "error"]

    result = {
        "valid": len(errors) == 0,
        "error_count": len(errors),
        "warning_count": len(issues) - len(errors),
        "issues": [{"severity": i.severity, "field": i.field, "message": i.message} for i in issues],
        "edi_837p": None,
    }

    if not errors:
        result["edi_837p"] = assemble_837p(claim)

    return result
