#!/usr/bin/env python3
"""
Test threshold breach detection by submitting 3 medication errors.

This will trigger:
1. Individual high-severity alerts for each event (physicians + safety officers)
2. Threshold breach alert after 3rd event (safety officers only)
"""

import time
from pathlib import Path
from dotenv import load_dotenv
from test_hospital_safety import invoke_safety_agent, get_cognito_token

# Load credentials
env_path = Path(__file__).parent.parent.parent.parent / "infra-cdk" / ".env"
if env_path.exists():
    load_dotenv(env_path)

# Three different medication errors
medication_errors = [
    """
    Medication Error #1:
    Patient in room 401 received 50mg of Metoprolol instead of prescribed 25mg.
    Patient's heart rate dropped to 48 bpm. Cardiology consulted. Error discovered
    during medication reconciliation.
    """.strip(),
    """
    Medication Error #2:
    Wrong patient received insulin dose intended for diabetic patient in adjacent room.
    Non-diabetic patient experienced hypoglycemia (blood glucose 52 mg/dL). Given D50
    bolus. Error caught when correct patient asked about missed insulin dose.
    """.strip(),
    """
    Medication Error #3:
    Patient received Coumadin 10mg instead of prescribed 5mg. INR elevated to 4.2
    (therapeutic range 2-3). Patient developed minor epistaxis. Vitamin K administered.
    High bleeding risk. Error discovered during routine INR check.
    """.strip(),
]

print("=" * 80)
print("THRESHOLD BREACH TEST")
print("=" * 80)
print("\nSubmitting 3 medication errors to trigger threshold breach alert...")
print(
    "\nExpected behavior:"
)
print("  - Events 1-3: Individual high-severity alerts to both physicians and safety officers")
print("  - Event 3: Additional threshold breach alert to safety officers only")
print(
    "\nCheck emails:"
)
print("  - physician@example.com (3 individual alerts)")
print(
    "  - safety@example.com (3 individual alerts + 1 threshold breach alert)"
)
print("=" * 80)

# Get JWT token once
jwt_token = get_cognito_token()

# Submit 3 medication errors with delay between them
for i, error_text in enumerate(medication_errors, 1):
    print(f"\n\n{'='*80}")
    print(f"Submitting Medication Error #{i}/3")
    print(f"{'='*80}")
    print(f"Event text: {error_text[:100]}...")

    try:
        result = invoke_safety_agent(
            error_text, user_id=f"threshold-test-{i}", jwt_token=jwt_token
        )
        print(f"\n✅ Event {i} submitted successfully")

        if i < 3:
            print(f"\n⏳ Waiting 10 seconds before next event...")
            time.sleep(10)  # Wait between events
    except Exception as e:
        print(f"\n❌ Error submitting event {i}: {e}")

print(f"\n\n{'='*80}")
print("TEST COMPLETE")
print(f"{'='*80}")
print(
    "\n📧 Check your emails:"
)
print("\n1. physician@example.com should have received:")
print("   - 3 individual [HIGH] alerts")
print("\n2. safety@example.com should have received:")
print("   - 3 individual [HIGH] alerts")
print("   - 1 [THRESHOLD BREACH] alert (after 3rd event)")
print("\n3. CloudWatch Logs should show:")
print("   - [THRESHOLD CHECK] messages")
print("   - [THRESHOLD BREACH] message after 3rd event")
print(
    "\nTo view logs:"
)
print(
    "  aws logs tail /aws/bedrock-agentcore/runtimes/FAST_stack_StrandsAgent-gH7qltD9cn-DEFAULT --since 5m | grep THRESHOLD"
)
print()
