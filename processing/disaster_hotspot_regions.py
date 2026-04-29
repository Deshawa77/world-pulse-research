from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

EARTHQUAKE_REGION_DEFINITIONS = [
    {"name": "Aleutian Arc", "lat": (48.0, 60.0), "lon": (-180.0, -150.0)},
    {"name": "Kuril-Kamchatka", "lat": (42.0, 62.0), "lon": (145.0, 175.0)},
    {"name": "Japan Trench", "lat": (30.0, 46.0), "lon": (138.0, 150.0)},
    {"name": "Mariana Arc", "lat": (10.0, 28.0), "lon": (140.0, 152.0)},
    {"name": "Philippine Trench", "lat": (5.0, 20.0), "lon": (124.0, 135.0)},
    {"name": "Indonesia Sunda Arc", "lat": (-12.0, 8.0), "lon": (94.0, 130.0)},
    {"name": "Tonga-Kermadec", "lat": (-42.0, -12.0), "lon": (-180.0, -165.0)},
    {"name": "Andean Margin", "lat": (-55.0, 12.0), "lon": (-82.0, -68.0)},
    {"name": "Middle America Trench", "lat": (6.0, 26.0), "lon": (-110.0, -84.0)},
    {"name": "Caribbean Boundary", "lat": (8.0, 24.0), "lon": (-86.0, -58.0)},
    {"name": "South Sandwich Arc", "lat": (-62.0, -48.0), "lon": (-40.0, -18.0)},
    {"name": "Mediterranean-Hellenic Arc", "lat": (30.0, 42.0), "lon": (18.0, 34.0)},
    {"name": "Anatolian-Iranian Belt", "lat": (28.0, 42.0), "lon": (34.0, 60.0)},
    {"name": "Himalayan Front", "lat": (24.0, 36.0), "lon": (72.0, 98.0)},
    {"name": "East African Rift", "lat": (-18.0, 14.0), "lon": (28.0, 44.0)},
    {"name": "Mid-Atlantic Ridge", "lat": (-60.0, 70.0), "lon": (-45.0, -10.0)},
    {"name": "Southwest Indian Ridge", "lat": (-55.0, -25.0), "lon": (18.0, 62.0)},
    {"name": "New Zealand Alpine Margin", "lat": (-48.0, -34.0), "lon": (166.0, 179.5)},
]


CYCLONE_REGION_DEFINITIONS = [
    {"name": "Atlantic Main Development Region", "lat": (8.0, 24.0), "lon": (-60.0, -18.0)},
    {"name": "Caribbean Cyclone Belt", "lat": (10.0, 26.0), "lon": (-88.0, -58.0)},
    {"name": "Eastern Pacific Hurricane Corridor", "lat": (8.0, 24.0), "lon": (-132.0, -92.0)},
    {"name": "Bay of Bengal Cyclone Basin", "lat": (6.0, 24.0), "lon": (80.0, 98.0)},
    {"name": "Arabian Sea Cyclone Basin", "lat": (8.0, 24.0), "lon": (56.0, 76.0)},
    {"name": "Southwest Indian Cyclone Belt", "lat": (-28.0, -6.0), "lon": (42.0, 86.0)},
    {"name": "Northwest Pacific Typhoon Corridor", "lat": (8.0, 28.0), "lon": (122.0, 158.0)},
    {"name": "Coral Sea Cyclone Basin", "lat": (-26.0, -8.0), "lon": (145.0, 168.0)},
]

FLOOD_REGION_DEFINITIONS = [
    {"name": "Lower Mississippi Basin", "lat": (28.0, 39.0), "lon": (-97.0, -86.0)},
    {"name": "Amazon Floodplain", "lat": (-12.0, 4.0), "lon": (-74.0, -48.0)},
    {"name": "La Plata Basin", "lat": (-35.0, -16.0), "lon": (-64.0, -50.0)},
    {"name": "West African Monsoon Belt", "lat": (4.0, 18.0), "lon": (-18.0, 12.0)},
    {"name": "Nile Delta Corridor", "lat": (21.0, 33.0), "lon": (28.0, 36.0)},
    {"name": "Danube-Carpathian Basin", "lat": (42.0, 49.0), "lon": (16.0, 29.0)},
    {"name": "Indus Floodplain", "lat": (22.0, 34.0), "lon": (66.0, 75.0)},
    {"name": "Ganges-Brahmaputra Delta", "lat": (20.0, 28.0), "lon": (86.0, 93.0)},
    {"name": "Mekong Basin", "lat": (8.0, 22.0), "lon": (98.0, 108.0)},
    {"name": "Yangtze Flood Belt", "lat": (24.0, 34.0), "lon": (108.0, 122.0)},
]

WILDFIRE_REGION_DEFINITIONS = [
    {"name": "Pacific Northwest Timber Belt", "lat": (40.0, 58.0), "lon": (-132.0, -116.0)},
    {"name": "California Chaparral", "lat": (31.0, 42.0), "lon": (-125.0, -114.0)},
    {"name": "Canadian Boreal West", "lat": (50.0, 67.0), "lon": (-140.0, -100.0)},
    {"name": "Mediterranean Fire Belt", "lat": (30.0, 46.0), "lon": (-10.0, 40.0)},
    {"name": "Amazon Fringe", "lat": (-18.0, 8.0), "lon": (-78.0, -45.0)},
    {"name": "Andean Dry Corridor", "lat": (-36.0, -8.0), "lon": (-76.0, -60.0)},
    {"name": "Southern Africa Bushveld", "lat": (-32.0, -8.0), "lon": (12.0, 38.0)},
    {"name": "East African Savanna", "lat": (-12.0, 14.0), "lon": (28.0, 46.0)},
    {"name": "Siberian Taiga South", "lat": (46.0, 64.0), "lon": (70.0, 140.0)},
    {"name": "Central Asian Steppe", "lat": (36.0, 54.0), "lon": (54.0, 92.0)},
    {"name": "Indonesia Dry Forest Arc", "lat": (-12.0, 8.0), "lon": (95.0, 135.0)},
    {"name": "Southeast Australia Bushfire Belt", "lat": (-42.0, -27.0), "lon": (141.0, 154.0)},
]

HOTSPOT_ALERT_BANDS = ["critical", "active", "monitor", "guarded"]
HOTSPOT_TREND_LABELS = ["accelerating", "cooling", "steady"]
HOTSPOT_TREND_WINDOWS = {
    "6h": 6,
    "24h": 24,
    "72h": 72,
}


def format_coord_label(value: float, positive: str, negative: str) -> str:
    rounded = int(round(abs(value)))
    direction = positive if value >= 0 else negative
    return f"{rounded}{direction}"


def format_hotspot_region_label(center_lat: float, center_lon: float) -> str:
    return f"{format_coord_label(center_lat, 'N', 'S')} / {format_coord_label(center_lon, 'E', 'W')} sector"


def lookup_hotspot_region_name(center_lat: float, center_lon: float, hazard: str = "earthquake") -> str:
    hazard_key = str(hazard).lower()
    if hazard_key == "wildfire":
        definitions = WILDFIRE_REGION_DEFINITIONS
    elif hazard_key == "cyclone":
        definitions = CYCLONE_REGION_DEFINITIONS
    elif hazard_key == "flood":
        definitions = FLOOD_REGION_DEFINITIONS
    else:
        definitions = EARTHQUAKE_REGION_DEFINITIONS
    for definition in definitions:
        lat_min, lat_max = definition["lat"]
        lon_min, lon_max = definition["lon"]
        if lat_min <= center_lat <= lat_max and lon_min <= center_lon <= lon_max:
            return str(definition["name"])
    hemisphere_ns = "North" if center_lat >= 0 else "South"
    if center_lon <= -120:
        hemisphere_ew = "Pacific Rim"
    elif center_lon <= -30:
        hemisphere_ew = "Americas Margin"
    elif center_lon <= 60:
        hemisphere_ew = "Eurasia-Africa Belt"
    elif center_lon <= 140:
        hemisphere_ew = "Indian-Pacific Belt"
    else:
        hemisphere_ew = "West Pacific Rim"
    if hazard_key == "wildfire":
        prefix = "Wildfire"
    elif hazard_key == "cyclone":
        prefix = "Cyclone"
    elif hazard_key == "flood":
        prefix = "Flood"
    else:
        prefix = hemisphere_ns
    return f"{prefix} {hemisphere_ew}"


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_region_metadata(center_lat: float, center_lon: float, hazard: str = "earthquake") -> dict[str, Any]:
    region_label = format_hotspot_region_label(center_lat, center_lon)
    region_name = lookup_hotspot_region_name(center_lat, center_lon, hazard=hazard)
    return {
        "region_name": region_name,
        "region_label": region_label,
        "display_label": f"{region_name} ({region_label})",
    }
