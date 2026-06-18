# utils.py
"""Utility functions shared across the Multi‑Asset Strategy Lab.
Includes colour helper and simple CSV persistence helpers.
"""
import csv
import os
from typing import List, Dict, Any

def hex_to_rgba(hex_color: str, alpha: float = 0.15) -> str:
    """Convert a hex colour (e.g. "#00e676") to an rgba string.
    If the input is malformed, fall back to a default green.
    """
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        return f"rgba(0, 230, 118, {alpha})"
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"

def ensure_folder(path: str) -> None:
    """Create a folder if it does not exist."""
    os.makedirs(path, exist_ok=True)

def read_csv_dict(filepath: str) -> List[Dict[str, Any]]:
    """Read a CSV file into a list of dictionaries (header based)."""
    if not os.path.exists(filepath):
        return []
    with open(filepath, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def write_csv_dict(filepath: str, fieldnames: List[str], rows: List[Dict[str, Any]]) -> None:
    """Write a list of dictionaries to a CSV file.
    Overwrites any existing file.
    """
    ensure_folder(os.path.dirname(filepath))
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

def get_active_strategy(asset: str) -> str:
    """Get the active strategy profile for a given asset from data/active_strategies.json."""
    import json
    path = os.path.join('data', 'active_strategies.json')
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                data = json.load(f)
                return data.get(asset, "Balanced")
        except Exception:
            pass
    return "Balanced"

def save_active_strategy(asset: str, strategy: str) -> None:
    """Save the active strategy profile for a given asset to data/active_strategies.json."""
    import json
    ensure_folder('data')
    path = os.path.join('data', 'active_strategies.json')
    data = {}
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                data = json.load(f)
        except Exception:
            pass
    data[asset] = strategy
    with open(path, 'w') as f:
        json.dump(data, f, indent=4)
