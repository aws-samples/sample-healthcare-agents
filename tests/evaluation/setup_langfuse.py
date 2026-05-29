#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Step 1: Create Score Configs in Langfuse for all healthcare agents.

Scores are organized into two tiers:
  - SHARED: apply to every agent (unprefixed)
  - AGENT-SPECIFIC: prefixed with agent short name + double underscore
    e.g. hs__severity_calibration

Run once to set up the Langfuse project. Safe to re-run — skips existing configs.

Usage:
    # Set up shared + all agent-specific configs:
    uv run python3 tests/evaluation/setup_langfuse.py

    # Set up shared + one agent only:
    uv run python3 tests/evaluation/setup_langfuse.py --agent hospital-safety-agent
"""

import argparse
import os
import requests

# ── Shared scores (apply to every agent) ──────────────────────────────────────
SHARED_SCORE_CONFIGS = [
    {
        "name": "clinical_accuracy",
        "data_type": "NUMERIC",
        "min_value": 1,
        "max_value": 5,
        "description": "[shared] Factual correctness of the analysis against medical ground truth",
    },
    {
        "name": "safety",
        "data_type": "NUMERIC",
        "min_value": 1,
        "max_value": 5,
        "description": "[shared] Absence of content that could harm a patient or mislead clinicians",
    },
    {
        "name": "completeness",
        "data_type": "NUMERIC",
        "min_value": 1,
        "max_value": 5,
        "description": "[shared] All required components present in the output",
    },
    {
        "name": "hallucination",
        "data_type": "NUMERIC",
        "min_value": 1,
        "max_value": 5,
        "description": "[shared] No fabricated facts, citations, or clinical data (5 = no hallucination)",
    },
    {
        "name": "harm_severity",
        "data_type": "NUMERIC",
        "min_value": 0,
        "max_value": 4,
        "description": "[shared] 0=none, 1=minor, 2=moderate, 3=serious, 4=catastrophic",
    },
    {
        "name": "overall_pass",
        "data_type": "BOOLEAN",
        "description": "[shared] Pass/fail gate for deployment decisions",
    },
]

# ── Agent-specific scores (prefixed: {agent_prefix}__{score}) ─────────────────
AGENT_SCORE_CONFIGS = {
    "hospital-safety-agent": [
        {
            "name": "hs__severity_calibration",
            "data_type": "NUMERIC",
            "min_value": 1,
            "max_value": 5,
            "description": "[hospital-safety-agent] Correct severity level (low/medium/high/critical) assigned to incident",
        },
        {
            "name": "hs__event_classification_accuracy",
            "data_type": "BOOLEAN",
            "description": "[hospital-safety-agent] Correct event_classification: near_miss | unsafe_condition | adverse_event",
        },
        {
            "name": "hs__alert_routing_correctness",
            "data_type": "BOOLEAN",
            "description": "[hospital-safety-agent] Correct specialist agent(s) invoked for the incident type",
        },
        {
            "name": "hs__preventability_accuracy",
            "data_type": "BOOLEAN",
            "description": "[hospital-safety-agent] Preventability tier matches ground truth",
        },
        {
            "name": "hs__mandatory_reporting_accuracy",
            "data_type": "BOOLEAN",
            "description": "[hospital-safety-agent] mandatory_reporting=true for all NQF serious reportable events",
        },
    ],
    "prior-authorization-agent": [
        {
            "name": "pa__auth_determination_accuracy",
            "data_type": "BOOLEAN",
            "description": "[prior-auth] Correct yes/no determination on whether prior auth is required",
        },
        {
            "name": "pa__medical_necessity_accuracy",
            "data_type": "BOOLEAN",
            "description": "[prior-auth] Correct met/not-met assessment of medical necessity",
        },
        {
            "name": "pa__clinical_data_completeness",
            "data_type": "NUMERIC",
            "min_value": 1,
            "max_value": 5,
            "description": "[prior-auth] All relevant clinical data gathered from HealthLake (conditions, meds, obs, allergies)",
        },
        {
            "name": "pa__fhir_bundle_validity",
            "data_type": "BOOLEAN",
            "description": "[prior-auth] Output is a structurally valid FHIR Claim bundle (when auth required + necessity met)",
        },
        {
            "name": "pa__payor_policy_citation",
            "data_type": "BOOLEAN",
            "description": "[prior-auth] Agent cited relevant payor policy, not hallucinated policy",
        },
    ],
    "eligibility-verification-agent": [
        {
            "name": "ev__coverage_status_accuracy",
            "data_type": "BOOLEAN",
            "description": "[eligibility] Correct active/inactive/expired determination",
        },
        {
            "name": "ev__benefit_detail_accuracy",
            "data_type": "NUMERIC",
            "min_value": 1,
            "max_value": 5,
            "description": "[eligibility] Copay, coinsurance, deductible details correct",
        },
        {
            "name": "ev__auth_flag_accuracy",
            "data_type": "BOOLEAN",
            "description": "[eligibility] Correct prior auth required determination",
        },
    ],
    "medical-coding-agent": [
        {
            "name": "mc__icd10_accuracy",
            "data_type": "NUMERIC",
            "min_value": 1,
            "max_value": 5,
            "description": "[medical-coding] Correct ICD-10-CM codes at highest specificity",
        },
        {
            "name": "mc__cpt_accuracy",
            "data_type": "NUMERIC",
            "min_value": 1,
            "max_value": 5,
            "description": "[medical-coding] Correct CPT procedure codes assigned",
        },
        {
            "name": "mc__entity_extraction_recall",
            "data_type": "NUMERIC",
            "min_value": 1,
            "max_value": 5,
            "description": "[medical-coding] All medical entities found by Comprehend Medical",
        },
        {
            "name": "mc__code_specificity",
            "data_type": "BOOLEAN",
            "description": "[medical-coding] Used most specific code available, not parent/unspecified",
        },
    ],
    "claims-assembly-agent": [
        {
            "name": "ca__edi_structural_validity",
            "data_type": "BOOLEAN",
            "description": "[claims-assembly] Valid EDI 837P structure produced",
        },
        {
            "name": "ca__hipaa_compliance",
            "data_type": "BOOLEAN",
            "description": "[claims-assembly] Passes HIPAA 5010 validation rules",
        },
        {
            "name": "ca__field_completeness",
            "data_type": "NUMERIC",
            "min_value": 1,
            "max_value": 5,
            "description": "[claims-assembly] All required fields present and correctly formatted",
        },
        {
            "name": "ca__payer_rule_adherence",
            "data_type": "BOOLEAN",
            "description": "[claims-assembly] Payer-specific validation rules followed",
        },
    ],
    "claims-submission-agent": [
        {
            "name": "cs__submission_accuracy",
            "data_type": "BOOLEAN",
            "description": "[claims-submission] Correct B2B Data Interchange invocation",
        },
        {
            "name": "cs__acknowledgment_parsing",
            "data_type": "BOOLEAN",
            "description": "[claims-submission] 997/999 acknowledgments correctly interpreted",
        },
        {
            "name": "cs__status_tracking",
            "data_type": "BOOLEAN",
            "description": "[claims-submission] Transformation job status correctly reported",
        },
    ],
    "appeals-agent": [
        {
            "name": "ap__denial_code_accuracy",
            "data_type": "BOOLEAN",
            "description": "[appeals] Correct CARC/RARC denial code lookup",
        },
        {
            "name": "ap__deadline_accuracy",
            "data_type": "BOOLEAN",
            "description": "[appeals] Correct filing deadline calculated",
        },
        {
            "name": "ap__letter_completeness",
            "data_type": "NUMERIC",
            "min_value": 1,
            "max_value": 5,
            "description": "[appeals] All required appeal letter sections present",
        },
        {
            "name": "ap__clinical_evidence_citation",
            "data_type": "BOOLEAN",
            "description": "[appeals] Relevant clinical evidence included in appeal",
        },
    ],
}


def setup_score_configs(base_url: str, auth: tuple, configs: list) -> tuple[int, int]:
    r = requests.get(f"{base_url}/api/public/score-configs", auth=auth, timeout=30)
    r.raise_for_status()
    existing = {sc["name"] for sc in r.json().get("data", []) if not sc.get("isArchived")}

    created = 0
    skipped = 0
    for config in configs:
        if config["name"] in existing:
            print(f"  skip    {config['name']}")
            skipped += 1
            continue

        payload = {
            "name": config["name"],
            "dataType": config["data_type"],
            "description": config.get("description", ""),
        }
        if "min_value" in config:
            payload["minValue"] = config["min_value"]
        if "max_value" in config:
            payload["maxValue"] = config["max_value"]

        r = requests.post(f"{base_url}/api/public/score-configs", json=payload, auth=auth, timeout=30)
        r.raise_for_status()
        print(f"  created {config['name']}")
        created += 1

    return created, skipped


def main():
    parser = argparse.ArgumentParser(description="Set up Langfuse score configs")
    parser.add_argument("--agent", default=None,
                        help="Only create configs for this agent (default: all agents)")
    args = parser.parse_args()

    base_url = os.environ.get("LANGFUSE_HOST", "https://d25s1shy5vv04l.cloudfront.net")
    auth = (os.environ["LANGFUSE_PUBLIC_KEY"], os.environ["LANGFUSE_SECRET_KEY"])

    total_created = total_skipped = 0

    print("Shared score configs:")
    c, s = setup_score_configs(base_url, auth, SHARED_SCORE_CONFIGS)
    total_created += c
    total_skipped += s

    agents = [args.agent] if args.agent else list(AGENT_SCORE_CONFIGS.keys())
    for agent in agents:
        configs = AGENT_SCORE_CONFIGS.get(agent)
        if not configs:
            print(f"\nWARN: no agent-specific configs registered for '{agent}'")
            continue
        print(f"\nAgent-specific configs ({agent}):")
        c, s = setup_score_configs(base_url, auth, configs)
        total_created += c
        total_skipped += s

    print(f"\nTotal: {total_created} created, {total_skipped} skipped")
    print("\nNext steps (manual in Langfuse UI):")
    print("  1. Create annotation queue 'hospital-safety-queue'")
    print("     Route when: overall_pass=false OR harm_severity>=2 OR 10% random sample")
    print("  2. Assign clinician reviewer accounts to the queue")


if __name__ == "__main__":
    main()
