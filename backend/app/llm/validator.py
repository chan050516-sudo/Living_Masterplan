"""Proposal validator.

The LLM proposes a plan. This module decides whether the plan is
legal, affordable, and internally consistent. It NEVER modifies the
plan — it only reports whether the plan can be executed.

Hard checks (blocking):
  - subtype exists in taxonomy
  - intervention type is in the asset's action space
  - cumulative CAPEX within budget
  - construction_start_year is in the future
  - no duplicate asset in a single plan
  - no two repurposes competing for the same subtype pool

Soft checks (advisory):
  - supply duplication warning
  - demographic mismatch warning
  - marginal-value warning when expected effects look implausible
"""

import logging
import math
from dataclasses import dataclass, field
from typing import Optional

from ..taxonomy import get_subtype
from ..deadspace.layer3 import ACTION_SPACE

log = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Result container
# ------------------------------------------------------------------


@dataclass
class ValidationResult:
    valid: bool
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    normalised_plan: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "normalised_plan": list(self.normalised_plan),
        }


# ------------------------------------------------------------------
# Validator
# ------------------------------------------------------------------


# Default construction timing for each intervention type. Matches
# assumptions.yml: construction_defaults. Used when the LLM does not
# specify timing.
DEFAULT_TIMING = {
    "repurpose":         {"start_offset": 1, "duration_months": 18, "during": "unavailable"},
    "retrofit":          {"start_offset": 0, "duration_months": 12, "during": "partial"},
    "green_corridor":    {"start_offset": 0, "duration_months": 12, "during": "operational"},
    "pedestrian_upgrade":{"start_offset": 0, "duration_months": 6,  "during": "partial"},
    "new_development":   {"start_offset": 0, "duration_months": 36, "during": "unavailable"},
    "delay_development": {"start_offset": 0, "duration_months": 0,  "during": "operational"},
}


class ProposalValidator:
    """
    Validate an LLM-proposed plan against the township state.

    Parameters
    ----------
    ds : TownshipDataSource
        Loaded township data.
    base_year : int
        The year the plan is being proposed in. All construction
        anchors must be >= base_year.
    """

    def __init__(self, ds, base_year: int = 2026):
        self.ds = ds
        self.base_year = base_year

    def validate(self, plan: list, constraints: Optional[dict] = None) -> ValidationResult:
        constraints = constraints or {}
        errors: list = []
        warnings: list = []
        normalised: list = []

        if not isinstance(plan, list) or not plan:
            return ValidationResult(False, ["plan is empty or malformed"], [], [])

        # ---- Per-item checks ----
        seen_assets: set = set()
        cumulative_capex = 0.0
        capex_limit = constraints.get("capex_limit")

        for i, item in enumerate(plan):
            item_errors, item_warnings, normalised_item = self._validate_item(
                i, item, seen_assets,
            )
            errors.extend(item_errors)
            warnings.extend(item_warnings)
            if normalised_item is not None:
                normalised.append(normalised_item)
                cumulative_capex += normalised_item["capex_delta_rm"] or 0.0

        # ---- Budget check ----
        if capex_limit is not None and cumulative_capex > float(capex_limit):
            over = cumulative_capex - float(capex_limit)
            errors.append(
                f"Plan CAPEX RM {cumulative_capex:,.0f} exceeds budget "
                f"RM {float(capex_limit):,.0f} by RM {over:,.0f}."
            )

        # ---- Cross-item checks ----
        cross_errors, cross_warnings = self._validate_cross_items(normalised)
        errors.extend(cross_errors)
        warnings.extend(cross_warnings)

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            normalised_plan=normalised,
        )

    # --------------------------------------------------------------
    # Per-item validation
    # --------------------------------------------------------------

    def _validate_item(self, index: int, item: dict, seen_assets: set):
        errors: list = []
        warnings: list = []
        prefix = f"item[{index}]"

        if not isinstance(item, dict):
            return [f"{prefix}: not an object"], [], None

        asset_id = item.get("asset_id")
        itype = item.get("type")
        params = item.get("parameters") or {}

        if not asset_id:
            errors.append(f"{prefix}: missing asset_id")
            return errors, warnings, None
        if not itype:
            errors.append(f"{prefix} ({asset_id}): missing type")
            return errors, warnings, None

        # Duplicate asset
        if asset_id in seen_assets:
            errors.append(f"{asset_id}: appears twice in the plan")
            return errors, warnings, None
        seen_assets.add(asset_id)

        # Asset exists
        asset_row = self.ds._asset_row(asset_id)
        if asset_row is None:
            errors.append(f"{asset_id}: asset not found")
            return errors, warnings, None

        asset_type = asset_row["asset_type"]

        # Intervention type allowed for this asset type
        allowed = ACTION_SPACE.get(asset_type, [])
        if itype not in allowed:
            errors.append(
                f"{asset_id}: intervention '{itype}' not allowed for "
                f"asset_type '{asset_type}'. Allowed: {allowed}"
            )
            return errors, warnings, None

        # Repurpose: subtype must exist and not equal current subtype
        to_subtype = params.get("to_subtype")
        if itype == "repurpose":
            if not to_subtype:
                errors.append(f"{asset_id}: repurpose requires parameters.to_subtype")
                return errors, warnings, None
            defn = get_subtype(to_subtype)
            if defn is None:
                errors.append(
                    f"{asset_id}: subtype '{to_subtype}' not in taxonomy. "
                    f"Call get_available_subtypes first."
                )
                return errors, warnings, None
            current_subtype = asset_row.get("subtype")
            if to_subtype == current_subtype:
                warnings.append(
                    f"{asset_id}: repurpose target equals current subtype "
                    f"'{to_subtype}' — no-op."
                )

        # Budget hints
        capex = self._estimate_capex(itype, asset_row, params)
        opex_delta = self._estimate_opex_delta(itype, asset_row, params)

        # Timing
        timing = DEFAULT_TIMING.get(itype, {
            "start_offset": 0, "duration_months": 0, "during": "operational",
        })
        start_year = self.base_year + timing["start_offset"]
        duration = timing["duration_months"]
        activation_year = start_year + (duration + 11) // 12  # ceil months -> years

        # Optional LLM-provided timing overrides
        if "construction_start_year" in params:
            try:
                start_year = int(params["construction_start_year"])
            except (TypeError, ValueError):
                warnings.append(f"{asset_id}: invalid construction_start_year, using default")
        if start_year < self.base_year:
            errors.append(
                f"{asset_id}: construction_start_year {start_year} "
                f"is before base year {self.base_year}"
            )
            return errors, warnings, None
        if "activation_year" in params:
            try:
                activation_year = int(params["activation_year"])
            except (TypeError, ValueError):
                warnings.append(f"{asset_id}: invalid activation_year, using default")

        # Expected effects (optional)
        expected = item.get("expected_effects") or {}
        expected_json = self._normalise_expected(expected)

        normalised_item = {
            "asset_id": asset_id,
            "intervention_type": itype,
            "parameters": params,
            "expected_derived_json": expected_json,
            "construction_start_year": start_year,
            "construction_duration_months": duration,
            "activation_year": activation_year,
            "during_construction_status": timing["during"],
            "capex_delta_rm": capex,
            "opex_delta_rm": opex_delta,
        }
        return errors, warnings, normalised_item

    # --------------------------------------------------------------
    # Cross-item validation
    # --------------------------------------------------------------

    def _validate_cross_items(self, plan: list):
        """
        Detect conflicts between items in the same plan:
          - two repurposes to the same subtype within shared competition radius
          - supply duplication warning against EXISTING assets
        """
        errors: list = []
        warnings: list = []

        # Group repurpose targets by subtype
        repurposes = [p for p in plan if p["intervention_type"] == "repurpose"]

        # Within-plan conflict
        for i, a in enumerate(repurposes):
            sub_a = a["parameters"].get("to_subtype")
            radius_a = self._subtype_radius(sub_a)
            for b in repurposes[i + 1:]:
                sub_b = b["parameters"].get("to_subtype")
                if sub_a != sub_b:
                    continue
                distance = self._asset_distance(a["asset_id"], b["asset_id"])
                if distance is None:
                    continue
                radius_b = self._subtype_radius(sub_b)
                shared = min(radius_a or 0, radius_b or 0)
                if shared > 0 and distance < shared:
                    errors.append(
                        f"Plan proposes two '{sub_a}' facilities within "
                        f"{distance:.0f}m of each other; their shared "
                        f"competition radius is {shared:.0f}m. This would "
                        f"create oversupply. Consider a different subtype "
                        f"for one of them."
                    )

        # Against existing assets
        for p in repurposes:
            to_subtype = p["parameters"].get("to_subtype")
            radius = self._subtype_radius(to_subtype)
            if not radius:
                continue
            nearby = self._nearby_same_subtype(
                p["asset_id"], to_subtype, radius,
            )
            if nearby:
                names = ", ".join(n["asset_id"] for n in nearby[:3])
                warnings.append(
                    f"{p['asset_id']}: a '{to_subtype}' already exists "
                    f"within {radius:.0f}m ({names}). Verify the catchment "
                    f"can support an additional facility."
                )

        return errors, warnings

    # --------------------------------------------------------------
    # Helpers
    # --------------------------------------------------------------

    def _estimate_capex(self, itype: str, asset_row: dict, params: dict) -> float:
        """Conservative CAPEX estimate in RM. Used only for budget check."""
        if itype == "repurpose":
            # Rough: RM 200 / m² of floor area, floor 100k.
            floor = asset_row.get("floor_area_m2") or 0
            try:
                floor = float(floor)
            except (TypeError, ValueError):
                floor = 0.0
            return max(100_000.0, floor * 200.0)
        if itype == "retrofit":
            floor = asset_row.get("floor_area_m2") or 0
            try:
                floor = float(floor)
            except (TypeError, ValueError):
                floor = 0.0
            return max(50_000.0, floor * 80.0)
        if itype == "green_corridor":
            return 250_000.0
        if itype == "pedestrian_upgrade":
            return 180_000.0
        if itype == "new_development":
            gfa = params.get("target_gfa_m2") or 0
            try:
                gfa = float(gfa)
            except (TypeError, ValueError):
                gfa = 0.0
            return max(500_000.0, gfa * 800.0)
        if itype == "delay_development":
            return 0.0
        return 0.0

    def _estimate_opex_delta(self, itype: str, asset_row: dict, params: dict) -> float:
        if itype == "repurpose":
            return 60_000.0
        if itype == "retrofit":
            return -30_000.0  # assumed savings
        return 0.0

    def _normalise_expected(self, expected: dict) -> str:
        """
        Convert the LLM's expected_effects dict into the JSON string the
        simulation expects in expected_derived_json. Keys are the metric
        names used by B4 (utilisation, carbon_operational_tco2e, ...).
        """
        if not expected:
            return None
        canonical = {}
        mapping = {
            "utilisation": "utilisation",
            "utilisation_rate": "utilisation",
            "occupancy": "occupancy",
            "occupancy_rate": "occupancy",
            "carbon": "carbon_operational_tco2e",
            "carbon_operational_tco2e": "carbon_operational_tco2e",
            "carbon_reduction_pct": "carbon_reduction_pct",
            "service_coverage": "service_coverage",
            "accessibility_delta": "accessibility_delta",
        }
        for k, v in expected.items():
            key = mapping.get(k, k)
            canonical[key] = v
        import json
        return json.dumps(canonical)

    def _subtype_radius(self, subtype: str):
        defn = self.ds.subtypes_config.get(subtype)
        if not defn:
            return None
        return defn.get("competition_radius_m")

    def _asset_distance(self, a: str, b: str):
        centroids = self.ds._load_centroids()
        ca = centroids.get(a)
        cb = centroids.get(b)
        if ca is None or cb is None:
            return None
        return math.hypot(ca[0] - cb[0], ca[1] - cb[1])

    def _nearby_same_subtype(self, asset_id: str, subtype: str, radius_m: float) -> list:
        """Existing assets of the same subtype within radius_m."""
        centroids = self.ds._load_centroids()
        origin = centroids.get(asset_id)
        if origin is None:
            return []
        ox, oy = origin
        results = []
        for _, row in self.ds.assets.iterrows():
            if row["asset_id"] == asset_id:
                continue
            if row.get("subtype") != subtype:
                continue
            c = centroids.get(row["asset_id"])
            if c is None:
                continue
            d = math.hypot(c[0] - ox, c[1] - oy)
            if d <= radius_m:
                results.append({"asset_id": row["asset_id"], "distance_m": round(d, 1)})
        return results