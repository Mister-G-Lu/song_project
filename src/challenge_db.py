"""
challenge_db.py — Curated challenge database and genre alias mappings.
Loads all data from JSON files in the data/ directory for easy editing.
"""
import os
import json
from typing import Dict, List


_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')


def _load_json(filename: str):
    """Load a JSON file from the data directory."""
    path = os.path.join(_DATA_DIR, filename)
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


# ============================================================
# Curated challenge songs — critically acclaimed/widely-loved tracks
# across diverse genres, organized by tier.
# ============================================================
CHALLENGE_DB: List[Dict] = _load_json('challenge_db.json')


# ============================================================
# Genre alias map — bridges classification genre names (e.g. "Rap/Hip-Hop")
# to challenge DB genre names (e.g. "Hip-Hop") so opposite-taste mode
# can correctly match your lowest-rated genres to challenge entries.
# ============================================================
GENRE_ALIAS_TO_CLASS: Dict[str, str] = _load_json('genre_alias_to_class.json')
