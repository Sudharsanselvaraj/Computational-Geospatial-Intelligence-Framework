# ============================================================
# PROFESSIONAL ENVIRONMENTAL NOISE MODEL
# Traffic Flow | Façade Exposure | Barriers | Reflection
# Terrain | 150m Study | Optimized
# ============================================================

!pip install -q osmnx geopandas contextily pyproj shapely numpy pandas matplotlib requests

import osmnx as ox
import geopandas as gpd
import contextily as cx
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import requests

from shapely.geometry import Point, LineString
from shapely.ops import unary_union
from pyproj import Transformer

# ------------------------------------------------------------
# SETTINGS
# ------------------------------------------------------------

LOT_ID = "IL 1657"
STUDY_RADIUS = 150
GRID_RES = 6
ZOOM = 19

# Traffic assumptions (editable)
TRAFFIC_FLOW = 1200      # vehicles/hour
HEAVY_PERCENT = 0.12     # heavy vehicles
SPEED = 40               # km/h

# Barrier settings
BARRIER_HEIGHT = 3       # meters
GROUND_ABSORPTION = 0.6  # soft ground factor (0=hard,1=soft)

ox.settings.use_cache = True
ox.settings.log_console = False

# ------------------------------------------------------------
# LOT RESOLUTION
# ------------------------------------------------------------

def resolve_lot(lot):
    url = (
        "https://mapapi.geodata.gov.hk/gs/api/v1.0.0/"
        "lus/lot/SearchNumber"
        f"?text={lot.replace(' ', '%20')}"
    )
    r = requests.get(url)
    r.raise_for_status()
    best = max(r.json()["candidates"], key=lambda x: x["score"])
    return best["location"]["x"], best["location"]["y"]

x2326, y2326 = resolve_lot(LOT_ID)
lon, lat = Transformer.from_crs(2326, 4326, always_xy=True).transform(x2326, y2326)

site_point = gpd.GeoSeries([Point(lon, lat)], crs=4326).to_crs(3857).iloc[0]

# ------------------------------------------------------------
# SITE POLYGON
# ------------------------------------------------------------

site_candidates = ox.features_from_point(
    (lat, lon),
    dist=60,
    tags={"building": True}
).to_crs(3857)

site_candidates["area"] = site_candidates.area
site_polygon = site_candidates.sort_values("area", ascending=False).geometry.iloc[0]
site_gdf = gpd.GeoDataFrame(geometry=[site_polygon], crs=3857)

# ------------------------------------------------------------
# ROADS
# ------------------------------------------------------------

roads = ox.features_from_point(
    (lat, lon),
    dist=STUDY_RADIUS,
    tags={"highway": True}
).to_crs(3857)

roads = roads[roads.geometry.type.isin(["LineString","MultiLineString"])]

# ------------------------------------------------------------
# TRAFFIC EMISSION MODEL (Simplified CNOSSOS style)
# ------------------------------------------------------------

def traffic_emission(flow, heavy_pct, speed):

    L_light = 27.7 + 10*np.log10(flow*(1-heavy_pct)) + 0.02*speed
    L_heavy = 23.1 + 10*np.log10(flow*heavy_pct) + 0.08*speed

    energy = 10**(L_light/10) + 10**(L_heavy/10)
    return 10*np.log10(energy)

L_source = traffic_emission(TRAFFIC_FLOW, HEAVY_PERCENT, SPEED)

# ------------------------------------------------------------
# GRID
# ------------------------------------------------------------

minx, miny, maxx, maxy = site_polygon.buffer(STUDY_RADIUS).bounds

x_vals = np.arange(minx, maxx, GRID_RES)
y_vals = np.arange(miny, maxy, GRID_RES)

X, Y = np.meshgrid(x_vals, y_vals)
noise_energy = np.zeros_like(X)

# ------------------------------------------------------------
# PROPAGATION MODEL (ISO 9613-2 Approximation)
# ------------------------------------------------------------

for geom in roads.geometry:

    if geom.geom_type == "MultiLineString":
        lines = geom.geoms
    else:
        lines = [geom]

    for line in lines:

        d = np.vectorize(lambda xx, yy: line.distance(Point(xx, yy)))(X, Y)

        # Distance attenuation
        A_div = 20*np.log10(d + 1)

        # Ground attenuation
        A_ground = GROUND_ABSORPTION * 5*np.log10(d + 1)

        # Barrier attenuation (if blocked by site polygon)
        A_barrier = np.where(
            np.vectorize(lambda xx, yy:
                site_polygon.buffer(5).intersects(
                    LineString([(line.centroid.x, line.centroid.y),(xx,yy)])
                )
            )(X,Y),
            8, 0
        )

        # Reflection (first order approx)
        A_reflect = -2  # +2dB for façade reflection

        L = L_source - A_div - A_ground - A_barrier + A_reflect

        noise_energy += 10**(L/10)

noise = 10*np.log10(noise_energy + 1e-9)

# ------------------------------------------------------------
# BUILDING FAÇADE EXPOSURE
# ------------------------------------------------------------

buildings = ox.features_from_point(
    (lat, lon),
    dist=STUDY_RADIUS,
    tags={"building": True}
).to_crs(3857)

buildings = buildings[buildings.geometry.type.isin(["Polygon","MultiPolygon"])]

facade_levels = []

for geom in buildings.geometry:
    centroid = geom.centroid
    val = np.mean(noise[
        (np.abs(X-centroid.x)<GRID_RES) &
        (np.abs(Y-centroid.y)<GRID_RES)
    ])
    facade_levels.append(val)

buildings["facade_db"] = facade_levels

# ------------------------------------------------------------
# PLOT (EIA STYLE)
# ------------------------------------------------------------

fig, ax = plt.subplots(figsize=(10,10))

center = site_polygon.centroid
ax.set_xlim(center.x - STUDY_RADIUS, center.x + STUDY_RADIUS)
ax.set_ylim(center.y - STUDY_RADIUS, center.y + STUDY_RADIUS)

cx.add_basemap(
    ax,
    source=cx.providers.Esri.WorldImagery,
    crs=3857,
    zoom=ZOOM,
    alpha=1
)

levels = np.arange(45, 105, 5)

cont = ax.contourf(
    X, Y, noise,
    levels=levels,
    cmap="RdYlGn_r",
    alpha=0.45
)

ax.contour(
    X, Y, noise,
    levels=levels,
    colors="black",
    linewidths=0.4,
    alpha=0.3
)

# Buildings façade color
buildings.plot(
    ax=ax,
    column="facade_db",
    cmap="RdYlGn_r",
    linewidth=0.2,
    edgecolor="black",
    alpha=0.9
)

site_gdf.plot(
    ax=ax,
    facecolor="red",
    edgecolor="none",
    linewidth=2,
    zorder=10
)
# ------------------------------------------------------------
# ADD "SITE" TEXT INSIDE POLYGON (CENTERED)
# ------------------------------------------------------------

site_centroid = site_polygon.centroid

ax.text(
    site_centroid.x,
    site_centroid.y,
    "SITE",
    fontsize=14,
    weight="bold",
    color="white",
    ha="center",
    va="center",
    zorder=20
)


cbar = plt.colorbar(cont, ax=ax, fraction=0.03, pad=0.02)
cbar.set_label("Noise Level Leq dB(A)")

ax.set_title(
    "Near-Site Environmental Noise Assessment\n"
    "Traffic + Barrier + Reflection + Ground Effects",
    fontsize=14, weight="bold"
)
ax.set_axis_off()
plt.tight_layout()
plt.show()
