#!/usr/bin/env python3
"""
cache_artist_popularity.py

Fetch Spotify artist popularity scores (0-100, follower-count proxy) for every
rated artist in the collection and cache them to data/artist_popularity.json.
These feed the constellation's "Extra Constellation" mode (popularity x genre).

Usage:
    python scripts/cache_artist_popularity.py

Requires SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET environment variables.
Without them, the script prints a warning and exits without changing the cache
(the engine falls back to challenge-derived + genre base rates).
"""

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CACHE_PATH = ROOT / "data" / "artist_popularity.json"


def main():
    sp = None
    try:
        import spotipy
        from spotipy.oauth2 import SpotifyClientCredentials

        client_id = os.environ.get("SPOTIFY_CLIENT_ID", "")
        client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET", "")
        if client_id and client_secret:
            auth = SpotifyClientCredentials(client_id=client_id, client_secret=client_secret)
            sp = spotipy.Spotify(auth_manager=auth)
            print("[OK] Spotify API connected")
        else:
            print("[WARN] No Spotify credentials (SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET)")
    except ImportError:
        print("[WARN] spotipy not installed")

    if sp is None:
        print("[SKIP] Cache left unchanged. Engine will use challenge-derived + genre fallbacks.")
        return

    # Load existing cache so reruns only fetch missing artists.
    cache = {}
    if CACHE_PATH.exists():
        try:
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            cache = {k: v for k, v in loaded.items() if not k.startswith("_") and isinstance(v, int)}
        except (json.JSONDecodeError, OSError):
            cache = {}

    # Rated artists only — the constellation only shows rated artists.
    from src.taste_engine import TasteEngine

    engine = TasteEngine(str(ROOT / "data" / "posts_tails.csv"))
    artists = sorted(
        a for a, info in engine.all_artists.items() if info.get("ratings")
    )
    total = len(artists)
    print(f"[..] Fetching popularity for {total} rated artists...")

    fetched = 0
    for i, artist in enumerate(artists):
        if artist in cache:
            continue
        try:
            results = sp.search(q=f'artist:"{artist}"', type="artist", limit=1)
            items = results.get("artists", {}).get("items", [])
            if items:
                pop = int(items[0].get("popularity", -1))
                if 0 <= pop <= 100:
                    cache[artist] = pop
                    fetched += 1
        except Exception as e:
            print(f"  Spotify error for {artist}: {e}")
        time.sleep(0.05)  # stay polite with the search API
        if (i + 1) % 25 == 0 or i == total - 1:
            print(f"  [{i + 1}/{total}] done")

    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)

    print(f"\n[OK] Cached {len(cache)} artists to {CACHE_PATH} ({fetched} newly fetched)")


if __name__ == "__main__":
    main()
