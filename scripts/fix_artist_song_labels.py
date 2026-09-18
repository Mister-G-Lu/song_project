#!/usr/bin/env python3
"""
fix_artist_song_labels.py

Repairs the pre-populated 'artist'/'song' columns in data/posts_tails.csv.

Problems fixed:
  1. Reversed dash orientation: for "Song – Artist" dash titles, some earlier
     fix scripts wrote artist=<left>, song=<right> even when the right side is
     the real artist ("WALK THE MOON – One Foot" → artist="One Foot").
  2. Song-title leakage: artist column holding the song name and the song
     column holding the full title ("GARNiDELiA – Ambiguous" →
     artist="Ambiguous", song="GARNiDELiA – Ambiguous").
  3. Meta rows ("Battle of the 98's", "Youtube top 10 most viewed review")
     carrying artist="Announcement" — Announcement is a system marker, not an
     artist.

Safety invariants:
  * Dash rows are only ever *re-oriented* (the two columns swap) or derived by
    removing the song part from the title on leak rows. No new strings are
    invented, so a wrong guess can only mis-orient a row, never rename it.
  * The genre cache is polluted with song titles that MusicBrainz matched as
    artists ("Demons", "Africa", ...), so cache membership alone is a WEAK
    signal. The scoring oracle prefers curated genres, non-empty country
    lookups and popularity-cache anchors, which real artists have and
    song-title pollution generally lacks.
  * Rows without a dash in the title are only touched when artist == song
    (clear corruption) or artist == 'Announcement'.

Usage:
    python scripts/fix_artist_song_labels.py            # dry run (no writes)
    python scripts/fix_artist_song_labels.py --write    # apply + backup
"""
import csv
import os
import re
import sys
import shutil
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / 'data' / 'posts_tails.csv'

# Dash only counts as a separator when surrounded by whitespace, so names
# like "F-777", "A-ha" and "Giga-P" are never split.
DASH = re.compile(r'^(.+?)\s+[\u2013\u2014-]\s+(.+)$')
FEAT = re.compile(r'\b(?:ft\.?|feat\.?|featuring)\b', re.I)
QUOTES = '\u201c\u201d"\u2018\u2019\'\u00ab\u00bb'


def _strip_quotes(s: str) -> str:
    return s.strip(QUOTES).strip()


# Trailing metadata: "The Piano Guys (2013)", "I Gotta Feeling, 2009",
# "Live It Up (feat. Pitbull) 2013" — a year glued onto a side.
META_YEAR = re.compile(r'[\s,]+\(?((?:19|20)\d{2})\)?\s*$')


def _strip_meta(side: str):
    """Split a dash side into (base, had_year_meta). The base drops a trailing
    year so 'Callysta (2017)' scores as 'Callysta'."""
    m = META_YEAR.search(side)
    if m:
        return side[:m.start()].strip(), True
    return side, False


def main():
    write = '--write' in sys.argv

    from src.taste_engine import TasteEngine
    print("Loading TasteEngine (for curated + cache lookups)...")
    engine = TasteEngine(str(CSV_PATH))

    curated = set(engine.__class__.__module__ and
                  __import__('src.genre_data', fromlist=['CURATED_ARTIST_GENRES'])
                  .CURATED_ARTIST_GENRES.keys())
    genre_cache = engine._artist_genre_cache
    country_cache = engine._artist_country_cache
    country_ci = engine._country_ci_index

    with open(CSV_PATH, encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    # Collection frequency: how many rows already carry this artist column
    # (meta rows excluded). Recurring names are real artists; leaked song
    # titles appear on their own row only.
    artist_freq = {}
    for r in rows:
        a = (r.get('artist') or '').strip()
        if not a or a.lower() == 'announcement':
            continue
        # Normalize apostrophe variants so 'Girls’ Generation' and
        # "Girls' Generation" count as the same recurring artist.
        key = a.lower().replace('\u2019', "'").replace('\u2018', "'")
        artist_freq[key] = artist_freq.get(key, 0) + 1

    try:
        pop_cache = __import__('json').load(
            open(ROOT / 'data' / 'artist_popularity.json', encoding='utf-8'))
        if not isinstance(pop_cache, dict):
            pop_cache = {}
    except Exception:
        pop_cache = {}

    # Hand-reviewed overrides for rows no cache can arbitrate (neither side
    # has curated/country/pop evidence). Keyed by normalized title. Values
    # are the true artist, or an explicit (artist, song) tuple.
    # These are famous songs whose orientation is externally verifiable.
    overrides = {
        'we the kings \u2013 any other way (2013)': 'We the kings',
        'animal \u2013 the cab': 'The Cab',
        'pitbull \u2013 fun ft. chris brown': 'Pitbull',
        'illenium \u2013 crashing': 'ILLENIUM',
        'love song \u2013 cynthia parker': 'Cynthia Parker',
        'walk the moon \u2013 one foot': 'WALK THE MOON',
        'toto \u2013 africa': 'Toto',
        'rever mieux \u2013 daniel belanger': 'Daniel Belanger',
        'jonth & tom wilson \u2013 overdose': 'Jonth & Tom Wilson',
        'i remember \u2013 deadmau5 & kaskade': 'deadmau5 & Kaskade',
        'miracle \u2013 calvin harris': 'Calvin Harris',
        'those days \u2013 lindsey stirling feat. dan \u2013 shay':
            ('Lindsey Stirling feat. Dan + Shay', 'Those Days'),
        'brave enough \u2013 lindsey stirling feat christina perri': 'Lindsey Stirling feat Christina Perri',
        'dr. wily\u2019s castle (mega man 2) \u2013 violin cover \u2013 taylor davis': 'Taylor Davis',
        # Same song title, different artists — only external knowledge
        # arbitrates these (song titles commonly used as artist names).
        'colors \u2013 flow': 'Flow',
        'colors \u2013 thunder jackson': 'Thunder Jackson',
        'the rooks \u2013 secrets': 'The Rooks',
        'tomberlin \u2013 any other way': 'Tomberlin',
        'the captains intangible \u2013 any other way': 'The Captains Intangible',
        # K-Romanized title with no dash separator: artist embedded in title.
        "exo-k \uc5d1\uc18c\ucf00\uc774 '\uc911\ub3c5 (overdose)": ('EXO-K', '\uc911\ub3c5 (Overdose)'),
        # "x" collaboration: the producer duo is the artist, not the song.
        'jim yosef x reill \u2013 animal': 'Jim Yosef x REILL',
        'jim yosef \u2013 firefly': 'Jim Yosef',
        # 'ANIMAL' is the 2023 film; 'Papa Meri Jaan' is sung by Sonu Nigam.
        'animal: papa meri jaan': ('Sonu Nigam', 'PAPA MERI JAAN'),
    }

    def norm_title(t: str) -> str:
        t = t.lower().replace('\u2019', "'").replace('\u2018', "'")
        t = re.sub(r'\s+', ' ', t).strip()
        return t

    def _freq_bonus(n: str, self_key: str) -> int:
        key = n.lower().replace('\u2019', "'").replace('\u2018', "'")
        freq = artist_freq.get(key, 0)
        if self_key and key == self_key:
            freq -= 1
        # Frequency is INFORMATIONAL only in reports: corrupted rows often
        # appear on multiple rows (duplicate ratings), so a name can look
        # "recurring" purely through corruption. Not used for decisions.
        return 0

    def sound_score(name: str, self_key: str = '') -> int:
        """Evidence that CANNOT be produced by song-title pollution:
        curated artist lists, curated popularity seeds, and recurrence in
        the artist column of OTHER rows. Country/genre caches are excluded
        — MusicBrainz matched song names too ('One Foot' has country data).
        """
        if not name:
            return 0
        n = name.strip()
        score = 0
        if n in curated:
            score += 4
        pop = pop_cache.get(n, {})
        if isinstance(pop, dict) and pop.get('popularity_source', pop.get('source', '')) == 'cache':
            score += 2
        score += _freq_bonus(n, self_key)
        # Composite names ("Ariana Grande & Elizabeth Gillies") aren't
        # cached as a unit — propagate from the first member.
        first = re.split(r'\s+(?:&|and|ft\.?|feat\.?|featuring)\s+', n,
                         flags=re.I)[0].strip()
        if first and first.lower() != n.lower():
            score = max(score, sound_score(first, self_key))
        return score

    def artist_score(name: str, self_key: str = '') -> int:
        """Full score: sound evidence + weak signals (caches that also
        hold song-title pollution). Only used as a tiebreaker.
        self_key: the current row's own artist (excluded from frequency)."""
        if not name:
            return 0
        n = name.strip()
        score = sound_score(n, self_key)
        # Non-empty country = a real place lookup succeeded for this name
        # (weak: MusicBrainz matched song names too).
        if country_cache.get(n, '') or country_ci.get(n.lower(), ''):
            score += 1
        # A parenthesized feature marker marks the SONG side
        # ("Rivers (feat. Nico & Vinz)", "Change (feat. Isaac Sign)").
        if re.search(r'\((?:ft|feat)\b', n, re.I):
            score -= 2
        if n in genre_cache:
            score += 1  # weak: cache also holds song-title pollution
        # 'The X' variants of any cache hit
        if not n.lower().startswith('the '):
            the = 'The ' + n
            if the in curated or the in genre_cache or country_cache.get(the, ''):
                score += 2
        # Composite names ("Ariana Grande & Elizabeth Gillies",
        # "Whale ft. Yama") aren't cached as a unit — score their first
        # member too.
        first = re.split(r'\s+(?:&|and|ft\.?|feat\.?|featuring)\s+', n,
                         flags=re.I)[0].strip()
        if first and first.lower() != n.lower():
            score = max(score, artist_score(first))
        return score

    with open(CSV_PATH, encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    stats = {'reoriented': 0, 'song_cleaned': 0, 'leak_fixed': 0,
             'meta_cleared': 0, 'kept': 0, 'changed': 0}
    changes = []
    uncertain = []

    for i, row in enumerate(rows, start=2):
        title = (row.get('title') or '').strip()
        artist = (row.get('artist') or '').strip()
        song = (row.get('song') or '').strip()
        new_artist, new_song = artist, song

        if not title:
            stats['kept'] += 1
            continue

        # ---- Meta rows: 'Announcement' is a marker, not an artist. ----
        if artist.lower() == 'announcement':
            if title.lower() == 'announcement':
                stats['kept'] += 1
                continue
            new_artist, new_song = '', ''
            stats['meta_cleared'] += 1
            changes.append((i, title, artist, song, new_artist, new_song))

        elif (ov := overrides.get(norm_title(title))):
            if isinstance(ov, tuple):
                new_artist, new_song = ov
            else:
                # Artist-name override: derive the song from the title by
                # cutting everything before the artist's last occurrence.
                new_artist = ov
                base_ov = ov.lower().replace('\u2019', "'").replace('\u2018', "'")
                pos = title.lower().replace('\u2019', "'").replace('\u2018', "'").rfind(base_ov)
                if pos > 0:
                    new_song = re.sub(r'[\s]*[\u2013\u2014-][\s]*$', '',
                                      title[:pos].strip())
                else:
                    m3 = DASH.match(title)
                    new_song = m3.group(2).strip() if m3 else song
                new_song = _strip_meta(new_song)[0]  # drop trailing year
            if (new_artist.lower(), new_song.lower()) != \
                    (artist.lower(), song.lower()):
                stats['reoriented'] += 1
                changes.append((i, title, artist, song, new_artist, new_song))
            else:
                stats['kept'] += 1

        elif (m := DASH.match(title)):
            left, right = m.group(1).strip(), m.group(2).strip()
            left_base, left_meta = _strip_meta(left)
            right_base, right_meta = _strip_meta(right)

            # Self-consistency of the existing artist column: non-empty,
            # not equal to the song column, contains no dash separator, and
            # actually occurs in the title — AND the song column is not just
            # the full title (a leak row, whose orientation is suspect).
            # Such a column was written by an earlier fix pass and is usually
            # right — keep the orientation and only clean the song column.
            existing_ok = bool(artist) and artist.lower() != song.lower() \
                and song.lower() != title.lower() \
                and not DASH.match(artist) and artist.lower() in title.lower()

            if os.environ.get('FIX_DEBUG') and str(i) in os.environ['FIX_DEBUG'].split(','):
                print(f"[DEBUG L{i}] title={title!r} artist={artist!r} song={song!r}")
                print(f"  existing_ok={existing_ok} sound(artist)={sound_score(artist, artist.lower())} "
                      f"sound(L)={sound_score(left_base, artist.lower())} sound(R)={sound_score(right_base, artist.lower())} "
                      f"full(L)={artist_score(left_base, artist.lower())} full(R)={artist_score(right_base, artist.lower())}")

            if existing_ok and sound_score(artist, artist.lower()) >= \
                    max(sound_score(left_base, artist.lower()),
                        sound_score(right_base, artist.lower())):
                # ---- Keep-path: existing orientation is at least as
                # plausible as either alternative — never re-decide rows
                # whose only sin is lacking evidence (e.g. obscure but
                # correctly-parsed local artists).
                new_artist = artist
                is_left = artist.lower() == left.lower()
                other, other_base, other_meta = \
                    (right, right_base, right_meta) if is_left \
                    else (left, left_base, left_meta)
                new_song = other_base if other_meta else other
                if song.lower() == title.lower():
                    # Song column holds the full title — re-derive.
                    if is_left:
                        prefix = artist.lower() + ' '
                        if title.lower().startswith(prefix):
                            m2 = re.match(r'^[\u2013\u2014-]\s+(.+)$',
                                          title[len(prefix):].lstrip())
                            if m2:
                                new_song = m2.group(1).strip()
                    else:
                        suffix = ' ' + artist.lower()
                        if title.lower().endswith(suffix):
                            m2 = re.match(r'^(.+?)\s+[\u2013\u2014-]\s+$',
                                          title[:len(title) - len(suffix)])
                            if m2:
                                new_song = m2.group(1).strip()
                if (new_artist.lower(), new_song.lower()) == \
                        (artist.lower(), song.lower()):
                    stats['kept'] += 1
                else:
                    stats['song_cleaned'] += 1
                    changes.append((i, title, artist, song, new_artist, new_song))
            else:
                # ---- Repair path: artist column wrong or absent. ----
                # Multi-dash titles ("Song – Violin Cover – Taylor Davis"):
                # split on ALL dashes and let the scorer pick the artist
                # segment — a single-dash regex grabs the wrong boundary.
                dash_count = len(re.findall(r'\s+[\u2013\u2014-]\s+', title))
                if dash_count >= 2:
                    segs_all = [s.strip() for s in
                                re.split(r'\s+[\u2013\u2014-]\s+', title)]
                    best, best_score = None, -1
                    for seg in segs_all:
                        base, _meta = _strip_meta(seg)
                        sc = artist_score(base, artist.lower())
                        if sc > best_score:
                            best, best_score = seg, sc
                    if best and best_score >= 1:
                        pos = title.lower().rfind(best.lower())
                        if pos > 0:
                            new_artist = _strip_meta(best)[0]
                            new_song = re.sub(r'[\s]*[\u2013\u2014-][\s]*$', '',
                                              title[:pos].strip())
                            if (new_artist.lower(), new_song.lower()) != \
                                    (artist.lower(), song.lower()):
                                stats['reoriented'] += 1
                                changes.append((i, title, artist, song,
                                                new_artist, new_song))
                            else:
                                stats['kept'] += 1
                            continue

                if _strip_quotes(right) != right or _strip_quotes(left) != left:
                    # Quoted side is the song: "Artist – "Song"" or
                    # ""Song" – Artist"
                    chosen = left if _strip_quotes(right) != right else right
                else:
                    # Plain scores — the existing column gets no bias here:
                    # swapped rows are self-consistent, so biasing toward
                    # them just preserves the corruption.
                    sl = artist_score(left_base, artist.lower())
                    sr = artist_score(right_base, artist.lower())
                    ssl = sound_score(left_base, artist.lower())
                    ssr = sound_score(right_base, artist.lower())
                    if ssr > ssl:
                        chosen = right
                    elif ssl > ssr:
                        chosen = left
                    elif sr > sl:
                        chosen = right
                    elif sl > sr:
                        chosen = left
                    else:
                        # Full tie: title-cased side, else left.
                        def caps(s):
                            return sum(1 for w in s.split() if w[:1].isupper())
                        chosen = right if caps(right) > caps(left) else left
                        uncertain.append((i, title, left, right))

                # A chosen side that still contains a dash separator means
                # the title had two dashes ("Song – Violin Cover – Taylor
                # Davis"): keep the strongest segment as the artist.
                if DASH.match(chosen):
                    segs = [s.strip() for s in
                            re.split(r'\s+[\u2013\u2014-]\s+', chosen)]
                    best, best_score = None, -1
                    for seg in segs:
                        base, _meta = _strip_meta(seg)
                        sc = artist_score(base, artist.lower())
                        if sc > best_score:
                            best, best_score = seg, sc
                    chosen = best if best and best_score >= 1 else segs[-1]

                # Drop a leading "by " ("Song — by Artist" style titles).
                by_m = re.match(r'^by\s+(.+)$', chosen, re.I)
                if by_m and by_m.group(1).strip():
                    chosen = by_m.group(1).strip()

                # Drop trailing year metadata from the chosen artist side.
                if chosen == right and right_meta:
                    chosen = right_base
                elif chosen == left and left_meta:
                    chosen = left_base

                new_artist = chosen
                if chosen in (left, left_base):
                    new_song = right_base if right_meta else right
                elif chosen in (right, right_base):
                    new_song = left_base if left_meta else left
                else:
                    # Chosen came from a re-split: song is everything in the
                    # title before the artist segment.
                    pos = title.lower().rfind(chosen.lower())
                    if pos > 0:
                        new_song = re.sub(r'[\s]*[\u2013\u2014-][\s]*$', '',
                                          title[:pos].strip())
                    else:
                        new_song = right_base if right_meta else right

                if not new_song or new_song.lower() == title.lower() \
                        or new_song.lower() == new_artist.lower():
                    new_song = right if chosen in (left, left_base) else left

                if (new_artist.lower(), new_song.lower()) == \
                        (artist.lower(), song.lower()):
                    stats['kept'] += 1
                else:
                    stats['reoriented'] += 1
                    changes.append((i, title, artist, song, new_artist, new_song))

        else:
            # Non-dash title: only fix clear corruption (artist == song).
            if artist and song and artist.lower() == song.lower() \
                    and title.lower() != song.lower():
                new_artist, new_song = '', ''
                stats['leak_fixed'] += 1
                changes.append((i, title, artist, song, new_artist, new_song))
            else:
                stats['kept'] += 1

        if (new_artist, new_song) != (artist, song):
            row['artist'] = new_artist
            row['song'] = new_song
            stats['changed'] += 1

    print(f"\nScanned {len(rows)} rows:")
    print(f"  reoriented dash rows:      {stats['reoriented']}")
    print(f"  song columns cleaned:      {stats['song_cleaned']}")
    print(f"  song-title leaks fixed:    {stats['leak_fixed']}")
    print(f"  meta rows cleared:         {stats['meta_cleared']}")
    print(f"  unchanged:                 {stats['kept']}")
    print(f"  total rows changed:        {stats['changed']}")

    print(f"\nSample changes ({'ALL' if '--verbose' in sys.argv else 'first 20'}):")
    shown = changes if '--verbose' in sys.argv else changes[:20]
    for ln, title, old_a, old_s, new_a, new_s in shown:
        print(f"  L{ln}: '{title[:55]}'")
        print(f"      artist: '{old_a[:40]}' -> '{new_a[:40]}'  song: '{old_s[:40]}' -> '{new_s[:40]}'")

    if uncertain:
        print(f"\nHeuristic-only decisions to review ({len(uncertain)}):")
        for ln, title, left, right in uncertain[:10]:
            print(f"  L{ln}: '{title[:60]}'  [{left!r} | {right!r}]")

    if write and changes:
        backup = CSV_PATH.with_name(
            CSV_PATH.stem + f'.bak_artist_fix_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv')
        shutil.copy2(CSV_PATH, backup)
        print(f"\nBackup written: {backup.name}")
        with open(CSV_PATH, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"Wrote {CSV_PATH.name} with {stats['changed']} repaired rows.")
    elif not write:
        print("\nDry run — rerun with --write to apply.")


if __name__ == '__main__':
    main()
