"""Map (asset_type, layer triggers) to a final deadspace status enum."""


def decide_status(asset_type, layer1, layer2, layer3, authority=None):
    """
    Decide the final status for a single asset.

    Priority order:
      1. No layer triggered -> healthy
      2. No actionable intervention -> monitor
      3. Type-specific classification

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
      The full l1 AND l2 requirement still applies to slow declines,
      where the asset is still functional and the operator has time.

    P2-1 fix — `actionable` is a deprecated alias for
      `has_legal_actions`, which is True for every asset type (all
      five classes appear in deadspace.layer3.ACTION_SPACE). The
      previous `if not l3: return "monitor"` was therefore dead
      code. The semantically correct signal is
      `candidate_interventions`: empty when neither layer fired,
      populated when the diagnosis indicates an intervention.
      With the layer3 flag-filter added, the field is now a
      filtered subset; the layer3 fallback keeps it non-empty for
      any diagnosed asset whose legal set is itself non-empty.

    Deepening (②) — community_facility now requires L1 AND L2.

      Previously any single L1 flag (`low_utilisation`,
      `high_uhi_exposure`, `high_stranded_carbon`) pushed the
      facility into "underperforming_facility". A small facility
      serving a small catchment has low utilisation by
      construction, not by failure. Requiring L2
      (`insufficient_coverage`) means the diagnosis actually has
      to demonstrate value failure, not just below-benchmark
      operation.

      `rapid_decline` is still allowed to fire alone. A facility
      losing 20%+ utilisation in one year is failing right now
      regardless of where its coverage sits. Note that
      `rapid_decline` implies `l1` (it is itself an L1 reason),
      so the correct expression is `(l1 and l2) or has_rapid_decline`,
      NOT `l1 and (l2 or has_rapid_decline)` — the latter
      collapses to `l1` when rapid_decline is present.
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

    if asset_type == "commercial":
        # Rapid decline plus any flagged signal = deadspace candidate.
        # Slow decline still requires both layers.
        if has_rapid_decline or (l1 and l2):
            return "deadspace_candidate"
        return "monitor"

    if asset_type == "community_facility":
        # Deepening (②): normal underperformance requires BOTH
        # layers (below benchmark AND value not realised).
        # rapid_decline remains an emergency override.
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
            # Same rule as commercial: rapid decline + any signal
            # crosses into deadspace_candidate. Slow decline still
            # requires both layers.
            if has_rapid_decline or (l1 and l2):
                return "deadspace_candidate"
            return "monitor"
        return "monitor"

    return "monitor"