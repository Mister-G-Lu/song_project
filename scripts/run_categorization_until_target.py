"""Targeted MusicBrainz backlog pass: classify multi-song uncategorized artists first.

Rate-limited (1 req/sec per MusicBrainz ToS), checkpointed every 50 lookups,
stops as soon as coverage reaches the target.
"""
import io
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.taste_engine import TasteEngine  # noqa: E402

TARGET_COVERAGE = 80.0
MB_BATCH = 60
MB_SLEEP = 1.1
CHECKPOINT_EVERY = 50


def coverage_pct(engine: TasteEngine) -> tuple:
    total = len(engine.rows)
    dist = engine._get_genre_distribution()
    unc = dist.get('Uncategorized', {}).get('count', 0)
    return (100.0 * (total - unc) / total if total else 0.0), unc, total


def backlog(engine: TasteEngine):
    artist_uncat = {}
    for r in engine.rows:
        if (r.get('_genre') or 'Uncategorized') != 'Uncategorized':
            continue
        for a in engine._extract_artists_from_row(r):
            if a and a not in engine._artist_genre_cache and len(a) > 2:
                artist_uncat[a] = artist_uncat.get(a, 0) + 1
    return sorted(artist_uncat.items(), key=lambda x: -x[1])


def main() -> int:
    start = time.time()
    engine = TasteEngine(str(ROOT / 'data' / 'posts_tails.csv'))
    cov, unc, total = coverage_pct(engine)
    print(f'start: {unc}/{total} uncategorized, coverage {cov:.2f}%', flush=True)

    round_no = 0
    while cov < TARGET_COVERAGE:
        round_no += 1
        bl = backlog(engine)
        if not bl:
            print('backlog exhausted — no uncached artists remain.', flush=True)
            break
        batch = [a for a, _ in bl[:MB_BATCH]]
        print(f'round {round_no}: {len(bl)} artists in backlog, '
              f'{sum(v for _, v in bl)} songs; top batch: '
              f'{", ".join(f"{a}({c})" for a, c in bl[:5])}', flush=True)

        found = 0
        for i, artist in enumerate(batch, 1):
            genre = engine._classify_artist_genre_musicbrainz(artist)
            if genre and genre != 'Uncategorized':
                ok = engine._cache_artist_genre(artist, genre)
                if ok:
                    found += 1
                    print(f'  + {artist} -> {genre} (song #{i} in batch)', flush=True)
            if i % CHECKPOINT_EVERY == 0:
                engine._save_genre_cache()
            time.sleep(MB_SLEEP)
        engine._save_genre_cache()

        engine._classify_rows()
        engine._build_artist_index()
        cov, unc, total = coverage_pct(engine)
        print(f'  after round {round_no}: {found} new artist genres, '
              f'{unc}/{total} uncategorized -> coverage {cov:.2f}%', flush=True)

    print(f'\nFINAL: coverage {cov:.2f}% ({unc}/{total} uncategorized), '
          f'cache={len(engine._artist_genre_cache)}, '
          f'elapsed {(time.time() - start)/60:.1f} min', flush=True)
    engine._save_genre_cache()
    return 0 if cov >= TARGET_COVERAGE else 1


if __name__ == '__main__':
    raise SystemExit(main())
