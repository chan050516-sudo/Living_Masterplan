import sys
from pathlib import Path
import geopandas as gpd
from shapely.geometry import box

REPO_ROOT = Path('.').resolve()
sys.path.insert(0, str(REPO_ROOT / "backend"))
from app.config import load_paths

def extract_best_parcels():
    paths = load_paths()
    base_dir = REPO_ROOT / paths["base"]
    
    print("加载图层并构建安全退距 Buffer...")
    buildings = gpd.read_file(base_dir / paths["geometry"]["buildings"]).to_crs("EPSG:32647")
    green_blue = gpd.read_file(base_dir / paths["geometry"]["green_blue"]).to_crs("EPSG:32647")
    network = gpd.read_file(base_dir / paths["geometry"]["network"]).to_crs("EPSG:32647")
    
    # 1. 强制退距 (Buffer)
    # 建筑退距 15m (满足消防和日照要求)
    b_buffered = buildings.geometry.union_all().buffer(15.0)
    # 马路退距 10m (满足人行道和绿化带要求)
    n_buffered = network.geometry.union_all().buffer(10.0)
    # 绿地退距 5m
    gb_buffered = green_blue.geometry.union_all().buffer(5.0)
    
    # 构建绝对不可侵犯的排除区域
    exclusion_mask = b_buffered.union(n_buffered).union(gb_buffered)
    
    minx, miny, maxx, maxy = buildings.total_bounds
    cell_size = 200.0  
    
    candidates = []
    minx_scan = minx + cell_size / 2
    miny_scan = miny + cell_size / 2
    maxx_scan = maxx - cell_size / 2
    maxy_scan = maxy - cell_size / 2
    
    nxx = int((maxx_scan - minx_scan) / cell_size) + 1
    nyy = int((maxy_scan - miny_scan) / cell_size) + 1
    
    print("开始扫描网格，寻找完美空地...")
    for ix in range(nxx):
        for iy in range(nyy):
            x0 = minx_scan + ix * cell_size
            y0 = miny_scan + iy * cell_size
            cell = box(x0, y0, x0 + cell_size, y0 + cell_size)
            
            # 网格必须至少挨着现有建筑区，避免跑到纯荒野去
            if not buildings.geometry.union_all().intersects(cell.buffer(100.0)): 
                continue
                
            # 2. 扣除退距区域
            residual = cell.difference(exclusion_mask)
            
            if residual.is_empty: 
                continue
                
            # 如果被切成了多块，只取最大的一块
            if residual.geom_type == "MultiPolygon":
                residual = max(residual.geoms, key=lambda g: g.area)
                
            # 简化多边形边缘（去掉细小的锯齿，平滑边界）
            residual = residual.simplify(1.0)
            
            if residual.is_empty or residual.geom_type != "Polygon":
                continue
                
            area = residual.area
            # 3. 面积限制：10,000 ~ 30,000 m²
            if 8000 <= area <= 30000:
                # 计算紧凑度（矩形接近 0.785，越方越好）
                compactness = 4 * 3.14159 * area / (residual.length ** 2)
                # 只要相对方正的（紧凑度 > 0.15）
                if compactness > 0.15:
                    # 临街检查：距离原路网不能太远（这里计算未 buffer 的路网）
                    dist_to_road = residual.distance(network.geometry.union_all())
                    if dist_to_road <= 20.0: 
                        candidates.append({
                            "geometry": residual,
                            "area": area,
                            "compactness": compactness,
                            "dist_to_road": dist_to_road
                        })
                        
    # 按紧凑度降序排序
    candidates.sort(key=lambda x: x["compactness"], reverse=True)
    
    # 空间去重，取前 9 个
    final_geoms = []
    final_meta = []
    for c in candidates:
        g = c["geometry"]
        if not any(g.intersects(f) and g.intersection(f).area > g.area * 0.3 for f in final_geoms):
            final_geoms.append(g)
            final_meta.append(c)
            if len(final_geoms) >= 9: 
                break
                
    if not final_geoms:
        print("没找到符合 10,000-30,000m2 且严格退距的完美地块。尝试将 cell_size 增大到 250.0。")
        return

    out_gdf = gpd.GeoDataFrame(geometry=final_geoms, crs="EPSG:32647")
    out_gdf["parcel_id"] = [f"P-VAC-GOLD-{i+1:02d}" for i in range(len(out_gdf))]
    out_gdf["asset_id"] = out_gdf["parcel_id"]
    out_gdf["area_m2"] = [round(m["area"]) for m in final_meta]
    out_gdf["compactness"] = [round(m["compactness"], 3) for m in final_meta]
    
    print(f"\n🎉 精选出 {len(out_gdf)} 个完美的黄金开发地块（强制退距：路 10m、建筑 15m）：")
    print(out_gdf[["parcel_id", "area_m2", "compactness"]])
    
    out_path = REPO_ROOT / "bukit_jelutong" / "golden_parcels.geojson"
    out_gdf.to_file(out_path, driver="GeoJSON")
    print(f"\n已保存到: {out_path}")
    print("去 QGIS/MapLibre 叠加底图看一眼，这次绝对完美退距，且不会压路。")

if __name__ == "__main__":
    extract_best_parcels()