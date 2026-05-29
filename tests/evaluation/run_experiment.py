#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Step 4: Run evaluation experiment against a healthcare agent golden set.

Uses Langfuse Python SDK v3 with dataset item.run() for automatic trace
creation and dataset linking, plus inline LLM-as-judge scoring via Bedrock.

Usage:
    export LANGFUSE_PUBLIC_KEY=pk-...
    export LANGFUSE_SECRET_KEY=sk-...
    export AWS_PROFILE=quicksuite

    uv run python3 tests/evaluation/run_experiment.py
    uv run python3 tests/evaluation/run_experiment.py --run-name claude-sonnet-4-6-2026-04-02
    uv run python3 tests/evaluation/run_experiment.py --dry-run
"""

import argparse
import json
import os
import time
import urllib.parse
import uuid
from datetime import date

import boto3
import requests
from langfuse import Langfuse

REGION = "us-east-1"
SSM_STACK_BASE = "healthcare-agents-stack"
LANGFUSE_HOST = "https://d25s1shy5vv04l.cloudfront.net"
SEVERITY_ORDER = ["low", "medium", "high", "critical"]
JUDGE_MODEL_ID = "us.anthropic.claude-sonnet-4-6-v1"

AGENT_DATASET_MAP = {
    "hospital-safety-agent": "hospital-safety-golden-v1",
    "prior-authorization-agent": "prior-auth-golden-v1",
    "eligibility-verification-agent": "eligibility-golden-v1",
    "medical-coding-agent": "medical-coding-golden-v1",
    "claims-assembly-agent": "claims-assembly-golden-v1",
    "claims-submission-agent": "claims-submission-golden-v1",
    "appeals-agent": "appeals-golden-v1",
}


# ── AWS helpers ────────────────────────────────────────────────────────────────

def get_machine_token() -> str:
    ssm = boto3.client("ssm", region_name=REGION)
    secrets = boto3.client("secretsmanager", region_name=REGION)
    client_id = ssm.get_parameter(Name=f"/{SSM_STACK_BASE}/machine_client_id")["Parameter"]["Value"]
    domain = ssm.get_parameter(Name=f"/{SSM_STACK_BASE}/cognito_provider")["Parameter"]["Value"]
    client_secret = secrets.get_secret_value(
        SecretId=f"/{SSM_STACK_BASE}/machine_client_secret"
    )["SecretString"]
    resp = requests.post(
        f"https://{domain}/oauth2/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": f"{SSM_STACK_BASE}-api/invoke",
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def get_runtime_arn(stack_name: str) -> str:
    cfn = boto3.client("cloudformation", region_name=REGION)
    outputs = cfn.describe_stacks(StackName=stack_name)["Stacks"][0]["Outputs"]
    for o in outputs:
        if o["OutputKey"] == "AgentRuntimeArn":
            return o["OutputValue"]
    raise ValueError(f"AgentRuntimeArn not found in {stack_name}")


def invoke_agent(prompt: str, token: str, runtime_arn: str, session_id: str) -> dict:
    escaped_arn = urllib.parse.quote(runtime_arn, safe="")
    url = f"https://bedrock-agentcore.{REGION}.amazonaws.com/runtimes/{escaped_arn}/invocations?qualifier=DEFAULT"
    resp = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": session_id,
        },
        json={"prompt": prompt, "userId": session_id, "runtimeSessionId": session_id},
        timeout=300,
        stream=True,
    )
    resp.raise_for_status()
    result = {"raw_events": [], "analysis": "", "classification": {}}
    for line in resp.iter_lines():
        if not line:
            continue
        text = line.decode("utf-8")
        if not text.startswith("data: "):
            continue
        try:
            event = json.loads(text[6:])
            result["raw_events"].append(event)
            if event.get("status") == "COMPLETED":
                result["analysis"] = event.get("analysis", "")
                result["classification"] = event.get("classification", {})
        except (json.JSONDecodeError, ValueError):
            pass
    return result


# ── LLM judge ─────────────────────────────────────────────────────────────────

def get_judge_prompts(agent_name: str) -> tuple[str, str]:
    """Get agent-specific judge system and user prompts."""
    from judge_prompt import AGENT_PROMPTS
    config = AGENT_PROMPTS.get(agent_name)
    if not config:
        raise ValueError(f"No judge prompt for agent '{agent_name}'")
    return config["system"], config["user"]


def run_judge(prompt: str, ai_output: str, expected: dict, agent_name: str = "hospital-safety-agent") -> dict:
    """Call Bedrock with the agent-specific judge rubric. Returns parsed scores dict."""
    system_prompt, user_template = get_judge_prompts(agent_name)

    user_msg = (
        user_template
        .replace("{{input}}", prompt)
        .replace("{{ai_output}}", ai_output)
        .replace("{{expected_output}}", json.dumps(expected, indent=2))
    )
    bedrock = boto3.client("bedrock-runtime", region_name=REGION)
    resp = bedrock.invoke_model(
        modelId=JUDGE_MODEL_ID,
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1024,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_msg}],
        }),
    )
    text = json.loads(resp["body"].read())["content"][0]["text"].strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


# ── Score recording ────────────────────────────────────────────────────────────

# ── Agent-specific score field mappings ─────────────────────────────────────────

AGENT_NUMERIC_SCORES = {
    "hospital-safety-agent": ["clinical_accuracy", "safety", "completeness", "hallucination",
                              "harm_severity", "hs__severity_calibration"],
    "prior-authorization-agent": ["clinical_accuracy", "safety", "completeness", "hallucination",
                                  "harm_severity", "pa__clinical_data_completeness"],
    "medical-coding-agent": ["clinical_accuracy", "safety", "completeness", "hallucination",
                             "harm_severity", "mc__icd10_accuracy", "mc__cpt_accuracy",
                             "mc__entity_extraction_recall"],
    "claims-assembly-agent": ["clinical_accuracy", "safety", "completeness", "hallucination",
                              "harm_severity", "ca__field_completeness"],
    "eligibility-verification-agent": ["clinical_accuracy", "safety", "completeness", "hallucination",
                                       "harm_severity", "ev__benefit_detail_accuracy"],
    "claims-submission-agent": ["clinical_accuracy", "safety", "completeness", "hallucination",
                                "harm_severity"],
    "appeals-agent": ["clinical_accuracy", "safety", "completeness", "hallucination",
                      "harm_severity", "ap__letter_completeness"],
}

AGENT_BOOLEAN_SCORES = {
    "hospital-safety-agent": ["hs__event_classification_accuracy", "hs__alert_routing_correctness",
                              "hs__preventability_accuracy", "hs__mandatory_reporting_accuracy",
                              "overall_pass"],
    "prior-authorization-agent": ["pa__auth_determination_accuracy", "pa__medical_necessity_accuracy",
                                  "pa__fhir_bundle_validity", "pa__payor_policy_citation",
                                  "overall_pass"],
    "medical-coding-agent": ["mc__code_specificity", "overall_pass"],
    "claims-assembly-agent": ["ca__edi_structural_validity", "ca__hipaa_compliance",
                              "ca__payer_rule_adherence", "overall_pass"],
    "eligibility-verification-agent": ["ev__coverage_status_accuracy", "ev__auth_flag_accuracy",
                                       "overall_pass"],
    "claims-submission-agent": ["cs__submission_accuracy", "cs__acknowledgment_parsing",
                                "cs__status_tracking", "overall_pass"],
    "appeals-agent": ["ap__denial_code_accuracy", "ap__deadline_accuracy",
                      "ap__clinical_evidence_citation", "overall_pass"],
}


def record_scores(span, output: dict, expected: dict, prompt: str, agent_name: str = "hospital-safety-agent") -> None:
    classification = (output or {}).get("classification", {})

    # Agent-specific hard gate scores
    if agent_name == "hospital-safety-agent":
        actual = classification.get("severity", "").lower()
        exp_sev = expected.get("severity", "").lower()
        missed = exp_sev == "critical" and actual != "critical"
        span.score_trace(name="sentinel_event_missed", value=1 if missed else 0,
                         comment=f"expected={exp_sev},actual={actual}")
        try:
            gap = abs(SEVERITY_ORDER.index(exp_sev) - SEVERITY_ORDER.index(actual))
        except ValueError:
            gap = 0
        span.score_trace(name="severity_gap", value=gap,
                         comment=f"expected={exp_sev},actual={actual}")

    # LLM judge scores (agent-aware)
    try:
        scores = run_judge(prompt, (output or {}).get("analysis", ""), expected, agent_name)
        reasoning = scores.get("reasoning", "")

        numeric_fields = AGENT_NUMERIC_SCORES.get(agent_name, ["clinical_accuracy", "safety", "completeness", "hallucination", "harm_severity"])
        for name in numeric_fields:
            if name in scores:
                span.score_trace(name=name, value=float(scores[name]), comment=reasoning)

        boolean_fields = AGENT_BOOLEAN_SCORES.get(agent_name, ["overall_pass"])
        for name in boolean_fields:
            if name in scores:
                span.score_trace(name=name, value=1.0 if scores[name] else 0.0, comment=reasoning)

        print(f"  judge: overall_pass={scores.get('overall_pass')}")
    except Exception as e:
        print(f"  WARN judge: {e}")


# ── Main experiment loop ───────────────────────────────────────────────────────

def run_experiment(agent_name: str, dataset_name: str, run_name: str, dry_run: bool) -> None:
    stack_name = f"{SSM_STACK_BASE}-{agent_name}"

    lf = Langfuse(
        public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
        secret_key=os.environ["LANGFUSE_SECRET_KEY"],
        host=os.environ.get("LANGFUSE_HOST", LANGFUSE_HOST),
    )

    dataset = lf.get_dataset(dataset_name)
    items = dataset.items
    print(f"Agent:    {agent_name}")
    print(f"Stack:    {stack_name}")
    print(f"Dataset:  {dataset_name} ({len(items)} items)")
    print(f"Run name: {run_name}\n")

    if dry_run:
        for i, item in enumerate(items):
            meta = item.metadata or {}
            exp = item.expected_output or {}
            prompt = (item.input or {}).get("prompt", "")
            print(f"[{i+1}/{len(items)}] {meta.get('id', '?')} — "
                  f"{exp.get('event_type', '?')} / {exp.get('severity', '?')}")
            print(f"  DRY RUN: {prompt[:80]}...")
        return

    print("Authenticating...")
    token = get_machine_token()
    runtime_arn = get_runtime_arn(stack_name)
    print(f"Runtime:  {runtime_arn}\n")

    for i, item in enumerate(items):
        meta = item.metadata or {}
        exp = item.expected_output or {}
        prompt = (item.input or {}).get("prompt", "")
        item_id = (meta or {}).get("id", f"item_{i}")

        print(f"[{i+1}/{len(items)}] {item_id} — "
              f"{exp.get('event_type', '?')} / {exp.get('severity', '?')}")

        session_id = f"eval-{uuid.uuid4()}"

        try:
            with item.run(run_name=run_name, run_metadata={"agent": agent_name}) as root_span:
                output = invoke_agent(prompt, token, runtime_arn, session_id)
                actual_severity = output["classification"].get("severity", "unknown")
                print(f"  -> severity={actual_severity} (expected {exp.get('severity', '?')}), "
                      f"events={len(output['raw_events'])}")

                root_span.update(
                    input={"prompt": prompt},
                    output=output.get("analysis", ""),
                    metadata={"classification": output.get("classification", {}),
                              "expected": exp},
                )

                record_scores(root_span, output, exp, prompt, agent_name)

        except Exception as e:
            print(f"  ERROR: {e}")

        time.sleep(1)

    lf.flush()
    print(f"\nExperiment '{run_name}' complete.")
    print(f"View: {LANGFUSE_HOST} -> Datasets -> {dataset_name}")


def main():
    parser = argparse.ArgumentParser(description="Run evaluation experiment for a healthcare agent")
    parser.add_argument("--agent", default="hospital-safety-agent")
    parser.add_argument("--dataset", default=None)
    parser.add_argument("--run-name", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    dataset = args.dataset or AGENT_DATASET_MAP.get(args.agent, f"{args.agent}-golden-v1")
    run_name = args.run_name or f"{args.agent}-{date.today()}"

    run_experiment(args.agent, dataset, run_name, args.dry_run)


if __name__ == "__main__":
    main()
