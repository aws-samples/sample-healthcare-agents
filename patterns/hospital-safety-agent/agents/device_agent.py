# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Device Malfunction Specialist Agent

Analyzes medical device failures, equipment malfunctions, and related safety events.
"""

import os
import requests
from datetime import datetime, timedelta
from typing import Dict, Any, List, Literal, Optional
from pydantic import BaseModel, Field
from strands import Agent, tool
from strands.models import BedrockModel
import boto3
from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig
from bedrock_agentcore.memory.integrations.strands.session_manager import (
    AgentCoreMemorySessionManager,
)


class MaudeResult(BaseModel):
    """Structured result from FDA MAUDE database query."""

    device_name: str
    found: bool
    report_count: int = 0
    event_types: List[str] = Field(default_factory=list)
    manufacturer: Optional[str] = None
    recent_reports: List[Dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None
    message: Optional[str] = None


class DeviceSeverityAssessment(BaseModel):
    """Structured assessment of device malfunction severity."""

    severity_score: int = Field(ge=1, le=5, description="Severity score from 1-5")
    severity_level: Literal["critical", "severe", "moderate", "minor", "none"]
    failure_mode: Literal[
        "complete_failure", "partial_failure", "alarm_failure",
        "software_error", "user_error", "unknown"
    ]
    is_life_critical_device: bool
    nqf_reportable: bool = Field(
        description="True if this qualifies as an NQF serious reportable event"
    )
    nqf_rationale: Optional[str] = None
    recommendations: List[str]
    requires_immediate_removal: bool


class DevicePatternResult(BaseModel):
    """Structured result from device malfunction pattern analysis."""

    device_name: str
    days_analyzed: int
    event_count: int
    is_recurring: bool
    risk_level: Literal["low", "medium", "high"]
    historical_events: List[Dict[str, Any]] = Field(default_factory=list)
    trend: Literal["stable", "increasing"]
    recommended_actions: List[str] = Field(default_factory=list)


class DeviceAnalysisResult(BaseModel):
    """Structured result returned by the Device Safety Agent to the orchestrator."""

    analysis_text: str = Field(description="Full formatted markdown analysis for display")
    device_name: str = Field(description="Primary device involved in the malfunction")
    is_recurring: bool = Field(description="True if same device has 3+ events in the analysis window")
    risk_level: Literal["low", "medium", "high"] = Field(description="Pattern risk level")
    event_count: int = Field(description="Number of historical events found for this device")
    nqf_reportable: bool = Field(description="True if this qualifies as NQF serious reportable event")


# Life-critical device types that escalate severity
LIFE_CRITICAL_DEVICES = {
    "ventilator", "defibrillator", "infusion pump", "iv pump", "pacemaker",
    "cardiac monitor", "pulse oximeter", "anesthesia machine", "dialysis",
    "ecmo", "iabp", "syringe pump", "feeding pump",
}

# NQF Serious Reportable Events related to devices
NQF_DEVICE_EVENTS = {
    "infusion pump": "NQF SRE: Death/serious disability associated with infusion pump",
    "iv pump": "NQF SRE: Death/serious disability associated with infusion pump",
    "syringe pump": "NQF SRE: Death/serious disability associated with infusion pump",
    "air embolism": "NQF SRE: Death/serious disability associated with air embolism",
    "retained": "NQF SRE: Unintended retention of a foreign object in patient",
    "surgical instrument": "NQF SRE: Unintended retention of a foreign object in patient",
}


class DeviceTools:
    """Tools for device malfunction safety analysis."""

    def __init__(self, region: str = "us-east-1"):
        self.dynamodb = boto3.resource("dynamodb", region_name=region)
        self.events_table = self.dynamodb.Table(
            os.environ.get("EVENTS_TABLE_NAME", "hospital-safety-events")
        )

    @tool
    def lookup_fda_maude(self, device_name: str) -> MaudeResult:
        """
        Query the FDA MAUDE (Manufacturer and User Facility Device Experience) database
        for adverse event reports related to a medical device.

        Use this to understand the known failure history and risk profile of the device
        involved in the incident.

        Args:
            device_name: Name of the medical device (e.g. "infusion pump", "ventilator")

        Returns:
            Structured MAUDE data including report count, event types, and recent reports
        """
        try:
            url = "https://api.fda.gov/device/event.json"
            params = {
                "search": f'device.generic_name:"{device_name}"',
                "limit": 5,
                "sort": "date_of_event:desc",
            }
            response = requests.get(url, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                results = data.get("results", [])
                meta = data.get("meta", {}).get("results", {})

                event_types = list({
                    r.get("event_type", "unknown")
                    for r in results
                    if r.get("event_type")
                })
                manufacturer = results[0].get("device", [{}])[0].get("manufacturer_d_name") if results else None

                recent = []
                for r in results[:3]:
                    recent.append({
                        "date": r.get("date_of_event", "unknown"),
                        "event_type": r.get("event_type", "unknown"),
                        "adverse_outcome": r.get("adverse_event_flag", "unknown"),
                    })

                return MaudeResult(
                    device_name=device_name,
                    found=True,
                    report_count=meta.get("total", len(results)),
                    event_types=event_types,
                    manufacturer=manufacturer,
                    recent_reports=recent,
                )

            return MaudeResult(
                device_name=device_name,
                found=False,
                message=f"No MAUDE records found for '{device_name}'",
            )

        except Exception as e:
            return MaudeResult(
                device_name=device_name,
                found=False,
                error=f"MAUDE query failed: {str(e)}",
            )

    @tool
    def assess_device_malfunction_severity(
        self, device_name: str, failure_mode: str, patient_impact: str
    ) -> DeviceSeverityAssessment:
        """
        Assess the severity of a device malfunction event.

        Evaluates severity based on device criticality, failure mode, and patient impact.
        Automatically flags NQF serious reportable events involving infusion pumps or
        retained surgical instruments.

        Args:
            device_name: Name of the device (e.g. "ventilator", "infusion pump")
            failure_mode: How the device failed: complete_failure | partial_failure |
                          alarm_failure | software_error | user_error | unknown
            patient_impact: Actual/potential harm: none | minor | moderate | severe | critical

        Returns:
            Structured severity assessment with NQF flag and recommended actions
        """
        severity_map = {"none": 1, "minor": 2, "moderate": 3, "severe": 4, "critical": 5}
        severity_score = severity_map.get(patient_impact.lower(), 3)

        device_lower = device_name.lower()
        is_life_critical = any(d in device_lower for d in LIFE_CRITICAL_DEVICES)

        # Life-critical device failures escalate severity
        if is_life_critical and failure_mode in ("complete_failure", "alarm_failure"):
            severity_score = min(5, severity_score + 1)

        # Check NQF reportability
        nqf_reportable = False
        nqf_rationale = None
        for keyword, rationale in NQF_DEVICE_EVENTS.items():
            if keyword in device_lower:
                if severity_score >= 3:  # moderate or higher
                    nqf_reportable = True
                    nqf_rationale = rationale
                    break

        severity_levels = {1: "none", 2: "minor", 3: "moderate", 4: "severe", 5: "critical"}
        severity_level = severity_levels.get(severity_score, "moderate")

        recommendations = []
        if severity_score >= 4:
            recommendations.extend([
                "Remove device from service immediately",
                "Notify biomedical engineering and risk management",
                "Preserve device and all associated records for investigation",
                "Complete incident report within 24 hours",
                "Notify FDA via MedWatch if device caused or may have caused death/serious injury",
            ])
        elif severity_score == 3:
            recommendations.extend([
                "Take device out of service pending inspection",
                "Notify biomedical engineering",
                "Complete incident report within 48 hours",
            ])
        else:
            recommendations.extend([
                "Document malfunction and schedule preventive maintenance review",
                "Complete incident report",
            ])

        if nqf_reportable:
            recommendations.append(
                f"MANDATORY EXTERNAL REPORT REQUIRED: {nqf_rationale}"
            )

        return DeviceSeverityAssessment(
            severity_score=severity_score,
            severity_level=severity_level,
            failure_mode=failure_mode,
            is_life_critical_device=is_life_critical,
            nqf_reportable=nqf_reportable,
            nqf_rationale=nqf_rationale,
            recommendations=recommendations,
            requires_immediate_removal=severity_score >= 4 or is_life_critical,
        )

    @tool
    def check_device_malfunction_patterns(
        self, device_name: str, days: int = 30
    ) -> DevicePatternResult:
        """
        Query historical device malfunction events to detect recurring failures.

        Args:
            device_name: Name of the device to check for recurring failures
            days: Number of days to look back (default: 30)

        Returns:
            Structured historical device malfunction data and pattern analysis
        """
        try:
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)

            response = self.events_table.scan(
                FilterExpression="event_type = :type AND #ts BETWEEN :start AND :end AND contains(equipment_involved, :device)",
                ExpressionAttributeNames={"#ts": "timestamp"},
                ExpressionAttributeValues={
                    ":type": "device_malfunction",
                    ":start": start_date.isoformat() + "Z",
                    ":end": end_date.isoformat() + "Z",
                    ":device": device_name.lower(),
                },
            )

            events = response.get("Items", [])
            event_count = len(events)
            is_recurring = event_count >= 3
            risk_level = "high" if event_count >= 5 else "medium" if is_recurring else "low"

            recommended_actions = []
            if risk_level == "high":
                recommended_actions = [
                    f"Escalate to biomedical engineering director — {event_count} malfunctions of {device_name} in {days} days",
                    "Conduct fleet-wide inspection of all units of this device model",
                    "Consider temporary suspension of device pending manufacturer investigation",
                    "File FDA MedWatch report for device-related recurring failures",
                ]
            elif risk_level == "medium":
                recommended_actions = [
                    f"Notify biomedical engineering of recurring {device_name} failures",
                    "Schedule accelerated preventive maintenance for all units",
                    "Review operator training compliance",
                ]
            else:
                recommended_actions = [
                    "Document and monitor for additional occurrences",
                    "Standard incident reporting process",
                ]

            return DevicePatternResult(
                device_name=device_name,
                days_analyzed=days,
                event_count=event_count,
                is_recurring=is_recurring,
                risk_level=risk_level,
                historical_events=events[:5],
                trend="increasing" if event_count > 2 else "stable",
                recommended_actions=recommended_actions,
            )

        except Exception as e:
            return DevicePatternResult(
                device_name=device_name,
                days_analyzed=days,
                event_count=0,
                is_recurring=False,
                risk_level="low",
                historical_events=[],
                trend="stable",
                recommended_actions=[f"Pattern check failed: {str(e)}"],
            )


def create_device_agent(user_id: str, session_id: str, langfuse_session_id: str = None) -> Agent:
    """
    Create the Device Safety Specialist Agent.

    Analyzes medical device malfunction events including:
    - Complete/partial device failures
    - Alarm failures on life-critical equipment
    - Software and firmware errors
    - IV pump, ventilator, defibrillator, and monitoring equipment failures
    - NQF serious reportable device events

    Args:
        user_id: User ID for memory tracking
        session_id: Session ID for conversation history
        langfuse_session_id: Langfuse session ID for observability grouping

    Returns:
        Configured Device Safety Agent
    """
    system_prompt = """IMPORTANT: Begin every response directly with the analysis. Never open with transitional phrases such as "I now have all the data needed", "Here is the full report", "Based on my analysis", or any similar preamble. Start with the first finding immediately.

You are the Device Safety Specialist. Follow this exact sequence:
1. Call lookup_fda_maude with the device name to check known failure history in the FDA MAUDE database.
2. Call assess_device_malfunction_severity with device name, failure mode, and patient impact.
3. Call check_device_malfunction_patterns with the device name to detect recurring facility failures.

Then return a DeviceAnalysisResult with:
- analysis_text: full formatted markdown report (below format)
- device_name: primary device involved
- is_recurring: from check_device_malfunction_patterns
- risk_level: from check_device_malfunction_patterns
- event_count: from check_device_malfunction_patterns
- nqf_reportable: from assess_device_malfunction_severity

Markdown format for analysis_text:

### 🔧 Device Malfunction
| | |
|--|--|
| **Device** | [name] |
| **Failure Mode** | [mode] |
| **Life-Critical Device** | [Yes / No] |
| **Severity** | [level] (score [n]/5) |
| **Immediate Removal Required** | [Yes / No] |

### 📊 Pattern Analysis
| | |
|--|--|
| **Recurring** | [Yes / No] |
| **Recent Failures** | [n] in last [days] days |
| **Risk Level** | [🟢 low · 🟡 medium · 🔴 high] |

### 📋 FDA MAUDE History
| | |
|--|--|
| **Total Reports** | [n] |
| **Event Types** | [types] |
| **Manufacturer** | [name or N/A] |

### ⚠️ NQF Reporting
[Flag if mandatory, or "Not required for this event"]

### ⚡ Recommended Actions
1. [Most urgent — removal/escalation if life-critical or recurring]
2. [Next]

Only state facts present in the event text or returned by tools. Do not infer, extrapolate, or add clinical reasoning beyond what the data supports. Omit rows where data is unavailable. No prose.
"""

    model_id = os.environ.get("MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")
    bedrock_model = BedrockModel(model_id=model_id, temperature=0.1)

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

    device_tools = DeviceTools(region=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))

    agent = Agent(
        name="DeviceSafety",
        system_prompt=system_prompt,
        tools=[
            device_tools.lookup_fda_maude,
            device_tools.assess_device_malfunction_severity,
            device_tools.check_device_malfunction_patterns,
        ],
        model=bedrock_model,
        session_manager=session_manager,
        trace_attributes={
            "user.id": user_id,
            "session.id": langfuse_session_id or session_id,
            "agent.type": "device_specialist",
        },
    )

    return agent
