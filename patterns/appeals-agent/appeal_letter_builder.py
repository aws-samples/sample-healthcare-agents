# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Appeal Letter Builder module for deterministic validation and assembly.

Validates that appeal letters contain all payer-required components before
saving. Pure-function module imported by the Appeals Agent.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class DenialInfo:
    """Denial details from the original claim."""

    claim_id: str
    denial_date: str
    denial_reason_code: str  # CARC code
    remark_codes: list[str] = field(default_factory=list)  # RARC codes
    payer_name: str = ""
    authorization_number: str = ""


@dataclass
class PatientInfo:
    """Patient demographics for the appeal."""

    name: str
    date_of_birth: str
    member_id: str


@dataclass
class ProviderInfo:
    """Provider information for the appeal."""

    name: str
    npi: str
    contact: str = ""


@dataclass
class AppealLetterComponents:
    """All required components of an appeal letter."""

    patient: PatientInfo
    provider: ProviderInfo
    denial: DenialInfo
    date_of_service: str
    clinical_rationale: str
    supporting_documents: list[str] = field(default_factory=list)
    requested_action: str = ""
    appeal_level: str = "First Level"


@dataclass
class ValidationIssue:
    """A validation problem found in the appeal letter."""

    severity: str  # "error" | "warning"
    field: str
    message: str


# Required components that must be present in every appeal letter
REQUIRED_FIELDS = [
    ("patient.name", "Patient name"),
    ("patient.date_of_birth", "Patient date of birth"),
    ("patient.member_id", "Patient member ID"),
    ("provider.name", "Provider name"),
    ("provider.npi", "Provider NPI"),
    ("denial.claim_id", "Claim ID"),
    ("denial.denial_date", "Denial date"),
    ("denial.denial_reason_code", "Denial reason code (CARC)"),
    ("denial.payer_name", "Payer name"),
    ("date_of_service", "Date of service"),
    ("clinical_rationale", "Clinical rationale"),
    ("requested_action", "Requested action"),
]

# NPI format: 10-digit number
NPI_PATTERN = re.compile(r"^\d{10}$")

# Known CARC code prefixes (non-exhaustive, for basic validation)
VALID_CARC_RANGE = range(0, 300)


def validate_components(components: AppealLetterComponents) -> list[ValidationIssue]:
    """
    Validate appeal letter components for completeness and correctness.

    Checks all required fields, format validation (NPI, dates), and
    warns about missing recommended elements.

    Returns:
        List of ValidationIssue objects. Empty list means valid.
    """
    issues: list[ValidationIssue] = []

    # Check required fields
    field_map = {
        "patient.name": components.patient.name,
        "patient.date_of_birth": components.patient.date_of_birth,
        "patient.member_id": components.patient.member_id,
        "provider.name": components.provider.name,
        "provider.npi": components.provider.npi,
        "denial.claim_id": components.denial.claim_id,
        "denial.denial_date": components.denial.denial_date,
        "denial.denial_reason_code": components.denial.denial_reason_code,
        "denial.payer_name": components.denial.payer_name,
        "date_of_service": components.date_of_service,
        "clinical_rationale": components.clinical_rationale,
        "requested_action": components.requested_action,
    }

    for field_path, display_name in REQUIRED_FIELDS:
        value = field_map.get(field_path, "")
        if not value or not value.strip():
            issues.append(ValidationIssue(
                severity="error",
                field=field_path,
                message=f"Missing required field: {display_name}",
            ))

    # NPI format validation
    if components.provider.npi and not NPI_PATTERN.match(components.provider.npi):
        issues.append(ValidationIssue(
            severity="error",
            field="provider.npi",
            message=f"Invalid NPI format: '{components.provider.npi}'. Must be 10 digits.",
        ))

    # CARC code validation
    carc = components.denial.denial_reason_code
    if carc:
        carc_num = re.sub(r"\D", "", carc)
        if not carc_num or int(carc_num) not in VALID_CARC_RANGE:
            issues.append(ValidationIssue(
                severity="warning",
                field="denial.denial_reason_code",
                message=f"Unrecognized CARC code: '{carc}'. Verify denial reason code.",
            ))

    # Clinical rationale minimum length
    if components.clinical_rationale and len(components.clinical_rationale.strip()) < 50:
        issues.append(ValidationIssue(
            severity="warning",
            field="clinical_rationale",
            message="Clinical rationale appears too brief. Include detailed medical necessity justification.",
        ))

    # Warn if no supporting documents listed
    if not components.supporting_documents:
        issues.append(ValidationIssue(
            severity="warning",
            field="supporting_documents",
            message="No supporting documents listed. Include clinical notes, lab results, or peer-reviewed literature.",
        ))

    return issues


def build_appeal_letter_html(
    components: AppealLetterComponents,
    letter_body: str,
) -> str:
    """
    Assemble a complete appeal letter in HTML with required header/footer structure.

    The letter_body (LLM-generated narrative) is wrapped in a compliant template
    that ensures all required identifiers and components are present regardless
    of what the LLM produces.

    Args:
        components: Validated appeal letter components
        letter_body: The LLM-generated appeal narrative

    Returns:
        Complete HTML appeal letter
    """
    today = datetime.now(timezone.utc).strftime("%B %d, %Y")

    supporting_docs_html = ""
    if components.supporting_documents:
        items = "".join(f"<li>{doc}</li>" for doc in components.supporting_documents)
        supporting_docs_html = f"""
        <h3>Supporting Documentation Enclosed</h3>
        <ol>{items}</ol>"""

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Appeal Letter — {components.denial.claim_id}</title>
<style>
  body {{ font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; color: #333; }}
  .header {{ margin-bottom: 30px; }}
  .reference-block {{ background: #f5f5f5; padding: 15px; border-left: 4px solid #0066cc; margin: 20px 0; }}
  .reference-block dt {{ font-weight: bold; }}
  .clinical-rationale {{ margin: 20px 0; }}
  .footer {{ margin-top: 40px; border-top: 1px solid #ccc; padding-top: 20px; }}
</style>
</head>
<body>

<div class="header">
  <p><strong>Date:</strong> {today}</p>
  <p><strong>To:</strong> {components.denial.payer_name} — Appeals Department</p>
  <p><strong>Re:</strong> {components.appeal_level} Appeal</p>
</div>

<div class="reference-block">
  <dl>
    <dt>Patient Name</dt><dd>{components.patient.name}</dd>
    <dt>Date of Birth</dt><dd>{components.patient.date_of_birth}</dd>
    <dt>Member ID</dt><dd>{components.patient.member_id}</dd>
    <dt>Claim ID</dt><dd>{components.denial.claim_id}</dd>
    <dt>Date of Service</dt><dd>{components.date_of_service}</dd>
    <dt>Denial Date</dt><dd>{components.denial.denial_date}</dd>
    <dt>Denial Reason (CARC)</dt><dd>{components.denial.denial_reason_code}</dd>
    <dt>Provider</dt><dd>{components.provider.name} (NPI: {components.provider.npi})</dd>
  </dl>
</div>

<div class="clinical-rationale">
{letter_body}
</div>

<p><strong>Requested Action:</strong> {components.requested_action}</p>

{supporting_docs_html}

<div class="footer">
  <p>Respectfully submitted,</p>
  <p><strong>{components.provider.name}</strong><br>
  NPI: {components.provider.npi}<br>
  {components.provider.contact}</p>
</div>

</body>
</html>"""


def validate_and_build(
    components: AppealLetterComponents,
    letter_body: str,
) -> dict:
    """
    Validate components and build the appeal letter if valid.

    This is the main entry point used by the agent tool.

    Returns:
        dict with 'valid', 'issues', and 'html' (if valid) keys.
    """
    issues = validate_components(components)
    errors = [i for i in issues if i.severity == "error"]

    result = {
        "valid": len(errors) == 0,
        "issues": [{"severity": i.severity, "field": i.field, "message": i.message} for i in issues],
        "html": None,
    }

    if not errors:
        result["html"] = build_appeal_letter_html(components, letter_body)

    return result
