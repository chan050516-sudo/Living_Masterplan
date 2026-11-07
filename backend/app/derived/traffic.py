"""Fallback daily traffic exposure derived from OSM road geometry.

This is a transparent capacity proxy for cells without Kido traffic values;
it is not a measured vehicle count.
"""

from __future__ import annotations

import math


# Approximate daily vehicle flow per kilometre of road class. These are
# intentionally broad planning assumptions and are not local traffic counts.
_VEHICLES_PER_DAY_PER_KM = {
    "motorway": 50_000,
    "motorway_link": 28_000,
    "trunk": 35_000,
    "trunk_link": 20_000,
    "primary": 22_000,
    "primary_link": 15_000,
    "secondary": 13_000,
    "secondary_link": 9_000,
    "tertiary": 7_000,
    "tertiary_link": 4_500,
    "unclassified": 3_500,
    "residential": 2_500,
    "living_street": 1_000,
    "service": 700,
    "road": 2_000,
    "track": 300,
}


def _normalise_road_type(value):
    """Normalise a road class string into the capacity lookup keys."""
    if value is None:
        return "road"
    if isinstance(value, (list, tuple, set)):
        for item in value:
            normalised = _normalise_road_type(item)
            if normalised and normalised != "road":
                return normalised
        return "road"

    text = str(value).strip().lower()
    if not text or text in {"nan", "none", "null"}:
        return "road"

    for separator in ("|", ",", "/"):
        parts = [part.strip() for part in text.split(separator)]
        if len(parts) > 1:
            for part in parts:
                if part:
                    normalised = _normalise_road_type(part)
                    if normalised and normalised != "road":
                        return normalised
            return "road"

    text = text.replace(" ", "_")
    text = text.replace("-", "_")
    text = text.replace("/", "_")
    text = text.replace("_junction", "")
    return text or "road"


def _road_capacity(road_type):
    """Look up a road class capacity, accepting OSM alias names and lists."""
    normalised = _normalise_road_type(road_type)
    if normalised in _VEHICLES_PER_DAY_PER_KM:
        return _VEHICLES_PER_DAY_PER_KM[normalised]
    if normalised.endswith("_link"):
        return _VEHICLES_PER_DAY_PER_KM.get(normalised.rsplit("_", 1)[0], 0)
    return 0


def estimate_osm_traffic_vpd(network_gdf, cell_geometry, cell_area_m2=160_000):
    """Estimate vehicle/day exposure from road length and OSM class.

    `network_gdf` and `cell_geometry` must already use the same projected
    metric CRS. The result is capped because overlapping or duplicate OSM
    segments can otherwise inflate the estimate.
    """
    if network_gdf is None or network_gdf.empty or cell_geometry is None:
        return 0

    length_weighted_flow = 0.0
    for row in network_gdf.itertuples():
        geom = getattr(row, "geometry", None)
        if geom is None:
            continue
        try:
            if geom.is_empty or not geom.intersects(cell_geometry):
                continue
        except (AttributeError, TypeError, ValueError):
            continue

        road_type = getattr(row, "edge_type", None)
        if road_type is None:
            road_type = getattr(row, "highway", "road")
        capacity = _road_capacity(road_type)
        if capacity <= 0:
            continue

        try:
            segment = geom.intersection(cell_geometry)
            if segment is None or getattr(segment, "is_empty", False):
                continue
            segment_length_km = segment.length / 1000.0
        except (AttributeError, TypeError, ValueError):
            continue
        length_weighted_flow += capacity * segment_length_km

    # Convert overlapping road-segment totals into a bounded cell exposure.
    area_scale = max(0.5, min(1.5, math.sqrt(max(cell_area_m2, 1.0) / 160_000)))
    return int(round(min(100_000, length_weighted_flow * area_scale)))


def resolve_traffic_exposure(kido_vpd, network_gdf, cell_geometry):
    """Prefer Kido values and fall back to the OSM capacity proxy."""
    try:
        if kido_vpd is not None and math.isfinite(float(kido_vpd)):
            return int(round(max(0.0, float(kido_vpd)))), "kido_mock"
    except (TypeError, ValueError):
        pass
    return estimate_osm_traffic_vpd(network_gdf, cell_geometry), "osm_proxy"
