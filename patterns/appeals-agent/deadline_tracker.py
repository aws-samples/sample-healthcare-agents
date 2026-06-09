# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Deadline Tracker module for appeal filing compliance.

Enforces payer-specific filing deadlines and tracks appeal status.
Pure-function module imported by the Appeals Agent.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

# Payer-specific filing deadlines (calendar days from denial date)
# These are sample values — customers must replace with actual contracted deadlines.
FILING_DEADLINES: dict[str, dict[str, int]] = {
    "default": {
        "first_level": 180,
        "second_level": 60,
        "external_review": 120,
        "peer_to_peer": 10,  # business days, but stored as calendar for simplicity
    },
    "medicare": {
        "first_level": 120,   # Redetermination by MAC
        "second_level": 180,  # Reconsideration by QIC
        "external_review": 60,  # ALJ hearing
    },
    "medicaid": {
        "first_level": 60,
        "second_level": 30,
    },
    "blue cross blue shield": {
        "first_level": 180,
        "second_level": 60,
        "peer_to_peer": 10,
    },
    "unitedhealthcare": {
        "first_level": 180,
        "second_level": 60,
        "peer_to_peer": 10,
    },
    "aetna": {
        "first_level": 180,
        "second_level": 60,
        "peer_to_peer": 10,
    },
    "cigna": {
        "first_level": 180,
        "second_level": 60,
        "external_review": 120,
    },
}


@dataclass
class DeadlineStatus:
    """Filing deadline assessment for an appeal."""

    payer: str
    appeal_level: str
    denial_date: str
    filing_deadline: str
    days_remaining: int
    is_expired: bool
    urgency: str  # "expired" | "critical" | "urgent" | "normal"


def check_filing_deadline(
    payer_name: str,
    denial_date_str: str,
    appeal_level: str = "first_level",
) -> DeadlineStatus:
    """
    Check whether the filing deadline has passed for a given appeal.

    Args:
        payer_name: Name of the payer (matched case-insensitively)
        denial_date_str: Denial date in YYYY-MM-DD format
        appeal_level: One of first_level, second_level, external_review, peer_to_peer

    Returns:
        DeadlineStatus with days remaining and urgency classification
    """
    denial_date = datetime.strptime(denial_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)

    # Look up payer deadlines (case-insensitive partial match)
    payer_key = "default"
    payer_lower = payer_name.lower()
    for key in FILING_DEADLINES:
        if key in payer_lower:
            payer_key = key
            break

    deadlines = FILING_DEADLINES[payer_key]
    deadline_days = deadlines.get(appeal_level, deadlines.get("first_level", 180))

    filing_deadline = denial_date + timedelta(days=deadline_days)
    days_remaining = (filing_deadline - now).days

    if days_remaining < 0:
        urgency = "expired"
    elif days_remaining <= 7:
        urgency = "critical"
    elif days_remaining <= 30:
        urgency = "urgent"
    else:
        urgency = "normal"

    return DeadlineStatus(
        payer=payer_name,
        appeal_level=appeal_level,
        denial_date=denial_date_str,
        filing_deadline=filing_deadline.strftime("%Y-%m-%d"),
        days_remaining=max(days_remaining, 0),
        is_expired=days_remaining < 0,
        urgency=urgency,
    )
