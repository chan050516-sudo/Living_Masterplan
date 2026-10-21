"""Export real baseline data and LLM context for a specific asset.

Usage:
    python backend/scripts/export_context.py BLD-0183
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
    target_id = sys.argv[1] if len(sys.argv) > 1 else "BLD-0183"
    repo_root = Path(__file__).resolve().parents[2]
    
    log.info(f"Loading TownshipDataSource for {target_id}...")
    ds = TownshipDataSource(repo_root, year=2026)

    # 1. 提取真实的资产画像（用于 AssetPanel）
    log.info(f"Extracting real asset profile for {target_id}...")
    asset_state = ds._asset_row(target_id)
    if not asset_state:
        log.error(f"Asset {target_id} not found!")
        return
        
    metric_state = ds._metric_row(target_id, 2026) or {}
    deadspace = ds.deadspace.get(target_id, {})
    
    # 清理 NaN 和不可序列化的对象
    def clean(d):
        if not isinstance(d, dict): return d
        out = {}
        for k, v in d.items():
            if hasattr(v, 'item'): v = v.item()
            if isinstance(v, float) and (v != v): v = None # NaN check
            out[k] = v
        return out

    real_baseline = {
        "asset_id": target_id,
        "asset_row": clean(asset_state),
        "metric_row": clean(metric_state),
        "deadspace": deadspace,
    }

    # 2. 提取准备送给 LLM 的上下文
    log.info(f"Building context pack for {target_id}...")
    fake_intent = {
        "target_asset_ids": [target_id],
        "objective": "balanced",
        "constraints": {"capex_limit": 2000000, "no_demolition": True},
        "question_text": "Review the attached feasibility summary. We need to stop the financial bleeding immediately."
    }
    
    context_pack = build_context_pack(fake_intent, ds)
    # 只保留该资产的 target block
    target_block = context_pack["targets"][0] if context_pack.get("targets") else {}

    # 3. 将结果写入文件
    out_file = repo_root / f"debug_{target_id}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({
            "real_baseline": real_baseline,
            "llm_context": target_block
        }, f, indent=2, ensure_ascii=False)
        
    log.info(f"✅ Success! Exported to: {out_file}")
    log.info("Please copy the contents of this file and send it to me.")

if __name__ == "__main__":
    main()