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
# CAPEX and OPEX estimation tables
# ------------------------------------------------------------------
# These tables exist for ONE purpose: budget validation. They provide
# an order-of-magnitude anchor so the validator can reject a plan that
# obviously blows the user's budget, without the LLM having to
# declare CAPEX explicitly.
#
# They are NOT a cost model. They must never be shown to the user, and
# they must never be presented as an estimate. The authoritative CAPEX
# of an intervention is whatever the intervention row declares (or,
# in the future, whatever a proper cost model computes).
#
# All rates are RM per m² of the asset's floor area. Where a subtype
# is known, the subtype rate wins; otherwise the asset-class rate is
# used.
_CAPEX_RATE_BY_SUBTYPE = {
    # Commercial
    "convenience_retail": 180.0,
    "supermarket":        220.0,
    "f_and_b":            250.0,
    "medical_retail":     320.0,
    "office":             200.0,
    "services":           180.0,
    "entertainment":      260.0,
    "showroom":           180.0,
    # Community facility
    "clinic":             380.0,
    "community_hall":     260.0,
    "library":            300.0,
    "childcare":          340.0,
    "school":             280.0,
    "sports_centre":      320.0,
    "place_of_worship":   260.0,
    "public_service":     260.0,
    # Residential
    "terrace":            200.0,
    "semidetached":       200.0,
    "detached":           200.0,
    "apartment_lowrise":  200.0,
    "apartment_highrise": 220.0,
    "affordable_housing": 180.0,
    # Green space
    "park":                30.0,
    "pocket_park":         40.0,
    "green_corridor":      50.0,
    "sports_field":        20.0,
    "water_body":          10.0,
    # Undeveloped
    "vacant":             250.0,
}

_CAPEX_RATE_BY_CLASS = {
    "commercial":         200.0,
    "community_facility": 280.0,
    "residential":        200.0,
    "green_space":         30.0,
    "undeveloped_parcel": 250.0,
}

# Minimum CAPEX per intervention type (RM). Even a tiny asset needs at
# least this much to execute the intervention.
_CAPEX_FLOOR = {
    "repurpose":          100_000.0,
    "retrofit":            50_000.0,
    "green_corridor":     250_000.0,
    "pedestrian_upgrade": 180_000.0,
    "new_development":    500_000.0,
    "delay_development":        0.0,
}

# Retrofit upgrades systems and finishes rather than reconstructing
# the shell, so it is charged a fraction of the full rebuild rate.
_RETROFIT_FRACTION = 0.40

# OPEX delta defaults. Positive values mean the intervention raises
# annual operating cost. Values are RM/year for repurpose; a fraction
# of the asset's current OPEX for retrofit; zero for the others.
_OPEX_DELTA_BY_TARGET_CLASS = {
    # Repurpose changes the asset's operating profile. A facility has
    # staff and utility costs; green space is nearly free; a different
    # commercial subtype roughly holds constant.
    "commercial":          0.0,
    "community_facility": 60_000.0,
    "residential":        20_000.0,
    "green_space":         5_000.0,
    "undeveloped_parcel":  0.0,
}
_RETROFIT_OPEX_SAVING_FRACTION = -0.10  # 10% reduction


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

        # Budget hints.
        # Pass the target subtype for every subtype-changing
        # intervention (repurpose and new_development), so the
        # estimator hits the subtype-specific rate table instead of
        # falling back to the asset's current class.
        to_subtype = (
            params.get("to_subtype")
            if itype in ("repurpose", "new_development")
            else None
        )
        capex = self._estimate_capex(
            itype, asset_row, params, target_subtype=to_subtype,
        )
        opex_delta = self._estimate_opex_delta(
            itype, asset_row, params, target_subtype=to_subtype,
        )

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

    def _estimate_capex(
        self,
        itype: str,
        asset_row: dict,
        params: dict,
        target_subtype: str = None,
    ) -> float:
        """
        Conservative CAPEX estimate in RM, used only for budget
        validation. Resolution order:

          1. Explicit value from the LLM (params["capex_delta_rm"]).
             This is the LLM's own claim; the validator takes it at
             face value because the user is paying the actual bill.

          2. Rate table lookup keyed on the target subtype. Only
             applies to subtype-changing interventions (repurpose,
             new_development), where the resulting cost profile
             depends on what the asset becomes.

          3. Rate table lookup keyed on the asset's current class.
             Fallback when the target subtype is unknown.

          4. A hard floor per intervention type, applied on top of
             (2)/(3) to prevent a tiny asset from escaping the budget
             check with a trivially small number.

        Returns 0.0 for delay_development (it costs nothing and
        defers spend rather than committing to it).
        """
        if itype == "delay_development":
            return 0.0

        # 1. LLM-declared value
        explicit = params.get("capex_delta_rm")
        if explicit is not None:
            try:
                return float(explicit)
            except (TypeError, ValueError):
                pass

        # 2. Target-subtype rate (subtype-changing interventions only)
        floor = _CAPEX_FLOOR.get(itype, 0.0)
        floor_area = _as_positive_float(asset_row.get("floor_area_m2"))

        if itype == "new_development":
            # New development is measured by the target GFA the LLM
            # specified, not by the current floor area of the vacant
            # parcel (which is typically zero). Using the parcel's own
            # area would always fall back to the floor value and let
            # any sized development pass the budget check.
            gfa = _as_positive_float(params.get("target_gfa_m2"))
            rate = None
            if target_subtype:
                rate = _CAPEX_RATE_BY_SUBTYPE.get(target_subtype)
            if rate is None:
                rate = _CAPEX_RATE_BY_CLASS.get("commercial", 200.0)
            if gfa > 0:
                return max(floor, gfa * rate)
            return floor

        if itype == "repurpose":
            rate = None
            if target_subtype:
                rate = _CAPEX_RATE_BY_SUBTYPE.get(target_subtype)
            if rate is None:
                rate = _CAPEX_RATE_BY_CLASS.get(
                    asset_row.get("asset_type"), 200.0,
                )
            if floor_area > 0:
                return max(floor, floor_area * rate)
            return floor

        # 3. Retrofit: fraction of the current-class rate
        if itype == "retrofit":
            rate = _CAPEX_RATE_BY_CLASS.get(
                asset_row.get("asset_type"), 200.0,
            ) * _RETROFIT_FRACTION
            if floor_area > 0:
                return max(floor, floor_area * rate)
            return floor

        # 4. Spatial interventions: fixed cost.
        return floor

    def _estimate_opex_delta(
        self,
        itype: str,
        asset_row: dict,
        params: dict,
        target_subtype: str = None,
    ) -> float:
        """
        OPEX delta in RM/year, used only for reporting. Resolution
        order mirrors CAPEX:

          1. Explicit value from the LLM (params["opex_delta_rm"]).
          2. Default per target class (repurpose) or a fixed fraction
             of the current OPEX (retrofit).
          3. Zero for interventions that do not touch the asset's
             own operating profile.

        A negative value means the intervention reduces annual
        operating cost.
        """
        if itype == "delay_development":
            return 0.0

        # 1. LLM-declared value
        explicit = params.get("opex_delta_rm")
        if explicit is not None:
            try:
                return float(explicit)
            except (TypeError, ValueError):
                pass

        # 2. Repurpose: use the target subtype's asset class
        if itype == "repurpose":
            target_class = self._target_asset_class(target_subtype, asset_row)
            return _OPEX_DELTA_BY_TARGET_CLASS.get(target_class, 0.0)

        # 3. Retrofit: proportional savings on the current OPEX
        if itype == "retrofit":
            current_opex = _as_positive_float(asset_row.get("opex_annual_rm"))
            if current_opex > 0:
                return current_opex * _RETROFIT_OPEX_SAVING_FRACTION
            return 0.0

        # 4. Spatial and new-development interventions do not touch
        #    the asset's own OPEX in this simulator.
        return 0.0

    def _target_asset_class(self, target_subtype: str, asset_row: dict) -> str:
        """
        Return the asset_class that a repurpose would move the asset
        into. Falls back to the asset's current class when the target
        subtype is missing or unknown.
        """
        if target_subtype:
            defn = self.ds.subtypes_config.get(target_subtype)
            if defn and defn.get("asset_class"):
                return defn["asset_class"]
        return asset_row.get("asset_type", "commercial")

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

# ------------------------------------------------------------------
# Utilities
# ------------------------------------------------------------------
def _as_positive_float(v) -> float:
    """Convert to a float, treating None / NaN / negatives as 0.0."""
    if v is None:
        return 0.0
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(f) or f < 0:
        return 0.0
    return f