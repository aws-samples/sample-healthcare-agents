# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Golden set for claims-submission-agent evaluation.

Each item contains:
  - input: assembled claim JSON + payor info
  - expected_output: submission status, acknowledgment handling

NOTE: Expected outputs require EDI/B2B SME validation before baseline.
"""

GOLDEN_SET = [

    # ── SUCCESSFUL SUBMISSIONS ────────────────────────────────────────────────

    {
        "id": "cs_001",
        "category": "successful_submission",
        "input": (
            "Submit the following assembled EDI 837P claim via B2B Data Interchange:\n"
            "Claim ID: CLM-2026-001\n"
            "Payor: UnitedHealthcare (Payer ID 87726)\n"
            "Total Charge: $150.00\n"
            "The claim has been validated and assembled. Please submit and track status."
        ),
        "expected_output": {
            "submission_initiated": True,
            "b2b_invocation_correct": True,
            "status_tracked": True,
            "key_findings": ["submitted", "B2B Data Interchange", "tracking"],
            "must_not_contain": ["error", "failed"],
        },
    },
    {
        "id": "cs_002",
        "category": "successful_submission",
        "input": (
            "Submit EDI 837P claim via B2B Data Interchange:\n"
            "Claim ID: CLM-2026-002\n"
            "Payor: Aetna (Payer ID 60054)\n"
            "Total Charge: $5300.00\n"
            "Prior Auth: AUTH-2026-789\n"
            "Submit and retrieve any acknowledgments."
        ),
        "expected_output": {
            "submission_initiated": True,
            "b2b_invocation_correct": True,
            "status_tracked": True,
            "key_findings": ["submitted", "acknowledgment check", "AUTH-2026-789"],
            "must_not_contain": [],
        },
    },
    {
        "id": "cs_003",
        "category": "successful_submission",
        "input": (
            "Submit EDI 837P claim via B2B Data Interchange:\n"
            "Claim ID: CLM-2026-003\n"
            "Payor: Medicare (Payer ID CMS)\n"
            "Total Charge: $200.00\n"
            "Submit, check transformation job status, and retrieve 997 acknowledgment."
        ),
        "expected_output": {
            "submission_initiated": True,
            "b2b_invocation_correct": True,
            "status_tracked": True,
            "acknowledgment_checked": True,
            "key_findings": ["submitted", "transformation job", "997", "Medicare"],
            "must_not_contain": [],
        },
    },

    # ── REJECTION SCENARIOS ───────────────────────────────────────────────────

    {
        "id": "cs_004",
        "category": "rejection",
        "input": (
            "Submit EDI 837P claim via B2B Data Interchange:\n"
            "Claim ID: CLM-2026-004\n"
            "Payor: Cigna (Payer ID 62308)\n"
            "Total Charge: $1200.00\n"
            "Note: The 999 acknowledgment indicates rejection — Implementation Acknowledgment "
            "shows error code AK4 (data element error in segment). Report the rejection details."
        ),
        "expected_output": {
            "submission_initiated": True,
            "b2b_invocation_correct": True,
            "rejection_identified": True,
            "rejection_details_reported": True,
            "key_findings": ["999", "rejected", "AK4", "data element error"],
            "must_not_contain": ["accepted", "successful"],
        },
    },
    {
        "id": "cs_005",
        "category": "rejection",
        "input": (
            "Submit EDI 837P claim via B2B Data Interchange:\n"
            "Claim ID: CLM-2026-005\n"
            "Payor: BCBS (Payer ID 00590)\n"
            "Total Charge: $3000.00\n"
            "Note: The 997 functional acknowledgment shows AK9 status R (rejected). "
            "Error: AK3 segment error in CLM segment. Report findings."
        ),
        "expected_output": {
            "submission_initiated": True,
            "b2b_invocation_correct": True,
            "rejection_identified": True,
            "rejection_details_reported": True,
            "key_findings": ["997", "rejected", "AK9", "CLM segment error"],
            "must_not_contain": ["accepted"],
        },
    },

    # ── TRANSFORMATION JOB FAILURES ───────────────────────────────────────────

    {
        "id": "cs_006",
        "category": "job_failure",
        "input": (
            "Submit EDI 837P claim via B2B Data Interchange:\n"
            "Claim ID: CLM-2026-006\n"
            "Payor: Humana (Payer ID 61101)\n"
            "Total Charge: $500.00\n"
            "Note: After submission, the B2B transformation job status returns FAILED. "
            "Report the failure and recommend next steps."
        ),
        "expected_output": {
            "submission_initiated": True,
            "b2b_invocation_correct": True,
            "failure_identified": True,
            "next_steps_provided": True,
            "key_findings": ["transformation job", "FAILED", "next steps", "retry or investigate"],
            "must_not_contain": ["successful", "accepted"],
        },
    },
    {
        "id": "cs_007",
        "category": "job_failure",
        "input": (
            "Check the status of a previously submitted claim:\n"
            "Claim ID: CLM-2026-007\n"
            "Submission was initiated 30 minutes ago but no acknowledgment has been received. "
            "Check transformation job status and report findings."
        ),
        "expected_output": {
            "submission_initiated": False,
            "status_tracked": True,
            "timeout_handled": True,
            "key_findings": ["status check", "no acknowledgment", "pending or delayed"],
            "must_not_contain": [],
        },
    },
]
