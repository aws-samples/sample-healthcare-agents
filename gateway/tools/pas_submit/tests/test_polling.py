# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Property-based tests for Polling Lambda.

Feature: davinci-pas-alignment
- Property 14: Polling lifecycle
- Property 15: Exponential backoff calculation
"""

import sys
import os

from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from polling_lambda import calculate_backoff_delay, INITIAL_DELAY_SECONDS, MAX_DELAY_SECONDS


# ---------------------------------------------------------------------------
# Property 15: Exponential backoff calculation
# ---------------------------------------------------------------------------

@given(retry_count=st.integers(min_value=0, max_value=20))
@settings(max_examples=100)
def test_exponential_backoff_calculation(retry_count):
    """
    Property 15: Exponential backoff calculation

    For any retry count n (0 <= n <= 20), the delay shall equal
    min(initial_delay * 2^n, max_delay). The delay shall never exceed
    max_delay and never be less than initial_delay.

    Validates: Requirements 10.4
    """
    delay = calculate_backoff_delay(retry_count)

    expected = min(INITIAL_DELAY_SECONDS * (2 ** retry_count), MAX_DELAY_SECONDS)
    assert delay == expected, f"Expected {expected}, got {delay} for retry {retry_count}"

    # Never exceeds max
    assert delay <= MAX_DELAY_SECONDS, f"Delay {delay} exceeds max {MAX_DELAY_SECONDS}"

    # Never less than initial
    assert delay >= INITIAL_DELAY_SECONDS, f"Delay {delay} less than initial {INITIAL_DELAY_SECONDS}"
