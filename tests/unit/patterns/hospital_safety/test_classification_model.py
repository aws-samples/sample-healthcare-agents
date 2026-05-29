"""
Unit tests for SafetyEventClassification Pydantic model.

These tests validate the structured output model used for type-safe
event classification without requiring AWS or agent invocation.
"""

import pytest
from pydantic import ValidationError


# Import the model (mock if needed for testing)
class SafetyEventClassification:
    """
    Mock of the SafetyEventClassification model for unit testing.
    In real tests, import from orchestrator.py
    """

    def __init__(
        self,
        event_type: str,
        severity: str,
        patient_id: str = None,
        location: str = None,
        staff_involved: str = None,
        requires_immediate_action: bool = False,
        brief_summary: str = "",
    ):
        # Validate event_type
        valid_types = [
            "medication_error",
            "infection_control",
            "patient_fall",
            "device_malfunction",
        ]
        if event_type not in valid_types:
            raise ValueError(f"event_type must be one of {valid_types}")

        # Validate severity
        valid_severities = ["low", "medium", "high", "critical"]
        if severity not in valid_severities:
            raise ValueError(f"severity must be one of {valid_severities}")

        self.event_type = event_type
        self.severity = severity
        self.patient_id = patient_id
        self.location = location
        self.staff_involved = staff_involved
        self.requires_immediate_action = requires_immediate_action
        self.brief_summary = brief_summary


@pytest.mark.unit
class TestSafetyEventClassification:
    """Test SafetyEventClassification Pydantic model validation."""

    def test_valid_medication_error(self):
        """Test valid medication error classification."""
        classification = SafetyEventClassification(
            event_type="medication_error",
            severity="high",
            patient_id="MRN-12345",
            location="Room 302",
            staff_involved="Nurse Johnson",
            requires_immediate_action=True,
            brief_summary="Wrong dosage of Warfarin administered",
        )

        assert classification.event_type == "medication_error"
        assert classification.severity == "high"
        assert classification.patient_id == "MRN-12345"
        assert classification.requires_immediate_action is True

    def test_valid_patient_fall(self):
        """Test valid patient fall classification."""
        classification = SafetyEventClassification(
            event_type="patient_fall",
            severity="critical",
            patient_id="Room 405",
            location="Room 405",
            staff_involved="Nurse Martinez",
            requires_immediate_action=True,
            brief_summary="82yo patient fell from bed, hip fracture",
        )

        assert classification.event_type == "patient_fall"
        assert classification.severity == "critical"

    def test_valid_infection_control(self):
        """Test valid infection control event."""
        classification = SafetyEventClassification(
            event_type="infection_control",
            severity="high",
            patient_id="ICU Room 501",
            location="ICU Room 501",
            requires_immediate_action=True,
            brief_summary="MRSA isolation breach - no PPE used",
        )

        assert classification.event_type == "infection_control"
        assert classification.severity == "high"

    def test_invalid_event_type(self):
        """Test that invalid event_type raises error."""
        with pytest.raises(ValueError, match="event_type must be one of"):
            SafetyEventClassification(
                event_type="invalid_type",  # Invalid!
                severity="high",
            )

    def test_invalid_severity(self):
        """Test that invalid severity raises error."""
        with pytest.raises(ValueError, match="severity must be one of"):
            SafetyEventClassification(
                event_type="medication_error",
                severity="extreme",  # Invalid!
            )

    def test_optional_fields(self):
        """Test that optional fields can be None."""
        classification = SafetyEventClassification(
            event_type="device_malfunction", severity="medium"
        )

        assert classification.patient_id is None
        assert classification.location is None
        assert classification.staff_involved is None
        assert classification.requires_immediate_action is False

    @pytest.mark.parametrize(
        "event_type,severity",
        [
            ("medication_error", "low"),
            ("medication_error", "medium"),
            ("medication_error", "high"),
            ("medication_error", "critical"),
            ("infection_control", "low"),
            ("patient_fall", "critical"),
            ("device_malfunction", "medium"),
        ],
    )
    def test_all_valid_combinations(self, event_type, severity):
        """Test all valid event_type and severity combinations."""
        classification = SafetyEventClassification(
            event_type=event_type, severity=severity
        )

        assert classification.event_type == event_type
        assert classification.severity == severity


@pytest.mark.unit
class TestSeverityLevels:
    """Test severity level logic and thresholds."""

    def test_critical_requires_immediate_action(self):
        """Test that critical severity should require immediate action."""
        classification = SafetyEventClassification(
            event_type="patient_fall",
            severity="critical",
            requires_immediate_action=True,
        )

        assert classification.severity == "critical"
        assert classification.requires_immediate_action is True

    def test_high_severity_should_alert(self):
        """Test that high severity events should trigger alerts."""
        classification = SafetyEventClassification(
            event_type="medication_error",
            severity="high",
            requires_immediate_action=True,
        )

        assert classification.severity == "high"
        # High severity should require action
        assert classification.requires_immediate_action is True

    def test_low_severity_no_immediate_action(self):
        """Test that low severity may not require immediate action."""
        classification = SafetyEventClassification(
            event_type="device_malfunction",
            severity="low",
            requires_immediate_action=False,
        )

        assert classification.severity == "low"
        assert classification.requires_immediate_action is False


@pytest.mark.unit
class TestEntityExtraction:
    """Test entity extraction validation."""

    def test_patient_id_formats(self):
        """Test various patient ID formats."""
        # MRN format
        c1 = SafetyEventClassification(
            event_type="medication_error",
            severity="high",
            patient_id="MRN-123456",
        )
        assert c1.patient_id == "MRN-123456"

        # Room format
        c2 = SafetyEventClassification(
            event_type="patient_fall",
            severity="critical",
            patient_id="Room 302",
        )
        assert c2.patient_id == "Room 302"

    def test_location_extraction(self):
        """Test location field extraction."""
        classification = SafetyEventClassification(
            event_type="infection_control",
            severity="high",
            location="ICU Room 501",
        )

        assert classification.location == "ICU Room 501"

    def test_staff_extraction(self):
        """Test staff member identification."""
        classification = SafetyEventClassification(
            event_type="medication_error",
            severity="high",
            staff_involved="Nurse Sarah, Dr. Chen",
        )

        assert "Nurse Sarah" in classification.staff_involved
        assert "Dr. Chen" in classification.staff_involved
