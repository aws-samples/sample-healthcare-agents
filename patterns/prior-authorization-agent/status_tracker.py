# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Status Tracker module for persisting and querying ClaimResponse statuses.

Stores prior authorization decisions in DynamoDB with support for:
- Persistence of ClaimResponse with metadata
- Query by user with optional status and date range filters
- Status updates for pended request resolution
"""

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import boto3
from boto3.dynamodb.conditions import Key, Attr

# Environment configuration
TABLE_NAME = os.getenv("PA_STATUS_TABLE_NAME", "pa-status")
TTL_DAYS = int(os.getenv("PA_STATUS_TTL_DAYS", "365"))

dynamodb = boto3.resource("dynamodb", region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"))


class StatusTracker:
    """Tracks prior authorization ClaimResponse statuses in DynamoDB."""

    def __init__(self, table_name: str | None = None):
        self.table = dynamodb.Table(table_name or TABLE_NAME)

    def persist_claim_response(
        self,
        claim_response: dict,
        claim_reference: str,
        patient_id: str,
        procedure_code: str,
        payer_name: str,
        user_id: str,
    ) -> str:
        """
        Write a ClaimResponse and metadata to DynamoDB.

        Returns the tracking ID (UUID).
        """
        tracking_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        ttl_epoch = int((datetime.now(timezone.utc) + timedelta(days=TTL_DAYS)).timestamp())

        # Derive status from ClaimResponse outcome
        outcome = claim_response.get("outcome", "")
        if outcome == "queued":
            status = "pended"
        elif outcome == "complete":
            # Error entries → denied; otherwise → approved
            status = "denied" if claim_response.get("error") else "approved"
        else:
            status = "error"

        # Extract display fields
        patient_name = ""
        disposition = claim_response.get("disposition", "")
        pre_auth_ref = claim_response.get("preAuthRef", "")
        procedure_display = ""

        item = {
            "trackingId": tracking_id,
            "userId": user_id,
            "createdAt": now,
            "status": status,
            "patientId": patient_id,
            "patientName": patient_name,
            "procedureCode": procedure_code,
            "procedureDisplay": procedure_display,
            "payerName": payer_name,
            "claimReference": claim_reference,
            "claimResponseJson": json.dumps(claim_response),
            "preAuthRef": pre_auth_ref,
            "disposition": disposition,
            "pollCount": 0,
            "ttl": ttl_epoch,
        }

        self.table.put_item(Item=item)
        return tracking_id

    def query_by_user(
        self,
        user_id: str,
        status_filter: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict]:
        """
        Query status records for a user, with optional filters.

        Uses the userId-createdAt-index GSI.
        """
        key_condition = Key("userId").eq(user_id)

        if date_from and date_to:
            key_condition = key_condition & Key("createdAt").between(date_from, date_to)
        elif date_from:
            key_condition = key_condition & Key("createdAt").gte(date_from)
        elif date_to:
            key_condition = key_condition & Key("createdAt").lte(date_to)

        kwargs = {
            "IndexName": "userId-createdAt-index",
            "KeyConditionExpression": key_condition,
            "ScanIndexForward": False,  # newest first
        }

        if status_filter:
            kwargs["FilterExpression"] = Attr("status").eq(status_filter)

        response = self.table.query(**kwargs)
        return response.get("Items", [])

    def update_status(self, tracking_id: str, updated_response: dict) -> None:
        """
        Update a pended record with a resolved ClaimResponse.

        Sets resolvedAt timestamp and updates status based on new outcome.
        """
        now = datetime.now(timezone.utc).isoformat()
        outcome = updated_response.get("outcome", "")

        if outcome == "complete":
            new_status = "denied" if updated_response.get("error") else "approved"
        elif outcome == "queued":
            new_status = "pended"
        else:
            new_status = "error"

        self.table.update_item(
            Key={"trackingId": tracking_id},
            UpdateExpression=(
                "SET #s = :status, claimResponseJson = :crj, "
                "resolvedAt = :resolved, disposition = :disp, preAuthRef = :par"
            ),
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":status": new_status,
                ":crj": json.dumps(updated_response),
                ":resolved": now,
                ":disp": updated_response.get("disposition", ""),
                ":par": updated_response.get("preAuthRef", ""),
            },
        )
