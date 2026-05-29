# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Hospital Safety Specialist Agents

This module contains specialized agents for analyzing different types of safety events:
- MedicationAgent: Medication errors and drug safety
- InfectionAgent: Healthcare-associated infections
- FallsAgent: Patient falls and injury prevention
"""

from .medication_agent import create_medication_agent, MedicationTools
from .infection_agent import create_infection_agent, InfectionControlTools
from .falls_agent import create_falls_agent, FallsTools

__all__ = [
    "create_medication_agent",
    "create_infection_agent",
    "create_falls_agent",
    "MedicationTools",
    "InfectionControlTools",
    "FallsTools",
]
