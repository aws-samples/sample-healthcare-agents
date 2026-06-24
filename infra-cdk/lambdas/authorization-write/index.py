# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Authorization Write API Lambda.

User-initiated persistence of a prior-authorization decision to AWS HealthLake.
The agent only *recommends* a decision; a human clicks "Save Authorization",
which POSTs the generated FHIR ClaimResponse here. This is a CREATE-ONLY
endpoint restricted to ClaimResponse / Task resource types — it cannot update
or delete, and cannot write arbitrary resource types.
"""

import json
import os

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.httpsession import URLLib3Session

AWS_REGION = os.getenv("HEALTHLAKE_REGION", "us-east-1")
DATASTORE_ID = os.getenv("HEALTHLAKE_DATASTORE_ID", "")
CORS_ORIGINS = os.getenv("CORS_ALLOWED_ORIGINS", "*")

# Only these resource types may be created through this endpoint.
ALLOWED_RESOURCE_TYPES = {"ClaimResponse", "Task"}

_session = boto3.Session()
_credentials = _session.get_credentials()
_http = URLLib3Session()


def _cors_headers(origin):
    allowed = [o.strip() for o in CORS_ORIGINS.split(",") if o.strip()]
    allow = origin if origin in allowed else (allowed[0] if allowed else "*")
    return {
        "Access-Control-Allow-Origin": allow,
        "Access-Control-Allow-Headers": "Content-Type,Authorization",
        "Access-Control-Allow-Methods": "POST,OPTIONS",
        "Content-Type": "application/json",
    }


def _create(resource_type, resource):
    url = f"https://healthlake.{AWS_REGION}.amazonaws.com/datastore/{DATASTORE_ID}/r4/{resource_type}"
    body = json.dumps(resource).encode("utf-8")
    req = AWSRequest(
        method="POST",
        url=url,
        data=body,
        headers={"Content-Type": "application/fhir+json", "Accept": "application/fhir+json"},
    )
    SigV4Auth(_credentials, "healthlake", AWS_REGION).add_auth(req)
    resp = _http.send(req.prepare())
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"HealthLake returned {resp.status_code}: {resp.text[:300]}")
    return json.loads(resp.text)


def handler(event, _context):
    origin = (event.get("headers") or {}).get("origin") or (event.get("headers") or {}).get("Origin") or ""
    headers = _cors_headers(origin)

    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": headers, "body": ""}

    if not DATASTORE_ID:
        return {"statusCode": 500, "headers": headers, "body": json.dumps({"error": "Datastore not configured"})}

    try:
        body = json.loads(event.get("body") or "{}")
    except (ValueError, TypeError):
        return {"statusCode": 400, "headers": headers, "body": json.dumps({"error": "Invalid JSON body"})}

    # Accept either {resource: {...}} or the bare FHIR resource.
    resource = body.get("resource") if isinstance(body, dict) and "resource" in body else body
    if not isinstance(resource, dict):
        return {"statusCode": 400, "headers": headers, "body": json.dumps({"error": "Missing FHIR resource"})}

    resource_type = resource.get("resourceType")
    if resource_type not in ALLOWED_RESOURCE_TYPES:
        return {
            "statusCode": 400,
            "headers": headers,
            "body": json.dumps({
                "error": f"resourceType must be one of {sorted(ALLOWED_RESOURCE_TYPES)}"
            }),
        }

    try:
        created = _create(resource_type, resource)
    except Exception as e:
        print(f"Authorization write error: {type(e).__name__}")
        return {"statusCode": 502, "headers": headers, "body": json.dumps({"error": "Save to HealthLake failed", "detail": str(e)[:300]})}

    return {
        "statusCode": 201,
        "headers": headers,
        "body": json.dumps({
            "created": True,
            "resourceType": created.get("resourceType", resource_type),
            "id": created.get("id"),
            "lastUpdated": (created.get("meta") or {}).get("lastUpdated"),
        }),
    }
