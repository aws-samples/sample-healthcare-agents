# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Threat T2 mitigation — provider NPI identity check.

Asserts:
- A bundle whose Claim.provider NPI matches the caller's token NPI is accepted.
- A bundle whose Claim.provider NPI does NOT match the caller's token NPI is
  rejected with a clear error message.
- A bundle without an NPI on the referenced Practitioner is rejected.
- A caller without an NPI claim is allowed through with an audit-only log
  (service principals do not have an NPI; payor-side enforces).
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def lambda_module():
    path = Path(__file__).resolve().parent.parent / "pas_submit_lambda.py"
    # Avoid actually creating boto sessions etc. by stubbing AWS env first.
    os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
    spec = importlib.util.spec_from_file_location("pas_submit_lambda", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _bundle_with_npi(provider_npi: str | None) -> dict:
    practitioner = {
        "resourceType": "Practitioner",
        "id": "prac-1",
    }
    if provider_npi is not None:
        practitioner["identifier"] = [
            {
                "system": "http://hl7.org/fhir/sid/us-npi",
                "value": provider_npi,
            }
        ]
    return {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [
            {
                "resource": {
                    "resourceType": "Claim",
                    "use": "preauthorization",
                    "provider": {"reference": "Practitioner/prac-1"},
                }
            },
            {"resource": practitioner},
        ],
    }


def test_npi_match_allows_submission(lambda_module):
    bundle = _bundle_with_npi("1234567893")
    err = lambda_module._validate_provider_identity(
        bundle, {"sub": "alice", "custom:npi": "1234567893"}
    )
    assert err is None


def test_npi_mismatch_returns_403_message(lambda_module):
    bundle = _bundle_with_npi("1234567893")
    err = lambda_module._validate_provider_identity(
        bundle, {"sub": "alice", "custom:npi": "9999999999"}
    )
    assert err is not None
    assert "1234567893" in err
    assert "9999999999" in err


def test_bundle_without_npi_is_rejected(lambda_module):
    bundle = _bundle_with_npi(None)
    err = lambda_module._validate_provider_identity(
        bundle, {"sub": "alice", "custom:npi": "1234567893"}
    )
    assert err is not None
    assert "valid 10-digit US NPI" in err


def test_invalid_npi_format_is_rejected(lambda_module):
    bundle = _bundle_with_npi("ABCDEF1234")  # not all digits
    err = lambda_module._validate_provider_identity(
        bundle, {"sub": "alice", "custom:npi": "1234567893"}
    )
    assert err is not None


def test_caller_without_npi_claim_is_allowed_through(lambda_module):
    # Service principals (client_credentials grant) do not have NPI on token.
    # Payor-side enforces. This path logs but does not reject.
    bundle = _bundle_with_npi("1234567893")
    err = lambda_module._validate_provider_identity(
        bundle, {"sub": "service-account-x"}
    )
    assert err is None
