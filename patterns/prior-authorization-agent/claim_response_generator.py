# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
ClaimResponse Generator module for Da Vinci PAS alignment.

Maps the Prior Authorization Agent's authorization decision to a FHIR
ClaimResponse resource conforming to the Da Vinci PAS ClaimResponse profile.
Pure-function module imported by the Prior Authorization Agent.
"""

import uuid
from datetime import datetime, timezone


# Standard FHIR coding system URIs
CLAIM_TYPE_SYSTEM = "http://terminology.hl7.org/CodeSystem/claim-type"
ADJUDICATION_SYSTEM = "http://terminology.hl7.org/CodeSystem/adjudication"
X12_CLAIM_ADJUSTMENT_REASON_SYSTEM = (
    "https://x12.org/codes/claim-adjustment-reason-codes"
)
REVIEW_ACTION_EXTENSION_URL = (
    "http://hl7.org/fhir/us/davinci-pas/StructureDefinition/extension-reviewAction"
)

VALID_DECISIONS = {"approved", "denied", "pended"}


class ClaimResponseGenerator:
    """
    Generates FHIR ClaimResponse resources from authorization decisions.

    Maps approved/denied/pended decisions to the appropriate FHIR outcome,
    preAuthRef, error entries, and extensions per the Da Vinci PAS IG.
    """

    def generate(
        self,
        claim_reference: str,
        patient_reference: str,
        insurer_reference: str,
        decision: str,
        disposition: str,
        pre_auth_ref: str | None = None,
        error_code: str | None = None,
        review_action: str | None = None,
    ) -> dict:
        """
        Generate a FHIR ClaimResponse resource.

        Args:
            claim_reference: Reference to the original Claim (e.g. "Claim/<id>")
            patient_reference: Reference to the Patient (e.g. "Patient/<id>")
            insurer_reference: Reference to the insurer Organization
            decision: One of "approved", "denied", "pended"
            disposition: Human-readable rationale for the decision
            pre_auth_ref: Authorization reference number (used for approved;
                          auto-generated if not provided)
            error_code: X12 claim adjustment reason code (required for denied)
            review_action: Review action code (used for pended)

        Returns:
            FHIR ClaimResponse resource dict

        Raises:
            ValueError: If decision is not in {approved, denied, pended}
        """
        if decision not in VALID_DECISIONS:
            raise ValueError(
                f"Invalid decision '{decision}'. "
                f"Must be one of: {', '.join(sorted(VALID_DECISIONS))}"
            )

        response_id = str(uuid.uuid4())

        claim_response: dict = {
            "resourceType": "ClaimResponse",
            "id": response_id,
            "status": "active",
            "type": {
                "coding": [
                    {
                        "system": CLAIM_TYPE_SYSTEM,
                        "code": "professional",
                    }
                ]
            },
            "use": "preauthorization",
            "patient": {"reference": patient_reference},
            "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "insurer": {"reference": insurer_reference},
            "request": {"reference": claim_reference},
            "disposition": disposition,
        }

        if decision == "approved":
            claim_response["outcome"] = "complete"
            claim_response["preAuthRef"] = pre_auth_ref or f"PA-{uuid.uuid4().hex[:12].upper()}"

        elif decision == "denied":
            claim_response["outcome"] = "complete"
            claim_response["error"] = [
                {
                    "code": {
                        "coding": [
                            {
                                "system": X12_CLAIM_ADJUSTMENT_REASON_SYSTEM,
                                "code": error_code or "96",
                                "display": _get_error_display(error_code or "96"),
                            }
                        ]
                    }
                }
            ]

        elif decision == "pended":
            claim_response["outcome"] = "queued"
            claim_response["extension"] = [
                {
                    "url": REVIEW_ACTION_EXTENSION_URL,
                    "valueCodeableConcept": {
                        "coding": [
                            {
                                "system": REVIEW_ACTION_EXTENSION_URL,
                                "code": review_action or "pend",
                            }
                        ]
                    },
                }
            ]

        return claim_response


def _get_error_display(code: str) -> str:
    """Return a human-readable display string for common X12 adjustment reason codes."""
    displays = {
        "1": "Deductible Amount",
        "2": "Coinsurance Amount",
        "3": "Co-payment Amount",
        "4": "The procedure code is inconsistent with the modifier used",
        "50": "Non-covered services",
        "96": "Non-covered charge(s)",
        "97": "Payment adjusted: benefit for this service not provided",
        "197": "Precertification/authorization/notification absent",
        "198": "Precertification/authorization exceeded",
    }
    return displays.get(code, f"Adjustment reason code {code}")
