"""
enrich_release_years.py — Fill in missing song release years.

Strategy: iTunes term search first (fast, original release dates), then an
artist-catalog fuzzy matcher (finds decorated/medley titles term search
misses), then Deezer, then MusicBrainz (rate-limited, auto-skipped while
it 503-throttles us).

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
import difflib
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.taste_engine import TasteEngine  # noqa: E402

DEFAULT_CACHE = ROOT / "data" / "release_year_cache.json"

# MusicBrainz throttle handling: after a 503, skip it for 5 minutes and let
# iTunes/Deezer carry the run; retried automatically after the backoff.
MB_BACKOFF_SECS = 300
_mb_down_until = 0.0


def itunes_release_year(artist: str, song: str):
    """Song release year via the iTunes Search API (free, no auth).

    Returns the earliest matching year, or None. A result only counts when
    BOTH the track name and the artist name match (similarity rules below),
    so a wrong-artist compilation can never poison the cache. iTunes often
    beats MusicBrainz on reissue-prone mainstream pop: the store lists the
    original single/album date, not the latest remaster.
    """
    import json as _json
    import urllib.parse
    import urllib.request

    url = "https://itunes.apple.com/search?" + urllib.parse.urlencode(
        {"term": f"{artist} {song}", "entity": "song", "limit": 5})
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (TasteScope year enrich)"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            data = _json.loads(r.read().decode("utf-8"))
    except Exception:
        return None
    best = None
    for t in data.get("results", []):
        if _artist_matches(artist, t.get("artistName") or "") and \
                _title_matches(song, t.get("trackName") or ""):
            y = (t.get("releaseDate") or "")[:4]
            if y.isdigit():
                y = int(y)
                best = y if best is None else min(best, y)
    return best


DECOR_RE = re.compile(
    r"(?i)\s*[(\[{](?:feat\.?|ft\.?|featuring|prod\.?|produced by|with|"
    r"remix|remaster(?:ed)?|live|acoustic|version|sped up|slowed)[^)\]}]*[)\]}]")
GENERIC_BRACKETS_RE = re.compile(r"\s*[(\[「『【].*?[\])」』】]\s*")
SUFFIX_RE = re.compile(
    r"(?i)\s+-\s+(intro|outro|live|remaster(?:ed)?|demo|acoustic|"
    r"instrumental|reprise|bonus.*|extended.*|radio edit)$")
SKIP_RE = re.compile(
    r"(?i)(<a href|https?://|\bbattle\b|\brematch\b|\bmashup\b|"
    r"match\s*[:/]|\bmatchup\b|my own composition|made entirely|"
    r"\bhiatus\b|\bepisode\b|\bpodcast\b)")


def _norm(s: str) -> str:
    return "".join(ch for ch in s.casefold() if ch.isalnum())


def _title_matches(candidate: str, hit: str) -> bool:
    """Similarity acceptance for rescued titles: exact, prefix (both ways,
    guarded by length), or >=0.92 difflib ratio — all on normalized text."""
    a, b = _norm(candidate), _norm(hit)
    if not a or not b:
        return candidate.strip().casefold() == hit.strip().casefold()
    if a == b:
        return True
    if min(len(a), len(b)) >= 6 and (a.startswith(b) or b.startswith(a)):
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.92


def _artist_matches(artist: str, hit: str) -> bool:
    a, b = _norm(artist), _norm(hit)
    if not a or not b:
        return artist.strip().casefold() == hit.strip().casefold()
    return a == b or (min(len(a), len(b)) >= 4 and (a in b or b in a))


def _title_candidates(song: str) -> list:
    """Simplified lookup candidates: decorated title, undecorated, medley
    parts, suffix-stripped — deduped, order preserved."""
    cands = [song.strip()]
    stripped = DECOR_RE.sub("", song).strip()
    if stripped and stripped != song.strip():
        cands.append(stripped)
    for base in list(cands):
        parts = [p.strip() for p in re.split(r"\s*/\s*", base) if p.strip()]
        cands.extend(parts)
    for base in list(cands):
        suf = SUFFIX_RE.sub("", base).strip()
        if suf and suf != base:
            cands.append(suf)
    seen, out = set(), []
    for c in cands:
        k = c.casefold()
        if k not in seen:
            seen.add(k)
            out.append(c)
    return out[:4]


def _deezer_release_year(artist: str, song: str):
    """Release year via Deezer search (free, no auth, fast). Strict on the
    artist; accepts the title with the same similarity rules as rescue."""
    import json as _json
    import urllib.parse
    import urllib.request

    url = "https://api.deezer.com/search?" + urllib.parse.urlencode(
        {"q": f"{artist} {song}", "limit": 10})
    try:
        with urllib.request.urlopen(url, timeout=8) as r:
            data = _json.loads(r.read().decode("utf-8"))
    except Exception:
        return None
    best = None
    for h in data.get("data", []):
        if not _artist_matches(artist, (h.get("artist") or {}).get("name", "")):
            continue
        if not _title_matches(song, h.get("title", "")):
            continue
        rd = (h.get("album") or {}).get("release_date", "")[:4]
        if rd.isdigit():
            y = int(rd)
            best = y if best is None else min(best, y)
    return best


_catalog_cache: dict = {}


def get_json(url: str):
    """GET a JSON URL with the shared UA; returns None on any failure."""
    import urllib.request

    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (TasteScope year enrich)"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def artist_catalog(artist: str):
    """The artist's iTunes track list [(trackName, 'YYYY'), …] via
    artist-id lookup — finds tracks that term search never surfaces
    (decorated titles, obscure B-sides). Cached per artist; None if the
    artist can't be resolved by exact normalized name."""
    import urllib.parse

    key = _norm(artist)
    if not key:
        return None
    if key in _catalog_cache:
        return _catalog_cache[key]
    d = get_json("https://itunes.apple.com/search?" + urllib.parse.urlencode(
        {"term": artist, "entity": "musicArtist", "limit": 5}))
    aid = None
    for a in (d or {}).get("results", []):
        if _norm(a.get("artistName", "")) == key:
            aid = a.get("artistId")
            break
    tracks = None
    if aid:
        d2 = get_json("https://itunes.apple.com/lookup?" + urllib.parse.urlencode(
            {"id": aid, "entity": "song", "limit": 200}))
        tracks = [(t.get("trackName") or "", (t.get("releaseDate") or "")[:4])
                  for t in (d2 or {}).get("results", [])
                  if t.get("wrapperType") == "track"] or None
    _catalog_cache[key] = tracks
    return tracks


def _strip_all_brackets(s: str) -> str:
    return GENERIC_BRACKETS_RE.sub(" ", s).strip()


def _fuzzy_title_year(cand: str, tracks: list):
    """Best (earliest) year among catalog tracks fuzzy-matching cand."""
    import difflib as _difflib

    cn = _norm(cand)
    if len(cn) < 4:
        return None
    best = None
    for tn, yr in tracks:
        hn = _norm(tn)
        if not hn or not yr.isdigit():
            continue
        ok = (cn == hn
              or (min(len(cn), len(hn)) >= 6
                  and (cn.startswith(hn) or hn.startswith(cn)))
              or _difflib.SequenceMatcher(None, cn, hn).ratio() >= 0.82)
        if ok:
            y = int(yr)
            best = y if best is None else min(best, y)
    return best


def catalog_release_year(artist: str, song: str):
    """Release year from the artist's iTunes catalog via fuzzy title match.
    Tries the raw title, the fully bracket-stripped title, then medley parts
    of it — this is what rescues decorated titles and medley entries."""
    tracks = artist_catalog(artist)
    if not tracks:
        return None
    stripped = _strip_all_brackets(song)
    cands, seen = [], set()
    for c in (song, stripped):
        k = c.casefold()
        if c and k not in seen:
            seen.add(k)
            cands.append(c)
    for part in re.split(r"\s*/\s*", stripped):
        part = part.strip()
        k = part.casefold()
        if part and k not in seen:
            seen.add(k)
            cands.append(part)
    for cand in cands[:5]:
        y = _fuzzy_title_year(cand, tracks)
        if y is not None:
            return y
    return None


def _mb_available() -> bool:
    """False while MusicBrainz is 503-throttling us; self-heals after
    MB_BACKOFF_SECS so long runs retry it automatically."""
    global _mb_down_until
    return time.monotonic() >= _mb_down_until


def _mb_mark_down():
    global _mb_down_until
    _mb_down_until = time.monotonic() + MB_BACKOFF_SECS


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


def enrich(engine, limit: int, sleep_sec: float, out: Path, use_itunes: bool = True) -> dict:
    """Resolve missing release years, iTunes-first with MusicBrainz fallback.

    iTunes is tried first: ~0.35s/song, strict both-side name matching, and
    the store lists ORIGINAL release dates (no reissue contamination).
    MusicBrainz (rate-limited) only runs for songs iTunes missed. The cache
    is checkpointed to disk every CHECKPOINT_EVERY songs so a killed run
    keeps its progress.
    """
    CHECKPOINT_EVERY = 50
    unmatched = collect_unmatched(engine)
    batch = unmatched if limit <= 0 else unmatched[:limit]
    batch = [(t, p) for t, p in batch if not SKIP_RE.search(t)]

    # The engine's MB lookup swallows 503s, so probe MB health once up
    # front; while it's throttling us, iTunes/Deezer carry the run.
    probe = TasteEngine._lookup_release_year_musicbrainz("Radiohead", "Creep")
    if probe is None and not itunes_release_year("Radiohead", "Creep"):
        _mb_mark_down()
        print("MusicBrainz appears throttled — skipping MB for "
              f"{MB_BACKOFF_SECS // 60} min (iTunes/Deezer only).", flush=True)
    elif probe is not None:
        TasteEngine._release_year_cache.setdefault(
            TasteEngine._release_year_key("Radiohead", "Creep"), probe)

    looked_up = found = 0
    mb_used = rescued = 0
    started = time.monotonic()
    print(f"Enriching {len(batch)} songs (iTunes-first, MB fallback, rescue for decorated titles)…", flush=True)
    for i, (title, pairs) in enumerate(batch, 1):
        year = None
        for artist, song in pairs:
            # 1) Fast paths: term search with simplified candidates, then
            #    the artist-catalog fuzzy matcher for decorated titles.
            for cand in _title_candidates(song):
                year = itunes_release_year(artist, cand)
                time.sleep(0.35)
                if year is not None:
                    break
            if year is None:
                year = catalog_release_year(artist, song)
                time.sleep(0.15)
            if year is not None:
                break
            # 2) Deezer rescue (same matching rules, slower to warm up).
            for cand in _title_candidates(song):
                year = _deezer_release_year(artist, cand)
                time.sleep(0.3)
                if year is not None:
                    rescued += 1
                    break
            if year is not None:
                break
        if year is None and _mb_available():
            for artist, song in pairs:
                if SKIP_RE.search(song):
                    continue
                year = TasteEngine._lookup_release_year_musicbrainz(artist, song)
                time.sleep(sleep_sec)
                if year is not None:
                    mb_used += 1
                    break
        looked_up += 1
        if year is not None:
            found += 1
            for artist, song in pairs:
                key = TasteEngine._release_year_key(artist, song)
                TasteEngine._release_year_cache.setdefault(key, year)
        if i % CHECKPOINT_EVERY == 0:
            TasteEngine._save_release_year_cache(str(out))
        if i % 50 == 0 or i == len(batch):
            elapsed = time.monotonic() - started
            print(
                f"  {i}/{len(batch)} — {found} found ({mb_used} via MB) "
                f"({elapsed / max(i, 1):.1f}s/song, ETA {elapsed / max(i, 1) * (len(batch) - i):.0f}s)",
                flush=True,
            )

    TasteEngine._save_release_year_cache(str(out))
    cov = engine.get_evolution()["release_year_coverage"]
    print(f"Saved cache -> {out}", flush=True)
    print(f"  looked up {looked_up}, found {found} ({mb_used} via MB, {rescued} via Deezer/catalog rescue); "
          f"coverage now {cov['matched']}/{cov['total']} "
          f"({100 * cov['matched'] / max(cov['total'], 1):.1f}%)", flush=True)
    return {"looked_up": looked_up, "found": found, "mb_used": mb_used,
            "rescued": rescued, "coverage": cov}


if __name__ == "__main__":
    # Windows consoles default to cp1252 and choke on Unicode (same fix app.py uses).
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        description="Resolve missing release years via MusicBrainz + iTunes.")
    parser.add_argument("--report", action="store_true",
                        help="Print coverage breakdown without any network calls.")
    parser.add_argument("--limit", type=int, default=0,
                        help="Only process the first N unmatched songs (0 = all).")
    parser.add_argument("--sleep", type=float, default=1.05,
                        help="Seconds between MusicBrainz requests (default 1.05 — be polite).")
    parser.add_argument("--out", default=str(DEFAULT_CACHE),
                        help="Cache file to write (default: data/release_year_cache.json).")
    parser.add_argument("--no-itunes", action="store_true",
                        help="Skip the iTunes fallback/cross-check pass.")
    args = parser.parse_args()

    engine = TasteEngine(str(ROOT / "data" / "posts_tails.csv"))
    if args.report:
        report(engine)
    else:
        enrich(engine, args.limit, args.sleep, Path(args.out),
               use_itunes=not args.no_itunes)
