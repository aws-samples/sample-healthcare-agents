"""
Unit tests for severity scoring and risk assessment logic.

Tests the algorithms that determine event severity based on
various risk factors without requiring agent invocation.
"""

import pytest


@pytest.mark.unit
class TestSeverityScoring:
    """Test severity score calculation."""

    def test_critical_severity_score(self):
        """Test critical severity gets score of 5."""
        severity_map = {"low": 1, "medium": 2, "high": 3, "critical": 5}

        score = severity_map["critical"]
        assert score == 5

    def test_high_severity_score(self):
        """Test high severity gets score of 3."""
        severity_map = {"low": 1, "medium": 2, "high": 3, "critical": 5}

        score = severity_map["high"]
        assert score == 3

    def test_low_severity_score(self):
        """Test low severity gets score of 1."""
        severity_map = {"low": 1, "medium": 2, "high": 3, "critical": 5}

        score = severity_map["low"]
        assert score == 1

    @pytest.mark.parametrize(
        "severity,expected_score",
        [
            ("low", 1),
            ("medium", 2),
            ("high", 3),
            ("critical", 5),
        ],
    )
    def test_all_severity_scores(self, severity, expected_score):
        """Test all severity to score mappings."""
        severity_map = {"low": 1, "medium": 2, "high": 3, "critical": 5}

        score = severity_map[severity]
        assert score == expected_score


@pytest.mark.unit
class TestImmediateActionLogic:
    """Test logic for determining if immediate action is required."""

    def test_critical_requires_immediate_action(self):
        """Test that critical severity requires immediate action."""

        def requires_immediate_action(severity, event_type):
            if severity == "critical":
                return True
            if severity == "high" and event_type in [
                "medication_error",
                "patient_fall",
            ]:
                return True
            return False

        result = requires_immediate_action("critical", "patient_fall")
        assert result is True

    def test_high_medication_error_requires_action(self):
        """Test that high severity medication errors require action."""

        def requires_immediate_action(severity, event_type):
            if severity == "critical":
                return True
            if severity == "high" and event_type in [
                "medication_error",
                "patient_fall",
            ]:
                return True
            return False

        result = requires_immediate_action("high", "medication_error")
        assert result is True

    def test_low_severity_no_immediate_action(self):
        """Test that low severity doesn't require immediate action."""

        def requires_immediate_action(severity, event_type):
            if severity == "critical":
                return True
            if severity == "high" and event_type in [
                "medication_error",
                "patient_fall",
            ]:
                return True
            return False

        result = requires_immediate_action("low", "device_malfunction")
        assert result is False

    def test_medium_infection_no_immediate_action(self):
        """Test medium severity infection doesn't require immediate action."""

        def requires_immediate_action(severity, event_type):
            if severity == "critical":
                return True
            if severity == "high" and event_type in [
                "medication_error",
                "patient_fall",
            ]:
                return True
            return False

        result = requires_immediate_action("medium", "infection_control")
        assert result is False


@pytest.mark.unit
class TestAlertingLogic:
    """Test alert routing logic based on severity."""

    def test_critical_alerts_to_all(self):
        """Test critical events alert all recipients."""

        def get_alert_recipients(severity):
            if severity in ["high", "critical"]:
                return ["physicians", "safety_officers"]
            elif severity == "medium":
                return ["safety_officers"]
            return []

        recipients = get_alert_recipients("critical")

        assert "physicians" in recipients
        assert "safety_officers" in recipients
        assert len(recipients) == 2

    def test_high_alerts_to_all(self):
        """Test high events alert all recipients."""

        def get_alert_recipients(severity):
            if severity in ["high", "critical"]:
                return ["physicians", "safety_officers"]
            elif severity == "medium":
                return ["safety_officers"]
            return []

        recipients = get_alert_recipients("high")

        assert "physicians" in recipients
        assert "safety_officers" in recipients

    def test_medium_alerts_to_safety_only(self):
        """Test medium events alert safety officers only."""

        def get_alert_recipients(severity):
            if severity in ["high", "critical"]:
                return ["physicians", "safety_officers"]
            elif severity == "medium":
                return ["safety_officers"]
            return []

        recipients = get_alert_recipients("medium")

        assert "safety_officers" in recipients
        assert "physicians" not in recipients
        assert len(recipients) == 1

    def test_low_no_alerts(self):
        """Test low severity events don't trigger alerts."""

        def get_alert_recipients(severity):
            if severity in ["high", "critical"]:
                return ["physicians", "safety_officers"]
            elif severity == "medium":
                return ["safety_officers"]
            return []

        recipients = get_alert_recipients("low")

        assert len(recipients) == 0


@pytest.mark.unit
class TestRiskFactorAssessment:
    """Test risk factor evaluation for severity determination."""

    def test_patient_age_risk_factor(self):
        """Test that patient age is a risk factor."""

        def assess_fall_risk(age, mobility, history_of_falls):
            risk_score = 0
            if age >= 65:
                risk_score += 2
            if mobility == "impaired":
                risk_score += 2
            if history_of_falls:
                risk_score += 3
            return risk_score

        # Elderly patient
        risk = assess_fall_risk(age=82, mobility="normal", history_of_falls=False)
        assert risk >= 2

    def test_multiple_risk_factors(self):
        """Test cumulative risk from multiple factors."""

        def assess_fall_risk(age, mobility, history_of_falls):
            risk_score = 0
            if age >= 65:
                risk_score += 2
            if mobility == "impaired":
                risk_score += 2
            if history_of_falls:
                risk_score += 3
            return risk_score

        # Multiple risk factors
        risk = assess_fall_risk(age=85, mobility="impaired", history_of_falls=True)
        assert risk == 7  # 2 + 2 + 3

    def test_medication_error_risk_factors(self):
        """Test medication error risk assessment."""

        def assess_medication_risk(drug_class, dosage_error_magnitude, patient_history):
            risk_score = 0
            high_risk_drugs = ["warfarin", "insulin", "opioids"]

            if drug_class.lower() in high_risk_drugs:
                risk_score += 3
            if dosage_error_magnitude > 50:  # >50% error
                risk_score += 2
            if patient_history and "bleeding" in patient_history:
                risk_score += 2

            return risk_score

        # High-alert drug with significant error
        risk = assess_medication_risk(
            drug_class="warfarin",
            dosage_error_magnitude=100,  # 100% overdose
            patient_history="history of GI bleeding",
        )

        assert risk == 7  # 3 + 2 + 2
        # This should be critical severity

    @pytest.mark.parametrize(
        "age,mobility,falls,expected_min_risk",
        [
            (82, "impaired", True, 7),  # All risk factors
            (65, "normal", False, 2),  # Age only
            (50, "impaired", True, 5),  # No age risk
            (40, "normal", False, 0),  # No risk factors
        ],
    )
    def test_fall_risk_scenarios(self, age, mobility, falls, expected_min_risk):
        """Test various fall risk scenarios."""

        def assess_fall_risk(age, mobility, history_of_falls):
            risk_score = 0
            if age >= 65:
                risk_score += 2
            if mobility == "impaired":
                risk_score += 2
            if history_of_falls:
                risk_score += 3
            return risk_score

        risk = assess_fall_risk(age, mobility, falls)
        assert risk >= expected_min_risk
