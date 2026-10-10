import osmnx as ox
import geopandas as gpd

# Configuration
# Configuration
# Configuration
# Coordinates near Elmina Central Park to capture commercial, residential, and green spaces
CENTER_POINT = (3.1610, 101.5030) 
DIST_M = 707 # 707m radius creates a 2 km^2 square bounding box
COMPUTE_CRS = "EPSG:32647" 
DISPLAY_CRS = "EPSG:4326"

def generate_ids(gdf, prefix):
    """Generates sequential IDs matching the Masterplan ID convention."""
    return [f"{prefix}{str(i+1).zfill(4)}" for i in range(len(gdf))]

def process_buildings():
    print("Fetching Buildings...")
    tags = {"building": True}
    gdf = ox.features_from_point(CENTER_POINT, dist=DIST_M, tags=tags)
    gdf = gdf[gdf.geometry.type.isin(['Polygon', 'MultiPolygon'])]
    
    # Reproject to compute CRS to get area in square meters
    gdf_proj = gdf.to_crs(COMPUTE_CRS)
    gdf['area_m2'] = gdf_proj.geometry.area
    
    # Task A5: Indexing & Schema matching
    gdf['building_id'] = generate_ids(gdf, "BLD-")
    gdf['building_type'] = gdf['building'].fillna('unknown')
    gdf['gfa_m2'] = gdf['area_m2'] # Base assumption, to be enriched later
    gdf['geometry_source'] = 'OSM'
    
    final_gdf = gdf[['building_id', 'building_type', 'gfa_m2', 'geometry_source', 'geometry']].to_crs(DISPLAY_CRS)
    final_gdf.to_file("buildings.geojson", driver="GeoJSON")
    print(f"Saved {len(final_gdf)} buildings.")

def process_parcels():
    print("Fetching Parcels (Land Use)...")
    tags = {"landuse": ["residential", "commercial", "retail", "industrial", "construction", "brownfield"]}
    gdf = ox.features_from_point(CENTER_POINT, dist=DIST_M, tags=tags)
    gdf = gdf[gdf.geometry.type.isin(['Polygon', 'MultiPolygon'])]
    
    gdf_proj = gdf.to_crs(COMPUTE_CRS)
    gdf['area_m2'] = gdf_proj.geometry.area
    
    # Task A5: Indexing & Schema matching
    gdf['parcel_id'] = generate_ids(gdf, "P-")
    gdf['land_use'] = gdf['landuse'].fillna('unclassified')
    gdf['geometry_source'] = 'OSM'
    gdf['geometry_confidence'] = 'Low (OSM inferred)'
    
    final_gdf = gdf[['parcel_id', 'land_use', 'area_m2', 'geometry_source', 'geometry_confidence', 'geometry']].to_crs(DISPLAY_CRS)
    final_gdf.to_file("parcels.geojson", driver="GeoJSON")
    print(f"Saved {len(final_gdf)} parcels.")

def process_network():
    print("Fetching Walk Network...")
    G = ox.graph_from_point(CENTER_POINT, dist=DIST_M, network_type="walk")
    
    # Convert graph to geodataframes
    nodes, edges = ox.graph_to_gdfs(G)
    
    # Edge Processing
    edges_proj = edges.to_crs(COMPUTE_CRS)
    edges['length_m'] = edges_proj.geometry.length
    edges = edges.reset_index()
    
    edges['edge_id'] = generate_ids(edges, "E-")
    edges['edge_type'] = edges['highway'].astype(str)
    edges['walk_speed_kmh'] = 4.5 # Default walking speed assumption
    
    final_edges = edges[['edge_id', 'edge_type', 'u', 'v', 'length_m', 'walk_speed_kmh', 'geometry']].to_crs(DISPLAY_CRS)
    final_edges = final_edges.rename(columns={'u': 'from_node', 'v': 'to_node'})
    final_edges.to_file("network_edges.geojson", driver="GeoJSON")
    print(f"Saved {len(final_edges)} network edges.")

def process_green_blue():
    print("Fetching Green & Blue Spaces...")
    tags = {
        "leisure": ["park", "nature_reserve", "pitch", "golf_course"],
        "natural": ["water", "wood", "scrub", "tree_row"],
        "landuse": ["grass", "forest", "recreation_ground"]
    }
    gdf = ox.features_from_point(CENTER_POINT, dist=DIST_M, tags=tags)
    gdf = gdf[gdf.geometry.type.isin(['Polygon', 'MultiPolygon'])]
    
    gdf_proj = gdf.to_crs(COMPUTE_CRS)
    gdf['area_m2'] = gdf_proj.geometry.area
    
    # Task A5: Indexing & Schema matching
    gdf['green_id'] = generate_ids(gdf, "G-")
    # Consolidate type from the multiple OSM tags
    gdf['green_type'] = gdf['leisure'].combine_first(gdf['natural']).combine_first(gdf['landuse']).fillna('unknown')
    gdf['canopy_m2'] = gdf['area_m2'] * 0.5 # Placeholder assumption for Task B3
    gdf['geometry_source'] = 'OSM'
    
    final_gdf = gdf[['green_id', 'green_type', 'area_m2', 'canopy_m2', 'geometry_source', 'geometry']].to_crs(DISPLAY_CRS)
    final_gdf.to_file("green_blue.geojson", driver="GeoJSON")
    print(f"Saved {len(final_gdf)} green/blue spaces.")

def process_amenities():
    print("Fetching Amenities...")
    tags = {"amenity": True}
    gdf = ox.features_from_point(CENTER_POINT, dist=DIST_M, tags=tags)
    # Amenities can be Points or Polygons, keep both for now
    
    # Task A5: Indexing & Schema matching
    gdf = gdf.reset_index()
    gdf['amenity_id'] = generate_ids(gdf, "A-")
    gdf['amenity_type'] = gdf['amenity'].fillna('unknown')
    gdf['capacity'] = 0 # Placeholder for business layer enrichment
    
    final_gdf = gdf[['amenity_id', 'amenity_type', 'capacity', 'geometry']].to_crs(DISPLAY_CRS)
    final_gdf.to_file("amenities.geojson", driver="GeoJSON")
    print(f"Saved {len(final_gdf)} amenities.")

if __name__ == "__main__":
    print("Starting Module A GeoJSON Pipeline...")
    process_buildings()
    process_parcels()
    process_network()
    process_green_blue()
    process_amenities()
    print("Task A2 & A5 Complete. Proceed to QGIS for Task A3 (Validation).")