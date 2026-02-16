import zipfile
import os

ZIP_NAME = "/content/Building_GEOJSON (1).zip"
EXTRACT_DIR = "building_data"

os.makedirs(EXTRACT_DIR, exist_ok=True)

with zipfile.ZipFile(ZIP_NAME, 'r') as zip_ref:
    zip_ref.extractall(EXTRACT_DIR)

print("Extracted files:")
for root, dirs, files in os.walk(EXTRACT_DIR):
    for f in files:
        print(os.path.join(root, f))
# ============================================================
# INSTALLS
# ============================================================
!pip install -q geopandas osmnx shapely pyproj requests matplotlib pandas

# ============================================================
# IMPORTS
# ============================================================
import osmnx as ox
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import requests
import pandas as pd
import math

from shapely.geometry import Point, Polygon
from pyproj import Transformer
from matplotlib.patches import Wedge, Patch

ox.settings.use_cache = True
ox.settings.log_console = False

# ============================================================
# USER INPUT
# ============================================================
LOT_ID = "IL 1657"
FETCH_RADIUS = 1500
MAP_RADIUS = 800
VIEW_RADIUS = 360
ARC_WIDTH = 40
SECTOR_SIZE = 20
SITE_HEIGHT_LIMIT = 200  # mPD

# ============================================================
# LOT → COORDINATES
# ============================================================
def resolve_lot(lot):
    url = f"https://mapapi.geodata.gov.hk/gs/api/v1.0.0/lus/lot/SearchNumber?text={lot.replace(' ','%20')}"
    r = requests.get(url)
    best = max(r.json()["candidates"], key=lambda x: x["score"])
    return best["location"]["x"], best["location"]["y"]

x2326, y2326 = resolve_lot(LOT_ID)
lon, lat = Transformer.from_crs(2326, 4326, always_xy=True).transform(x2326, y2326)

# ============================================================
# SITE POLYGON
# ============================================================
site_building = ox.features_from_point(
    (lat, lon),
    dist=60,
    tags={"building": True}
).to_crs(3857)

if len(site_building):
    site_geom = (
        site_building.assign(area=site_building.area)
        .sort_values("area", ascending=False)
        .geometry.iloc[0]
    )
else:
    site_geom = gpd.GeoSeries([Point(lon, lat)], crs=4326).to_crs(3857).iloc[0].buffer(25)

center = site_geom.centroid
analysis_circle = center.buffer(MAP_RADIUS)

# ============================================================
# CONTEXT DATA
# ============================================================
def fetch_layer(tags):
    gdf = ox.features_from_point((lat, lon), dist=FETCH_RADIUS, tags=tags).to_crs(3857)
    return gdf[gdf.intersects(analysis_circle)]

buildings = fetch_layer({"building": True})
parks = fetch_layer({"leisure":"park","landuse":"grass","natural":"wood"})
water = fetch_layer({"waterway":True,"natural":"water"})

# ============================================================
# HEIGHT DATA
# ============================================================
LANDSD_FILE = "/content/building_data/Building_Outline_Public_v20260119_Building_converted.geojson"

landsd = gpd.read_file(LANDSD_FILE).to_crs(3857)
landsd["HEIGHT_M"] = landsd["TopHeight"] - landsd["BaseHeight"]
landsd = landsd[landsd["HEIGHT_M"] > 5]
nearby = landsd[landsd.intersects(analysis_circle)].copy()

# ============================================================
# CREATE FIGURE
# ============================================================
fig, ax = plt.subplots(figsize=(12,12))
ax.set_facecolor("#f2f2f2")
ax.set_xlim(center.x - MAP_RADIUS, center.x + MAP_RADIUS)
ax.set_ylim(center.y - MAP_RADIUS, center.y + MAP_RADIUS)
ax.set_aspect("equal")

# ============================================================
# BASE MAP
# ============================================================
if len(parks):
    parks.plot(ax=ax, color="#b8c8a0", edgecolor="none", zorder=1)

if len(water):
    water.plot(ax=ax, color="#6bb6d9", edgecolor="none", zorder=2)

buildings.plot(ax=ax, color="#e3e3e3", edgecolor="none", zorder=3)

# ============================================================
# RADIAL GUIDES
# ============================================================
for angle in range(0, 360, SECTOR_SIZE):
    rad = np.radians(angle)
    ax.plot(
        [center.x, center.x + MAP_RADIUS*np.cos(rad)],
        [center.y, center.y + MAP_RADIUS*np.sin(rad)],
        linestyle=(0,(2,4)),
        linewidth=0.8,
        color="#d49a2a",
        alpha=0.35,
        zorder=4
    )

# ============================================================
# MPD RINGS + LABELS
# ============================================================
for d in [80,160,200]:
    circle = center.buffer(d)
    gpd.GeoSeries([circle], crs=3857).boundary.plot(
        ax=ax,
        linestyle=(0,(4,4)),
        linewidth=1.2,
        color="#555555",
        alpha=0.9,
        zorder=5
    )

    ax.text(
        center.x + d,
        center.y,
        f"{d} mPD",
        fontsize=8,
        weight="bold",
        color="white",
        bbox=dict(facecolor="black", edgecolor="none", pad=2),
        zorder=6
    )

# ============================================================
# SECTOR FUNCTION
# ============================================================
def create_sector(center, radius, start_angle, end_angle):
    angles = np.linspace(start_angle, end_angle, 40)
    points = [(center.x, center.y)]
    for angle in angles:
        rad = np.radians(angle)
        x = center.x + radius * np.cos(rad)
        y = center.y + radius * np.sin(rad)
        points.append((x, y))
    return Polygon(points)

# ============================================================
# METRIC COLLECTION
# ============================================================
sector_data = []

for angle in range(0, 360, SECTOR_SIZE):
    start = angle
    end = angle + SECTOR_SIZE
    sector = create_sector(center, VIEW_RADIUS, start, end)
    sector_area = sector.area

    green_area = parks.intersection(sector).area.sum() if len(parks) else 0
    water_area = water.intersection(sector).area.sum() if len(water) else 0
    building_area = buildings.intersection(sector).area.sum() if len(buildings) else 0

    green_ratio = green_area / sector_area if sector_area else 0
    water_ratio = water_area / sector_area if sector_area else 0
    building_ratio = building_area / sector_area if sector_area else 0

    sector_heights = nearby[nearby.intersects(sector)]
    avg_height = sector_heights["HEIGHT_M"].mean() if len(sector_heights) else 0

    sector_data.append({
        "start": start,
        "end": end,
        "green": green_ratio,
        "water": water_ratio,
        "building": building_ratio,
        "avg_height": avg_height
    })

df = pd.DataFrame(sector_data)

# ============================================================
# NORMALIZATION
# ============================================================
def normalize(series):
    if series.max() - series.min() == 0:
        return series * 0
    return (series - series.min()) / (series.max() - series.min())

df["green_n"] = normalize(df["green"])
df["water_n"] = normalize(df["water"])
df["height_n"] = normalize(df["avg_height"])
df["density_n"] = normalize(df["building"])

# ============================================================
# SCORING
# ============================================================
df["city_score"] = df["height_n"] * df["density_n"]
df["green_score"] = df["green_n"]
df["water_score"] = df["water_n"]
df["open_score"] = (1 - df["density_n"]) * (1 - df["height_n"])

df["view"] = df[["green_score","water_score","city_score","open_score"]].idxmax(axis=1)
df["view"] = df["view"].str.replace("_score","").str.upper()

# ============================================================
# MERGE CONTINUOUS SECTORS (WRAP SAFE)
# ============================================================
merged = []
current_start = df.iloc[0]["start"]
current_end = df.iloc[0]["end"]
current_type = df.iloc[0]["view"]

for i in range(1, len(df)):
    row = df.iloc[i]
    if row["view"] == current_type:
        current_end = row["end"]
    else:
        merged.append((current_start, current_end, current_type))
        current_start = row["start"]
        current_end = row["end"]
        current_type = row["view"]

merged.append((current_start, current_end, current_type))

if merged[0][2] == merged[-1][2]:
    merged[0] = (merged[-1][0], merged[0][1], merged[0][2])
    merged.pop()

# ============================================================
# DRAW VIEW ARCS + LABELS
# ============================================================
color_map = {
    "GREEN": "#3dbb74",
    "WATER": "#4fa3d1",
    "CITY": "#e75b8c",
    "OPEN": "#f0a25a"
}

for start, end, view_type in merged:

    arc = Wedge(
        (center.x, center.y),
        VIEW_RADIUS,
        start,
        end,
        width=ARC_WIDTH,
        facecolor=color_map[view_type],
        edgecolor="white",
        linewidth=2,
        zorder=7
    )
    ax.add_patch(arc)

    mid_angle = (start + end) / 2
    rad = np.radians(mid_angle)
    label_radius = VIEW_RADIUS - ARC_WIDTH/2

    lx = center.x + label_radius * np.cos(rad)
    ly = center.y + label_radius * np.sin(rad)

    rotation = mid_angle - 90
    if 90 < mid_angle < 270:
        rotation += 180

    if (end - start) >= SECTOR_SIZE:
        ax.text(
            lx,
            ly,
            f"{view_type} VIEW",
            fontsize=10,
            weight="bold",
            color="white",
            ha="center",
            va="center",
            rotation=rotation,
            rotation_mode="anchor",
            zorder=8
        )

# ============================================================
# HEIGHT LABELS
# ============================================================
top_buildings = nearby.sort_values("HEIGHT_M", ascending=False).head(25)

for _, row in top_buildings.iterrows():
    centroid = row.geometry.centroid
    ax.text(
        centroid.x,
        centroid.y,
        f"{row['HEIGHT_M']:.1f} m",
        fontsize=7,
        color="white",
        bbox=dict(facecolor="black", edgecolor="none", pad=1.5),
        zorder=12
    )

# ============================================================
# SITE
# ============================================================
gpd.GeoSeries([site_geom]).plot(
    ax=ax,
    facecolor="#e74c3c",
    edgecolor="white",
    linewidth=1.5,
    zorder=13
)

ax.text(
    center.x,
    center.y - 35,
    "SITE",
    fontsize=12,
    weight="bold",
    ha="center",
    va="top",
    zorder=14
)

# ============================================================
# SITE HEIGHT LIMIT BOX
# ============================================================
site_storeys = int(site_bhc["BHC_VALUE_NUM"].iloc[0])

ax.text(
    center.x + MAP_RADIUS*0.55,
    center.y + MAP_RADIUS*0.75,
    f"SITE HEIGHT LIMIT\n{site_storeys} STOREYS",
    fontsize=10,
    weight="bold",
    bbox=dict(facecolor="white", edgecolor="black", boxstyle="round,pad=0.5"),
    zorder=20
)

# ============================================================
# LEGEND
# ============================================================
legend_elements = [
    Patch(facecolor="#3dbb74", label="Green View"),
    Patch(facecolor="#4fa3d1", label="Water View"),
    Patch(facecolor="#e75b8c", label="City View"),
    Patch(facecolor="#f0a25a", label="Open View"),
]

ax.legend(
    handles=legend_elements,
    loc="lower right",
    frameon=True,
    facecolor="white",
    edgecolor="#444444",
    framealpha=0.95,
    fontsize=9
)

# ============================================================
# FINAL
# ============================================================
ax.set_title("SITE ANALYSIS – View Analysis (Fully Automated)", fontsize=16, weight="bold")
ax.set_axis_off()
plt.tight_layout()
plt.show()
