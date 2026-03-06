# ============================================================
# INSTALL (Run once)
# ============================================================
!pip install -q geopandas osmnx contextily shapely pyproj requests matplotlib pillow

# ============================================================
# IMPORTS
# ============================================================
import osmnx as ox
import geopandas as gpd
import contextily as cx
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.lines as mlines
import numpy as np
import requests

from shapely.geometry import Point, box
from pyproj import Transformer
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
from PIL import Image

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
    {"type": "PRN", "value": "12345678"},
    {"type": "STT", "value": "STT1001"}
]

MAP_RADIUS = 3000

COLOR_ROADS      = "#e85d9e"
COLOR_WATER      = "#6fa8dc"
COLOR_BUILDINGS  = "#d6d6d6"
COLOR_SITE       = "#FF0000"
COLOR_LIGHT_RAIL = "#D3A809"


# ============================================================
# MTR LINE COLOR MAP
# ============================================================

MTR_LINE_COLORS = {
    "island":              "#007DC5",
    "kwun tong":           "#00AB4E",
    "tsuen wan":           "#ED1D24",
    "tseung kwan o":       "#7D499D",
    "tung chung":          "#F7943E",
    "east rail":           "#5EB6E4",
    "tuen ma":             "#923011",
    "south island":        "#BAC429",
    "airport express":     "#888B8D",
    "lantau and airport":  "#888B8D",
    "guangzhoushen":       "#007DC5",
}

DEFAULT_MTR_COLOR = "#3f78b5"

# Official display names for legend (ordered)
MTR_LEGEND_LINES = [
    ("island",            "#007DC5", "Island Line"),
    ("kwun tong",         "#00AB4E", "Kwun Tong Line"),
    ("tsuen wan",         "#ED1D24", "Tsuen Wan Line"),
    ("tseung kwan o",     "#7D499D", "Tseung Kwan O Line"),
    ("tung chung",        "#F7943E", "Tung Chung Line"),
    ("east rail",         "#5EB6E4", "East Rail Line"),
    ("tuen ma",           "#923011", "Tuen Ma Line"),
    ("south island",      "#BAC429", "South Island Line"),
    ("airport express",   "#888B8D", "Airport Express"),
    ("lantau and airport","#888B8D", "Airport Express"),
    ("guangzhoushen",     "#007DC5", "Express Rail Link"),
]


def get_mtr_color(name: str) -> str:
    name_lower = name.lower()
    for key, color in MTR_LINE_COLORS.items():
        if key in name_lower:
            return color
    return DEFAULT_MTR_COLOR


# ============================================================
# LOAD MTR LOGO
# ============================================================

# Change this to your uploaded MTR logo filename
MTR_LOGO_PATH = "/content/HK_MTR_logo.png"

try:
    mtr_logo_img   = Image.open(MTR_LOGO_PATH).convert("RGBA")
    mtr_logo_array = np.array(mtr_logo_img)
    MTR_LOGO_LOADED = True
    print(f"MTR logo loaded from: {MTR_LOGO_PATH}")
except Exception as e:
    MTR_LOGO_LOADED = False
    print(f"MTR logo not found ({e}). Falling back to drawn roundel.")


# ============================================================
# DRAWN ROUNDEL FALLBACK  (used only if logo fails to load)
# ============================================================

def draw_mtr_roundel_fallback(ax, x, y, size=60, color="#ED1D24", zorder=9):
    ax.add_patch(plt.Circle((x, y), size, color=color, zorder=zorder))
    bar_w = size * 2.0
    bar_h = size * 0.55
    ax.add_patch(plt.Rectangle((x - bar_w/2, y - bar_h/2), bar_w, bar_h,
                                color="white", zorder=zorder + 1))
    ax.add_patch(plt.Circle((x, y), size * 0.55, color="white", zorder=zorder + 2))
    ax.add_patch(plt.Rectangle((x - bar_w/2, y - bar_h/2), bar_w, bar_h,
                                color=color, zorder=zorder + 3))


# ============================================================
# DRAW STATION MARKER  (logo image or fallback roundel)
# ============================================================

def draw_station(ax, x, y, zoom=0.055, fallback_color="#ED1D24", zorder=9):
    """
    Place MTR logo image at map coordinate (x, y).
    Adjust zoom to resize:
        0.03  → very small
        0.055 → medium (default)
        0.10  → large
        0.15  → very large
    """
    if MTR_LOGO_LOADED:
        imagebox = OffsetImage(mtr_logo_array, zoom=zoom)
        imagebox.image.axes = ax
        ab = AnnotationBbox(
            imagebox,
            (x, y),
            xycoords='data',
            frameon=False,
            zorder=zorder
        )
        ax.add_artist(ab)
    else:
        draw_mtr_roundel_fallback(ax, x, y, size=60,
                                  color=fallback_color, zorder=zorder)


# ============================================================
# UNIVERSAL SAFE HK LANDSD RESOLVER
# ============================================================

def resolve_query(data_type, value):
    base_url  = "https://mapapi.geodata.gov.hk/gs/api/v1.0.0"
    data_type = data_type.upper().strip()

    try:
        if data_type == "LOT":
            url = f"{base_url}/lus/lot/SearchNumber?text={value.replace(' ', '%20')}"
        else:
            url = f"{base_url}/lus/{data_type.lower()}/Search?value={value}"

        response = requests.get(url)
        if response.status_code != 200:
            return None

        data = response.json()
        if "candidates" not in data or len(data["candidates"]) == 0:
            return None

        best  = max(data["candidates"], key=lambda x: x.get("score", 0))
        x2326 = best["location"]["x"]
        y2326 = best["location"]["y"]

        lon, lat = Transformer.from_crs(
            2326, 4326, always_xy=True
        ).transform(x2326, y2326)

        return {
            "type":      data_type,
            "value":     value,
            "longitude": lon,
            "latitude":  lat
        }
    except:
        return None


# ============================================================
# RESOLVE INPUTS
# ============================================================

results = []

if INPUT_MODE == "SINGLE":
    result = resolve_query(SINGLE_QUERY["type"], SINGLE_QUERY["value"])
    if result:
        results.append(result)
    else:
        print(f"{SINGLE_QUERY['type']} {SINGLE_QUERY['value']} → Not Found")

elif INPUT_MODE == "MULTIPLE":
    for query in MULTIPLE_QUERIES:
        result = resolve_query(query["type"], query["value"])
        if result:
            results.append(result)
        else:
            print(f"{query['type']} {query['value']} → Not Found")

else:
    print("INPUT_MODE must be SINGLE or MULTIPLE")


# ============================================================
# RUN ANALYSIS FOR EACH VALID INPUT
# ============================================================

if len(results) == 0:
    print("No valid locations to analyse.")


for res in results:

    print(f"\nRunning transport analysis for {res['type']} - {res['value']}")

    lon = res["longitude"]
    lat = res["latitude"]

    site_point = gpd.GeoSeries(
        [Point(lon, lat)], crs=4326
    ).to_crs(3857).iloc[0]


    # --------------------------------------------------------
    # SAFE FETCH FUNCTIONS
    # --------------------------------------------------------

    def safe_fetch(tags):
        try:
            gdf = ox.features_from_point((lat, lon), dist=MAP_RADIUS, tags=tags)
            if not gdf.empty:
                return gdf.to_crs(3857)
            return gpd.GeoDataFrame(geometry=[], crs=3857)
        except:
            return gpd.GeoDataFrame(geometry=[], crs=3857)

    def keep_lines(gdf):
        if not gdf.empty:
            return gdf[gdf.geometry.type.isin(["LineString", "MultiLineString"])]
        return gpd.GeoDataFrame(geometry=[], crs=3857)


    # --------------------------------------------------------
    # FETCH DATA
    # --------------------------------------------------------

    buildings  = safe_fetch({"building": True})
    roads      = keep_lines(safe_fetch({"highway": ["motorway", "trunk", "primary", "secondary"]}))
    light_rail = keep_lines(safe_fetch({"railway": "light_rail"}))
    stations   = safe_fetch({"railway": "station"})
    water      = safe_fetch({"natural": "water"})
    mtr_routes = keep_lines(safe_fetch({"railway": ["rail", "subway"]}))


    # --------------------------------------------------------
    # SITE POLYGON
    # --------------------------------------------------------

    if not buildings.empty:
        distances   = buildings.geometry.distance(site_point)
        nearest_idx = distances.idxmin()
        site_geom   = buildings.loc[nearest_idx, "geometry"]
    else:
        site_geom = site_point.buffer(40)

    site_gdf = gpd.GeoDataFrame(geometry=[site_geom], crs=3857)


    # --------------------------------------------------------
    # PLOT
    # --------------------------------------------------------

    fig, ax = plt.subplots(figsize=(18, 10))
    fig.patch.set_facecolor("#f4f4f4")
    ax.set_facecolor("#f4f4f4")

    cx.add_basemap(ax, source=cx.providers.CartoDB.Positron, zoom=15, alpha=0.5)

    if not buildings.empty:
        buildings.plot(ax=ax, color=COLOR_BUILDINGS, alpha=0.5, zorder=1)

    if not water.empty:
        water.plot(ax=ax, color=COLOR_WATER, alpha=0.8, zorder=2)

    if not roads.empty:
        roads.plot(ax=ax, color=COLOR_ROADS, linewidth=2.2, zorder=3)


    # --------------------------------------------------------
    # MAP EXTENT
    # --------------------------------------------------------

    xmin = site_point.x - 1600
    xmax = site_point.x + 2200
    ymin = site_point.y - 1100
    ymax = site_point.y + 1100

    clip_box = box(xmin, ymin, xmax, ymax)
    clip_gdf = gpd.GeoDataFrame(geometry=[clip_box], crs=3857)


    # --------------------------------------------------------
    # MTR ROUTES — per-line coloring
    # --------------------------------------------------------

    lines_on_map = {}   # color → display_label  (for legend, deduplicated)

    if not mtr_routes.empty:

        mtr_visible = gpd.clip(mtr_routes, clip_gdf)

        if not mtr_visible.empty:

            placed_positions = []
            name_col = "name" if "name" in mtr_visible.columns else None

            if name_col:
                unique_names = mtr_visible[name_col].dropna().unique()

                for name in unique_names:
                    clean_name = ''.join(c for c in name if ord(c) < 128).strip()
                    if clean_name == "":
                        continue

                    line_color = get_mtr_color(clean_name)
                    subset     = mtr_visible[mtr_visible[name_col] == name]

                    subset.plot(ax=ax, color="white",    linewidth=8,   zorder=4)
                    subset.plot(ax=ax, color=line_color, linewidth=4.5, zorder=5)

                    # Track for legend (deduplicate by color)
                    if line_color not in lines_on_map:
                        official_label = clean_name.title()
                        for key, c, label in MTR_LEGEND_LINES:
                            if key in clean_name.lower():
                                official_label = label
                                break
                        lines_on_map[line_color] = official_label

                    # Line label annotation
                    merged = subset.union_all()
                    if merged.length < 600:
                        continue

                    midpoint = merged.interpolate(0.5, normalized=True)
                    offset_y = 0
                    for pt in placed_positions:
                        if midpoint.distance(pt) < 500:
                            offset_y += 150

                    new_point = Point(midpoint.x, midpoint.y + offset_y)
                    placed_positions.append(new_point)

                    if xmin <= new_point.x <= xmax and ymin <= new_point.y <= ymax:
                        ax.text(
                            new_point.x, new_point.y,
                            clean_name.upper(),
                            fontsize=9, weight="bold",
                            color=line_color,
                            ha="center", va="center",
                            zorder=12,
                            bbox=dict(facecolor="white", edgecolor="none", alpha=0.85, pad=2)
                        )

                # Unnamed routes fallback
                unnamed = mtr_visible[mtr_visible[name_col].isna()]
                if not unnamed.empty:
                    unnamed.plot(ax=ax, color="white",           linewidth=8,   zorder=4)
                    unnamed.plot(ax=ax, color=DEFAULT_MTR_COLOR, linewidth=4.5, zorder=5)

            else:
                mtr_visible.plot(ax=ax, color="white",           linewidth=8,   zorder=4)
                mtr_visible.plot(ax=ax, color=DEFAULT_MTR_COLOR, linewidth=4.5, zorder=5)


    # --------------------------------------------------------
    # LIGHT RAIL — official yellow
    # --------------------------------------------------------

    if not light_rail.empty:
        light_rail.plot(ax=ax, color="white",          linewidth=6,   zorder=4)
        light_rail.plot(ax=ax, color=COLOR_LIGHT_RAIL, linewidth=3.5, zorder=5)


    # --------------------------------------------------------
    # STATIONS — MTR logo image (or fallback roundel)
    # --------------------------------------------------------

    if not stations.empty:
        station_pts = stations.copy()
        station_pts["geometry"] = station_pts.centroid

        # Filter to map extent only
        station_pts = station_pts[
            (station_pts.geometry.x >= xmin) & (station_pts.geometry.x <= xmax) &
            (station_pts.geometry.y >= ymin) & (station_pts.geometry.y <= ymax)
        ]

        for _, row in station_pts.iterrows():
            sx, sy = row.geometry.x, row.geometry.y

            # Determine fallback color (used only if logo not loaded)
            fallback_color = "#ED1D24"
            name_val = row.get("name", None)
            if isinstance(name_val, str) and name_val.strip():
                c = get_mtr_color(name_val)
                if c != DEFAULT_MTR_COLOR:
                    fallback_color = c
                elif not mtr_routes.empty and "name" in mtr_routes.columns:
                    pt       = Point(sx, sy)
                    min_dist = float("inf")
                    for lname, grp in mtr_routes.groupby("name"):
                        if not isinstance(lname, str):
                            continue
                        d = grp.union_all().distance(pt)
                        if d < min_dist:
                            min_dist      = d
                            fallback_color = get_mtr_color(lname)

            # ⬇Adjust zoom here to resize the logo
            draw_station(ax, sx, sy, zoom=0.055, fallback_color=fallback_color, zorder=9)


    # --------------------------------------------------------
    # SITE  (drawn last so always visible)
    # --------------------------------------------------------

    site_gdf.plot(ax=ax, facecolor=COLOR_SITE, edgecolor="none", zorder=13)

    centroid = site_geom.centroid
    ax.text(
        centroid.x, centroid.y - 120,
        "SITE",
        fontsize=14, weight="bold",
        ha="center", zorder=14
    )


    # --------------------------------------------------------
    # NORTH ARROW
    # --------------------------------------------------------

    ax.annotate(
        '',
        xy=(0.07, 0.85), xytext=(0.07, 0.80),
        xycoords=ax.transAxes,
        arrowprops=dict(facecolor='black', width=1.5, headwidth=8, headlength=10)
    )
    ax.text(
        0.07, 0.86, "N",
        transform=ax.transAxes,
        ha='center', va='bottom', fontsize=12
    )


    # --------------------------------------------------------
    # EXTENT
    # --------------------------------------------------------

    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)


# --------------------------------------------------------
    # LEGEND — small, clean, deduplicated, ordered
    # --------------------------------------------------------

    legend_handles = []

    # Light Rail
    legend_handles.append(
        mlines.Line2D([], [], color=COLOR_LIGHT_RAIL, linewidth=4, label="Light Rail")
    )

    # MTR lines actually on the map — in official order, deduplicated by color
    seen_colors_legend = set()
    for key, color, label in MTR_LEGEND_LINES:
        if color in lines_on_map and color not in seen_colors_legend:
            legend_handles.append(
                mlines.Line2D([], [], color=color, linewidth=4, label=label)
            )
            seen_colors_legend.add(color)

    # Vehicle roads
    legend_handles.append(
        mlines.Line2D([], [], color=COLOR_ROADS, linewidth=4, label="Vehicle Circulation")
    )

    # Site patch
    legend_handles.append(
        mpatches.Patch(facecolor=COLOR_SITE, label="Site")
    )

    # MTR Station — logo thumbnail if loaded, else small red circle
    if MTR_LOGO_LOADED:
        thumb     = Image.fromarray(mtr_logo_array).resize((20, 20), Image.LANCZOS)
        thumb_arr = np.array(thumb)

        class LogoHandler(mlines.Line2D):
            pass

        import matplotlib.legend_handler as lh

        class HandlerLogo(lh.HandlerBase):
            def create_artists(self, legend, orig_handle,
                               xdescent, ydescent, width, height, fontsize, trans):
                ox_pos = xdescent + width / 2
                oy_pos = ydescent + height / 2
                box = OffsetImage(thumb_arr, zoom=0.8)
                ab  = AnnotationBbox(
                    box, (ox_pos, oy_pos),
                    xycoords=trans,
                    frameon=False
                )
                return [ab]

        logo_handle = LogoHandler([], [], label="MTR Station")
        legend_handles.append(logo_handle)
        handler_map = {LogoHandler: HandlerLogo()}

    else:
        legend_handles.append(
            mlines.Line2D(
                [], [], marker='o', linestyle='None',
                markerfacecolor='#ED1D24',
                markeredgecolor='white',
                markeredgewidth=2,
                markersize=10,
                label="MTR Station"
            )
        )
        handler_map = {}

    legend = ax.legend(
        handles=legend_handles,
        handler_map=handler_map if MTR_LOGO_LOADED else None,
        loc="lower left",
        bbox_to_anchor=(0.02, 0.02),
        frameon=True,
        facecolor="white",
        edgecolor="black",
        fontsize=10,
        title_fontsize=10,
        labelspacing=0.4,
        handlelength=1.8,
        handleheight=1.0,
        borderpad=0.6,
        title="Legend"
    )
    legend.get_frame().set_linewidth(2)

    # --------------------------------------------------------
    # TITLE
    # --------------------------------------------------------

    ax.set_title(
        f"SITE ANALYSIS – Transportation ({res['type']} {res['value']})",
        fontsize=18, weight="bold"
    )

    ax.set_axis_off()
    plt.tight_layout()
    plt.savefig(f"site_analysis_{res['type']}_{res['value']}.png", dpi=300)
    plt.show()
