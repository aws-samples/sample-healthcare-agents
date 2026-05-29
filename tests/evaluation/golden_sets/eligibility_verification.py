# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Golden set for eligibility-verification-agent evaluation.

Each item contains:
  - input: patient_id, service_type, date_of_service
  - expected_output: coverage status, plan details, cost sharing, auth requirements

NOTE: Expected outputs require benefits SME validation before baseline.
"""

GOLDEN_SET = [

    # ── ACTIVE COVERAGE ───────────────────────────────────────────────────────

    {
        "id": "ev_001",
        "category": "active_coverage",
        "input": (
            "Verify insurance eligibility for Patient/smart-1032702. "
            "Service: MRI lumbar spine (CPT 72148). Date of service: 2026-04-15. "
            "Payor: UnitedHealthcare."
        ),
        "expected_output": {
            "coverage_active": True,
            "plan_type": "PPO",
            "copay_identified": True,
            "deductible_checked": True,
            "prior_auth_required": True,
            "key_findings": ["active coverage", "PPO", "prior auth required for MRI"],
            "must_not_contain": ["expired", "terminated"],
        },
    },
    {
        "id": "ev_002",
        "category": "active_coverage",
        "input": (
            "Verify insurance eligibility for Patient/smart-1032702. "
            "Service: Office visit (CPT 99213). Date of service: 2026-04-15. "
            "Payor: Aetna."
        ),
        "expected_output": {
            "coverage_active": True,
            "plan_type": "HMO",
            "copay_identified": True,
            "deductible_checked": True,
            "prior_auth_required": False,
            "key_findings": ["active coverage", "HMO", "no prior auth for office visit"],
            "must_not_contain": ["expired", "not covered"],
        },
    },
    {
        "id": "ev_003",
        "category": "active_coverage",
        "input": (
            "Verify insurance eligibility for Patient/smart-1032702. "
            "Service: Total knee arthroplasty (CPT 27447). Date of service: 2026-05-01. "
            "Payor: Medicare Part A."
        ),
        "expected_output": {
            "coverage_active": True,
            "plan_type": "Medicare",
            "copay_identified": True,
            "deductible_checked": True,
            "prior_auth_required": True,
            "key_findings": ["active Medicare", "Part A", "inpatient", "prior auth required"],
            "must_not_contain": ["terminated"],
        },
    },
    {
        "id": "ev_004",
        "category": "active_coverage",
        "input": (
            "Verify insurance eligibility for Patient/smart-1032702. "
            "Service: Preventive colonoscopy (CPT 45378). Date of service: 2026-04-20. "
            "Payor: BlueCross BlueShield."
        ),
        "expected_output": {
            "coverage_active": True,
            "plan_type": "PPO",
            "copay_identified": True,
            "deductible_checked": True,
            "prior_auth_required": False,
            "key_findings": ["active coverage", "preventive", "no prior auth", "covered benefit"],
            "must_not_contain": ["not covered"],
        },
    },

    # ── EXPIRED / TERMINATED COVERAGE ─────────────────────────────────────────

    {
        "id": "ev_005",
        "category": "expired_coverage",
        "input": (
            "Verify insurance eligibility for Patient/smart-1032702. "
            "Service: CT abdomen (CPT 74177). Date of service: 2026-04-15. "
            "Payor: Cigna. Note: Patient's coverage terminated 2026-03-31."
        ),
        "expected_output": {
            "coverage_active": False,
            "plan_type": "N/A",
            "copay_identified": False,
            "deductible_checked": False,
            "prior_auth_required": False,
            "key_findings": ["coverage terminated", "not active", "2026-03-31"],
            "must_not_contain": ["active coverage", "covered"],
        },
    },
    {
        "id": "ev_006",
        "category": "expired_coverage",
        "input": (
            "Verify insurance eligibility for Patient/smart-1032702. "
            "Service: Physical therapy evaluation (CPT 97161). Date of service: 2026-04-15. "
            "Payor: Humana. Note: Patient's plan effective dates are 2025-01-01 to 2025-12-31."
        ),
        "expected_output": {
            "coverage_active": False,
            "plan_type": "N/A",
            "copay_identified": False,
            "deductible_checked": False,
            "prior_auth_required": False,
            "key_findings": ["expired", "effective dates", "2025-12-31", "not active for DOS"],
            "must_not_contain": ["active"],
        },
    },

    # ── SERVICE EXCLUSIONS ────────────────────────────────────────────────────

    {
        "id": "ev_007",
        "category": "service_exclusion",
        "input": (
            "Verify insurance eligibility for Patient/smart-1032702. "
            "Service: Cosmetic rhinoplasty (CPT 30400). Date of service: 2026-04-15. "
            "Payor: UnitedHealthcare."
        ),
        "expected_output": {
            "coverage_active": True,
            "plan_type": "PPO",
            "copay_identified": False,
            "deductible_checked": False,
            "prior_auth_required": False,
            "key_findings": ["active coverage", "cosmetic procedure", "not a covered benefit", "exclusion"],
            "must_not_contain": [],
        },
    },
    {
        "id": "ev_008",
        "category": "service_exclusion",
        "input": (
            "Verify insurance eligibility for Patient/smart-1032702. "
            "Service: Experimental gene therapy (CPT 0537T). Date of service: 2026-04-15. "
            "Payor: Aetna."
        ),
        "expected_output": {
            "coverage_active": True,
            "plan_type": "HMO",
            "copay_identified": False,
            "deductible_checked": False,
            "prior_auth_required": False,
            "key_findings": ["active coverage", "experimental", "not covered", "exclusion"],
            "must_not_contain": [],
        },
    },

    # ── MEDICARE / MEDICAID EDGE CASES ────────────────────────────────────────

    {
        "id": "ev_009",
        "category": "medicare_medicaid",
        "input": (
            "Verify insurance eligibility for Patient/smart-1032702. "
            "Service: Diabetic eye exam (CPT 92014). Date of service: 2026-04-15. "
            "Payor: Medicare Part B. Patient also has Medicaid as secondary."
        ),
        "expected_output": {
            "coverage_active": True,
            "plan_type": "Medicare",
            "copay_identified": True,
            "deductible_checked": True,
            "prior_auth_required": False,
            "key_findings": ["dual eligible", "Medicare primary", "Medicaid secondary", "covered"],
            "must_not_contain": ["not covered"],
        },
    },
    {
        "id": "ev_010",
        "category": "medicare_medicaid",
        "input": (
            "Verify insurance eligibility for Patient/smart-1032702. "
            "Service: Home oxygen therapy (HCPCS E1390). Date of service: 2026-04-15. "
            "Payor: Medicare Part B."
        ),
        "expected_output": {
            "coverage_active": True,
            "plan_type": "Medicare",
            "copay_identified": True,
            "deductible_checked": True,
            "prior_auth_required": True,
            "key_findings": ["Medicare Part B", "DME", "prior auth required", "covered with conditions"],
            "must_not_contain": ["not covered"],
        },
    },
]
