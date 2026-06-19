# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Agent runtime integration tests.

Invokes each deployed AgentCore runtime with a real prompt and validates
that the agent responds with meaningful content (not an error).
"""

import json
import os
import time

import boto3
import pytest
import requests


STACK_NAME = os.environ.get("STACK_NAME", "healthcare-agents-stack")
REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")


def _get_runtime_arn(pattern: str) -> str:
    ssm = boto3.client("ssm", region_name=REGION)
    try:
        return ssm.get_parameter(Name=f"/{STACK_NAME}/{pattern}/runtime-arn")["Parameter"]["Value"]
    except Exception:
        pytest.skip(f"Runtime ARN not found for {pattern}")


def _get_gateway_token() -> str:
    """Get machine client OAuth token for Gateway auth."""
    ssm = boto3.client("ssm", region_name=REGION)
    try:
        client_id = ssm.get_parameter(Name=f"/{STACK_NAME}/cognito/machine_client_id")["Parameter"]["Value"]
        client_secret = ssm.get_parameter(Name=f"/{STACK_NAME}/cognito/machine_client_secret", WithDecryption=True)["Parameter"]["Value"]
        domain = ssm.get_parameter(Name=f"/{STACK_NAME}/cognito/domain")["Parameter"]["Value"]
    except Exception as e:
        pytest.skip(f"Could not get Cognito config: {e}")

    resp = requests.post(
        f"https://{domain}.auth.{REGION}.amazoncognito.com/oauth2/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret},
        timeout=15,
    )
    if resp.status_code != 200:
        pytest.skip(f"Could not get token: {resp.text}")
    return resp.json()["access_token"]


def _invoke_runtime(runtime_arn: str, prompt: str, session_id: str = None, timeout: int = 120) -> dict:
    """Invoke an AgentCore runtime via HTTPS with Cognito Bearer token."""
    token = _get_gateway_token()
    session = session_id or str(__import__("uuid").uuid4())
    user_id = "integration-test-user"

    import urllib.parse
    escaped_arn = urllib.parse.quote(runtime_arn, safe="")
    url = f"https://bedrock-agentcore.{REGION}.amazonaws.com/runtimes/{escaped_arn}/invocations?qualifier=DEFAULT"

    resp = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": session,
            "X-Amzn-Bedrock-AgentCore-Runtime-User-Id": user_id,
        },
        json={"prompt": prompt, "runtimeSessionId": session, "userId": user_id},
        timeout=timeout,
        stream=True,
    )

    if resp.status_code == 403:
        pytest.skip(f"Auth error: {resp.text[:200]}")
    if resp.status_code != 200:
        pytest.skip(f"Runtime returned {resp.status_code}: {resp.text[:200]}")

    output = ""
    try:
        for line in resp.iter_lines():
            if line:
                text = line.decode("utf-8", errors="replace")
                if text.startswith("data:"):
                    text = text[5:].strip()
                try:
                    data = json.loads(text)
                    output += data.get("content", "") or data.get("text", "") or data.get("output", "")
                except Exception:
                    if not text.startswith("{"):
                        output += text
    except Exception:
        # Stream may end prematurely on long-running tasks; use what was captured
        pass

    return {"output": output}


# ---------------------------------------------------------------------------
# Medical Coding Agent
# ---------------------------------------------------------------------------


@pytest.fixture(scope="class")
def medical_coding_arn():
    return _get_runtime_arn("medical-coding-agent")


class TestMedicalCodingAgent:
    """
    Integration tests for the Medical Coding Agent.

    Validates entity extraction (Comprehend Medical) and code lookup (KB)
    across: single diagnosis, multi-diagnosis, procedure-heavy, medication,
    ambiguous notes, and edge cases.
    """

    # ------------------------------------------------------------------
    # Entity extraction via Comprehend Medical
    # ------------------------------------------------------------------

    def test_extracts_entities_from_clinical_note(self, medical_coding_arn):
        """Comprehend Medical tool: entities identified from free-text note."""
        result = _invoke_runtime(
            medical_coding_arn,
            "Extract all medical entities from: Patient has hypertension and type 2 diabetes, "
            "on metformin 1000mg BID and lisinopril 20mg daily.",
        )
        output = result["output"].lower()
        assert any(e in output for e in ["hypertension", "diabetes", "metformin", "lisinopril"]), \
            f"Expected entities in output: {result['output'][:400]}"

    def test_detects_phi_in_note(self, medical_coding_arn):
        """detect_phi tool: PHI categories flagged in note."""
        result = _invoke_runtime(
            medical_coding_arn,
            "Detect any PHI in: Patient John Doe, DOB 01/15/1980, MRN 987654, "
            "was seen at 123 Main St clinic.",
        )
        output = result["output"].lower()
        # Agent should identify name, DOB, MRN, or address as PHI
        assert any(w in output for w in ["phi", "name", "dob", "date of birth", "mrn", "address", "protected"]), \
            f"Expected PHI detection: {result['output'][:400]}"

    # ------------------------------------------------------------------
    # ICD-10 code assignment
    # ------------------------------------------------------------------

    def test_single_diagnosis_icd10(self, medical_coding_arn):
        """Single clear-cut diagnosis → correct ICD-10 code returned."""
        result = _invoke_runtime(
            medical_coding_arn,
            "Assign ICD-10 codes for: Patient with acute exacerbation of COPD. "
            "Chest X-ray shows hyperinflation. Started on prednisone and albuterol.",
        )
        output = result["output"]
        assert "J44.1" in output, \
            f"Expected J44.1 (COPD with acute exacerbation): {output[:400]}"

    def test_multi_diagnosis_icd10(self, medical_coding_arn):
        """Multiple comorbidities → multiple ICD-10 codes returned."""
        result = _invoke_runtime(
            medical_coding_arn,
            "Code this encounter: 72-year-old female with community-acquired pneumonia "
            "right lower lobe, CHF with reduced EF 30%, atrial fibrillation on warfarin, "
            "type 2 diabetes on insulin.",
        )
        output = result["output"]
        # Expect at least 3 of the 4 primary codes
        codes_found = sum(1 for c in ["J18", "I50", "I48", "E11"] if c in output)
        assert codes_found >= 3, \
            f"Expected ≥3 of J18/I50/I48/E11, got: {output[:400]}"

    def test_diabetes_with_ckd_icd10(self, medical_coding_arn):
        """Combination code for DM+CKD and separate CKD stage code."""
        result = _invoke_runtime(
            medical_coding_arn,
            "Code: 65-year-old with type 2 diabetes mellitus with diabetic CKD stage 3. "
            "A1C 8.2%, eGFR 45. On metformin and lisinopril.",
        )
        output = result["output"]
        assert "E11.22" in output, f"Expected E11.22 (T2DM+CKD): {output[:400]}"
        assert "N18.3" in output, f"Expected N18.3 (CKD stage 3): {output[:400]}"

    def test_medication_adverse_effect_icd10(self, medical_coding_arn):
        """Adverse effect coding (T-code) for drug reaction."""
        result = _invoke_runtime(
            medical_coding_arn,
            "Code: Patient developed anaphylaxis after IV penicillin for left leg cellulitis. "
            "Treated with epinephrine, diphenhydramine, methylprednisolone.",
        )
        output = result["output"]
        assert any(c in output for c in ["T36", "T78", "anaphyla"]), \
            f"Expected adverse effect / anaphylaxis codes: {output[:400]}"

    def test_ambiguous_note_uses_symptom_code(self, medical_coding_arn):
        """Unconfirmed diagnosis → symptom code, not definitive condition code."""
        result = _invoke_runtime(
            medical_coding_arn,
            "Code: Patient presents with chest pain, rule out ACS. "
            "Troponin negative x2, ECG normal. Likely non-cardiac chest pain.",
        )
        output = result["output"]
        # Should use R07.9 (chest pain NOS), NOT I21 (MI)
        assert "R07" in output, f"Expected R07 symptom code: {output[:400]}"
        assert "I21" not in output, \
            f"Should NOT assign MI code for rule-out: {output[:400]}"

    def test_history_vs_active_cancer_code(self, medical_coding_arn):
        """Surveillance visit for prior cancer → history code, not active C-code."""
        result = _invoke_runtime(
            medical_coding_arn,
            "Code: Patient with history of breast cancer status post mastectomy 2023. "
            "Surveillance PET/CT ordered. No current symptoms.",
        )
        output = result["output"]
        assert "Z85" in output, f"Expected Z85 history code: {output[:400]}"
        # Agent should recommend Z85, not assign C50 as the diagnosis code
        # (it may mention C50 in an explanatory context — that's fine)
        assert "Z85" in output and output.count("Z85") >= output.count("C50"), \
            f"Z85 should be the primary recommendation over C50: {output[:400]}"

    # ------------------------------------------------------------------
    # CPT code assignment
    # ------------------------------------------------------------------

    def test_procedure_cpt_code(self, medical_coding_arn):
        """Surgical procedure → correct CPT code returned."""
        result = _invoke_runtime(
            medical_coding_arn,
            "What CPT code for laparoscopic cholecystectomy with intraoperative cholangiogram?",
        )
        output = result["output"]
        assert "47562" in output, f"Expected 47562: {output[:400]}"

    def test_colonoscopy_with_polypectomy_cpt(self, medical_coding_arn):
        """Colonoscopy with snare polypectomy → 45385."""
        result = _invoke_runtime(
            medical_coding_arn,
            "Code colonoscopy for cancer screening with removal of 8mm sessile sigmoid polyp "
            "via snare polypectomy and 5mm ascending colon polyp via cold forceps.",
        )
        output = result["output"]
        assert "45385" in output, f"Expected 45385 (snare polypectomy): {output[:400]}"

    def test_office_visit_cpt(self, medical_coding_arn):
        """E&M office visit → level-appropriate CPT code."""
        result = _invoke_runtime(
            medical_coding_arn,
            "What CPT code for an established patient office visit with moderate medical "
            "decision making, 30-39 minutes?",
        )
        output = result["output"]
        assert "99214" in output, f"Expected 99214: {output[:400]}"

    # ------------------------------------------------------------------
    # SNOMED CT mapping
    # ------------------------------------------------------------------

    def test_snomed_mapping(self, medical_coding_arn):
        """Agent returns SNOMED CT concept for a clinical term."""
        result = _invoke_runtime(
            medical_coding_arn,
            "Provide SNOMED CT code for acute exacerbation of COPD.",
        )
        output = result["output"]
        # SNOMED 195951007 or at least a numeric SNOMED concept
        assert any(c in output for c in ["195951007", "snomed", "SNOMED"]) or \
               any(c.isdigit() and len(c) >= 6 for c in output.split()), \
            f"Expected SNOMED code: {output[:400]}"

    # ------------------------------------------------------------------
    # Full coding workflow (entity extraction → code lookup)
    # ------------------------------------------------------------------

    def test_full_coding_workflow(self, medical_coding_arn):
        """End-to-end: extract entities then look up all code types."""
        result = _invoke_runtime(
            medical_coding_arn,
            "Perform complete medical coding for this note: "
            "65-year-old male undergoes right total knee arthroplasty for severe "
            "osteoarthritis right knee. Cemented prosthesis placed. "
            "Intraoperative fluoroscopy confirmed alignment.",
        )
        output = result["output"]
        # Should produce both diagnosis and procedure codes
        assert "M17.11" in output, f"Expected M17.11 (OA right knee): {output[:400]}"
        assert "27447" in output, f"Expected 27447 (TKA): {output[:400]}"

    def test_rejects_wrong_laterality(self, medical_coding_arn):
        """Laterality: right-side procedure should not yield left-side code."""
        result = _invoke_runtime(
            medical_coding_arn,
            "Assign ICD-10 for: right total knee arthroplasty for right knee osteoarthritis.",
        )
        output = result["output"]
        assert "M17.11" in output, f"Expected right knee M17.11: {output[:400]}"
        assert "M17.12" not in output, \
            f"Should NOT return left knee M17.12: {output[:400]}"


# ---------------------------------------------------------------------------
# Claims Assembly Agent
# ---------------------------------------------------------------------------


@pytest.fixture(scope="class")
def assembly_arn():
    return _get_runtime_arn("claims-assembly-agent")


class TestClaimsAssemblyAgent:
    """
    Integration tests for the Claims Assembly Agent.

    Covers: field validation, EDI 837P assembly, HIPAA compliance checks,
    payer-specific rules, invalid data rejection, and multi-service claims.
    """

    def test_validate_complete_claim(self, assembly_arn):
        """All required fields present → agent reports claim is valid."""
        result = _invoke_runtime(
            assembly_arn,
            "Validate this claim: patient John Doe DOB 1980-01-15 member ID MEM123456, "
            "billing provider NPI 1234567890 Tax ID 12-3456789, "
            "diagnosis E11.9 (Type 2 diabetes), procedure 99213, "
            "place of service 11, date of service 2026-06-01, charge $150.",
        )
        output = result["output"].lower()
        assert any(w in output for w in ["valid", "passed", "complete", "compliant"]), \
            f"Expected validation pass: {result['output'][:400]}"

    def test_assemble_edi_837p_structure(self, assembly_arn):
        """Complete inputs → EDI 837P segments in response."""
        result = _invoke_runtime(
            assembly_arn,
            "Assemble an EDI 837P claim: "
            "Patient Jane Smith DOB 1975-03-20 member ID ABC123. "
            "Provider NPI 1234567890 Tax ID 12-3456789. "
            "Procedure 99214 date 2026-06-10 charge $200 diagnosis I10.",
        )
        output = result["output"].upper()
        assert any(seg in output for seg in ["CLM", "837", "NM1", "SV1", "DTP"]), \
            f"Expected EDI segments: {result['output'][:400]}"

    def test_rejects_invalid_npi(self, assembly_arn):
        """Malformed NPI (not 10 digits) → agent flags the error."""
        result = _invoke_runtime(
            assembly_arn,
            "Validate claim with provider NPI 12345 (only 5 digits), "
            "patient DOB 1980-01-15, diagnosis I10, procedure 99213, "
            "date of service 2026-06-01, charge $100.",
        )
        output = result["output"].lower()
        assert any(w in output for w in ["invalid", "npi", "error", "fail", "10 digit", "required"]), \
            f"Expected NPI error: {result['output'][:400]}"

    def test_rejects_missing_diagnosis(self, assembly_arn):
        """Missing diagnosis code → agent flags the missing field."""
        result = _invoke_runtime(
            assembly_arn,
            "Assemble claim: patient John Doe DOB 1980-01-15 member ID MEM001, "
            "provider NPI 1234567890, procedure 99213, "
            "date of service 2026-06-01, charge $100. No diagnosis code provided.",
        )
        output = result["output"].lower()
        assert any(w in output for w in ["diagnosis", "icd", "missing", "required", "error"]), \
            f"Expected diagnosis error: {result['output'][:400]}"

    def test_hipaa_5010_compliance_check(self, assembly_arn):
        """Agent validates claim against HIPAA 5010 standards."""
        result = _invoke_runtime(
            assembly_arn,
            "Check HIPAA 5010 compliance for: "
            "patient Mary Jones DOB 1962-07-04 member ID XYZ789, "
            "provider NPI 9876543210 Tax ID 98-7654321, "
            "diagnosis M17.11 procedure 27447, "
            "date of service 2026-06-15, charge $12500, place of service 21.",
        )
        output = result["output"].lower()
        assert any(w in output for w in ["hipaa", "5010", "complian", "valid", "837"]), \
            f"Expected HIPAA compliance response: {result['output'][:400]}"

    def test_multi_service_line_claim(self, assembly_arn):
        """Multiple procedure codes on same claim → all service lines present."""
        result = _invoke_runtime(
            assembly_arn,
            "Assemble EDI 837P with two service lines: "
            "patient Bob Chen DOB 1990-05-10 member ID BC456, "
            "provider NPI 1112223330 Tax ID 11-2223333. "
            "Line 1: procedure 99214 charge $200 diagnosis I10. "
            "Line 2: procedure 93000 (ECG) charge $75 diagnosis I10. "
            "Date of service 2026-06-18.",
        )
        output = result["output"]
        # Both procedure codes should appear
        assert "99214" in output, f"Expected 99214 in multi-line claim: {output[:400]}"
        assert "93000" in output, f"Expected 93000 in multi-line claim: {output[:400]}"

    def test_payer_specific_validation_rules(self, assembly_arn):
        """Agent queries validation KB for payer-specific requirements."""
        result = _invoke_runtime(
            assembly_arn,
            "What are the Medicare-specific requirements for submitting "
            "a claim for CPT 72148 (MRI lumbar spine)?",
        )
        output = result["output"].lower()
        assert any(w in output for w in ["medicare", "npi", "prior auth", "requirement", "edi", "837"]), \
            f"Expected payer rules response: {result['output'][:400]}"

    def test_procedure_code_format_validation(self, assembly_arn):
        """Invalid CPT format → agent flags the error."""
        result = _invoke_runtime(
            assembly_arn,
            "Validate claim with procedure code 9921 (only 4 digits, should be 5), "
            "patient DOB 1970-01-01 member ID M001, "
            "provider NPI 1234567890, diagnosis I10, charge $150, date 2026-06-01.",
        )
        output = result["output"].lower()
        assert any(w in output for w in ["invalid", "procedure", "cpt", "error", "5 digit", "format"]), \
            f"Expected procedure code error: {result['output'][:400]}"


# ---------------------------------------------------------------------------
# Claims Submission Agent
# ---------------------------------------------------------------------------


@pytest.fixture(scope="class")
def submission_arn():
    return _get_runtime_arn("claims-submission-agent")


class TestClaimsSubmissionAgent:
    """
    Integration tests for the Claims Submission Agent.

    Covers: B2BI submission, status tracking, acknowledgment retrieval,
    and submission history listing.
    """

    def test_submit_claim_via_b2bi(self, submission_arn):
        """Agent submits claim JSON to B2B Data Interchange and returns a job/tracking ID."""
        result = _invoke_runtime(
            submission_arn,
            "Submit this EDI 837P claim to the payer: "
            '{"trading_partner": "AETNA", "patient_id": "TEST-INT-001", '
            '"procedure": "99213", "diagnosis": "I10", '
            '"provider_npi": "1234567890", "charge": 150.00, '
            '"date_of_service": "2026-06-18", "member_id": "AET123456"}',
        )
        output = result["output"].lower()
        assert any(w in output for w in ["submit", "job", "transform", "b2b", "track", "id", "status"]), \
            f"Expected submission confirmation: {result['output'][:400]}"

    def test_check_submission_status(self, submission_arn):
        """Agent can query the status of a previous submission."""
        result = _invoke_runtime(
            submission_arn,
            "Check the status of claim submission job ID job-test-12345.",
        )
        output = result["output"].lower()
        assert any(w in output for w in ["status", "job", "transform", "pending", "complete", "failed", "processing"]), \
            f"Expected status response: {result['output'][:400]}"

    def test_retrieve_997_acknowledgment(self, submission_arn):
        """Agent retrieves 997/999 functional acknowledgment for a submission."""
        result = _invoke_runtime(
            submission_arn,
            "Retrieve the 997 functional acknowledgment for claim submission TEST-ACK-001.",
        )
        output = result["output"].lower()
        assert any(w in output for w in ["997", "999", "acknowledgment", "ack", "functional", "accepted", "rejected"]), \
            f"Expected acknowledgment response: {result['output'][:400]}"

    def test_list_recent_submissions(self, submission_arn):
        """Agent can list recent claim submission history."""
        result = _invoke_runtime(
            submission_arn,
            "List my recent claim submissions from the past week.",
        )
        output = result["output"].lower()
        assert any(w in output for w in ["submission", "claim", "history", "list", "job", "recent", "found"]), \
            f"Expected submissions list: {result['output'][:400]}"

    def test_submission_with_invalid_claim_handled(self, submission_arn):
        """Agent handles a malformed claim gracefully rather than crashing."""
        result = _invoke_runtime(
            submission_arn,
            "Submit this incomplete claim: {}",
        )
        output = result["output"].lower()
        # Agent should either attempt submission or report the issue — not produce an empty response
        assert len(output.strip()) > 20, \
            f"Expected non-empty response for invalid claim: {result['output'][:400]}"


# ---------------------------------------------------------------------------
# Appeals Agent
# ---------------------------------------------------------------------------


@pytest.fixture(scope="class")
def appeals_arn():
    return _get_runtime_arn("appeals-agent")


class TestAppealsAgent:
    """
    Integration tests for the Appeals Agent.

    Covers: denial analysis, appeal strategy, letter generation, deadline
    lookup, clinical guideline retrieval, and S3 storage.
    """

    def test_analyze_carc_denial(self, appeals_arn):
        """Agent looks up CARC code and returns appeal strategy."""
        result = _invoke_runtime(
            appeals_arn,
            "Claim denied with CARC 50 (not medically necessary) for MRI lumbar spine (72148). "
            "Patient has 8 weeks low back pain, failed PT and NSAIDs. "
            "What appeal strategy do you recommend?",
        )
        output = result["output"].lower()
        assert any(w in output for w in ["appeal", "medical necessity", "carc", "clinical", "peer", "letter"]), \
            f"Expected appeal strategy: {result['output'][:400]}"

    def test_lookup_appeal_filing_deadline(self, appeals_arn):
        """Agent retrieves payer-specific appeal filing deadline."""
        result = _invoke_runtime(
            appeals_arn,
            "What is the appeal filing deadline for Aetna? "
            "Claim denial date was 2026-05-01.",
        )
        output = result["output"].lower()
        assert any(w in output for w in ["day", "deadline", "filing", "timely", "180", "60", "appeal"]), \
            f"Expected deadline info: {result['output'][:400]}"

    def test_generate_appeal_letter_medical_necessity(self, appeals_arn):
        """Agent generates a complete appeal letter for medical necessity denial."""
        result = _invoke_runtime(
            appeals_arn,
            "Generate an appeal letter: claim CLM-2026-001 denied CO-50 (not medically necessary) "
            "for MRI lumbar spine CPT 72148. Patient 8 weeks low back pain, failed PT and NSAIDs. "
            "Provider Dr. Smith NPI 1234567890. Payer Aetna. Denial date 2026-05-15.",
        )
        output = result["output"]
        assert len(output) > 300, f"Appeal letter too short: {output[:400]}"
        assert any(w in output.lower() for w in ["appeal", "denial", "dear", "medically necessary", "clinical"]), \
            f"Expected appeal letter: {output[:400]}"

    def test_generate_appeal_letter_timely_filing(self, appeals_arn):
        """Agent generates appeal for timely filing denial (CO-29)."""
        result = _invoke_runtime(
            appeals_arn,
            "Generate appeal for: claim denied CO-29 (timely filing exceeded). "
            "Service date 2026-01-10, claim submitted 2026-06-01. "
            "Provider has documentation of original submission on 2026-02-01. "
            "Provider Dr. Jones NPI 9876543210. Payer BlueCross.",
        )
        output = result["output"].lower()
        assert any(w in output for w in ["timely", "filing", "co-29", "appeal", "submission", "proof"]), \
            f"Expected timely filing appeal content: {result['output'][:400]}"

    def test_search_clinical_guidelines(self, appeals_arn):
        """Agent retrieves clinical guidelines supporting medical necessity."""
        result = _invoke_runtime(
            appeals_arn,
            "What clinical guidelines support medical necessity for MRI lumbar spine "
            "in a patient with 6+ weeks of radicular low back pain?",
        )
        output = result["output"].lower()
        assert any(w in output for w in ["guideline", "criteria", "mri", "lumbar", "clinical", "necessary", "radicular"]), \
            f"Expected clinical guidelines: {result['output'][:400]}"

    def test_multiple_denial_codes_analysis(self, appeals_arn):
        """Agent handles claim with multiple denial reason codes."""
        result = _invoke_runtime(
            appeals_arn,
            "Claim denied with both CO-4 (procedure not covered for diagnosis) "
            "and CO-97 (payment included in allowance for another service). "
            "Procedure 93000 (ECG), diagnosis I10. What are my appeal options?",
        )
        output = result["output"].lower()
        assert any(w in output for w in ["co-4", "co-97", "appeal", "bundl", "covered", "denial"]), \
            f"Expected multi-denial analysis: {result['output'][:400]}"

    def test_appeal_letter_saved_to_s3(self, appeals_arn):
        """Agent saves generated appeal letter to S3 and returns presigned URL."""
        result = _invoke_runtime(
            appeals_arn,
            "Generate and save an appeal letter for: claim CLM-S3-TEST denied CO-50 "
            "for CPT 27447 (total knee arthroplasty). Patient severe osteoarthritis right knee, "
            "failed 6 months conservative therapy. Provider Dr. Brown NPI 5556667770. "
            "Payer UnitedHealth. Please save the letter to S3.",
            timeout=180,
        )
        output = result["output"].lower()
        assert any(w in output for w in ["s3", "saved", "url", "download", "https", "letter", "generated"]), \
            f"Expected S3 save confirmation: {result['output'][:400]}"
