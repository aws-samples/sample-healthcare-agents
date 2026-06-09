# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Golden set for appeals-agent evaluation.

Each item contains:
  - input: denial details (claim ID, denial code, procedure, payor, date)
  - expected_output: denial analysis, deadline, letter generation, evidence citation

Reference: CARC/RARC code sets, CMS appeal timelines, payer-specific filing rules.
NOTE: Expected outputs require appeals SME validation before baseline.
"""

GOLDEN_SET = [

    # ── MEDICAL NECESSITY DENIALS ─────────────────────────────────────────────

    {
        "id": "ap_001",
        "category": "medical_necessity",
        "input": (
            "Generate an appeal for a denied claim:\n"
            "Claim ID: CLM-2026-D001\n"
            "Denial Code: CO-50 (Medical necessity)\n"
            "RARC: N386 (Missing/incomplete/invalid initial treatment date)\n"
            "Procedure: CPT 72148 (MRI lumbar spine)\n"
            "Diagnosis: M54.5 (Low back pain)\n"
            "Payor: UnitedHealthcare\n"
            "Date of Denial: 2026-04-01\n"
            "Clinical Context: Patient has chronic low back pain with radiculopathy, "
            "failed 6 weeks PT and NSAIDs. Positive straight leg raise."
        ),
        "expected_output": {
            "denial_code_identified": True,
            "carc_rarc_lookup_correct": True,
            "filing_deadline_checked": True,
            "deadline_within_window": True,
            "appeal_letter_generated": True,
            "clinical_evidence_cited": True,
            "key_findings": ["CO-50", "medical necessity", "180 days", "conservative therapy failed"],
            "must_not_contain": [],
        },
    },
    {
        "id": "ap_002",
        "category": "medical_necessity",
        "input": (
            "Generate an appeal for a denied claim:\n"
            "Claim ID: CLM-2026-D002\n"
            "Denial Code: CO-50\n"
            "Procedure: CPT 27447 (Total knee arthroplasty)\n"
            "Diagnosis: M17.11 (Primary osteoarthritis, right knee)\n"
            "Payor: Aetna\n"
            "Date of Denial: 2026-03-15\n"
            "Clinical Context: 70-year-old with severe OA, KL grade IV, failed PT, "
            "injections x3, significant functional limitation."
        ),
        "expected_output": {
            "denial_code_identified": True,
            "carc_rarc_lookup_correct": True,
            "filing_deadline_checked": True,
            "deadline_within_window": True,
            "appeal_letter_generated": True,
            "clinical_evidence_cited": True,
            "key_findings": ["CO-50", "KL grade IV", "failed conservative", "functional limitation"],
            "must_not_contain": [],
        },
    },
    {
        "id": "ap_003",
        "category": "medical_necessity",
        "input": (
            "Generate an appeal for a denied claim:\n"
            "Claim ID: CLM-2026-D003\n"
            "Denial Code: CO-50\n"
            "Procedure: HCPCS J0585 (Botox injection)\n"
            "Diagnosis: G43.909 (Migraine, unspecified)\n"
            "Payor: BlueCross BlueShield\n"
            "Date of Denial: 2026-03-20\n"
            "Clinical Context: Chronic migraine, 20 headache days/month, failed topiramate, "
            "propranolol, amitriptyline, and erenumab."
        ),
        "expected_output": {
            "denial_code_identified": True,
            "carc_rarc_lookup_correct": True,
            "filing_deadline_checked": True,
            "deadline_within_window": True,
            "appeal_letter_generated": True,
            "clinical_evidence_cited": True,
            "key_findings": ["CO-50", "chronic migraine", "4 failed preventives", "20 headache days"],
            "must_not_contain": [],
        },
    },

    # ── AUTHORIZATION-RELATED DENIALS ─────────────────────────────────────────

    {
        "id": "ap_004",
        "category": "auth_denial",
        "input": (
            "Generate an appeal for a denied claim:\n"
            "Claim ID: CLM-2026-D004\n"
            "Denial Code: CO-197 (Precertification/authorization/notification absent)\n"
            "Procedure: CPT 74177 (CT abdomen pelvis with contrast)\n"
            "Diagnosis: R10.9 (Unspecified abdominal pain)\n"
            "Payor: UnitedHealthcare\n"
            "Date of Denial: 2026-04-05\n"
            "Clinical Context: Emergent presentation with acute abdominal pain, "
            "CT ordered from ED. Auth was not obtained due to emergent nature."
        ),
        "expected_output": {
            "denial_code_identified": True,
            "carc_rarc_lookup_correct": True,
            "filing_deadline_checked": True,
            "deadline_within_window": True,
            "appeal_letter_generated": True,
            "clinical_evidence_cited": True,
            "key_findings": ["CO-197", "no prior auth", "emergent", "retroactive auth"],
            "must_not_contain": [],
        },
    },
    {
        "id": "ap_005",
        "category": "auth_denial",
        "input": (
            "Generate an appeal for a denied claim:\n"
            "Claim ID: CLM-2026-D005\n"
            "Denial Code: CO-197\n"
            "Procedure: CPT 43239 (EGD with biopsy)\n"
            "Diagnosis: K21.0 (GERD with esophagitis)\n"
            "Payor: Cigna\n"
            "Date of Denial: 2026-03-28\n"
            "Clinical Context: Auth was obtained (AUTH-2026-100) but claim was submitted "
            "with wrong auth number. Correct auth on file."
        ),
        "expected_output": {
            "denial_code_identified": True,
            "carc_rarc_lookup_correct": True,
            "filing_deadline_checked": True,
            "deadline_within_window": True,
            "appeal_letter_generated": True,
            "clinical_evidence_cited": True,
            "key_findings": ["CO-197", "auth number mismatch", "correct auth on file", "AUTH-2026-100"],
            "must_not_contain": [],
        },
    },

    # ── CODING-RELATED DENIALS ────────────────────────────────────────────────

    {
        "id": "ap_006",
        "category": "coding_denial",
        "input": (
            "Generate an appeal for a denied claim:\n"
            "Claim ID: CLM-2026-D006\n"
            "Denial Code: CO-4 (Procedure code inconsistent with modifier or missing modifier)\n"
            "Procedure: CPT 99214 with modifier 25\n"
            "Diagnosis: E11.9 (Type 2 diabetes)\n"
            "Payor: Aetna\n"
            "Date of Denial: 2026-04-10\n"
            "Clinical Context: E&M visit with separate diabetic foot exam (CPT 11721) "
            "on same date. Modifier 25 applied to indicate separate E&M service."
        ),
        "expected_output": {
            "denial_code_identified": True,
            "carc_rarc_lookup_correct": True,
            "filing_deadline_checked": True,
            "deadline_within_window": True,
            "appeal_letter_generated": True,
            "clinical_evidence_cited": True,
            "key_findings": ["CO-4", "modifier 25", "separate E&M", "distinct service"],
            "must_not_contain": [],
        },
    },
    {
        "id": "ap_007",
        "category": "coding_denial",
        "input": (
            "Generate an appeal for a denied claim:\n"
            "Claim ID: CLM-2026-D007\n"
            "Denial Code: CO-97 (Payment adjusted — bundled procedure)\n"
            "Procedure: CPT 36415 (Venipuncture) billed separately from CPT 80053 (CMP)\n"
            "Diagnosis: E11.22 (Type 2 diabetes with CKD)\n"
            "Payor: Medicare\n"
            "Date of Denial: 2026-04-08\n"
            "Clinical Context: Venipuncture billed separately but is bundled with lab panel per CCI edits."
        ),
        "expected_output": {
            "denial_code_identified": True,
            "carc_rarc_lookup_correct": True,
            "filing_deadline_checked": True,
            "deadline_within_window": True,
            "appeal_letter_generated": False,
            "clinical_evidence_cited": False,
            "key_findings": ["CO-97", "bundled", "CCI edits", "denial is correct", "no appeal recommended"],
            "must_not_contain": [],
        },
    },

    # ── TIMELY FILING DENIALS ─────────────────────────────────────────────────

    {
        "id": "ap_008",
        "category": "timely_filing",
        "input": (
            "Generate an appeal for a denied claim:\n"
            "Claim ID: CLM-2026-D008\n"
            "Denial Code: CO-29 (Time limit for filing has expired)\n"
            "Procedure: CPT 99213\n"
            "Diagnosis: J06.9 (Acute URI)\n"
            "Payor: UnitedHealthcare\n"
            "Date of Denial: 2026-04-01\n"
            "Date of Service: 2025-03-15\n"
            "Clinical Context: Claim was originally submitted timely on 2025-04-01 "
            "but rejected for missing info. Corrected claim submitted 2026-03-20."
        ),
        "expected_output": {
            "denial_code_identified": True,
            "carc_rarc_lookup_correct": True,
            "filing_deadline_checked": True,
            "deadline_within_window": True,
            "appeal_letter_generated": True,
            "clinical_evidence_cited": True,
            "key_findings": ["CO-29", "timely filing", "original submission proof", "2025-04-01"],
            "must_not_contain": [],
        },
    },
    {
        "id": "ap_009",
        "category": "timely_filing",
        "input": (
            "Generate an appeal for a denied claim:\n"
            "Claim ID: CLM-2026-D009\n"
            "Denial Code: CO-29\n"
            "Procedure: CPT 99214\n"
            "Diagnosis: I10 (Hypertension)\n"
            "Payor: Aetna\n"
            "Date of Denial: 2026-04-15\n"
            "Date of Service: 2024-06-01\n"
            "Clinical Context: Claim was never submitted previously. "
            "Aetna filing limit is 90 days. DOS was nearly 2 years ago."
        ),
        "expected_output": {
            "denial_code_identified": True,
            "carc_rarc_lookup_correct": True,
            "filing_deadline_checked": True,
            "deadline_within_window": False,
            "appeal_letter_generated": False,
            "clinical_evidence_cited": False,
            "key_findings": ["CO-29", "filing deadline expired", "no appeal viable", "90 days exceeded"],
            "must_not_contain": ["appeal letter"],
        },
    },

    # ── DUPLICATE CLAIM DENIALS ───────────────────────────────────────────────

    {
        "id": "ap_010",
        "category": "duplicate",
        "input": (
            "Generate an appeal for a denied claim:\n"
            "Claim ID: CLM-2026-D010\n"
            "Denial Code: CO-18 (Duplicate claim/service)\n"
            "Procedure: CPT 99213\n"
            "Diagnosis: M54.5 (Low back pain)\n"
            "Payor: BCBS\n"
            "Date of Denial: 2026-04-12\n"
            "Clinical Context: Patient was seen twice on the same day — morning for back pain, "
            "afternoon for new onset headache (R51.9). Different chief complaints, "
            "separate documentation for each visit."
        ),
        "expected_output": {
            "denial_code_identified": True,
            "carc_rarc_lookup_correct": True,
            "filing_deadline_checked": True,
            "deadline_within_window": True,
            "appeal_letter_generated": True,
            "clinical_evidence_cited": True,
            "key_findings": ["CO-18", "duplicate", "two separate visits", "different diagnoses", "modifier 76 or 77"],
            "must_not_contain": [],
        },
    },
]
