# Site Analysis – ALKF

> Automated Geospatial Intelligence System for Urban Site Feasibility, Accessibility, Environmental Impact & 360° View Analysis

---

## Overview

**Site Analysis – ALKF** is a fully automated geospatial analysis toolkit designed for professional urban feasibility assessment.

It integrates:

- OpenStreetMap (OSM)
- Government Building Height Data
- Transportation Networks
- Land Use & Amenity Layers
- Spatial Scoring Algorithms
- Traffic Noise Modelling
- Multi-Type Input Resolver (LOT / PRN / STT)

The system produces high-quality professional maps for urban planning and development analysis.

---

# System Architecture

## High-Level Workflow

```
User Input (LOT / PRN / STT)
            │
            ▼
Government GIS Resolver API
            │
            ▼
Coordinate Transformation
(EPSG:2326 → 4326 → 3857)
            │
            ▼
Context Data Extraction
(OSM + Static GIS)
            │
            ├── Land Use
            ├── Amenities
            ├── Transportation Network
            ├── Building Heights
            ├── Noise Sources
            │
            ▼
Spatial Analysis Engine
            │
            ├── Distance Calculations
            ├── Sector-Based View Scoring
            ├── Traffic Noise Modeling
            ├── Accessibility Buffers
            ├── Density Metrics
            │
            ▼
Visualization Engine
(Matplotlib + GeoPandas)
            │
            ▼
Professional Map Output
```

---

#  Repository Structure

```
site-analysis-ALKF/
│
├── Competing Developments Analysis.py
├── Driving Distance Analysis.py
├── Road Traffic Noise Impact.py
├── Surrounding Amenities & Land Use Context.py
├── Transportation Network Analysis.py
├── Walking Distance.py
│
├── building_data/
│   └── Building_Outline_Public.geojson
│
├── outputs/
│   ├── maps/
│   ├── reports/
│   └── charts/
│
└── README.md
```

---

# 🔍 Module Breakdown

---

## Surrounding Amenities & Land Use Context

**Purpose:**  
Evaluate zoning environment and surrounding context.

**Features:**
- Residential / Commercial classification
- Park & green space mapping
- School & institution proximity
- MTR routing
- Bus stop clustering
- Pedestrian path mapping

**Core Engine:**
- OSM spatial filtering
- GeoDataFrame intersections
- NetworkX shortest path routing

---

## Transportation Network Analysis

**Purpose:**  
Assess mobility and connectivity efficiency.

**Features:**
- Drive-time buffers
- Walk-time buffers
- Isochrone generation
- Network graph centrality

**Technology:**
- OSMnx Graph Extraction
- Weighted Edge Routing

---

## Walking Distance Analysis

**Purpose:**  
Measure pedestrian accessibility to amenities.

**Methodology:**
- Extract walkable graph
- Compute nearest node routing
- Generate service buffers
- Amenity density overlay

---

## Driving Distance Analysis

**Purpose:**  
Evaluate vehicular accessibility.

**Methodology:**
- Drive network extraction
- Travel-time weighted routing
- Isochrone visualization
- Major node proximity scoring

---

## Road Traffic Noise Impact

**Purpose:**  
Estimate environmental noise exposure.

**Model Basis:**

```
L = L₀ − 20 log₁₀(r)
```

Where:

- `L₀` = Base traffic noise level  
- `r` = Distance from road source  

**Includes:**
- Road hierarchy weighting
- Distance attenuation modelling
- Exposure zone classification

---

## 360° View Analysis Engine

**Purpose:**  
Classify directional view quality around site.

### Methodology

1. Divide 360° into equal sectors  
2. Compute:
   - Green ratio
   - Water ratio
   - Building density
   - Average building height  
3. Normalize features  
4. Apply weighted scoring  
5. Assign dominant view type  

### Scoring Model

```
Green Score  = green_ratio
Water Score  = water_ratio
City Score   = height_norm × density_norm
Open Score   = (1 - density_norm) × (1 - height_norm)
```

### Output Classes

- GREEN VIEW
- WATER VIEW
- CITY VIEW
- OPEN VIEW

---

# Implementation Status

| Module | Status |
|--------|--------|
| Multi-Type Input Resolver | ✅ Completed |
| Context Mapping | ✅ Completed |
| Walking Network Analysis | ✅ Completed |
| Driving Network Analysis | ✅ Completed |
| Noise Impact Modeling | ✅ Completed |
| 360° View Analysis | ✅ Completed |
| Visualization Engine | ✅ Completed |
| Optimization Layer | ⚙️ Ongoing |
| Report Automation | 🔄 Planned |
| Web Deployment | 🔄 Planned |

---

# Optimization Strategy

### OSMnx Caching Enabled  
Reduces redundant API calls.

### Vectorized GeoPandas Operations  
Avoids nested loops for performance.

### Sector Merging Algorithm  
Reduces rendering overhead.

### Spatial Radius Clipping  
Pre-filter geometry before intersection.

---

# Requirements

```
geopandas
osmnx
shapely
pyproj
requests
networkx
matplotlib
pandas
scikit-learn
```

Install:

```bash
pip install geopandas osmnx shapely pyproj requests networkx matplotlib pandas scikit-learn
```

---

# How To Run

```bash
git clone https://github.com/your-username/site-analysis-ALKF.git
cd site-analysis-ALKF
python "Surrounding Amenities & Land Use Context.py"
```

---

# Outputs

The system generates:

- High-resolution urban context maps
- View quality radial diagrams
- Noise exposure overlays
- Accessibility buffers
- Competitive density maps

---

# Engineering Value

This repository demonstrates:

- Advanced geospatial automation
- Urban spatial intelligence modelling
- Graph-based network analytics
- Environmental impact modelling
- Planning decision-support systems

---


