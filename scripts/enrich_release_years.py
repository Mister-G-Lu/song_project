"""
enrich_release_years.py — Fill in missing song release years via MusicBrainz.

Why this exists
---------------
Only a small fraction of rated songs resolve to a release year offline:
the curated challenge database has 230 songs, and only ~5% of titles embed
a year (e.g. "Song (Artist, 2012)"). Everything else — anime, Vocaloid,
city pop, Eurovision, game OSTs — has no year anywhere in the title.

MusicBrainz — the same free, no-auth API the engine already uses for artist
genres — returns first-release dates for recordings, so it can resolve most
of the remaining catalog. Results are cached in data/release_year_cache.json
and committed, so the live app, the test suite, and the GitHub Pages build
all resolve years offline afterwards.

Usage (from the project root)
-----------------------------
    python scripts/enrich_release_years.py --report            # coverage breakdown, no network
    python scripts/enrich_release_years.py --limit 300         # first batch (~1 req/s)
    python scripts/enrich_release_years.py                     # everything (long, be patient)
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.taste_engine import TasteEngine  # noqa: E402

DEFAULT_CACHE = ROOT / "data" / "release_year_cache.json"


def collect_unmatched(engine) -> list:
    """Rated songs that still lack a release year but have parseable
    (artist, song) candidates we could look up."""
    unmatched = []
    for r in engine.rated_entries:
        title = (r.get("title") or "").strip()
        if not title:
            continue
        if TasteEngine._release_year_for(title) is not None:
            continue
        pairs = [
            (a.strip(), s.strip())
            for a, s in TasteEngine._parse_title_candidates(title)
            if len(a.strip()) >= 2 and len(s.strip()) >= 2
        ]
        if pairs:
            unmatched.append((title, pairs))
    return unmatched


def report(engine) -> dict:
    cov = engine.get_evolution()["release_year_coverage"]
    unmatched = collect_unmatched(engine)
    print("Release-year coverage")
    print(f"  rated songs            : {cov['total']}")
    print(f"  matched                : {cov['matched']} ({100 * cov['matched'] / max(cov['total'], 1):.1f}%)")
    by = cov.get("by_source", {})
    print(f"    from title year      : {by.get('title', 0)}")
    print(f"    from challenge DB    : {by.get('db', 0)}")
    print(f"    from MusicBrainz cache: {by.get('cache', 0)}")
    print(f"  unmatched, parseable   : {len(unmatched)} (candidates for MusicBrainz)")
    return {"coverage": cov, "parseable_unmatched": len(unmatched)}


def enrich(engine, limit: int, sleep_sec: float, out: Path) -> dict:
    unmatched = collect_unmatched(engine)
    batch = unmatched if limit <= 0 else unmatched[:limit]

    looked_up = found = 0
    started = time.monotonic()
    print(f"Enriching {len(batch)} songs via MusicBrainz (~{sleep_sec:.1f}s/request)…")
    for i, (title, pairs) in enumerate(batch, 1):
        year = None
        for artist, song in pairs:
            year = TasteEngine._lookup_release_year_musicbrainz(artist, song)
            time.sleep(sleep_sec)
            if year is not None:
                break
        looked_up += 1
        if year is not None:
            found += 1
            for artist, song in pairs:
                key = TasteEngine._release_year_key(artist, song)
                TasteEngine._release_year_cache.setdefault(key, year)
        if i % 50 == 0 or i == len(batch):
            elapsed = time.monotonic() - started
            print(
                f"  {i}/{len(batch)} — {found} found "
                f"({elapsed / max(i, 1):.1f}s/song, ETA {elapsed / max(i, 1) * (len(batch) - i):.0f}s)"
            )

    TasteEngine._save_release_year_cache(str(out))
    cov = engine.get_evolution()["release_year_coverage"]
    print(f"Saved cache -> {out}")
    print(f"  looked up {looked_up}, found {found}; coverage now "
          f"{cov['matched']}/{cov['total']} ({100 * cov['matched'] / max(cov['total'], 1):.1f}%)")
    return {"looked_up": looked_up, "found": found, "coverage": cov}


if __name__ == "__main__":
    # Windows consoles default to cp1252 and choke on Unicode (same fix app.py uses).
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Resolve missing release years via MusicBrainz.")
    parser.add_argument("--report", action="store_true",
                        help="Print coverage breakdown without any network calls.")
    parser.add_argument("--limit", type=int, default=0,
                        help="Only process the first N unmatched songs (0 = all).")
    parser.add_argument("--sleep", type=float, default=1.05,
                        help="Seconds between MusicBrainz requests (default 1.05 — be polite).")
    parser.add_argument("--out", default=str(DEFAULT_CACHE),
                        help="Cache file to write (default: data/release_year_cache.json).")
    args = parser.parse_args()

    engine = TasteEngine(str(ROOT / "data" / "posts_tails.csv"))
    if args.report:
        report(engine)
    else:
        enrich(engine, args.limit, args.sleep, Path(args.out))
