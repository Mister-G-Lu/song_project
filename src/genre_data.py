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


# ============================================================
# Genre spectrum X-axis ordering for the constellation.
# Numeric position 0..1 maps each canonical genre keyword to a horizontal
# slot so that musically similar genres share adjacent spans. The
# constellation chart lays genres left→right by this order; within each
# genre column, artists are sorted vertically by rating (highest at top).
#
# These keys match the canonical genre names from genre_keywords.json
# (the classification tiers produce exactly these strings).
# ============================================================
GENRE_SPECTRUM_ORDER: Dict[str, float] = {
    # ---- Far left: Rap / Hip-Hop ----
    'Rap/Hip-Hop':      0.04,

    # ---- Left: R&B / Soul / Funk (historically adjacent to Hip-Hop) ----
    'R&B/Soul':         0.12,
    'Disco/Funk':       0.16,

    # ---- Center-left: Pop + K-Pop + J-Pop/Anime + Eurovision ----
    'Pop':              0.24,
    'K-Pop':            0.28,
    'J-Pop/Anime':      0.32,
    'Eurovision':       0.36,
    'A Cappella':       0.38,
    'Christmas/Holiday': 0.40,

    # ---- Center: Jazz / Swing ----
    'Jazz/Swing':       0.44,

    # ---- Center-right: Rock + Indie/Alternative + Punk + Metal ----
    'Rock':             0.52,
    'Indie/Alternative': 0.58,
    'Punk':             0.62,
    'Metal':            0.66,

    # ---- Right: Electronic / Dance ----
    'Electronic/Dance': 0.74,

    # ---- Far right: Folk / Acoustic + Country + Blues ----
    'Folk/Acoustic':    0.82,
    'Country':          0.86,
    'Blues':            0.88,

    # ---- Separate corner: Classical / Instrumental ----
    'Classical/Instrumental': 0.92,

    # ---- Separate: Latin + World + Reggae/Dub + Soundtrack ----
    'Latin':            0.10,
    'Reggae/Dub':       0.14,
    'Soundtrack/Score': 0.42,
}


def genre_spectrum_x(genre: str) -> float:
    """Return the 0..1 horizontal position for a genre on the constellation
    spectrum axis. Uncategorized / unknown genres default to 0.5 (centre).
    """
    return GENRE_SPECTRUM_ORDER.get(genre, 0.5)
