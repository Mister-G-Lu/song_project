"""
genre_data.py — Genre classification data for TasteEngine
Loads all data from JSON files in the data/ directory for easy editing
without touching Python code.
"""
import os
import json
from typing import Dict, List, Set


_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')


def _load_json(filename: str):
    """Load a JSON file from the data directory."""
    path = os.path.join(_DATA_DIR, filename)
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


# ============================================================
# Genre keyword mapping — review text → genre classifier
# ============================================================
GENRE_KEYWORDS: Dict[str, List[str]] = _load_json('genre_keywords.json')


# ============================================================
# Curated artist→genre mapping — 400+ well-known artists
# Takes priority over MusicBrainz/Wikidata but below keyword matching.
# ============================================================
CURATED_ARTIST_GENRES: Dict[str, str] = _load_json('curated_artist_genres.json')


# ============================================================
# Your personal favorite artists with your own 1-10 ratings.
# Stored here so the recommender can boost similar artists.
# ============================================================
FAVORITE_ARTISTS: Dict[str, float] = _load_json('favorite_artists.json')


# ============================================================
# Song-title fragments that get mis-parsed as artist names
# ============================================================
PARSE_ARTIFACTS: Set[str] = set(_load_json('parse_artifacts.json'))
