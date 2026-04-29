from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from processing.disaster_early_warning import compute_disaster_early_warning


def compute_wildfire_forecast(country: str | None = None, limit: int = 6) -> dict[str, Any]:
    """Return wildfire-only forecast and hotspot slices from the shared disaster engine."""
    payload = compute_disaster_early_warning(country=country, limit=max(limit, 6))
    forecasts = [item for item in (payload.get("forecasts") or []) if str(item.get("event_type") or "") == "wildfire"][:limit]
    hotspots = ((payload.get("regional_hotspots") or {}).get("wildfire") or [])[:limit]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "event_type": "wildfire",
        "country": payload.get("country") or (country or "GLB"),
        "forecasts": forecasts,
        "regional_hotspots": hotspots,
        "notes": [
            "Wildfire slice is produced from the shared disaster warning engine.",
            "Signals currently prioritize heat, wind, fire detections, and world-state events.",
        ],
    }
