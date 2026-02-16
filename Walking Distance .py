# ============================================================
# INSTALLS (RUN ONCE IN COLAB)
# ============================================================
!pip install -q geopandas osmnx contextily shapely pyproj networkx requests matplotlib

# ============================================================
# IMPORTS
# ============================================================
import osmnx as ox
import geopandas as gpd
import contextily as cx
import matplotlib.pyplot as plt
import networkx as nx
import requests
import numpy as np

from shapely.geometry import Point
from pyproj import Transformer

ox.settings.log_console = False
ox.settings.use_cache = True

# ============================================================
# USER INPUT
# ============================================================
LOT_ID = "IL 1657"
WALK_SPEED_KMPH = 5
MAP_EXTENT = 2000

# ============================================================
# LOT → COORDINATES (HK LandsD)
# ============================================================
def resolve_lot(lot):
    url = f"https://mapapi.geodata.gov.hk/gs/api/v1.0.0/lus/lot/SearchNumber?text={lot.replace(' ','%20')}"
    r = requests.get(url)
    r.raise_for_status()
    best = max(r.json()["candidates"], key=lambda x: x["score"])
    return best["location"]["x"], best["location"]["y"]

x2326, y2326 = resolve_lot(LOT_ID)
lon, lat = Transformer.from_crs(2326, 4326, always_xy=True).transform(x2326, y2326)

# ============================================================
# GET REAL SITE FOOTPRINT FROM OSM
# ============================================================
osm_site = ox.features_from_point((lat, lon), dist=60, tags={"building": True}).to_crs(3857)

if len(osm_site):
    osm_site["area_calc"] = osm_site.geometry.area
    site_geom = osm_site.sort_values("area_calc", ascending=False).geometry.iloc[0]
else:
    site_geom = gpd.GeoSeries([Point(lon, lat)], crs=4326).to_crs(3857).iloc[0].buffer(40)

site_gdf = gpd.GeoDataFrame(geometry=[site_geom], crs=3857)
site_point = site_geom.centroid  # TRUE VISUAL SITE POINT

# ============================================================
# WALK NETWORK
# ============================================================
G_walk = ox.graph_from_point((lat, lon), dist=3000, network_type="walk")
roads = ox.graph_to_gdfs(G_walk, nodes=False).to_crs(3857)

# Snap ROUTE START to DISPLAYED SITE CENTROID
site_centroid_wgs = gpd.GeoSeries([site_point], crs=3857).to_crs(4326).iloc[0]
site_node = ox.distance.nearest_nodes(G_walk, site_centroid_wgs.x, site_centroid_wgs.y)

# ============================================================
# FETCH MTR STATIONS
# ============================================================
stations = ox.features_from_point(
    (lat, lon),
    tags={"railway": "station"},
    dist=3000
).to_crs(3857)

stations = stations[stations.geometry.notnull()]
stations["station_name"] = stations.apply(
    lambda r: r.get("name:en") if isinstance(r.get("name:en"), str)
    else r.get("name") if isinstance(r.get("name"), str)
    else "MTR Station",
    axis=1
)

stations["dist"] = stations.geometry.centroid.distance(site_point)
stations = stations.sort_values("dist").head(3)

# ============================================================
# ROUTE CALCULATION
# ============================================================
routes = []

for _, row in stations.iterrows():

    st_centroid = row.geometry.centroid
    st_wgs = gpd.GeoSeries([st_centroid], crs=3857).to_crs(4326).iloc[0]
    st_node = ox.distance.nearest_nodes(G_walk, st_wgs.x, st_wgs.y)

    try:
        path = nx.shortest_path(G_walk, site_node, st_node, weight="length")
    except nx.NetworkXNoPath:
        continue

    route = ox.routing.route_to_gdf(G_walk, path).to_crs(3857)

    dist_km = round(route.length.sum() / 1000, 2)
    time_min = max(1, round((dist_km / WALK_SPEED_KMPH) * 60))

    routes.append({
        "route": route,
        "distance": dist_km,
        "time": time_min,
        "station_polygon": row.geometry,
        "station_centroid": st_centroid,
        "name": row["station_name"]
    })

# ============================================================
# PLOT MAP
# ============================================================
fig, ax = plt.subplots(figsize=(12,12))

# Roads
roads.plot(ax=ax, linewidth=0.25, color="#8a8a8a", alpha=0.4)

# 15-min shaded area
gpd.GeoSeries([site_point.buffer(1125)], crs=3857).plot(
    ax=ax, color="#2aa9ff", alpha=0.15
)

# Rings
for d, lbl in [(375,"5 min"), (750,"10 min"), (1125,"15 min")]:
    gpd.GeoSeries([site_point.buffer(d)], crs=3857).boundary.plot(
        ax=ax,
        linestyle=(0,(4,3)),
        linewidth=2,
        color="#2aa9ff"
    )
    ax.text(site_point.x + d + 120, site_point.y, lbl, fontsize=9)

# Routes + Labels
# Routes + Stations (Professional Style)
# Routes + Stations (Balanced Professional Style)

colors = ["#4caf50", "#ef5350", "#42a5f5"]
  # green, red, blue

for i, r in enumerate(routes):

    route_color = colors[i]

    # --------------------------------
    # 1. ROUTE (lighter + softer)
    # --------------------------------
    r["route"].plot(
        ax=ax,
        linewidth=2.8,      # slightly thinner
        color=route_color,
        alpha=0.85,
        zorder=5
    )

    # --------------------------------
    # 2. STATION POLYGON (very soft)
    # --------------------------------
    gpd.GeoSeries([r["station_polygon"]], crs=3857).plot(
        ax=ax,
        facecolor=route_color,
        edgecolor=route_color,
        linewidth=1,
        alpha=0.18,
        zorder=4
    )

    # --------------------------------
    # 3. STATION NAME
    # --------------------------------
    ax.text(
        r["station_centroid"].x,
        r["station_centroid"].y + 120,
        r["name"].upper(),
        fontsize=10,
        weight="bold",
        ha="center",
        color="black",
        zorder=7
    )

    # --------------------------------
    # 4. TIME + DISTANCE (clean text)
    # --------------------------------
    mid = r["route"].geometry.iloc[len(r["route"]) // 2].centroid

    ax.text(
        mid.x,
        mid.y,
        f'{r["time"]} min\n{r["distance"]} km',
        fontsize=9,
        weight="bold",
        color=route_color,
        ha="center",
        zorder=6
    )



# Site polygon
site_gdf.plot(ax=ax, facecolor="red", edgecolor="none", linewidth=1.5)
ax.text(
    site_point.x,
    site_point.y - 120,
    "SITE",
    color="red",
    weight="bold",
    ha="center"
)

# Extent
ax.set_xlim(site_point.x - MAP_EXTENT, site_point.x + MAP_EXTENT)
ax.set_ylim(site_point.y - MAP_EXTENT, site_point.y + MAP_EXTENT)

# Basemap
cx.add_basemap(
    ax,
    source=cx.providers.CartoDB.PositronNoLabels,
    zoom=15,
    alpha=0.4
)

ax.set_title("Walking Accessibility to Public Transport", fontsize=15, weight="bold")
ax.set_axis_off()

plt.show()
