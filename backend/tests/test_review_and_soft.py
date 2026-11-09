"""Backend review fixes (10 Nov 2026) and soft interventions."""

import json
import math
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString, Polygon

from app.deadspace.layer3 import ACTION_SPACE, classify_by_authority
from app.simulation import soft
from app.simulation.spatial import add_access_link, asset_geometry

PROMPTS = Path(__file__).resolve().parents[1] / "app" / "llm" / "prompts"
CRS = "EPSG:32647"


def _square(x, y, s=10):
    return Polygon([(x, y), (x + s, y), (x + s, y + s), (x, y + s)])


# ------------------------------------------------------------------
# Issue 2 — assets that share a parcel can be located
# ------------------------------------------------------------------

def test_asset_on_shared_parcel_resolves_through_parcel_id():
    parcels = gpd.GeoDataFrame(
        {"parcel_id": ["P1"], "asset_id": ["A"]},
        geometry=[_square(0, 0)], crs=CRS,
    )
    assets = pd.DataFrame({"asset_id": ["A", "B"], "parcel_id": ["P1", "P1"]})
    assert asset_geometry("A", parcels, assets) is not None
    assert asset_geometry("B", parcels, assets) is not None   # was None
    assert asset_geometry("B", parcels) is None               # no asset table


# ------------------------------------------------------------------
# Issue 3 — a walkway can add a short link across a barrier
# ------------------------------------------------------------------

def _net(edges):
    rows = []
    for i, (u, v, a, b) in enumerate(edges):
        line = LineString([a, b])
        rows.append({"edge_id": f"E{i}", "edge_type": "footway", "from_node": u,
                     "to_node": v, "length_m": line.length,
                     "canopy_coverage_ratio": 0.0, "geometry": line})
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=CRS)


def test_new_link_closes_a_detour():
    # Shop at the origin. Node "far" is 60 m away in a straight line,
    # but the streets go round a 1 km loop to reach it.
    net = _net([
        ("s", "w1", (0, 0), (0, 500)),
        ("w1", "w2", (0, 500), (60, 500)),
        ("w2", "far", (60, 500), (60, 0)),
    ])
    parcels = gpd.GeoDataFrame({"parcel_id": ["P"], "asset_id": ["SHOP"]},
                               geometry=[_square(-5, -5)], crs=CRS)
    out = add_access_link(net, {"intervention_id": "I1", "target_asset_id": "SHOP"},
                          {"new_link": True}, parcels_gdf=parcels)
    assert len(out) == len(net) + 1
    link = out.iloc[-1]
    assert {link["from_node"], link["to_node"]} == {"s", "far"}
    assert link["length_m"] == pytest.approx(60, abs=1)


def test_no_link_when_streets_are_direct():
    net = _net([("s", "far", (0, 0), (60, 0))])
    parcels = gpd.GeoDataFrame({"parcel_id": ["P"], "asset_id": ["SHOP"]},
                               geometry=[_square(-5, -5)], crs=CRS)
    out = add_access_link(net, {"intervention_id": "I1", "target_asset_id": "SHOP"},
                          {"new_link": True}, parcels_gdf=parcels)
    assert len(out) == len(net)


# ------------------------------------------------------------------
# Soft interventions
# ------------------------------------------------------------------

def test_soft_types_are_legal_and_collaborative_on_sold_shops():
    assert {"tenant_matching", "tactical_placemaking"} <= set(ACTION_SPACE["commercial"])
    split = classify_by_authority("commercial", "advisory")
    assert "tenant_matching" in split["collaborative"]
    assert "tactical_placemaking" in split["collaborative"]
    assert "repurpose" in split["recommendation_only"]
    assert "tenant_matching" in classify_by_authority("commercial", "full_control")["executable"]


def test_markov_occupancy_moves_towards_benchmark():
    assert soft.matched_occupancy(0.05, 0.85, 0.5, 0) == pytest.approx(0.05)
    one = soft.matched_occupancy(0.05, 0.85, 0.5, 1)
    two = soft.matched_occupancy(0.05, 0.85, 0.5, 2)
    assert one == pytest.approx(0.45)
    assert 0.45 < two < 0.85


def test_success_probability_is_bounded():
    assert soft.success_probability(0.0, 0.0) == 0.25
    assert soft.success_probability(1.0, 1.0) == 0.90
    assert 0.1 <= soft.success_probability(0.5) <= 0.9


def test_suitability_prefers_demand_and_room():
    assets = pd.DataFrame({
        "asset_id": ["T", "R1", "R2", "R3", "R4"],
        "subtype": ["services", "cafe", "cafe", "cafe", "cafe"],
        "asset_type": ["commercial"] * 5,
    })
    points = {a: (0.0, float(i)) for i, a in enumerate(assets["asset_id"])}
    cfg = {
        "cafe": {"asset_class": "commercial", "competition_radius_m": 300},
        "kopitiam": {"asset_class": "commercial", "competition_radius_m": 300},
        "services": {"asset_class": "commercial", "competition_radius_m": 300},
        "office": {"asset_class": "commercial", "competition_radius_m": 300},
    }
    row = {"dsr_by_subtype_json": json.dumps({"cafe": 0.2, "kopitiam": 0.2, "office": 5.0})}
    ranking = soft.suitability_ranking("T", row, assets, points, cfg)
    names = [r["subtype"] for r in ranking]
    assert "office" not in names and "services" not in names   # not a shoplot / current
    assert names[0] == "kopitiam"   # same demand as cafe, but no rivals nearby
    assert ranking[0]["demand"] == 1.0  # scaled against shoplot candidates only


def test_placemaking_is_temporary_and_decays_with_distance():
    assets = pd.DataFrame({"asset_id": ["SITE", "NEAR", "FAR"],
                           "asset_type": ["green_space", "commercial", "commercial"]})
    points = {"SITE": (0, 0), "NEAR": (50, 0), "FAR": (1000, 0)}
    iv = pd.DataFrame([{
        "intervention_type": "tactical_placemaking", "target_asset_id": "SITE",
        "activation_year": 2027,
        "parameters_json": json.dumps({"kind": "night_market", "duration_years": 2}),
    }])
    b27 = soft.footfall_boosts(iv, 2027, assets, points)
    assert "FAR" not in b27 and b27["NEAR"] > 1.4
    assert soft.footfall_boosts(iv, 2029, assets, points) == {}


def test_street_survival_counts_shops_in_radius():
    assets = pd.DataFrame({"asset_id": ["A", "B", "C"], "asset_type": ["commercial"] * 3})
    points = {"A": (0, 0), "B": (100, 0), "C": (5000, 0)}
    state = {"A": {"occupancy_rate": 0.8}, "B": {"proxied_occupancy_lbs": 0.2},
             "C": {"occupancy_rate": 0.9}}
    share, n = soft.street_survival("A", state, assets, points)
    assert (share, n) == (0.5, 2)


# ------------------------------------------------------------------
# Prompts carry the new rules
# ------------------------------------------------------------------

def test_prompts_carry_soft_and_status_rules():
    gen = (PROMPTS / "candidate_generator.md").read_text(encoding="utf-8")
    writer = (PROMPTS / "final_decision_writer.md").read_text(encoding="utf-8")
    assert "tenant_matching" in gen and "tactical_placemaking" in gen
    assert "strategic_learning" in gen and "new_link" in gen
    assert "street survival" in writer.lower()


# ------------------------------------------------------------------
# Real data (skipped when the processed data is not present)
# ------------------------------------------------------------------

REPO = Path(__file__).resolve().parents[2]
HAS_DATA = (REPO / "bukit_jelutong" / "processed" / "business" / "assets.csv").exists()


@pytest.mark.skipif(not HAS_DATA, reason="processed data not available")
def test_context_pack_has_no_nan_and_hides_sold_leases():
    from app.llm.context_builder import build_context_pack
    from app.llm.tool_service import TownshipDataSource
    ds = TownshipDataSource(REPO, 2026)
    assert len(ds._load_centroids()) == len(ds.assets)          # issue 2
    sold_shop = ds.assets[(ds.assets.asset_type == "commercial")
                          & (ds.assets.authority != "full_control")].asset_id.iloc[0]
    pack = build_context_pack({"target_asset_ids": [sold_shop, "BLD-0037"]}, ds)
    text = json.dumps(pack, default=str)
    assert "NaN" not in text                                      # issue 5
    sold, owned = pack["targets"]
    assert sold["lease_schedule"] is None                         # issue 7
    assert "collaborative" in sold["authority"]
    base = pack["township_baseline"]
    assert base["commercial_supply_m2"] < 200_000                 # issue 4
    assert "sold_estimate_tier_3a" in base["commercial_avg_occupancy"]
    assert "flag_tiers" in owned["deadspace"]                     # issue 8
    assert "soft_intervention_vocabulary" in pack
