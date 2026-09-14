#!/usr/bin/env python3
"""
cache_artist_popularity_deezer.py

Fill data/artist_popularity.json for artists that have no Spotify popularity
on record, using the Deezer public API (no auth required).

Deezer exposes `nb_fan` per artist — a direct followers proxy. We calibrate
fan counts onto the Spotify 0-100 popularity scale using every artist for
which we DO have a real Spotify value (the explicit cache + the per-song
challenge cache), interpolating popularity over log10(fans).

Guards:
  * Spotify anchor values are never overwritten.
  * Deezer-estimated values are tracked in `_deezer_estimates` and excluded
    from future calibration (no self-reinforcing feedback loop).
  * Popularity output is clamped to 0-100 and monotonic in fan count.
  * Song titles, quoted names, and CSV parse artifacts are never looked up.

Usage:
    python scripts/cache_artist_popularity_deezer.py
"""

import difflib
import json
import math
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.genre_data import PARSE_ARTIFACTS  # noqa: E402

CACHE_PATH = ROOT / "data" / "artist_popularity.json"
DEEZER_SEARCH = "https://api.deezer.com/search/artist"

_NAME_BLOCKLIST = {'the', 'announcement', 'various artists', 'unknown artist'}


def _norm(name: str) -> str:
    return re.sub(r'[^a-z0-9]', '', name.lower())


def _is_plausible_artist_name(name: str) -> bool:
    """Reject song titles, quoted names, and parse artifacts before the API."""
    n = name.strip()
    if not n or len(n) > 80:
        return False
    if n.lower() in _NAME_BLOCKLIST:
        return False
    if any(c in n for c in '"\'\u201c\u201d\u2018\u2019'):
        # Quotes usually wrap song titles like "Hanuman" or 'Seven Nation Army'.
        return False
    if n in PARSE_ARTIFACTS:
        return False
    return True


def deezer_fans(name: str, session: requests.Session) -> int | None:
    """Fetch nb_fan for an artist, returning None when no confident match."""
    try:
        r = session.get(DEEZER_SEARCH, params={'q': f'"{name}"', 'limit': 1}, timeout=10)
        items = r.json().get('data', [])
        if not items:
            return None
        top = items[0]
        returned = _norm(top.get('name', ''))
        queried = _norm(name)
        # Guard against wrong-artist matches on unusual names.
        if not returned or (queried not in returned and
                            difflib.SequenceMatcher(None, queried, returned).ratio() < 0.75):
            return None
        fans = top.get('nb_fan')
        return int(fans) if fans is not None else None
    except Exception:
        return None


def build_calibration(anchors: dict[str, int], session: requests.Session,
                      cached_fans: dict[str, int] | None = None) -> list[tuple[float, float]]:
    """Return sorted (log10_fans, spotify_popularity) anchor points.
    Fans for anchors are reused from cached_fans when present; newly fetched
    counts are written BACK into cached_fans (mutated in place) so callers can
    persist them."""
    points = []
    cached_fans = cached_fans if cached_fans is not None else {}
    for artist, pop in anchors.items():
        fans = cached_fans.get(artist)
        if fans is None:
            fans = deezer_fans(artist, session)
            if fans and fans > 0:
                cached_fans[artist] = int(fans)
            time.sleep(0.05)
        if fans and fans > 0:
            points.append((math.log10(fans), float(pop)))
    # Collapse duplicate x values by averaging their y (some fan counts repeat).
    merged: dict[float, list[float]] = {}
    for x, y in points:
        merged.setdefault(round(x, 4), []).append(y)
    return sorted((x, sum(ys) / len(ys)) for x, ys in merged.items())


def fan_to_popularity(fans: int, curve: list[tuple[float, float]]) -> int | None:
    """Interpolate Spotify-style popularity from a Deezer fan count.
    Monotonicity is enforced: fewer fans can never map to a HIGHER popularity
    than a smaller-fanned anchor, and every result is clamped to [0, 100]."""
    if not curve or fans <= 0:
        return None
    x = math.log10(fans)
    if x <= curve[0][0]:
        # Below the lowest anchor: follow the bottom segment's slope, but the
        # result may never exceed the bottom anchor's popularity.
        (x0, y0), (x1, y1) = curve[0], curve[1]
        slope = (y1 - y0) / (x1 - x0) if x1 > x0 else 0
        val = y0 + slope * (x - x0)
        return max(0, min(100, int(round(min(val, y0)))))
    if x >= curve[-1][0]:
        # Above the highest anchor: follow the top segment's slope, but the
        # result may never fall below the top anchor's popularity.
        (x0, y0), (x1, y1) = curve[-2], curve[-1]
        slope = (y1 - y0) / (x1 - x0) if x1 > x0 else 0
        val = y1 + slope * (x - x1)
        return min(100, max(0, int(round(max(val, y1)))))
    for (x0, y0), (x1, y1) in zip(curve, curve[1:]):
        if x0 <= x <= x1:
            if x1 == x0:
                return int(round(y0))
            frac = (x - x0) / (x1 - x0)
            return max(0, min(100, int(round(y0 + frac * (y1 - y0)))))
    return None


FANS_PATH = ROOT / "data" / "artist_popularity_fans.json"


def _save_all_fans(fans: dict[str, int]) -> None:
    """Persist raw Deezer fan counts (the followers axis reads this file)."""
    try:
        FANS_PATH.write_text(json.dumps(fans, indent=2), encoding='utf-8')
        print(f"[OK] Saved {len(fans)} raw fan counts to {FANS_PATH.name}", flush=True)
    except OSError as e:
        print(f"[WARN] Could not save fan counts: {e}", flush=True)


def main():
    session = requests.Session()
    session.headers.update({'User-Agent': 'freebuff-taste-engine/1.0'})

    # ---- Known Spotify values: explicit cache + challenge-derived artists ----
    # Deezer-ESTIMATED entries (recorded in _deezer_estimates) must NOT become
    # calibration anchors — they were derived FROM the curve, and re-using them
    # would make the calibration self-reinforcing on every rerun.
    cache: dict = {}
    prior_estimates: dict[str, int] = {}
    if CACHE_PATH.exists():
        try:
            loaded = json.loads(CACHE_PATH.read_text(encoding='utf-8'))
            cache = {k: v for k, v in loaded.items()
                     if not k.startswith('_') and isinstance(v, (int, float))}
            prior_estimates = loaded.get('_deezer_estimates', {})
        except (json.JSONDecodeError, OSError):
            cache = {}
    spotify_anchors = {k: v for k, v in cache.items() if k not in prior_estimates}
    anchors: dict[str, int] = {k: int(v) for k, v in spotify_anchors.items()}

    from src.taste_engine import TasteEngine
    engine = TasteEngine(str(ROOT / 'data' / 'posts_tails.csv'))
    challenge = engine._load_popularity_cache()
    per_artist: dict[str, list[int]] = {}
    for key, meta in challenge.items():
        artist = key.split('|', 1)[0] if isinstance(key, str) else None
        try:
            p = int(meta.get('popularity', -1))
        except (TypeError, ValueError, AttributeError):
            continue
        if artist and 0 <= p <= 100:
            per_artist.setdefault(artist, []).append(p)
    for artist, scores in per_artist.items():
        anchors.setdefault(artist, round(sum(scores) / len(scores)))

    print(f"[1/3] Calibrating Deezer fans -> Spotify popularity "
          f"using {len(anchors)} artists with known values...", flush=True)
    # Reuse any fan counts already fetched on disk (anchors + old estimates).
    disk_fans: dict[str, int] = {}
    if FANS_PATH.exists():
        try:
            disk_fans = json.loads(FANS_PATH.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError):
            disk_fans = {}
    curve = build_calibration(anchors, session, disk_fans)
    # build_calibration wrote any newly fetched anchor fans back into disk_fans.
    if len(curve) < 5:
        print(f"[FAIL] Only {len(curve)} calibration points matched — aborting "
              f"(cache left unchanged).", flush=True)
        return
    sample = curve[::max(1, len(curve) // 8)]
    print("  anchor samples (log10 fans -> pop): " +
          ", ".join(f"{x:.1f}->{int(y)}" for x, y in sample), flush=True)

    # ---- Fetch fans for every rated artist missing from the cache ----
    # Small thread pool: Deezer allows generous concurrency on search, and the
    # work is pure network I/O. 8 workers ≈ 5-8 min for ~1700 artists.
    rated = [a for a, info in engine.all_artists.items() if info.get('ratings')]
    todo = sorted(a for a in rated if a not in cache and _is_plausible_artist_name(a))
    skipped = len(rated) - len(todo) - len([a for a in rated if a in cache])
    print(f"[2/3] Fetching Deezer fans for {len(todo)} artists "
          f"({skipped} implausible names skipped, 8 threads)...", flush=True)

    results: dict[str, int | None] = {}
    done = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(deezer_fans, a, session): a for a in todo}
        for fut, artist in futures.items():
            try:
                results[artist] = fut.result()
            except Exception:
                results[artist] = None
            done += 1
            if done % 200 == 0 or done == len(todo):
                got = sum(1 for v in results.values() if v)
                print(f"  [{done}/{len(todo)}] matched={got}", flush=True)

    filled, unmatched = 0, 0
    new_estimates: dict[str, int] = {}
    estimate_fans: dict[str, int] = {}
    for artist, fans in results.items():
        if fans:
            cache[artist] = fan_to_popularity(fans, curve)
            new_estimates[artist] = fans  # provenance (guards calibration on rerun)
            estimate_fans[artist] = fans  # raw signal for the followers axis
            filled += 1
        else:
            unmatched += 1

    # Persist every Deezer fan count we have (anchors + estimates). This is the
    # raw followers data the constellation's Followers axis reads directly.
    all_fans: dict[str, int] = {}
    if FANS_PATH.exists():
        try:
            all_fans = json.loads(FANS_PATH.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError):
            all_fans = {}
    all_fans.update(estimate_fans)
    # Anchors (Spotify-valued artists) MUST be in the fans file — they are the
    # superstars that anchor the log axis' right edge.
    for artist in anchors:
        if artist in disk_fans:
            all_fans[artist] = disk_fans[artist]

    # ---- Write cache (existing Spotify values were never touched) ----
    # _-prefixed keys are metadata: the engine skips them (non-numeric values).
    # Raw Deezer fan counts live in data/artist_popularity_fans.json — the
    # followers axis needs the raw signal, not just the 0-100 compression.
    cache['_comment'] = ("Artist popularity 0-100 for the Popularity/Followers views. "
                         "Explicit Spotify values + Deezer-fan-calibrated estimates "
                         "(scripts/cache_artist_popularity_deezer.py). Regenerable.")
    cache['_deezer_estimates'] = {**prior_estimates, **new_estimates}
    CACHE_PATH.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding='utf-8')
    _save_all_fans(all_fans)

    real = sum(1 for k, v in cache.items() if not k.startswith('_'))
    print(f"[3/3] Cached {real} artists "
          f"({filled} filled from Deezer, {unmatched} unmatched, "
          f"{len(anchors)} Spotify anchors preserved)", flush=True)


if __name__ == "__main__":
    main()
