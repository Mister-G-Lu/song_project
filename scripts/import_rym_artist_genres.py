"""Backfill artist genres for RYM-imported songs via the iTunes Search API.

RYM gives every release primary genres + descriptors, but the original export
isn't in the repo. iTunes' musicArtist entity provides a comparable curated
`primaryGenreName` per artist in one request, with fine genres (K-Pop, J-Pop,
Hip-Hop/Rap) that MusicBrainz community tags lack for non-Western artists.

Matching is deliberately strict (normalized-exact preferred, >=0.9 fuzz
fallback, otherwise skipped) so a lookalike artist can never poison the cache.

Usage:
  python scripts/import_rym_artist_genres.py            # full backlog run
  python scripts/import_rym_artist_genres.py --limit 50 # small test batch
"""
import argparse
import collections
import difflib
import io
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.taste_engine import TasteEngine  # noqa: E402

ITUNES_URL = "https://itunes.apple.com/search"
SLEEP_SEC = 0.35          # ~3 req/sec, well within iTunes limits
CHECKPOINT_EVERY = 50
REPORT_PATH = ROOT / "data" / "rym_genre_backfill_report.json"

# iTunes primaryGenreName -> TasteScope taxonomy. Anything not listed here is
# recorded in the report for manual mapping instead of guessed.
ITUNES_GENRE_MAP = {
    "pop": "Pop",
    "rock": "Rock",
    "alternative": "Indie/Alternative",
    "indie rock": "Indie/Alternative",
    "indie pop": "Indie/Alternative",
    "college rock": "Indie/Alternative",
    "hip-hop/rap": "Rap/Hip-Hop",
    "rap": "Rap/Hip-Hop",
    "k-pop": "K-Pop",
    "j-pop": "J-Pop/Anime",
    "anime": "J-Pop/Anime",
    "j-rock": "J-Pop/Anime",
    "electronic": "Electronic/Dance",
    "dance": "Electronic/Dance",
    "house": "Electronic/Dance",
    "techno": "Electronic/Dance",
    "electro": "Electronic/Dance",
    "edm": "Electronic/Dance",
    "trance": "Electronic/Dance",
    "r&b/soul": "R&B/Soul",
    "r&b": "R&B/Soul",
    "soul": "R&B/Soul",
    "metal": "Metal",
    "hard rock": "Metal",
    "alternative metal": "Metal",
    "metalcore": "Metal",
    "jazz": "Jazz/Swing",
    "classical": "Classical/Instrumental",
    "classical crossover": "Classical/Instrumental",
    "new age": "Classical/Instrumental",
    "soundtrack": "Soundtrack/Score",
    "disney": "Soundtrack/Score",
    "tv soundtrack": "Soundtrack/Score",
    "video game soundtrack": "Soundtrack/Score",
    "country": "Country",
    "americana": "Country",
    "bluegrass": "Country",
    "folk": "Folk/Acoustic",
    "singer/songwriter": "Folk/Acoustic",
    "acoustic": "Folk/Acoustic",
    "folk-rock": "Folk/Acoustic",
    "latin": "Latin",
    "latin urban": "Latin",
    "urbano latino": "Latin",
    "reggae": "Reggae/Dub",
    "dub": "Reggae/Dub",
    "blues": "Blues",
    "christian": "Christian/Holiday?",  # placeholder — kept unmapped below
    "holiday": "Christmas/Holiday",
    "christmas": "Christmas/Holiday",
    "vocal": "Pop",
    "vocal pop": "Pop",
    "dance pop": "Pop",
    "punk": "Punk",
    "hardcore punk": "Punk",
    "ambient": "Electronic/Dance",
    "worldwide": "Pop",
    "world": "Pop",
    "international": "Pop",
    "korean folk": "Folk/Acoustic",
    "korean soundtrack": "Soundtrack/Score",
    "japanese soundtrack": "Soundtrack/Score",
    "french pop": "Pop",
    "pop latino": "Latin",
    "latin pop": "Latin",
    "rock y alternativo": "Indie/Alternative",
    "rock alternativo": "Indie/Alternative",
    "mpb": "Latin",
    "mandopop": "Pop",
    "c-pop": "Pop",
    "regional indian": "Pop",
    "indian pop": "Pop",
    "arabic pop": "Pop",
    "arabic": "Pop",
    "teen pop": "Pop",
    "electronica": "Electronic/Dance",
    "idm": "Electronic/Dance",
    "flamenco": "Latin",
    "comedy": "META/Other",
    "spoken word": "META/Other",
    "stand-up comedy": "META/Other",
    "brazilian": "Latin",
    "forr\u00f3": "Latin",
    "children's music": "META/Other",
    "jungle/drum'n'bass": "Electronic/Dance",
    "drum & bass": "Electronic/Dance",
    "downtempo": "Electronic/Dance",
    "blues-rock": "Blues",
    "celtic": "Folk/Acoustic",
    "traditional folk": "Folk/Acoustic",
    "korean indie": "Indie/Alternative",
    "german pop": "Pop",
    "funk": "Disco/Funk",
    "alternative rap": "Rap/Hip-Hop",
    "action & adventure": "Soundtrack/Score",
    "asia": "Pop",
    "instrumental": "Classical/Instrumental",
    "kayokyoku": "J-Pop/Anime",
    "mbalax": "Latin",
    "african": "Pop",
    "video game": "Soundtrack/Score",
    "fantezi": "Pop",
}
UNMAPPABLE = {"christian"}  # no taxonomy home — record, don't guess


def _norm_name(name: str) -> str:
    t = (name or "").lower()
    t = re.sub(r"[^\w\s]", " ", t, flags=re.UNICODE)
    return re.sub(r"\s+", " ", t).strip()


def itunes_lookup(name: str):
    """Return (itunes_genre, matched_name) or (None, reason). Retries on 5xx."""
    url = ITUNES_URL + "?" + urllib.parse.urlencode(
        {"term": name, "entity": "musicArtist", "limit": 3})
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (TasteScope genre backfill)"})
    data = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.loads(r.read().decode("utf-8"))
            break
        except Exception as e:
            if attempt == 2:
                return None, f"HTTP-ERR {e}"
            time.sleep(2 * (attempt + 1))
    results = (data or {}).get("results", [])
    if not results:
        return None, "NO RESULTS"
    want = _norm_name(name)
    chosen = next((a for a in results if _norm_name(a.get("artistName") or "") == want), None)
    if chosen is None:
        top = results[0]
        ratio = difflib.SequenceMatcher(None, _norm_name(top.get("artistName") or ""), want).ratio()
        if ratio >= 0.9:
            chosen = top
        else:
            return None, f"MISMATCH top={top.get('artistName')!r} ratio={ratio:.2f}"
    return chosen.get("primaryGenreName"), chosen.get("artistName")


def map_genre(itunes_genre: str):
    g = (itunes_genre or "").strip().lower()
    if g in ITUNES_GENRE_MAP and g not in UNMAPPABLE:
        return ITUNES_GENRE_MAP[g]
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="cap artists processed (0 = all)")
    args = ap.parse_args()

    print("Loading engine...", flush=True)
    engine = TasteEngine(str(ROOT / "data" / "posts_tails.csv"))
    total = len(engine.rows)
    dist = engine._get_genre_distribution()
    unc0 = dist.get("Uncategorized", {}).get("count", 0)
    print(f"baseline: {unc0}/{total} uncategorized ({100*(total-unc0)/total:.1f}% coverage)", flush=True)

    # Backlog: uncategorized rows whose artists are not yet cached
    backlog = {}
    rym_rows = 0
    rym_block_sig = None  # all rows appended by the RYM import carry the import date
    import_dates = set()
    for r in engine.rows:
        d = (r.get("date") or "")
        if d.startswith("2026-09") and (r.get("title") or "").strip():
            import_dates.add(d[:10])
    for r in engine.rows:
        if (r.get("_genre") or "Uncategorized") != "Uncategorized":
            continue
        if (r.get("date") or "")[:10] in import_dates:
            rym_rows += 1
        for a in engine._extract_artists_from_row(r):
            if a and a not in engine._artist_genre_cache and len(a) > 2:
                backlog.setdefault(a, 0)
                backlog[a] += 1
    artists = sorted(backlog, key=lambda a: -backlog[a])
    if args.limit:
        artists = artists[:args.limit]
    rym_share = 100 * rym_rows / max(unc0, 1)
    print(f"backlog: {len(backlog)} uncached artists across {rym_rows} RYM-block rows "
          f"({rym_share:.0f}% of all uncategorized)", flush=True)

    stats = {"looked_up": 0, "matched": 0, "mapped": 0, "cache_rejected": 0}
    unmatched = {}
    unmapped_genres = collections.Counter()
    t0 = time.time()

    for i, artist in enumerate(artists, 1):
        # Curated entries are authoritative — apply without a lookup
        curated = engine._curated_genre_for(artist)
        if curated:
            engine._cache_artist_genre(artist, curated)
            stats["mapped"] += 1
            continue

        stats["looked_up"] += 1
        itg, matched = itunes_lookup(artist)
        if itg is None:
            unmatched[artist] = matched
        else:
            stats["matched"] += 1
            genre = map_genre(itg)
            if genre:
                if engine._cache_artist_genre(artist, genre):
                    stats["mapped"] += 1
                else:
                    stats["cache_rejected"] += 1  # song-title pollution guard
            else:
                g = (itg or "").strip().lower()
                if g not in UNMAPPABLE:
                    unmapped_genres[itg] += 1

        if i % 25 == 0:
            print(f"  [{i}/{len(artists)}] matched={stats['matched']} "
                  f"mapped={stats['mapped']} unmatched={len(unmatched)} "
                  f"({(time.time()-t0)/i:.2f}s/art)", flush=True)
        if i % CHECKPOINT_EVERY == 0:
            engine._save_genre_cache()
        time.sleep(SLEEP_SEC)

    # Reclassify with the updated cache and persist everything
    engine._classify_rows()
    engine._build_artist_index()
    engine._save_genre_cache()

    dist = engine._get_genre_distribution()
    unc1 = dist.get("Uncategorized", {}).get("count", 0)
    print(f"\nAFTER: {unc1}/{total} uncategorized ({100*(total-unc1)/total:.1f}% coverage), "
          f"resolved {unc0 - unc1} songs this run", flush=True)
    print(f"cache: {len(engine._artist_genre_cache)} entries | "
          f"lookup stats: {stats}", flush=True)
    if unmapped_genres:
        print("unmapped iTunes genres (extend ITUNES_GENRE_MAP):",
              dict(unmapped_genres.most_common(15)), flush=True)

    REPORT_PATH.write_text(json.dumps({
        "stats": stats,
        "unmatched": unmatched,
        "unmapped_itunes_genres": dict(unmapped_genres),
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"report: {REPORT_PATH}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
