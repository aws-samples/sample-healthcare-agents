# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Golden set for medical-coding-agent evaluation.

Each item contains:
  - input: clinical_text to be coded
  - expected_output: verified ground truth
    - icd10_codes: list of {code, description}
    - cpt_codes: list of {code, description}
    - snomed_codes: list of {code, description} (optional)
    - entities_extracted: medical entities that must be found
    - key_findings: facts that MUST appear
    - must_not_contain: hallucination check

Reference: ICD-10-CM 2026, CPT 2026, SNOMED CT US Edition.
NOTE: Expected outputs require clinical coding SME validation before baseline.
"""

GOLDEN_SET = [

    # ── SINGLE DIAGNOSIS (clear-cut) ──────────────────────────────────────────

    {
        "id": "mc_001",
        "category": "single_diagnosis",
        "input": (
            "Patient presents with acute exacerbation of chronic obstructive pulmonary disease. "
            "Chest X-ray shows hyperinflation. Started on prednisone taper and albuterol nebulizer."
        ),
        "expected_output": {
            "icd10_codes": [{"code": "J44.1", "description": "COPD with acute exacerbation"}],
            "cpt_codes": [{"code": "71046", "description": "Chest X-ray 2 views"}],
            "snomed_codes": [{"code": "195951007", "description": "Acute exacerbation of COPD"}],
            "entities_extracted": ["COPD", "prednisone", "albuterol", "chest X-ray"],
            "key_findings": ["J44.1", "acute exacerbation"],
            "must_not_contain": [],
        },
    },
    {
        "id": "mc_002",
        "category": "single_diagnosis",
        "input": (
            "65-year-old male with type 2 diabetes mellitus with diabetic chronic kidney disease, "
            "stage 3. Current A1C 8.2%. On metformin 1000mg BID and lisinopril 20mg daily. "
            "eGFR 45 mL/min."
        ),
        "expected_output": {
            "icd10_codes": [
                {"code": "E11.22", "description": "Type 2 diabetes with diabetic CKD"},
                {"code": "N18.3", "description": "CKD stage 3"},
            ],
            "cpt_codes": [{"code": "83036", "description": "Hemoglobin A1C"}],
            "snomed_codes": [],
            "entities_extracted": ["type 2 diabetes", "chronic kidney disease", "metformin", "lisinopril", "A1C"],
            "key_findings": ["E11.22", "N18.3", "stage 3"],
            "must_not_contain": ["type 1 diabetes", "E10"],
        },
    },
    {
        "id": "mc_003",
        "category": "single_diagnosis",
        "input": (
            "Patient diagnosed with major depressive disorder, recurrent, moderate. "
            "PHQ-9 score 15. Started on sertraline 50mg daily. "
            "Referred to cognitive behavioral therapy."
        ),
        "expected_output": {
            "icd10_codes": [{"code": "F33.1", "description": "Major depressive disorder, recurrent, moderate"}],
            "cpt_codes": [],
            "snomed_codes": [],
            "entities_extracted": ["major depressive disorder", "sertraline", "PHQ-9"],
            "key_findings": ["F33.1", "recurrent", "moderate"],
            "must_not_contain": ["bipolar", "F31"],
        },
    },
    {
        "id": "mc_004",
        "category": "single_diagnosis",
        "input": (
            "3-year-old child with acute otitis media, right ear. Tympanic membrane erythematous "
            "and bulging. Started on amoxicillin 90mg/kg/day divided BID for 10 days."
        ),
        "expected_output": {
            "icd10_codes": [{"code": "H66.91", "description": "Otitis media, unspecified, right ear"}],
            "cpt_codes": [],
            "snomed_codes": [],
            "entities_extracted": ["otitis media", "tympanic membrane", "amoxicillin"],
            "key_findings": ["H66", "right ear", "acute"],
            "must_not_contain": ["bilateral", "left"],
        },
    },
    {
        "id": "mc_005",
        "category": "single_diagnosis",
        "input": (
            "Patient presents with acute ST-elevation myocardial infarction of the anterior wall. "
            "Troponin I elevated at 12.5 ng/mL. ECG shows ST elevation in V1-V4. "
            "Taken emergently for percutaneous coronary intervention with drug-eluting stent "
            "placement in the left anterior descending artery."
        ),
        "expected_output": {
            "icd10_codes": [{"code": "I21.01", "description": "STEMI involving LAD"}],
            "cpt_codes": [{"code": "92928", "description": "Percutaneous coronary stent placement"}],
            "snomed_codes": [],
            "entities_extracted": ["myocardial infarction", "troponin", "ECG", "stent", "LAD"],
            "key_findings": ["I21.01", "STEMI", "anterior wall", "LAD"],
            "must_not_contain": ["NSTEMI"],
        },
    },

    # ── MULTI-DIAGNOSIS (comorbidities) ───────────────────────────────────────

    {
        "id": "mc_006",
        "category": "multi_diagnosis",
        "input": (
            "72-year-old female admitted with community-acquired pneumonia, right lower lobe. "
            "History of congestive heart failure with reduced ejection fraction (EF 30%), "
            "atrial fibrillation on warfarin, and type 2 diabetes on insulin. "
            "Chest CT confirms right lower lobe consolidation. Started on ceftriaxone and azithromycin. "
            "BNP elevated at 1200 pg/mL. INR 2.5."
        ),
        "expected_output": {
            "icd10_codes": [
                {"code": "J18.1", "description": "Lobar pneumonia"},
                {"code": "I50.22", "description": "Chronic systolic heart failure"},
                {"code": "I48.91", "description": "Atrial fibrillation"},
                {"code": "E11.9", "description": "Type 2 diabetes"},
            ],
            "cpt_codes": [{"code": "71260", "description": "CT chest with contrast"}],
            "snomed_codes": [],
            "entities_extracted": ["pneumonia", "heart failure", "atrial fibrillation", "diabetes",
                                   "warfarin", "ceftriaxone", "azithromycin", "insulin"],
            "key_findings": ["J18", "I50", "I48", "right lower lobe", "reduced ejection fraction"],
            "must_not_contain": [],
        },
    },
    {
        "id": "mc_007",
        "category": "multi_diagnosis",
        "input": (
            "55-year-old male with uncontrolled hypertension (BP 178/102), "
            "hyperlipidemia (LDL 185), obesity BMI 36, and obstructive sleep apnea on CPAP. "
            "Comprehensive metabolic panel and lipid panel ordered. "
            "Amlodipine increased to 10mg, atorvastatin started at 40mg."
        ),
        "expected_output": {
            "icd10_codes": [
                {"code": "I10", "description": "Essential hypertension"},
                {"code": "E78.5", "description": "Hyperlipidemia"},
                {"code": "E66.01", "description": "Morbid obesity due to excess calories"},
                {"code": "G47.33", "description": "Obstructive sleep apnea"},
            ],
            "cpt_codes": [
                {"code": "80053", "description": "Comprehensive metabolic panel"},
                {"code": "80061", "description": "Lipid panel"},
            ],
            "snomed_codes": [],
            "entities_extracted": ["hypertension", "hyperlipidemia", "obesity", "sleep apnea",
                                   "amlodipine", "atorvastatin", "CPAP"],
            "key_findings": ["I10", "E78", "E66", "G47.33"],
            "must_not_contain": [],
        },
    },
    {
        "id": "mc_008",
        "category": "multi_diagnosis",
        "input": (
            "48-year-old female with rheumatoid arthritis on methotrexate presenting with "
            "acute flare of bilateral hand joints. Also has Sjogren syndrome with dry eyes "
            "and hypothyroidism on levothyroxine. X-rays of bilateral hands ordered. "
            "Prednisone 10mg taper initiated."
        ),
        "expected_output": {
            "icd10_codes": [
                {"code": "M06.09", "description": "Rheumatoid arthritis, multiple sites"},
                {"code": "M35.00", "description": "Sjogren syndrome, unspecified"},
                {"code": "E03.9", "description": "Hypothyroidism, unspecified"},
            ],
            "cpt_codes": [{"code": "73130", "description": "X-ray hand, minimum 3 views"}],
            "snomed_codes": [],
            "entities_extracted": ["rheumatoid arthritis", "methotrexate", "Sjogren", "hypothyroidism",
                                   "levothyroxine", "prednisone"],
            "key_findings": ["M06", "M35", "E03", "bilateral"],
            "must_not_contain": ["osteoarthritis"],
        },
    },

    # ── PROCEDURE-HEAVY NOTES ─────────────────────────────────────────────────

    {
        "id": "mc_009",
        "category": "procedure_heavy",
        "input": (
            "Patient underwent laparoscopic cholecystectomy for acute cholecystitis with cholelithiasis. "
            "Intraoperative cholangiogram performed, no common bile duct stones identified. "
            "Specimen sent to pathology. Estimated blood loss 50mL."
        ),
        "expected_output": {
            "icd10_codes": [
                {"code": "K80.00", "description": "Calculus of gallbladder with acute cholecystitis"},
            ],
            "cpt_codes": [
                {"code": "47562", "description": "Laparoscopic cholecystectomy with cholangiography"},
            ],
            "snomed_codes": [],
            "entities_extracted": ["cholecystectomy", "cholecystitis", "cholelithiasis", "cholangiogram"],
            "key_findings": ["K80", "47562", "laparoscopic"],
            "must_not_contain": ["open cholecystectomy"],
        },
    },
    {
        "id": "mc_010",
        "category": "procedure_heavy",
        "input": (
            "Colonoscopy performed for colorectal cancer screening in 52-year-old male. "
            "Two polyps found and removed — 8mm sessile polyp in sigmoid colon (snare polypectomy) "
            "and 5mm polyp in ascending colon (cold forceps). Specimens sent to pathology."
        ),
        "expected_output": {
            "icd10_codes": [
                {"code": "K63.5", "description": "Polyp of colon"},
                {"code": "Z12.11", "description": "Encounter for screening for malignant neoplasm of colon"},
            ],
            "cpt_codes": [
                {"code": "45385", "description": "Colonoscopy with snare polypectomy"},
                {"code": "45380", "description": "Colonoscopy with biopsy"},
            ],
            "snomed_codes": [],
            "entities_extracted": ["colonoscopy", "polyp", "sigmoid colon", "ascending colon", "polypectomy"],
            "key_findings": ["K63.5", "Z12.11", "45385", "screening"],
            "must_not_contain": [],
        },
    },
    {
        "id": "mc_011",
        "category": "procedure_heavy",
        "input": (
            "Right total knee arthroplasty performed for severe osteoarthritis right knee. "
            "Cemented prosthesis placed. Tourniquet time 65 minutes. "
            "Intraoperative fluoroscopy confirmed component alignment. "
            "Patient tolerated procedure well, transferred to PACU in stable condition."
        ),
        "expected_output": {
            "icd10_codes": [
                {"code": "M17.11", "description": "Primary osteoarthritis, right knee"},
            ],
            "cpt_codes": [
                {"code": "27447", "description": "Total knee arthroplasty"},
            ],
            "snomed_codes": [],
            "entities_extracted": ["knee arthroplasty", "osteoarthritis", "prosthesis", "fluoroscopy"],
            "key_findings": ["M17.11", "27447", "right knee"],
            "must_not_contain": ["left knee", "M17.12"],
        },
    },

    # ── MEDICATION-FOCUSED ────────────────────────────────────────────────────

    {
        "id": "mc_012",
        "category": "medication_focused",
        "input": (
            "Patient developed anaphylaxis after receiving IV penicillin for cellulitis of left leg. "
            "Symptoms included urticaria, angioedema, and hypotension (BP 80/50). "
            "Treated with epinephrine 0.3mg IM, diphenhydramine 50mg IV, methylprednisolone 125mg IV. "
            "Patient stabilized and admitted for observation."
        ),
        "expected_output": {
            "icd10_codes": [
                {"code": "T36.0X5A", "description": "Adverse effect of penicillins, initial encounter"},
                {"code": "T78.2XXA", "description": "Anaphylactic shock, unspecified, initial encounter"},
                {"code": "L03.116", "description": "Cellulitis of left lower limb"},
            ],
            "cpt_codes": [],
            "snomed_codes": [],
            "entities_extracted": ["anaphylaxis", "penicillin", "cellulitis", "epinephrine",
                                   "diphenhydramine", "methylprednisolone", "urticaria", "angioedema"],
            "key_findings": ["T36", "T78.2", "anaphylaxis", "penicillin", "adverse effect"],
            "must_not_contain": ["poisoning"],
        },
    },
    {
        "id": "mc_013",
        "category": "medication_focused",
        "input": (
            "82-year-old on warfarin for mechanical aortic valve presents with INR 5.8 and "
            "epistaxis. No other active bleeding. Warfarin held, vitamin K 2.5mg oral administered. "
            "Repeat INR in 24 hours."
        ),
        "expected_output": {
            "icd10_codes": [
                {"code": "T45.515A", "description": "Adverse effect of anticoagulants, initial encounter"},
                {"code": "R04.0", "description": "Epistaxis"},
                {"code": "Z95.2", "description": "Presence of prosthetic heart valve"},
            ],
            "cpt_codes": [{"code": "85610", "description": "Prothrombin time (PT/INR)"}],
            "snomed_codes": [],
            "entities_extracted": ["warfarin", "INR", "epistaxis", "vitamin K", "mechanical valve"],
            "key_findings": ["T45.515", "R04.0", "anticoagulant", "adverse effect"],
            "must_not_contain": ["poisoning", "intentional"],
        },
    },

    # ── AMBIGUOUS NOTES ───────────────────────────────────────────────────────

    {
        "id": "mc_014",
        "category": "ambiguous",
        "input": (
            "Patient presents with chest pain, rule out acute coronary syndrome. "
            "Troponin negative x2. ECG normal sinus rhythm, no ST changes. "
            "Stress test ordered for tomorrow. Likely non-cardiac chest pain — "
            "possible GERD given history of reflux symptoms."
        ),
        "expected_output": {
            "icd10_codes": [
                {"code": "R07.9", "description": "Chest pain, unspecified"},
            ],
            "cpt_codes": [
                {"code": "93015", "description": "Cardiovascular stress test"},
            ],
            "snomed_codes": [],
            "entities_extracted": ["chest pain", "troponin", "ECG", "stress test", "GERD"],
            "key_findings": ["R07.9", "chest pain", "rule out"],
            "must_not_contain": ["I21", "myocardial infarction"],
        },
    },
    {
        "id": "mc_015",
        "category": "ambiguous",
        "input": (
            "Patient with history of breast cancer (status post mastectomy 2023) presents for "
            "surveillance imaging. No current symptoms. PET/CT ordered. "
            "Exam unremarkable, no palpable masses or lymphadenopathy."
        ),
        "expected_output": {
            "icd10_codes": [
                {"code": "Z85.3", "description": "Personal history of malignant neoplasm of breast"},
                {"code": "Z90.11", "description": "Acquired absence of right breast and nipple"},
            ],
            "cpt_codes": [
                {"code": "78816", "description": "PET/CT for limited area"},
            ],
            "snomed_codes": [],
            "entities_extracted": ["breast cancer", "mastectomy", "PET/CT", "surveillance"],
            "key_findings": ["Z85.3", "history of", "surveillance"],
            "must_not_contain": ["C50", "active malignancy"],
        },
    },

    # ── EDGE CASES ────────────────────────────────────────────────────────────

    {
        "id": "mc_016",
        "category": "edge_case",
        "input": (
            "Bilateral carpal tunnel release performed. Patient had bilateral carpal tunnel syndrome "
            "confirmed by nerve conduction studies. Right side more symptomatic than left."
        ),
        "expected_output": {
            "icd10_codes": [
                {"code": "G56.03", "description": "Carpal tunnel syndrome, bilateral"},
            ],
            "cpt_codes": [
                {"code": "64721", "description": "Neuroplasty, carpal tunnel"},
                {"code": "64721-50", "description": "Neuroplasty, carpal tunnel, bilateral modifier"},
            ],
            "snomed_codes": [],
            "entities_extracted": ["carpal tunnel", "nerve conduction", "bilateral"],
            "key_findings": ["G56.03", "64721", "bilateral"],
            "must_not_contain": ["unilateral"],
        },
    },
    {
        "id": "mc_017",
        "category": "edge_case",
        "input": (
            "Patient seen for well-child visit, 12-month-old. Developmental milestones on track. "
            "Immunizations administered: MMR, varicella, hepatitis A, PCV13. "
            "Height and weight at 50th percentile."
        ),
        "expected_output": {
            "icd10_codes": [
                {"code": "Z00.121", "description": "Encounter for routine child health exam with abnormal findings"},
            ],
            "cpt_codes": [
                {"code": "99391", "description": "Preventive visit, infant"},
                {"code": "90707", "description": "MMR vaccine"},
                {"code": "90716", "description": "Varicella vaccine"},
            ],
            "snomed_codes": [],
            "entities_extracted": ["well-child", "immunizations", "MMR", "varicella", "hepatitis A"],
            "key_findings": ["Z00.12", "99391", "preventive"],
            "must_not_contain": ["illness", "sick visit"],
        },
    },
    {
        "id": "mc_018",
        "category": "edge_case",
        "input": (
            "Encounter for adjustment of insulin pump. Patient with type 1 diabetes, well-controlled, "
            "A1C 6.8%. Pump settings adjusted — basal rate increased overnight. "
            "No hypoglycemic episodes reported."
        ),
        "expected_output": {
            "icd10_codes": [
                {"code": "Z46.81", "description": "Encounter for fitting and adjustment of insulin pump"},
                {"code": "E10.9", "description": "Type 1 diabetes without complications"},
            ],
            "cpt_codes": [],
            "snomed_codes": [],
            "entities_extracted": ["insulin pump", "type 1 diabetes", "A1C"],
            "key_findings": ["Z46.81", "E10", "type 1", "pump adjustment"],
            "must_not_contain": ["type 2", "E11"],
        },
    },
]
