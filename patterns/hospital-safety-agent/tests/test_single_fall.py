#!/usr/bin/env python3
"""Quick test for fall event classification"""

import os
import json
from pathlib import Path
from dotenv import load_dotenv
from test_hospital_safety import invoke_safety_agent, get_cognito_token

# Load credentials
env_path = Path(__file__).parent.parent.parent.parent / "infra-cdk" / ".env"
if env_path.exists():
    load_dotenv(env_path)

# Test fall event
fall_event = """
86-year-old patient fell while attempting to reach the bathroom unassisted.
Found on floor by nursing staff. Patient reports hip pain. Call bell was
within reach but patient did not use it. Fall risk assessment was marked as high.
""".strip()

print("Testing fall event classification...")
print(f"Event: {fall_event}\n")

# Get token and invoke
jwt_token = get_cognito_token()
result = invoke_safety_agent(fall_event, user_id="test-fall", jwt_token=jwt_token)

print(f"\n✅ Test completed!")
print(f"Check your email for the alert - it should say 'Type: patient_fall' (not medication_error)")
