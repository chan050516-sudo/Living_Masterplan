"""Run Phase 3 — B6 Deadspace Detection (flag-based)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.deadspace.engine import (
    detect_all_deadspace,
    write_deadspace_json,
    deadspace_list,
)


def _fmt(v, decimals=2):
    if v is None:
        return "-"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if abs(f) >= 1000:
        return f"{f:,.0f}"
    return f"{round(f, decimals)}"


def _section(title, width=72):
    print("\n" + "=" * width)
    print(f"  {title}")
    print("=" * width)


def main():
    repo_root = Path(__file__).resolve().parents[2]
    year = 2026

    print(f"\nRunning Phase 3 (B6) for year {year}...")
    all_records = detect_all_deadspace(repo_root=repo_root, year=year)

    _section(f"DEADSPACE — ALL ASSETS — {year}")
    header = f"  {'Asset':<8} {'Status':<26} {'Flags':>5}  {'Urgency':>8}"
    print(header)
    print("  " + "-" * len(header))
    for r in all_records:
        print(
            f"  {r['asset_id']:<8} {r['status']:<26} "
            f"{len(r['flags']):>5}  {_fmt(r['urgency_index'], 1):>8}"
        )

    for r in all_records:
        _section(f"{r['asset_id']} — {r['status'].upper()}")
        print(f"  Flags: {', '.join(r['flags']) or '(none)'}")
        print(f"  Urgency index: {_fmt(r['urgency_index'], 1)}")

        if r["contributing_factors"]:
            print("  Contributing factors:")
            for f in r["contributing_factors"]:
                pct = round(f["contribution"] * 100, 1)
                bar = "#" * int(pct / 5)
                print(f"     {f['factor']:<32} {pct:>5}%  {bar}")

        if r["evidence"]:
            print("  Evidence:")
            for e in r["evidence"]:
                print(f"     - {e}")

    out = write_deadspace_json(all_records, repo_root=repo_root, year=year)

    _section("DEADSPACE LIST (sorted by urgency, descending)")
    for r in deadspace_list(all_records):
        print(
            f"  {r['asset_id']:<8} {r['status']:<26} "
            f"urgency={_fmt(r['urgency_index'], 1)}"
        )

    print("\n" + "=" * 72)
    print(f"  Wrote deadspace JSON: {out}")
    print("=" * 72 + "\n")


if __name__ == "__main__":
    main()