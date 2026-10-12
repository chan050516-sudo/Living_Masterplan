"""The only place the LLM layer touches David's simulator."""
import json
import shutil
import tempfile
from pathlib import Path

import pandas as pd

from ..config import load_paths
from ..simulation.engine import simulate_scenario
from .schemas import Option

ROOT = Path(__file__).resolve().parents[3]


def _base() -> Path:
    return ROOT / load_paths()["base"]


def list_assets() -> list[dict]:
    df = pd.read_csv(_base() / "business" / "assets.csv")
    return json.loads(df.to_json(orient="records"))


def get_asset_state(asset_id: str) -> dict | None:
    df = pd.read_csv(_base() / "business" / "assets.csv")
    row = df[df["asset_id"] == asset_id]
    return None if row.empty else json.loads(row.to_json(orient="records"))[0]


def get_asset_metrics(asset_id: str, year: int | None = None) -> list[dict]:
    df = pd.read_csv(_base() / "business" / "asset_metrics.csv")
    df = df[df["asset_id"] == asset_id]
    if year is not None and "year" in df.columns:
        df = df[df["year"] == year]
    return json.loads(df.to_json(orient="records"))


def simulate_option(option: Option, years: list[int] | None = None) -> dict:
    """Run one LLM option through David's engine without touching the real mock data."""
    scenario_id = f"SC-LLM-{option.option_id}"
    rel = load_paths()["base"]
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        shutil.copytree(ROOT / rel, tmp_root / rel)
        csv_path = tmp_root / rel / "business" / "interventions.csv"
        df = pd.read_csv(csv_path)
        rows = [i.to_row(scenario_id) for i in option.interventions]
        df = pd.concat([df, pd.DataFrame(rows)], ignore_index=True)
        df.to_csv(csv_path, index=False)
        return simulate_scenario(scenario_id, repo_root=tmp_root, years=years)