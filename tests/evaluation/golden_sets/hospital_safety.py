# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Golden set for hospital-safety-agent evaluation.

Aligned with the agent's actual schema (SafetyEventClassification):
  - event_type: medication_error | infection_control | patient_fall | device_malfunction
  - event_classification: near_miss | unsafe_condition | adverse_event
  - severity: low | medium | high | critical
  - harm_level: none | emotional_distress | additional_treatment | temporary | permanent | severe_permanent | death

Based on NQF serious reportable events and IOM patient safety taxonomy.
Reference: IOM "Patient Safety: Achieving a New Standard for Care" (2004), Ch. 9.

Each item contains:
  - input: incident description sent to the agent
  - expected_output: verified ground truth for scoring
    - event_type: what type the agent must classify
    - event_classification: near_miss | unsafe_condition | adverse_event
    - severity: low | medium | high | critical
    - harm_level: expected patient harm level
    - specialists: list of expected specialist agents to be invoked
    - key_findings: facts that MUST appear in the analysis
    - must_not_contain: strings that must NOT appear (hallucination check)
"""

GOLDEN_SET = [

    # ── PATIENT FALLS ─────────────────────────────────────────────────────────

    {
        "id": "fall_001",
        "category": "patient_fall",
        "input": (
            "86-year-old patient fell while attempting to reach the bathroom unassisted. "
            "Found on floor by nursing staff. Patient reports hip pain. "
            "Fall risk assessment was marked as high."
        ),
        "expected_output": {
            "event_type": "patient_fall",
            "event_classification": "adverse_event",
            "severity": "high",
            "harm_level": "additional_treatment",
            "preventability": "preventable",
            "mandatory_reporting": False,
            "specialists": ["FallsPrevention"],
            "key_findings": ["hip", "fall risk", "high"],
            "must_not_contain": [],
        },
    },
    {
        "id": "fall_002",
        "category": "patient_fall",
        "input": (
            "Patient in room 214 slipped on wet floor near the nurses station. "
            "No injury reported. Fall risk was low per assessment. "
            "Wet floor sign was not placed after mopping."
        ),
        "expected_output": {
            "event_type": "patient_fall",
            "event_classification": "adverse_event",
            "severity": "low",
            "harm_level": "none",
            "preventability": "preventable",
            "mandatory_reporting": False,
            "specialists": ["FallsPrevention"],
            "key_findings": ["wet floor", "no injury"],
            "must_not_contain": [],
        },
    },
    {
        "id": "fall_003",
        "category": "patient_fall",
        "input": (
            "Post-surgical patient fell from bed attempting to self-transfer to wheelchair. "
            "Patient sustained laceration to forehead requiring sutures and possible concussion. "
            "Bed rails were down. Call light was out of reach."
        ),
        "expected_output": {
            "event_type": "patient_fall",
            "event_classification": "adverse_event",
            "severity": "high",
            "harm_level": "additional_treatment",
            "preventability": "preventable",
            "mandatory_reporting": False,
            "specialists": ["FallsPrevention"],
            "key_findings": ["laceration", "concussion", "bed rails"],
            "must_not_contain": [],
        },
    },
    {
        "id": "fall_004",
        "category": "patient_fall",
        "input": (
            "Elderly patient found unresponsive on bathroom floor. "
            "Head injury with active bleeding. Patient is on anticoagulants. "
            "Unwitnessed fall. Code called."
        ),
        "expected_output": {
            "event_type": "patient_fall",
            "event_classification": "adverse_event",
            "severity": "critical",
            "harm_level": "severe_permanent",
            "preventability": "preventable",
            "mandatory_reporting": True,  # NQF SRE: death or serious disability from inpatient fall
            "specialists": ["FallsPrevention"],
            "key_findings": ["unresponsive", "head injury", "anticoagulant", "code"],
            "must_not_contain": [],
        },
    },
    {
        "id": "fall_005",
        "category": "patient_fall",
        "input": (
            "Third fall this week for patient in room 308. "
            "Each fall occurred during night shift. Patient has dementia and "
            "repeatedly attempts to climb out of bed. Bed alarm was not activated."
        ),
        "expected_output": {
            "event_type": "patient_fall",
            "event_classification": "adverse_event",
            "severity": "high",
            "harm_level": "none",
            "preventability": "preventable",
            "mandatory_reporting": False,
            "specialists": ["FallsPrevention"],
            "key_findings": ["dementia", "night shift", "bed alarm", "recurring"],
            "must_not_contain": [],
        },
    },
    {
        "id": "fall_006_unsafe_condition",
        "category": "patient_fall",
        "input": (
            "Charge nurse identified that bed alarms have been consistently deactivated "
            "on the night shift in rooms 310-315. No falls have occurred yet. "
            "Reviewed and confirmed by supervisor after a nursing assistant complaint."
        ),
        "expected_output": {
            "event_type": "patient_fall",
            "event_classification": "unsafe_condition",
            "severity": "medium",
            "harm_level": "none",
            "preventability": "preventable",
            "mandatory_reporting": False,
            "specialists": ["FallsPrevention"],
            "key_findings": ["bed alarm", "night shift", "deactivated"],
            "must_not_contain": [],
        },
    },

    # ── MEDICATION ERRORS ─────────────────────────────────────────────────────

    {
        "id": "med_001",
        "category": "medication_error",
        "input": (
            "Nurse administered 20mg of Lasix instead of prescribed 10mg to patient "
            "in room 302. Blood pressure dropped to 90/60. "
            "Medication error discovered during shift change."
        ),
        "expected_output": {
            "event_type": "medication_error",
            "event_classification": "adverse_event",
            "severity": "high",
            "harm_level": "additional_treatment",
            "preventability": "preventable",
            "mandatory_reporting": False,
            "specialists": ["MedicationSafety"],
            "key_findings": ["Lasix", "double dose", "hypotension"],
            "must_not_contain": [],
        },
    },
    {
        "id": "med_002_wrong_patient",
        "category": "medication_error",
        "input": (
            "Wrong patient received insulin injection. Nurse scanned incorrect wristband. "
            "Patient is not diabetic. Blood glucose dropped to 48. "
            "Patient became diaphoretic and confused."
        ),
        "expected_output": {
            "event_type": "medication_error",
            "event_classification": "adverse_event",
            "severity": "critical",
            "harm_level": "temporary",
            "preventability": "preventable",
            "mandatory_reporting": False,
            "specialists": ["MedicationSafety"],
            "key_findings": ["wrong patient", "insulin", "hypoglycemia", "wristband"],
            "must_not_contain": [],
        },
    },
    {
        "id": "med_003_sentinel",
        "category": "medication_error",
        "input": (
            "Pharmacy dispensed methotrexate daily instead of weekly for rheumatoid "
            "arthritis patient. Patient received 6 daily doses before error caught. "
            "Patient now showing signs of mucositis and bone marrow suppression."
        ),
        "expected_output": {
            "event_type": "medication_error",
            "event_classification": "adverse_event",
            "severity": "critical",
            "harm_level": "severe_permanent",
            "preventability": "preventable",
            "mandatory_reporting": True,  # NQF SRE: serious disability from medication error
            "specialists": ["MedicationSafety"],
            "key_findings": ["methotrexate", "daily", "weekly", "mucositis", "bone marrow"],
            "must_not_contain": [],
        },
    },
    {
        "id": "med_004_allergy",
        "category": "medication_error",
        "input": (
            "Nurse prepared IV antibiotic but did not check allergy band. "
            "Patient received penicillin despite documented penicillin allergy. "
            "Patient developed hives. Anaphylaxis protocol initiated."
        ),
        "expected_output": {
            "event_type": "medication_error",
            "event_classification": "adverse_event",
            "severity": "high",
            "harm_level": "additional_treatment",
            "preventability": "preventable",
            "mandatory_reporting": False,
            "specialists": ["MedicationSafety"],
            "key_findings": ["allergy", "penicillin", "anaphylaxis"],
            "must_not_contain": [],
        },
    },
    {
        "id": "med_005_concentration",
        "category": "medication_error",
        "input": (
            "Incorrect concentration of heparin infusion prepared. "
            "25,000 units/250mL mixed instead of 25,000 units/500mL. "
            "Patient received double the intended heparin dose for 4 hours. "
            "PTT now critically elevated at 180 seconds."
        ),
        "expected_output": {
            "event_type": "medication_error",
            "event_classification": "adverse_event",
            "severity": "critical",
            "harm_level": "temporary",
            "preventability": "preventable",
            "mandatory_reporting": False,
            "specialists": ["MedicationSafety"],
            "key_findings": ["heparin", "concentration", "double dose", "PTT"],
            "must_not_contain": [],
        },
    },
    {
        "id": "med_006_near_miss",
        "category": "medication_error",
        "input": (
            "Pharmacist caught a prescribing error before dispensing. "
            "Physician ordered 100mg metoprolol IV instead of oral. "
            "IV metoprolol at that dose would have caused severe bradycardia. "
            "Prescription returned to physician for correction. No medication given."
        ),
        "expected_output": {
            "event_type": "medication_error",
            "event_classification": "near_miss",
            "severity": "high",
            "harm_level": "none",
            "preventability": "preventable",
            "mandatory_reporting": False,
            "specialists": ["MedicationSafety"],
            "key_findings": ["metoprolol", "IV", "pharmacist", "caught", "no medication given"],
            "must_not_contain": [],
        },
    },
    {
        "id": "med_007_omission",
        "category": "medication_error",
        "input": (
            "Diabetic patient did not receive scheduled insulin for 18 hours due to missed "
            "pharmacy order entry. Blood glucose rose to 450. Patient developed signs of "
            "diabetic ketoacidosis. Night shift nurse discovered the gap during medication reconciliation."
        ),
        "expected_output": {
            "event_type": "medication_error",
            "event_classification": "adverse_event",
            "severity": "high",
            "harm_level": "additional_treatment",
            "preventability": "preventable",
            "mandatory_reporting": False,
            "specialists": ["MedicationSafety"],
            "key_findings": ["insulin", "omission", "DKA", "blood glucose"],
            "must_not_contain": [],
        },
    },
    {
        "id": "med_008_pediatric",
        "category": "medication_error",
        "input": (
            "4-year-old patient received adult dose of acetaminophen (650mg) instead of "
            "weight-based pediatric dose (160mg). Dose was 4x the appropriate amount. "
            "Error caught by nurse on second check before any symptoms developed. "
            "Poison control consulted."
        ),
        "expected_output": {
            "event_type": "medication_error",
            "event_classification": "adverse_event",
            "severity": "high",
            "harm_level": "none",
            "preventability": "preventable",
            "mandatory_reporting": False,
            "specialists": ["MedicationSafety"],
            "key_findings": ["pediatric", "acetaminophen", "adult dose", "weight-based"],
            "must_not_contain": [],
        },
    },

    # ── INFECTION CONTROL ─────────────────────────────────────────────────────

    {
        "id": "inf_001_cauti",
        "category": "infection_control",
        "input": (
            "Patient in ICU bed 5 developed CAUTI on day 4 of catheterization. "
            "Temperature spiked to 101.5F. Urine culture positive for E. coli. "
            "Two other patients in the ICU also have catheter-associated infections this week."
        ),
        "expected_output": {
            "event_type": "infection_control",
            "event_classification": "adverse_event",
            "severity": "high",
            "harm_level": "additional_treatment",
            "preventability": "probably_preventable",
            "mandatory_reporting": False,
            "specialists": ["InfectionControl"],
            "key_findings": ["CAUTI", "E. coli", "catheter", "cluster"],
            "must_not_contain": [],
        },
    },
    {
        "id": "inf_002_ssi",
        "category": "infection_control",
        "input": (
            "Post-op patient developed surgical site infection 5 days after hip replacement. "
            "Wound is erythematous with purulent drainage. Culture pending. "
            "Three other orthopedic patients had SSIs this month."
        ),
        "expected_output": {
            "event_type": "infection_control",
            "event_classification": "adverse_event",
            "severity": "high",
            "harm_level": "additional_treatment",
            "preventability": "probably_preventable",
            "mandatory_reporting": False,
            "specialists": ["InfectionControl"],
            "key_findings": ["SSI", "hip replacement", "purulent", "cluster"],
            "must_not_contain": [],
        },
    },
    {
        "id": "inf_003_hand_hygiene",
        "category": "infection_control",
        "input": (
            "Nurse observed skipping hand hygiene before central line dressing change. "
            "Patient has no signs of infection currently. Observed by charge nurse."
        ),
        "expected_output": {
            "event_type": "infection_control",
            "event_classification": "unsafe_condition",
            "severity": "low",
            "harm_level": "none",
            "preventability": "preventable",
            "mandatory_reporting": False,
            "specialists": ["InfectionControl"],
            "key_findings": ["hand hygiene", "central line", "compliance"],
            "must_not_contain": [],
        },
    },
    {
        "id": "inf_004_cdiff",
        "category": "infection_control",
        "input": (
            "Four patients on the same medical-surgical floor tested positive for "
            "Clostridioides difficile within 10 days. All 4 had recent antibiotic use. "
            "Environmental cleaning logs show inconsistent terminal cleaning of rooms."
        ),
        "expected_output": {
            "event_type": "infection_control",
            "event_classification": "adverse_event",
            "severity": "high",
            "harm_level": "additional_treatment",
            "preventability": "probably_preventable",
            "mandatory_reporting": False,
            "specialists": ["InfectionControl"],
            "key_findings": ["C. diff", "cluster", "antibiotic", "environmental cleaning"],
            "must_not_contain": [],
        },
    },
    {
        "id": "inf_005_clabsi",
        "category": "infection_control",
        "input": (
            "MRSA bacteremia identified in ICU patient with central line in place for 8 days. "
            "CLABSI bundle compliance was 60% per last audit. "
            "This is the second CLABSI this month in the same unit."
        ),
        "expected_output": {
            "event_type": "infection_control",
            "event_classification": "adverse_event",
            "severity": "high",
            "harm_level": "additional_treatment",
            "preventability": "probably_preventable",
            "mandatory_reporting": False,
            "specialists": ["InfectionControl"],
            "key_findings": ["MRSA", "CLABSI", "central line", "bundle compliance", "cluster"],
            "must_not_contain": [],
        },
    },

    # ── DEVICE MALFUNCTION ────────────────────────────────────────────────────

    {
        "id": "device_001_iv_pump",
        "category": "device_malfunction",
        "input": (
            "IV pump alarm failed to sound when the infusion line became occluded. "
            "Patient received no medication for 6 hours. Nurse discovered the occlusion "
            "during routine rounding. Pump model XYZ-500. No patient harm reported."
        ),
        "expected_output": {
            "event_type": "device_malfunction",
            "event_classification": "adverse_event",
            "severity": "medium",
            "harm_level": "none",
            "preventability": "probably_not_preventable",
            "mandatory_reporting": False,
            "specialists": [],
            "key_findings": ["IV pump", "alarm", "occlusion", "6 hours"],
            "must_not_contain": [],
        },
    },
    {
        "id": "device_002_ventilator",
        "category": "device_malfunction",
        "input": (
            "Ventilator low-pressure alarm did not activate when ET tube became dislodged "
            "during patient repositioning. Respiratory therapist noticed desaturation "
            "and manually ventilated patient. SpO2 dropped to 78% before recovery. "
            "Patient stabilized."
        ),
        "expected_output": {
            "event_type": "device_malfunction",
            "event_classification": "adverse_event",
            "severity": "critical",
            "harm_level": "temporary",
            "preventability": "probably_not_preventable",
            "mandatory_reporting": False,
            "specialists": [],
            "key_findings": ["ventilator", "alarm", "ET tube", "desaturation", "SpO2"],
            "must_not_contain": [],
        },
    },
    {
        "id": "device_003_near_miss",
        "category": "device_malfunction",
        "input": (
            "Biomedical engineering flagged that 12 defibrillators on the cardiac unit "
            "failed their scheduled self-test. Units removed from service immediately. "
            "No cardiac arrest occurred during the period. "
            "Manufacturer notified. Replacement units obtained."
        ),
        "expected_output": {
            "event_type": "device_malfunction",
            "event_classification": "unsafe_condition",
            "severity": "high",
            "harm_level": "none",
            "preventability": "probably_not_preventable",
            "mandatory_reporting": False,
            "specialists": [],
            "key_findings": ["defibrillator", "self-test", "failed", "cardiac unit"],
            "must_not_contain": [],
        },
    },

    # ── MULTI-SPECIALIST EVENTS ───────────────────────────────────────────────

    {
        "id": "multi_001_fall_med",
        "category": "multi_specialist",
        "input": (
            "Patient fell out of bed during night shift after receiving evening sedation. "
            "Fall was unwitnessed. Patient found confused on floor with laceration to arm. "
            "Sedation dose was higher than prescribed — pharmacist error identified."
        ),
        "expected_output": {
            "event_type": "patient_fall",
            "event_classification": "adverse_event",
            "severity": "high",
            "harm_level": "additional_treatment",
            "preventability": "preventable",
            "mandatory_reporting": False,
            "specialists": ["FallsPrevention", "MedicationSafety"],
            "key_findings": ["sedation", "overdose", "fall", "laceration"],
            "must_not_contain": [],
        },
    },
    {
        "id": "multi_002_inf_fall",
        "category": "multi_specialist",
        "input": (
            "Patient with PICC line developed fever and chills. "
            "Line was last changed 14 days ago. PICC site shows redness and tenderness. "
            "Blood culture drawn. Patient also found to have fallen earlier today with no injury."
        ),
        "expected_output": {
            "event_type": "infection_control",
            "event_classification": "adverse_event",
            "severity": "high",
            "harm_level": "additional_treatment",
            "preventability": "probably_preventable",
            "mandatory_reporting": False,
            "specialists": ["InfectionControl", "FallsPrevention"],
            "key_findings": ["PICC", "fever", "CLABSI", "fall"],
            "must_not_contain": [],
        },
    },

    # ── NEAR MISSES WITH ACTIVE RECOVERY (IOM: recovery = key distinguishing factor) ──

    {
        "id": "edge_001_near_miss_recovery",
        "category": "edge_case",
        "input": (
            "Nurse almost gave patient the wrong medication but caught the error "
            "before administration when the patient stated the pill looked different. "
            "Confirmed wrong drug pulled from Pyxis. No medication given. "
            "Incident documented. Pyxis cabinet override log reviewed."
        ),
        "expected_output": {
            "event_type": "medication_error",
            "event_classification": "near_miss",
            "severity": "medium",
            "harm_level": "none",
            "preventability": "preventable",
            "mandatory_reporting": False,
            "specialists": ["MedicationSafety"],
            "key_findings": ["near miss", "patient caught", "Pyxis", "no medication given"],
            "must_not_contain": [],
        },
    },
    {
        "id": "edge_002_visitor",
        "category": "edge_case",
        "input": (
            "Visitor reported slipping on a wet floor in the main lobby. "
            "No patient involved. Visitor declined medical evaluation. "
            "Wet floor sign was not in place."
        ),
        "expected_output": {
            "event_type": "patient_fall",
            "event_classification": "adverse_event",
            "severity": "low",
            "harm_level": "none",
            "preventability": "preventable",
            "mandatory_reporting": False,
            "specialists": ["FallsPrevention"],
            "key_findings": ["visitor", "wet floor", "lobby"],
            "must_not_contain": [],
        },
    },
    {
        "id": "edge_003_unlabeled_syringe",
        "category": "edge_case",
        "input": (
            "Staff member found an unlabeled syringe on the medication cart. "
            "Contents unknown. No patient exposure confirmed. "
            "Pharmacy investigating."
        ),
        "expected_output": {
            "event_type": "medication_error",
            "event_classification": "unsafe_condition",
            "severity": "medium",
            "harm_level": "none",
            "preventability": "preventable",
            "mandatory_reporting": False,
            "specialists": ["MedicationSafety"],
            "key_findings": ["unlabeled", "syringe", "unknown contents"],
            "must_not_contain": [],
        },
    },
    {
        "id": "edge_004_cascading",
        "category": "edge_case",
        "input": (
            "Patient developed pressure ulcer after nursing staff failed to reposition "
            "every 2 hours per protocol for 3 days. Root cause identified as short staffing "
            "and lack of repositioning documentation. Stage 2 wound noted on sacrum. "
            "Wound care team consulted."
        ),
        "expected_output": {
            "event_type": "infection_control",
            "event_classification": "adverse_event",
            "severity": "medium",
            "harm_level": "additional_treatment",
            "preventability": "preventable",
            "mandatory_reporting": False,
            "specialists": ["InfectionControl"],
            "key_findings": ["pressure ulcer", "repositioning", "protocol", "staffing"],
            "must_not_contain": [],
        },
    },
    {
        "id": "edge_005_communication_failure",
        "category": "edge_case",
        "input": (
            "Incoming shift nurse was not informed during handoff that patient had developed "
            "new allergy to sulfa drugs during the prior shift. Patient received sulfamethoxazole "
            "at 6am and developed rash. Allergy was documented in chart but not communicated verbally."
        ),
        "expected_output": {
            "event_type": "medication_error",
            "event_classification": "adverse_event",
            "severity": "high",
            "harm_level": "emotional_distress",
            "preventability": "preventable",
            "mandatory_reporting": False,
            "specialists": ["MedicationSafety"],
            "key_findings": ["handoff", "allergy", "sulfa", "communication"],
            "must_not_contain": [],
        },
    },
    {
        "id": "edge_006_multi_contributing_factors",
        "category": "edge_case",
        "input": (
            "Patient received wrong blood type during transfusion. Three contributing factors "
            "identified: (1) specimen label printed for wrong patient due to system glitch, "
            "(2) bedside nurse did not perform two-patient-identifier check, "
            "(3) blood bank issued unit without second verification. "
            "Patient developed transfusion reaction. ABO incompatibility confirmed."
        ),
        "expected_output": {
            "event_type": "medication_error",
            "event_classification": "adverse_event",
            "severity": "critical",
            "harm_level": "temporary",
            "preventability": "preventable",
            "mandatory_reporting": True,  # NQF SRE: wrong blood type transfusion
            "specialists": ["MedicationSafety"],
            "key_findings": ["wrong blood", "transfusion", "ABO incompatibility", "multiple contributing factors"],
            "must_not_contain": [],
        },
    },
    {
        "id": "edge_007_retained_instrument",
        "category": "edge_case",
        "input": (
            "Post-operative X-ray showed a retained surgical sponge in the abdomen following "
            "exploratory laparotomy. Patient taken back to OR for removal. "
            "Final sponge count at end of surgery was documented as correct. "
            "Count discrepancy under investigation."
        ),
        "expected_output": {
            "event_type": "device_malfunction",
            "event_classification": "adverse_event",
            "severity": "critical",
            "harm_level": "additional_treatment",
            "preventability": "probably_preventable",
            "mandatory_reporting": True,  # NQF SRE: retained instrument post-procedure
            "specialists": [],
            "key_findings": ["retained", "sponge", "laparotomy", "count", "OR"],
            "must_not_contain": [],
        },
    },
    {
        "id": "edge_008_neonatal",
        "category": "edge_case",
        "input": (
            "Neonate in NICU received morphine infusion at 10x the intended dose due to a "
            "decimal point error in the order (1.0mg instead of 0.1mg). "
            "Baby showed respiratory depression and required naloxone reversal. "
            "Stabilized after intervention."
        ),
        "expected_output": {
            "event_type": "medication_error",
            "event_classification": "adverse_event",
            "severity": "critical",
            "harm_level": "temporary",
            "preventability": "preventable",
            "mandatory_reporting": False,
            "specialists": ["MedicationSafety"],
            "key_findings": ["neonate", "morphine", "decimal", "10x dose", "naloxone"],
            "must_not_contain": [],
        },
    },
    {
        "id": "edge_009_wrong_site_surgery",
        "category": "edge_case",
        "input": (
            "Surgeon performed knee arthroscopy on the left knee. Consent form and surgical "
            "plan indicated right knee. Pre-operative site marking was not done per protocol. "
            "Error discovered by circulating nurse after procedure began. "
            "Patient notified. Incident under investigation."
        ),
        "expected_output": {
            "event_type": "device_malfunction",
            "event_classification": "adverse_event",
            "severity": "critical",
            "harm_level": "permanent",
            "preventability": "preventable",
            "mandatory_reporting": True,  # NQF SRE: wrong-site surgery
            "specialists": [],
            "key_findings": ["wrong site", "wrong knee", "site marking", "consent"],
            "must_not_contain": [],
        },
    },
]
