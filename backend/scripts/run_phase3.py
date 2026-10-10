"""Run Phase 3 — B6 Deadspace Detection."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.deadspace.engine import detect_all_deadspace, write_deadspace_json, deadspace_list


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
    header = f"  {'Asset':<8} {'Status':<26} {'Score':>6}  {'L1':<3} {'L2':<3} {'L3':<3}"
    print(header)
    print("  " + "-" * len(header))
    for r in all_records:
        l1 = "Y" if r["layer1"]["triggered"] else "-"
        l2 = "Y" if r["layer2"]["triggered"] else "-"
        l3 = "Y" if r["layer3"]["actionable"] else "-"
        print(f"  {r['asset_id']:<8} {r['status']:<26} "
              f"{_fmt(r['score'], 1):>6}  {l1:<3} {l2:<3} {l3:<3}")

    # Detail
    for r in all_records:
        _section(f"{r['asset_id']} — {r['status'].upper()}")

        print(f"  Score: {_fmt(r['score'], 2)}")
        print(f"  Layer 1 (Underperformance): {'YES' if r['layer1']['triggered'] else 'no'}")
        if r["layer1"]["reasons"]:
            for reason in r["layer1"]["reasons"]:
                print(f"     - {reason}")

        print(f"  Layer 2 (Low Value Realisation): {'YES' if r['layer2']['triggered'] else 'no'}")
        if r["layer2"]["reasons"]:
            for reason in r["layer2"]["reasons"]:
                print(f"     - {reason}")

        print(f"  Layer 3 (Actionability): {'YES' if r['layer3']['actionable'] else 'no'}")
        if r["layer3"]["candidate_interventions"]:
            print(f"     candidates: {', '.join(r['layer3']['candidate_interventions'])}")

        if r["contributing_factors"]:
            print("  Contributing factors:")
            for f in r["contributing_factors"]:
                pct = round(f["contribution"] * 100, 1)
                bar = "#" * int(pct / 5)
                print(f"     {f['factor']:<28} {pct:>5}%  {bar}")

        if r["evidence"]:
            print("  Evidence:")
            for e in r["evidence"]:
                print(f"     - {e}")

    # Write
    out = write_deadspace_json(all_records, repo_root=repo_root, year=year)

    _section("DEADSPACE LIST (non-healthy only)")
    for r in deadspace_list(all_records):
        print(f"  {r['asset_id']:<8} {r['status']:<26} score={_fmt(r['score'], 1)}")

    print("\n" + "=" * 72)
    print(f"  Wrote deadspace JSON: {out}")
    print("=" * 72 + "\n")


if __name__ == "__main__":
    main()