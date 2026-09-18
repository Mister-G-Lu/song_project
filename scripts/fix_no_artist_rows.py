"""
One-time data fix: resolve the no-artist rows in posts_tails.csv.

Two actions, both backed up first:

  1. ARCHIVE meta posts to data/posts_tails_special.csv. Titles like
     '6/18/2018's Spotify', '5/21/2018's Weekly Discovery',
     'Worldwide Listening Challenge', 'Favorite Artists/ "Banned" artists'
     and 'Music Personality/Taste Over Time!' are blog posts, not songs —
     they cannot be analyzed by Spotify/weekly-discovery tooling and
     pollute song-level stats. They join the existing special archive
     (VS battles, rating meta) with special_type='meta'.
     NOTE: they stay in posts_tails.csv too — _load_all() already excludes
     archived titles by signature at load time; removing them from the
     base CSV is left to a future consolidation pass.

  2. LABEL the remaining no-artist rows in place. The engine's
     _label_row_artists() derives artist/song from the raw title
     ('Christina Grimmie "Feeling Good" (2013)' -> Christina Grimmie /
     Feeling Good); this writes those derived values into the CSV's
     structured columns so every consumer (static export, scripts,
     other tools) sees the same identity as the running engine.
     Only rows where the engine successfully labels are rewritten.

Run:  python -X utf8 scripts/fix_no_artist_rows.py [--dry-run]
"""
import argparse
import csv
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / 'data' / 'posts_tails.csv'
SPECIAL_PATH = ROOT / 'data' / 'posts_tails_special.csv'

sys.path.insert(0, str(ROOT))

# Titles that are blog posts, not songs. Matched case-insensitively as
# exact normalized forms — keep this list small and explicit.
META_POST_PATTERNS = [
    # Date-prefixed post titles: '6/18/2018's Spotify', '8/13's Spotify',
    # '5/21/2018's Weekly Discovery' — with or without the year, straight
    # or curly apostrophe.
    re.compile(r"^\d{1,2}/\d{1,2}(?:/\d{2,4})?['’]?s\s+spotify$", re.I),
    re.compile(r"^\d{1,2}/\d{1,2}(?:/\d{2,4})?['’]?s\s+weekly\s+discovery$", re.I),
    re.compile(r"^worldwide\s+listening\s+challenge$", re.I),
    re.compile(r"^music\s+personality/taste\s+over\s+time!$", re.I),
    re.compile(r"^favorite\s+artists/\s*[“\"']?banned[”\"']?\s*artists$", re.I),
]


def is_meta_post(title: str) -> bool:
    t = (title or '').strip()
    return any(p.match(t) for p in META_POST_PATTERNS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    from src.taste_engine import TasteEngine

    with open(CSV_PATH, 'r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    # Engine instance purely for _label_row_artists() on synthetic row dicts
    engine = TasteEngine.__new__(TasteEngine)
    engine._base_rows = rows  # known-artist source for the labeler
    engine.additions_path = str(ROOT / 'data' / 'posts_tails_additions.csv')

    # ---------------- 1. Archive meta posts ----------------
    meta_rows = [r for r in rows
                 if not (r.get('artist') or '').strip()
                 and is_meta_post(r.get('title') or '')]

    # ---------------- 2. Label the rest --------------------
    label_rewrites = []
    for r in rows:
        if (r.get('artist') or '').strip():
            continue
        title = (r.get('title') or '').strip()
        if not title or is_meta_post(title):
            continue
        probe = dict(r)
        engine._label_row_artists(probe)
        new_artist = (probe.get('artist') or '').strip()
        new_song = (probe.get('song') or '').strip()
        if new_artist:
            label_rewrites.append((r, new_artist, new_song))

    print(f'Meta posts to archive: {len(meta_rows)}')
    for r in meta_rows:
        print(f"   [{r['rating'] or '-':>3}] {r['title']!r}")
    print(f'No-artist rows the labeler can fix: {len(label_rewrites)}')
    for r, a, s in label_rewrites[:12]:
        print(f'   {r["title"][:48]!r} -> {a!r} | {s!r}')
    if len(label_rewrites) > 12:
        print(f'   ... and {len(label_rewrites) - 12} more')

    if args.dry_run:
        print('DRY RUN — nothing written.')
        return

    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    # Apply label rewrites to the row dicts
    for r, a, s in label_rewrites:
        r['artist'] = a
        if s:
            r['song'] = s
        else:
            r.setdefault('song', '')

    # Backup + write base CSV
    shutil.copy(CSV_PATH, str(CSV_PATH) + f'.bak_noartist_{stamp}')
    with open(CSV_PATH, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f'Wrote {len(rows)} rows -> {CSV_PATH.name} (backup: .bak_noartist_{stamp})')

    # Append archived meta posts to the special archive
    if meta_rows:
        with open(SPECIAL_PATH, 'a', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(
                f,
                fieldnames=['date', 'rating', 'title', 'tail', 'artist', 'song',
                            'title_original', 'title_english',
                            'special_type', 'special_note'],
                extrasaction='ignore',
            )
            for r in meta_rows:
                out = dict(r)
                out['special_type'] = 'meta'
                out['special_note'] = 'no-artist meta post; archived by fix_no_artist_rows.py'
                writer.writerow(out)
        print(f'Appended {len(meta_rows)} meta posts -> {SPECIAL_PATH.name}')


if __name__ == '__main__':
    sys.exit(main())
