import json
from enum import Enum
from pydantic import BaseModel, Field


class InterventionType(str, Enum):
    REPURPOSE = "repurpose"
    RETROFIT = "retrofit"
    GREEN_CORRIDOR = "green_corridor"
    PEDESTRIAN_UPGRADE = "pedestrian_upgrade"
    NEW_DEVELOPMENT = "new_development"
    DELAY_DEVELOPMENT = "delay_development"
    NO_OP = "no_op"


class ConstructionStatus(str, Enum):
    UNAVAILABLE = "unavailable"
    PARTIAL = "partial"
    OPERATIONAL = "operational"


class Intervention(BaseModel):
    """One row of interventions.csv. Field names match the CSV header exactly."""
    intervention_id: str                      # e.g. "INT-001"
    target_asset_id: str                      # asset (B-03), edge (E-R17) or project (PRJ-P3)
    intervention_type: InterventionType
    parameters: dict = Field(default_factory=dict)          # -> parameters_json
    expected_derived: dict = Field(default_factory=dict)    # -> expected_derived_json
    construction_start_year: int = 2027
    construction_duration_months: int = 0
    activation_year: int = 2027
    during_construction_status: ConstructionStatus = ConstructionStatus.OPERATIONAL
    capex_delta_rm: float = 0
    opex_delta_rm: float = 0

    def to_row(self, scenario_id: str) -> dict:
        return {
            "scenario_id": scenario_id,
            "intervention_id": self.intervention_id,
            "target_asset_id": self.target_asset_id,
            "intervention_type": self.intervention_type.value,
            "parameters_json": json.dumps(self.parameters),
            "expected_derived_json": json.dumps(self.expected_derived) if self.expected_derived else "",
            "expected_source": "llm_estimate" if self.expected_derived else "",
            "construction_start_year": self.construction_start_year,
            "construction_duration_months": self.construction_duration_months,
            "activation_year": self.activation_year,
            "during_construction_status": self.during_construction_status.value,
            "capex_delta_rm": self.capex_delta_rm,
            "opex_delta_rm": self.opex_delta_rm,
            "validation_status": "pending",
            "status": "simulated",
        }


class Option(BaseModel):
    option_id: str            # "A", "B", "C"
    title: str
    interventions: list[Intervention]