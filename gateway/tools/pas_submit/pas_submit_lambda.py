# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Claim/$submit and Claim/$inquire Lambda — backed by HealthLake native PAS operations.

$submit: Forwards PAS Bundles to HealthLake's native Claim/$submit endpoint.
         HealthLake validates against Da Vinci PAS profiles, persists all resources,
         and returns a ClaimResponse with outcome="queued".

$inquire: Calls HealthLake's native Claim/$inquire to check the status of a
          previously submitted prior authorization request.

Both operations use SigV4 authentication to call HealthLake.
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.httpsession import URLLib3Session

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment configuration
AWS_REGION = os.getenv("HEALTHLAKE_REGION", os.getenv("AWS_DEFAULT_REGION", "us-east-1"))
HEALTHLAKE_DATASTORE_ID = os.getenv("HEALTHLAKE_DATASTORE_ID", "")
HEALTHLAKE_ENDPOINT = f"https://healthlake.{AWS_REGION}.amazonaws.com"

# AWS session and credentials
session = boto3.Session()
credentials = session.get_credentials()
http_session = URLLib3Session()


def _healthlake_post(operation_path: str, body: dict) -> dict:
    """
    POST to HealthLake FHIR endpoint with SigV4 auth.

    Args:
        operation_path: e.g. "Claim/$submit" or "Claim/$inquire"
        body: FHIR Bundle dict

    Returns:
        dict with 'status_code' and 'body' (parsed JSON)
    """
    url = f"{HEALTHLAKE_ENDPOINT}/datastore/{HEALTHLAKE_DATASTORE_ID}/r4/{operation_path}"

    request = AWSRequest(
        method="POST",
        url=url,
        data=json.dumps(body),
        headers={"Content-Type": "application/fhir+json"},
    )
    SigV4Auth(credentials, "healthlake", AWS_REGION).add_auth(request)

    response = http_session.send(request.prepare())
    response_body = json.loads(response.content) if response.content else {}

    return {
        "status_code": response.status_code,
        "body": response_body,
    }


def _operation_outcome(severity, code, diagnostics):
    """Build a FHIR OperationOutcome resource."""
    return {
        "resourceType": "OperationOutcome",
        "issue": [{"severity": severity, "code": code, "diagnostics": diagnostics}],
    }


def _validate_bundle(bundle):
    """Basic client-side validation before sending to HealthLake."""
    if not isinstance(bundle, dict):
        return "Request body must be a JSON object"
    if bundle.get("resourceType") != "Bundle":
        return "Resource must be a FHIR Bundle"
    if bundle.get("type") != "collection":
        return "Bundle.type must be 'collection'"

    entries = bundle.get("entry", [])
    if not entries:
        return "Bundle must contain at least one entry"

    # Check for exactly one Claim with use=preauthorization
    claims = [
        e.get("resource", {})
        for e in entries
        if e.get("resource", {}).get("resourceType") == "Claim"
        and e.get("resource", {}).get("use") == "preauthorization"
    ]
    if len(claims) == 0:
        return "Bundle must contain a Claim resource with use='preauthorization'"
    if len(claims) > 1:
        return f"Bundle must contain exactly one preauthorization Claim, found {len(claims)}"

    return None  # Valid


def _extract_provider_npi(bundle):
    """Extract the provider NPI from a PAS Bundle's Claim.provider reference.

    Returns the NPI digits or None if not found / malformed.
    """
    if not isinstance(bundle, dict):
        return None
    entries = bundle.get("entry", [])
    claim = next(
        (e.get("resource", {}) for e in entries
         if e.get("resource", {}).get("resourceType") == "Claim"),
        {},
    )
    provider_ref = (claim.get("provider") or {}).get("reference") or ""
    if not provider_ref.startswith("Practitioner/") and not provider_ref.startswith("Organization/"):
        return None
    ref_id = provider_ref.split("/", 1)[1]

    # Find the referenced Practitioner / Organization in the bundle
    for entry in entries:
        resource = entry.get("resource", {})
        if resource.get("id") != ref_id:
            continue
        for ident in resource.get("identifier") or []:
            system = ident.get("system", "")
            if "us-npi" in system or system == "http://hl7.org/fhir/sid/us-npi":
                value = ident.get("value", "")
                if value.isdigit() and len(value) == 10:
                    return value
    return None


def _validate_provider_identity(bundle, claims_principal):
    """Mitigates Threat T2: prevent submission with a provider NPI
    that does not match the authenticated caller's claimed NPI.

    The Cognito JWT is expected to carry a custom claim ``custom:npi`` for
    healthcare provider users. Bundles submitted by a user whose token NPI
    does not match the bundle's Claim.provider NPI are rejected.

    For service principals (Cognito client-credentials grant) without an
    NPI claim, fall through and let payor-side rules enforce. Logged for
    audit.
    """
    bundle_npi = _extract_provider_npi(bundle)
    if not bundle_npi:
        return "Bundle Claim.provider must reference a Practitioner or Organization with a valid 10-digit US NPI"

    token_npi = (claims_principal or {}).get("custom:npi")
    if not token_npi:
        # No NPI in token (likely a service principal or pre-rollout user).
        # Log for audit but do not reject — payor-side will catch impersonation.
        logger.info(
            "provider_npi_check=no_token_npi bundle_npi=%s sub=%s",
            bundle_npi,
            (claims_principal or {}).get("sub"),
        )
        return None

    if token_npi != bundle_npi:
        logger.warning(
            "provider_npi_check=mismatch bundle_npi=%s token_npi=%s sub=%s",
            bundle_npi,
            token_npi,
            (claims_principal or {}).get("sub"),
        )
        return f"Authenticated provider NPI ({token_npi}) does not match Claim.provider NPI ({bundle_npi})"

    logger.info("provider_npi_check=ok npi=%s", bundle_npi)
    return None


def _cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
        "Content-Type": "application/fhir+json",
    }


def handler(event, context):
    """
    Handles both $submit and $inquire based on the request path.

    POST /Claim/$submit  → Forward to HealthLake Claim/$submit
    POST /Claim/$inquire → Forward to HealthLake Claim/$inquire
    """
    headers = _cors_headers()

    # Handle CORS preflight
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": headers, "body": ""}

    if not HEALTHLAKE_DATASTORE_ID:
        return {
            "statusCode": 500,
            "headers": headers,
            "body": json.dumps(_operation_outcome("error", "exception", "HEALTHLAKE_DATASTORE_ID not configured")),
        }

    try:
        # Parse request body
        body_str = event.get("body", "")
        if not body_str:
            return {
                "statusCode": 400,
                "headers": headers,
                "body": json.dumps(_operation_outcome("error", "invalid", "Request body is empty")),
            }

        try:
            bundle = json.loads(body_str)
        except json.JSONDecodeError as e:
            return {
                "statusCode": 400,
                "headers": headers,
                "body": json.dumps(_operation_outcome("error", "invalid", f"Invalid JSON: {e}")),
            }

        # Determine operation from path
        path = event.get("path", "") or event.get("rawPath", "")
        if "$inquire" in path:
            operation = "Claim/$inquire"
        else:
            operation = "Claim/$submit"

        # Client-side validation
        error_msg = _validate_bundle(bundle)
        if error_msg:
            return {
                "statusCode": 400,
                "headers": headers,
                "body": json.dumps(_operation_outcome("error", "invalid", error_msg)),
            }

        # Mitigates Threat T2 — provider identity must match the
        # authenticated caller's NPI claim. Only enforced for $submit; an
        # $inquire is a status check, not a new authorization.
        if operation == "Claim/$submit":
            claims_principal = (
                event.get("requestContext", {})
                .get("authorizer", {})
                .get("claims", {})
            )
            identity_err = _validate_provider_identity(bundle, claims_principal)
            if identity_err:
                return {
                    "statusCode": 403,
                    "headers": headers,
                    "body": json.dumps(_operation_outcome("error", "forbidden", identity_err)),
                }

        logger.info("Forwarding to HealthLake %s (datastore: %s)", operation, HEALTHLAKE_DATASTORE_ID)

        # Forward to HealthLake native PAS operation
        result = _healthlake_post(operation, bundle)

        logger.info("HealthLake %s returned status %d", operation, result["status_code"])

        return {
            "statusCode": result["status_code"],
            "headers": headers,
            "body": json.dumps(result["body"]),
        }

    except Exception as e:
        logger.error("Internal error: %s", str(e), exc_info=True)
        return {
            "statusCode": 500,
            "headers": headers,
            "body": json.dumps(_operation_outcome("error", "exception", f"Internal error: {str(e)}")),
        }
