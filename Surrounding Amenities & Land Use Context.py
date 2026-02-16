# ============================================================
# INSTALLS (RUN ONCE)
# ============================================================
!pip install -q geopandas osmnx contextily shapely pyproj requests networkx matplotlib scikit-learn

# ============================================================
# IMPORTS
# ============================================================
import osmnx as ox
import geopandas as gpd
import matplotlib.pyplot as plt
import contextily as cx
import requests
import networkx as nx
import matplotlib.patches as mpatches
import numpy as np
import textwrap

from shapely.geometry import Point
from pyproj import Transformer
from sklearn.cluster import KMeans

ox.settings.use_cache = True
ox.settings.log_console = False

# ============================================================
# CONSTANTS
# ============================================================
MTR_COLOR = "#ffd166"# ORANGE for MTR stations

# ============================================================
# USER INPUT
# ============================================================
LOT_ID = "IL 1657"
FETCH_RADIUS = 1500
MAP_HALF_SIZE = 900
OZP_ZONE_PATH = "/content/extracted_data/Statutory Plan GIS Data GeoJSON/ZONE.json"

# ============================================================
# TEXT HELPERS
# ============================================================
def wrap_label(text, width=18):
    return "\n".join(textwrap.wrap(text, width))

def get_constraint_text(row):
    for k in ["DESC_ENG", "NOTE_ENG", "REMARKS", "CONSTRAINT", "ANNOTATION"]:
        if k in row and isinstance(row[k], str) and row[k].strip():
            return row[k]
    return "No special statutory planning constraints identified."

# ============================================================
# LOT → COORDINATES
# ============================================================
def resolve_lot(lot):
    url = (
        "https://mapapi.geodata.gov.hk/gs/api/v1.0.0/lus/lot/SearchNumber"
        f"?text={lot.replace(' ', '%20')}"
    )
    r = requests.get(url)
    r.raise_for_status()
    best = max(r.json()["candidates"], key=lambda x: x["score"])
    return best["location"]["x"], best["location"]["y"]

x2326, y2326 = resolve_lot(LOT_ID)
lon, lat = Transformer.from_crs(2326, 4326, always_xy=True).transform(x2326, y2326)
site_point = gpd.GeoSeries([Point(lon, lat)], crs=4326).to_crs(3857).iloc[0]

# ============================================================
# OZP → SITE TYPE
# ============================================================
ozp = gpd.read_file(OZP_ZONE_PATH).to_crs(3857)
primary = ozp[ozp.contains(site_point)].iloc[0]
zone = primary["ZONE_LABEL"]

def infer_site_type(zone):
    if zone.startswith("R"): return "RESIDENTIAL"
    if zone.startswith("C"): return "COMMERCIAL"
    if zone.startswith("G"): return "INSTITUTIONAL"
    if "HOTEL" in zone.upper() or zone.startswith("OU"): return "HOTEL"
    return "MIXED"

SITE_TYPE = infer_site_type(zone)
CONSTRAINT_TEXT = wrap_label(get_constraint_text(primary), 38)

# ============================================================
# SITE-TYPE DRIVEN LABEL RULES
# ============================================================
def context_rules(site_type):
    if site_type == "RESIDENTIAL":
        return {"amenity":["school","college","university"],"leisure":["park"],"place":["neighbourhood"]}
    if site_type == "COMMERCIAL":
        return {"amenity":["bank","restaurant","market"],"railway":["station"]}
    if site_type == "INSTITUTIONAL":
        return {"amenity":["school","college","hospital"],"leisure":["park"]}
    return {"amenity":True,"leisure":True}

LABEL_RULES = context_rules(SITE_TYPE)

# ============================================================
# FETCH OSM POLYGONS
# ============================================================
polygons = ox.features_from_point(
    (lat, lon),
    dist=FETCH_RADIUS,
    tags={"landuse":True,"leisure":True,"amenity":True,"building":True}
).to_crs(3857)

# ============================================================
# SITE FOOTPRINT
# ============================================================
candidates = polygons[
    polygons.geometry.geom_type.isin(["Polygon","MultiPolygon"]) &
    (polygons.geometry.distance(site_point) < 40)
]

site_geom = (
    candidates.assign(area=candidates.area)
    .sort_values("area", ascending=False)
    .geometry.iloc[0]
    if len(candidates) else site_point.buffer(40)
)

site_gdf = gpd.GeoDataFrame(geometry=[site_geom], crs=3857)

# ============================================================
# LAND USE LAYERS
# ============================================================
residential = polygons[polygons.get("landuse")=="residential"]
industrial  = polygons[polygons.get("landuse").isin(["industrial","commercial"])]
parks       = polygons[polygons.get("leisure")=="park"]
schools     = polygons[polygons.get("amenity").isin(["school","college","university"])]
buildings   = polygons[polygons.get("building").notnull()]

# ============================================================
# MTR STATIONS (REAL FOOTPRINTS)
# ============================================================
stations = ox.features_from_point(
    (lat, lon), tags={"railway":"station"}, dist=2000
).to_crs(3857)

stations["name"] = stations.get("name:en").fillna(stations.get("name"))
stations["centroid"] = stations.geometry.centroid
stations["dist"] = stations["centroid"].distance(site_point)

stations = (
    stations.dropna(subset=["name"])
    .sort_values("dist")
    .head(2)
)

# ============================================================
# BUS STOPS (CLUSTERED)
# ============================================================
bus_stops = ox.features_from_point(
    (lat, lon), tags={"highway":"bus_stop"}, dist=900
).to_crs(3857)

if len(bus_stops) > 6:
    coords = np.array([[g.x,g.y] for g in bus_stops.geometry])
    bus_stops["cluster"] = KMeans(n_clusters=6, random_state=0).fit(coords).labels_
    bus_stops = bus_stops.groupby("cluster").first()

# ============================================================
# WALK ROUTES TO MTR
# ============================================================
G = ox.graph_from_point((lat, lon), dist=2000, network_type="walk")
site_node = ox.distance.nearest_nodes(G, lon, lat)

routes = []
for _, st in stations.iterrows():
    ll = gpd.GeoSeries([st.centroid], crs=3857).to_crs(4326).iloc[0]
    st_node = ox.distance.nearest_nodes(G, ll.x, ll.y)
    path = nx.shortest_path(G, site_node, st_node, weight="length")
    routes.append(ox.routing.route_to_gdf(G, path).to_crs(3857))

# ============================================================
# PLACE LABELS
# ============================================================
labels = ox.features_from_point(
    (lat, lon), dist=800, tags=LABEL_RULES
).to_crs(3857)

labels["label"] = labels.get("name:en").fillna(labels.get("name"))
labels = labels.dropna(subset=["label"]).drop_duplicates("label").head(24)

# ============================================================
# PLOT
# ============================================================
fig, ax = plt.subplots(figsize=(12,12))

cx.add_basemap(ax, source=cx.providers.CartoDB.Positron, zoom=16, alpha=0.95)

ax.set_xlim(site_point.x-MAP_HALF_SIZE, site_point.x+MAP_HALF_SIZE)
ax.set_ylim(site_point.y-MAP_HALF_SIZE, site_point.y+MAP_HALF_SIZE)
ax.set_aspect("equal")
ax.autoscale(False)

residential.plot(ax=ax,color="#f2c6a0",alpha=0.75)
industrial.plot(ax=ax,color="#b39ddb",alpha=0.75)
parks.plot(ax=ax,color="#b7dfb9",alpha=0.9)
schools.plot(ax=ax,color="#9ecae1",alpha=0.9)
buildings.plot(ax=ax,color="#d9d9d9",alpha=0.35)

for r in routes:
    r.plot(ax=ax,color="#005eff",linewidth=2.2,linestyle="--")

bus_stops.plot(ax=ax,color="#0d47a1",markersize=35,zorder=9)

# MTR FOOTPRINTS (ORANGE)
stations.plot(
    ax=ax,
    facecolor=MTR_COLOR,
    edgecolor="none",
    linewidth=0,
    alpha=0.9,
    zorder=10
)


site_gdf.plot(ax=ax,facecolor="#e53935",edgecolor="darkred",linewidth=2,zorder=11)
ax.text(site_geom.centroid.x, site_geom.centroid.y,"SITE",
        color="white",weight="bold",ha="center",va="center",zorder=12)

# MTR NAMES (SAME STYLE AS OTHER LABELS)
for _, st in stations.iterrows():
    ax.text(
        st.centroid.x,
        st.centroid.y + 120,
        wrap_label(st["name"], 18),
        fontsize=9,
        ha="center",
        va="center",
        bbox=dict(facecolor="white", edgecolor="none", alpha=0.8, pad=1.0),
        zorder=12,
        clip_on=True
    )

# PLACE LABELS
offsets=[(0,35),(0,-35),(35,0),(-35,0),(25,25),(-25,25)]
placed=[]

for i,(_,row) in enumerate(labels.iterrows()):
    p=row.geometry.representative_point()
    if p.distance(site_point)<120: continue
    if any(p.distance(pp)<120 for pp in placed): continue
    dx,dy=offsets[i%len(offsets)]
    ax.text(
        p.x+dx,p.y+dy,
        wrap_label(row["label"],18),
        fontsize=9,
        ha="center",va="center",
        bbox=dict(facecolor="white",edgecolor="none",alpha=0.8,pad=1.0),
        zorder=12,clip_on=True
    )
    placed.append(p)

# INFO BOX
ax.text(
    0.015,0.985,
    f"Lot: {LOT_ID}\n"
    f"OZP Plan: {primary['PLAN_NO']}\n"
    f"Zoning: {zone}\n"
    f"Site Type: {SITE_TYPE}\n",
    transform=ax.transAxes,
    ha="left",va="top",fontsize=9.2,
    bbox=dict(facecolor="white",edgecolor="black",pad=6)
)

# LEGEND
ax.legend(
    handles=[
        mpatches.Patch(color="#f2c6a0",label="Residential"),
        mpatches.Patch(color="#b39ddb",label="Industrial / Commercial"),
        mpatches.Patch(color="#b7dfb9",label="Public Park"),
        mpatches.Patch(color="#9ecae1",label="School / Institution"),
        mpatches.Patch(color=MTR_COLOR,label="MTR Station"),
        mpatches.Patch(color="#e53935",label="Site"),
        mpatches.Patch(color="#005eff",label="Pedestrian Route to MTR"),
        mpatches.Patch(color="#0d47a1",label="Bus Stop"),
    ],
    loc="lower left",
    bbox_to_anchor=(0.02,0.08),
    fontsize=8.5,
    framealpha=0.95
)

ax.set_title("Automated Site Context Analysis (Building-Type Driven)",fontsize=15,weight="bold")
ax.set_axis_off()

plt.savefig("SITE_CONTEXT_FINAL_BUILDING_LOGIC_COMPLETE.pdf",dpi=400)
plt.show()
