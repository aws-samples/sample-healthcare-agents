#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Step 2: Upload golden sets to Langfuse as datasets.

Supports all healthcare agents. Golden sets are locked after upload —
never modify existing items. Add new test cases in a versioned dataset.

Usage:
    uv run python3 tests/evaluation/upload_golden_sets.py
    uv run python3 tests/evaluation/upload_golden_sets.py --agent prior-authorization-agent
    uv run python3 tests/evaluation/upload_golden_sets.py --agent hospital-safety-agent --dataset hospital-safety-golden-v2
"""

import argparse
import importlib
import json
import os

from langfuse import Langfuse

AGENT_GOLDEN_SETS = {
    "hospital-safety-agent": {
        "module": "golden_sets.hospital_safety",
        "dataset": "hospital-safety-golden-v1",
        "metadata_fields": lambda item: {
            "id": item["id"],
            "event_type": item["expected_output"]["event_type"],
            "severity": item["expected_output"]["severity"],
        },
        "input_fn": lambda item: {"prompt": item["input"]},
    },
    "prior-authorization-agent": {
        "module": "golden_sets.prior_authorization",
        "dataset": "prior-auth-golden-v1",
        "metadata_fields": lambda item: {
            "id": item["id"],
            "category": item["category"],
            "procedure_code": item["input"]["procedure_code"],
            "payor": item["input"]["payor"],
        },
        "input_fn": lambda item: {
            "prompt": (
                f"Patient: {item['input']['patient_id']}\n"
                f"Procedure: {item['input']['procedure_code']} - {item['input']['procedure_description']}\n"
                f"Payor: {item['input']['payor']}\n"
                f"Clinical Context: {item['input']['clinical_context']}"
            ),
        },
    },
    "medical-coding-agent": {
        "module": "golden_sets.medical_coding",
        "dataset": "medical-coding-golden-v1",
        "metadata_fields": lambda item: {
            "id": item["id"],
            "category": item["category"],
        },
        "input_fn": lambda item: {"prompt": item["input"]},
    },
    "claims-assembly-agent": {
        "module": "golden_sets.claims_assembly",
        "dataset": "claims-assembly-golden-v1",
        "metadata_fields": lambda item: {
            "id": item["id"],
            "category": item["category"],
        },
        "input_fn": lambda item: {"prompt": item["input"]},
    },
    # Add as golden sets are created:
    "eligibility-verification-agent": {
        "module": "golden_sets.eligibility_verification",
        "dataset": "eligibility-golden-v1",
        "metadata_fields": lambda item: {
            "id": item["id"],
            "category": item["category"],
        },
        "input_fn": lambda item: {"prompt": item["input"]},
    },
    "claims-submission-agent": {
        "module": "golden_sets.claims_submission",
        "dataset": "claims-submission-golden-v1",
        "metadata_fields": lambda item: {
            "id": item["id"],
            "category": item["category"],
        },
        "input_fn": lambda item: {"prompt": item["input"]},
    },
    "appeals-agent": {
        "module": "golden_sets.appeals",
        "dataset": "appeals-golden-v1",
        "metadata_fields": lambda item: {
            "id": item["id"],
            "category": item["category"],
        },
        "input_fn": lambda item: {"prompt": item["input"]},
    },
    # "eligibility-verification-agent": { ... },
    # "medical-coding-agent": { ... },
    # "claims-assembly-agent": { ... },
    # "claims-submission-agent": { ... },
    # "appeals-agent": { ... },
}


def upload_golden_set(langfuse: Langfuse, agent_name: str, dataset_override: str = None) -> None:
    config = AGENT_GOLDEN_SETS.get(agent_name)
    if not config:
        print(f"ERROR: No golden set registered for '{agent_name}'")
        print(f"Available: {', '.join(AGENT_GOLDEN_SETS.keys())}")
        return

    mod = importlib.import_module(config["module"])
    golden_set = mod.GOLDEN_SET
    dataset_name = dataset_override or config["dataset"]

    try:
        existing = langfuse.get_dataset(dataset_name)
        existing_ids = {item.metadata.get("id") for item in existing.items if item.metadata}
        print(f"Dataset '{dataset_name}' exists with {len(existing.items)} items.")
    except Exception:
        existing = None
        existing_ids = set()
        langfuse.create_dataset(
            name=dataset_name,
            description=f"{agent_name} golden set — locked after baseline",
            metadata={"version": dataset_name, "agent": agent_name},
        )
        print(f"Created dataset '{dataset_name}'")

    added = skipped = 0
    for item in golden_set:
        if item["id"] in existing_ids:
            print(f"  skip  {item['id']}")
            skipped += 1
            continue

        langfuse.create_dataset_item(
            dataset_name=dataset_name,
            input=config["input_fn"](item),
            expected_output=item["expected_output"],
            metadata=config["metadata_fields"](item),
        )
        print(f"  added {item['id']} ({item['category']})")
        added += 1

    print(f"\n{agent_name}: {added} added, {skipped} skipped")
    total = (len(existing.items) if existing else 0) + added
    print(f"Total items in '{dataset_name}': {total}")


def main():
    parser = argparse.ArgumentParser(description="Upload golden sets to Langfuse")
    parser.add_argument("--agent", default=None, help="Agent to upload (default: all)")
    parser.add_argument("--dataset", default=None, help="Override dataset name")
    args = parser.parse_args()

    langfuse = Langfuse(
        public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
        secret_key=os.environ["LANGFUSE_SECRET_KEY"],
        host=os.environ.get("LANGFUSE_HOST", "https://d25s1shy5vv04l.cloudfront.net"),
    )

    agents = [args.agent] if args.agent else list(AGENT_GOLDEN_SETS.keys())
    for agent_name in agents:
        print(f"\n{'='*60}")
        print(f"Uploading: {agent_name}")
        print(f"{'='*60}\n")
        upload_golden_set(langfuse, agent_name, args.dataset)

    print("\nDone. Run experiments next:")
    for agent_name in agents:
        print(f"  uv run python3 tests/evaluation/run_experiment.py --agent {agent_name}")


if __name__ == "__main__":
    main()
