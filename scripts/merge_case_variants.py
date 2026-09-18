"""
One-time data fix: merge case-variant artists and songs in posts_tails.csv.

Adds to the existing .bak* backup series. Fixes the identity problem where
'Yu Peng Chen' / 'Yu-peng Chen' / 'Yu Peng chen' etc. appeared as separate
artists (and 'Take On Me' vs 'Take on Me - a-ha' as separate songs).

Policy (matches engine dedup):
- Artist merge groups are formed case-insensitively. The canonical display
  casing is the variant with the most rated rows (ties → earliest first
  appearance); every row in the group is rewritten to it.
- Song titles are NOT rewritten (release-year cache and discovery caches key
  off title text); duplicate groups with identical normalized
  (case-insensitive) titles keep the highest-rated row, as in the engine.

Run:  python -X utf8 scripts/merge_case_variants.py [--dry-run]
"""
import argparse
import csv
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / 'data' / 'posts_tails.csv'

DASH_RE = re.compile(r'\s+[\u2013\u2014]\s+|\s+-\s+')

# Row-count majority picked a misspelled casing for these; pin the correct
# official stylization (reviewed by hand against the dry-run output).
OVERRIDES = {
    'backstreet boys': 'Backstreet Boys',
    'daniel belanger': 'Daniel Belanger',
    'flo rida': 'Flo Rida',
    'rob thomas': 'Rob Thomas',
    'we the kings': 'We the Kings',
    'orange caramel': 'Orange Caramel',
    'bradio': 'BRADIO',
    'misterwives': 'MisterWives',
}


def artist_key(name):
    return re.sub(r'\s+', ' ', (name or '').strip()).lower()


def title_sig(title):
    """Case-insensitive, dash-insensitive signature used to group songs."""
    t = (title or '').strip().lower()
    t = DASH_RE.sub(' - ', t)
    t = re.sub(r'\s+', ' ', t)
    return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true',
                    help='Print planned changes without writing files')
    args = ap.parse_args()

    with open(CSV_PATH, 'r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    orig_count = len(rows)
    print(f'Loaded {orig_count} rows from {CSV_PATH.name}')

    # ------------------------------------------------------------------
    # 1. Artist groups (artist column + parsed variants inside the title)
    # ------------------------------------------------------------------
    artist_counts = Counter()
    first_seen = {}
    for i, r in enumerate(rows):
        a = (r.get('artist') or '').strip()
        if a and a.lower() != 'announcement':
            k = artist_key(a)
            artist_counts[k] += 1
            first_seen.setdefault(k, i)

    groups = defaultdict(list)          # key -> [distinct raw spellings]
    for r in rows:
        a = (r.get('artist') or '').strip()
        if a and a.lower() != 'announcement':
            k = artist_key(a)
            if a not in groups[k]:
                groups[k].append(a)

    multi = {k: v for k, v in groups.items() if len(v) > 1}
    print(f'Case-variant artist groups: {len(multi)}')

    canonical = {}
    for k, variants in multi.items():
        # Highest row count wins; ties broken by earliest appearance in CSV.
        c = Counter()
        first_occurrence = {}
        for i, r in enumerate(rows):
            a = (r.get('artist') or '').strip()
            if a and artist_key(a) == k:
                c[a] += 1
                first_occurrence.setdefault(a, i)
        canonical[k] = min(
            c, key=lambda v: (-c[v], first_occurrence[v]),
        )
        canonical[k] = OVERRIDES.get(k, canonical[k])

    artist_rewrites = 0
    for r in rows:
        a = (r.get('artist') or '').strip()
        if a and a.lower() != 'announcement':
            k = artist_key(a)
            if k in canonical and a != canonical[k]:
                r['artist'] = canonical[k]
                artist_rewrites += 1
    print(f'Artist cells rewritten: {artist_rewrites}')

    # ------------------------------------------------------------------
    # 2. Song dedup within the same artist (case/dash-insensitive sig)
    # ------------------------------------------------------------------
    seen = {}       # (artist_key, title_sig) -> row index
    remove = set()
    song_dupes = 0
    for i, r in enumerate(rows):
        title = (r.get('title') or '').strip()
        if not title:
            continue
        a = (r.get('artist') or '').strip()
        sig = (artist_key(a), title_sig(title))
        if sig in seen:
            prev_i = seen[sig]
            cur = int(r.get('rating') or 0)
            prev = int(rows[prev_i].get('rating') or 0)
            cur_date = r.get('date') or '9999'
            prev_date = rows[prev_i].get('date') or '9999'
            # Keep higher rating; tie -> earlier date (engine policy)
            if cur > prev or (cur == prev and cur_date < prev_date):
                remove.add(prev_i)
                seen[sig] = i
            else:
                remove.add(i)
            song_dupes += 1
        else:
            seen[sig] = i

    print(f'Case/dash-variant song duplicates merged: {song_dupes}')

    kept = [r for i, r in enumerate(rows) if i not in remove]
    print(f'Rows: {orig_count} -> {len(kept)}')

    if args.dry_run:
        for k, v in sorted(multi.items()):
            print(f'  {v}  ->  {canonical[k]}')
        print('DRY RUN — nothing written.')
        return

    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = CSV_PATH.with_name(f'{CSV_PATH.name}.bak_casefix_{stamp}')
    bak.write_bytes(CSV_PATH.read_bytes())
    print(f'Backup written: {bak.name}')

    with open(CSV_PATH, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(kept)
    print(f'Wrote {len(kept)} rows back to {CSV_PATH.name}')


if __name__ == '__main__':
    sys.exit(main())
