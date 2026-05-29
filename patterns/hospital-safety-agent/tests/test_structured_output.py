#!/usr/bin/env python3
"""
Test structured output classification.

This tests the new Pydantic-based classification which should:
1. Return type-safe event_type and severity (no more keyword matching!)
2. Automatically extract patient_id, location, and staff_involved
3. Generate a brief summary
"""

from pathlib import Path
from dotenv import load_dotenv
from test_hospital_safety import invoke_safety_agent, get_cognito_token

# Load credentials
env_path = Path(__file__).parent.parent.parent.parent / "infra-cdk" / ".env"
if env_path.exists():
    load_dotenv(env_path)

# Test event with clear entities to extract
test_event = """
Patient in room 401 (MRN-789012) received wrong dose of Metoprolol.
Nurse Sarah administered 50mg instead of the prescribed 25mg.
Patient's heart rate dropped to 48 bpm. Cardiology was consulted.
Error was discovered during medication reconciliation by Pharmacist Dr. Chen.
"""

print("=" * 80)
print("STRUCTURED OUTPUT CLASSIFICATION TEST")
print("=" * 80)
print("\nTest Event:")
print(test_event)
print("\n" + "=" * 80)
print("Expected Structured Output:")
print("  - event_type: 'medication_error' (type-safe, no keyword matching!)")
print("  - severity: 'high' or 'critical'")
print("  - patient_id: 'room 401' or 'MRN-789012' (automatically extracted)")
print("  - location: 'room 401' (automatically extracted)")
print("  - staff_involved: 'Nurse Sarah' or 'Dr. Chen' (automatically extracted)")
print("  - brief_summary: One-sentence summary")
print("=" * 80)

# Get JWT token and invoke
jwt_token = get_cognito_token()
print("\n📤 Submitting event...")

try:
    result = invoke_safety_agent(
        test_event, user_id="structured-output-test", jwt_token=jwt_token
    )
    print("\n✅ Event submitted successfully!")
    print("\n📋 Check CloudWatch Logs for structured classification:")
    print(
        "  aws logs tail /aws/bedrock-agentcore/runtimes/FAST_stack_StrandsAgent-gH7qltD9cn-DEFAULT --since 2m | grep ORCHESTRATOR"
    )
except Exception as e:
    print(f"\n❌ Error: {e}")

print("\n" + "=" * 80)
print("BENEFITS OF STRUCTURED OUTPUT:")
print("=" * 80)
print("✅ No more brittle keyword matching")
print("✅ Type-safe classification (guaranteed valid event types)")
print("✅ Automatic entity extraction (patient_id, location, staff)")
print("✅ Pydantic validation ensures correct data structure")
print("✅ IDE autocomplete and type hints")
print()
