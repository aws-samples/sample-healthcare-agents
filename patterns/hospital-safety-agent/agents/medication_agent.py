# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Medication Safety Specialist Agent

Analyzes medication errors, drug interactions, and dosing issues.
"""

import os
import requests
from typing import Dict, Any, List, Literal, Optional
from pydantic import BaseModel, Field
from strands import Agent, tool
from strands.models import BedrockModel
from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig
from bedrock_agentcore.memory.integrations.strands.session_manager import (
    AgentCoreMemorySessionManager,
)


class DrugDatabaseResult(BaseModel):
    """Structured result from FDA drug database query."""

    drug_name: str
    found: bool
    warnings: List[str] = Field(default_factory=list)
    indications: List[str] = Field(default_factory=list)
    dosage: List[str] = Field(default_factory=list)
    error: Optional[str] = Field(default=None, description="Error message if query failed")
    message: Optional[str] = Field(default=None, description="Info message if drug not found")


class MedicationSeverityAssessment(BaseModel):
    """Structured assessment of medication error severity."""

    severity_score: int = Field(ge=1, le=5, description="Severity score from 1-5")
    severity_level: Literal["none", "minor", "moderate", "severe", "critical"]
    error_type: Literal["wrong_drug", "wrong_dose", "wrong_patient", "wrong_time", "wrong_route"]
    recommendations: List[str]
    requires_immediate_action: bool


class MedicationTools:
    """
    Tools for medication safety analysis.
    """

    @tool
    def check_drug_database(self, drug_name: str) -> DrugDatabaseResult:
        """
        Query FDA drug database for medication information.

        Uses FDA's OpenFDA API to retrieve drug details, warnings, and interactions.

        Args:
            drug_name: Name of the medication to look up

        Returns:
            Structured drug information including warnings, interactions, and proper dosing
        """
        try:
            # Query FDA OpenFDA API
            url = f"https://api.fda.gov/drug/label.json"
            params = {"search": f'openfda.brand_name:"{drug_name}"', "limit": 1}

            response = requests.get(url, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                if data.get("results"):
                    result = data["results"][0]
                    return DrugDatabaseResult(
                        drug_name=drug_name,
                        found=True,
                        warnings=result.get("warnings", ["No warnings available"]),
                        indications=result.get(
                            "indications_and_usage", ["No indication info"]
                        ),
                        dosage=result.get(
                            "dosage_and_administration", ["No dosage info"]
                        ),
                    )

            return DrugDatabaseResult(
                drug_name=drug_name,
                found=False,
                message="Drug not found in FDA database",
            )

        except Exception as e:
            return DrugDatabaseResult(
                drug_name=drug_name,
                found=False,
                error=f"Failed to query drug database: {str(e)}",
            )

    @tool
    def assess_medication_severity(
        self, error_type: str, patient_impact: str
    ) -> MedicationSeverityAssessment:
        """
        Assess the severity of a medication error.

        Evaluates medication errors on a scale of 1-5 based on error type
        and actual/potential patient impact.

        Args:
            error_type: Type of error (wrong_drug, wrong_dose, wrong_patient, wrong_time, wrong_route)
            patient_impact: Patient impact (none, minor, moderate, severe, critical)

        Returns:
            Structured severity assessment with score 1-5 and recommended actions
        """
        severity_map = {
            "none": 1,
            "minor": 2,
            "moderate": 3,
            "severe": 4,
            "critical": 5,
        }

        severity_score = severity_map.get(patient_impact.lower(), 3)

        # Adjust based on error type
        high_risk_errors = ["wrong_patient", "wrong_drug", "wrong_route"]
        if error_type.lower() in high_risk_errors:
            severity_score = min(5, severity_score + 1)

        recommendations = []
        if severity_score >= 4:
            recommendations.extend(
                [
                    "Immediate patient assessment required",
                    "Notify attending physician immediately",
                    "Complete incident report within 24 hours",
                    "Initiate root cause analysis",
                ]
            )
        elif severity_score == 3:
            recommendations.extend(
                [
                    "Monitor patient closely",
                    "Complete incident report within 48 hours",
                    "Review with pharmacy team",
                ]
            )
        else:
            recommendations.extend(
                [
                    "Document in patient record",
                    "Complete incident report",
                    "Consider process improvement",
                ]
            )

        return MedicationSeverityAssessment(
            severity_score=severity_score,
            severity_level=patient_impact,
            error_type=error_type,
            recommendations=recommendations,
            requires_immediate_action=severity_score >= 4,
        )


def create_medication_agent(user_id: str, session_id: str) -> Agent:
    """
    Create the Medication Safety Specialist Agent.

    This agent specializes in analyzing medication-related safety events:
    - Medication errors (wrong drug, dose, patient, route)
    - Drug interactions
    - Adverse drug reactions
    - Dosing issues

    Args:
        user_id: User ID for memory tracking
        session_id: Session ID for conversation history

    Returns:
        Configured Medication Safety Agent
    """
    system_prompt = """You are the Medication Safety Specialist Agent.

Your expertise includes:
- Medication errors (administration, prescribing, dispensing)
- Drug interactions and contraindications
- Adverse drug reactions
- Dosing errors and calculations
- High-alert medications

When analyzing a medication safety event:

1. Identify the specific medication(s) involved
2. Use check_drug_database to get official FDA information
3. Determine the type of error:
   - Wrong drug
   - Wrong dose
   - Wrong patient
   - Wrong time
   - Wrong route
   - Drug interaction

4. Assess patient impact:
   - No harm (error caught before reaching patient)
   - Minor (no treatment needed)
   - Moderate (required intervention)
   - Severe (caused significant harm)
   - Critical (life-threatening)

5. Use assess_medication_severity to calculate risk score
6. Provide specific recommendations

Be thorough, evidence-based, and focused on patient safety.
"""

    # Get model ID from environment variable (configured in CDK)
    model_id = os.environ.get("MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")
    bedrock_model = BedrockModel(model_id=model_id, temperature=0.1)

    # Setup memory
    memory_id = os.environ.get("MEMORY_ID")
    if memory_id:
        agentcore_memory_config = AgentCoreMemoryConfig(
            memory_id=memory_id, session_id=session_id, actor_id=user_id
        )
        session_manager = AgentCoreMemorySessionManager(
            agentcore_memory_config=agentcore_memory_config,
            region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
        )
    else:
        session_manager = None

    # Create tools
    med_tools = MedicationTools()

    # Create agent with trace attributes for Langfuse observability
    agent = Agent(
        name="MedicationSafety",
        system_prompt=system_prompt,
        tools=[med_tools.check_drug_database, med_tools.assess_medication_severity],
        model=bedrock_model,
        session_manager=session_manager,
        trace_attributes={
            "user.id": user_id,
            "session.id": session_id,
            "agent.type": "medication_specialist",
        },
    )

    return agent
