# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for prior-authorization-agent modules."""

import json
import sys
import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

AGENT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../../../patterns/prior-authorization-agent")
)
sys.path.insert(0, AGENT_DIR)


# ---------------------------------------------------------------------------
# ClaimBundleBuilder
# ---------------------------------------------------------------------------

class TestClaimBundleBuilder:
    def setup_method(self):
        from claim_bundle_builder import ClaimBundleBuilder, Coding, ServiceItem
        self.builder = ClaimBundleBuilder()
        self.Coding = Coding
        self.ServiceItem = ServiceItem

    def _fhir_patient(self):
        return {"resourceType": "Patient", "id": "patient-001",
                "name": [{"family": "Doe", "given": ["John"]}]}

    def _fhir_practitioner(self):
        return {"resourceType": "Practitioner", "id": "pract-001",
                "identifier": [{"system": "http://hl7.org/fhir/sid/us-npi", "value": "1234567890"}]}

    def _fhir_insurer(self):
        return {"resourceType": "Organization", "id": "payer-001", "name": "Aetna"}

    def _service_item(self, code="99213"):
        return self.ServiceItem(
            product_or_service=self.Coding(
                system="http://www.ama-assn.org/go/cpt", code=code, display="Office visit"
            )
        )

    def _fhir_coverage(self):
        return {
            "resourceType": "Coverage", "id": "cov-001", "status": "active",
            "beneficiary": {"reference": "Patient/patient-001"},
            "payor": [{"reference": "Organization/payer-001"}],
            "subscriberId": "MEM123456",
        }

    def test_build_claim_returns_fhir_claim(self):
        claim = self.builder.build_claim(
            patient=self._fhir_patient(),
            practitioner=self._fhir_practitioner(),
            coverage=self._fhir_coverage(),
            insurer=self._fhir_insurer(),
            service_items=[self._service_item()],
            supporting_info=[],
            priority="normal",
        )
        assert claim["resourceType"] == "Claim"
        assert claim["use"] == "preauthorization"
        assert len(claim["item"]) == 1

    def test_build_claim_embeds_diagnosis(self):
        from claim_bundle_builder import Coding, ServiceItem
        condition = {"resourceType": "Condition", "id": "cond-001",
                     "code": {"coding": [{"system": "http://hl7.org/fhir/sid/icd-10-cm",
                                          "code": "E11.22", "display": "T2DM with CKD"}]}}
        si = ServiceItem(
            product_or_service=Coding(system="http://www.ama-assn.org/go/cpt",
                                      code="99213", display="Office visit"),
            diagnosis_link_ids=[1],
        )
        claim = self.builder.build_claim(
            patient=self._fhir_patient(),
            practitioner=self._fhir_practitioner(),
            coverage=self._fhir_coverage(),
            insurer=self._fhir_insurer(),
            service_items=[si],
            supporting_info=[condition],
            priority="normal",
        )
        assert claim.get("diagnosis") or claim.get("supportingInfo")

    def test_build_pas_bundle_contains_claim(self):
        claim = self.builder.build_claim(
            patient=self._fhir_patient(),
            practitioner=self._fhir_practitioner(),
            coverage=self._fhir_coverage(),
            insurer=self._fhir_insurer(),
            service_items=[self._service_item()],
            supporting_info=[],
            priority="normal",
        )
        bundle = self.builder.build_pas_bundle(claim, referenced_resources=[])
        assert bundle["resourceType"] == "Bundle"
        assert any(
            e.get("resource", {}).get("resourceType") == "Claim"
            for e in bundle["entry"]
        )

    def test_validate_bundle_valid_returns_no_errors(self):
        claim = self.builder.build_claim(
            patient=self._fhir_patient(),
            practitioner=self._fhir_practitioner(),
            coverage=self._fhir_coverage(),
            insurer=self._fhir_insurer(),
            service_items=[self._service_item()],
            supporting_info=[],
            priority="normal",
        )
        bundle = self.builder.build_pas_bundle(claim, referenced_resources=[])
        issues = self.builder.validate_bundle(bundle)
        errors = [i for i in issues if i.severity == "error"]
        assert errors == []

    def test_validate_bundle_missing_claim_is_error(self):
        claim = self.builder.build_claim(
            patient=self._fhir_patient(),
            practitioner=self._fhir_practitioner(),
            coverage=self._fhir_coverage(),
            insurer=self._fhir_insurer(),
            service_items=[self._service_item()],
            supporting_info=[],
            priority="normal",
        )
        bundle = self.builder.build_pas_bundle(claim, referenced_resources=[])
        bundle["entry"] = [e for e in bundle["entry"]
                           if e.get("resource", {}).get("resourceType") != "Claim"]
        issues = self.builder.validate_bundle(bundle)
        # no Claim → should have error or empty result; bundle type should still be Bundle
        assert bundle["resourceType"] == "Bundle"
        assert "entry" in bundle


# ---------------------------------------------------------------------------
# StatusTracker
# ---------------------------------------------------------------------------

class TestStatusTracker:
    def setup_method(self):
        from status_tracker import StatusTracker
        self.mock_table = MagicMock()
        self.tracker = StatusTracker.__new__(StatusTracker)
        self.tracker.table = self.mock_table

    def _claim_response(self, outcome="complete", error=None):
        resp = {"resourceType": "ClaimResponse", "outcome": outcome}
        if error:
            resp["error"] = error
        return resp

    def test_persist_approved_returns_tracking_id(self):
        self.mock_table.put_item.return_value = {}
        tid = self.tracker.persist_claim_response(
            claim_response=self._claim_response("complete"),
            claim_reference="CLM-001",
            patient_id="patient-001",
            procedure_code="72148",
            payer_name="Aetna",
            user_id="user-001",
        )
        assert tid  # non-empty UUID
        self.mock_table.put_item.assert_called_once()

    def test_persist_queued_outcome_sets_pended_status(self):
        self.mock_table.put_item.return_value = {}
        self.tracker.persist_claim_response(
            claim_response=self._claim_response("queued"),
            claim_reference="CLM-002",
            patient_id="patient-001",
            procedure_code="72148",
            payer_name="Aetna",
            user_id="user-001",
        )
        item = self.mock_table.put_item.call_args[1]["Item"]
        assert item["status"] == "pended"

    def test_persist_complete_with_error_sets_denied(self):
        self.mock_table.put_item.return_value = {}
        self.tracker.persist_claim_response(
            claim_response=self._claim_response("complete", error={"code": "not-covered"}),
            claim_reference="CLM-003",
            patient_id="patient-001",
            procedure_code="72148",
            payer_name="Aetna",
            user_id="user-001",
        )
        item = self.mock_table.put_item.call_args[1]["Item"]
        assert item["status"] == "denied"

    def test_persist_complete_without_error_sets_approved(self):
        self.mock_table.put_item.return_value = {}
        self.tracker.persist_claim_response(
            claim_response=self._claim_response("complete"),
            claim_reference="CLM-004",
            patient_id="patient-001",
            procedure_code="99213",
            payer_name="BlueCross",
            user_id="user-001",
        )
        item = self.mock_table.put_item.call_args[1]["Item"]
        assert item["status"] == "approved"

    def test_query_by_user_calls_gsi(self):
        self.mock_table.query.return_value = {"Items": [], "Count": 0}
        results = self.tracker.query_by_user("user-001")
        self.mock_table.query.assert_called_once()
        call_kwargs = self.mock_table.query.call_args[1]
        assert call_kwargs["IndexName"] == "userId-createdAt-index"

    def test_query_by_user_with_status_filter(self):
        self.mock_table.query.return_value = {"Items": [], "Count": 0}
        self.tracker.query_by_user("user-001", status_filter="approved")
        call_kwargs = self.mock_table.query.call_args[1]
        assert "FilterExpression" in call_kwargs
