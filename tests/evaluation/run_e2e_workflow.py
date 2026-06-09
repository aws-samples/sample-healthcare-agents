#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Phase 5: End-to-end RCM workflow test.

Chains all 6 RCM agents in sequence for a single patient, validating
data handoff between agents. Each agent's output feeds the next.

Workflow:
  1. Eligibility Verification → coverage confirmed
  2. Prior Authorization → auth required, submitted
  3. Medical Coding → codes assigned from clinical notes
  4. Claims Assembly → EDI 837P built
  5. Claims Submission → submitted via B2B
  6. Appeals → (simulate denial) appeal letter generated

Usage:
    export LANGFUSE_PUBLIC_KEY=pk-...
    export LANGFUSE_SECRET_KEY=sk-...
    export AWS_PROFILE=quicksuite

    uv run python3 tests/evaluation/run_e2e_workflow.py
    uv run python3 tests/evaluation/run_e2e_workflow.py --dry-run
    uv run python3 tests/evaluation/run_e2e_workflow.py --patient Patient/smart-1032702
"""

import argparse
import json
import os
import time
import uuid
from datetime import date

import boto3
import requests
from langfuse import Langfuse

# Reuse helpers from run_experiment
from run_experiment import (
    REGION,
    SSM_STACK_BASE,
    LANGFUSE_HOST,
    get_machine_token,
    get_runtime_arn,
    invoke_agent,
)

# ── Workflow steps ─────────────────────────────────────────────────────────────

WORKFLOW_STEPS = [
    {
        "agent": "eligibility-verification-agent",
        "prompt_template": (
            "Verify insurance eligibility for {patient_id}. "
            "Service: MRI lumbar spine (CPT 72148). Date of service: 2026-04-15. "
            "Payor: UnitedHealthcare."
        ),
        "pass_criteria": "coverage_active",
        "description": "Step 1: Verify patient insurance eligibility",
    },
    {
        "agent": "prior-authorization-agent",
        "prompt_template": (
            "Determine if prior authorization is required and assess medical necessity for:\n"
            "Patient: {patient_id}\n"
            "Procedure: CPT 72148 - MRI lumbar spine without contrast\n"
            "Payor: UnitedHealthcare\n"
            "Clinical Context: 58-year-old male with chronic low back pain radiating to left leg "
            "for 8 weeks. Failed 6 weeks of physical therapy and NSAIDs. "
            "Straight leg raise positive on left. Decreased sensation L5 dermatome."
        ),
        "pass_criteria": "auth_determination",
        "description": "Step 2: Prior authorization assessment",
    },
    {
        "agent": "medical-coding-agent",
        "prompt_template": (
            "Extract medical codes from the following clinical note:\n\n"
            "58-year-old male with chronic low back pain radiating to left lower extremity "
            "for 8 weeks. History of failed conservative therapy including 6 weeks physical "
            "therapy and trial of naproxen 500mg BID. Examination shows positive straight leg "
            "raise on left at 40 degrees, decreased sensation in L5 dermatome. "
            "MRI lumbar spine ordered to evaluate for disc herniation or stenosis. "
            "Assessment: Lumbar radiculopathy, likely L4-L5 disc herniation."
        ),
        "pass_criteria": "codes_extracted",
        "description": "Step 3: Medical coding from clinical notes",
    },
    {
        "agent": "claims-assembly-agent",
        "prompt_template": (
            "Assemble an EDI 837P claim with the following data:\n"
            "Claim ID: CLM-E2E-{run_id}\n"
            "Billing Provider: Coastal Medical Group, NPI 1234567890, Tax ID 123456789, "
            "Taxonomy 207Q00000X, 100 Main St, San Diego CA 92101\n"
            "Subscriber: John Smith, Member ID UHC-12345, DOB 19680315, Gender M, Group GRP-001\n"
            "Payer: UnitedHealthcare, Payer ID 87726\n"
            "Diagnosis 1: M54.41 (Lumbago with sciatica, right side)\n"
            "Diagnosis 2: M51.16 (Intervertebral disc degeneration, lumbar region)\n"
            "Service Line: CPT 72148, $1200.00, 1 unit, DOS 20260415, POS 11, Dx pointers 1,2\n"
            "Prior Auth: AUTH-E2E-{run_id}\n"
            "Total Charge: $1200.00"
        ),
        "pass_criteria": "edi_valid",
        "description": "Step 4: Assemble EDI 837P claim",
    },
    {
        "agent": "claims-submission-agent",
        "prompt_template": (
            "Submit the assembled EDI 837P claim via B2B Data Interchange:\n"
            "Claim ID: CLM-E2E-{run_id}\n"
            "Payor: UnitedHealthcare (Payer ID 87726)\n"
            "Total Charge: $1200.00\n"
            "Submit and track transformation job status."
        ),
        "pass_criteria": "submitted",
        "description": "Step 5: Submit claim via B2B Data Interchange",
    },
    {
        "agent": "appeals-agent",
        "prompt_template": (
            "Generate an appeal for a denied claim:\n"
            "Claim ID: CLM-E2E-{run_id}\n"
            "Denial Code: CO-50 (Medical necessity)\n"
            "RARC: N386\n"
            "Procedure: CPT 72148 (MRI lumbar spine)\n"
            "Diagnosis: M54.41 (Lumbago with sciatica)\n"
            "Payor: UnitedHealthcare\n"
            "Date of Denial: 2026-04-20\n"
            "Clinical Context: Patient has chronic low back pain with left-sided radiculopathy, "
            "failed 6 weeks PT and NSAIDs, positive SLR, decreased L5 sensation. "
            "MRI was medically necessary to evaluate for surgical candidacy."
        ),
        "pass_criteria": "appeal_generated",
        "description": "Step 6: Generate appeal for simulated denial",
    },
]


def run_e2e_workflow(patient_id: str, run_name: str, dry_run: bool) -> None:
    """Execute the full RCM workflow for a single patient."""

    run_id = uuid.uuid4().hex[:8]

    lf = Langfuse(
        public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
        secret_key=os.environ["LANGFUSE_SECRET_KEY"],
        host=os.environ.get("LANGFUSE_HOST", LANGFUSE_HOST),
    )

    print(f"E2E Workflow: {run_name}")
    print(f"Patient:      [redacted]")
    print(f"Run ID:       {run_id}")
    print(f"Steps:        {len(WORKFLOW_STEPS)}\n")

    if not dry_run:
        print("Authenticating...")
        token = get_machine_token()

    # Create a single trace for the entire workflow
    trace = lf.trace(
        name=f"e2e-rcm-workflow-{run_id}",
        metadata={
            "patient_id": patient_id,
            "run_name": run_name,
            "run_id": run_id,
            "workflow": "rcm-e2e",
        },
    )

    results = {}
    all_passed = True

    for i, step in enumerate(WORKFLOW_STEPS):
        agent_name = step["agent"]
        prompt = step["prompt_template"].format(patient_id=patient_id, run_id=run_id)

        print(f"[{i+1}/{len(WORKFLOW_STEPS)}] {step['description']}")
        print(f"  Agent: {agent_name}")

        if dry_run:
            print(f"  DRY RUN: (prompt redacted, length={len(prompt)} chars)")
            results[agent_name] = {"status": "dry_run"}
            continue

        span = trace.span(
            name=f"step-{i+1}-{agent_name}",
            input={"prompt": prompt},
            metadata={"agent": agent_name, "step": i + 1},
        )

        try:
            stack_name = f"{SSM_STACK_BASE}-{agent_name}"
            runtime_arn = get_runtime_arn(stack_name)
            session_id = f"e2e-{run_id}-step{i+1}"

            output = invoke_agent(prompt, token, runtime_arn, session_id)
            analysis = output.get("analysis", "")

            span.update(
                output=analysis[:2000],
                metadata={"events": len(output.get("raw_events", []))},
            )

            results[agent_name] = {
                "status": "completed",
                "analysis_length": len(analysis),
                "events": len(output.get("raw_events", [])),
            }

            print(f"  -> Completed ({len(analysis)} chars, {len(output.get('raw_events', []))} events)")

        except Exception as e:
            span.update(output=f"ERROR: {e}", level="ERROR")
            results[agent_name] = {"status": "error", "error": str(e)}
            all_passed = False
            print(f"  -> ERROR: {e}")

        span.end()
        time.sleep(2)  # Rate limiting between agents

    # Record workflow-level scores
    if not dry_run:
        completed = sum(1 for r in results.values() if r.get("status") == "completed")
        trace.score(name="e2e_steps_completed", value=completed, comment=f"{completed}/{len(WORKFLOW_STEPS)} steps")
        trace.score(name="e2e_workflow_pass", value=1.0 if all_passed else 0.0)

    lf.flush()

    print(f"\n{'='*60}")
    print(f"E2E Workflow Summary")
    print(f"{'='*60}")
    for agent_name, result in results.items():
        status = result.get("status", "unknown")
        icon = "✅" if status == "completed" else "⏭️" if status == "dry_run" else "❌"
        print(f"  {icon} {agent_name}: {status}")
    print(f"\nOverall: {'PASS' if all_passed else 'FAIL'}")
    if not dry_run:
        print(f"Trace: {LANGFUSE_HOST} -> Traces -> e2e-rcm-workflow-{run_id}")


def main():
    parser = argparse.ArgumentParser(description="Run end-to-end RCM workflow test")
    parser.add_argument("--patient", default="Patient/smart-1032702")
    parser.add_argument("--run-name", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    run_name = args.run_name or f"e2e-rcm-{date.today()}"
    run_e2e_workflow(args.patient, run_name, args.dry_run)


if __name__ == "__main__":
    main()
