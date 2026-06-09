# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Infection Control Specialist Agent

Analyzes healthcare-associated infections (HAIs), contamination events, and hygiene violations.
"""

import os
import boto3
from typing import Dict, Any, List, Literal, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
from strands import Agent, tool
from strands.models import BedrockModel
from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig
from bedrock_agentcore.memory.integrations.strands.session_manager import (
    AgentCoreMemorySessionManager,
)


class InfectionPatternResult(BaseModel):
    """Structured result from infection pattern analysis."""

    location: str
    infection_type: str
    days_analyzed: int
    event_count: int
    is_cluster: bool
    outbreak_risk: Literal["high", "medium", "low"]
    historical_events: List[dict]
    trend: Literal["increasing", "stable", "decreasing"]
    error: Optional[str] = Field(default=None, description="Error message if query failed")


class OutbreakRiskAssessment(BaseModel):
    """Structured assessment of infection outbreak risk."""

    risk_score: int = Field(ge=1, le=5, description="Risk score from 1-5")
    risk_level: Literal["high", "medium", "low"]
    infection_type: str
    affected_patients: int
    location: str
    containment_actions: List[str]
    requires_outbreak_response: bool


class InfectionControlTools:
    """
    Tools for infection control analysis.
    """

    def __init__(self, region: str = "us-east-1"):
        """Initialize with DynamoDB client for querying historical infection data."""
        self.dynamodb = boto3.resource("dynamodb", region_name=region)
        self.events_table = self.dynamodb.Table(
            os.environ.get("EVENTS_TABLE_NAME", "hospital-safety-events")
        )

    @tool
    def check_infection_patterns(
        self, location: str, infection_type: str, days: int = 30
    ) -> InfectionPatternResult:
        """
        Query historical infection events to detect patterns or clusters.

        Analyzes past infection events in the same location to identify
        potential outbreaks or recurring issues.

        Args:
            location: Hospital location (unit, ward, room)
            infection_type: Type of infection (CAUTI, CLABSI, SSI, pneumonia, C.diff, MRSA)
            days: Number of days to look back (default: 30)

        Returns:
            Structured historical infection data and trend analysis
        """
        try:
            # Calculate date range
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)

            # Query events table (simplified - in production would use GSI)
            response = self.events_table.scan(
                FilterExpression="event_type = :type AND #loc = :location AND #ts BETWEEN :start AND :end",
                ExpressionAttributeNames={"#loc": "location", "#ts": "timestamp"},
                ExpressionAttributeValues={
                    ":type": "infection_control",
                    ":location": location,
                    ":start": start_date.isoformat(),
                    ":end": end_date.isoformat(),
                },
            )

            events = response.get("Items", [])
            event_count = len(events)

            # Analyze trends
            is_cluster = event_count >= 3  # 3+ events in 30 days suggests cluster
            outbreak_risk = "high" if event_count >= 5 else "medium" if is_cluster else "low"

            return InfectionPatternResult(
                location=location,
                infection_type=infection_type,
                days_analyzed=days,
                event_count=event_count,
                is_cluster=is_cluster,
                outbreak_risk=outbreak_risk,
                historical_events=events[:5],  # Return up to 5 most recent
                trend="increasing" if event_count > 2 else "stable",
            )

        except Exception as e:
            return InfectionPatternResult(
                location=location,
                infection_type=infection_type,
                days_analyzed=days,
                event_count=0,
                is_cluster=False,
                outbreak_risk="low",
                historical_events=[],
                trend="stable",
                error=f"Failed to query infection patterns: {str(e)}",
            )

    @tool
    def assess_outbreak_risk(
        self, infection_type: str, affected_patients: int, location: str
    ) -> OutbreakRiskAssessment:
        """
        Calculate outbreak risk score based on infection characteristics.

        Assesses the risk of an infection outbreak based on infection type,
        number of affected patients, and location characteristics.

        Args:
            infection_type: Type of infection (CAUTI, CLABSI, SSI, pneumonia, C.diff, MRSA)
            affected_patients: Number of patients affected
            location: Hospital location (ICU, medical ward, surgical unit)

        Returns:
            Structured outbreak risk assessment with score and containment recommendations
        """
        # Define high-risk infections
        high_risk_infections = ["c.diff", "mrsa", "vre", "cre", "norovirus"]
        high_risk_locations = ["icu", "nicu", "burn unit", "transplant unit"]

        # Calculate base risk score (1-5)
        risk_score = 1

        # Infection type risk
        if infection_type.lower() in high_risk_infections:
            risk_score += 2
        else:
            risk_score += 1

        # Patient count risk
        if affected_patients >= 3:
            risk_score += 2
        elif affected_patients >= 2:
            risk_score += 1

        # Location risk
        if any(loc in location.lower() for loc in high_risk_locations):
            risk_score += 1

        risk_score = min(5, risk_score)  # Cap at 5

        # Determine risk level
        if risk_score >= 4:
            risk_level = "high"
            containment_actions = [
                "Immediately notify infection control team",
                "Initiate contact precautions",
                "Review hand hygiene compliance",
                "Enhanced environmental cleaning",
                "Cohort affected patients if possible",
                "Daily infection control rounds",
                "Notify department of health if required",
            ]
        elif risk_score == 3:
            risk_level = "medium"
            containment_actions = [
                "Notify infection control team",
                "Implement standard precautions",
                "Review cleaning protocols",
                "Monitor for additional cases",
                "Staff education on prevention",
            ]
        else:
            risk_level = "low"
            containment_actions = [
                "Document in infection control log",
                "Monitor situation",
                "Standard precautions sufficient",
            ]

        return OutbreakRiskAssessment(
            risk_score=risk_score,
            risk_level=risk_level,
            infection_type=infection_type,
            affected_patients=affected_patients,
            location=location,
            containment_actions=containment_actions,
            requires_outbreak_response=risk_score >= 4,
        )


def create_infection_agent(user_id: str, session_id: str) -> Agent:
    """
    Create the Infection Control Specialist Agent.

    This agent specializes in analyzing infection-related safety events:
    - Healthcare-associated infections (HAIs)
    - Contamination events
    - Hygiene protocol violations
    - Outbreak detection

    Args:
        user_id: User ID for memory tracking
        session_id: Session ID for conversation history

    Returns:
        Configured Infection Control Agent
    """
    system_prompt = """You are the Infection Control Specialist Agent.

Your expertise includes:
- Healthcare-associated infections (HAIs)
  - CAUTI (catheter-associated UTI)
  - CLABSI (central line-associated bloodstream infection)
  - SSI (surgical site infection)
  - VAP (ventilator-associated pneumonia)
- Contamination events
- Hand hygiene violations
- Environmental cleaning issues
- Outbreak investigation

When analyzing an infection control event:

1. Identify the infection type or contamination source
2. Determine patient impact:
   - Number of patients affected
   - Severity of infections
   - Preventability of event

3. Use check_infection_patterns to identify clusters
4. Use assess_outbreak_risk to calculate outbreak potential
5. Assess root causes:
   - Hand hygiene compliance
   - Environmental cleaning
   - Device maintenance
   - Protocol adherence

6. Provide specific containment and prevention recommendations

Focus on preventing spread and implementing evidence-based infection control practices.
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
    infection_tools = InfectionControlTools(
        region=os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
    )

    # Create agent with trace attributes for Langfuse observability
    agent = Agent(
        name="InfectionControl",
        system_prompt=system_prompt,
        tools=[
            infection_tools.check_infection_patterns,
            infection_tools.assess_outbreak_risk,
        ],
        model=bedrock_model,
        session_manager=session_manager,
        trace_attributes={
            "user.id": user_id,
            "session.id": session_id,
            "agent.type": "infection_specialist",
        },
    )

    return agent
