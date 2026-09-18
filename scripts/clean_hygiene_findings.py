#!/usr/bin/env python3
"""
clean_hygiene_findings.py — one-time data cleanup driven by the hygiene scan.

Phases (idempotent; safe to re-run):
  1. artist_self_rows  — title==artist==song rows from the RYM album import
     are artist-level ratings, not songs. They move to the special-posts
     archive (special_type=artist-level) so they stop polluting song stats
     but stay on record, exactly like the VS-battle/meta archive.
  2. duplicate_songs   — same artist+song on disk twice (across BOTH csv
     files): keep the best row (dated preferred, then highest rating).
  3. cache_conflicts   — genre-cache fold-groups with contradictory values:
     keep the entry for the canonical (most-prevalent) spelling, delete the
     case-variant duplicates.
  4. archived-meta residue — meta-post rows already in the special archive
     but never deleted from the base CSV are removed from the base.
  5. generic_artists   — 'Various Artists' rows are compilation-album
     ratings (RYM import), i.e. album-level: archive like self-rows.
  6. case variants     — artist spellings differing only by case/punctuation
     are rewritten to the canonical spelling (most rows, ties → earliest).
  7. no_artist         — confident titles get structured artist/song labels
     (paren-form 'Fix You (Coldplay)', known standards); already-archived
     meta rows are deleted from base; the genuinely unknown stay flagged.

Operates on BOTH posts_tails.csv and posts_tails_additions.csv (the engine
reads both), and computes the FULL finding sets itself — the hygiene
endpoint's report lists are truncated ([:20]/[:15]) and must not be used
as the work list. Backs up every touched file before writing.
"""
import csv
import json
import re
import shutil
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.taste_engine import TasteEngine  # noqa: E402

TAILS = ROOT / 'data' / 'posts_tails.csv'
ADDITIONS = ROOT / 'data' / 'posts_tails_additions.csv'
SPECIAL = ROOT / 'data' / 'posts_tails_special.csv'
CACHE = ROOT / 'data' / 'artist_genre_cache.json'

DRY_RUN = '--dry-run' in sys.argv
STAMP = datetime.now().strftime('%Y%m%d_%H%M%S')


def s(v) -> str:
    return (v or '').strip()


def backup(path: Path) -> None:
    if path.exists():
        shutil.copy2(path, path.with_suffix(path.suffix + f'.bak_hygiene_{STAMP}'))


def is_self_row(row: dict) -> bool:
    """Artist-level row: title==artist and song empty-or-equal (engine rule)."""
    title, artist, song = s(row.get('title')), s(row.get('artist')), s(row.get('song'))
    return bool(title and artist and title.lower() == artist.lower()
                and (not song or song.lower() == artist.lower()))


def read_csv(path: Path):
    with open(path, encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)


def write_csv(path: Path, rows, fields) -> None:
    backup(path)
    with open(path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def append_special(rows, fields) -> None:
    SPECIAL.parent.mkdir(exist_ok=True)
    with open(SPECIAL, 'a', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        if not SPECIAL.exists() or SPECIAL.stat().st_size == 0:
            writer.writeheader()
        writer.writerows(rows)


def load_engine() -> TasteEngine:
    return TasteEngine(str(TAILS))


def rank(row):
    try:
        rating = float(s(row.get('rating')) or -1)
    except ValueError:
        rating = -1
    return (1 if s(row.get('date')) else 0, rating)


def main() -> None:
    # ---------- 1. Archive artist-level rows (both files) -----------------
    moved_total = 0
    for path in (TAILS, ADDITIONS):
        if not path.exists():
            continue
        fields, rows = read_csv(path)
        keep = [r for r in rows if not is_self_row(r)]
        moved = [r for r in rows if is_self_row(r)]
        if moved:
            for r in moved:
                r['special_type'] = 'artist-level'
                r['special_note'] = (f"RYM album import: '{s(r.get('artist'))}' rated "
                                     f"as an album/artist-level entry, not a song")
            print(f"1. artist-level: {len(moved)} rows from {path.name} -> archive")
            moved_total += len(moved)
            if not DRY_RUN:
                write_csv(path, keep, fields)
                append_special(moved, fields)
    if DRY_RUN:
        print(f"1. artist-level: {moved_total} would move")

    # ---------- 2. Deduplicate songs (cross-file) -------------------------
    engine = load_engine()
    dup_sigs = {sig for sig, rows in _dup_groups(engine).items() if len(rows) > 1}
    if dup_sigs:
        # Tag raw rows by file so we can find the global winner per sig.
        tagged = []
        for fname, path in (('base', TAILS), ('additions', ADDITIONS)):
            if not path.exists():
                continue
            fields, rows = read_csv(path)
            for idx, r in enumerate(rows):
                title, artist = s(r.get('title')), s(r.get('artist'))
                sig = engine._normalize_sig(f"{artist} {title}")
                if sig in dup_sigs and title:
                    tagged.append((fname, idx, sig, rank(r)))
        winner = {}
        for fname, idx, sig, rk in tagged:
            if sig not in winner or rk > winner[sig][1]:
                winner[sig] = ((fname, idx), rk)
        for fname, idx, sig, rk in tagged:
            if winner[sig][0] != (fname, idx):
                print(f"2. dedup: drop [{fname}:{idx}] {sig[:50]}")
        if not DRY_RUN:
            for fname, path in (('base', TAILS), ('additions', ADDITIONS)):
                if not path.exists():
                    continue
                fields, rows = read_csv(path)
                losers = {idx for f2, idx, sig, _ in tagged
                          if f2 == fname and winner[sig][0] != (fname, idx)}
                if losers:
                    write_csv(path, [r for i, r in enumerate(rows) if i not in losers],
                              fields)

    # ---------- 3. Unify cache conflicts -----------------------------------
    cache = json.loads(CACHE.read_text(encoding='utf-8'))
    engine = load_engine()
    groups = defaultdict(dict)
    for k, g in cache.items():
        fk = engine._fold_artist_key(k)
        if fk:
            groups[fk][k] = g
    removed = 0
    raw_rows = engine._read_raw_rows()
    for fk, variants in groups.items():
        if len(variants) < 2 or len(set(variants.values())) <= 1:
            continue
        counts = {v: 0 for v in variants}
        for r in raw_rows:
            a = engine._artist_case(s(r.get('artist')))
            if a in counts:
                counts[a] += 1
        keep_key = max(variants, key=lambda k: counts.get(k, 0))
        for k in variants:
            if k != keep_key and k in cache:
                del cache[k]
                removed += 1
        print(f"3. cache: kept {keep_key!r} (removed {len(variants) - 1})")
    print(f"3. cache: {removed} conflicting entries removed")
    if not DRY_RUN and removed:
        backup(CACHE)
        CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2),
                         encoding='utf-8')

    # ---------- 4. Delete archived-meta rows still on base disk ------------
    engine = load_engine()
    fields, rows = read_csv(TAILS)
    meta_left = [r for r in rows
                 if engine._normalize_sig(s(r.get('title'))) in engine.special_sigs]
    if meta_left:
        print(f"4. meta residue: {len(meta_left)} archived rows deleted from base")
        for r in meta_left:
            print(f"     - {s(r.get('title'))[:60]!r}")
        if not DRY_RUN:
            write_csv(TAILS,
                      [r for r in rows if r not in meta_left], fields)

    # ---------- 5. Generic artists: archive compilation albums -------------
    engine = load_engine()
    for path in (TAILS, ADDITIONS):
        if not path.exists():
            continue
        fields, rows = read_csv(path)
        generic = [r for r in rows
                   if engine._is_generic_artist_name(s(r.get('artist')))
                   and s(r.get('artist')).lower() == 'various artists']
        if generic:
            print(f"5. generic: {len(generic)} 'Various Artists' compilation rows "
                  f"from {path.name} -> archive")
            for r in generic:
                r['special_type'] = 'artist-level'
                r['special_note'] = "Compilation-album rating ('Various Artists'), not a song"
            if not DRY_RUN:
                write_csv(path, [r for r in rows if r not in generic], fields)
                append_special(generic, fields)

    # ---------- 6. Rewrite case-variant spellings --------------------------
    engine = load_engine()
    raw = engine._read_raw_rows()
    spellings = defaultdict(lambda: defaultdict(int))  # fold-key -> {spelling: n}
    first_seen = {}
    for order, r in enumerate(raw):
        a = s(r.get('artist'))
        if not a or a.lower() == 'announcement' or engine._is_generic_artist_name(a):
            continue
        fk = engine._fold_artist_key(a)
        spellings[fk][a] += 1
        first_seen.setdefault(fk, (order, a))
    renames = {}
    for fk, variants in spellings.items():
        if len(variants) < 2:
            continue
        canonical = sorted(variants.items(),
                           key=lambda kv: (-kv[1], first_seen[fk][0]))[0][0]
        for v in variants:
            if v != canonical:
                renames[v] = canonical
    if renames:
        print(f"6. case variants: {len(renames)} spellings to canonicalize")
        for v, c in sorted(renames.items()):
            print(f"     {v!r} -> {c!r}")
        if not DRY_RUN:
            for path in (TAILS, ADDITIONS):
                if not path.exists():
                    continue
                fields, rows = read_csv(path)
                changed = 0
                for r in rows:
                    a = s(r.get('artist'))
                    if a in renames:
                        r['artist'] = renames[a]
                        changed += 1
                if changed:
                    print(f"     {changed} rows rewritten in {path.name}")
                    write_csv(path, rows, fields)

    # ---------- 7. Label confident no-artist rows --------------------------
    engine = load_engine()
    KNOWN = {
        '「星の涙」三月のパンタシア': ('三月のパンタシア', '星の涙'),
        'It’s the Most Wonderful Time of the Year': ('Andy Williams', 'It’s the Most Wonderful Time of the Year'),
        'Fate/Zero OP 1': ('LiSA', 'oath sign'),
        'Dot Hack Sign Opening': ('See-Saw', 'Obsession'),
        '“Mr Blobby”, Mr Blobby': ('Mr Blobby', 'Mr Blobby'),
        'Amen, Brother': ('The Winstons', 'Amen, Brother'),
        'Sheet Music Boss Theme V2': ('Sheet Music Boss', 'Sheet Music Boss Theme V2'),
        'Marine Corp Hymn': ('United States Marine Band', 'Marine Corp Hymn'),
    }
    PAREN = re.compile(r'^(?P<song>.+?)\s*\((?P<artist>[^()]+)\)$')
    # Parentheticals that describe the recording, not the artist.
    DESCRIPTOR = re.compile(
        r'\b(piano|song|version|ver|remix|live|acoustic|cover|instrumental|'
        r'full|short|opening|ending|theme|mix|edit|karaoke|arrangement|'
        r'orchestral|reprise|demo|ost)\b', re.IGNORECASE)
    labeled = 0
    for path in (TAILS, ADDITIONS):
        if not path.exists():
            continue
        fields, rows = read_csv(path)
        changed = 0
        for r in rows:
            title = s(r.get('title'))
            if s(r.get('artist')) or not title or title.lower() == 'announcement':
                continue
            if engine._normalize_sig(title) in engine.special_sigs:
                continue  # archived meta: handled in phase 4
            if title in KNOWN:
                artist, song = KNOWN[title]
            else:
                m = PAREN.match(title)
                if (m and m.group('artist').lower() != 'various artists'
                        and not DESCRIPTOR.search(m.group('artist'))
                        and m.group('artist')[0].isupper()):
                    artist, song = m.group('artist').strip(), m.group('song').strip()
                else:
                    continue
            r['artist'], r['song'] = artist, song
            labeled += 1
            changed += 1
            print(f"7. label: {title[:50]!r} -> {artist!r} / {song!r}")
        if changed and not DRY_RUN:
            write_csv(path, rows, fields)
    print(f"7. no-artist: {labeled} rows labeled")

    # ---------- Verify ------------------------------------------------------
    engine = load_engine()
    h = engine.get_data_hygiene()
    print("\nPost-fix scan:")
    for k, v in h['summary'].items():
        print(f"  {k}: {v}")


def _dup_groups(engine: TasteEngine):
    sig_rows = defaultdict(list)
    for row in engine._read_raw_rows():
        title, artist = s(row.get('title')), s(row.get('artist'))
        if not title:
            continue
        if engine._normalize_sig(title) in engine.special_sigs:
            continue
        sig_rows[engine._normalize_sig(f"{artist} {title}")].append(row)
    return sig_rows


if __name__ == '__main__':
    main()
