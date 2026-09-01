#!/usr/bin/env python3
"""
cache_challenge_popularity.py

Fetch Spotify popularity scores (0-100) for every song in the challenge DB
and cache them to data/challenge_popularity.json.

Usage:
    python scripts/cache_challenge_popularity.py

Requires SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET environment variables.
Without them, falls back to estimating popularity from listen_score.
"""

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.challenge_db import CHALLENGE_DB

CACHE_PATH = ROOT / "data" / "challenge_popularity.json"


def estimate_popularity(song: dict) -> int:
    """
    Estimate popularity (0-100) from listen_score and year.
    Lower listen_score + older year = more obscure = lower popularity.
    """
    ls = song.get("listen_score", 50)
    year = song.get("year", 2000)
    tier = song.get("tier", "classic")

    # Base from listen_score (scale 90-99 → 40-95)
    base = max(0, min(100, int((ls - 90) * 10.5 + 45)))

    # Year decay: older songs lose ~2 points per decade
    age = max(0, 2025 - year)
    year_penalty = min(20, int(age / 10) * 2)

    # Tier boost: cult = more obscure, legendary = more known
    tier_mod = {"cult": -10, "classic": -3, "modern_classic": 2, "legendary": 5}
    base += tier_mod.get(tier, 0)

    return max(0, min(100, base - year_penalty))


def fetch_spotify_popularity(artist: str, song: str, sp) -> int:
    """Search Spotify and return track popularity (0-100)."""
    try:
        query = f"track:{song} artist:{artist}"
        results = sp.search(q=query, type="track", limit=1)
        tracks = results.get("tracks", {}).get("items", [])
        if tracks:
            return tracks[0].get("popularity", 0)
    except Exception as e:
        print(f"  Spotify error for {artist} – {song}: {e}")
    return 0


def main():
    cache = {}

    # Try Spotify API
    sp = None
    try:
        from spotipy.oauth2 import SpotifyClientCredentials
        import spotipy

        client_id = os.environ.get("SPOTIFY_CLIENT_ID", "")
        client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET", "")
        if client_id and client_secret:
            auth = SpotifyClientCredentials(client_id=client_id, client_secret=client_secret)
            sp = spotipy.Spotify(auth_manager=auth)
            print('[OK] Spotify API connected')
        else:
            print('[WARN] No Spotify credentials - using estimated popularity')
    except ImportError:
        print('[WARN] spotipy not installed - using estimated popularity')

    total = len(CHALLENGE_DB)
    fetched = 0

    for i, song in enumerate(CHALLENGE_DB):
        key = f"{song['artist']}|{song['song']}"
        if sp:
            pop = fetch_spotify_popularity(song["artist"], song["song"], sp)
            if pop > 0:
                fetched += 1
            time.sleep(0.1)  # rate limit
        else:
            pop = estimate_popularity(song)

        cache[key] = {
            "popularity": pop,
            "listen_score": song.get("listen_score", 50),
            "tier": song.get("tier", "classic"),
            "year": song.get("year", 0),
        }

        if (i + 1) % 20 == 0 or i == total - 1:
            print(f"  [{i+1}/{total}] done")

    # Save cache
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)

    print(f"\n[OK] Cached {len(cache)} songs to {CACHE_PATH}")
    if sp:
        print(f"  {fetched}/{total} fetched from Spotify, rest estimated")
    else:
        print("  All estimated from listen_score + year + tier")


if __name__ == "__main__":
    main()
