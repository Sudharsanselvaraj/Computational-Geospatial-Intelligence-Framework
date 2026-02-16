import zipfile

zip_path = "/content/GeoJSON_Statutory_Plans (1).zip"
extract_path = "/content/extracted_data/"

with zipfile.ZipFile(zip_path, 'r') as zip_ref:
    zip_ref.extractall(extract_path)

print("ZIP file extracted successfully.")
# ============================================================
# INSTALLS (Run once)
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
import matplotlib.lines as mlines

from shapely.geometry import Point
from pyproj import Transformer

ox.settings.use_cache = True
ox.settings.log_console = False

# ============================================================
# SETTINGS
# ============================================================
LOT_ID = "IL 1657"
DRIVE_SPEED = 35
MAP_EXTENT = 1400
OZP_ZONE_PATH = "/content/extracted_data/Statutory Plan GIS Data GeoJSON/ZONE.json"

# ============================================================
# GET LOT COORDINATE
# ============================================================
def resolve_lot(lot):
    url = f"https://mapapi.geodata.gov.hk/gs/api/v1.0.0/lus/lot/SearchNumber?text={lot.replace(' ','%20')}"
    r = requests.get(url)
    best = max(r.json()["candidates"], key=lambda x: x["score"])
    return best["location"]["x"], best["location"]["y"]

x2326, y2326 = resolve_lot(LOT_ID)
lon, lat = Transformer.from_crs(2326, 4326, always_xy=True).transform(x2326, y2326)

site_point = gpd.GeoSeries([Point(lon, lat)], crs=4326).to_crs(3857).iloc[0]

# ============================================================
# LOAD OZP → REAL SITE POLYGON
# ============================================================
ozp = gpd.read_file(OZP_ZONE_PATH).to_crs(3857)
site_polygon = ozp[ozp.contains(site_point)].geometry.iloc[0]
site_gdf = gpd.GeoDataFrame(geometry=[site_polygon], crs=3857)

centroid = site_polygon.centroid

# ============================================================
# DRIVE NETWORK
# ============================================================
G = ox.graph_from_point((lat, lon), dist=3000, network_type="drive")

for u, v, k, data in G.edges(keys=True, data=True):
    data["travel_time"] = data["length"] / (DRIVE_SPEED * 1000 / 60)

site_node = ox.distance.nearest_nodes(G, lon, lat)

# ============================================================
# GET NEAREST MTR STATIONS
# ============================================================
stations = ox.features_from_point(
    (lat, lon),
    tags={"railway": "station"},
    dist=3000
).to_crs(3857)

stations["dist"] = stations.centroid.distance(centroid)
stations = stations.sort_values("dist").head(3)

# ============================================================
# ROUTE FUNCTION
# ============================================================
def get_route(node_from, node_to):
    try:
        route = nx.shortest_path(G, node_from, node_to, weight="travel_time")
        return ox.routing.route_to_gdf(G, route).to_crs(3857)
    except:
        return None
from shapely.geometry import LineString, MultiLineString

def add_route_arrow(ax, gdf_route, color):
    if gdf_route is None or gdf_route.empty:
        return

    merged = gdf_route.geometry.union_all()

    # Handle MultiLineString properly
    if isinstance(merged, MultiLineString):
        merged = max(list(merged.geoms), key=lambda g: g.length)

    if not isinstance(merged, LineString):
        return

    coords = list(merged.coords)

    if len(coords) < 2:
        return

    # Place arrow at 60% of route
    idx = int(len(coords) * 0.6)

    ax.annotate(
        "",
        xy=coords[idx + 1],
        xytext=coords[idx],
        arrowprops=dict(
            arrowstyle="-|>",
            color=color,
            lw=2,
            mutation_scale=18
        ),
        zorder=20   # VERY IMPORTANT
    )


# ============================================================
# PLOT
# ============================================================
fig, ax = plt.subplots(figsize=(12,12))
fig.patch.set_facecolor("#f2f2f2")
ax.set_facecolor("#f2f2f2")

# ------------------------------------------------------------
# BASEMAP (FIXED ZOOM – no warning)
# ------------------------------------------------------------
cx.add_basemap(
    ax,
    source=cx.providers.CartoDB.PositronNoLabels,
    zoom=17,
    alpha=1.0
)

# ------------------------------------------------------------
# ROAD NETWORK
# ------------------------------------------------------------
edges = ox.graph_to_gdfs(G, nodes=False).to_crs(3857)
edges.plot(
    ax=ax,
    linewidth=0.6,
    color="#8f8f8f",
    alpha=0.35,
    zorder=1
)

# ------------------------------------------------------------
# DISTANCE RINGS
# ------------------------------------------------------------
ring1 = centroid.buffer(375)
ring2 = centroid.buffer(750)
ring3 = centroid.buffer(1125)

# soft fill
gpd.GeoSeries([ring3], crs=3857).plot(ax=ax, color="#f4d03f", alpha=0.05, zorder=2)
gpd.GeoSeries([ring2], crs=3857).plot(ax=ax, color="#f4d03f", alpha=0.07, zorder=3)
gpd.GeoSeries([ring1], crs=3857).plot(ax=ax, color="#f4d03f", alpha=0.10, zorder=4)

# dashed boundaries
for ring in [ring1, ring2, ring3]:
    gpd.GeoSeries([ring], crs=3857).boundary.plot(
        ax=ax,
        color="#c8a600",
        linewidth=2,
        linestyle=(0,(6,5)),
        zorder=5
    )

# ------------------------------------------------------------
# ROUTES + STATIONS
# ------------------------------------------------------------
for _, station in stations.iterrows():

    st_centroid = station.geometry.centroid
    st_wgs = gpd.GeoSeries([st_centroid], crs=3857).to_crs(4326).iloc[0]
    station_node = ox.distance.nearest_nodes(G, st_wgs.x, st_wgs.y)

    ingress = get_route(station_node, site_node)
    egress  = get_route(site_node, station_node)

    if ingress is not None:
      ingress.plot(ax=ax, linewidth=2.5, color="#e74c3c", zorder=10)
      add_route_arrow(ax, ingress, "#e74c3c")

    if egress is not None:
      egress.plot(ax=ax, linewidth=2.5, color="#27ae60", zorder=10)
      add_route_arrow(ax, egress, "#27ae60")


    # Station footprint
    gpd.GeoSeries([station.geometry], crs=3857).plot(
        ax=ax,
        facecolor="#5dade2",
        edgecolor="#2e86c1",
        linewidth=1.5,
        alpha=0.6,
        zorder=7
    )

    # Station Name Label
    name = station.get("name:en") or station.get("name") or "STATION"

    ax.text(
        st_centroid.x,
        st_centroid.y + 120,
        name.upper(),
        fontsize=9,
        weight="bold",
        ha="center",
        va="center",
        bbox=dict(facecolor="white", edgecolor="none", alpha=0.9, pad=2),
        zorder=8
    )

# ------------------------------------------------------------
# SITE POLYGON (IMPROVED STYLE)
# ------------------------------------------------------------
site_gdf.plot(
    ax=ax,
    facecolor="#ff4d4d",
    edgecolor="none",
    linewidth=2,
    alpha=0.45,
    zorder=9
)


# SITE label slightly offset (cleaner)
ax.text(
    centroid.x,
    centroid.y - 70,
    "SITE",
    color="black",
    weight="bold",
    ha="center",
    va="center",
    fontsize=11,
    zorder=10
)

# ------------------------------------------------------------
# DISTANCE LABELS
# ------------------------------------------------------------
ax.text(centroid.x + 500, centroid.y,
        "1.5 MINS\n0.375 KM",
        fontsize=10,
        weight="bold",

        zorder=10)

ax.text(centroid.x + 900, centroid.y,
        "3 MINS\n0.75 KM",
        fontsize=10,
        weight="bold",

        zorder=10)

ax.text(centroid.x + 1300, centroid.y,
        "4.5 MINS\n1.125 KM",
        fontsize=10,
        weight="bold",

        zorder=10)

# ------------------------------------------------------------
# LEGEND
# ------------------------------------------------------------
ingress_line = mlines.Line2D([], [], color="#e74c3c", linewidth=2.5, label="Ingress Route")
egress_line = mlines.Line2D([], [], color="#27ae60", linewidth=2.5, label="Egress Route")

ax.legend(
    handles=[ingress_line, egress_line],
    loc="lower right",
    frameon=True,
    facecolor="white",
    edgecolor="black"
)

# ------------------------------------------------------------
# EXTENT
# ------------------------------------------------------------
ax.set_xlim(centroid.x - MAP_EXTENT, centroid.x + MAP_EXTENT)
ax.set_ylim(centroid.y - MAP_EXTENT, centroid.y + MAP_EXTENT)

ax.set_title(
    "SITE ANALYSIS - Driving Distance",
    fontsize=16,
    weight="bold"
)

ax.set_axis_off()
plt.tight_layout()
plt.show()
