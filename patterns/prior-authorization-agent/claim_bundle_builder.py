# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Claim Bundle Builder module for Da Vinci PAS alignment.

Assembles FHIR Claim resources (use=preauthorization) and PAS Bundles
containing all referenced supporting resources. Pure-function module
imported by the Prior Authorization Agent.
"""

import json
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Coding:
    """FHIR Coding data type."""

    system: str
    code: str
    display: str | None = None


@dataclass
class ServiceItem:
    """Represents a single service line item for a Claim."""

    product_or_service: Coding  # CPT or HCPCS
    diagnosis_link_ids: list[int] = field(default_factory=list)
    quantity: float | None = None
    unit_price: float | None = None


@dataclass
class OperationOutcomeIssue:
    """FHIR OperationOutcome issue entry."""

    severity: str  # "error" | "warning" | "information"
    code: str
    diagnostics: str


# Standard FHIR coding system URIs
CPT_SYSTEM = "http://www.ama-assn.org/go/cpt"
HCPCS_SYSTEM = "https://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets"
ICD10CM_SYSTEM = "http://hl7.org/fhir/sid/icd-10-cm"
LOINC_SYSTEM = "http://loinc.org"
SNOMED_SYSTEM = "http://snomed.info/sct"
CLAIM_TYPE_SYSTEM = "http://terminology.hl7.org/CodeSystem/claim-type"
PROCESS_PRIORITY_SYSTEM = "http://terminology.hl7.org/CodeSystem/processpriority"
PAS_SUPPORTING_INFO_SYSTEM = (
    "http://hl7.org/fhir/us/davinci-pas/CodeSystem/PASSupportingInfoType"
)

VALID_PRIORITIES = {"normal", "urgent", "emergency"}

# Map resource types to supportingInfo category codes
_RESOURCE_TYPE_TO_CATEGORY = {
    "Condition": "patientEvent",
    "MedicationRequest": "patientEvent",
    "Observation": "patientEvent",
}


def _load_code_reference(file_path: str) -> dict[str, dict[str, str]]:
    """
    Parse a medical codes reference file into a lookup dict.

    Returns a dict keyed by lowercase title/synonyms mapping to
    {"code": ..., "title": ...}.
    """
    lookup: dict[str, dict[str, str]] = {}
    if not os.path.isfile(file_path):
        return lookup

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    entries = content.split("---")
    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue
        code_match = re.search(r"^Code:\s*(.+)$", entry, re.MULTILINE)
        title_match = re.search(r"^Title:\s*(.+)$", entry, re.MULTILINE)
        includes_match = re.search(r"^(?:Includes|Synonyms):\s*(.+)$", entry, re.MULTILINE)

        if not code_match or not title_match:
            continue

        code_val = code_match.group(1).strip()
        title_val = title_match.group(1).strip()
        record = {"code": code_val, "title": title_val}

        # Index by title
        lookup[title_val.lower()] = record

        # Index by synonyms/includes
        if includes_match:
            for synonym in includes_match.group(1).split(","):
                synonym = synonym.strip().lower()
                if synonym:
                    lookup[synonym] = record

    return lookup


class ClaimBundleBuilder:
    """
    Builds FHIR Claim resources and PAS Bundles conforming to the
    Da Vinci PAS Implementation Guide.
    """

    def __init__(self, data_dir: str | None = None):
        """
        Initialize with path to medical codes reference data.

        Args:
            data_dir: Path to `data/medical-codes-data/` directory.
                      Defaults to `data/medical-codes-data/` relative to repo root.
        """
        if data_dir is None:
            # Default: resolve relative to this file's location
            module_dir = os.path.dirname(os.path.abspath(__file__))
            data_dir = os.path.join(module_dir, "..", "..", "data", "medical-codes-data")

        self._data_dir = os.path.normpath(data_dir)
        self._code_lookups: dict[str, dict[str, dict[str, str]]] = {}

    def _get_code_lookup(self, target_system: str) -> dict[str, dict[str, str]]:
        """Lazy-load and cache code reference data for a target system."""
        if target_system in self._code_lookups:
            return self._code_lookups[target_system]

        system_to_dir = {
            CPT_SYSTEM: "cpt",
            HCPCS_SYSTEM: "cpt",  # HCPCS shares the CPT reference file
            ICD10CM_SYSTEM: "icd10cm",
            LOINC_SYSTEM: "snomed",  # LOINC uses snomed reference as fallback
            SNOMED_SYSTEM: "snomed",
        }

        dir_name = system_to_dir.get(target_system)
        if not dir_name:
            self._code_lookups[target_system] = {}
            return {}

        file_path = os.path.join(self._data_dir, dir_name, "common-codes.txt")
        lookup = _load_code_reference(file_path)
        self._code_lookups[target_system] = lookup
        return lookup

    def map_code(self, code_text: str, target_system: str) -> Coding | None:
        """
        Map free-text code description to a standard coding system.

        Args:
            code_text: Free-text description of the code (e.g. "Type 2 diabetes")
            target_system: Target FHIR coding system URI

        Returns:
            Coding with the matched code, or None if no match found.
        """
        lookup = self._get_code_lookup(target_system)
        if not lookup:
            return None

        normalized = code_text.strip().lower()

        # Exact match
        if normalized in lookup:
            record = lookup[normalized]
            return Coding(system=target_system, code=record["code"], display=record["title"])

        # Substring match: check if any key is contained in the text or vice versa
        for key, record in lookup.items():
            if key in normalized or normalized in key:
                return Coding(system=target_system, code=record["code"], display=record["title"])

        return None

    def build_claim(
        self,
        patient: dict,
        practitioner: dict,
        coverage: dict | None,
        insurer: dict,
        service_items: list[ServiceItem],
        supporting_info: list[dict],
        priority: str,
    ) -> dict:
        """
        Build a FHIR Claim resource with use=preauthorization.

        Args:
            patient: FHIR Patient resource dict
            practitioner: FHIR Practitioner resource dict
            coverage: FHIR Coverage resource dict, or None if missing
            insurer: FHIR Organization resource dict (the payer)
            service_items: List of ServiceItem with procedure codes and diagnosis links
            supporting_info: List of FHIR resources (Condition, MedicationRequest, Observation)
            priority: One of "normal", "urgent", "emergency"

        Returns:
            FHIR Claim resource dict

        Raises:
            ValueError: If priority is not in {normal, urgent, emergency}
        """
        if priority not in VALID_PRIORITIES:
            raise ValueError(
                f"Invalid priority '{priority}'. Must be one of: {', '.join(sorted(VALID_PRIORITIES))}"
            )

        if coverage is None:
            return {
                "error_type": "missing_coverage",
                "message": "No active Coverage resource found for the patient. "
                "Cannot generate a prior authorization Claim without insurance coverage data.",
            }

        claim_id = str(uuid.uuid4())

        # Build references using resource id or generate UUID-based URN
        patient_ref = self._make_reference(patient)
        practitioner_ref = self._make_reference(practitioner)
        insurer_ref = self._make_reference(insurer)
        coverage_ref = self._make_reference(coverage)

        # Collect unique diagnoses from service items
        all_diagnosis_ids: set[int] = set()
        for item in service_items:
            all_diagnosis_ids.update(item.diagnosis_link_ids)

        diagnosis_entries = []
        for seq, diag_id in enumerate(sorted(all_diagnosis_ids), start=1):
            # Find the corresponding supporting info resource for this diagnosis
            diag_resource = self._find_diagnosis_resource(supporting_info, diag_id)
            if diag_resource:
                coding = self._extract_diagnosis_coding(diag_resource)
            else:
                coding = {
                    "system": ICD10CM_SYSTEM,
                    "code": f"unknown-{diag_id}",
                    "display": f"Unknown diagnosis (link ID {diag_id})",
                }
            diagnosis_entries.append({
                "sequence": seq,
                "diagnosisCodeableConcept": {"coding": [coding]},
            })

        # Build item entries
        items = []
        for seq, si in enumerate(service_items, start=1):
            item_entry: dict = {
                "sequence": seq,
                "productOrService": {
                    "coding": [{
                        "system": si.product_or_service.system,
                        "code": si.product_or_service.code,
                    }]
                },
                "diagnosisSequence": list(si.diagnosis_link_ids),
            }
            if si.product_or_service.display:
                item_entry["productOrService"]["coding"][0]["display"] = si.product_or_service.display
            if si.quantity is not None:
                item_entry["quantity"] = {"value": si.quantity}
            if si.unit_price is not None:
                item_entry["unitPrice"] = {"value": si.unit_price, "currency": "USD"}
            items.append(item_entry)

        # Build supportingInfo entries
        supporting_info_entries = []
        for seq, resource in enumerate(supporting_info, start=1):
            resource_type = resource.get("resourceType", "Unknown")
            category_code = _RESOURCE_TYPE_TO_CATEGORY.get(resource_type, "patientEvent")
            ref = self._make_reference(resource)
            supporting_info_entries.append({
                "sequence": seq,
                "category": {
                    "coding": [{
                        "system": PAS_SUPPORTING_INFO_SYSTEM,
                        "code": category_code,
                    }]
                },
                "valueReference": {"reference": ref},
            })

        claim = {
            "resourceType": "Claim",
            "id": claim_id,
            "status": "active",
            "type": {
                "coding": [{
                    "system": CLAIM_TYPE_SYSTEM,
                    "code": "professional",
                }]
            },
            "use": "preauthorization",
            "patient": {"reference": patient_ref},
            "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "insurer": {"reference": insurer_ref},
            "provider": {"reference": practitioner_ref},
            "priority": {
                "coding": [{
                    "system": PROCESS_PRIORITY_SYSTEM,
                    "code": priority,
                }]
            },
            "insurance": [{
                "sequence": 1,
                "focal": True,
                "coverage": {"reference": coverage_ref},
            }],
        }

        if diagnosis_entries:
            claim["diagnosis"] = diagnosis_entries
        if items:
            claim["item"] = items
        if supporting_info_entries:
            claim["supportingInfo"] = supporting_info_entries

        return claim

    def build_pas_bundle(
        self,
        claim: dict,
        referenced_resources: list[dict],
        questionnaire_response: dict | None = None,
    ) -> dict:
        """
        Assemble a PAS Bundle of type 'collection' with UUID-based fullUrl entries.

        All resources are tagged with their Da Vinci PAS profile meta for
        HealthLake native $submit validation.

        Args:
            claim: FHIR Claim resource dict (from build_claim)
            referenced_resources: List of FHIR resources referenced by the Claim
                (Patient, Practitioner, Coverage, Organization, Condition, etc.)
            questionnaire_response: Optional FHIR QuestionnaireResponse to include

        Returns:
            FHIR Bundle resource dict of type 'collection'
        """
        # PAS profile mapping by resourceType
        PAS_PROFILES = {
            "Claim": "http://hl7.org/fhir/us/davinci-pas/StructureDefinition/profile-claim",
            "Patient": "http://hl7.org/fhir/us/davinci-pas/StructureDefinition/profile-subscriber",
            "Coverage": "http://hl7.org/fhir/us/davinci-pas/StructureDefinition/profile-coverage",
            "ServiceRequest": "http://hl7.org/fhir/us/davinci-pas/StructureDefinition/profile-servicerequest",
            "MedicationRequest": "http://hl7.org/fhir/us/davinci-pas/StructureDefinition/profile-medicationrequest",
            "DeviceRequest": "http://hl7.org/fhir/us/davinci-pas/StructureDefinition/profile-devicerequest",
            "Practitioner": "http://hl7.org/fhir/us/davinci-pas/StructureDefinition/profile-practitioner",
            "PractitionerRole": "http://hl7.org/fhir/us/davinci-pas/StructureDefinition/profile-practitionerrole",
            "DocumentReference": "http://hl7.org/fhir/us/davinci-pas/StructureDefinition/profile-documentreference",
        }

        def _tag_profile(resource: dict) -> dict:
            """Add PAS profile meta tag to a resource if applicable."""
            rt = resource.get("resourceType", "")
            profile = PAS_PROFILES.get(rt)
            if not profile:
                # Organization: determine insurer vs requestor by type coding
                if rt == "Organization":
                    type_codes = [
                        c.get("code", "")
                        for t in resource.get("type", [])
                        for c in t.get("coding", [])
                    ]
                    if "PR" in type_codes:
                        profile = "http://hl7.org/fhir/us/davinci-pas/StructureDefinition/profile-insurer"
                    else:
                        profile = "http://hl7.org/fhir/us/davinci-pas/StructureDefinition/profile-requestor"
            if profile:
                resource.setdefault("meta", {})
                resource["meta"]["profile"] = [profile]
            return resource

        entries = []
        ref_map: dict[str, str] = {}

        # Add referenced resources first so we can build the ref map
        for resource in referenced_resources:
            resource = _tag_profile(resource)
            entry_uuid = str(uuid.uuid4())
            full_url = f"urn:uuid:{entry_uuid}"
            original_ref = self._make_reference(resource)
            ref_map[original_ref] = full_url
            entries.append({
                "fullUrl": full_url,
                "resource": resource,
            })

        # Add QuestionnaireResponse if provided
        if questionnaire_response is not None:
            qr_uuid = str(uuid.uuid4())
            qr_full_url = f"urn:uuid:{qr_uuid}"
            original_ref = self._make_reference(questionnaire_response)
            ref_map[original_ref] = qr_full_url
            entries.append({
                "fullUrl": qr_full_url,
                "resource": questionnaire_response,
            })

            # Add supportingInfo entry to the claim for the QuestionnaireResponse
            existing_si = claim.get("supportingInfo", [])
            next_seq = max((si.get("sequence", 0) for si in existing_si), default=0) + 1
            existing_si.append({
                "sequence": next_seq,
                "category": {
                    "coding": [{
                        "system": PAS_SUPPORTING_INFO_SYSTEM,
                        "code": "patientEvent",
                    }]
                },
                "valueReference": {"reference": qr_full_url},
            })
            claim["supportingInfo"] = existing_si

        # Rewrite references in the claim to use urn:uuid
        rewritten_claim = self._rewrite_references(claim, ref_map)
        rewritten_claim = _tag_profile(rewritten_claim)

        # Add the claim entry (must be first per HealthLake validation)
        claim_uuid = str(uuid.uuid4())
        claim_full_url = f"urn:uuid:{claim_uuid}"
        entries.insert(0, {
            "fullUrl": claim_full_url,
            "resource": rewritten_claim,
        })

        bundle = {
            "resourceType": "Bundle",
            "meta": {
                "profile": ["http://hl7.org/fhir/us/davinci-pas/StructureDefinition/profile-pas-request-bundle"]
            },
            "identifier": {
                "system": "http://example.org/SUBMITTER_TRANSACTION_IDENTIFIER",
                "value": str(uuid.uuid4()),
            },
            "type": "collection",
            "timestamp": datetime.now(timezone.utc).isoformat() if hasattr(datetime, 'now') else "",
            "entry": entries,
        }

        return bundle

    def validate_bundle(self, bundle: dict) -> list[OperationOutcomeIssue]:
        """
        Validate that all references within the Bundle resolve to entries.

        Args:
            bundle: FHIR Bundle resource dict

        Returns:
            List of OperationOutcomeIssue for any unresolved references.
        """
        issues: list[OperationOutcomeIssue] = []

        entries = bundle.get("entry", [])
        # Collect all fullUrls in the bundle
        full_urls: set[str] = set()
        for entry in entries:
            full_url = entry.get("fullUrl")
            if full_url:
                full_urls.add(full_url)

        # Check all references in each resource
        for entry in entries:
            resource = entry.get("resource", {})
            refs = self._collect_references(resource)
            for ref_value in refs:
                if ref_value.startswith("urn:uuid:") and ref_value not in full_urls:
                    resource_type = resource.get("resourceType", "Unknown")
                    issues.append(OperationOutcomeIssue(
                        severity="warning",
                        code="not-found",
                        diagnostics=(
                            f"Reference '{ref_value}' in {resource_type} "
                            f"does not resolve to any entry in the Bundle."
                        ),
                    ))

        return issues

    # ---- Private helpers ----

    @staticmethod
    def _make_reference(resource: dict) -> str:
        """Build a FHIR reference string from a resource dict."""
        resource_type = resource.get("resourceType", "Resource")
        resource_id = resource.get("id", str(uuid.uuid4()))
        return f"{resource_type}/{resource_id}"

    @staticmethod
    def _find_diagnosis_resource(supporting_info: list[dict], diag_id: int) -> dict | None:
        """Find a Condition resource matching a diagnosis link ID (1-based index)."""
        conditions = [r for r in supporting_info if r.get("resourceType") == "Condition"]
        idx = diag_id - 1  # Convert 1-based to 0-based
        if 0 <= idx < len(conditions):
            return conditions[idx]
        return None

    @staticmethod
    def _extract_diagnosis_coding(condition: dict) -> dict:
        """Extract the primary coding from a Condition resource."""
        code_obj = condition.get("code", {})
        codings = code_obj.get("coding", [])
        if codings:
            c = codings[0]
            return {
                "system": c.get("system", ICD10CM_SYSTEM),
                "code": c.get("code", "unknown"),
                "display": c.get("display", ""),
            }
        # Fallback: use code.text if available
        text = code_obj.get("text", "Unknown condition")
        return {
            "system": ICD10CM_SYSTEM,
            "code": "unknown",
            "display": text,
        }

    def _rewrite_references(self, obj: dict | list | str, ref_map: dict[str, str]):
        """Recursively rewrite reference values using the ref_map."""
        if isinstance(obj, dict):
            result = {}
            for key, value in obj.items():
                if key == "reference" and isinstance(value, str) and value in ref_map:
                    result[key] = ref_map[value]
                else:
                    result[key] = self._rewrite_references(value, ref_map)
            return result
        elif isinstance(obj, list):
            return [self._rewrite_references(item, ref_map) for item in obj]
        return obj

    def _collect_references(self, obj, refs: list[str] | None = None) -> list[str]:
        """Recursively collect all 'reference' field values from a resource."""
        if refs is None:
            refs = []
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key == "reference" and isinstance(value, str):
                    refs.append(value)
                else:
                    self._collect_references(value, refs)
        elif isinstance(obj, list):
            for item in obj:
                self._collect_references(item, refs)
        return refs
