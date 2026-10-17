"""Validate Phase 3 (B6 deadspace detection) output quality.

Run from repo root:
    python backend/scripts/validate_phase3.py

Checks:
  1. Completeness — every asset has a record.
  2. Status distribution — no single status dominates spuriously.
  3. Flag distribution — every flag's trigger count, plus
     detection of flags not registered in FLAG_WEIGHTS.
  4. Urgency distribution — percentiles and top-15.
  5. Per-subtype mix flags — verify subtype_mix_dead / _low
     appear (or explain why not).
  6. Internal consistency — flags == layer1.reasons + layer2.reasons;
     contributing_factors sums to ~1.0 when flags exist.
  7. Special cases — unsold residential, anchor deadspace.
"""

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from app.config import load_paths
from app.deadspace.urgency import FLAG_WEIGHTS


def _hdr(title):
    print("\n" + "=" * 72)
    print(f"  {title}")
    print("=" * 72)


def _ok(msg):
    print(f"[ OK ] {msg}")


def _warn(msg):
    print(f"[WARN] {msg}")


def _fail(msg):
    print(f"[FAIL] {msg}")
    raise SystemExit(1)


def main():
    repo_root = Path(__file__).resolve().parents[2]
    paths = load_paths()
    base = repo_root / paths["base"]

    deadspace_path = base / "business" / "deadspace_2026.json"
    assets_path = base / "business" / "assets.csv"
    enriched_path = base / "business" / "asset_metrics_enriched.csv"

    for p in (deadspace_path, assets_path, enriched_path):
        if not p.exists():
            _fail(f"file missing: {p}")

    with open(deadspace_path, encoding="utf-8") as f:
        records = json.load(f)

    assets = pd.read_csv(assets_path)
    enriched = pd.read_csv(enriched_path)
    current = enriched[enriched["year"] == 2026]

    # ------------------------------------------------------------------
    # 1. Completeness
    # ------------------------------------------------------------------
    _hdr("1. Completeness")
    print(f"  assets.csv:          {len(assets)}")
    print(f"  deadspace records:   {len(records)}")

    record_ids = {r["asset_id"] for r in records}
    asset_ids = set(assets["asset_id"].astype(str))
    missing = asset_ids - record_ids
    extra = record_ids - asset_ids

    if missing:
        _fail(f"{len(missing)} assets have no deadspace record: "
              f"{list(missing)[:5]}")
    if extra:
        _warn(f"{len(extra)} deadspace records have no asset: "
              f"{list(extra)[:5]}")
    _ok(f"all {len(asset_ids)} assets have records")

    # ------------------------------------------------------------------
    # 2. Status distribution
    # ------------------------------------------------------------------
    _hdr("2. Status distribution")
    status_counts = Counter(r["status"] for r in records)
    for s, n in status_counts.most_common():
        pct = 100.0 * n / len(records)
        print(f"  {s:<30} {n:>4}  ({pct:>5.1f}%)")

    if status_counts.get("deadspace_candidate", 0) == 0:
        _fail("no deadspace_candidate — detection produced nothing")
    if status_counts.get("healthy", 0) == 0:
        _warn("no healthy assets — every asset has some flag")
    _ok(f"{status_counts.get('deadspace_candidate', 0)} "
        f"deadspace candidates found")

    # ------------------------------------------------------------------
    # 3. Flag distribution
    # ------------------------------------------------------------------
    _hdr("3. Flag distribution")
    flag_counts = Counter()
    for r in records:
        for f in r["flags"]:
            flag_counts[f] += 1

    print(f"  {'flag':<45} {'count':>6}  {'weight':>7}")
    print("  " + "-" * 62)

    undefined_flags = []
    for flag, n in flag_counts.most_common():
        weight = FLAG_WEIGHTS.get(flag)
        if weight is None:
            undefined_flags.append(flag)
            weight_str = "MISSING"
        else:
            weight_str = f"{weight}"
        print(f"  {flag:<45} {n:>6}  {weight_str:>7}")

    # Flags defined but never triggered — could mean thresholds too
    # tight, or the check simply doesn't apply to this data.
    defined_flags = set(FLAG_WEIGHTS.keys())
    triggered_flags = set(flag_counts.keys())
    never_triggered = sorted(defined_flags - triggered_flags)
    if never_triggered:
        _warn(f"{len(never_triggered)} flags defined but never triggered: "
              f"{never_triggered}")

    if undefined_flags:
        _fail(f"flags not in FLAG_WEIGHTS: {undefined_flags}")
    _ok(f"{len(triggered_flags)} distinct flags, all in FLAG_WEIGHTS")

    # ------------------------------------------------------------------
    # 4. Urgency distribution
    # ------------------------------------------------------------------
    _hdr("4. Urgency distribution")
    urgencies = sorted(r["urgency_index"] for r in records)
    n = len(urgencies)
    if n > 0:
        print(f"  min:    {urgencies[0]:.2f}")
        print(f"  p25:    {urgencies[n // 4]:.2f}")
        print(f"  p50:    {urgencies[n // 2]:.2f}")
        print(f"  p75:    {urgencies[3 * n // 4]:.2f}")
        print(f"  p90:    {urgencies[9 * n // 10]:.2f}")
        print(f"  max:    {urgencies[-1]:.2f}")
        if urgencies[-1] == 0.0:
            _fail("max urgency is 0 — nothing is flagged")

    # ------------------------------------------------------------------
    # 5. Per-subtype mix flags
    # ------------------------------------------------------------------
    _hdr("5. Per-subtype mix flags (Phase B.2)")
    mix_dead = [r for r in records if "subtype_mix_dead" in r["flags"]]
    mix_low = [r for r in records if "subtype_mix_low" in r["flags"]]

    print(f"  subtype_mix_dead: {len(mix_dead)}")
    print(f"  subtype_mix_low:  {len(mix_low)}")

    if len(mix_dead) == 0 and len(mix_low) == 0:
        _warn("no subtype mix flags fired. Commercial unit mixes in "
              "this dataset may all have healthy subtypes, or the "
              "per-subtype occupancy fell within expected range.")
    else:
        for r in (mix_dead + mix_low)[:5]:
            print(f"    {r['asset_id']}  "
                  f"status={r['status']}  "
                  f"urgency={r['urgency_index']:.1f}")

    # ------------------------------------------------------------------
    # 6. Internal consistency
    # ------------------------------------------------------------------
    _hdr("6. Internal consistency")

    flag_mismatch = []
    factor_sum_bad = []
    for r in records:
        combined = (
            list(r.get("layer1", {}).get("reasons", []))
            + list(r.get("layer2", {}).get("reasons", []))
        )
        if sorted(combined) != sorted(r["flags"]):
            flag_mismatch.append(r["asset_id"])

        if r["flags"]:
            contrib_sum = sum(
                f["contribution"] for f in r.get("contributing_factors", [])
            )
            if abs(contrib_sum - 1.0) > 0.01:
                factor_sum_bad.append((r["asset_id"], contrib_sum))

    if flag_mismatch:
        _fail(f"{len(flag_mismatch)} records have flags != l1+l2 reasons: "
              f"{flag_mismatch[:5]}")
    _ok("flags == layer1.reasons + layer2.reasons for every record")

    if factor_sum_bad:
        _warn(f"{len(factor_sum_bad)} records have contributing_factors "
              f"sum != 1.0: {factor_sum_bad[:5]}")
    else:
        _ok("contributing_factors sum to 1.0")

    # ------------------------------------------------------------------
    # 7. Special cases
    # ------------------------------------------------------------------
    _hdr("7. Special cases")

    # Unsold residential: should be deadspace_candidate or monitor
    unsold = assets[
        (assets["asset_type"] == "residential")
        & (assets["developer_held_units"] > 0)
    ]["asset_id"].astype(str).tolist()

    unsold_records = [r for r in records if r["asset_id"] in unsold]
    if unsold_records:
        statuses = Counter(r["status"] for r in unsold_records)
        print(f"  Unsold residential ({len(unsold_records)}):")
        for s, n in statuses.most_common():
            print(f"    {s}: {n}")
        if statuses.get("deadspace_candidate", 0) == 0:
            _warn("no unsold residential reaches deadspace_candidate. "
                  "Check layer2 built_value_not_realized and "
                  "developer_held authority.")
    else:
        print("  (no unsold residential — skipped)")

    # Subtype mix dead commercial: what status?
    if mix_dead:
        statuses = Counter(r["status"] for r in mix_dead)
        print(f"\n  Subtype-mix-dead commercial ({len(mix_dead)}):")
        for s, n in statuses.most_common():
            print(f"    {s}: {n}")

    # Top 15 deadspace list
    _hdr("8. Top 15 by urgency (non-healthy)")
    top = sorted(
        [r for r in records if r["status"] != "healthy"],
        key=lambda r: r["urgency_index"],
        reverse=True,
    )[:15]
    print(f"  {'asset_id':<14} {'status':<26} {'urgency':>8}  "
          f"{'flags':>5}  top_flag")
    print("  " + "-" * 78)
    for r in top:
        top_flag = r["flags"][0] if r["flags"] else ""
        if r.get("contributing_factors"):
            top_flag = r["contributing_factors"][0]["factor"]
        print(f"  {r['asset_id']:<14} {r['status']:<26} "
              f"{r['urgency_index']:>8.1f}  "
              f"{len(r['flags']):>5}  {top_flag}")

    print("\n" + "=" * 72)
    print("  Phase 3 validation complete.")
    print("=" * 72 + "\n")


if __name__ == "__main__":
    main()