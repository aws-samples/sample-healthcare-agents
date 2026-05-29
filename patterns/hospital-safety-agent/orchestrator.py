# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Hospital Safety Event Orchestrator Agent

This agent receives safety events, classifies them, and routes to specialist agents.
"""

import os
import json
import boto3
from datetime import datetime
from typing import Dict, Any, Optional, Literal
from pydantic import BaseModel, Field
from strands import Agent, tool
from strands.models import BedrockModel
from strands.telemetry import StrandsTelemetry
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig
from bedrock_agentcore.memory.integrations.strands.session_manager import (
    AgentCoreMemorySessionManager,
)

# Import specialist agents
from agents.medication_agent import create_medication_agent
from agents.infection_agent import create_infection_agent
from agents.falls_agent import create_falls_agent

app = BedrockAgentCoreApp()

# Initialize Langfuse observability via OpenTelemetry
# This must be done before creating any agents
_telemetry_initialized = False

def initialize_telemetry():
    """Initialize Strands telemetry with Langfuse (OTEL) configuration.

    HIPAA Compliance: Langfuse credentials are fetched from AWS Secrets Manager
    at runtime instead of being stored in environment variables.
    """
    global _telemetry_initialized
    if not _telemetry_initialized:
        # Check if Langfuse secret ARN is provided
        secret_arn = os.environ.get("LANGFUSE_SECRET_ARN")
        otel_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")

        if secret_arn and otel_endpoint:
            try:
                # Fetch Langfuse credentials from Secrets Manager
                import json
                import base64

                secretsmanager = boto3.client("secretsmanager")
                response = secretsmanager.get_secret_value(SecretId=secret_arn)
                secret_data = json.loads(response["SecretString"])

                public_key = secret_data.get("publicKey", "")
                secret_key = secret_data.get("secretKey", "")

                if public_key and secret_key:
                    # Construct OTEL auth header from credentials
                    auth_token = base64.b64encode(
                        f"{public_key}:{secret_key}".encode()
                    ).decode()
                    auth_header = f"Authorization=Basic {auth_token}"

                    # Set auth header in environment for OTEL exporter
                    os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = auth_header

                    # Initialize telemetry
                    strands_telemetry = StrandsTelemetry()
                    strands_telemetry.setup_otlp_exporter()
                    _telemetry_initialized = True
                    print(
                        "[TELEMETRY] Langfuse observability initialized from Secrets Manager"
                    )
                else:
                    print(
                        "[TELEMETRY] Langfuse credentials empty in Secrets Manager - skipping"
                    )
            except Exception as e:
                print(f"[TELEMETRY] Failed to fetch Langfuse credentials: {e}")
                print("[TELEMETRY] Continuing without observability")
        else:
            print("[TELEMETRY] Langfuse not configured - skipping observability")


# ===== Pydantic Models for Structured Output =====


class SafetyEventClassification(BaseModel):
    """
    Structured classification of a hospital safety event.

    This schema enforces type-safe classification and automatic entity extraction
    from unstructured safety event text according to comprehensive patient safety
    event report standards.
    """

    event_type: Literal[
        "medication_error", "infection_control", "patient_fall", "device_malfunction"
    ] = Field(
        description="Type of safety event. medication_error: wrong drug/dose/patient/route/time. infection_control: HAIs, contamination, hygiene violations. patient_fall: patient falls from bed/chair/standing. device_malfunction: medical equipment failures."
    )

    event_classification: Literal["near_miss", "unsafe_condition", "adverse_event"] = Field(
        description="Event classification. near_miss: could have caused harm but didn't (by chance or intervention). unsafe_condition: circumstance that increases probability of harm. adverse_event: harm occurred from treatment/diagnosis."
    )

    severity: Literal["low", "medium", "high", "critical"] = Field(
        description="Severity level. low: minor issue, no harm. medium: potential harm, requires review. high: caused harm or high risk, immediate action needed. critical: severe harm, life-threatening, emergency response."
    )

    event_date: Optional[str] = Field(
        default=None,
        description="Date and time when the safety event actually occurred. Extract from incident description. Examples: '2026-01-29 03:15 AM', 'January 29, 2026 at 3:15am', '01/29/2026 03:15'. Extract as written.",
    )

    date_reported: str = Field(
        description="Current date and time when this event is being reported. Use current timestamp in ISO format.",
        default_factory=lambda: datetime.utcnow().isoformat(),
    )

    patient_id: Optional[str] = Field(
        default=None,
        description="Patient identifier if mentioned (MRN, medical record number, room number like 'room 302', bed number like 'ICU bed 5', or patient name). Extract exactly as written.",
    )

    patient_mrn: Optional[str] = Field(
        default=None,
        description="Patient Medical Record Number (MRN) if explicitly mentioned. Examples: 'MRN-12345', 'Medical Record #67890'. Extract numeric or alphanumeric identifier only.",
    )

    location: Optional[str] = Field(
        default=None,
        description="Location where incident occurred (specific room number, unit name, floor). Examples: 'room 401', 'ICU bed 5', '3rd floor hallway'.",
    )

    clinical_state: Optional[str] = Field(
        default=None,
        description="Patient's clinical condition at time of event. Examples: 'post-operative day 2', 'confused and agitated', 'stable vital signs'. Extract verbatim if mentioned.",
    )

    staff_involved: Optional[str] = Field(
        default=None,
        description="Names or roles of staff involved in the incident if mentioned (nurses, physicians, technicians).",
    )

    equipment_involved: Optional[list[Dict[str, str]]] = Field(
        default=None,
        description="Medical equipment, devices, or medications involved. Extract as list of dicts with 'type' and 'description'. Examples: [{'type': 'IV pump', 'description': 'Model XYZ-100'}, {'type': 'medication', 'description': 'Heparin 5000 units'}]",
    )

    harm_level: Optional[Literal["none", "emotional_distress", "additional_treatment", "temporary", "permanent", "severe_permanent", "death"]] = Field(
        default=None,
        description="Level of patient harm. none: no harm occurred. emotional_distress: mild transient anxiety/pain/discomfort. additional_treatment: increased intervention or length of stay. temporary: bodily/psychological injury, not permanent. permanent: lifelong injury. severe_permanent: severe lifelong injury affecting quality of life. death: patient died.",
    )

    immediate_actions: Optional[list[str]] = Field(
        default=None,
        description="Immediate actions taken to protect patient after event discovery. Examples: ['Called rapid response team', 'Applied pressure to wound', 'Administered antidote']. Extract as list.",
    )

    root_causes: Optional[list[str]] = Field(
        default=None,
        description="Contributing factors or root causes mentioned. Examples: ['Communication breakdown', 'Staff fatigue', 'Equipment malfunction', 'Training gap']. Extract as list.",
    )

    timeline_details: Optional[Dict[str, str]] = Field(
        default=None,
        description="Chronological timeline of event if specific times mentioned. Extract as dict with keys like 'ordered', 'administered', 'discovered', 'responded'. Examples: {'ordered': '10:00', 'given': '10:15', 'error_discovered': '10:30'}",
    )

    patient_age_category: Optional[Literal["neonate", "infant", "child", "adolescent", "adult", "mature_adult", "older_adult", "aged_adult"]] = Field(
        default=None,
        description="Patient age category. neonate: 0-28 days. infant: >28 days to <1 year. child: 1-12 years. adolescent: 13-17 years. adult: 18-64 years. mature_adult: 65-74 years. older_adult: 74-84 years. aged_adult: 85+ years.",
    )

    rescue_attempted: Optional[Literal["yes", "no", "unknown"]] = Field(
        default=None,
        description="Was intervention attempted to rescue patient (prevent, minimize, or reverse harm)? yes/no/unknown.",
    )

    patient_family_notified: Optional[Literal["yes", "no", "unknown"]] = Field(
        default=None,
        description="After discovery, was patient/family/guardian notified of the incident? yes/no/unknown.",
    )

    increased_length_of_stay: Optional[Literal["yes", "no", "unknown"]] = Field(
        default=None,
        description="Did or will the incident result in increased length of stay? yes/no/unknown.",
    )

    time_harm_assessed: Optional[Literal["within_24h", "24h_to_3days", "3plus_days", "unknown"]] = Field(
        default=None,
        description="When after discovery was harm assessed? within_24h: within 24 hours. 24h_to_3days: after 24h but before 3 days. 3plus_days: 3 days or later. unknown.",
    )

    requires_immediate_action: bool = Field(
        description="True if severity is high or critical and requires immediate clinical response (not just documentation)."
    )

    brief_summary: str = Field(
        description="One-sentence summary of what happened (max 100 characters).",
        max_length=100,
    )


class SafetyEventClassifier:
    """
    Tools for classifying and routing safety events.
    """

    def __init__(self, region: str = "us-east-1"):
        """
        Initialize the classifier with AWS clients.

        Args:
            region: AWS region for DynamoDB and other services
        """
        self.dynamodb = boto3.resource("dynamodb", region_name=region)
        self.events_table = self.dynamodb.Table(
            os.environ.get("EVENTS_TABLE_NAME", "hospital-safety-events")
        )
        self.analysis_table = self.dynamodb.Table(
            os.environ.get("ANALYSIS_TABLE_NAME", "hospital-safety-analysis")
        )

        # Initialize email configurations if they don't exist
        self._ensure_email_configs()

    @tool
    def classify_safety_event(self, event_text: str) -> Dict[str, Any]:
        """
        Classify a hospital safety event and extract key entities.

        This tool analyzes unstructured safety event text to determine:
        - Event type (medication_error, infection_control, patient_fall, device_malfunction)
        - Severity level (low, medium, high, critical)
        - Key entities (patient_id, location, date/time, staff involved)

        Args:
            event_text: Raw text describing the safety event

        Returns:
            Dictionary containing classification results:
            {
                "event_type": str,
                "severity": str,
                "entities": dict,
                "requires_immediate_action": bool
            }
        """
        # This would typically use the LLM to classify
        # For now, returning structured format that the orchestrator will populate
        return {
            "event_type": "unknown",  # Will be determined by orchestrator
            "severity": "unknown",
            "entities": {},
            "requires_immediate_action": False,
        }

    @tool
    def store_event(
        self,
        event_id: str,
        event_type: str,
        severity: str,
        raw_text: str,
        classification: Dict[str, Any],
        patient_id: Optional[str] = None,
        patient_mrn: Optional[str] = None,
        location: Optional[str] = None,
        clinical_state: Optional[str] = None,
        staff_involved: Optional[str] = None,
        equipment_involved: Optional[list] = None,
        harm_level: Optional[str] = None,
        immediate_actions: Optional[list] = None,
        root_causes: Optional[list] = None,
        timeline_details: Optional[dict] = None,
        event_date: Optional[str] = None,
        date_reported: Optional[str] = None,
        event_classification: Optional[str] = None,
        patient_age_category: Optional[str] = None,
        rescue_attempted: Optional[str] = None,
        patient_family_notified: Optional[str] = None,
        increased_length_of_stay: Optional[str] = None,
        time_harm_assessed: Optional[str] = None,
    ) -> Dict[str, str]:
        """
        Store a classified safety event in DynamoDB with comprehensive report fields.

        Args:
            event_id: Unique identifier for the event
            event_type: Type of safety event (medication_error, infection_control, etc.)
            severity: Severity level (low, medium, high, critical)
            raw_text: Original event description
            classification: Full classification details
            patient_id: Extracted patient identifier (optional)
            patient_mrn: Patient Medical Record Number (optional)
            location: Extracted location (optional)
            clinical_state: Patient's clinical condition (optional)
            staff_involved: Extracted staff information (optional)
            equipment_involved: List of equipment/devices (optional)
            harm_level: Level of patient harm (optional)
            immediate_actions: List of immediate actions taken (optional)
            root_causes: List of contributing factors (optional)
            timeline_details: Chronological timeline dict (optional)
            event_date: Date/time when the event occurred (optional)
            date_reported: Date/time when event is being reported (optional)

        Returns:
            Confirmation message with event ID
        """
        from datetime import datetime

        try:
            item = {
                "event_id": event_id,
                "timestamp": datetime.utcnow().isoformat(),
                "event_type": event_type,
                "severity": severity,
                "description": raw_text,  # Store as 'description' for consistency with schema
                "classification": classification,
                "status": "pending_analysis",
            }

            # Add extracted entities if available
            if patient_id:
                item["patient_id"] = patient_id
            if patient_mrn:
                item["patient_mrn"] = patient_mrn
            if location:
                item["location"] = location
            if clinical_state:
                item["clinical_state"] = clinical_state
            if staff_involved:
                item["staff_involved"] = staff_involved
            if equipment_involved:
                item["equipment_involved"] = json.dumps(equipment_involved)
            if harm_level:
                item["harm_level"] = harm_level
            if immediate_actions:
                item["immediate_actions"] = json.dumps(immediate_actions)
            if root_causes:
                item["root_causes"] = json.dumps(root_causes)
            if timeline_details:
                item["timeline_details"] = json.dumps(timeline_details)
            if event_date:
                item["event_date"] = event_date
            if date_reported:
                item["date_reported"] = date_reported
            if event_classification:
                item["event_classification"] = event_classification
            if patient_age_category:
                item["patient_age_category"] = patient_age_category
            if rescue_attempted:
                item["rescue_attempted"] = rescue_attempted
            if patient_family_notified:
                item["patient_family_notified"] = patient_family_notified
            if increased_length_of_stay:
                item["increased_length_of_stay"] = increased_length_of_stay
            if time_harm_assessed:
                item["time_harm_assessed"] = time_harm_assessed

            self.events_table.put_item(Item=item)

            return {
                "status": "success",
                "message": f"Event {event_id} stored successfully",
            }
        except Exception as e:
            return {"status": "error", "message": f"Failed to store event: {str(e)}"}

    @tool
    def store_analysis(
        self,
        event_id: str,
        agent_name: str,
        analysis: Dict[str, Any],
        severity_score: int,
        recommendations: list,
    ) -> Dict[str, str]:
        """
        Store specialist agent analysis results in DynamoDB.

        Args:
            event_id: Event being analyzed
            agent_name: Name of the specialist agent (medication, infection, falls)
            analysis: Full analysis results from specialist
            severity_score: Numerical severity (1-5)
            recommendations: List of recommended actions

        Returns:
            Confirmation message
        """
        from datetime import datetime
        import uuid

        try:
            analysis_id = f"anl_{uuid.uuid4().hex[:12]}"
            self.analysis_table.put_item(
                Item={
                    "analysis_id": analysis_id,
                    "event_id": event_id,
                    "agent": agent_name,
                    "timestamp": datetime.utcnow().isoformat(),
                    "severity_score": severity_score,
                    "analysis": analysis,
                    "recommendations": recommendations,
                }
            )
            return {
                "status": "success",
                "message": f"Analysis {analysis_id} stored successfully",
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to store analysis: {str(e)}",
            }

    def _ensure_email_configs(self):
        """
        Initialize default email configurations in DynamoDB using single-table design.
        Configs are stored with event_id pattern: CONFIG#EMAIL#<type>
        """
        from datetime import datetime

        configs = {
            "physician": {
                "email": os.environ.get("PHYSICIAN_EMAIL", "physician@example.com"),
                "alert_types": ["high", "critical"],
                "description": "On-call physicians for immediate patient safety alerts",
            },
            "safety_officer": {
                "email": os.environ.get("SAFETY_OFFICER_EMAIL", "safety@example.com"),
                "alert_types": ["threshold_breach", "pattern_alert", "high", "critical"],
                "description": "Safety officers for threshold breaches and pattern alerts",
            },
        }

        for recipient_type, config in configs.items():
            try:
                # Check if config exists
                response = self.events_table.get_item(
                    Key={
                        "event_id": f"CONFIG#EMAIL#{recipient_type}",
                        "timestamp": "config",
                    }
                )

                if "Item" not in response:
                    # Create config if it doesn't exist
                    self.events_table.put_item(
                        Item={
                            "event_id": f"CONFIG#EMAIL#{recipient_type}",
                            "timestamp": "config",
                            "config_type": "email_recipient",
                            "recipient_type": recipient_type,
                            "email": config["email"],
                            "alert_types": config["alert_types"],
                            "description": config["description"],
                            "created_at": datetime.utcnow().isoformat(),
                            "enabled": True,
                        }
                    )
                    print(
                        f"[CONFIG] Created email config for {recipient_type}: {config['email']}"
                    )
            except Exception as e:
                print(f"[CONFIG ERROR] Failed to initialize {recipient_type} config: {e}")

    def _get_email_recipients(self, alert_type: str) -> list:
        """
        Get email recipients for a specific alert type.

        Args:
            alert_type: Type of alert (high, critical, threshold_breach, pattern_alert)

        Returns:
            List of email addresses
        """
        recipients = []
        try:
            # Query for all email configs
            for recipient_type in ["physician", "safety_officer"]:
                response = self.events_table.get_item(
                    Key={
                        "event_id": f"CONFIG#EMAIL#{recipient_type}",
                        "timestamp": "config",
                    }
                )

                if "Item" in response:
                    config = response["Item"]
                    if (
                        config.get("enabled", True)
                        and alert_type in config.get("alert_types", [])
                    ):
                        recipients.append(config["email"])

        except Exception as e:
            print(f"[CONFIG ERROR] Failed to retrieve email recipients: {e}")

        return recipients

    @tool
    def check_event_threshold(
        self, event_type: str, threshold: int = 3, timeframe_days: int = 30
    ) -> Dict[str, Any]:
        """
        Check if event type has exceeded threshold within timeframe.

        Queries historical events to detect if a specific event type (medication_error,
        patient_fall, infection_control) has occurred too frequently, suggesting a
        systemic issue requiring safety officer attention.

        Args:
            event_type: Type of safety event to check
            threshold: Number of events that triggers alert (default: 3)
            timeframe_days: Number of days to look back (default: 30)

        Returns:
            Dictionary with:
            - event_count: Number of events in timeframe
            - threshold_breached: Boolean indicating if threshold exceeded
            - breach_level: "none", "warning", or "critical"
            - recent_events: List of recent event IDs
        """
        from datetime import datetime, timedelta

        try:
            # Calculate date range
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=timeframe_days)

            # Query using event-type-index GSI
            response = self.events_table.query(
                IndexName="event-type-index",
                KeyConditionExpression="event_type = :type AND #ts >= :start",
                ExpressionAttributeNames={"#ts": "timestamp"},
                ExpressionAttributeValues={
                    ":type": event_type,
                    ":start": start_date.isoformat(),
                },
            )

            events = response.get("Items", [])
            event_count = len(events)

            # Determine breach level
            threshold_breached = event_count >= threshold
            if event_count >= threshold * 2:
                breach_level = "critical"
            elif threshold_breached:
                breach_level = "warning"
            else:
                breach_level = "none"

            # Get recent event IDs
            recent_events = [
                {
                    "event_id": e["event_id"],
                    "timestamp": e["timestamp"],
                    "severity": e.get("severity", "unknown"),
                }
                for e in sorted(events, key=lambda x: x["timestamp"], reverse=True)[
                    :10
                ]
            ]

            return {
                "event_type": event_type,
                "event_count": event_count,
                "threshold": threshold,
                "timeframe_days": timeframe_days,
                "threshold_breached": threshold_breached,
                "breach_level": breach_level,
                "recent_events": recent_events,
                "message": f"Found {event_count} {event_type} events in last {timeframe_days} days (threshold: {threshold})",
            }

        except Exception as e:
            return {
                "event_type": event_type,
                "threshold_breached": False,
                "error": f"Failed to check threshold: {str(e)}",
            }


def create_orchestrator_agent(
    user_id: str, session_id: str, event_text: str
) -> tuple[Agent, SafetyEventClassifier]:
    """
    Create the orchestrator agent for safety event processing.

    This agent coordinates the entire safety event workflow:
    1. Receives and classifies events
    2. Routes to appropriate specialist agents
    3. Coordinates storage and alerting

    Args:
        user_id: ID of the user/system invoking the agent
        session_id: Session ID for memory tracking
        event_text: The safety event to process

    Returns:
        Tuple of (Agent, SafetyEventClassifier tools)
    """
    system_prompt = f"""You are the Hospital Safety Event Orchestrator Agent.

Your role is to:
1. Analyze the safety event and classify it into one of these categories:
   - medication_error: Drug administration errors, wrong dosage, drug interactions
   - infection_control: HAIs, contamination, hygiene violations
   - patient_fall: Falls, slip incidents, injury from falling
   - device_malfunction: Medical equipment failures

2. Determine severity level:
   - low: Minor issue, no patient harm
   - medium: Potential for harm, requires review
   - high: Caused harm or high risk, immediate action needed
   - critical: Severe harm, life-threatening, emergency response

3. Extract key information:
   - Patient ID (if mentioned)
   - Location (room, unit, floor)
   - Date/time of incident
   - Staff involved
   - Witnesses

4. Route to the appropriate specialist agent for detailed analysis.

The safety event to analyze is:
{event_text}

First, classify this event and then route it to the specialist for detailed analysis.
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

    # Create classifier tools
    classifier = SafetyEventClassifier(
        region=os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
    )

    # Create orchestrator agent with classification tools and trace attributes
    agent = Agent(
        name="SafetyOrchestrator",
        system_prompt=system_prompt,
        tools=[
            classifier.classify_safety_event,
            classifier.store_event,
            classifier.store_analysis,
        ],
        model=bedrock_model,
        session_manager=session_manager,
        trace_attributes={
            "user.id": user_id,
            "session.id": session_id,
            "agent.type": "orchestrator",
            # NOTE: event.text removed for HIPAA compliance - do not log PHI
        },
    )

    return agent, classifier


async def process_safety_event(
    event_text: str, user_id: str = "system", session_id: str = "default"
) -> Dict[str, Any]:
    """
    Process a safety event through the orchestrator and specialist agents.

    Workflow:
    1. Orchestrator classifies the event
    2. Routes to appropriate specialist agent
    3. Specialist analyzes and provides recommendations
    4. Results stored in DynamoDB
    5. Alerts sent if severity is high/critical

    Args:
        event_text: Raw safety event description
        user_id: User ID for tracking
        session_id: Session ID for memory

    Returns:
        Complete analysis results from orchestrator and specialist
    """
    import uuid

    event_id = f"evt_{uuid.uuid4().hex[:12]}"

    # Create orchestrator
    orchestrator, classifier = create_orchestrator_agent(
        user_id, session_id, event_text
    )

    # Step 1: Get structured classification from orchestrator
    print(f"[ORCHESTRATOR] Processing event {event_id}")

    # Use structured output for type-safe, validated classification (new pattern)
    result = await orchestrator.invoke_async(
        f"""Analyze and classify this hospital safety event. Extract all available information.

Safety Event:
{event_text}
""",
        structured_output_model=SafetyEventClassification,
    )

    # Extract structured output from AgentResult
    classification = result.structured_output

    # Extract type-safe fields from structured output
    event_type = classification.event_type
    severity = classification.severity
    patient_id = classification.patient_id
    location = classification.location
    staff_involved = classification.staff_involved

    # HIPAA Compliance: Log only event_id, type, and severity - NO patient data
    print(
        f"[ORCHESTRATOR] Classified: event_id={event_id}, type={event_type}, severity={severity}"
    )

    # Store the classified event with extracted entities
    classifier.store_event(
        event_id=event_id,
        event_type=event_type,
        severity=severity,
        raw_text=event_text,
        classification=classification.dict(),  # Store full structured classification
        patient_id=patient_id,
        patient_mrn=classification.patient_mrn,
        location=location,
        clinical_state=classification.clinical_state,
        staff_involved=staff_involved,
        equipment_involved=classification.equipment_involved,
        harm_level=classification.harm_level,
        immediate_actions=classification.immediate_actions,
        root_causes=classification.root_causes,
        timeline_details=classification.timeline_details,
        event_date=classification.event_date,
        date_reported=classification.date_reported,
        event_classification=classification.event_classification,
        patient_age_category=classification.patient_age_category,
        rescue_attempted=classification.rescue_attempted,
        patient_family_notified=classification.patient_family_notified,
        increased_length_of_stay=classification.increased_length_of_stay,
        time_harm_assessed=classification.time_harm_assessed,
    )

    # Step 2: Route to specialist agent with structured prompt for proper telemetry
    # IMPORTANT: Use separate session IDs for specialist agents to avoid sharing
    # conversation history with the orchestrator, which would cause tool result mismatches
    specialist_session_id = f"{session_id}_specialist_{event_id}"

    specialist_result = None
    if event_type == "medication_error":
        print(f"[ORCHESTRATOR] Routing to Medication Safety Agent")
        medication_agent = create_medication_agent(user_id, specialist_session_id)
        specialist_result = await medication_agent.invoke_async(
            f"""Analyze this medication safety event:

Event ID: {event_id}
Classification: {event_type} - {severity}
Patient: {patient_id or 'Unknown'}
Location: {location or 'Unknown'}

Event Description:
{event_text}

Provide detailed analysis including:
1. Type of medication error
2. Patient impact assessment
3. Severity score
4. Specific recommendations
"""
        )
    elif event_type == "infection_control":
        print(f"[ORCHESTRATOR] Routing to Infection Control Agent")
        infection_agent = create_infection_agent(user_id, specialist_session_id)
        specialist_result = await infection_agent.invoke_async(
            f"""Analyze this infection control event:

Event ID: {event_id}
Classification: {event_type} - {severity}
Patient: {patient_id or 'Unknown'}
Location: {location or 'Unknown'}

Event Description:
{event_text}

Provide detailed analysis including infection risk assessment and recommendations.
"""
        )
    elif event_type == "patient_fall":
        print(f"[ORCHESTRATOR] Routing to Patient Falls Agent")
        falls_agent = create_falls_agent(user_id, specialist_session_id)
        specialist_result = await falls_agent.invoke_async(
            f"""Analyze this patient fall event:

Event ID: {event_id}
Classification: {event_type} - {severity}
Patient: {patient_id or 'Unknown'}
Location: {location or 'Unknown'}

Event Description:
{event_text}

Provide detailed analysis including injury assessment and fall prevention compliance.
"""
        )

    # Extract specialist analysis text
    specialist_text = str(specialist_result) if specialist_result else ""

    # Step 3: Store analysis results
    if specialist_text:
        classifier.store_analysis(
            event_id=event_id,
            agent_name=event_type,
            analysis={"findings": specialist_text},
            severity_score=4 if severity == "high" else 3,
            recommendations=["Review immediately", "Notify department head"],
        )

    # Step 4: Check threshold for pattern detection
    threshold_info = classifier.check_event_threshold(
        event_type=event_type, threshold=3, timeframe_days=30
    )

    print(
        f"[THRESHOLD CHECK] {event_type}: {threshold_info.get('event_count', 0)} events in last 30 days (threshold: 3)"
    )

    # Step 5: Send appropriate alerts
    # 5a. Immediate alert for high/critical severity
    if severity in ["high", "critical"]:
        send_alert(
            event_id=event_id,
            event_type=event_type,
            severity=severity,
            event_text=event_text,
            alert_type=severity,
            classifier=classifier,
        )

    # 5b. Threshold breach alert for safety officer
    if threshold_info.get("threshold_breached", False):
        print(
            f"[THRESHOLD BREACH] {event_type} threshold exceeded: {threshold_info.get('breach_level', 'warning')} level"
        )
        send_alert(
            event_id=event_id,
            event_type=event_type,
            severity=severity,
            event_text=event_text,
            alert_type="threshold_breach",
            threshold_info=threshold_info,
            classifier=classifier,
        )

    return {
        "event_id": event_id,
        "classification": classification.dict(),  # Return structured classification
        "specialist_analysis": specialist_text if specialist_text else None,
        "threshold_check": threshold_info,
        "status": "completed",
    }


def send_alert(
    event_id: str,
    event_type: str,
    severity: str,
    event_text: str,
    alert_type: str = None,
    threshold_info: Dict[str, Any] = None,
    classifier: SafetyEventClassifier = None,
):
    """
    Send multi-tier SNS alerts based on severity and alert type.

    Routes alerts to appropriate recipients:
    - high/critical severity → physicians + safety officers
    - threshold_breach → safety officers only
    - pattern_alert → safety officers only

    Args:
        event_id: Event identifier
        event_type: Type of safety event
        severity: Severity level
        event_text: Event description
        alert_type: Type of alert (None uses severity, or "threshold_breach", "pattern_alert")
        threshold_info: Additional info for threshold breach alerts
        classifier: SafetyEventClassifier instance for email lookup
    """
    sns_topic_arn = os.environ.get("ALERT_SNS_TOPIC_ARN")
    if not sns_topic_arn:
        print(f"[ALERT] No SNS topic configured, skipping alert")
        return

    sns = boto3.client(
        "sns", region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
    )

    # Determine alert type if not specified
    if alert_type is None:
        alert_type = severity  # "high" or "critical"

    # Get appropriate recipients from DynamoDB
    recipients = []
    if classifier:
        recipients = classifier._get_email_recipients(alert_type)

    if not recipients:
        # Fallback to default if no config found
        print(
            f"[ALERT] No recipients configured for {alert_type}, using default topic"
        )
        recipients_str = "configured recipients"
    else:
        recipients_str = ", ".join(recipients)
        print(f"[ALERT] Sending {alert_type} alert to: {recipients_str}")

    # Build message based on alert type
    if alert_type in ["threshold_breach", "pattern_alert"] and threshold_info:
        subject = f"[THRESHOLD BREACH] {event_type} - {threshold_info.get('event_count', 0)} events"
        message = f"""
Hospital Safety Threshold Alert

Alert Type: Threshold Breach Detected
Event Type: {event_type}
Current Count: {threshold_info.get('event_count', 0)} events
Threshold: {threshold_info.get('threshold', 0)} events
Timeframe: Last {threshold_info.get('timeframe_days', 30)} days
Breach Level: {threshold_info.get('breach_level', 'warning').upper()}

Latest Event:
  Event ID: {event_id}
  Severity: {severity}
  Type: {event_type}

IMPORTANT: Event details contain PHI/PII and are not included in this alert.
Access the secure healthcare safety system with Event ID: {event_id} to view full details.

Recent Events:
{format_recent_events(threshold_info.get('recent_events', []))}

Action Required:
This pattern suggests a systemic issue requiring root cause analysis.
Please review recent {event_type} events and implement corrective actions.

Recipients: {recipients_str}
        """
    else:
        # Standard high/critical severity alert
        subject = f"[{severity.upper()}] Hospital Safety Alert - {event_type}"
        message = f"""
Hospital Safety Event Alert

Event ID: {event_id}
Type: {event_type}
Severity: {severity}

IMPORTANT: This alert contains de-identified information only.
Event details contain PHI/PII and are not included in this email.

Action Required:
1. Access the secure healthcare safety system
2. Search for Event ID: {event_id}
3. Review full event details and analysis
4. Implement immediate response as needed

Recipients: {recipients_str}
        """

    try:
        # Publish to SNS topic (subscribers will receive email)
        sns.publish(
            TopicArn=sns_topic_arn,
            Subject=subject,
            Message=message,
        )
        print(f"[ALERT] Sent {alert_type} alert for event {event_id}")
    except Exception as e:
        print(f"[ALERT ERROR] Failed to send alert: {e}")


def format_recent_events(events: list) -> str:
    """Format recent events for alert message."""
    if not events:
        return "  (No recent events available)"

    lines = []
    for i, evt in enumerate(events[:5], 1):
        lines.append(
            f"  {i}. {evt.get('event_id', 'unknown')} - {evt.get('timestamp', 'unknown')} (severity: {evt.get('severity', 'unknown')})"
        )
    return "\n".join(lines)


@app.entrypoint
async def agent_stream(payload):
    """
    AgentCore Runtime entrypoint for hospital safety event processing.

    This function is called by AgentCore Runtime when a safety event is submitted.
    It processes the event through the orchestrator and specialist agents, yielding
    structured status events at each processing stage.

    Args:
        payload: Contains prompt (event text), userId, runtimeSessionId

    Yields:
        Structured status events + text streaming from LLM responses
    """
    # Initialize Langfuse telemetry on first invocation
    initialize_telemetry()

    event_text = payload.get("prompt")
    user_id = payload.get("userId", "system")
    session_id = payload.get("runtimeSessionId", "default")

    if not event_text:
        yield {"status": "ERROR", "error": "No event text provided"}
        return

    try:
        print(f"[MAIN] Processing safety event for user {user_id}")

        # Status Event 1: RECEIVED
        yield {
            "status": "RECEIVED",
            "message": "Safety event received",
            "timestamp": datetime.utcnow().isoformat()
        }

        # Generate event ID
        import uuid
        event_id = f"evt_{str(uuid.uuid4())[:8]}"

        # Create orchestrator
        orchestrator, classifier = create_orchestrator_agent(
            user_id, session_id, event_text
        )

        # Status Event 2: CLASSIFYING
        yield {
            "status": "CLASSIFYING",
            "message": "Analyzing event with orchestrator",
            "timestamp": datetime.utcnow().isoformat()
        }

        # Step 1: Get structured classification from orchestrator
        print(f"[ORCHESTRATOR] Processing event {event_id}")

        result = await orchestrator.invoke_async(
            f"""Analyze and classify this hospital safety event. Extract all available information.

Safety Event:
{event_text}
""",
            structured_output_model=SafetyEventClassification,
        )

        classification = result.structured_output
        event_type = classification.event_type
        severity = classification.severity

        # Status Event 3: CLASSIFIED
        yield {
            "status": "CLASSIFIED",
            "event_id": event_id,
            "classification": {
                "event_type": event_type,
                "severity": severity,
                "requires_immediate_action": classification.requires_immediate_action
            },
            "timestamp": datetime.utcnow().isoformat()
        }

        # HIPAA Compliance: Log only event_id, type, and severity - NO patient data
        print(
            f"[ORCHESTRATOR] Classified: event_id={event_id}, type={event_type}, severity={severity}"
        )

        # Store the classified event
        classifier.store_event(
            event_id=event_id,
            event_type=event_type,
            severity=severity,
            raw_text=event_text,
            classification=classification.dict(),
            patient_id=classification.patient_id,
            patient_mrn=classification.patient_mrn,
            location=classification.location,
            clinical_state=classification.clinical_state,
            staff_involved=classification.staff_involved,
            equipment_involved=classification.equipment_involved,
            harm_level=classification.harm_level,
            immediate_actions=classification.immediate_actions,
            root_causes=classification.root_causes,
            timeline_details=classification.timeline_details,
            event_date=classification.event_date,
            date_reported=classification.date_reported,
            event_classification=classification.event_classification,
            patient_age_category=classification.patient_age_category,
            rescue_attempted=classification.rescue_attempted,
            patient_family_notified=classification.patient_family_notified,
            increased_length_of_stay=classification.increased_length_of_stay,
            time_harm_assessed=classification.time_harm_assessed,
        )

        # Step 2: Route to specialist agent
        specialist_session_id = f"{session_id}_specialist_{event_id}"

        # Determine specialist name
        specialist_name_map = {
            "medication_error": "MedicationSafety",
            "infection_control": "InfectionControl",
            "patient_fall": "FallsPrevention",
            "device_malfunction": "DeviceSafety"
        }
        specialist_name = specialist_name_map.get(event_type, "Specialist")

        # Status Event 4: ROUTED
        yield {
            "status": "ROUTED",
            "specialist": specialist_name,
            "message": f"Event routed to {specialist_name} for analysis",
            "timestamp": datetime.utcnow().isoformat()
        }

        print(f"[ORCHESTRATOR] Routing to {specialist_name} Agent")

        # Status Event 5: ANALYZING
        yield {
            "status": "ANALYZING",
            "specialist": specialist_name,
            "message": f"{specialist_name} analyzing event",
            "timestamp": datetime.utcnow().isoformat()
        }

        # Invoke specialist agent and emit tool call notifications
        specialist_text = ""
        specialist_agent = None
        prompt = ""
        expected_tools = []

        if event_type == "medication_error":
            specialist_agent = create_medication_agent(user_id, specialist_session_id)
            expected_tools = ["check_drug_database", "assess_medication_severity"]
            prompt = f"""Analyze this medication safety event:

Event ID: {event_id}
Classification: {event_type} - {severity}
Patient: {classification.patient_id or 'Unknown'}
Location: {classification.location or 'Unknown'}

Event Description:
{event_text}

Provide detailed analysis including:
1. Type of medication error
2. Patient impact assessment
3. Severity score
4. Specific recommendations
"""
        elif event_type == "infection_control":
            specialist_agent = create_infection_agent(user_id, specialist_session_id)
            expected_tools = ["assess_infection_risk"]
            prompt = f"""Analyze this infection control event:

Event ID: {event_id}
Classification: {event_type} - {severity}
Patient: {classification.patient_id or 'Unknown'}
Location: {classification.location or 'Unknown'}

Event Description:
{event_text}

Provide detailed analysis including infection risk assessment and recommendations.
"""
        elif event_type == "patient_fall":
            specialist_agent = create_falls_agent(user_id, specialist_session_id)
            expected_tools = ["assess_fall_risk"]
            prompt = f"""Analyze this patient fall event:

Event ID: {event_id}
Classification: {event_type} - {severity}
Patient: {classification.patient_id or 'Unknown'}
Location: {classification.location or 'Unknown'}

Event Description:
{event_text}

Provide detailed analysis including injury assessment and fall prevention compliance.
"""

        # Emit notification that specialist is using tools
        if expected_tools:
            for tool_name in expected_tools:
                yield {
                    "type": "specialist_tool_start",
                    "specialist": specialist_name,
                    "tool_name": tool_name,
                    "tool_call_id": f"specialist_{event_id}_{tool_name}",
                    "timestamp": datetime.utcnow().isoformat()
                }

        # Invoke specialist agent
        if specialist_agent:
            specialist_result = await specialist_agent.invoke_async(prompt)
            specialist_text = str(specialist_result) if specialist_result else ""

            # Emit notification that tools completed
            if expected_tools:
                for tool_name in expected_tools:
                    yield {
                        "type": "specialist_tool_result",
                        "specialist": specialist_name,
                        "tool_name": tool_name,
                        "tool_call_id": f"specialist_{event_id}_{tool_name}",
                        "result": f"Analysis completed by {specialist_name}",
                        "timestamp": datetime.utcnow().isoformat()
                    }

        # Store analysis results
        if specialist_text:
            classifier.store_analysis(
                event_id=event_id,
                agent_name=event_type,
                analysis={"findings": specialist_text},
                severity_score=4 if severity == "high" else 3,
                recommendations=["Review immediately", "Notify department head"],
            )

        # Step 3: Check threshold for pattern detection
        threshold_info = classifier.check_event_threshold(
            event_type=event_type, threshold=3, timeframe_days=30
        )

        print(
            f"[THRESHOLD CHECK] {event_type}: {threshold_info.get('event_count', 0)} events in last 30 days (threshold: 3)"
        )

        # Status Event 6: THRESHOLD_BREACHED (if applicable)
        if threshold_info.get("threshold_breached", False):
            yield {
                "status": "THRESHOLD_BREACHED",
                "threshold_info": threshold_info,
                "timestamp": datetime.utcnow().isoformat()
            }

        # Step 4: Send appropriate alerts
        alerts_sent = False
        if severity in ["high", "critical"]:
            send_alert(
                event_id=event_id,
                event_type=event_type,
                severity=severity,
                event_text=event_text,
                alert_type=severity,
                classifier=classifier,
            )
            alerts_sent = True

        if threshold_info.get("threshold_breached", False):
            send_alert(
                event_id=event_id,
                event_type=event_type,
                severity=severity,
                event_text=event_text,
                alert_type="threshold_breach",
                threshold_info=threshold_info,
                classifier=classifier,
            )
            alerts_sent = True

        # Status Event 7: ALERT_SENT (if applicable)
        if alerts_sent:
            alert_type = "high_severity" if severity in ["high", "critical"] else "threshold_breach"
            yield {
                "status": "ALERT_SENT",
                "alert_type": alert_type,
                "timestamp": datetime.utcnow().isoformat()
            }

        # Status Event 8: COMPLETED
        yield {
            "status": "COMPLETED",
            "event_id": event_id,
            "classification": classification.dict(),
            "analysis": specialist_text if specialist_text else None,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        import traceback
        import re

        # HIPAA Compliance: Sanitize error messages to remove PHI patterns
        error_msg = str(e)
        # Redact patient IDs (MRN-\d+, Patient \d+)
        error_msg = re.sub(r'\bMRN-\d+\b', '[PATIENT_ID]', error_msg, flags=re.IGNORECASE)
        error_msg = re.sub(r'\bPatient\s+\d+\b', '[PATIENT_ID]', error_msg, flags=re.IGNORECASE)
        # Redact room numbers
        error_msg = re.sub(r'\bRoom\s+\d+\b', '[LOCATION]', error_msg, flags=re.IGNORECASE)
        # Redact ages
        error_msg = re.sub(r'\b\d+yo\b', '[AGE]', error_msg, flags=re.IGNORECASE)
        error_msg = re.sub(r'\b\d+\s*year[s]?\s*old\b', '[AGE]', error_msg, flags=re.IGNORECASE)
        # Redact names after titles (Nurse, Dr., Doctor)
        error_msg = re.sub(r'\b(Nurse|Dr\.|Doctor)\s+[A-Z][a-z]+\b', r'\1 [NAME]', error_msg)

        print(f"[ERROR] Failed to process safety event: {error_msg}")

        # Get sanitized traceback
        tb_lines = traceback.format_exc()
        tb_lines = re.sub(r'\bMRN-\d+\b', '[PATIENT_ID]', tb_lines, flags=re.IGNORECASE)
        tb_lines = re.sub(r'\bPatient\s+\d+\b', '[PATIENT_ID]', tb_lines, flags=re.IGNORECASE)
        tb_lines = re.sub(r'\bRoom\s+\d+\b', '[LOCATION]', tb_lines, flags=re.IGNORECASE)
        tb_lines = re.sub(r'\b\d+yo\b', '[AGE]', tb_lines, flags=re.IGNORECASE)
        tb_lines = re.sub(r'\b\d+\s*year[s]?\s*old\b', '[AGE]', tb_lines, flags=re.IGNORECASE)
        tb_lines = re.sub(r'\b(Nurse|Dr\.|Doctor)\s+[A-Z][a-z]+\b', r'\1 [NAME]', tb_lines)
        print(tb_lines)

        yield {"status": "ERROR", "error": error_msg}


if __name__ == "__main__":
    app.run()
