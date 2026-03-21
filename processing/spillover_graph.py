from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_CONFIG_PATH = Path(__file__).resolve().parent / "config" / "country_spillovers.json"


@lru_cache(maxsize=1)
def load_country_spillover_map() -> dict[str, list[dict[str, str]]]:
    if not _CONFIG_PATH.exists():
        return {}
    raw = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return {}

    normalized: dict[str, list[dict[str, str]]] = {}
    for country, entries in raw.items():
        code = str(country or "").upper().strip()
        if len(code) != 3 or not isinstance(entries, list):
            continue
        clean_entries: list[dict[str, str]] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            neighbor = str(entry.get("country") or "").upper().strip()
            relationship = str(entry.get("relationship") or "Regional spillover").strip()
            if len(neighbor) != 3:
                continue
            clean_entries.append({"country": neighbor, "relationship": relationship or "Regional spillover"})
        if clean_entries:
            normalized[code] = clean_entries
    return normalized
