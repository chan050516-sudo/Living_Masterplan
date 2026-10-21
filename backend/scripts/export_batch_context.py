"""Export baseline data and LLM context for a list of assets.

Usage:
    python backend/scripts/export_batch_context.py BLD-0568 P-VAC-06 P-VAC-07
"""

import sys
import json
import logging
from pathlib import Path

# Ensure backend.app can be imported
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.llm.tool_service import TownshipDataSource
from app.llm.context_builder import build_context_pack

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

def main():
    if len(sys.argv) < 2:
        log.error("Usage: python backend/scripts/export_batch_context.py <ASSET_ID_1> <ASSET_ID_2> ...")
        return

    target_ids = sys.argv[1:]
    repo_root = Path(__file__).resolve().parents[2]
    
    log.info(f"Loading TownshipDataSource for targets: {target_ids}...")
    ds = TownshipDataSource(repo_root, year=2026)

    def clean(d):
        if not isinstance(d, dict): return d
        out = {}
        for k, v in d.items():
            if hasattr(v, 'item'): v = v.item()
            if isinstance(v, float) and (v != v): v = None # NaN check
            out[k] = v
        return out

    real_baselines = {}
    for target_id in target_ids:
        log.info(f"Extracting real asset profile for {target_id}...")
        asset_state = ds._asset_row(target_id)
        if not asset_state:
            log.error(f"Asset {target_id} not found!")
            continue
            
        metric_state = ds._metric_row(target_id, 2026) or {}
        deadspace = ds.deadspace.get(target_id, {})
        
        real_baselines[target_id] = {
            "asset_row": clean(asset_state),
            "metric_row": clean(metric_state),
            "deadspace": deadspace,
        }

    log.info(f"Building context pack for {target_ids}...")
    fake_intent = {
        "target_asset_ids": target_ids,
        "objective": "balanced",
        "constraints": {"capex_limit": 5000000},
        "question_text": "Compare these assets and find the best catalytic synergy."
    }
    
    context_pack = build_context_pack(fake_intent, ds)

    out_file = repo_root / f"debug_batch_{'_'.join(target_ids)}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({
            "real_baselines": real_baselines,
            "llm_context": context_pack
        }, f, indent=2, ensure_ascii=False)
        
    log.info(f"✅ Success! Exported to: {out_file}")
    log.info("Please copy the contents of this file and send it to me.")

if __name__ == "__main__":
    main()