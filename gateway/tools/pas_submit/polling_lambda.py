# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Polling Lambda for pended prior authorization requests.

Triggered by EventBridge on a schedule (default: every 15 minutes).
Queries DynamoDB for pended records and calls HealthLake's native
Claim/$inquire to check for resolution.
"""

import json
import logging
import os
from datetime import datetime, timezone, timedelta

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.httpsession import URLLib3Session

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment configuration
PA_STATUS_TABLE = os.getenv("PA_STATUS_TABLE_NAME", "pa-status")
AWS_REGION = os.getenv("HEALTHLAKE_REGION", os.getenv("AWS_DEFAULT_REGION", "us-east-1"))
HEALTHLAKE_DATASTORE_ID = os.getenv("HEALTHLAKE_DATASTORE_ID", "")
HEALTHLAKE_ENDPOINT = f"https://healthlake.{AWS_REGION}.amazonaws.com"
MAX_POLL_DAYS = int(os.getenv("MAX_POLL_DAYS", "30"))

# AWS clients
session = boto3.Session()
credentials = session.get_credentials()
http_session = URLLib3Session()
dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
status_table = dynamodb.Table(PA_STATUS_TABLE)


def healthlake_inquire(inquiry_bundle: dict) -> dict:
    """Call HealthLake Claim/$inquire with SigV4 auth."""
    url = f"{HEALTHLAKE_ENDPOINT}/datastore/{HEALTHLAKE_DATASTORE_ID}/r4/Claim/$inquire"

    request = AWSRequest(
        method="POST",
        url=url,
        data=json.dumps(inquiry_bundle),
        headers={"Content-Type": "application/fhir+json"},
    )
    SigV4Auth(credentials, "healthlake", AWS_REGION).add_auth(request)

    response = http_session.send(request.prepare())
    return {
        "status_code": response.status_code,
        "body": json.loads(response.content) if response.content else {},
    }


def build_inquiry_bundle(record: dict) -> dict:
    """
    Build a Claim/$inquire request Bundle from a DynamoDB tracking record.

    The inquiry uses query-by-example: HealthLake matches on patient, insurer,
    provider, and created date from the original Claim.
    """
    original_bundle = json.loads(record.get("originalBundleJson", "{}"))
    if not original_bundle.get("entry"):
        return None

    # Extract the Claim and required referenced resources
    entries = []
    for entry in original_bundle.get("entry", []):
        resource = entry.get("resource", {})
        rt = resource.get("resourceType", "")
        # Include Claim, Patient, and Organization resources for the inquiry
        if rt in ("Claim", "Patient", "Organization"):
            # For the inquiry, Claim needs profile-claim-inquiry
            if rt == "Claim":
                resource = {**resource}
                resource["meta"] = {
                    "profile": ["http://hl7.org/fhir/us/davinci-pas/StructureDefinition/profile-claim-inquiry"]
                }
            entries.append({"fullUrl": entry.get("fullUrl", ""), "resource": resource})

    if not entries:
        return None

    return {
        "resourceType": "Bundle",
        "id": f"inquiry-{record.get('trackingId', '')}",
        "meta": {
            "profile": ["http://hl7.org/fhir/us/davinci-pas/StructureDefinition/profile-pas-inquiry-request-bundle"]
        },
        "type": "collection",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "entry": entries,
    }


def get_pended_records():
    """Query DynamoDB for pended records within the max polling duration."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=MAX_POLL_DAYS)).isoformat()
    try:
        response = status_table.query(
            IndexName="status-createdAt-index",
            KeyConditionExpression=boto3.dynamodb.conditions.Key("status").eq("pended")
            & boto3.dynamodb.conditions.Key("createdAt").gte(cutoff),
        )
        return response.get("Items", [])
    except Exception as e:
        logger.error("Failed to query pended records: %s", str(e))
        return []


def update_record(record, claim_response):
    """Update a DynamoDB record with the resolved ClaimResponse from $inquire."""
    tracking_id = record.get("trackingId")
    now = datetime.now(timezone.utc).isoformat()

    outcome = claim_response.get("outcome", "queued")
    disposition = claim_response.get("disposition", "")
    pre_auth_ref = claim_response.get("preAuthRef", "")

    if outcome == "queued":
        new_status = "pended"
    elif outcome == "complete":
        new_status = "approved" if "approved" in disposition.lower() else "denied"
    elif outcome == "error":
        new_status = "denied"
    else:
        new_status = "pended"

    try:
        status_table.update_item(
            Key={"trackingId": tracking_id},
            UpdateExpression=(
                "SET #s = :status, claimResponseJson = :crj, "
                "resolvedAt = :resolved, disposition = :disp, preAuthRef = :par, "
                "pollCount = pollCount + :inc, lastPollAt = :now"
            ),
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":status": new_status,
                ":crj": json.dumps(claim_response),
                ":resolved": now if new_status != "pended" else "",
                ":disp": disposition,
                ":par": pre_auth_ref,
                ":inc": 1,
                ":now": now,
            },
        )
        logger.info("Updated record %s: outcome=%s → status=%s", tracking_id, outcome, new_status)
    except Exception as e:
        logger.error("Failed to update record %s: %s", tracking_id, str(e))


def handler(event, context):
    """EventBridge scheduled handler — polls pended PA requests via HealthLake $inquire."""
    logger.info("Polling Lambda triggered")

    if not HEALTHLAKE_DATASTORE_ID:
        logger.error("HEALTHLAKE_DATASTORE_ID not configured")
        return {"error": "HEALTHLAKE_DATASTORE_ID not configured"}

    records = get_pended_records()
    logger.info("Found %d pended records to poll", len(records))

    resolved_count = 0
    error_count = 0

    for record in records:
        tracking_id = record.get("trackingId", "unknown")
        try:
            inquiry_bundle = build_inquiry_bundle(record)
            if not inquiry_bundle:
                logger.warning("Cannot build inquiry bundle for %s — missing original bundle", tracking_id)
                error_count += 1
                continue

            result = healthlake_inquire(inquiry_bundle)

            if result["status_code"] == 200:
                # Extract ClaimResponse from the response bundle
                response_bundle = result["body"]
                claim_responses = [
                    e.get("resource", {})
                    for e in response_bundle.get("entry", [])
                    if e.get("resource", {}).get("resourceType") == "ClaimResponse"
                ]
                if claim_responses:
                    # Use the most recent ClaimResponse
                    latest_cr = sorted(
                        claim_responses,
                        key=lambda cr: cr.get("created", ""),
                        reverse=True,
                    )[0]
                    update_record(record, latest_cr)
                    if latest_cr.get("outcome") != "queued":
                        resolved_count += 1
                else:
                    logger.info("No ClaimResponse in $inquire result for %s", tracking_id)
            else:
                logger.warning(
                    "$inquire returned %d for %s: %s",
                    result["status_code"], tracking_id, json.dumps(result["body"])[:200],
                )
                error_count += 1

        except Exception as e:
            error_count += 1
            logger.error("Error polling %s: %s", tracking_id, str(e))

    logger.info("Polling complete: %d polled, %d resolved, %d errors", len(records), resolved_count, error_count)
    return {"polled": len(records), "resolved": resolved_count, "errors": error_count}
