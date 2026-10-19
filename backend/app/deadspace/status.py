"""Map (asset_type, layer triggers) to a final deadspace status enum."""

import math


# ------------------------------------------------------------------
# Ramp-up grace period
# ------------------------------------------------------------------
# A newly-delivered asset is not deadspace just because occupancy
# starts low. Real townships have a 1-3 year ramp-up window where
# tenants / residents are still arriving. The size of that window
# depends on the asset class.
#
# During the grace window, the asset is classified "monitor" even
# when both layers fire — UNLESS a hard-failure flag is present.
# That preserves the ability to catch genuine early failure
# (rapid decline, recent crash) while fixing the systematic
# over-classification of "not yet full" new stock as deadspace.
#
# zero-grace classes (green_space, undeveloped_parcel) never enter
# this branch: their occupancy concept does not apply.
_RAMP_UP_GRACE_YEARS = {
    "residential":         3,   # developer sell-off usually 2-3 yrs
    "commercial":          2,   # tenant fill-up 1-2 yrs
    "community_facility":  3,   # residents discover a new facility
    "green_space":         0,
    "undeveloped_parcel":  0,
}

# Flags that cancel the ramp-up grace unconditionally. A new asset
# whose occupancy has collapsed in a single year is failing NOW,
# not ramping. `recent_failure` is normalised to `rapid_decline`
# by B3's `_check_trajectory`, so it appears here under that name.
_HARD_FAILURE_FLAGS = frozenset({
    "rapid_decline",
})


def _is_in_ramp_up_window(asset_type, completion_year, base_year):
    """
    True if the asset is inside its ramp-up grace window.

    Missing / unparseable completion_year returns False — we cannot
    prove the asset is new, so we do not exempt it.
    """
    if completion_year is None:
        return False
    try:
        if isinstance(completion_year, float) and math.isnan(completion_year):
            return False
    except (TypeError, ValueError):
        pass
    try:
        age = int(base_year) - int(completion_year)
    except (TypeError, ValueError):
        return False
    if age < 0:
        return False
    grace = _RAMP_UP_GRACE_YEARS.get(asset_type, 0)
    if grace <= 0:
        return False
    return age < grace


def decide_status(asset_type, layer1, layer2, layer3, authority=None,
                  completion_year=None, base_year=2026):
    """
    Decide the final status for a single asset.

    Priority order:
      1. No layer triggered -> healthy
      2. No actionable intervention -> monitor
      3. Ramp-up grace (new asset, no hard-failure flag) -> monitor
      4. Type-specific classification

    Phase 15 — authority-aware classification:
      - residential + sold / advisory    -> monitor (owner-occupied)
      - residential + developer_held     -> deadspace_candidate if both
                                            layers trigger (built but
                                            unsold)
      - green_space is NEVER deadspace (intrinsic ecological value)

    Phase B.3 — rapid_decline override.
      A commercial or developer-held residential asset with a
      rapid_decline trajectory is failing RIGHT NOW. Requiring layer2
      confirmation would postpone the intervention by a full year —
      exactly when postponement is most expensive. Rapid decline
      plus ANY snapshot flag is sufficient for deadspace_candidate.

    P2-1 fix — `actionable` is a deprecated alias for
      `has_legal_actions`, which is True for every asset type.
      `candidate_interventions` is the semantically correct signal.

    Deepening (③) — community_facility now requires L1 AND L2.
      Previously any L1 flag (`low_utilisation`, `high_uhi_exposure`,
      `high_stranded_carbon`) pushed the facility into
      "underperforming_facility". A small facility serving a small
      catchment has low utilisation by construction, not by failure.
      Requiring L2 (`insufficient_coverage`) means the diagnosis
      actually has to demonstrate value failure. `rapid_decline`
      remains an emergency override.

    Ramp-up exemption:
      New assets inside their grace window are held at "monitor"
      even when L1 and L2 both fire. This prevents the systematic
      over-classification of developer-held unsold units (age 1-2
      with 0% occupancy by definition) as deadspace. Hard-failure
      flags (rapid_decline) override the grace so genuine early
      failure still surfaces.
    """
    l1 = layer1["triggered"]
    l2 = layer2["triggered"]
    l3 = bool(layer3.get("candidate_interventions"))

    if not (l1 or l2):
        return "healthy"

    if not l3:
        return "monitor"

    reasons = layer1.get("reasons", [])
    has_rapid_decline = "rapid_decline" in reasons

    # ---- Ramp-up exemption ----
    # Applies to commercial / residential / community_facility only.
    # A new asset with no hard-failure signal is in a normal
    # transition, not a failure state.
    if _is_in_ramp_up_window(asset_type, completion_year, base_year):
        all_reasons = (
            list(reasons)
            + list(layer2.get("reasons", []))
        )
        if not (set(all_reasons) & _HARD_FAILURE_FLAGS):
            return "monitor"

    # ---- Type-specific classification ----
    if asset_type == "commercial":
        if has_rapid_decline or (l1 and l2):
            return "deadspace_candidate"
        return "monitor"

    if asset_type == "community_facility":
        if (l1 and l2) or has_rapid_decline:
            return "underperforming_facility"
        return "monitor"

    if asset_type == "undeveloped_parcel":
        if l1 or l2:
            return "development_risk"
        return "monitor"

    if asset_type == "green_space":
        if l1 or l2:
            return "improvement_opportunity"
        return "monitor"

    if asset_type == "residential":
        if authority == "full_control":
            if has_rapid_decline or (l1 and l2):
                return "deadspace_candidate"
            return "monitor"
        return "monitor"

    return "monitor"