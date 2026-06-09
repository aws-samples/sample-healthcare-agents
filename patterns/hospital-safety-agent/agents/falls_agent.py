# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Patient Falls Specialist Agent

Analyzes patient fall events, injury assessment, and fall prevention protocols.
"""

import os
from typing import Dict, Any, List, Literal
from pydantic import BaseModel, Field
from strands import Agent, tool
from strands.models import BedrockModel
from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig
from bedrock_agentcore.memory.integrations.strands.session_manager import (
    AgentCoreMemorySessionManager,
)


class FallInjuryAssessment(BaseModel):
    """Structured assessment of fall-related injuries."""

    severity: Literal["critical", "severe", "moderate", "minor", "none"]
    severity_score: int = Field(ge=1, le=5, description="Severity score from 1-5")
    injury_location: str
    injury_description: str
    medical_response: List[str]
    requires_immediate_intervention: bool


class FallPreventionCompliance(BaseModel):
    """Structured assessment of fall prevention protocol compliance."""

    fall_risk_level: str
    compliance_level: Literal["excellent", "adequate", "partial", "inadequate"]
    compliance_score: float = Field(description="Compliance percentage")
    present_interventions: List[str]
    missing_interventions: List[str]
    recommendations: List[str]
    protocol_followed: bool


class FallsTools:
    """
    Tools for patient falls analysis.
    """

    @tool
    def assess_fall_injury(
        self, injury_description: str, injury_location: str
    ) -> FallInjuryAssessment:
        """
        Assess the severity of injuries resulting from a patient fall.

        Categorizes fall injuries and determines required medical response.

        Args:
            injury_description: Description of injuries sustained
            injury_location: Body location of injuries (head, hip, back, extremities, etc.)

        Returns:
            Structured injury severity assessment with medical response recommendations
        """
        # Keywords for severity classification
        critical_keywords = [
            "fracture",
            "head injury",
            "hip",
            "skull",
            "unconscious",
            "bleeding",
            "compound",
        ]
        severe_keywords = ["laceration", "sprain", "bruise", "contusion", "pain"]

        description_lower = injury_description.lower()
        location_lower = injury_location.lower()

        # Assess severity
        if any(keyword in description_lower for keyword in critical_keywords):
            severity = "critical"
            severity_score = 5
        elif any(keyword in description_lower for keyword in severe_keywords):
            severity = "moderate"
            severity_score = 3
        elif "no injury" in description_lower or "uninjured" in description_lower:
            severity = "none"
            severity_score = 1
        else:
            severity = "minor"
            severity_score = 2

        # High-risk injury locations
        if any(
            location in location_lower for location in ["head", "hip", "spine", "neck"]
        ):
            severity_score = min(5, severity_score + 1)
            if severity != "none":
                severity = "critical" if severity_score >= 4 else "moderate"

        # Medical response recommendations
        if severity_score >= 4:
            medical_response = [
                "Immediate physician assessment required",
                "Order imaging (X-ray/CT) as indicated",
                "Neuro checks if head injury suspected",
                "Complete fall assessment form",
                "Notify family",
                "Consider transfer to higher level of care",
            ]
        elif severity_score == 3:
            medical_response = [
                "Physician assessment within 1 hour",
                "Monitor vital signs",
                "Complete fall assessment form",
                "Consider imaging if indicated",
                "Document in medical record",
            ]
        elif severity_score == 2:
            medical_response = [
                "Nursing assessment",
                "Monitor for delayed symptoms",
                "Complete fall assessment form",
                "Document in medical record",
            ]
        else:
            medical_response = [
                "Observation",
                "Complete fall assessment form",
                "Document unwitnessed/witnessed status",
            ]

        return FallInjuryAssessment(
            severity=severity,
            severity_score=severity_score,
            injury_location=injury_location,
            injury_description=injury_description,
            medical_response=medical_response,
            requires_immediate_intervention=severity_score >= 4,
        )

    @tool
    def check_fall_prevention_protocol(
        self, fall_risk_level: str, preventions_in_place: str
    ) -> FallPreventionCompliance:
        """
        Verify if appropriate fall prevention measures were in place.

        Checks if interventions matched the patient's fall risk level according
        to evidence-based fall prevention protocols.

        Args:
            fall_risk_level: Patient's fall risk (low, moderate, high)
            preventions_in_place: Description of prevention measures that were in place

        Returns:
            Structured protocol compliance assessment with identified gaps
        """
        # Standard fall prevention interventions by risk level
        required_interventions = {
            "low": [
                "call light within reach",
                "bed in low position",
                "clear pathway to bathroom",
            ],
            "moderate": [
                "call light within reach",
                "bed in low position",
                "hourly rounding",
                "yellow fall risk band",
                "non-slip socks",
                "clear pathway",
            ],
            "high": [
                "call light within reach",
                "bed in low position",
                "bed alarm activated",
                "hourly rounding",
                "yellow fall risk band",
                "non-slip socks",
                "room close to nurses station",
                "toileting schedule",
                "consider bed/chair alarm",
            ],
        }

        risk_level = fall_risk_level.lower()
        preventions_lower = preventions_in_place.lower()

        # Get required interventions for risk level
        required = required_interventions.get(risk_level, required_interventions["low"])

        # Check which interventions were in place
        present_interventions = []
        missing_interventions = []

        for intervention in required:
            if any(word in preventions_lower for word in intervention.split()):
                present_interventions.append(intervention)
            else:
                missing_interventions.append(intervention)

        # Calculate compliance score
        compliance_score = (
            len(present_interventions) / len(required) * 100 if required else 100
        )

        # Determine compliance level
        if compliance_score >= 90:
            compliance_level = "excellent"
        elif compliance_score >= 75:
            compliance_level = "adequate"
        elif compliance_score >= 50:
            compliance_level = "partial"
        else:
            compliance_level = "inadequate"

        recommendations = []
        if missing_interventions:
            recommendations.append(
                f"Implement missing interventions: {', '.join(missing_interventions)}"
            )
        if compliance_level in ["partial", "inadequate"]:
            recommendations.extend(
                [
                    "Review fall prevention protocol with nursing staff",
                    "Provide additional staff education",
                    "Audit fall prevention compliance",
                ]
            )

        return FallPreventionCompliance(
            fall_risk_level=fall_risk_level,
            compliance_level=compliance_level,
            compliance_score=round(compliance_score, 1),
            present_interventions=present_interventions,
            missing_interventions=missing_interventions,
            recommendations=recommendations,
            protocol_followed=compliance_score >= 75,
        )


def create_falls_agent(user_id: str, session_id: str) -> Agent:
    """
    Create the Patient Falls Specialist Agent.

    This agent specializes in analyzing fall-related safety events:
    - Patient falls (from bed, chair, standing)
    - Injury assessment
    - Fall prevention protocol compliance
    - Environmental hazards

    Args:
        user_id: User ID for memory tracking
        session_id: Session ID for conversation history

    Returns:
        Configured Patient Falls Agent
    """
    system_prompt = """You are the Patient Falls Specialist Agent.

Your expertise includes:
- Patient fall events and circumstances
- Fall-related injury assessment
- Fall risk assessment (Morse Fall Scale, STRATIFY)
- Fall prevention protocols and interventions
- Environmental safety

When analyzing a patient fall event:

1. Gather fall circumstances:
   - Location of fall (bed, bathroom, hallway)
   - Witnessed vs unwitnessed
   - Activity at time of fall (transferring, toileting, ambulating)
   - Time of day

2. Assess injuries using assess_fall_injury tool:
   - Head/neck injuries (highest priority)
   - Hip/pelvic injuries
   - Extremity injuries
   - No visible injury (but monitor)

3. Review fall prevention using check_fall_prevention_protocol:
   - Patient's fall risk level (low/moderate/high)
   - Interventions that were in place
   - Identify gaps in prevention

4. Identify contributing factors:
   - Patient factors (weakness, confusion, medications)
   - Environmental factors (lighting, wet floors, clutter)
   - System factors (staffing, equipment, protocols)

5. Provide recommendations:
   - Immediate medical response
   - Additional prevention measures
   - Environmental modifications
   - Staff education needs

Focus on preventing future falls and ensuring appropriate injury response.
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
    falls_tools = FallsTools()

    # Create agent with trace attributes for Langfuse observability
    agent = Agent(
        name="PatientFalls",
        system_prompt=system_prompt,
        tools=[falls_tools.assess_fall_injury, falls_tools.check_fall_prevention_protocol],
        model=bedrock_model,
        session_manager=session_manager,
        trace_attributes={
            "user.id": user_id,
            "session.id": session_id,
            "agent.type": "falls_specialist",
        },
    )

    return agent
