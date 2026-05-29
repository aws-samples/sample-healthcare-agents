# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Golden set for claims-assembly-agent evaluation.

Each item contains:
  - input: claim data elements (patient, provider, diagnosis, procedure, payor)
  - expected_output: verified ground truth
    - edi_837p_valid: whether output should be a valid EDI 837P structure
    - hipaa_5010_compliant: whether it passes HIPAA validation
    - all_required_fields_present: no missing required fields
    - validation_errors: list of expected validation errors (for invalid claims)
    - key_findings: facts that MUST appear
    - must_not_contain: hallucination check

Reference: HIPAA 5010 837P Implementation Guide, NUCC taxonomy codes.
NOTE: Expected outputs require billing SME validation before baseline.
"""

GOLDEN_SET = [

    # ── COMPLETE VALID CLAIMS ─────────────────────────────────────────────────

    {
        "id": "ca_001",
        "category": "valid_complete",
        "input": (
            "Assemble an EDI 837P claim with the following data:\n"
            "Claim ID: CLM-2026-001\n"
            "Billing Provider: Coastal Medical Group, NPI 1234567890, Tax ID 123456789, "
            "Taxonomy 207Q00000X, 100 Main St, San Diego CA 92101, Phone 6195551234\n"
            "Subscriber: John Smith, Member ID UHC-12345, DOB 19580315, Gender M, Group GRP-001\n"
            "Payer: UnitedHealthcare, Payer ID 87726\n"
            "Diagnosis: M54.5 (Low back pain)\n"
            "Service Line: CPT 99213, $150.00, 1 unit, DOS 20260415, POS 11, Dx pointer 1\n"
            "Total Charge: $150.00"
        ),
        "expected_output": {
            "edi_837p_valid": True,
            "hipaa_5010_compliant": True,
            "all_required_fields_present": True,
            "validation_errors": [],
            "key_findings": ["1234567890", "99213", "M54.5", "150.00", "87726"],
            "must_not_contain": [],
        },
    },
    {
        "id": "ca_002",
        "category": "valid_complete",
        "input": (
            "Assemble an EDI 837P claim:\n"
            "Claim ID: CLM-2026-002\n"
            "Billing Provider: Pacific Surgery Center, NPI 9876543210, Tax ID 987654321, "
            "Taxonomy 261QA1903X, 200 Harbor Dr, Los Angeles CA 90012\n"
            "Subscriber: Maria Garcia, Member ID AET-67890, DOB 19720820, Gender F, Group GRP-500\n"
            "Payer: Aetna, Payer ID 60054\n"
            "Diagnosis: K80.00 (Calculus of gallbladder with acute cholecystitis)\n"
            "Service Line 1: CPT 47562, $4500.00, 1 unit, DOS 20260410, POS 22, Dx pointer 1\n"
            "Service Line 2: CPT 74177, $800.00, 1 unit, DOS 20260410, POS 22, Dx pointer 1\n"
            "Rendering Provider: Dr. James Lee, NPI 5678901234, Taxonomy 208600000X\n"
            "Prior Auth: AUTH-2026-789\n"
            "Total Charge: $5300.00"
        ),
        "expected_output": {
            "edi_837p_valid": True,
            "hipaa_5010_compliant": True,
            "all_required_fields_present": True,
            "validation_errors": [],
            "key_findings": ["47562", "74177", "K80.00", "5300.00", "AUTH-2026-789", "two service lines"],
            "must_not_contain": [],
        },
    },
    {
        "id": "ca_003",
        "category": "valid_complete",
        "input": (
            "Assemble an EDI 837P claim:\n"
            "Claim ID: CLM-2026-003\n"
            "Billing Provider: Desert Family Medicine, NPI 1112223334, Tax ID 111222333, "
            "Taxonomy 208D00000X, 50 Cactus Rd, Phoenix AZ 85001\n"
            "Subscriber: Robert Johnson, Member ID BCBS-11111, DOB 19450101, Gender M\n"
            "Payer: BlueCross BlueShield of Arizona, Payer ID 00590\n"
            "Diagnosis 1: E11.22 (Type 2 diabetes with diabetic CKD)\n"
            "Diagnosis 2: N18.3 (CKD stage 3)\n"
            "Diagnosis 3: I10 (Essential hypertension)\n"
            "Service Line: CPT 99214, $200.00, 1 unit, DOS 20260401, POS 11, Dx pointers 1,2,3\n"
            "Total Charge: $200.00"
        ),
        "expected_output": {
            "edi_837p_valid": True,
            "hipaa_5010_compliant": True,
            "all_required_fields_present": True,
            "validation_errors": [],
            "key_findings": ["E11.22", "N18.3", "I10", "99214", "three diagnosis codes"],
            "must_not_contain": [],
        },
    },
    {
        "id": "ca_004",
        "category": "valid_complete",
        "input": (
            "Assemble an EDI 837P claim:\n"
            "Claim ID: CLM-2026-004\n"
            "Billing Provider: Sunrise Radiology, NPI 4445556667, Tax ID 444555666, "
            "Taxonomy 2085R0202X, 300 Imaging Way, Denver CO 80202\n"
            "Subscriber: Sarah Williams, Member ID MED-A1234, DOB 19500612, Gender F\n"
            "Payer: Medicare, Payer ID CMS\n"
            "Diagnosis: M17.11 (Primary osteoarthritis, right knee)\n"
            "Service Line: CPT 73562, $250.00, 1 unit, DOS 20260420, POS 11, Dx pointer 1, "
            "Modifier TC\n"
            "Total Charge: $250.00"
        ),
        "expected_output": {
            "edi_837p_valid": True,
            "hipaa_5010_compliant": True,
            "all_required_fields_present": True,
            "validation_errors": [],
            "key_findings": ["M17.11", "73562", "TC", "Medicare", "modifier"],
            "must_not_contain": [],
        },
    },

    # ── MISSING REQUIRED FIELDS (should flag errors) ──────────────────────────

    {
        "id": "ca_005",
        "category": "missing_fields",
        "input": (
            "Assemble an EDI 837P claim:\n"
            "Claim ID: CLM-2026-005\n"
            "Billing Provider: Test Clinic, NPI (missing), Tax ID 123456789\n"
            "Subscriber: Jane Doe, Member ID UHC-99999, DOB 19800101, Gender F\n"
            "Payer: UnitedHealthcare, Payer ID 87726\n"
            "Diagnosis: J06.9 (Acute upper respiratory infection)\n"
            "Service Line: CPT 99212, $100.00, 1 unit, DOS 20260415, POS 11, Dx pointer 1\n"
            "Total Charge: $100.00"
        ),
        "expected_output": {
            "edi_837p_valid": False,
            "hipaa_5010_compliant": False,
            "all_required_fields_present": False,
            "validation_errors": ["Missing or invalid NPI for billing provider"],
            "key_findings": ["NPI", "invalid", "error"],
            "must_not_contain": [],
        },
    },
    {
        "id": "ca_006",
        "category": "missing_fields",
        "input": (
            "Assemble an EDI 837P claim:\n"
            "Claim ID: CLM-2026-006\n"
            "Billing Provider: Valley Health, NPI 1234567890, Tax ID 123456789\n"
            "Subscriber: Tom Brown, Member ID AET-55555, DOB 19900515, Gender M\n"
            "Payer: Aetna, Payer ID 60054\n"
            "Diagnosis: (none provided)\n"
            "Service Line: CPT 99213, $150.00, 1 unit, DOS 20260415, POS 11\n"
            "Total Charge: $150.00"
        ),
        "expected_output": {
            "edi_837p_valid": False,
            "hipaa_5010_compliant": False,
            "all_required_fields_present": False,
            "validation_errors": ["At least one diagnosis code is required"],
            "key_findings": ["diagnosis", "required", "missing"],
            "must_not_contain": [],
        },
    },
    {
        "id": "ca_007",
        "category": "missing_fields",
        "input": (
            "Assemble an EDI 837P claim:\n"
            "Claim ID: CLM-2026-007\n"
            "Billing Provider: Metro Health, NPI 1234567890, Tax ID 123456789\n"
            "Subscriber: (name missing), Member ID (missing), DOB (missing), Gender M\n"
            "Payer: Cigna, Payer ID 62308\n"
            "Diagnosis: R10.9 (Unspecified abdominal pain)\n"
            "Service Line: CPT 99213, $150.00, 1 unit, DOS 20260415, POS 11, Dx pointer 1\n"
            "Total Charge: $150.00"
        ),
        "expected_output": {
            "edi_837p_valid": False,
            "hipaa_5010_compliant": False,
            "all_required_fields_present": False,
            "validation_errors": [
                "Missing subscriber last name",
                "Missing subscriber first name",
                "Missing member ID",
                "Invalid DOB format",
            ],
            "key_findings": ["subscriber", "missing", "multiple errors"],
            "must_not_contain": [],
        },
    },

    # ── PAYER-SPECIFIC RULE VIOLATIONS ────────────────────────────────────────

    {
        "id": "ca_008",
        "category": "payer_rule_violation",
        "input": (
            "Assemble an EDI 837P claim:\n"
            "Claim ID: CLM-2026-008\n"
            "Billing Provider: Coastal Medical, NPI 1234567890, Tax ID 123456789, "
            "Taxonomy 207Q00000X\n"
            "Subscriber: Alice Chen, Member ID UHC-77777, DOB 19650301, Gender F\n"
            "Payer: UnitedHealthcare, Payer ID 87726\n"
            "Diagnosis: M54.5 (Low back pain)\n"
            "Service Line: CPT 72148, $1200.00, 1 unit, DOS 20260415, POS 11, Dx pointer 1\n"
            "Note: This MRI requires prior authorization but no auth number is provided.\n"
            "Total Charge: $1200.00"
        ),
        "expected_output": {
            "edi_837p_valid": True,
            "hipaa_5010_compliant": True,
            "all_required_fields_present": True,
            "validation_errors": ["Prior authorization required for CPT 72148 with UnitedHealthcare but not provided"],
            "key_findings": ["prior authorization", "72148", "warning"],
            "must_not_contain": [],
        },
    },
    {
        "id": "ca_009",
        "category": "payer_rule_violation",
        "input": (
            "Assemble an EDI 837P claim:\n"
            "Claim ID: CLM-2026-009\n"
            "Billing Provider: City Orthopedics, NPI 1234567890, Tax ID 123456789\n"
            "Subscriber: David Park, Member ID MED-B5678, DOB 19480720, Gender M\n"
            "Payer: Medicare, Payer ID CMS\n"
            "Diagnosis: M17.11 (Primary osteoarthritis, right knee)\n"
            "Service Line: CPT 27447, $25000.00, 1 unit, DOS 20260410, POS 21, Dx pointer 1\n"
            "Rendering Provider: Dr. Smith, NPI 999888777\n"
            "Total Charge: $25000.00"
        ),
        "expected_output": {
            "edi_837p_valid": False,
            "hipaa_5010_compliant": False,
            "all_required_fields_present": False,
            "validation_errors": ["Invalid rendering provider NPI: must be 10 digits"],
            "key_findings": ["NPI", "invalid", "rendering provider", "9 digits"],
            "must_not_contain": [],
        },
    },

    # ── HIPAA FORMAT EDGE CASES ───────────────────────────────────────────────

    {
        "id": "ca_010",
        "category": "format_edge_case",
        "input": (
            "Assemble an EDI 837P claim:\n"
            "Claim ID: CLM-2026-010\n"
            "Billing Provider: National Health, NPI 1234567890, Tax ID 12-3456789, "
            "Taxonomy 207Q00000X\n"
            "Subscriber: Lisa Wong, Member ID BCBS-33333, DOB 03/15/1975, Gender F\n"
            "Payer: BCBS, Payer ID 00590\n"
            "Diagnosis: J44.1 (COPD with acute exacerbation)\n"
            "Service Line: CPT 99214, $200.00, 1 unit, DOS 04/15/2026, POS 11, Dx pointer 1\n"
            "Total Charge: $200.00"
        ),
        "expected_output": {
            "edi_837p_valid": True,
            "hipaa_5010_compliant": True,
            "all_required_fields_present": True,
            "validation_errors": [],
            "key_findings": ["date format conversion", "CCYYMMDD", "tax ID normalization"],
            "must_not_contain": [],
        },
    },
    {
        "id": "ca_011",
        "category": "format_edge_case",
        "input": (
            "Assemble an EDI 837P claim:\n"
            "Claim ID: CLM-2026-011\n"
            "Billing Provider: Summit Health, NPI 1234567890, Tax ID 123456789\n"
            "Subscriber: Mark Taylor, Member ID AET-44444, DOB 19850101, Gender M\n"
            "Payer: Aetna, Payer ID 60054\n"
            "Diagnosis 1 through 13: M54.5, M54.2, M54.30, M54.31, M54.32, M54.40, M54.41, "
            "M54.42, M47.812, M47.816, M51.16, M51.17, G89.29\n"
            "Service Line: CPT 99215, $300.00, 1 unit, DOS 20260415, POS 11, Dx pointer 1\n"
            "Total Charge: $300.00"
        ),
        "expected_output": {
            "edi_837p_valid": False,
            "hipaa_5010_compliant": False,
            "all_required_fields_present": True,
            "validation_errors": ["Maximum 12 diagnosis codes allowed, got 13"],
            "key_findings": ["13 diagnosis codes", "maximum 12", "error"],
            "must_not_contain": [],
        },
    },

    # ── MULTI-LINE CLAIMS ─────────────────────────────────────────────────────

    {
        "id": "ca_012",
        "category": "multi_line",
        "input": (
            "Assemble an EDI 837P claim:\n"
            "Claim ID: CLM-2026-012\n"
            "Billing Provider: Premier Medical, NPI 1234567890, Tax ID 123456789, "
            "Taxonomy 207Q00000X\n"
            "Subscriber: Karen White, Member ID UHC-88888, DOB 19600225, Gender F\n"
            "Payer: UnitedHealthcare, Payer ID 87726\n"
            "Diagnosis 1: E11.22 (Type 2 diabetes with CKD)\n"
            "Diagnosis 2: N18.3 (CKD stage 3)\n"
            "Diagnosis 3: I10 (Hypertension)\n"
            "Service Line 1: CPT 99214, $200.00, 1 unit, DOS 20260415, POS 11, Dx pointers 1,2,3\n"
            "Service Line 2: CPT 80053, $35.00, 1 unit, DOS 20260415, POS 11, Dx pointers 1,2\n"
            "Service Line 3: CPT 83036, $25.00, 1 unit, DOS 20260415, POS 11, Dx pointer 1\n"
            "Service Line 4: CPT 81001, $15.00, 1 unit, DOS 20260415, POS 11, Dx pointer 2\n"
            "Total Charge: $275.00"
        ),
        "expected_output": {
            "edi_837p_valid": True,
            "hipaa_5010_compliant": True,
            "all_required_fields_present": True,
            "validation_errors": [],
            "key_findings": ["4 service lines", "3 diagnosis codes", "275.00", "diagnosis pointers correct"],
            "must_not_contain": [],
        },
    },
]
