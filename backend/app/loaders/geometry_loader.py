"""Load GeoJSON geometry layers and normalise CRS."""

from pathlib import Path
import geopandas as gpd


def load_geometry(repo_root: Path, paths: dict) -> dict:
    """
    Load all geometry layers listed under paths['geometry'].
    Reprojects to analysis_crs (EPSG:32647) for distance/area computation.
    """
    base = repo_root / paths["base"]
    analysis_crs = "EPSG:32647"

    layers = {}
    for key, rel in paths["geometry"].items():
        path = base / rel
        if not path.exists():
            raise FileNotFoundError(f"Geometry file not found: {path}")
        gdf = gpd.read_file(path)
        if gdf.crs is None:
            gdf = gdf.set_crs("EPSG:4326")
        gdf_analysis = gdf.to_crs(analysis_crs)
        layers[key] = {
            "raw": gdf,                # EPSG:4326 (for export / display)
            "analysis": gdf_analysis,  # EPSG:32647 (for computation)
        }
    return layers