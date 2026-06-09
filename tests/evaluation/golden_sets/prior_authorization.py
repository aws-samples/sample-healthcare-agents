# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Golden set for prior-authorization-agent evaluation.

Each item contains:
  - input: dict with patient_id, procedure_code, procedure_description, payor, clinical_context
  - expected_output: verified ground truth for scoring
    - auth_required: whether prior auth is needed
    - medical_necessity_met: whether clinical evidence supports necessity
    - clinical_data_gathered: list of FHIR resource types that should be retrieved
    - payor_policy_cited: whether agent should cite payor policy
    - fhir_bundle_valid: whether output should be a valid FHIR Claim bundle
    - key_findings: facts that MUST appear in the analysis
    - must_not_contain: strings that must NOT appear (hallucination check)

Reference: CMS Medicare Benefit Policy Manual Ch.15, UHC/Aetna/BCBS prior auth lists.
NOTE: Expected outputs require clinical SME validation before baseline.
"""

GOLDEN_SET = [

    # ── REQUIRES AUTH (common procedures) ─────────────────────────────────────

    {
        "id": "pa_001",
        "category": "requires_auth",
        "input": {
            "patient_id": "Patient/smart-1032702",
            "procedure_code": "72148",
            "procedure_description": "MRI lumbar spine without contrast",
            "payor": "UnitedHealthcare",
            "clinical_context": (
                "58-year-old male with chronic low back pain radiating to left leg for 8 weeks. "
                "Failed 6 weeks of physical therapy and NSAIDs. Straight leg raise positive on left. "
                "Neurological exam shows decreased sensation L5 dermatome."
            ),
        },
        "expected_output": {
            "auth_required": True,
            "medical_necessity_met": True,
            "clinical_data_gathered": ["conditions", "medications", "observations"],
            "payor_policy_cited": True,
            "fhir_bundle_valid": True,
            "key_findings": ["chronic low back pain", "failed conservative therapy", "radiculopathy", "L5"],
            "must_not_contain": [],
        },
    },
    {
        "id": "pa_002",
        "category": "requires_auth",
        "input": {
            "patient_id": "Patient/smart-1032702",
            "procedure_code": "27447",
            "procedure_description": "Total knee arthroplasty",
            "payor": "Aetna",
            "clinical_context": (
                "72-year-old female with severe osteoarthritis right knee. BMI 28. "
                "Failed 12 months conservative management including PT, cortisone injections x3, "
                "hyaluronic acid injections. Kellgren-Lawrence grade IV on X-ray. "
                "Significant functional limitation — unable to walk more than one block."
            ),
        },
        "expected_output": {
            "auth_required": True,
            "medical_necessity_met": True,
            "clinical_data_gathered": ["conditions", "medications", "observations", "allergies"],
            "payor_policy_cited": True,
            "fhir_bundle_valid": True,
            "key_findings": ["osteoarthritis", "Kellgren-Lawrence IV", "failed conservative", "functional limitation"],
            "must_not_contain": [],
        },
    },
    {
        "id": "pa_003",
        "category": "requires_auth",
        "input": {
            "patient_id": "Patient/smart-1032702",
            "procedure_code": "74177",
            "procedure_description": "CT abdomen and pelvis with contrast",
            "payor": "BlueCross BlueShield",
            "clinical_context": (
                "45-year-old male presenting with unexplained weight loss of 15 lbs over 3 months, "
                "new onset abdominal pain, and elevated CEA levels. Family history of colon cancer. "
                "Colonoscopy 2 weeks ago showed suspicious mass in ascending colon."
            ),
        },
        "expected_output": {
            "auth_required": True,
            "medical_necessity_met": True,
            "clinical_data_gathered": ["conditions", "observations"],
            "payor_policy_cited": True,
            "fhir_bundle_valid": True,
            "key_findings": ["weight loss", "elevated CEA", "suspicious mass", "colon"],
            "must_not_contain": [],
        },
    },
    {
        "id": "pa_004",
        "category": "requires_auth",
        "input": {
            "patient_id": "Patient/smart-1032702",
            "procedure_code": "E1390",
            "procedure_description": "Oxygen concentrator, single delivery port",
            "payor": "Medicare",
            "clinical_context": (
                "78-year-old female with COPD GOLD stage III. Room air SpO2 consistently 86-88% "
                "at rest documented over 3 visits. ABG shows PaO2 52 mmHg. "
                "Currently on maximum bronchodilator therapy."
            ),
        },
        "expected_output": {
            "auth_required": True,
            "medical_necessity_met": True,
            "clinical_data_gathered": ["conditions", "observations", "medications"],
            "payor_policy_cited": True,
            "fhir_bundle_valid": True,
            "key_findings": ["COPD", "SpO2 86-88%", "PaO2 52", "oxygen"],
            "must_not_contain": [],
        },
    },
    {
        "id": "pa_005",
        "category": "requires_auth",
        "input": {
            "patient_id": "Patient/smart-1032702",
            "procedure_code": "J0585",
            "procedure_description": "Botulinum toxin type A (Botox) injection",
            "payor": "UnitedHealthcare",
            "clinical_context": (
                "42-year-old female with chronic migraine — 18 headache days per month for past 6 months. "
                "Failed trials of topiramate, propranolol, and amitriptyline. "
                "CGRP inhibitor (Aimovig) tried for 3 months with inadequate response."
            ),
        },
        "expected_output": {
            "auth_required": True,
            "medical_necessity_met": True,
            "clinical_data_gathered": ["conditions", "medications"],
            "payor_policy_cited": True,
            "fhir_bundle_valid": True,
            "key_findings": ["chronic migraine", "18 headache days", "failed preventives", "CGRP inadequate"],
            "must_not_contain": [],
        },
    },

    # ── DOES NOT REQUIRE AUTH ─────────────────────────────────────────────────

    {
        "id": "pa_006",
        "category": "no_auth_required",
        "input": {
            "patient_id": "Patient/smart-1032702",
            "procedure_code": "80053",
            "procedure_description": "Comprehensive metabolic panel",
            "payor": "UnitedHealthcare",
            "clinical_context": (
                "55-year-old male with type 2 diabetes, annual wellness visit. "
                "Routine lab work ordered for diabetes management."
            ),
        },
        "expected_output": {
            "auth_required": False,
            "medical_necessity_met": True,
            "clinical_data_gathered": ["conditions"],
            "payor_policy_cited": False,
            "fhir_bundle_valid": False,
            "key_findings": ["routine lab", "no auth required"],
            "must_not_contain": ["prior authorization required"],
        },
    },
    {
        "id": "pa_007",
        "category": "no_auth_required",
        "input": {
            "patient_id": "Patient/smart-1032702",
            "procedure_code": "99213",
            "procedure_description": "Office visit, established patient, low complexity",
            "payor": "Aetna",
            "clinical_context": (
                "35-year-old female presenting for follow-up of well-controlled hypertension. "
                "BP 128/82. No medication changes needed."
            ),
        },
        "expected_output": {
            "auth_required": False,
            "medical_necessity_met": True,
            "clinical_data_gathered": ["conditions"],
            "payor_policy_cited": False,
            "fhir_bundle_valid": False,
            "key_findings": ["office visit", "no auth required"],
            "must_not_contain": ["prior authorization required"],
        },
    },
    {
        "id": "pa_008",
        "category": "no_auth_required",
        "input": {
            "patient_id": "Patient/smart-1032702",
            "procedure_code": "99281",
            "procedure_description": "Emergency department visit",
            "payor": "BlueCross BlueShield",
            "clinical_context": (
                "28-year-old male brought to ED after motor vehicle accident. "
                "Complaining of chest pain and shortness of breath. GCS 15."
            ),
        },
        "expected_output": {
            "auth_required": False,
            "medical_necessity_met": True,
            "clinical_data_gathered": ["conditions"],
            "payor_policy_cited": False,
            "fhir_bundle_valid": False,
            "key_findings": ["emergency", "no auth required"],
            "must_not_contain": ["prior authorization required"],
        },
    },

    # ── INSUFFICIENT CLINICAL EVIDENCE ────────────────────────────────────────

    {
        "id": "pa_009",
        "category": "insufficient_evidence",
        "input": {
            "patient_id": "Patient/smart-1032702",
            "procedure_code": "72148",
            "procedure_description": "MRI lumbar spine without contrast",
            "payor": "UnitedHealthcare",
            "clinical_context": (
                "40-year-old male with low back pain for 2 weeks. "
                "No radiculopathy. No red flags. No prior treatment attempted."
            ),
        },
        "expected_output": {
            "auth_required": True,
            "medical_necessity_met": False,
            "clinical_data_gathered": ["conditions", "medications", "observations"],
            "payor_policy_cited": True,
            "fhir_bundle_valid": False,
            "key_findings": ["no conservative therapy", "no red flags", "insufficient evidence"],
            "must_not_contain": [],
        },
    },
    {
        "id": "pa_010",
        "category": "insufficient_evidence",
        "input": {
            "patient_id": "Patient/smart-1032702",
            "procedure_code": "27447",
            "procedure_description": "Total knee arthroplasty",
            "payor": "Aetna",
            "clinical_context": (
                "55-year-old male with knee pain. X-ray shows mild osteoarthritis "
                "Kellgren-Lawrence grade II. No physical therapy attempted. "
                "BMI 38. No injections tried."
            ),
        },
        "expected_output": {
            "auth_required": True,
            "medical_necessity_met": False,
            "clinical_data_gathered": ["conditions", "medications", "observations"],
            "payor_policy_cited": True,
            "fhir_bundle_valid": False,
            "key_findings": ["mild osteoarthritis", "KL grade II", "no conservative therapy", "BMI 38"],
            "must_not_contain": [],
        },
    },
    {
        "id": "pa_011",
        "category": "insufficient_evidence",
        "input": {
            "patient_id": "Patient/smart-1032702",
            "procedure_code": "J0585",
            "procedure_description": "Botulinum toxin type A (Botox) injection",
            "payor": "UnitedHealthcare",
            "clinical_context": (
                "30-year-old female with episodic migraine — 8 headache days per month. "
                "Tried topiramate for 4 weeks, stopped due to side effects. "
                "No other preventive medications attempted."
            ),
        },
        "expected_output": {
            "auth_required": True,
            "medical_necessity_met": False,
            "clinical_data_gathered": ["conditions", "medications"],
            "payor_policy_cited": True,
            "fhir_bundle_valid": False,
            "key_findings": ["episodic migraine", "8 days", "only one preventive tried", "does not meet chronic criteria"],
            "must_not_contain": [],
        },
    },

    # ── PAYOR-SPECIFIC EDGE CASES ─────────────────────────────────────────────

    {
        "id": "pa_012",
        "category": "payor_edge_case",
        "input": {
            "patient_id": "Patient/smart-1032702",
            "procedure_code": "70553",
            "procedure_description": "MRI brain with and without contrast",
            "payor": "Medicare",
            "clinical_context": (
                "68-year-old female with new onset seizures. CT head negative. "
                "Neurologist recommends MRI brain to evaluate for structural lesion."
            ),
        },
        "expected_output": {
            "auth_required": False,
            "medical_necessity_met": True,
            "clinical_data_gathered": ["conditions", "observations"],
            "payor_policy_cited": True,
            "fhir_bundle_valid": False,
            "key_findings": ["Medicare", "new onset seizures", "no auth for Medicare MRI brain"],
            "must_not_contain": [],
        },
    },
    {
        "id": "pa_013",
        "category": "payor_edge_case",
        "input": {
            "patient_id": "Patient/smart-1032702",
            "procedure_code": "70553",
            "procedure_description": "MRI brain with and without contrast",
            "payor": "UnitedHealthcare",
            "clinical_context": (
                "68-year-old female with new onset seizures. CT head negative. "
                "Neurologist recommends MRI brain to evaluate for structural lesion."
            ),
        },
        "expected_output": {
            "auth_required": True,
            "medical_necessity_met": True,
            "clinical_data_gathered": ["conditions", "observations"],
            "payor_policy_cited": True,
            "fhir_bundle_valid": True,
            "key_findings": ["UHC requires auth for MRI brain", "new onset seizures", "medical necessity met"],
            "must_not_contain": [],
        },
    },

    # ── COMPLEX CLINICAL HISTORY ──────────────────────────────────────────────

    {
        "id": "pa_014",
        "category": "complex_history",
        "input": {
            "patient_id": "Patient/smart-1032702",
            "procedure_code": "43239",
            "procedure_description": "Upper GI endoscopy with biopsy",
            "payor": "Aetna",
            "clinical_context": (
                "62-year-old male with Barrett's esophagus on surveillance, type 2 diabetes, "
                "CKD stage 3, on warfarin for atrial fibrillation. Last EGD 2 years ago showed "
                "low-grade dysplasia. Gastroenterologist recommends repeat surveillance EGD with biopsy. "
                "INR currently 2.8 — will need warfarin bridge protocol."
            ),
        },
        "expected_output": {
            "auth_required": True,
            "medical_necessity_met": True,
            "clinical_data_gathered": ["conditions", "medications", "observations", "allergies"],
            "payor_policy_cited": True,
            "fhir_bundle_valid": True,
            "key_findings": ["Barrett's", "dysplasia", "surveillance", "warfarin", "comorbidities"],
            "must_not_contain": [],
        },
    },
    {
        "id": "pa_015",
        "category": "complex_history",
        "input": {
            "patient_id": "Patient/smart-1032702",
            "procedure_code": "64483",
            "procedure_description": "Transforaminal epidural steroid injection, lumbar",
            "payor": "BlueCross BlueShield",
            "clinical_context": (
                "50-year-old female with lumbar radiculopathy, L4-L5 disc herniation on prior MRI. "
                "History of lumbar fusion L5-S1 (2022). Failed 8 weeks PT, gabapentin 300mg TID, "
                "and oral prednisone taper. Pain score 8/10. Unable to work as a nurse. "
                "Allergic to NSAIDs (anaphylaxis). Previous epidural 6 months ago provided 3 months relief."
            ),
        },
        "expected_output": {
            "auth_required": True,
            "medical_necessity_met": True,
            "clinical_data_gathered": ["conditions", "medications", "observations", "allergies"],
            "payor_policy_cited": True,
            "fhir_bundle_valid": True,
            "key_findings": ["disc herniation", "prior fusion", "failed conservative", "NSAID allergy", "functional limitation"],
            "must_not_contain": [],
        },
    },
]
