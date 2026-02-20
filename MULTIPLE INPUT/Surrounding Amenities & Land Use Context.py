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
# USER INPUT CONFIGURATION
# ============================================================

INPUT_MODE = "SINGLE"   # "SINGLE" or "MULTIPLE"

SINGLE_QUERY = {
    "type": "LOT",
    "value": "IL 1657"
}

MULTIPLE_QUERIES = [
    {"type": "LOT", "value": "IL 1657"},
    {"type": "LOT", "value": "IL 904"}
]

FETCH_RADIUS = 1500
MAP_HALF_SIZE = 900
OZP_ZONE_PATH = "/content/extracted_data/Statutory Plan GIS Data GeoJSON/ZONE.json"

MTR_COLOR = "#ffd166"


# ============================================================
# UNIVERSAL HK RESOLVER
# ============================================================

def resolve_query(data_type, value):

    base_url = "https://mapapi.geodata.gov.hk/gs/api/v1.0.0"
    data_type = data_type.upper().strip()

    try:
        if data_type == "LOT":
            url = f"{base_url}/lus/lot/SearchNumber?text={value.replace(' ','%20')}"
        else:
            url = f"{base_url}/lus/{data_type.lower()}/Search?value={value}"

        r = requests.get(url)
        if r.status_code != 200:
            return None

        data = r.json()
        if "candidates" not in data or len(data["candidates"]) == 0:
            return None

        best = max(data["candidates"], key=lambda x: x["score"])

        x2326 = best["location"]["x"]
        y2326 = best["location"]["y"]

        lon, lat = Transformer.from_crs(
            2326, 4326, always_xy=True
        ).transform(x2326, y2326)

        return lon, lat

    except:
        return None


# ============================================================
# TEXT HELPERS
# ============================================================

def wrap_label(text, width=18):
    return "\n".join(textwrap.wrap(str(text), width))

def get_constraint_text(row):
    for k in ["DESC_ENG", "NOTE_ENG", "REMARKS", "CONSTRAINT", "ANNOTATION"]:
        if k in row and isinstance(row[k], str) and row[k].strip():
            return row[k]
    return "No special statutory planning constraints identified."

def infer_site_type(zone):
    if zone.startswith("R"): return "RESIDENTIAL"
    if zone.startswith("C"): return "COMMERCIAL"
    if zone.startswith("G"): return "INSTITUTIONAL"
    if "HOTEL" in zone.upper() or zone.startswith("OU"): return "HOTEL"
    return "MIXED"

def context_rules(site_type):
    if site_type == "RESIDENTIAL":
        return {"amenity":["school","college","university"],"leisure":["park"],"place":["neighbourhood"]}
    if site_type == "COMMERCIAL":
        return {"amenity":["bank","restaurant","market"],"railway":["station"]}
    if site_type == "INSTITUTIONAL":
        return {"amenity":["school","college","hospital"],"leisure":["park"]}
    return {"amenity":True,"leisure":True}


# ============================================================
# RESOLVE INPUTS
# ============================================================

locations = []

if INPUT_MODE == "SINGLE":
    coords = resolve_query(SINGLE_QUERY["type"], SINGLE_QUERY["value"])
    if coords:
        locations.append((SINGLE_QUERY["value"], coords))

elif INPUT_MODE == "MULTIPLE":
    for q in MULTIPLE_QUERIES:
        coords = resolve_query(q["type"], q["value"])
        if coords:
            locations.append((q["value"], coords))

if len(locations) == 0:
    print("No valid inputs found.")


# ============================================================
# LOAD OZP DATA ONCE
# ============================================================

ozp = gpd.read_file(OZP_ZONE_PATH).to_crs(3857)


# ============================================================
# MAIN LOOP
# ============================================================

for LOT_ID, coords in locations:

    print(f"Running analysis for {LOT_ID}")

    lon, lat = coords
    site_point = gpd.GeoSeries([Point(lon, lat)], crs=4326).to_crs(3857).iloc[0]

    # --------------------------------------------------------
    # ZONING
    # --------------------------------------------------------

    primary = ozp[ozp.contains(site_point)]

    if primary.empty:
        print("No zoning polygon found.")
        continue

    primary = primary.iloc[0]
    zone = primary["ZONE_LABEL"]
    SITE_TYPE = infer_site_type(zone)
    LABEL_RULES = context_rules(SITE_TYPE)

    # --------------------------------------------------------
    # FETCH OSM DATA
    # --------------------------------------------------------

    polygons = ox.features_from_point(
        (lat, lon),
        dist=FETCH_RADIUS,
        tags={"landuse":True,"leisure":True,"amenity":True,"building":True}
    ).to_crs(3857)

    residential = polygons[polygons.get("landuse")=="residential"]
    industrial  = polygons[polygons.get("landuse").isin(["industrial","commercial"])]
    parks       = polygons[polygons.get("leisure")=="park"]
    schools     = polygons[polygons.get("amenity").isin(["school","college","university"])]
    buildings   = polygons[polygons.get("building").notnull()]

    # --------------------------------------------------------
    # SITE FOOTPRINT
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # MTR STATIONS
    # --------------------------------------------------------

    stations = ox.features_from_point(
        (lat, lon), tags={"railway":"station"}, dist=2000
    ).to_crs(3857)

    if not stations.empty:
        stations["name"] = stations.get("name:en").fillna(stations.get("name"))
        stations["centroid"] = stations.geometry.centroid
        stations["dist"] = stations["centroid"].distance(site_point)
        stations = stations.dropna(subset=["name"]).sort_values("dist").head(2)

    # --------------------------------------------------------
    # BUS STOPS (CLUSTERED)
    # --------------------------------------------------------

    bus_stops = ox.features_from_point(
        (lat, lon), tags={"highway":"bus_stop"}, dist=900
    ).to_crs(3857)

    if len(bus_stops) > 6:
        coords_array = np.array([[g.x,g.y] for g in bus_stops.geometry])
        bus_stops["cluster"] = KMeans(n_clusters=6, random_state=0).fit(coords_array).labels_
        bus_stops = bus_stops.groupby("cluster").first()

    # --------------------------------------------------------
    # WALK ROUTES TO MTR
    # --------------------------------------------------------

    routes = []

    if not stations.empty:
        G = ox.graph_from_point((lat, lon), dist=2000, network_type="walk")
        site_node = ox.distance.nearest_nodes(G, lon, lat)

        for _, st in stations.iterrows():
            ll = gpd.GeoSeries([st.centroid], crs=3857).to_crs(4326).iloc[0]
            st_node = ox.distance.nearest_nodes(G, ll.x, ll.y)
            path = nx.shortest_path(G, site_node, st_node, weight="length")
            routes.append(ox.routing.route_to_gdf(G, path).to_crs(3857))

    # --------------------------------------------------------
    # PLACE LABELS
    # --------------------------------------------------------

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

# ============================================================
# DRAW PLACE LABELS
# ============================================================

offsets = [(0,35),(0,-35),(35,0),(-35,0),(25,25),(-25,25)]
placed = []

for i, (_, row) in enumerate(labels.iterrows()):
    p = row.geometry.representative_point()

    if p.distance(site_point) < 140:
        continue

    if any(p.distance(pp) < 120 for pp in placed):
        continue

    dx, dy = offsets[i % len(offsets)]

    ax.text(
        p.x + dx,
        p.y + dy,
        wrap_label(row["label"], 18),
        fontsize=9,
        ha="center",
        va="center",
        bbox=dict(
            facecolor="white",
            edgecolor="none",
            alpha=0.85,
            boxstyle="round,pad=0.25"
        ),
        zorder=12,
        clip_on=True
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
