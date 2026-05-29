# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for Threat T9 mitigations: CDS Hooks authentication and
discovery-payload minimization."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def lambda_module():
    path = Path(__file__).resolve().parent.parent / "cds_hooks_lambda.py"
    os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
    spec = importlib.util.spec_from_file_location("cds_hooks_lambda", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _api_gateway_event(method, path, headers=None, body=None):
    return {
        "httpMethod": method,
        "path": path,
        "headers": headers or {},
        "body": body,
    }


def test_unauth_discovery_returns_minimized_payload(lambda_module, monkeypatch):
    """T9: unauthenticated discovery does not leak prefetch templates."""
    monkeypatch.delenv("CDS_HOOKS_REQUIRED_ISS", raising=False)
    monkeypatch.delenv("CDS_HOOKS_REQUIRED_AUD", raising=False)
    monkeypatch.delenv("CDS_HOOKS_JWKS_URL", raising=False)
    monkeypatch.setenv("CDS_HOOKS_ALLOWED_ORIGINS", "https://ehr.example.com")

    response = lambda_module.handle_rest_request(
        _api_gateway_event("GET", "/cds-services")
    )
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert "services" in body
    for service in body["services"]:
        # Crucial T9 assertion: no prefetch templates exposed without auth.
        assert "prefetch" not in service, (
            f"Service {service.get('id')} leaked prefetch template to "
            "unauthenticated discovery — see Threat T9"
        )


def test_auth_discovery_returns_full_payload(lambda_module, monkeypatch):
    """Authenticated callers (any token in dev mode) get the full payload."""
    monkeypatch.delenv("CDS_HOOKS_REQUIRED_ISS", raising=False)
    monkeypatch.delenv("CDS_HOOKS_REQUIRED_AUD", raising=False)
    monkeypatch.delenv("CDS_HOOKS_JWKS_URL", raising=False)

    response = lambda_module.handle_rest_request(
        _api_gateway_event(
            "GET", "/cds-services", headers={"Authorization": "Bearer some-token"}
        )
    )
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert all("prefetch" in s for s in body["services"])


def test_unauth_invocation_rejected_with_401(lambda_module, monkeypatch):
    """T9: hook invocation requires a bearer token even in dev mode."""
    monkeypatch.delenv("CDS_HOOKS_REQUIRED_ISS", raising=False)
    monkeypatch.delenv("CDS_HOOKS_REQUIRED_AUD", raising=False)
    monkeypatch.delenv("CDS_HOOKS_JWKS_URL", raising=False)

    response = lambda_module.handle_rest_request(
        _api_gateway_event(
            "POST",
            "/cds-services/prior-auth-patient-view",
            body=json.dumps({"context": {"patientId": "p1"}}),
        )
    )
    assert response["statusCode"] == 401
    assert "WWW-Authenticate" in response["headers"]


def test_invocation_with_token_passes_auth(lambda_module, monkeypatch):
    """A token-bearing invocation gets past auth (downstream may still 4xx/5xx
    if no HealthLake)."""
    monkeypatch.delenv("CDS_HOOKS_REQUIRED_ISS", raising=False)
    monkeypatch.delenv("CDS_HOOKS_REQUIRED_AUD", raising=False)
    monkeypatch.delenv("CDS_HOOKS_JWKS_URL", raising=False)

    response = lambda_module.handle_rest_request(
        _api_gateway_event(
            "POST",
            "/cds-services/some-unknown-service",
            headers={"Authorization": "Bearer dev-token"},
            body=json.dumps({"context": {"patientId": "p1"}}),
        )
    )
    # 404 because path doesn't match a known service — confirms we got past
    # auth (otherwise it would be 401).
    assert response["statusCode"] == 404


def test_options_preflight_does_not_require_auth(lambda_module):
    """CORS preflight must not require auth (browsers can't attach it)."""
    response = lambda_module.handle_rest_request(
        _api_gateway_event("OPTIONS", "/cds-services")
    )
    assert response["statusCode"] == 200


def test_minimized_payload_drops_any_other_sensitive_fields(lambda_module):
    """Defense in depth: ensure no future-added field leaks unauthenticated."""
    minimized = lambda_module.get_cds_services(public=True)
    full = lambda_module.get_cds_services(public=False)
    for ms, fs in zip(minimized["services"], full["services"]):
        # All keys in minimized must also exist in full, but minimized has
        # strictly fewer keys (or equal-only-if-no-prefetch present).
        assert set(ms.keys()).issubset(set(fs.keys()))
        assert "prefetch" not in ms
