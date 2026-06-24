# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Patient Search API Lambda.

Provides a fast, structured patient search over AWS HealthLake (FHIR R4) for the
authenticated frontend. Searches by patient name (prefix) or FHIR id.

Returns a JSON array of { id, name, birthDate, gender } — no PHI is logged.
"""

import json
import os
import re

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.httpsession import URLLib3Session

AWS_REGION = os.getenv("HEALTHLAKE_REGION", "us-east-1")
DATASTORE_ID = os.getenv("HEALTHLAKE_DATASTORE_ID", "")
CORS_ORIGINS = os.getenv("CORS_ALLOWED_ORIGINS", "*")

_session = boto3.Session()
_credentials = _session.get_credentials()
_http = URLLib3Session()

_UUID_LIKE = re.compile(r"^[0-9a-fA-F-]{16,}$")


def _cors_headers(origin):
    allowed = [o.strip() for o in CORS_ORIGINS.split(",") if o.strip()]
    allow = origin if origin in allowed else (allowed[0] if allowed else "*")
    return {
        "Access-Control-Allow-Origin": allow,
        "Access-Control-Allow-Headers": "Content-Type,Authorization",
        "Access-Control-Allow-Methods": "GET,OPTIONS",
        "Content-Type": "application/json",
    }


def _fhir_search(resource_type, params):
    base = f"https://healthlake.{AWS_REGION}.amazonaws.com/datastore/{DATASTORE_ID}/r4/{resource_type}"
    from urllib.parse import urlencode

    url = f"{base}?{urlencode(params)}"
    req = AWSRequest(method="GET", url=url, headers={"Accept": "application/fhir+json"})
    SigV4Auth(_credentials, "healthlake", AWS_REGION).add_auth(req)
    resp = _http.send(req.prepare())
    if resp.status_code != 200:
        raise RuntimeError(f"HealthLake returned {resp.status_code}")
    return json.loads(resp.text)


def _coverage_for_patient(patient_id):
    """Best-effort active Coverage lookup -> (payor_name, member_id).

    Returns (None, None) on any error so the patient lookup still succeeds.
    """
    try:
        bundle = _fhir_search("Coverage", {"patient": patient_id, "_count": "5"})
    except Exception:
        return None, None
    for entry in bundle.get("entry", []):
        cov = entry.get("resource", {})
        if cov.get("resourceType") != "Coverage":
            continue
        payor_name = None
        for payor in cov.get("payor", []) or []:
            if payor.get("display"):
                payor_name = payor["display"]
                break
        member_id = cov.get("subscriberId")
        if not member_id:
            for ident in cov.get("identifier", []) or []:
                if ident.get("value"):
                    member_id = ident["value"]
                    break
        if payor_name or member_id:
            return payor_name, member_id
    return None, None


def _active_conditions_for_patient(patient_id):
    """Best-effort list of the patient's condition display strings. Empty on
    error. Includes resolved conditions too (Synthea data is often all
    'resolved'), so the form has useful patient context to show."""
    try:
        bundle = _fhir_search("Condition", {"patient": patient_id, "_count": "20"})
    except Exception:
        return []
    conditions = []
    for entry in bundle.get("entry", []):
        res = entry.get("resource", {})
        if res.get("resourceType") != "Condition":
            continue
        cc = res.get("code", {}) or {}
        label = cc.get("text")
        if not label:
            for c in cc.get("coding", []) or []:
                if c.get("display"):
                    label = c["display"]
                    break
        if label and label not in conditions:
            conditions.append(label)
    return conditions


def _format_name(name_field):
    if not name_field:
        return None
    entry = name_field[0] if isinstance(name_field, list) else name_field
    if not isinstance(entry, dict):
        return None
    raw = entry.get("text")
    if not raw:
        given = " ".join(entry.get("given", []) or [])
        family = entry.get("family", "") or ""
        raw = f"{given} {family}".strip()
    if not raw:
        return None
    cleaned = re.sub(r"\d+", "", raw)
    return re.sub(r"\s+", " ", cleaned).strip() or None


def handler(event, _context):
    origin = (event.get("headers") or {}).get("origin") or (event.get("headers") or {}).get("Origin") or ""
    headers = _cors_headers(origin)

    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": headers, "body": ""}

    if not DATASTORE_ID:
        return {"statusCode": 500, "headers": headers, "body": json.dumps({"error": "Datastore not configured"})}

    qs = event.get("queryStringParameters") or {}
    q = (qs.get("q") or "").strip()
    if not q:
        return {"statusCode": 400, "headers": headers, "body": json.dumps({"error": "Missing query parameter 'q'"})}

    try:
        is_id_query = bool(_UUID_LIKE.match(q))
        params = {"_id": q} if is_id_query else {"name": q, "_count": "20"}
        bundle = _fhir_search("Patient", params)
    except Exception as e:
        print(f"Patient search error: {type(e).__name__}")
        return {"statusCode": 502, "headers": headers, "body": json.dumps({"error": "Search failed"})}

    patients = []
    for entry in bundle.get("entry", []):
        r = entry.get("resource", {})
        if r.get("resourceType") != "Patient":
            continue
        patients.append(
            {
                "id": r.get("id"),
                "name": _format_name(r.get("name")),
                "birthDate": r.get("birthDate"),
                "gender": r.get("gender"),
            }
        )

    # For a single, exact patient match (ID lookup), enrich with insurance
    # (payer + member ID from active Coverage) and active conditions so the
    # New Order form can auto-populate those fields deterministically.
    if is_id_query and len(patients) == 1:
        pid = patients[0]["id"]
        payor_name, member_id = _coverage_for_patient(pid)
        patients[0]["payorName"] = payor_name
        patients[0]["memberId"] = member_id
        patients[0]["conditions"] = _active_conditions_for_patient(pid)

    return {"statusCode": 200, "headers": headers, "body": json.dumps({"patients": patients})}
