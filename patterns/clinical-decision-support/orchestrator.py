# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Clinical Decision Support Agent

This agent provides real-time clinical decision support by:
1. Retrieving patient data from Epic FHIR (with user authorization)
2. Analyzing drug interactions, contraindications, and allergies
3. Providing safety recommendations and alternatives

Uses Epic 3LO (User Federation) flow for user-authorized access.
"""

import os
from typing import Dict, Any, List
from pydantic import BaseModel, Field
from strands import Agent, tool
from strands.models import BedrockModel
from bedrock_agentcore.runtime import BedrockAgentCoreApp

# Import Epic User Federation tools
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from gateway.tools.epic_fhir_user_federation import (
    get_patient_with_user_auth,
    get_medications_with_user_auth,
    get_allergies_with_user_auth,
    get_observations_with_user_auth
)

app = BedrockAgentCoreApp()


# ===== Pydantic Models =====

class DrugInteraction(BaseModel):
    """Drug interaction finding"""
    severity: str = Field(description="Severity: CRITICAL, MAJOR, MODERATE, MINOR")
    drug1: str = Field(description="First drug name")
    drug2: str = Field(description="Second drug name")
    interaction: str = Field(description="Description of the interaction")
    recommendation: str = Field(description="Clinical recommendation")


class ClinicalRecommendation(BaseModel):
    """Clinical decision support recommendation"""
    safety_level: str = Field(description="SAFE, CAUTION, or CONTRAINDICATED")
    summary: str = Field(description="Brief summary of findings")
    interactions: List[DrugInteraction] = Field(default_factory=list, description="Drug interactions found")
    contraindications: List[str] = Field(default_factory=list, description="Contraindications")
    allergies_flagged: List[str] = Field(default_factory=list, description="Allergy concerns")
    alternatives: List[str] = Field(default_factory=list, description="Alternative medications to consider")
    clinical_notes: str = Field(description="Additional clinical guidance")


# ===== Clinical Decision Support Agent =====

def create_clinical_decision_support_agent() -> Agent:
    """Create the clinical decision support agent with Epic 3LO integration"""

    model = BedrockModel(
        model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        temperature=0.1,  # Low temperature for clinical accuracy
        max_tokens=4000
    )

    agent = Agent(
        name="ClinicalDecisionSupportAgent",
        model=model,
        description="Clinical decision support agent that analyzes drug safety using patient FHIR data",
        instruction="""You are a clinical decision support agent that helps healthcare providers make safe medication decisions.

When analyzing a medication for a patient, you MUST:

1. **Retrieve Patient Data** (using Epic 3LO with user authorization):
   - Current medications
   - Allergies
   - Recent lab results (if relevant)
   - Patient demographics

2. **Analyze Drug Safety**:
   - Check for drug-drug interactions
   - Identify contraindications based on patient conditions
   - Flag allergy concerns
   - Consider lab values (e.g., kidney function for renally-cleared drugs)

3. **Provide Recommendations**:
   - Rate safety level: SAFE, CAUTION, or CONTRAINDICATED
   - List specific concerns with severity ratings
   - Suggest alternatives if contraindicated
   - Include clinical guidance

4. **Be Accurate and Conservative**:
   - If unsure, recommend consulting pharmacy or references
   - Always prioritize patient safety
   - Use evidence-based guidelines

You have access to Epic FHIR data through User Federation (3LO). The first time you access patient data, the user will need to authorize via Epic login.
""",
        tools=[
            get_patient_with_user_auth,
            get_medications_with_user_auth,
            get_allergies_with_user_auth,
            get_observations_with_user_auth
        ],
        response_model=ClinicalRecommendation
    )

    return agent


# ===== AgentCore Runtime Handler =====

@app.agent()
def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main handler for clinical decision support queries

    Expected input:
    {
        "patientId": "8MsEzCJO3BA3",
        "medication": "Metformin",
        "query": "Check if Metformin is safe for this patient"
    }
    """

    # Extract query parameters
    patient_id = event.get('patientId')
    medication = event.get('medication')
    query = event.get('query')

    if not patient_id:
        return {
            'status': 'error',
            'message': 'Missing required parameter: patientId'
        }

    # Build query for agent
    if not query:
        if medication:
            query = f"Analyze the safety of prescribing {medication} for patient {patient_id}. Check for drug interactions, contraindications, and allergy concerns."
        else:
            query = f"Provide clinical decision support for patient {patient_id}"

    # Create agent
    agent = create_clinical_decision_support_agent()

    # Run agent with structured output
    try:
        result = agent.run(query)

        return {
            'status': 'success',
            'patientId': patient_id,
            'medication': medication,
            'recommendation': result.model_dump() if hasattr(result, 'model_dump') else result
        }

    except Exception as e:
        # Check if this is an authorization error (first-time 3LO)
        error_str = str(e)
        if 'authorization' in error_str.lower() or 'auth' in error_str.lower():
            return {
                'status': 'authorization_required',
                'message': 'User authorization needed to access patient data',
                'patientId': patient_id,
                'error': error_str
            }

        return {
            'status': 'error',
            'message': f'Error analyzing medication safety: {str(e)}',
            'patientId': patient_id
        }


if __name__ == "__main__":
    # Local testing
    print("Clinical Decision Support Agent initialized")
    print("Tools available:")
    print("  - get_patient_with_user_auth")
    print("  - get_medications_with_user_auth")
    print("  - get_allergies_with_user_auth")
    print("  - get_observations_with_user_auth")
