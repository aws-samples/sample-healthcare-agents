#!/usr/bin/env python3
"""Quick test for infection event classification"""

import os
import json
from pathlib import Path
from dotenv import load_dotenv
from test_hospital_safety import invoke_safety_agent, get_cognito_token

# Load credentials
env_path = Path(__file__).parent.parent.parent.parent / "infra-cdk" / ".env"
if env_path.exists():
    load_dotenv(env_path)

# Test infection event
infection_event = """
Patient in ICU bed 5 developed CAUTI on day 4 of catheterization. Temperature
spiked to 101.5F. Urine culture positive for E. coli. Two other patients in
the ICU also have catheter-associated infections this week.
""".strip()

print("Testing infection control event classification...")
print(f"Event: {infection_event}\n")

# Get token and invoke
jwt_token = get_cognito_token()
result = invoke_safety_agent(infection_event, user_id="test-infection", jwt_token=jwt_token)

print(f"\n✅ Test completed!")
print(f"Check your email for the alert - it should say 'Type: infection_control'")
