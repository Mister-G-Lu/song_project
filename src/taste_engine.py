"""
taste_engine.py - Core data processing and recommendation engine
Analyzes posts_tails.csv to build taste profiles, find blind spots,
and generate recommendations.
"""

import csv
import json as _json
import math
import os
import re
import time
import urllib.parse
from collections import Counter, defaultdict
from datetime import datetime
from typing import List, Dict, Set, Optional

import networkx as nx
from networkx.algorithms.community import louvain_communities

from src.genre_data import GENRE_KEYWORDS, CURATED_ARTIST_GENRES, PARSE_ARTIFACTS, FAVORITE_ARTISTS, GENRE_SPECTRUM_ORDER, genre_spectrum_x
from src.artist_year_model import ArtistYearModel, backtest_artist_year, backtest_artist_year_vs_artist_only
from src.challenge_db import CHALLENGE_DB, GENRE_ALIAS_TO_CLASS
from src.backfill import LETTER_GRADE_MAP, extract_letter_grade, infer_tone_rating


# ---------------------------------------------------------------------------
# Meta-title detection
# ---------------------------------------------------------------------------
# The collection is curated from blog posts, so review meta posts (date
# recaps, "Battle of the 94's", "Double Review: ...") sit alongside real
# song entries. They must never produce artists — a date like '4/16/18' or
# a review title like 'Double Review: UP 12ISING' is not a person.
_META_TITLE_RE = re.compile(
    r'^\d{1,4}[/.-]\d{1,2}([/.-]\d{2,4})?\s*:'   # date-prefixed: '4/16/18: ...', '2021-05-30: ...'
    r'|^\d{4}\s*:'                                   # bare-year prefixed: '2021: Battle of the 94's'
    r'|^double review\b',                            # 'Double Review: ...'
    re.IGNORECASE,
)


def _is_meta_title(title: str) -> bool:
    """True for review/meta post titles that are not real song entries."""
    t = (title or '').strip()
    return t == 'Announcement' or bool(_META_TITLE_RE.match(t))


class TasteEngine:
    def __init__(self, csv_path: str = "data/posts_tails.csv"):
        self.csv_path = csv_path
        self.additions_path = csv_path.replace('.csv', '_additions.csv')
        self.ban_list_path = "data/ban_list.json"
        self.ban_list = {"genres": [], "artists": [], "songs": []}
        self.rows: List[Dict] = []
        self.ratings: List[int] = []
        self.rated_entries: List[Dict] = []
        self.genre_keywords: Dict[str, List[str]] = {}
        self.known_sigs: Set[str] = set()      # normalized song signatures (O(1) lookup)
        self.known_titles: Set[str] = set()     # normalized raw titles (broader match)
        self._word_index: Dict[str, Set[str]] = defaultdict(set)  # word→title sigs (O(1) fuzzy)
        self._artist_genre_cache: Dict[str, str] = {}  # artist→genre cache (MusicBrainz, Wikidata, propagation)
        self._genre_cache_folded: Dict[str, str] = {}  # fold-key → genre (case-insensitive lookup)
        self._title_segment_sigs: Set[str] = set()  # normalized song-name segments (pollution guard)
        self._artist_col_sigs: Set[str] = set()     # names confirmed as artists in the CSV
        self._genre_popularity_base: Dict[str, int] = {}  # genre→avg popularity (chart modes)
        self._artist_popularity_collection_avg: int = 30  # fallback popularity
        self._explicit_popularity_artists: Set[str] = set()
        self._pop_fans_curve: List[tuple] = []  # fan↔popularity calibration
        self._implied_fans_count: int = 0
        self._genre_followers_median: Dict[str, int] = {}
        self._collection_followers_median: int = 1000
        self._raw_fans_artists: Set[str] = set()
        self._base_rows: List[Dict] = []  # rows from the base CSV (never modified by API)
        self._additions_rows: List[Dict] = []  # rows from the additions CSV (API writes only)
        self.special_sigs = self._load_special_post_sigs()
        self._load_all()
        self._init_genre_keywords()
        self._load_genre_cache()  # load persisted cache before building index
        self._load_release_year_cache()  # MusicBrainz-enriched song release years
        self._load_ban_list()
        self._artist_country_cache = self._load_artist_country_cache()
        self._country_ci_index = self._build_country_ci_index(self._artist_country_cache)
        dedup_result = self.deduplicate(write_back=False)
        if dedup_result['removed'] > 0:
            print(f'[dedup] Removed {dedup_result["removed"]} duplicates (in-memory merge)')
        self._build_song_index()   # before classify so the pollution guard is live
        self._classify_rows()      # pre-compute genre for every row (O(n), done once)
        self._build_artist_index()
        # Build artist×year preference model
        self.artist_year_model = ArtistYearModel()
        self.artist_year_model.build(self.rated_entries, self._release_year_for)

    # ------------------------------------------------------------------
    # Two-file overlay: base CSV + additions CSV
    # ------------------------------------------------------------------

    def _load_special_post_sigs(self) -> Set[str]:
        """Signatures of VS-battle / rating-meta posts moved to
        data/posts_tails_special.csv. Those rows are posts, not songs, so
        they must never count toward song statistics. Matching by signature
        (not by file) also guards against the same titles sneaking back in
        through the additions CSV."""
        path = "data/posts_tails_special.csv"
        sigs: Set[str] = set()
        if not os.path.exists(path):
            return sigs
        with open(path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = None
            title_idx = 0
            for row in reader:
                if not row:
                    continue
                if row[0].lstrip().startswith('#'):
                    continue  # explanatory comment line
                if header is None:
                    header = row
                    title_idx = header.index('title') if 'title' in header else 0
                    continue
                if len(row) > title_idx:
                    title = (row[title_idx] or '').strip()
                    if title:
                        sigs.add(self._normalize_sig(title))
        return sigs

    def _load_csv_file(self, path: str) -> List[Dict]:
        """Load a single CSV file, returning list of row dicts."""
        if not os.path.exists(path):
            return []
        with open(path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            return list(reader)

    def _load_all(self):
        """Load base CSV + additions CSV, merge in memory."""
        self._base_rows = self._load_csv_file(self.csv_path)
        self._additions_rows = self._load_csv_file(self.additions_path)
        # Merge: base first, then additions (dedup keeps higher rating)
        self.rows = self._merge_rows(self._base_rows, self._additions_rows)
        # Some imported additions contain only a display title such as
        # "Fix You (Coldplay)". Hydrate the structured columns in memory so
        # every downstream analysis sees the same artist/song identity as the
        # classification and constellation code. Never overwrite non-empty
        # structured values: those may contain deliberate corrections.
        self._hydrate_structured_metadata(self.rows)
        # Label rows that carry no artist at all ('Christina Grimmie "Feeling
        # Good" (2013)' → artist/song) so they feed artist-based analyses.
        for row in self.rows:
            self._label_row_artists(row)
        # Exclude VS-battle / meta posts (moved to data/posts_tails_special.csv)
        if self.special_sigs:
            before = len(self.rows)
            self.rows = [
                r for r in self.rows
                if self._normalize_sig((r.get('title') or '').strip()) not in self.special_sigs
            ]
            excluded = before - len(self.rows)
            if excluded:
                print(f'[special-posts] Excluded {excluded} battle/meta rows '
                      f'(archived in data/posts_tails_special.csv)')
        self.rated_entries = [r for r in self.rows if r.get('rating')]
        self.ratings = [int(r['rating']) for r in self.rated_entries]

    def _merge_rows(self, base: List[Dict], additions: List[Dict]) -> List[Dict]:
        """Merge base and additions, dedup by normalized signature.
        Keeps the row with the higher rating; on ties keeps the earlier date.
        Base rows take priority when ratings are equal.
        """
        seen: Dict[str, int] = {}  # sig → index in merged list
        merged = []
        # Process base first (priority on ties)
        for row in base:
            title = (row.get('title') or '').strip()
            if not title or _is_meta_title(title):
                continue
            sig = self._normalize_sig(title)
            if sig not in seen:
                seen[sig] = len(merged)
                merged.append(row)
            else:
                # Keep higher rating
                existing = merged[seen[sig]]
                cur_rating = int(row.get('rating') or 0)
                prev_rating = int(existing.get('rating') or 0)
                if cur_rating > prev_rating:
                    merged[seen[sig]] = row
        # Process additions
        for row in additions:
            title = (row.get('title') or '').strip()
            if not title or _is_meta_title(title):
                continue
            sig = self._normalize_sig(title)
            if sig not in seen:
                seen[sig] = len(merged)
                merged.append(row)
            else:
                existing = merged[seen[sig]]
                cur_rating = int(row.get('rating') or 0)
                prev_rating = int(existing.get('rating') or 0)
                if cur_rating > prev_rating:
                    merged[seen[sig]] = row
        return merged

    def _hydrate_structured_metadata(self, rows: List[Dict]) -> None:
        """Fill missing artist/song columns from an unambiguous title.

        RYM additions sometimes arrive as ``Song (Artist)`` without the
        structured columns that older exports contain. Only hydrate artists
        already present in the curated map; this deliberately avoids turning
        arbitrary parenthetical song text into a false artist. Existing
        non-empty columns are never changed.
        """
        for row in rows:
            title = (row.get('title') or '').strip()
            if not title:
                continue
            if (row.get('artist') or '').strip() and (row.get('song') or '').strip():
                continue
            match = re.match(
                r'^(.+?)\s*\(([^(),]+?)(?:,\s*(?:19|20)\d{2})?\)\s*$',
                title,
            )
            if not match:
                continue
            artist = match.group(2).strip()
            if self._curated_genre_for(artist) is None:
                continue
            if not (row.get('artist') or '').strip():
                row['artist'] = artist
            if not (row.get('song') or '').strip():
                row['song'] = match.group(1).strip()

    def _label_row_artists(self, row: Dict) -> None:
        """Fill missing artist/song columns from the raw title.

        The CSV's no-artist rows are mostly old posts that wrote the song as
        'Artist Song', 'Artist | Song', 'Artist // Song' or 'Song' Artist'
        (e.g. 'Christina Grimmie “Feeling Good” (2013)', 'Panic! at the
        Disco | Hallelujah', 'Lord of the Rings | The Piano Guys'). Without
        structured columns those rows cannot feed artist-based analyses
        (constellation, favorite artists, genre distribution).

        Strategies, most-confident first:
          1. Separators: ' | ', ' // ', ' ~ ', ' _ ' (artist on the left,
             title on the right) and quoted-title forms ('Song" Artist).
          2. Known-artist scan: any known/curated artist appearing as a
             substring of the title (handles 'Artist Song', 'Song' Artist
             and translated variants like '「星の涙」三月のパンタシア').
          3. « Artist – Song » reversed separator (song on the left).

        Existing non-empty columns are never overwritten. Meta rows are
        skipped — they are not songs.
        """
        title = (row.get('title') or '').strip()
        if not title or _is_meta_title(title):
            return
        if (row.get('artist') or '').strip() and (row.get('song') or '').strip():
            return

        labeled = None  # (artist, song) or None

        # Known-artist name set: everything in the CSV's artist column plus
        # the curated map. Safe to call during _load_all (before the artist
        # index exists) because it reads raw column data only.
        known = {
            (r.get('artist') or '').strip().lower()
            for r in (self._base_rows or [])
            if (r.get('artist') or '').strip()
        }
        known |= {a.lower() for a in CURATED_ARTIST_GENRES}

        # --- Strategy 0: '[Artist, Year)' bracket typo --------------------
        m = re.search(r'\[([^,\[\]]+?),\s*(?:19|20)\d{2}\)', title)
        if m and m.group(1).strip().lower() in known:
            song_part = title[:m.start()].strip(' |~_“"’') or title
            labeled = (m.group(1).strip(), song_part)

        # --- Strategy 1: explicit separators ------------------------------
        seps = [' | ', ' // ', ' ~ ', ' _ ', ' //']
        if labeled is None:
            for sep in seps:
                if sep in title:
                    left, right = title.split(sep, 1)
                    left, right = left.strip(), right.strip()
                    if left and right:
                        # If only the RIGHT side is a known artist, the row
                        # is 'Song | Artist' — swap so the artist wins.
                        if left.lower() not in known and right.lower() in known:
                            left, right = right, left
                        # Strip paren aliases from the artist ('DAZBEE (ダズビー)')
                        m2 = re.match(r'^(.*?)\s*\(([^)]+)\)\s*$', left)
                        if m2 and m2.group(1).strip().lower() in known:
                            left = m2.group(1).strip()
                        labeled = (left, right)
                        break
        if labeled is None:
            # Quoted-song forms: 'Song" Artist  /  Artist "Song" (2013)'
            m = re.match(r'^(.+?)\s*[“"](.+?)[”"]\s*(?:\((?:19|20)\d{2}\))?\s*$', title)
            if m:
                a, s = m.group(1).strip(), m.group(2).strip()
                if a and s:
                    labeled = (a, s)
        # --- Strategy 2: known-artist substring scan ----------------------
        if labeled is None:
            t_lower = title.lower()
            # Prefer longer names: 'Girls’ Generation' over a shorter name
            # contained in it.
            best = None
            for a_lower in known:
                if len(a_lower) < 4:
                    continue
                if a_lower in t_lower and (best is None or len(a_lower) > len(best)):
                    best = a_lower
            if best is not None:
                # Recover display casing from the title itself when possible
                idx = t_lower.find(best)
                artist_raw = title[idx:idx + len(best)]
                rest = (title[:idx] + title[idx + len(best):])
                # Drop leftover years and quote/separator debris
                rest = re.sub(r'\s*\((?:19|20)?\d{2,4}\)\s*$', '', rest)
                rest = rest.strip(' |~_–—-“"’').strip()
                if not rest:
                    # Title is exactly the artist name (artist-level row)
                    return
                labeled = (artist_raw, rest or title)

        # --- Strategy 3: 'Song – Artist' reversed dash --------------------
        if labeled is None:
            m = re.match(r'^(.+?)\s+[–—]\s+(.+)$', title)
            if m:
                left, right = m.group(1).strip(), m.group(2).strip()
                # Only trust it when the RIGHT side is a known artist
                if getattr(self, 'all_artists', None):
                    canon = self._artist_case(right)
                    if canon in self.all_artists:
                        labeled = (right, left)

        if labeled:
            artist, song = labeled
            song = song.strip('“”„‘’"\'').strip()
            song = re.sub(r'\s*\((?:19|20)\d{2}\)\s*$', '', song).strip()
            if not (row.get('artist') or '').strip():
                row['artist'] = artist
            current_song = (row.get('song') or '').strip()
            # Overwrite only a DEGENERATE song column: empty, or a stale
            # copy of the whole title (from an old enrichment pass). A real
            # previously-assigned song name is never clobbered.
            if not current_song or self._normalize_sig(current_song) == self._normalize_sig(title):
                row['song'] = song

    def _load_data(self):
        """Legacy method — loads only the base CSV. Use _load_all() instead."""
        self._load_all()

    def reload(self):
        """Re-read both CSVs from disk. Call after manual edits to the base CSV."""
        self._load_all()
        self._build_song_index()
        self._classify_rows()
        self._build_artist_index()
        if hasattr(self, 'artist_year_model'):
            self.artist_year_model = ArtistYearModel()
            self.artist_year_model.build(self.rated_entries, self._release_year_for)


    def consolidate(self) -> Dict:
        """Merge additions into the base CSV, then clear the additions file.
        Returns stats about what was merged.
        """
        additions = self._load_csv_file(self.additions_path)
        if not additions:
            return {'merged': 0, 'message': 'No additions to consolidate'}

        # Append additions to base CSV (dedup will clean up on next reload)
        with open(self.csv_path, 'a', encoding='utf-8', newline='') as f:
            if additions:
                fieldnames = list(additions[0].keys())
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
                for row in additions:
                    writer.writerow(row)

        # Clear the additions file
        with open(self.additions_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['date', 'rating', 'title', 'tail'])
            writer.writeheader()

        merged_count = len(additions)
        self.reload()  # Re-read everything
        return {'merged': merged_count, 'message': f'Merged {merged_count} additions into base CSV'}

    # ------------------------------------------------------------------
    # Duplicate detection & removal
    # ------------------------------------------------------------------

    def deduplicate(self, *, write_back: bool = False) -> Dict:
        """Remove duplicate rows by normalized title signature.

        Two rows are duplicates if _normalize_sig(title1) == _normalize_sig(title2).
        Keeps the row with the higher rating; on ties keeps the earlier date.

        Args:
            write_back: If True, consolidate all data into the base CSV and
                        clear the additions file. Use sparingly — the normal
                        startup path uses write_back=False.

        Returns:
            { 'removed': int, 'kept': int, 'dupes': [{ 'title': str, 'kept': str }] }
        """
        seen: Dict[str, int] = {}  # sig → index in self.rows
        dupes = []
        indices_to_remove = set()

        for i, row in enumerate(self.rows):
            title = (row.get('title') or '').strip()
            if not title or _is_meta_title(title):
                continue
            sig = self._normalize_sig(title)
            if sig in seen:
                prev_idx = seen[sig]
                prev_row = self.rows[prev_idx]
                # Decide which to keep: higher rating wins, then earlier date
                cur_rating = int(row.get('rating') or 0)
                prev_rating = int(prev_row.get('rating') or 0)
                cur_date = row.get('date', '9999')
                prev_date = prev_row.get('date', '9999')

                if cur_rating > prev_rating or (
                    cur_rating == prev_rating and cur_date < prev_date
                ):
                    # Current row is better — remove previous
                    indices_to_remove.add(prev_idx)
                    seen[sig] = i
                    dupes.append({'title': title, 'kept': title})
                else:
                    # Previous row is better — remove current
                    indices_to_remove.add(i)
                    dupes.append({'title': title, 'kept': prev_row.get('title', '')})
            else:
                seen[sig] = i

        if not dupes:
            return {'removed': 0, 'kept': len(self.rows), 'dupes': []}

        self.rows = [r for i, r in enumerate(self.rows) if i not in indices_to_remove]
        self.rated_entries = [r for r in self.rows if r.get('rating')]
        self.ratings = [int(r['rating']) for r in self.rated_entries]

        if write_back:
            # Consolidate: write deduped rows to base CSV, clear additions
            self._base_rows = list(self.rows)
            self._write_csv()
            # Clear additions file
            with open(self.additions_path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=['date', 'rating', 'title', 'tail'])
                writer.writeheader()
            self._additions_rows = []

        return {
            'removed': len(dupes),
            'kept': len(self.rows),
            'dupes': dupes,
        }

    def _write_csv(self):
        """Rewrite the BASE CSV file from self._base_rows.
        Never touches the additions file — API writes go there.
        """
        if not self._base_rows:
            return
        fieldnames = list(self._base_rows[0].keys())
        # Strip internal _genre and other computed fields
        write_fields = [f for f in fieldnames if not f.startswith('_')]
        with open(self.csv_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=write_fields, extrasaction='ignore')
            writer.writeheader()
            for row in self._base_rows:
                writer.writerow({k: row.get(k, '') for k in write_fields})

    # ------------------------------------------------------------------
    # Row-level genre classification — pre-computed once on load
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_artist_key(name: str) -> str:
        """Normalize an artist name for case-insensitive + apostrophe-insensitive
        lookup against CURATED_ARTIST_GENRES. Lowercases and removes all
        apostrophes (straight and curly) so "Guns N' Roses" matches "Guns N Roses".
        """
        if not name:
            return ''
        return name.lower().replace("'", '').replace('\u2019', '').replace('\u2018', '')

    def _curated_genre_for(self, artist: str) -> Optional[str]:
        """Look up an artist in CURATED_ARTIST_GENRES with case-insensitive +
        apostrophe-insensitive matching. Returns the genre string or None.
        """
        if not artist:
            return None
        key = self._normalize_artist_key(artist)
        if not key:
            return None
        if self._is_generic_artist_name(artist):
            return None
        for ck, genre in CURATED_ARTIST_GENRES.items():
            if self._normalize_artist_key(ck) == key:
                return genre
        return None

    def _classify_row(self, row: Dict) -> str:
        """Classify a single row into a genre using 4-tier fallback:
          1. _artist_genre_cache (MusicBrainz / propagation) — most reliable
          2. CURATED_ARTIST_GENRES (400+ well-known artists) — authoritative
          3. Keyword match against title ONLY (not review text)
          4. Keyword match against review text as last resort
          5. 'Uncategorized'
        Stores the result in row['_genre'] for O(1) reuse.
        """
        artists = self._extract_artists_from_row(row)

        # Tier 1: Artist cache (MusicBrainz, propagation, etc.), with a
        # pollution guard — a song title that leaked into the artist column
        # must not inherit a genre cached for the leaked name.
        if self._artist_genre_cache:
            for artist in artists:
                cached_genre = self._lookup_genre_cached(artist)
                if cached_genre is not None:
                    row['_genre'] = cached_genre
                    return cached_genre

        # Tier 2: Curated artist-genre mapping (case-insensitive +
        # apostrophe-insensitive so 'Guns N' Roses' matches 'Guns N Roses').
        for artist in artists:
            curated_genre = self._curated_genre_for(artist)
            if curated_genre is not None:
                row['_genre'] = curated_genre
                return curated_genre

        # Tier 3: Keyword match against title ONLY (not review text)
        title_lower = (row.get('title') or '').lower()
        for genre, keywords in self.genre_keywords.items():
            for kw in keywords:
                if self._kw_in_text(kw, title_lower):
                    row['_genre'] = genre
                    return genre

        # Tier 4: Keyword match against review text (last resort)
        combined = ((row.get('tail') or '') + ' ' + (row.get('title') or '')).lower()
        for genre, keywords in self.genre_keywords.items():
            for kw in keywords:
                if self._kw_in_text(kw, combined):
                    row['_genre'] = genre
                    return genre

        # Tier 5: Uncategorized
        row['_genre'] = 'Uncategorized'
        return 'Uncategorized'

    def _classify_rows(self):
        """Pre-compute genre for every row. Called once during __init__."""
        for row in self.rows:
            self._classify_row(row)

    def _extract_artists(self, title: str) -> List[str]:
        """Extract artist names from song title.
        Handles multiple formats:
          - Title (Artist, Year)
          - Artist – Song (forward dash)
          - Song – Artist (reverse dash, checks curated list)
          - Song by Artist
          - Artist: Song
          - [MV] Artist _ Song
        """
        if not title or not isinstance(title, str):
            return []
        results = []

        # ========== EARLY BAIL-OUT PATTERNS (run before dash to avoid false matches) ==========

        # A1: Covered-by pattern: "Song (covered by Artist, Year)"
        m_cov = re.search(r'\(covered\s+by\s+([^)]+)\)', title, re.I)
        if m_cov:
            artist = m_cov.group(1).strip().strip('"').strip("'")
            artist = re.sub(r',?\s*\d{4}\s*$', '', artist).strip()
            artist = re.sub(r'^covered\s+by\s+', '', artist, flags=re.I).strip()
            if artist and len(artist) > 1:
                results.append(artist)

        # A2: Bracket format: "Song [Artist, Year]" or "Song [Artist feat. X, Year]"
        if not results:
            m_br = re.search(r'\[([^\[\]]+?),?\s*\d{4}\]', title)
            if m_br:
                artist = m_br.group(1).strip().strip('"').strip("'")
                feat_match = re.match(r'^(.+?)\s+feat\.\s+(.+)$', artist, re.I)
                if feat_match:
                    artist = feat_match.group(1).strip()
                if artist and len(artist) > 1:
                    results.append(artist)

        # A3: ft/feat in parentheses: "Song (ft. Artist)" or "Song (feat. Artist)"
        # NOTE: deliberately checked AFTER Pattern 1 — the A3 regex matches
        # 'ft.' ANYWHERE inside parens, so running it early hijacked
        # 'Song (Artist A ft. Artist B, Year)' and dropped the primary
        # artist. Pattern 1 splits featured artists correctly when a year is
        # present; A3 then catches the bare-feature forms Pattern 1 can't.

        # A4: Corrupted quotes: "Song ? Artist" (question mark = corrupted single-quote)
        # Use " ? " (space-question-space) to avoid splitting inside words like "Auli'i"
        if not results:
            parts = re.split(r'\s+\?\s+', title)
            if len(parts) >= 2:
                for part in reversed(parts):
                    part = part.strip().strip('"').strip("'")
                    if re.match(r'^\(?\d{4}\)?$', part):
                        continue
                    if re.match(r'^\(?\w+\s*\d{4}\)?$', part):
                        continue
                    if re.match(r'^(ft\.|feat\.)', part, re.I):
                        continue
                    if re.match(r'^[a-z]', part) and len(part.split()) == 1:
                        continue
                    if len(part) > 1:
                        results.append(part)
                        break

        # A5: Single question mark NOT surrounded by spaces (e.g. "Auli'i")
        # Skip this — too risky for false matches

        # ========== Pattern 1: Title (Artist, Year) ==========
        if not results:
            m = re.search(r'\(([^)]+),\s*\d{4}\)', title)
            if m:
                artists_str = m.group(1)
                if not re.search(r'covered\s+by', artists_str, re.I):
                    parts = re.split(r'\s+(?:ft\.|feat\.|featuring|and|&)\s+|\s*,\s*', artists_str)
                    for p in parts:
                        p = p.strip().strip('"').strip("'")
                        if p and len(p) > 1 and p.lower() not in PARSE_ARTIFACTS:
                            results.append(p)

        # ========== Pattern 1b: Title (Artist) without an embedded year ==========
        # Newer imported rows may omit the year but still use an unambiguous
        # final parenthetical artist, e.g. "Fix You (Coldplay)". Restrict this
        # fallback to known artists so song annotations like "(Radio Edit)"
        # cannot become fake artist nodes.
        if not results:
            m_plain = re.search(r'\(([^(),]+)\)\s*$', title)
            if m_plain:
                artist = m_plain.group(1).strip().strip('"').strip("'")
                if (artist and len(artist) > 1
                        and not re.match(r'^(?:ft|feat|covered)\b', artist, re.I)
                        and self._curated_genre_for(artist) is not None):
                    results.append(artist)

        # ========== Pattern 2: Artist – Song (forward) or Song – Artist (reverse) ==========
        if not results:
            m = re.match(r'^(.+?)\s*[–\-]\s+(.+)$', title)
            if m:
                before = m.group(1).strip().rstrip(',').strip('"').strip("'").strip()
                after = m.group(2).strip().rstrip('.').strip('"').strip("'").strip()

                song_indicators = ['theme', 'song', 'anthem', 'ballad', 'medley', 'remix',
                                  'cover', 'version', 'suite', 'symphony', 'sonata']
                before_is_song = any(before.lower().endswith(ind) or before.lower().startswith(ind)
                                     for ind in song_indicators) or before.lower() in PARSE_ARTIFACTS

                candidate_forward = before
                candidate_reverse = after

                forward_known = (self._curated_genre_for(candidate_forward) is not None or
                                 candidate_forward in self._artist_genre_cache or
                                 self._artist_country_cache.get(candidate_forward, '') or
                                 self._country_ci_index.get(candidate_forward.lower(), ''))
                reverse_known = (self._curated_genre_for(candidate_reverse) is not None or
                                 candidate_reverse in self._artist_genre_cache or
                                 self._artist_country_cache.get(candidate_reverse, '') or
                                 self._country_ci_index.get(candidate_reverse.lower(), ''))

                if forward_known and reverse_known:
                    forward_curated = self._curated_genre_for(candidate_forward) is not None
                    reverse_curated = self._curated_genre_for(candidate_reverse) is not None
                    if forward_curated and not reverse_curated:
                        chosen = candidate_forward
                    elif reverse_curated and not forward_curated:
                        chosen = candidate_reverse if not before_is_song else candidate_forward
                    else:
                        chosen = candidate_forward
                    if chosen and len(chosen) > 1 and chosen not in results:
                        results.append(chosen)
                elif reverse_known and not before_is_song:
                    if candidate_reverse and len(candidate_reverse) > 1 and candidate_reverse not in results:
                        results.append(candidate_reverse)
                elif forward_known:
                    if candidate_forward and len(candidate_forward) > 1 and candidate_forward not in results:
                        results.append(candidate_forward)
                else:
                    def _looks_like_artist_name(n):
                        words = n.split()
                        if len(words) < 1 or len(words) > 5:
                            return False
                        cap_words = sum(1 for w in words if w and w[0].isupper())
                        return cap_words >= max(1, len(words) - 1)

                    forward_artist_score = sum(1 for w in candidate_forward.split() if w and w[0].isupper())
                    reverse_artist_score = sum(1 for w in candidate_reverse.split() if w and w[0].isupper())
                    forward_words = len(candidate_forward.split())
                    reverse_words = len(candidate_reverse.split())
                    forward_is_artist = _looks_like_artist_name(candidate_forward)
                    reverse_is_artist = _looks_like_artist_name(candidate_reverse)

                    choose_reverse = False
                    if reverse_is_artist and not forward_is_artist:
                        choose_reverse = True
                    elif forward_is_artist and not reverse_is_artist:
                        choose_reverse = False
                    elif reverse_artist_score > forward_artist_score:
                        choose_reverse = True
                    elif reverse_words >= 2 and reverse_artist_score >= 1 and forward_artist_score == 0:
                        choose_reverse = True
                    elif forward_words > reverse_words and reverse_artist_score >= 1:
                        choose_reverse = True
                    elif before_is_song:
                        choose_reverse = True
                    elif len(candidate_forward) >= 30:
                        choose_reverse = True

                    if choose_reverse:
                        if candidate_reverse and len(candidate_reverse) > 1 and candidate_reverse not in results:
                            results.append(candidate_reverse)
                    else:
                        if candidate_forward and len(candidate_forward) > 1 and candidate_forward not in results:
                            results.append(candidate_forward)

        # ========== A3 (relocated): bare ft/feat feature markers ========== 
        # Runs after Pattern 1/2 so '(Artist A ft. Artist B, Year)' is parsed
        # by Pattern 1's splitter instead of being hijacked here.
        if not results:
            m_ft = re.search(r'\(?ft\.?\s+([^)]+)\)', title, re.I)
            if m_ft:
                artist = m_ft.group(1).strip().strip('"').strip("'")
                artist = re.sub(r',?\s*\d{4}\s*$', '', artist).strip()
                if artist and len(artist) > 1:
                    results.append(artist)

        # Pattern 2b: Em dash / no-space dash
        if not results:
            m2b = re.match(r'^(.+?)\u2014(.+)$', title) or re.match(r'^(.+?)-([A-Z].+)$', title)
            if m2b:
                artist = m2b.group(1).strip().strip('"').strip("'").strip()
                if artist and len(artist) > 1 and artist not in results:
                    results.append(artist)

        # Pattern 2c: Middle dot separator
        if not results:
            m2c = re.match(r'^(.+?)\s*\u00b7\s+(.+)$', title)
            if m2c:
                artist = m2c.group(1).strip().strip('"').strip("'").strip()
                if artist and len(artist) > 1 and artist not in results:
                    results.append(artist)

        # Pattern 2d: Japanese bracket format
        if not results:
            m2d = re.search(r'\u300c([^\u300c\u300d]+)\u300d', title)
            if m2d:
                artist = m2d.group(1).strip()
                if artist and len(artist) > 1 and artist not in results:
                    results.append(artist)
            else:
                m2e = re.search(r'\uff08([^\uff08\uff09]+)\uff09', title)
                if m2e:
                    artist = m2e.group(1).strip()
                    if artist and len(artist) > 1 and artist not in results:
                        results.append(artist)

        # Pattern 2e: Double pipe separator
        if not results:
            m2f = re.match(r'^(.+?)\s*\|\|\s+(.+)$', title)
            if m2f:
                artist = m2f.group(1).strip().strip('"').strip("'").strip()
                if artist and len(artist) > 1 and artist not in results:
                    results.append(artist)

        # Pattern 2e2: Tilde separator
        if not results:
            m_tilde = re.match(r'^(.+?)\s*~\s+(.+)$', title)
            if m_tilde:
                before = m_tilde.group(1).strip().strip('"').strip("'")
                after = m_tilde.group(2).strip().strip('"').strip("'")
                before_known = (before in self._artist_country_cache or
                               self._country_ci_index.get(before.lower(), ''))
                after_known = (after in self._artist_country_cache or
                              self._country_ci_index.get(after.lower(), ''))
                if after_known and not before_known:
                    if after not in results:
                        results.append(after)
                elif before_known:
                    if before not in results:
                        results.append(before)
                else:
                    if after not in results:
                        results.append(after)

        # Pattern 2e3: Double slash separator
        if not results:
            m_slash = re.match(r'^(.+?)\s*//\s*(.+)$', title)
            if m_slash:
                artist = m_slash.group(1).strip().strip('"').strip("'")
                if artist and len(artist) > 1 and artist not in results:
                    results.append(artist)

        # Pattern 2f: Artist "Song Title" with title in quotes
        if not results:
            m2g = re.match(r'^(.+?)\s+["\u201c]([^"\u201d]+)["\u201d]', title)
            if m2g:
                artist = m2g.group(1).strip()
                if artist and len(artist) > 1 and artist not in results:
                    results.append(artist)

        # ========== Pattern 3: Song by Artist ==========
        if not results:
            m2 = re.search(r'\s+by\s+(.+)$', title)
            if m2:
                artist = m2.group(1).strip().strip('"').strip("'").strip('"').rstrip('.').strip()
                if artist and len(artist) > 1 and artist not in results:
                    artist = re.sub(r'^the\s+', '', artist, flags=re.I).strip()
                    if artist and len(artist) > 1:
                        results.append(artist)

        # Pattern 4: Artist: Song
        if not results:
            m3 = re.match(r'^([A-Za-z0-9][A-Za-z0-9\s.]+?):\s+', title)
            if m3:
                artist = m3.group(1).strip()
                if artist and len(artist) > 1 and artist not in results:
                    results.append(artist)

        # Pattern 5: [MV] Artist _ Song (Korean/Japanese format)
        if not results:
            m4 = re.match(r'^\[MV\]\s+(.+?)\s*[_]\s+', title)
            if m4:
                artist = m4.group(1).strip()
                if artist and len(artist) > 1 and artist not in results:
                    results.append(artist)

        return results

    # Known multi-word artists that should NOT be split on ' &' }
    _MULTIWORD_ARTISTS = {
        'earth, wind & fire', 'rage against the machine',
        'system of a down', 'all time low',
        'panic! at the disco', 'fall out boy',
        'my chemical romance', 'avenged sevenfold',
        'breaking benjamin', 'linkin park',
        'guns n\' roses', 'guns n’ roses',
        'nirvana', 'foo fighters',
    }

    def _extract_artists_from_row(self, row: Dict) -> List[str]:
        """Extract artist names, preferring the pre-populated 'artist' column.
        Falls back to parsing the title if 'artist' is empty.
        """
        artist_col = (row.get('artist') or '').strip()
        if not artist_col:
            return self._extract_artists(row.get('title', ''))

        # Guard: 'Announcement' is the meta/system marker, never an artist.
        if artist_col.lower() == 'announcement':
            return []

        # --- Cleaning pipeline ---
        # Normalize Unicode apostrophes to ASCII
        artist_col = artist_col.replace('\u2019', "'").replace('\u2018', "'").replace('\u201c', '"').replace('\u201d', '"')

        # Strip HTML tags
        artist_col = re.sub(r'<[^>]+>', '', artist_col).strip()

        # "Title『Artist』" or "Title【Artist】" — extract from brackets
        m_br = re.search(r'[「『【](.+?)[」』】]', artist_col)
        if m_br:
            artist_col = m_br.group(1).strip()

        # "covered by Artist" — extract artist name
        m_cov = re.search(r'covered\s+by\s+(.+)', artist_col, re.I)
        if m_cov:
            artist_col = m_cov.group(1).strip()

        # Strip trailing parenthetical year/residue: "Artist (2011]" → "Artist"
        artist_col = re.sub(r'\s*\([\w\s,]+\)\s*$', '', artist_col).strip()
        artist_col = re.sub(r'\s*\([\d]{4}\]?\s*$', '', artist_col).strip()

        # Strip ft./feat./featuring/Featuring — keep primary + featured
        ft_match = re.split(r'\s*[,&]?\s*(?:(?<![a-zA-Z])ft\.?\s|(?<![a-zA-Z])feat\.?\s|featuring\s)', artist_col, flags=re.I)
        artists = []
        # Check if this is a known multi-word artist with '&'
        al_check = artist_col.lower()
        is_multiword = any(mw in al_check for mw in self._MULTIWORD_ARTISTS)
        for part in ft_match:
            part = part.strip().strip('()').strip().strip(',').strip()
            if part and len(part) >= 2:
                if is_multiword:
                    artists.append(part)
                else:
                    artists.extend([a.strip() for a in part.split('&') if a.strip() and len(a.strip()) >= 2])
        # Guard: a pre-populated artist column that is song-title pollution
        # must never be indexed as an artist. Two corruption shapes:
        #   A) artist == song and the title is a different string
        #      ('Ambiguous' / 'Ambiguous' from 'GARNiDELiA – Ambiguous')
        #   B) the song column holds the FULL title (the split never
        #      happened), so the artist column is a possibly-wrong slice
        #      ('Ambiguous' / 'GARNiDELiA – Ambiguous')
        # In both, re-parse the title instead of trusting the column.
        # Self-titled tracks (artist == song == title, e.g. 'Iron Maiden')
        # are NOT corruption — the title confirms the pairing.
        song_col = (row.get('song') or '').strip()
        title_col = (row.get('title') or '').strip()
        if artists and len(artists) == 1:
            a0 = artists[0].lower()
            artist_eq_song = song_col and a0 == song_col.lower() \
                and title_col.lower() != a0
            song_holds_title = title_col and song_col.lower() == title_col.lower() \
                and a0 != title_col.lower()
            if artist_eq_song or song_holds_title:
                # When the structured artist column is a curated, normalized
                # artist and the song column contains the full raw title, keep
                # the trusted artist instead of reparsing a malformed separator
                # such as "Happier -Ed Sheeran" as artist="Happier".
                if artists and (
                    self._curated_genre_for(artists[0]) is not None
                    or self._lookup_genre_cached(artists[0]) is not None
                ):
                    return artists
                reparsed = self._extract_artists(row.get('title', ''))
                # If re-parsing the title yields nothing (e.g. title is just
                # "More" with no artist separator), keep the original artist
                # column — discarding it would lose valid genre classification.
                return reparsed if reparsed else artists

        if artists:
            return artists

        # "and" as separator: "Artist1 and Artist2"
        # But skip if it looks like a known multi-word artist
        if ' and ' in artist_col.lower():
            al = artist_col.lower()
            is_multiword = any(mw in al for mw in self._MULTIWORD_ARTISTS)
            if not is_multiword:
                return [a.strip() for a in artist_col.split(' and ') if a.strip() and len(a.strip()) >= 2]

        return [artist_col] if artist_col else []

    @staticmethod
    def _extract_release_year(title: str) -> Optional[int]:
        """Extract the song's release year from its title.
        Prefers a 4-digit year inside parentheses ("Song (Artist, 2012)"),
        falling back to the first plausible year anywhere in the title.
        """
        if not title:
            return None
        current = datetime.now().year

        def _plausible(year: int) -> bool:
            return 1900 <= year <= current

        for m in re.finditer(r'\(([^()]*)\)', title):
            ym = re.search(r'\b(19\d{2}|20\d{2})\b', m.group(1))
            if ym and _plausible(int(ym.group(1))):
                return int(ym.group(1))

        ym = re.search(r'\b(19\d{2}|20\d{2})\b', title)
        if ym and _plausible(int(ym.group(1))):
            return int(ym.group(1))
        return None

    @staticmethod
    def _norm_for_match(text: str) -> str:
        """Strict normalization for matching titles against the song database:
        lowercase, alphanumerics only."""
        return re.sub(r'[^a-z0-9]+', '', (text or '').lower())

    @staticmethod
    def _parse_title_candidates(title: str):
        """Yield (artist, song) candidates for a rating title.
        The data uses several formats:
          "Song (Artist, Year)", "Artist - Song", "Song - Artist"
          and occasionally "Artist | Song" / "Song | Artist".
        For dashed/pipe titles the orientation is ambiguous, so both orders
        are yielded and the database lookup picks whichever one matches.
        """
        m = re.match(r'^(.*?)\s*\(([^)]+?)(?:,\s*(19\d{2}|20\d{2}))?\)\s*$', title or '')
        if m:
            paren = m.group(2).strip()
            # Skip if the parenthetical is not an artist:
            # ft./feat. markers, or year-only like "(2012)"
            skip = False
            if re.match(r'^(?:ft|feat)\.?\b', paren, re.I):
                skip = True  # e.g. "Stay Young (ft. Tessa)"
            elif re.match(r'^\d{4}$', paren):
                skip = True  # year-only, not an artist
            if not skip:
                # Multi-artist credits: "Song (A, B & C)" — the first
                # credited name is the primary artist. Tiny trailing parts
                # ("Jr", "III", "II") belong to the previous name. The full
                # credit string is yielded too: earlier enrichment runs
                # stored cache keys under it, so dropping it would orphan
                # those entries.
                if ',' in paren or '&' in paren:
                    parts = [p.strip() for p in re.split(r',|&', paren)]
                    merged = []
                    for p in parts:
                        if p and merged and len(p.replace('.', '')) <= 3:
                            merged[-1] = f"{merged[-1]}, {p}"
                        elif p:
                            merged.append(p)
                    first = merged[0] if merged else ''
                    if len(first) >= 2:
                        yield first, m.group(1).strip()
                yield paren, m.group(1).strip()
                return
        m2 = re.match(r'^(.+?)\s*[\u2013\u2014-]\s*(.+)$', title or '')
        if m2:
            a, b = m2.group(1).strip(), m2.group(2).strip()
            yield a, b
            yield b, a
            return
        m3 = re.match(r'^(.+?)\s*\|\s*(.+)$', title or '')
        if m3:
            a, b = m3.group(1).strip(), m3.group(2).strip()
            yield a, b
            yield b, a
            return

        # Pattern 4: Artist: Song (colon separator)
        # e.g. "Panic! At The Disco: I Write Sins Not Tragedies"
        m4 = re.match(r'^(.+?):\s+(.+)$', title or '')
        if m4:
            a, b = m4.group(1).strip(), m4.group(2).strip()
            yield a, b
            yield b, a
            return

        # Pattern 5: Song by Artist (case-insensitive)
        # e.g. "Lamentations of the Heart by Philip Wesley" or "Tonight Tonight By Hot Chelle Rae"
        m5 = re.match(r'^(.+?)\s+by\s+(.+)$', title or '', re.IGNORECASE)
        if m5:
            song, artist = m5.group(1).strip(), m5.group(2).strip()
            yield artist, song
            return

        # Pattern 6: Japanese brackets: Song「Artist」or「Artist」Song,
        # and the black-lenticular variant Song【Artist】/【Artist】Song
        # e.g. "Koisuru Kimochi「Kana Nishino」", 「Yura Hatsuki」Shadows,
        # "【Lowland Jazz】純情スカート"
        m6 = re.search(r'[「【]([^」】]+)[」】]', title or '')
        if m6:
            bracket_content = m6.group(1).strip()
            before = title[:m6.start()].strip()
            after = title[m6.end():].strip()
            # Try both orientations: bracket is artist or bracket is song
            if before and bracket_content:
                yield bracket_content, before  # bracket=artist, before=song
                yield before, bracket_content  # bracket=song, before=artist
            if after and bracket_content:
                yield bracket_content, after    # bracket=artist, after=song
                yield after, bracket_content    # bracket=song, after=artist
            return

        # Pattern 7c: square-bracket album markers: "Song [Album]"
        # e.g. "Hey Jude [The Beatles Again]" — bracket holds the album,
        # artist unknown; fall back to the bare title below.
        m6c = re.search(r'\[([^\]]+)\]', title or '')
        if m6c:
            bare = (title[:m6c.start()] + ' ' + title[m6c.end():]).strip()
            if bare:
                yield bare, bare  # self-titled fallback on the bare song
            return

        # Pattern 8: bare title with no separator (self-titled album row,
        # e.g. "The Smiths", "KAI") — only candidate is the title itself.
        # Must not swallow dotted/dashed/bracketed forms handled above/below.
        bare = (title or '').strip()
        if bare and not re.search(r'[\u2013\u2014-]|\||:|\(|\[|「|【|·|\u30fb|\uFF0F', bare):
            yield bare, bare
            return

        # Pattern 7: Multi-artist separator · (middle dot)
        # e.g. "Breakthrough · Adam Hicks · Bridgit Mendler"
        if '·' in (title or ''):
            parts = [p.strip() for p in title.split('·')]
            if len(parts) >= 2:
                # First part is likely song, rest are artists
                yield parts[0], parts[-1]  # song, last artist
                yield parts[-1], parts[0]  # last artist, song
                return

    _release_year_db = None  # lazily built {(norm_artist, norm_song): year}

    @classmethod
    def _db_year_for(cls, title: str) -> Optional[int]:
        """Look up the song's official release year in the curated challenge
        database (data/challenge_db.json), which has authoritative metadata."""
        if cls._release_year_db is None:
            cls._release_year_db = {
                (cls._norm_for_match(e['artist']), cls._norm_for_match(e['song'])): e['year']
                for e in CHALLENGE_DB
            }
        for artist, song in cls._parse_title_candidates(title):
            year = cls._release_year_db.get(
                (cls._norm_for_match(artist), cls._norm_for_match(song))
            )
            if year is not None:
                return year
        return None

    # MusicBrainz-enriched release-year cache: "(norm_artist|norm_song)" → year.
    # Populated by scripts/enrich_release_years.py (the same free MusicBrainz
    # API the genre classifier uses) and committed so the live app, tests, and
    # the GitHub Pages build all resolve years offline.
    _release_year_cache: Dict[str, int] = {}

    @classmethod
    def _release_year_key(cls, artist: str, song: str) -> str:
        """Stable cache key for an (artist, song) pair."""
        return f"{cls._norm_for_match(artist)}|{cls._norm_for_match(song)}"

    @classmethod
    def _load_release_year_cache(cls, path: str = "data/release_year_cache.json"):
        """Load persisted release-year cache from disk (missing/corrupt → no-op)."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                cached = _json.load(f)
                if isinstance(cached, dict):
                    for k, v in cached.items():
                        if isinstance(v, int):
                            cls._release_year_cache[str(k)] = v
                        elif isinstance(v, str) and v.isdigit():
                            cls._release_year_cache[str(k)] = int(v)
        except (FileNotFoundError, ValueError, UnicodeDecodeError):
            pass

    @classmethod
    def _save_release_year_cache(cls, path: str = "data/release_year_cache.json"):
        """Persist release-year cache to disk."""
        try:
            with open(path, 'w', encoding='utf-8') as f:
                _json.dump(cls._release_year_cache, f, indent=2, ensure_ascii=True)
        except Exception:
            pass

    @classmethod
    def _cache_year_for(cls, title: str) -> Optional[int]:
        """Look up a title's release year in the MusicBrainz-enriched cache."""
        for artist, song in cls._parse_title_candidates(title):
            # Try exact key first
            year = cls._release_year_cache.get(cls._release_year_key(artist, song))
            if year is not None:
                return year
            # Also try with ft./feat. stripped from artist and song
            # (old cache entries may have been stored with/without ft.)
            clean_a = re.sub(r'\s*[,*]?\s*ft\.?.*$', '', artist, flags=re.I).strip()
            clean_s = re.sub(r'\s*[,*]?\s*ft\.?.*$', '', song, flags=re.I).strip()
            clean_a = re.sub(r'\s*[,*]?\s*feat\.?.*$', '', clean_a, flags=re.I).strip()
            clean_s = re.sub(r'\s*[,*]?\s*feat\.?.*$', '', clean_s, flags=re.I).strip()
            if clean_a and clean_s:
                year = cls._release_year_cache.get(cls._release_year_key(clean_a, clean_s))
                if year is not None:
                    return year
            # Try reversed artist/song — some titles have them flipped
            # (e.g. "\"Chaeri\" — by Magdalena Bay" → parser: (Chaeri, by Magdalena Bay))
            year = cls._release_year_cache.get(cls._release_year_key(song, artist))
            if year is not None:
                return year
            # Also try with "by" prefix stripped from reversed artist
            # (e.g. parser: (Chaeri, by Magdalena Bay) → reversed: (by Magdalena Bay, Chaeri)
            #  → stripped: (Magdalena Bay, Chaeri) → matches cache)
            by_stripped = re.sub(r'^by\s+', '', song, flags=re.I).strip()
            if by_stripped and by_stripped != song:
                year = cls._release_year_cache.get(cls._release_year_key(by_stripped, artist))
                if year is not None:
                    return year
        # Fallback: unparseable titles can be stored as a normalized full-title key
        # (e.g. "badbloodtaylorswift": 2014 for "Bad Blood Taylor Swift")
        full_norm = cls._norm_for_match(title)
        if full_norm:
            year = cls._release_year_cache.get(full_norm)
            if year is not None:
                return year
        # Also try Unicode normalization under "unicode:" prefix — this catches
        # titles where the cache was stored with the unicode: prefix
        # (e.g. "unicode:baphoneymoon" for "B.A.P _ HONEYMOON")
        unicode_key = 'unicode:' + full_norm if full_norm else ''
        if unicode_key:
            year = cls._release_year_cache.get(unicode_key)
            if year is not None:
                return year
        # Last resort: \w normalization preserves CJK characters
        # (e.g. "unicode:秋山黄色caffeine" for "秋山黄色『Caffeine』")
        unicode_w = re.sub(r'[^\w]', '', (title or '').lower())
        if unicode_w and unicode_w != full_norm:
            year = cls._release_year_cache.get('unicode:' + unicode_w)
            if year is not None:
                return year
        return None

    @classmethod
    def _release_year_source(cls, title: str) -> Optional[str]:
        """Which source resolved this title's release year: 'db' (curated
        challenge database), 'cache' (enrichment), 'title' (year embedded in
        the title), or None. Exposed for the coverage breakdown in
        get_evolution().

        Order matters: the hand-curated database year is authoritative (a
        fuzzy web-search result could otherwise override e.g. Dancing Queen
        1976 with a compilation's 2004). The cache only ever contains songs
        the database didn't have, so in practice it resolves everything else."""
        if cls._db_year_for(title) is not None:
            return 'db'
        if cls._cache_year_for(title) is not None:
            return 'cache'
        if cls._extract_release_year(title) is not None:
            return 'title'
        return None

    # Titles that are fan mashups/remixes of many songs: they have no single
    # release year of their own (the underlying songs have their own years),
    # so they must never appear on the Song vs Year chart.
    _MASHUP_TITLE_RE = re.compile(
        r'(?i)\b(mashup|megamix|medley)\b')

    @classmethod
    def _is_mashup_title(cls, title: str) -> bool:
        return bool(cls._MASHUP_TITLE_RE.search(title or ''))

    @classmethod
    def _release_year_for(cls, title: str) -> Optional[int]:
        """Best-effort release year for a rated song title.
        Resolution order: official challenge database (authoritative), then
        the enrichment cache (MusicBrainz / iTunes results for songs the
        database doesn't have), then the year embedded in the title.
        Mashup/medley titles are always yearless — they compile many songs
        with their own years, so no single year applies."""
        if cls._is_mashup_title(title):
            return None
        src = cls._release_year_source(title)
        if src == 'db':
            return cls._db_year_for(title)
        if src == 'cache':
            return cls._cache_year_for(title)
        return cls._extract_release_year(title)

    @staticmethod
    def _year_from_mb_recording(data: dict) -> Optional[int]:
        """Extract the earliest release year from a MusicBrainz recording search
        response (checks first-release-date and per-release dates)."""
        years = []
        for rec in data.get('recordings', []):
            fd = rec.get('first-release-date') or ''
            m = re.search(r'\b(19\d{2}|20\d{2})\b', fd)
            if m:
                years.append(int(m.group(1)))
            for rel in rec.get('releases', []) or []:
                d = rel.get('date') or ''
                m = re.search(r'\b(19\d{2}|20\d{2})\b', d)
                if m:
                    years.append(int(m.group(1)))
        return min(years) if years else None

    @staticmethod
    def _mb_title_confirms(recorded_title: str, song: str) -> bool:
        """Guard against false-positive MusicBrainz hits: the top recording's
        title must match the song we searched for (exact or containment)."""
        nt = TasteEngine._norm_for_match(recorded_title)
        ns = TasteEngine._norm_for_match(song)
        return bool(nt and ns and (nt == ns or nt in ns or ns in nt))

    @staticmethod
    def _lookup_release_year_musicbrainz(artist: str, song: str) -> Optional[int]:
        """Look up a song's release year via the MusicBrainz public API
        (free, no auth — the same service the genre classifier uses).

        Prefers RELEASE-GROUP search: its first-release-date is the original
        single/album date. Recording search alone is unreliable here — a song
        like Dancing Queen has hundreds of releases and the truncated per-
        recording list is skewed toward compilations (it reports 2004, not
        1976). Falls back to recording search only if no group matches.
        """
        import urllib.request
        import json as _json

        # Strip parenthetical suffices that would break the search
        # (e.g. "(Radio Edit)", "(feat. X)", "(Remastered)").
        clean_song = re.sub(
            r'\s*\((?:radio edit|album version|feat\..*?|ft\..*?|remaster.*?|original mix|edit)\)\s*$',
            '', song.strip(), flags=re.I
        ) or song.strip()
        # Also strip bare ft./feat. at the end of the title
        # (e.g. "Play Hard ft. Ne-Yo, Akon" → "Play Hard")
        clean_song = re.sub(
            r'\s*[,\s]*ft\.?.*$', '', clean_song, flags=re.I
        ).strip() or clean_song
        clean_song = re.sub(
            r'\s*[,\s]*feat\.?.*$', '', clean_song, flags=re.I
        ).strip() or clean_song
        # Strip trailing parenthetical years (from em-dash titles like
        # "Artist – Song (2013)")
        clean_song = re.sub(
            r'\s*\(\d{4}\)\s*$', '', clean_song, flags=re.I
        ).strip() or clean_song
        clean_artist = artist.strip().strip('"').strip("'")
        # Also strip ft./feat. from artist name
        # (e.g. "Christina Perri ft. Jason Mraz" -> "Christina Perri")
        clean_artist = re.sub(
            r'\s*[,\s]*ft\.?.*$', '', clean_artist, flags=re.I
        ).strip() or clean_artist
        clean_artist = re.sub(
            r'\s*[,\s]*feat\.?.*$', '', clean_artist, flags=re.I
        ).strip() or clean_artist

        # --- Primary: release-group search (original release date) ---
        rg_query = urllib.parse.quote(
            f'releasegroup:"{clean_song}" AND artist:"{clean_artist}"'
        )
        rg_url = f'https://musicbrainz.org/ws/2/release-group/?query={rg_query}&fmt=json&limit=3'
        for _retry in range(2):
            rg_req = urllib.request.Request(rg_url, headers={
                'User-Agent': 'TasteScope/1.0 (music-analyzer)',
                'Accept': 'application/json'
            })
            try:
                with urllib.request.urlopen(rg_req, timeout=8) as resp:
                    rg_data = _json.loads(resp.read().decode('utf-8'))
                for group in rg_data.get('release-groups', []) or []:
                    if not TasteEngine._mb_title_confirms(group.get('title', ''), clean_song):
                        continue
                    m = re.search(r'\b(19\d{2}|20\d{2})\b', group.get('first-release-date') or '')
                    if m:
                        return int(m.group(1))
                break  # Got a response (even if 0 results), no retry needed
            except urllib.error.HTTPError as e:
                if e.code == 503 and _retry == 0:
                    time.sleep(3)
                    continue
                break
            except Exception:
                break

        # --- Fallback: recording search (broader, less accurate) ---
        rec_query = urllib.parse.quote(
            f'recording:"{clean_song}" AND artist:"{clean_artist}"'
        )
        rec_url = f'https://musicbrainz.org/ws/2/recording/?query={rec_query}&fmt=json&limit=3'
        for _retry in range(2):
            rec_req = urllib.request.Request(rec_url, headers={
                'User-Agent': 'TasteScope/1.0 (music-analyzer)',
                'Accept': 'application/json'
            })
            try:
                with urllib.request.urlopen(rec_req, timeout=8) as resp:
                    rec_data = _json.loads(resp.read().decode('utf-8'))
                recordings = rec_data.get('recordings', []) or []
                if recordings and TasteEngine._mb_title_confirms(recordings[0].get('title', ''), clean_song):
                    return TasteEngine._year_from_mb_recording(rec_data)
                break
            except urllib.error.HTTPError as e:
                if e.code == 503 and _retry == 0:
                    time.sleep(3)
                    continue
                break
            except Exception:
                break

        # --- Final fallback: Discogs (60 req/min, no auth needed) ---
        try:
            dq = urllib.parse.quote(f'{clean_artist} {clean_song}')
            d_url = f'https://api.discogs.com/database/search?q={dq}&type=release&per_page=3'
            d_req = urllib.request.Request(d_url, headers={
                'User-Agent': 'TasteScope/1.0 (music-analyzer)',
            })
            with urllib.request.urlopen(d_req, timeout=8) as resp:
                d_data = _json.loads(resp.read().decode('utf-8'))
            for r in d_data.get('results', []) or []:
                yr = r.get('year')
                title_match = TasteEngine._mb_title_confirms(
                    r.get('title', ''), clean_song
                )
                if yr and title_match:
                    return int(yr)
        except Exception:
            pass

        return None

    def _build_artist_index(self):
        """Build artist-to-ratings mapping, pre-computing genre for each artist."""
        all_artists_info = defaultdict(lambda: {'ratings': [], 'count': 0, 'songs': [], 'genre_score': defaultdict(int)})

        for r in self.rows:
            artists = self._extract_artists_from_row(r)
            rating = int(r['rating']) if r['rating'] else None
            combined = ((r.get('tail') or '') + ' ' + (r.get('title') or '')).lower()
            is_self_row = self._is_artist_self_row(r)
            
            for artist in artists:
                if rating:
                    all_artists_info[artist]['ratings'].append(rating)
                    if not is_self_row:
                        all_artists_info[artist]['songs'].append({
                            'title': r['title'],
                            'rating': rating,
                            'date': r.get('date', '')
                        })
                        all_artists_info[artist]['count'] += 1
                elif not is_self_row:
                    all_artists_info[artist]['count'] += 1
                
                # Pre-compute genre score during the row iteration (avoids O(n^2) later)
                for genre, keywords in self.genre_keywords.items():
                    for kw in keywords:
                        if self._kw_in_text(kw, combined):
                            all_artists_info[artist]['genre_score'][genre] += 2
                            break
                    else:
                        continue
                    break

        # Convert defaultdict genre scores to a single primary genre string.
        # Curated mapping is authoritative, then the MusicBrainz/Wikidata cache,
        # and only then the keyword vote — a vote from song-title keywords
        # (e.g. "Dance of the Sugar Plum Fairy" → dance) mislabels artists whose
        # catalog merely contains genre-flavored words.
        # Case-insensitive artist identity: names differing only by case
        # ('Lindsey Stirling' vs 'lindsey stirling') are the same artist.
        # The fold key also ignores punctuation/hyphens so 'Yu-Peng Chen' and
        # 'Yu Peng Chen' merge, using the strict alphanumeric matcher.
        # Pure-CJK names normalize to '' under that matcher, so they fall back
        # to plain case-folding to avoid collapsing distinct artists.
        # The canonical display form is the variant with the most ratings
        # (ties → lexicographically smallest for determinism); every other
        # variant is folded away and resolvable via _artist_case().
        # Curated-genre lookup is case-insensitive already, so the folded
        # index keeps the same genre assignment quality.
        folded: Dict[str, Dict] = {}
        display_case: Dict[str, str] = {}
        for artist, info in all_artists_info.items():
            genre_scores = info.pop('genre_score', {})
            curated = self._curated_genre_for(artist)
            if curated is not None:
                info['genre'] = curated
            elif self._lookup_genre_cached(artist) is not None:
                info['genre'] = self._lookup_genre_cached(artist)
            elif genre_scores:
                info['genre'] = max(genre_scores, key=genre_scores.get)
            else:
                info['genre'] = 'Uncategorized'

            key = self._fold_artist_key(artist)
            if key not in folded:
                folded[key] = info
                display_case[key] = artist
            else:
                target = folded[key]
                target['ratings'].extend(info.get('ratings', []))
                target['songs'].extend(info.get('songs', []))
                target['count'] += info.get('count', 0)
                # Genre: prefer a non-Uncategorized assignment from either side.
                if target.get('genre') == 'Uncategorized' and info.get('genre') != 'Uncategorized':
                    target['genre'] = info.get('genre')
        # Second pass: choose display casing per group by rating count.
        display_counts: Dict[str, Dict[str, int]] = defaultdict(dict)
        for artist, info in all_artists_info.items():
            key = self._fold_artist_key(artist)
            display_counts[key][artist] = len(info.get('ratings', []))
        for key in folded:
            variants = display_counts.get(key, {})
            if variants:
                # Most ratings wins; tie → lexicographically smallest name.
                display_case[key] = sorted(variants.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]

        self.all_artists = {display_case[k]: v for k, v in folded.items()}
        self._artist_case_map = {k: display_case[k] for k in folded}
        # Artist index available — re-resolve genre-cache fold conflicts
        # with rating counts (step 2 of the conflict policy).
        self._rebuild_genre_cache_folded()

    def _is_artist_self_row(self, row: Dict) -> bool:
        """True when a row is an artist-level rating, not a song row.

        Some imports write artist ratings as degenerate rows where
        title == artist == song (e.g. title 'Michael Jackson' with artist
        'Michael Jackson'). Treating those as songs corrupts song stats —
        the constellation once listed 'Michael Jackson' as his own song —
        so they count toward artist ratings but never as song entries.
        """
        title = (row.get('title') or '').strip()
        artist = (row.get('artist') or '').strip()
        song = (row.get('song') or '').strip()
        if not title or not artist or title.lower() != artist.lower():
            return False
        # song empty or identical to the artist → artist-level row
        return (not song) or song.lower() == artist.lower()

    def _fold_artist_key(self, name: str) -> str:
        """Identity key for folding artist-name variants: alphanumeric-only
        lowercase when the name has Latin content (merges case/punctuation
        variants like 'Yu-Peng Chen' == 'Yu Peng Chen'), plain case-fold for
        names that normalize to nothing (pure CJK)."""
        strict = self._norm_for_match(name)
        return strict if strict else (name or '').lower().strip()

    def _artist_case(self, name: str) -> str:
        """Resolve an artist name to its canonical display form, ignoring case.

        The artist index is fold-keyed, so exact-case lookups
        (all_artists.get(song_artist)) must go through this resolver —
        otherwise 'lindsey stirling' would miss 'Lindsey Stirling' and
        'Yu Peng Chen' would miss 'Yu-Peng Chen'. Unresolvable names
        return the input unchanged.
        """
        if not name:
            return name
        key = self._fold_artist_key(name)
        if not key:
            return name
        return self._artist_case_map.get(key, name)

    def _init_genre_keywords(self):
        """Initialize genre keyword mapping for classification."""
        self.genre_keywords = GENRE_KEYWORDS.copy()

    def get_stats(self) -> Dict:
        """Get overall statistics about the music taste data."""
        dates = [r['date'] for r in self.rows if r.get('date')]
        stats = {
            'total_entries': len(self.rows),
            'rated_entries': len(self.rated_entries),
            'avg_rating': round(sum(self.ratings) / len(self.ratings), 1) if self.ratings else 0,
            'median_rating': sorted(self.ratings)[len(self.ratings)//2] if self.ratings else 0,
            'min_rating': min(self.ratings) if self.ratings else 0,
            'max_rating': max(self.ratings) if self.ratings else 0,
            'unique_artists': len([a for a in self.all_artists if self.all_artists[a]['ratings']]),
            'date_range': {
                'start': min(dates) if dates else '',
                'end': max(dates) if dates else ''
            },
            'rating_distribution': self._get_rating_distribution(),
            'genre_distribution': self._get_genre_distribution(),
            'top_artists': self._get_top_artists(20),
            'top_songs': self._get_top_songs(50),
            'recent_reviews': self._get_recent_reviews(10),
            'favorite_artists': self.get_favorite_artists(),
        }
        return stats

    # ------------------------------------------------------------------
    # Song deduplication — hash-set-based O(1) lookup
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_sig(text: str) -> str:
        """Normalize a song title / artist string for hashing.
        Strips years, punctuation, extra whitespace, unicode accents, lowercases.
        Dash variants (hyphen '-', en-dash '\u2013', em-dash '\u2014') are unified so
        'Song - Artist' and 'Song \u2013 Artist' dedup to the same signature.
        """
        t = text.lower()
        # Unify dash variants BEFORE punctuation stripping. A spaced dash is
        # the artist/song connector in this dataset ('Song - Artist'), so it
        # is REMOVED like the other connectors ('by', '&', 'vs') — this makes
        # 'Song - Artist', 'Song – Artist' and 'Song – Artist' dedup together
        # while intra-word hyphens (Yu-Peng, punk-o-matic) are preserved.
        t = re.sub(r'[\u2013\u2014\u2015\u2012\u2011]', '-', t)
        t = re.sub(r'\s+-\s+', ' ', t)
        # Remove parenthetical years: (2017), 2017
        t = re.sub(r'\(?\s*\d{4}\s*\)?', '', t)
        # Remove common filler: "ft.", "feat.", "featuring"
        t = re.sub(r'\s+ft\.?\s*|\s+feat\.?\s*|\s+featuring\s*', ' ', t)
        # Remove connecting words between artist/song
        t = re.sub(r'\s+by\s+|\s+and\s+|\s+&\s+|\s+vs\.?\s+', ' ', t)
        # Remove all punctuation except hyphens in words
        t = re.sub(r'[^\w\s-]', ' ', t)
        # Collapse whitespace
        t = re.sub(r'\s+', ' ', t).strip()
        return t

    @staticmethod
    def _normalize_latin(text: str) -> str:
        """Strip all non-Latin characters (CJK, katakana, etc.) keeping only
        a-z, 0-9 and spaces.  Used for cross-script duplicate detection
        (e.g. 'プラスティック・ラブ (Plastic Love)' → 'plastic love').
        """
        t = text.lower()
        t = re.sub(r'\(?\s*\d{4}\s*\)?', '', t)
        t = re.sub(r'\s+ft\.?\s*|\s+feat\.?\s*|\s+featuring\s*', ' ', t)
        # Keep only ASCII alphanumerics + spaces
        t = re.sub(r'[^a-z0-9\s]', ' ', t)
        t = re.sub(r'\s+', ' ', t).strip()
        return t

    @staticmethod
    def _similar_score(a: str, b: str) -> float:
        """Jaccard similarity of word sets between two normalized strings.
        Returns 0.0–1.0.  A score ≥ 0.95 indicates near-duplicate songs
        even when one has extra words (e.g. Japanese transliteration).
        """
        sa = set(a.split())
        sb = set(b.split())
        if not sa or not sb:
            return 0.0
        return len(sa & sb) / len(sa | sb)

    def _build_song_index(self):
        """Build normalized hash sets of all known songs for O(1) duplicate lookup.

        Structures:
          known_sigs     — normalized "artist — song" combo for O(1) exact match
          known_titles   — normalized raw title from the CSV (broader match surface)
          _word_index    — maps each word → set of title sigs (O(1) fuzzy)
          _latin_titles  — Latin-only normalized titles (set for O(1) lookup)
          _latin_to_raw  — latin-normalized → list of raw DB titles (reverse map)
          _raw_to_latin  — raw title → latin-normalized form (forward map)
        """
        sigs: Set[str] = set()
        titles: Set[str] = set()
        latin_titles: Set[str] = set()
        latin_to_raw: Dict[str, List[str]] = defaultdict(list)
        raw_to_latin: Dict[str, str] = {}
        word_index: Dict[str, Set[str]] = defaultdict(set)

        for r in self.rows:
            raw = (r.get('title') or '').strip()
            if not raw or raw == 'Announcement':
                continue
            title_sig = self._normalize_sig(raw)
            titles.add(title_sig)

            # Latin-only normalization for cross-script matching
            latin_sig = self._normalize_latin(raw)
            raw_to_latin[title_sig] = latin_sig
            if latin_sig and latin_sig != title_sig:
                latin_titles.add(latin_sig)
                latin_to_raw[latin_sig].append(title_sig)

            # Index each word for fast fuzzy lookup
            for word in title_sig.split():
                if len(word) >= 2:  # skip single-char noise
                    word_index[word].add(title_sig)

            # Also build artist+sig from extraction for precise matching
            artists = self._extract_artists(raw)
            for artist in artists:
                # Try to extract just the song name from "Title (Artist, Year)"
                m = re.search(r'^(.+?)\s*\(', raw)
                song_part = m.group(1).strip() if m else raw
                combo = f"{artist} {song_part}"
                sigs.add(self._normalize_sig(combo))

        self.known_sigs = sigs
        self.known_titles = titles
        self._latin_titles = latin_titles
        self._latin_to_raw = latin_to_raw
        self._raw_to_latin = raw_to_latin
        self._word_index = word_index

        # Pollution-guard indexes: song-name segments (dash-split title parts
        # plus the dedicated song column) and names confirmed as artists by
        # the engine's own row extraction. Extraction (not the raw column) is
        # the whitelist source because it re-parses corrupted rows to the
        # CORRECT artist — a leaked name never whitelists itself, while
        # title-parsed artists ('Test Artist – Rock Song' with no artist
        # column) and self-titled tracks ('Iron Maiden – Iron Maiden') do.
        segments: Set[str] = set()
        artist_sigs: Set[str] = set()
        # Space on EITHER side counts ('Theme- Lindsey', 'Song- Artist'),
        # so an en-dash glued to one word still splits the title.
        dash_sep = re.compile(r'\s+[\u2013\u2014-]\s*|\s*[\u2013\u2014-]\s+')
        year_meta = re.compile(r'[\s,]+\(?((?:19|20)\d{2})\)?\s*$')
        for r in self.rows:
            title = (r.get('title') or '').strip()
            if title and title != 'Announcement':
                for part in dash_sep.split(title) or [title]:
                    part = year_meta.sub('', part.strip()).strip()
                    part = re.sub(r'\([^()]*\)', ' ', part).strip()  # drop (Artist, Year) / (feat. X)
                    if part:
                        sig = self._normalize_sig(part)
                        if sig:
                            segments.add(sig)
                song_col = (r.get('song') or '').strip()
                if song_col and song_col.lower() != title.lower() \
                        and song_col != 'Announcement':
                    sig = self._normalize_sig(song_col)
                    if sig:
                        segments.add(sig)
            artist_col = (r.get('artist') or '').strip()
            if artist_col and artist_col.lower() != 'announcement':
                sig = self._normalize_sig(artist_col)
                if sig:
                    artist_sigs.add(sig)
            # Names the extraction pipeline itself reports as artists for
            # this row (re-parses leak shapes, parses no-column CSVs).
            try:
                for artist in self._extract_artists_from_row(r):
                    sig = self._normalize_sig(artist)
                    if sig:
                        artist_sigs.add(sig)
            except Exception:
                pass
        self._title_segment_sigs = segments
        self._artist_col_sigs = artist_sigs
    def check_song_exists(self, artist: str, song: str, timeout_sec: float = 10.0) -> Dict:
        """Check whether an artist+song combo already exists in your collection.
        Returns {'exists': True/False, 'match': 'exact'|'fuzzy'|'latin'|'similar'|None,
                 'title': matching title or None}

        Matching tiers:
          1. Exact normalized combo match (O(1))
          2. Exact normalized title match (O(1))
          3. Word-indexed substring containment (O(k))
          4. Latin-only match — catches CJK/katakana variants by comparing
             Latin-normalized forms bidirectionally (O(1) or O(L))
          5. Jaccard word similarity >= 0.95 against Latin titles (O(L))

        Timeout: Aborts after timeout_sec (default 10s) for safety.
        """
        start_time = time.monotonic()

        # 1. Exact O(1): normalized combo in hash set
        combo_sig = self._normalize_sig(f"{artist} {song}")
        if combo_sig in self.known_sigs:
            return {'exists': True, 'match': 'exact', 'title': f"{artist} – {song}"}

        # 2. Exact O(1): normalized song title in hash set
        song_sig = self._normalize_sig(song)
        if song_sig in self.known_titles:
            return {'exists': True, 'match': 'fuzzy', 'title': None}

        # 3. Word-indexed fuzzy O(k): only check titles sharing ≥1 word
        words = [w for w in song_sig.split() if len(w) >= 2]
        candidates: Set[str] = set()
        for word in words:
            candidates.update(self._word_index.get(word, set()))

        for known in candidates:
            if time.monotonic() - start_time > timeout_sec:
                return {'exists': False, 'match': None, 'title': None, 'timeout': True}
            if song_sig in known or known in song_sig:
                return {'exists': True, 'match': 'fuzzy', 'title': None}

        # 4. Latin-only bidirectional matching — catches cross-script duplicates
        #    e.g. 'スパークル (Sparkle)' ↔ 'Sparkle (RADWIMPS, 2016)'
        latin_sig = self._normalize_latin(song)
        latin_combo = self._normalize_latin(f"{artist} {song}") if artist else ''

        if latin_sig and len(latin_sig) >= 3:
            # Forward: input latin form is in the DB's latin set
            if latin_sig in self._latin_titles:
                return {'exists': True, 'match': 'latin', 'title': None}
            # Substring: input latin form is contained in a DB entry's latin form
            # (e.g. 'sparkle' ⊂ 'sparkle radwimps'). Known entries below 3
            # latin chars ('4', 'GO') are exempt from substring matching —
            # containment on them false-positives for any title sharing a
            # character; exact equality above still catches those.
            for known_latin in self._latin_titles:
                if time.monotonic() - start_time > timeout_sec:
                    return {'exists': False, 'match': None, 'title': None, 'timeout': True}
                if len(known_latin) >= 3 and (latin_sig in known_latin or known_latin in latin_sig):
                    return {'exists': True, 'match': 'latin', 'title': None}

        # Also try with artist+song combo (Latin-normalized)
        if latin_combo and len(latin_combo) >= 5:
            if latin_combo in self._latin_titles:
                return {'exists': True, 'match': 'latin', 'title': None}
            # Substring check on combo too — but a known title whose latin
            # form is contained in the ARTIST portion alone (e.g. 'yoasobi'
            # inside 'yoasobi <new song>') is not a song match; without this
            # guard every new song by a latin-named artist would be flagged
            # as a duplicate.
            latin_artist = self._normalize_latin(artist) if artist else ''
            for known_latin in self._latin_titles:
                if time.monotonic() - start_time > timeout_sec:
                    return {'exists': False, 'match': None, 'title': None, 'timeout': True}
                if len(known_latin) >= 3 and (latin_combo in known_latin or (
                    known_latin in latin_combo and known_latin not in latin_artist
                )):
                    return {'exists': True, 'match': 'latin', 'title': None}

        # 5. Jaccard similarity >= 0.95 against Latin titles
        if latin_sig and len(latin_sig) >= 3:
            for known_latin in self._latin_titles:
                if time.monotonic() - start_time > timeout_sec:
                    return {'exists': False, 'match': None, 'title': None, 'timeout': True}
                score = self._similar_score(latin_sig, known_latin)
                if score >= 0.95:
                    return {'exists': True, 'match': 'similar', 'title': None}

        return {'exists': False, 'match': None, 'title': None}

    # ------------------------------------------------------------------
    # Write-time submission screening
    # ------------------------------------------------------------------

    def _candidate_artist_song_pairs(self, title: str):
        """Yield (artist, song) pairs the way the rest of the engine parses
        a submission title: parenthetical credit, dash/pipe/colon separators
        (both orientations), 'by', CJK brackets, plus the (full-title-as-song,
        extracted-artist) pair."""
        seen = set()
        pairs = []

        def _add(artist, song):
            a = (artist or '').strip()
            s = (song or '').strip()
            if a and s and (a, s) not in seen:
                seen.add((a, s))
                pairs.append((a, s))

        for a, s in self._parse_title_candidates(title or ''):
            _add(a, s)
        for artist in self._extract_artists(title or ''):
            _add(artist, title or '')
        return pairs

    def screen_submission(self, title: str) -> Dict:
        """Screen a user submission BEFORE it is written to the CSV. This is
        the write-time half of the data-hygiene policy: the loader already
        guards the existing data (artist-level rows, meta posts, case
        variants), and this keeps new submissions from re-introducing them.

        Returns a decision dict:
          {'decision': 'reject', 'reason': 'artist_level',   ...}
          {'decision': 'reject', 'reason': 'special_post',   ...}
          {'decision': 'reject', 'reason': 'duplicate',      ...}
          {'decision': 'canonicalize', 'title': <fixed>,     ...}
          {'decision': 'accept', 'title': <unchanged>}

        Checks, in order:
          1. Artist-level row — some parse orientation has title == artist
             (self-titled album rows like 'Weezer - Weezer' or 'Michael
             Jackson' rated as a song). These corrupt song statistics, so
             they are rejected outright; an album *rating* belongs in the
             artist-level flow, not the song log.
          2. Archived meta/VS-battle post — the special-posts archive holds
             titles that are posts, not songs; reject so they can't sneak
             back in through the additions CSV.
          3. Duplicate — full check_song_exists (exact, fuzzy, latin,
             similar) against the collection.
          4. Canonicalize — if the parsed artist is a case/punctuation
             variant of a known artist (folded identity), rewrite the title
             to the canonical display spelling so 'yu peng chen' is stored
             as 'Yu-Peng Chen'.
        """
        raw = (title or '').strip()
        if not raw:
            return {'decision': 'accept', 'title': raw}

        # 1. Artist-level rows: reject when any parse orientation yields a
        #    degenerate pair whose artist and song are identical ('Weezer -
        #    Weezer', 'X | X', 'X by X', 'X (X)'). Bare titles are exempt:
        #    their only parse is the (bare, bare) fallback, which is
        #    indistinguishable from an ordinary self-titled song
        #    ('Yesterday') — the loader's artist-column guard handles those
        #    once an artist is known.
        has_structure = bool(re.search(
            r'[\u2013\u2014\-|:\(\)\[\u300c\u3010\u00b7\u30fb\uff0f/]|\bby\b',
            raw, re.I))
        if has_structure:
            for artist, song in self._candidate_artist_song_pairs(raw):
                if artist and song and artist.lower() == song.lower():
                    return {
                        'decision': 'reject',
                        'reason': 'artist_level',
                        'message': (
                            f"'{artist}' is an artist-level rating, not a song "
                            "(the title names the artist on both sides). Rate "
                            "albums on the artist page instead."
                        ),
                        'artist': artist,
                    }

        # 2. Archived meta/VS-battle posts must not re-enter as songs.
        special_sig = self._normalize_sig(raw)
        if special_sig and special_sig in self.special_sigs:
            return {
                'decision': 'reject',
                'reason': 'special_post',
                'message': (
                    "This title is an archived VS-battle / rating-meta post, "
                    "not a song. It is excluded from song statistics by design."
                ),
            }

        # 3. Duplicates (any known artist/song parsing).
        for artist, song in self._candidate_artist_song_pairs(raw):
            dup = self.check_song_exists(artist, song, timeout_sec=3.0)
            if dup.get('exists'):
                return {
                    'decision': 'reject',
                    'reason': 'duplicate',
                    'message': (
                        "This song already exists in your collection "
                        f"(matched: {dup.get('title') or raw})."
                    ),
                    'match': dup.get('match'),
                }

        # 4. Canonicalize the artist spelling when it's a known variant.
        fixed = self.canonicalize_title_artists(raw)
        if fixed != raw:
            return {'decision': 'canonicalize', 'title': fixed}
        return {'decision': 'accept', 'title': raw}

    def canonicalize_title_artists(self, title: str) -> str:
        """Rewrite artist spellings in a submission title to the canonical
        display form from the artist index ('lindsey stirling' → 'Lindsey
        Stirling', 'yu peng chen' → 'Yu-Peng Chen').

        Only names the engine's own extractor identifies as artists are
        rewritten (never arbitrary title words that coincide with an artist
        name), and only whole-name occurrences: the pattern rebuilds each
        artist from its own words with tolerant separators, so case,
        hyphenation and spacing variants all match. A variant already in
        canonical form is left untouched. Names that fold to nothing (pure
        CJK) are skipped — the fold map can't represent them distinctly.
        """
        if not title or not getattr(self, '_artist_case_map', None):
            return title

        result = title
        extracted = sorted(set(self._extract_artists(title)), key=lambda a: -len(a))
        for artist in extracted:
            key = self._fold_artist_key(artist)
            if not key:
                continue
            display = self._artist_case_map.get(key)
            if not display or display == artist:
                continue
            words = [re.escape(w) for w in re.split(r'[\s\-\u2013\u2014_.]+', artist.strip()) if w]
            if not words:
                continue
            sep = r'[\s\-\u2013\u2014_.]*'
            pattern = re.compile(
                r'(?<![a-z0-9])' + sep.join(words) + r'(?![a-z0-9])', re.IGNORECASE)
            result = pattern.sub(
                lambda m: display if self._norm_for_match(m.group(0)) == key else m.group(0),
                result)
        return result

    def _get_rating_distribution(self) -> Dict:
        """Get rating distribution buckets."""
        buckets = {'0-59': 0, '60-69': 0, '70-79': 0, '80-89': 0, '90-95': 0, '96-100': 0}
        for r in self.ratings:
            if r < 60: buckets['0-59'] += 1
            elif r < 70: buckets['60-69'] += 1
            elif r < 80: buckets['70-79'] += 1
            elif r < 90: buckets['80-89'] += 1
            elif r < 96: buckets['90-95'] += 1
            else: buckets['96-100'] += 1
        return buckets

    def _get_genre_distribution(self) -> Dict[str, Dict]:
        """Return genre distribution stats from pre-computed row genres.
        No re-classification — uses row['_genre'] computed once on load.
        """
        genre_data = defaultdict(lambda: {'count': 0, 'ratings': [], 'songs': []})

        for r in self.rows:
            genre = r.get('_genre', 'Uncategorized')
            rating = int(r['rating']) if r['rating'] else None
            genre_data[genre]['count'] += 1
            if rating:
                genre_data[genre]['ratings'].append(rating)
                genre_data[genre]['songs'].append({
                    'title': (r.get('title') or '')[:60],
                    'rating': rating
                })

        result = {}
        for genre, data in sorted(genre_data.items(), key=lambda x: -x[1]['count']):
            avg = round(sum(data['ratings']) / len(data['ratings']), 1) if data['ratings'] else 0
            result[genre] = {
                'count': data['count'],
                'avg_rating': avg,
                'top_songs': sorted(data['songs'], key=lambda x: -x['rating'])[:5]
            }
        # Always include Uncategorized so downstream consumers can rely on the key
        if 'Uncategorized' not in result:
            result['Uncategorized'] = {'count': 0, 'avg_rating': 0, 'top_songs': []}
        return result

    # ------------------------------------------------------------------
    # Genre cache pollution guard
    # ------------------------------------------------------------------

    def _is_title_collision(self, name: str) -> bool:
        """True when `name` is a SONG NAME in the collection rather than an
        artist.

        Historical enrichment passes classified rows by keyword and propagated
        whatever _extract_artists_from_row returned into the genre cache —
        including song titles that had leaked into the artist column
        ('Ambiguous' → Rock, 'Halo Theme' → Soundtrack/Score, 'Africa' →
        Pop). Every genre-cache writer routes through this guard so a song
        name can never masquerade as a cached artist again.

        A name counts as a song when it matches a dash-split segment of some
        title, or a dedicated song-column value — UNLESS the same name also
        appears in the CSV artist column (self-titled tracks like
        'Iron Maiden – Iron Maiden' must keep their artist cached).
        """
        if not name:
            return False
        n = self._normalize_sig(name)
        if not n:
            return False
        if n in self._artist_col_sigs:
            return False
        if n in self._title_segment_sigs:
            return True
        # Paren-suffixed forms: 'Africa (Toto)' is still the song 'Africa'.
        base = re.sub(r'\([^()]*\)', ' ', name)
        if base != name:
            bn = self._normalize_sig(base)
            if bn and bn not in self._artist_col_sigs \
                    and bn in self._title_segment_sigs:
                return True
        return False

    _GENERIC_ARTIST_FOLDS = {
        'unknown', 'various', 'artist', 'variousartists', 'unknownartist',
        'noartist', 'na', 'testartist', 'test',
    }

    def _is_generic_artist_name(self, name: str) -> bool:
        """True for placeholder artist names ('Unknown Artist', 'Various
        Artists', '[unknown artist]', 'Test Artist', ...). These must never
        resolve to a genre — pollution from past test runs and RYM imports
        ('unknown artist': 'J-Pop/Anime') leaks into every unattributed row
        once lookups become case-insensitive."""
        return self._fold_artist_key(name) in self._GENERIC_ARTIST_FOLDS

    def _cache_artist_genre(self, artist: str, genre: str) -> bool:
        """Store artist→genre in the cache UNLESS the name collides with a
        known song title (pollution guard). Returns True when stored."""
        if not artist or not genre:
            return False
        if self._is_title_collision(artist):
            return False
        if self._is_generic_artist_name(artist):
            return False
        self._artist_genre_cache[artist] = genre
        fold_key = self._fold_artist_key(artist)
        if fold_key:
            self._genre_cache_folded[fold_key] = genre
        return True

    def _lookup_genre_cached(self, artist: str) -> Optional[str]:
        """Cached genre lookup that ignores song-title pollution entries —
        a title leaking into the artist column must not inherit a genre
        from the cache (e.g. 'One Foot' would otherwise read 'Rock').
        Matching is case/punctuation-insensitive via the folded index
        ('yu peng chen' finds 'Yu-Peng Chen')."""
        if not artist:
            return None
        if self._is_title_collision(artist):
            return None
        if self._is_generic_artist_name(artist):
            return None
        fold_key = self._fold_artist_key(artist)
        if fold_key and fold_key in self._genre_cache_folded:
            return self._genre_cache_folded[fold_key]
        return self._artist_genre_cache.get(artist)

    @staticmethod
    def _load_artist_country_cache(path: str = 'data/artist_country_cache.json') -> Dict[str, str]:
        """Load persisted artist→country cache from disk."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                cached = _json.load(f)
                if isinstance(cached, dict):
                    return {k: v for k, v in cached.items() if isinstance(v, str)}
        except (FileNotFoundError, ValueError, UnicodeDecodeError):
            pass
        return {}

    @staticmethod
    def _build_country_ci_index(cache: Dict[str, str]) -> Dict[str, str]:
        """Build a lowercase→country index for fast case-insensitive lookup."""
        idx = {}
        for k, v in cache.items():
            if v:
                idx[k.lower()] = v
        return idx

    @staticmethod
    def _build_country_ci_index(cache: Dict[str, str]) -> Dict[str, str]:
        """Build a lowercase→country index for fast case-insensitive lookup."""
        idx = {}
        for k, v in cache.items():
            if v:
                idx[k.lower()] = v
        return idx

    def get_geography(self) -> Dict:
        """Compute geographic listening distribution from artist country cache.
        Returns country distribution, region distribution, and blind spots.
        """
        # COUNTRY_META maps ISO code → {name, region}
        # Defined in the enrichment script; we inline a minimal version here
        # for the region mapping
        REGION_MAP = {
            'US': 'North America', 'CA': 'North America', 'MX': 'North America',
            'CU': 'North America', 'JM': 'North America', 'PR': 'North America',
            'DO': 'North America', 'TT': 'North America',
            'GB': 'Europe', 'DE': 'Europe', 'FR': 'Europe', 'IT': 'Europe',
            'ES': 'Europe', 'SE': 'Europe', 'NO': 'Europe', 'DK': 'Europe',
            'FI': 'Europe', 'NL': 'Europe', 'BE': 'Europe', 'CH': 'Europe',
            'AT': 'Europe', 'IE': 'Europe', 'PT': 'Europe', 'PL': 'Europe',
            'CZ': 'Europe', 'HU': 'Europe', 'RO': 'Europe', 'GR': 'Europe',
            'RU': 'Europe', 'UA': 'Europe', 'IS': 'Europe', 'HR': 'Europe',
            'RS': 'Europe', 'BG': 'Europe', 'SK': 'Europe', 'SI': 'Europe',
            'LT': 'Europe', 'LV': 'Europe', 'EE': 'Europe',
            'JP': 'Asia', 'KR': 'Asia', 'CN': 'Asia', 'TW': 'Asia',
            'TH': 'Asia', 'PH': 'Asia', 'ID': 'Asia', 'MY': 'Asia',
            'SG': 'Asia', 'VN': 'Asia', 'IN': 'Asia', 'TR': 'Asia',
            'IL': 'Asia', 'LB': 'Asia',
            'BR': 'South America', 'AR': 'South America', 'CO': 'South America',
            'CL': 'South America', 'VE': 'South America', 'PE': 'South America',
            'EC': 'South America', 'UY': 'South America',
            'AU': 'Oceania', 'NZ': 'Oceania',
            'ZA': 'Africa', 'NG': 'Africa', 'KE': 'Africa', 'GH': 'Africa',
            'EG': 'Africa', 'MA': 'Africa',
        }

        country_data = defaultdict(lambda: {'count': 0, 'ratings': [], 'artists': set()})
        region_data = defaultdict(lambda: {'count': 0, 'ratings': [], 'countries': set()})
        uncategorized_count = 0
        uncategorized_ratings = []

        for r in self.rows:
            artists = self._extract_artists_from_row(r)
            rating = int(r['rating']) if r['rating'] else None
            
            row_country = None
            for artist in artists:
                code = self._artist_country_cache.get(artist, '')
                if not code:
                    code = self._country_ci_index.get(artist.lower(), '')
                if code:
                    row_country = code
                    break
            
            if row_country:
                country_data[row_country]['count'] += 1
                if rating:
                    country_data[row_country]['ratings'].append(rating)
                for artist in artists:
                    country_data[row_country]['artists'].add(artist)
                
                region = REGION_MAP.get(row_country, 'Other')
                region_data[region]['count'] += 1
                if rating:
                    region_data[region]['ratings'].append(rating)
                region_data[region]['countries'].add(row_country)
            else:
                uncategorized_count += 1
                if rating:
                    uncategorized_ratings.append(rating)

        # Build country list
        # ISO code → friendly name
        COUNTRY_NAMES = {
            'US': 'United States', 'GB': 'United Kingdom', 'CA': 'Canada', 'AU': 'Australia',
            'JP': 'Japan', 'KR': 'South Korea', 'DE': 'Germany', 'FR': 'France', 'IT': 'Italy',
            'ES': 'Spain', 'BR': 'Brazil', 'MX': 'Mexico', 'AR': 'Argentina', 'CO': 'Colombia',
            'CL': 'Chile', 'SE': 'Sweden', 'NO': 'Norway', 'DK': 'Denmark', 'FI': 'Finland',
            'NL': 'Netherlands', 'BE': 'Belgium', 'CH': 'Switzerland', 'AT': 'Austria',
            'IE': 'Ireland', 'PT': 'Portugal', 'PL': 'Poland', 'CZ': 'Czech Republic',
            'HU': 'Hungary', 'RO': 'Romania', 'GR': 'Greece', 'RU': 'Russia', 'UA': 'Ukraine',
            'IS': 'Iceland', 'HR': 'Croatia', 'RS': 'Serbia', 'BG': 'Bulgaria',
            'SK': 'Slovakia', 'SI': 'Slovenia', 'LT': 'Lithuania', 'LV': 'Latvia', 'EE': 'Estonia',
            'TW': 'Taiwan', 'CN': 'China', 'TH': 'Thailand', 'PH': 'Philippines',
            'ID': 'Indonesia', 'MY': 'Malaysia', 'SG': 'Singapore', 'VN': 'Vietnam', 'IN': 'India',
            'TR': 'Turkey', 'IL': 'Israel', 'LB': 'Lebanon',
            'ZA': 'South Africa', 'NG': 'Nigeria', 'KE': 'Kenya', 'GH': 'Ghana',
            'EG': 'Egypt', 'MA': 'Morocco', 'BJ': 'Benin', 'SN': 'Senegal',
            'NZ': 'New Zealand', 'CU': 'Cuba', 'JM': 'Jamaica', 'TT': 'Trinidad and Tobago',
            'PR': 'Puerto Rico', 'DO': 'Dominican Republic', 'VE': 'Venezuela',
            'PE': 'Peru', 'EC': 'Ecuador', 'UY': 'Uruguay',
        }
        countries = []
        for code, data in country_data.items():
            avg = round(sum(data['ratings']) / len(data['ratings']), 1) if data['ratings'] else 0
            top = max(data['ratings']) if data['ratings'] else None
            countries.append({
                'code': code,
                'name': COUNTRY_NAMES.get(code, code),
                'count': data['count'],
                'avg_rating': avg,
                'top_rating': top,
                'artist_count': len(data['artists']),
                'region': REGION_MAP.get(code, 'Other'),
            })
        countries.sort(key=lambda x: -x['count'])

        # Build region list
        regions = []
        for region, data in region_data.items():
            avg = round(sum(data['ratings']) / len(data['ratings']), 1) if data['ratings'] else 0
            top = max(data['ratings']) if data['ratings'] else None
            regions.append({
                'name': region,
                'count': data['count'],
                'avg_rating': avg,
                'top_rating': top,
                'country_count': len(data['countries']),
            })
        regions.sort(key=lambda x: -x['count'])

        # Blind spots: regions with 0 songs
        all_regions = {'North America', 'South America', 'Europe', 'Asia', 'Africa', 'Oceania'}
        explored_regions = {r['name'] for r in regions}
        blind_spots = sorted(all_regions - explored_regions)

        # Coverage stats
        total_rows = len(self.rows)
        covered = total_rows - uncategorized_count
        coverage_pct = round(100 * covered / total_rows, 1) if total_rows else 0

        # Unique countries
        unique_countries = len(countries)
        unique_artists_with_country = sum(len(d['artists']) for d in country_data.values())
        total_artists = len(self.all_artists)

        return {
            'countries': countries,
            'regions': regions,
            'blind_spots': blind_spots,
            'coverage': {
                'total_songs': total_rows,
                'songs_with_country': covered,
                'coverage_pct': coverage_pct,
                'unique_countries': unique_countries,
                'unique_artists_total': total_artists,
                'unique_artists_with_country': unique_artists_with_country,
            },
            'uncategorized': {
                'count': uncategorized_count,
                'avg_rating': round(sum(uncategorized_ratings) / len(uncategorized_ratings), 1) if uncategorized_ratings else 0,
            },
        }

    def _get_top_artists(self, limit: int = 20) -> List[Dict]:
        """Get top artists by average rating (min 2 songs rated)."""
        artists = []
        for artist, info in self.all_artists.items():
            if len(info['ratings']) >= 2:
                avg = round(sum(info['ratings']) / len(info['ratings']), 1)
                artists.append({
                    'name': artist,
                    'avg_rating': avg,
                    'song_count': len(info['ratings']),
                    'top_songs': sorted(info['songs'], key=lambda x: -x['rating'])[:3]
                })
        return sorted(artists, key=lambda x: (-x['avg_rating'], -x['song_count']))[:limit]

    def _get_top_songs(self, limit: int = 50) -> List[Dict]:
        """Get top rated songs."""
        songs = []
        for r in self.rated_entries:
            tail_preview = (r.get('tail') or '')[:150].replace('\n', ' ')
            songs.append({
                'title': r['title'],
                'rating': int(r['rating']),
                'date': r.get('date', ''),
                'preview': tail_preview
            })
        return sorted(songs, key=lambda x: -x['rating'])[:limit]

    def _get_recent_reviews(self, limit: int = 10) -> List[Dict]:
        """Get most recent reviews."""
        recent = sorted(
            [r for r in self.rows if r.get('title', '') != 'Announcement' and r.get('title')],
            key=lambda x: x['date'],
            reverse=True
        )[:limit]
        result = []
        for r in recent:
            tail_preview = (r.get('tail') or '')[:200].replace('\n', ' ')
            result.append({
                'title': (r.get('title') or '')[:80],
                'rating': int(r['rating']) if r.get('rating') else None,
                'date': r.get('date', ''),
                'preview': tail_preview
            })
        return result

    def get_blind_spots(self) -> Dict:
        """Identify genre blind spots and unexplored territory."""
        genre_data = self._get_genre_distribution()
        
        # What you love most (by avg rating)
        loved = sorted(
            [(g, d['avg_rating'], d['count']) for g, d in genre_data.items() if d['count'] >= 3],
            key=lambda x: -x[1]
        )

        # Under-explored genres that might be promising
        blind_spots = {
            'French Touch / House': {
                'why': 'You rated Daft Punk (Get Lucky) 98/100 and love disco/funk. French house is a natural expansion.',
                'suggestion': 'Try: Justice, Air, Stardust, Cassius, DJ Mehdi',
                'expected_rating': '90-96'
            },
            'Neoclassical / Modern Classical': {
                'why': 'You love classical piano (V.K., Philip Wesley, Chopin) and instrumentals. Modern classical composers push this further.',
                'suggestion': 'Try: Ólafur Arnalds, Max Richter, Nils Frahm, Ludovico Einaudi, Yann Tiersen',
                'expected_rating': '88-97'
            },
            'City Pop': {
                'why': 'You rated Plastic Love (Mariya Takeuchi) 98/100 and love groovy/upbeat songs. City pop is a goldmine.',
                'suggestion': 'Try: Tatsuro Yamashita, Anri, Junko Ohashi, Miki Matsubara, Tomoko Aran',
                'expected_rating': '85-96'
            },
            'Eurovision Deep Cuts': {
                'why': 'You consistently rate Eurovision songs highly (avg ~89). Thousands of entries you haven\'t heard.',
                'suggestion': 'Try: Past winners & fan favorites from 2000-2024, national final gems',
                'expected_rating': '80-95'
            },
            'Symphonic Metal': {
                'why': 'You rated Within Temptation and Nightwish perfectly. This is a whole genre built around that sound.',
                'suggestion': 'Try: Epica, Delain, Leaves\' Eyes, Xandria, Eluveitie',
                'expected_rating': '85-98'
            },
            'Electro-Swing Deep Dive': {
                'why': 'You love Caravan Palace (97), Parov Stelar (95-97), Booty Swing. There\'s a whole scene.',
                'suggestion': 'Try: Swingrowers, Jamie Berry, Odd Chap, Wolfgang Lohr, Tape Five, The Correspondents',
                'expected_rating': '85-97'
            },
            'Video Game Soundtracks (Orchestral)': {
                'why': 'You rated Skyrim Theme 99, Gerudo Valley 97, He\'s a Pirate 100. Many game soundtracks match this epic orchestral style.',
                'suggestion': 'Try: Nobuo Uematsu (Final Fantasy), Yoko Shimomura (Kingdom Hearts), Mick Gordon (Doom), Lena Raine (Celeste)',
                'expected_rating': '85-100'
            },
            'J-Pop Deep Cuts / Shibuya-kei': {
                'why': "You love Japanese music (410 songs) and have a refined ear. Shibuya-kei is Japan's answer to sophisticated pop -- think Bacharach meets Haruki Murakami, filtered through 90s Tokyo.",
                'suggestion': "Try: Pizzicato Five, Cornelius ('Point' album), Cibo Matto ('Sugar Water'), Fantastic Plastic Machine, Kahimi Karie.",
                'expected_rating': '85-97'
            },
            'Orchestral Crossover / Neo-Classical Metal': {
                'why': "You love classical (126 songs, avg 87) AND metal (56 songs, avg 81). Neo-classical metal fuses both -- Vivaldi on 12-string guitars with an orchestra behind it.",
                'suggestion': "Try: Yngwie Malmsteen ('Far Beyond the Sun'), Apocalyptica, Symphony X ('The Odyssey'), Trans-Siberian Orchestra, Polyphia ('GOAT').",
                'expected_rating': '85-98'
            },
            'Eurovision Deep Cuts & National Finals': {
                'why': "You rate Eurovision 87.3/100 - one of your highest averages. 1600+ songs in Eurovision history, 3000+ national final entries, and you've barely scratched the surface.",
                'suggestion': "Try: Melfest (Sweden), Vidbir (Ukraine), Sanremo (Italy), Eesti Laul (Estonia), Festival da Cancao (Portugal).",
                'expected_rating': '82-98'
            },
            'Indie/Alt with Depth': {
                'why': 'Your indie avg is low (60), but you love songs with lyrical depth. The right indie (not simple/meandering) could score highly.',
                'suggestion': 'Try: Mitski, Phoebe Bridgers (you rated one), Father John Misty, The National, Arctic Monkeys (AM era)',
                'expected_rating': '75-92'
            },
            'Latin / Reggaeton (Artistic)': {
                'why': 'You gave low scores to reggaeton (Moviendo Caderas 52) but enjoyed artistic Latin pop (Ricky Martin, Shakira).',
                'suggestion': 'Try: Rosalía, Bad Bunny (Un Verano Sin Ti), J Balvin (Colores), C. Tangana',
                'expected_rating': '70-88'
            },
            'Japanese Rock / Math Rock': {
                'why': 'You love Japanese music and rock. Math rock combines technical complexity (which you reward) with Japanese melodies.',
                'suggestion': 'Try: toe, tricot, LITE, Uchu Nekoko, Mass of the Fermenting Dregs',
                'expected_rating': '82-95'
            }
        }

        return {
            'top_loved_genres': loved[:10],
            'blind_spots': blind_spots,
            'year_blind_spots': self._get_year_blind_spots(),
        }

    def _get_year_blind_spots(self, max_under=6, max_low=6) -> List[Dict]:
        """Data-driven release-YEAR blind spots — the era counterpart to the
        hand-written genre spots above. Uses the same release-year resolution
        as the Evolution chart, then flags two kinds of gaps:
          * 'disliked-era': years you rated well BELOW your own average.
          * 'under-explored': years you've barely rated at all (<=2 songs).
        Each spot is paired with acclaimed songs from challenge_db released
        around that year, so it carries a concrete "try these" suggestion.
        """
        year_ratings = defaultdict(list)
        for r in self.rated_entries:
            yr = self._release_year_for(r.get('title', ''))
            if yr:
                year_ratings[yr].append(int(r['rating']))
        if not year_ratings:
            return []

        overall_mean = (sum(self.ratings) / len(self.ratings)) if self.ratings else 80

        def suggestions_for(year):
            """Top acclaimed challenge-DB songs around that year (±1)."""
            cands = [
                c for c in CHALLENGE_DB
                if c.get('year') and abs(c['year'] - year) <= 1
            ]
            cands.sort(key=lambda c: -(c.get('listen_score') or 0))
            return cands[:3]

        spots: List[Dict] = []

        # A) Eras you rate consistently low = genuine dislikes to challenge.
        for yr in sorted(year_ratings):
            rs = year_ratings[yr]
            cnt = len(rs)
            if cnt < 3:
                continue
            avg = sum(rs) / cnt
            if avg < overall_mean - 8:
                sug = suggestions_for(yr)
                spots.append({
                    'kind': 'disliked-era',
                    'year': yr,
                    'count': cnt,
                    'avg': round(avg, 1),
                    'why': (f"You rated {cnt} songs released in {yr} at "
                            f"{avg:.0f}/100 on average — well below your overall "
                            f"{overall_mean:.0f}/100. This era is a gap in your taste."),
                    'suggestion': sug,
                })
        spots.sort(key=lambda s: -s['avg'])  # most-disliked era first
        spots = spots[:max_low]

        # B) Years you've barely explored (<=2 reviews) with acclaimed songs
        #    to offer, least-explored first.
        under = [
            (yr, year_ratings[yr])
            for yr in year_ratings
            if len(year_ratings[yr]) <= 2 and suggestions_for(yr)
        ]
        under.sort(key=lambda t: len(t[1]))
        for yr, rs in under[:max_under]:
            sug = suggestions_for(yr)
            avg = round(sum(rs) / len(rs), 1) if rs else None
            n = len(rs)
            why = f"You've only rated {n} song{'s' if n != 1 else ''} released in {yr}"
            if avg is not None:
                why += f" (avg {avg:g}/100)"
            why += f". Try the acclaimed {yr} songs below."
            spots.append({
                'kind': 'under-explored',
                'year': yr,
                'count': n,
                'avg': avg,
                'why': why,
                'suggestion': sug,
            })

        return spots

    def get_favorite_artists(self) -> List[Dict]:
        """Return your personal favorite artists enriched with genre info and
        stats from your collection. Helps the recommender prioritize similar
        artists and gives you a quick reference of who you love most."""
        favorites = []
        for artist, rating in FAVORITE_ARTISTS.items():
            entry = {
                'name': artist,
                'my_rating': rating,
                'genre': CURATED_ARTIST_GENRES.get(artist, 'Unknown'),
                'in_collection': False,
                'collection_ratings': [],
                'avg_collection_rating': None,
                'song_count': 0,
            }
            canon = self._artist_case(artist)
            if canon in self.all_artists:
                info = self.all_artists[canon]
                entry['in_collection'] = True
                entry['song_count'] = info.get('count', 0)
                entry['collection_ratings'] = info.get('ratings', [])
                if info.get('ratings'):
                    entry['avg_collection_rating'] = round(
                        sum(info['ratings']) / len(info['ratings']), 1
                    )
                # Use the genre from the artist index if available
                coll_genre = info.get('genre')
                if coll_genre and coll_genre != 'Uncategorized':
                    entry['genre'] = coll_genre
            favorites.append(entry)
        # Sort by my_rating descending
        favorites.sort(key=lambda x: -x['my_rating'])
        return favorites

    # ------------------------------------------------------------------
    # Artist popularity (mainstream-ness) — used by the constellation's
    # "Extra Constellation" mode. Popularity is the Spotify 0–100 score,
    # a good proxy for follower counts. Lookup order:
    #   1. data/artist_popularity.json (explicit artist cache, filled by
    #      scripts/cache_artist_popularity.py from the Spotify API)
    #   2. data/challenge_popularity.json (per-song Spotify scores from the
    #      challenge DB — averaged into artist-level scores)
    #   3. Genre base rates (from already-cached artists; uncached genres get
    #      the collection-wide average)
    # Unknown artists stay at a neutral 30 so the axis stays stable.
    # ------------------------------------------------------------------
    @staticmethod
    def _load_artist_popularity_cache(cache_path: Optional[str] = None) -> Dict:
        """Load the explicit artist→popularity cache (Spotify 0–100).
        A missing or corrupt cache degrades gracefully to {} — the Popularity
        mode then falls back to challenge-derived and genre base-rate
        popularity instead of breaking the view."""
        if cache_path is None:
            cache_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'artist_popularity.json')
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                return _json.load(f)
        except _json.JSONDecodeError as e:
            print(f'[WARN] Corrupt artist_popularity.json ({e}) — using fallback popularity')
            return {}
        except (FileNotFoundError, OSError):
            return {}

    @staticmethod
    def _load_artist_fans_cache(fans_path: Optional[str] = None) -> Dict[str, int]:
        """Load the raw artist→fan-count cache (Deezer nb_fan; Spotify
        followers proxy). Missing/corrupt file → {} without raising."""
        if fans_path is None:
            fans_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'artist_popularity_fans.json')
        try:
            with open(fans_path, 'r', encoding='utf-8') as f:
                raw = _json.load(f)
            return {k: int(v) for k, v in raw.items()
                    if isinstance(v, (int, float)) and v > 0}
        except (_json.JSONDecodeError, OSError, ValueError, TypeError):
            return {}

    def _implied_fans_from_popularity(self, pop: int, curve: List[tuple]) -> Optional[int]:
        """Invert the fan→popularity calibration curve: given a Spotify-style
        popularity, return the fan count it implies. Used to place artists on
        the followers axis when only popularity is known (Spotify data)."""
        if not curve or len(curve) < 2 or pop is None:
            return None
        for (x0, y0), (x1, y1) in zip(curve, curve[1:]):
            if y0 <= pop <= y1 or (y1 <= pop <= y0):  # handle any local ordering
                if y1 == y0:
                    return int(round(10 ** x0))
                frac = (pop - y0) / (y1 - y0)
                return int(round(10 ** (x0 + frac * (x1 - x0))))
        # Outside the observed range: clamp to the nearest end.
        if pop < curve[0][1]:
            return int(round(10 ** curve[0][0]))
        if pop > curve[-1][1]:
            return int(round(10 ** curve[-1][0]))
        return None

    def _build_artist_popularity_lookup(self) -> Dict[str, int]:
        """Build artist→popularity map, layering challenge scores over the
        explicit cache, then deriving genre base rates as a fallback."""
        lookup: Dict[str, int] = {}
        explicit = self._load_artist_popularity_cache()
        self._explicit_popularity_artists: Set[str] = set()
        for artist, val in explicit.items():
            try:
                p = int(val)
            except (TypeError, ValueError):
                continue
            if 0 <= p <= 100:
                lookup[artist] = p
                self._explicit_popularity_artists.add(artist)

        # Artist-level averages from the per-song challenge popularity cache.
        # NOTE: these are per-artist facts only — they must NOT feed the genre
        # base rates below, because the challenge DB is curated legendary/
        # acclaimed songs (popularity 83-100) and would drag every genre prior
        # toward "superstar", flattening the X axis.
        challenge = self._load_popularity_cache()
        artist_scores: Dict[str, List[int]] = defaultdict(list)
        for key, meta in challenge.items():
            artist = key.split('|', 1)[0] if isinstance(key, str) else None
            try:
                p = int(meta.get('popularity', -1))
            except (TypeError, ValueError, AttributeError):
                continue
            if artist and 0 <= p <= 100:
                artist_scores[artist].append(p)
        for artist, scores in artist_scores.items():
            lookup.setdefault(artist, round(sum(scores) / len(scores)))

        # Genre base rates: average popularity of explicitly cached artists
        # per genre (trusted curated data only). Gives every artist *some*
        # sensible position on the axis without superstar inflation.
        genre_scores: Dict[str, List[int]] = defaultdict(list)
        for artist, info in self.all_artists.items():
            if artist in self._explicit_popularity_artists and info.get('ratings'):
                p = lookup[artist]
                genre_scores[info.get('genre', 'Uncategorized')].append(p)
        genre_avg = {
            g: round(sum(scores) / len(scores))
            for g, scores in genre_scores.items() if scores
        }
        collection_avg = (
            round(sum(p for scores in genre_scores.values() for p in scores) /
                  max(1, sum(len(s) for s in genre_scores.values())))
            if genre_scores else 30
        )
        self._genre_popularity_base = genre_avg
        self._artist_popularity_collection_avg = collection_avg
        return lookup

    def _artist_popularity(self, artist: str, genre: str, lookup: Dict[str, int]) -> tuple:
        """Popularity (0–100) + source for one artist, with layered fallbacks.
        Source is one of: 'cache', 'challenge', 'genre', 'collection'."""
        p = lookup.get(artist)
        if p is not None:
            src = 'cache' if artist in self._explicit_popularity_artists else 'challenge'
            return p, src
        genre_base = self._genre_popularity_base.get(genre)
        if genre_base is not None:
            return genre_base, 'genre'
        return self._artist_popularity_collection_avg, 'collection'

    def _build_artist_followers_lookup(self, popularity_lookup: Dict[str, int]) -> Dict[str, int]:
        """Build artist→follower-count map (raw Deezer nb_fan, a Spotify
        followers proxy). Layered fallbacks:
          1. Raw fan counts (data/artist_popularity_fans.json)
          2. Popularity inverted through the local fan↔popularity calibration
             curve — a known popularity implies a fan count
          3. Genre median of known follower counts
          4. Collection median
        Followers (not the 0-100 popularity) drive the constellation's
        Followers axis because raw counts span ~6 orders of magnitude and
        spread the collection far better than Spotify's 60-100 clustering.
        """
        fans_cache = self._load_artist_fans_cache()

        # Local calibration curve: fan↔popularity pairs for artists we know
        # BOTH values for (from the on-disk caches; no network needed).
        pairs: List[tuple] = []
        for artist, pop in popularity_lookup.items():
            f = fans_cache.get(artist)
            if f and f > 0:
                pairs.append((math.log10(f), float(pop)))
        pairs.sort()
        # Collapse near-duplicate x values by averaging y.
        merged: Dict[float, List[float]] = {}
        for x, y in pairs:
            merged.setdefault(round(x, 4), []).append(y)
        curve = sorted((x, sum(ys) / len(ys)) for x, ys in merged.items())
        self._pop_fans_curve = curve

        followers: Dict[str, int] = dict(fans_cache)
        self._raw_fans_artists: Set[str] = set(fans_cache.keys())
        implied = 0
        for artist, pop in popularity_lookup.items():
            if artist in followers:
                continue
            f = self._implied_fans_from_popularity(pop, curve)
            if f:
                followers[artist] = f
                implied += 1
        self._implied_fans_count = implied

        # Fallbacks: genre median, then collection median (medians are robust
        # to the superstar tail — the right pick for a log axis).
        rated = [a for a, info in self.all_artists.items() if info.get('ratings')]
        genre_scores: Dict[str, List[int]] = defaultdict(list)
        for artist in rated:
            f = followers.get(artist)
            if f:
                genre = self.all_artists[artist].get('genre', 'Uncategorized')
                genre_scores[genre].append(f)

        def _median(vals: List[int]) -> int:
            s = sorted(vals)
            n = len(s)
            return s[n // 2] if n % 2 else round((s[n // 2 - 1] + s[n // 2]) / 2)

        self._genre_followers_median = {g: _median(v) for g, v in genre_scores.items() if v}
        all_known = [f for v in genre_scores.values() for f in v]
        self._collection_followers_median = _median(all_known) if all_known else 1000
        return followers

    def _artist_followers(self, artist: str, genre: str, followers: Dict[str, int]) -> tuple:
        """Follower count + source for one artist ('fans' | 'implied' |
        'genre' | 'collection')."""
        f = followers.get(artist)
        if f is not None:
            src = 'fans' if artist in self._raw_fans_artists else 'implied'
            return f, src
        g = self._genre_followers_median.get(genre)
        if g is not None:
            return g, 'genre'
        return self._collection_followers_median, 'collection'

    def get_constellation(self) -> Dict:
        """Build artist similarity network for the constellation view.
        Uses a multi-tier edge strategy:
          1. Collaboration edges — artists that appear together in songs
          2. Genre-similarity edges — artists sharing the same genre
          3. Rating-pattern edges — artists with similar rating profiles
          4. Community detection (Louvain) — finds natural groupings from the
             edge structure, assigns each artist a community_id so the frontend
             can cluster them visually without needing a genre-based layout.
        Each node also carries 'popularity' (Spotify 0–100, best-effort) with
        'popularity_source' ('cache' | 'challenge' | 'genre' | 'collection'),
        and 'followers' (raw Deezer nb_fan, a Spotify followers proxy) with
        'followers_source' ('fans' | 'implied' | 'genre' | 'collection')
        for the popularity / followers × genre chart modes.
        """
        popularity_lookup = self._build_artist_popularity_lookup()
        followers_lookup = self._build_artist_followers_lookup(popularity_lookup)
        nodes: List[Dict] = []
        edges: List[Dict] = []
        artist_set: Set[str] = set()
        genre_artists: Dict[str, List[str]] = defaultdict(list)
        artist_ratings_vec: Dict[str, List[int]] = {}  # for rating-pattern similarity

        # Build nodes from artists with ratings
        for artist, info in self.all_artists.items():
            if len(info['ratings']) > 0:
                artist_set.add(artist)
                avg = round(sum(info['ratings']) / len(info['ratings']), 1)
                max_r = max(info['ratings'])
                genre = info.get('genre', 'Uncategorized')
                pop, pop_src = self._artist_popularity(artist, genre, popularity_lookup)
                fol, fol_src = self._artist_followers(artist, genre, followers_lookup)
                # Top rated songs (best 3 by rating) so tooltips can show the
                # actual songs behind the artist — makes mislabeled or
                # mis-parsed artist names immediately visible.
                top_songs = [
                    {'title': s['title'][:60], 'rating': s['rating']}
                    for s in sorted(info['songs'], key=lambda x: -x['rating'])[:3]
                ]
                nodes.append({
                    'id': artist,
                    'name': artist,
                    'avg_rating': avg,
                    'song_count': len(info['ratings']),
                    'max_rating': max_r,
                    'genre': genre,
                    'genre_x': genre_spectrum_x(genre),
                    'popularity': pop,
                    'popularity_source': pop_src,
                    'followers': fol,
                    'followers_source': fol_src,
                    'top_songs': top_songs
                })
                genre_artists[genre].append(artist)
                artist_ratings_vec[artist] = info['ratings']

        # ---- Edges ----

        # Tier 1: Collaboration edges (artists appearing together in songs)
        seen_collab: Set[tuple] = set()
        for r in self.rows:
            artists = self._extract_artists_from_row(r)
            for i in range(len(artists)):
                for j in range(i+1, len(artists)):
                    if artists[i] in artist_set and artists[j] in artist_set:
                        key = tuple(sorted([artists[i], artists[j]]))
                        if key not in seen_collab:
                            seen_collab.add(key)
                            edges.append({
                                'source': artists[i],
                                'target': artists[j],
                                'song': (r.get('title') or '')[:40]
                            })

        # Tier 2: Genre-similarity edges — denser connectivity so the graph
        # has enough structure for community detection to work well.
        seen_genre: Set[tuple] = set()
        for genre, artists in genre_artists.items():
            if len(artists) >= 2:
                for i, artist in enumerate(artists):
                    for j in range(i + 1, min(i + 6, len(artists))):
                        if artist in artist_set and artists[j] in artist_set:
                            key = tuple(sorted([artist, artists[j]]))
                            if key not in seen_genre and key not in seen_collab:
                                seen_genre.add(key)
                                edges.append({
                                    'source': artist,
                                    'target': artists[j],
                                    'song': f"Same genre: {genre}"
                                })

        # Tier 3: Rating-pattern similarity (artists you rate similarly tend
        # to be related). Only for artists with 10+ ratings to avoid noise.
        # Sample each artist's ratings into a histogram for comparison.
        # We use a simple overlap measure: shared rating-range affinity.
        seen_rating: Set[tuple] = set()
        high_count_artists = [
            (a, v) for a, v in sorted(
                [(a, len(r)) for a, r in artist_ratings_vec.items()],
                key=lambda x: -x[1]
            )
            if v >= 5
        ]
        for i in range(len(high_count_artists)):
            a1, c1 = high_count_artists[i]
            if c1 < 5:
                continue
            for j in range(i + 1, min(i + 8, len(high_count_artists))):
                a2, c2 = high_count_artists[j]
                if c2 < 5:
                    continue
                key = tuple(sorted([a1, a2]))
                if key in seen_collab or key in seen_genre or key in seen_rating:
                    continue

                # Rating preference overlap: do they share the same "zone"?
                vec1 = artist_ratings_vec[a1]
                vec2 = artist_ratings_vec[a2]
                avg1 = sum(vec1) / len(vec1)
                avg2 = sum(vec2) / len(vec2)
                if abs(avg1 - avg2) < 8:
                    seen_rating.add(key)
                    edges.append({
                        'source': a1,
                        'target': a2,
                        'song': f"Similar avg rating ({round(avg1, 1)} vs {round(avg2, 1)})"
                    })

        # ---- Community Detection (Louvain) ----
        # Build a NetworkX graph from our edges and run modularity-based community
        # detection. This finds natural groupings that the frontend can use to
        # cluster artists visually, even in "unsorted" mode.
        communities_meta: Dict[str, Dict] = {}
        try:
            G = nx.Graph()
            for node in nodes:
                G.add_node(node['id'])
            for edge in edges:
                G.add_edge(edge['source'], edge['target'])

            if G.number_of_edges() > 0 and G.number_of_nodes() > 1:
                # Louvain community detection
                communities = louvain_communities(G, seed=42)

                # Build artist → community_id map
                artist_to_community: Dict[str, int] = {}
                community_id = 0
                for community in communities:
                    for artist in community:
                        artist_to_community[artist] = community_id
                    community_id += 1

                # Attach community_id to each node
                for node in nodes:
                    cid = artist_to_community.get(node['id'], -1)
                    node['community_id'] = cid

                # Build community metadata: size, dominant genre, top artists
                community_data: Dict[int, Dict] = {}
                for node in nodes:
                    cid = node['community_id']
                    if cid < 0:
                        continue
                    if cid not in community_data:
                        community_data[cid] = {
                            'size': 0,
                            'genres': defaultdict(int),
                            'top_artists': [],
                            'avg_rating': 0
                        }
                    community_data[cid]['size'] += 1
                    community_data[cid]['genres'][node.get('genre', 'Unknown')] += 1
                    community_data[cid]['top_artists'].append({
                        'name': node['name'],
                        'song_count': node['song_count'],
                        'avg_rating': node['avg_rating']
                    })

                # Summarize each community
                for cid, data in community_data.items():
                    # Dominant genre = most common genre in this community
                    dominant_genre = max(data['genres'], key=data['genres'].get)
                    # Top artists by song count
                    data['top_artists'] = sorted(
                        data['top_artists'],
                        key=lambda x: -x['song_count']
                    )[:5]
                    # Average rating across community
                    ratings = [a['avg_rating'] for a in data['top_artists'] if a['avg_rating']]
                    data['avg_rating'] = round(sum(ratings) / len(ratings), 1) if ratings else 0
                    data['dominant_genre'] = dominant_genre
                    # Keep genre breakdown (for legend display)
                    data['genre_breakdown'] = dict(sorted(
                        data['genres'].items(), key=lambda x: -x[1]
                    )[:3])
                    del data['genres']  # clean up

                communities_meta = {
                    str(k): v for k, v in sorted(
                        community_data.items(), key=lambda x: -x[1]['size']
                    )
                }
        except Exception:
            # If community detection fails (e.g., no edges), fall back gracefully
            for node in nodes:
                node['community_id'] = -1

        # Defect fix: if the graph had <= 1 node or 0 edges, the `if` condition
        # above was false and the except didn't run, so community_id is unset.
        # Assign -1 to any node still missing the key.
        for node in nodes:
            node.setdefault('community_id', -1)

        return {
            'nodes': nodes,
            'edges': edges,
            'communities': communities_meta,
            'community_count': len(communities_meta)
        }

    def get_evolution(self) -> Dict:
        """Track taste evolution over time."""
        # Group ratings by month. Rows with no review date (for example a
        # score import) still contribute to rating/genre analysis, but cannot
        # be placed honestly on a review timeline.
        monthly = defaultdict(list)
        for r in self.rated_entries:
            month_key = (r.get('date') or '')[:7]  # YYYY-MM
            if re.fullmatch(r'\d{4}-\d{2}', month_key):
                monthly[month_key].append(int(r['rating']))

        monthly_avg = {}
        for month, ratings in sorted(monthly.items()):
            monthly_avg[month] = round(sum(ratings) / len(ratings), 1)

        # Genre evolution over time — uses pre-computed row['_genre']
        genre_monthly = defaultdict(lambda: defaultdict(list))
        for r in self.rows:
            if r.get('rating'):
                month_key = (r.get('date') or '')[:7]
                genre = r.get('_genre', 'Uncategorized')
                if genre != 'Uncategorized':
                    genre_monthly[genre][month_key].append(int(r['rating']))

        genre_evolution = {}
        for genre, months in genre_monthly.items():
            sorted_months = sorted(months.items())
            if len(sorted_months) >= 3:
                genre_evolution[genre] = [
                    {'month': m, 'avg': round(sum(r)/len(r), 1), 'count': len(r)}
                    for m, r in sorted_months
                ]

        # Yearly stats. Missing/invalid review dates are excluded from this
        # time series rather than being grouped under a misleading blank year.
        yearly = defaultdict(list)
        for r in self.rated_entries:
            year = (r.get('date') or '')[:4]
            if re.fullmatch(r'\d{4}', year):
                yearly[year].append(int(r['rating']))

        yearly_avg = {}
        for year, ratings in sorted(yearly.items()):
            yearly_avg[year] = {
                'avg': round(sum(ratings) / len(ratings), 1),
                'count': len(ratings),
                'top_rating': max(ratings)
            }

        # Cumulative song count — adaptive sampling targets ~200 data points
        cumulative = []
        dated_rows = [r for r in self.rows if re.fullmatch(r'\d{4}-\d{2}-\d{2}', r.get('date') or '')]
        sorted_rows = sorted(dated_rows, key=lambda x: x['date'])
        # First pass: count total eligible songs to compute step size
        total_songs = sum(
            1 for r in sorted_rows
            if r.get('title', '') and r.get('title', '') != 'Announcement' and r.get('rating')
        )
        step = max(1, total_songs // 200)  # target ~200 chart points
        count = 0
        for r in sorted_rows:
            if r.get('title', '') and r.get('title', '') != 'Announcement':
                if r.get('rating'):
                    count += 1
                    if count % step == 0 or count == 1 or count == total_songs:
                        cumulative.append({
                            'date': r.get('date', ''),
                            'total_songs': count
                        })

        # Average rating by song RELEASE year: official challenge-database
        # match first, then the year embedded in the title. Independent of when
        # the review was written, so it reveals which eras of music you actually
        # enjoyed most, not just when you listened.
        release_year_ratings = defaultdict(list)
        release_year_by_source = {'cache': 0, 'db': 0, 'title': 0}
        for r in self.rated_entries:
            title = r.get('title', '')
            yr = self._release_year_for(title)
            if yr:
                release_year_ratings[yr].append(int(r['rating']))
                src = self._release_year_source(title)
                if src in release_year_by_source:
                    release_year_by_source[src] += 1

        release_year_avg = {
            str(yr): {
                'avg': round(sum(rs) / len(rs), 1),
                'count': len(rs),
                'top_rating': max(rs),
            }
            for yr, rs in sorted(release_year_ratings.items())
        }

        release_year_coverage = {
            'matched': sum(len(rs) for rs in release_year_ratings.values()),
            'total': len(self.rated_entries),
            'by_source': release_year_by_source,
        }

        return {
            'monthly_avg': monthly_avg,
            'yearly': yearly_avg,
            'genre_evolution': genre_evolution,
            'cumulative': cumulative,
            'release_year_avg': release_year_avg,
            'release_year_coverage': release_year_coverage
        }

    # ------------------------------------------------------------------
    # Uncategorized Breakdown — detailed analysis of unclassified songs
    # ------------------------------------------------------------------

    @staticmethod
    def _kw_in_text(keyword: str, text: str) -> bool:
        """Check if keyword appears in text, using word boundary matching
        for short keywords (<= 4 chars) to avoid false positives like 'ost' in 'post'.
        """
        if len(keyword) <= 4:
            # Use word boundary regex for short keywords
            return bool(re.search(r'\b' + re.escape(keyword) + r'\b', text))
        return keyword in text

    def get_uncategorized_breakdown(self) -> Dict:
        """Analyze all uncategorized songs using pre-computed row['_genre'].
        Only processes rows where _genre == 'Uncategorized', avoiding re-classification.
        Groups results by:
          - Known artists (artists in CURATED_ARTIST_GENRES but classification failed)
          - Unknown artists (extractable but not in any mapping)
          - No-artist entries (can't extract artist name at all)
          - Meta/system entries (Announcement, monthly recaps, etc.)
        """

        breakdown = {
            'known_artists': {},      # artist → {count, sample_songs, suggested_genre}
            'unknown_artists': {},    # artist → {count, sample_songs}
            'no_artist': [],          # list of {title, preview, rating}
            'meta_entries': [],       # Announcement, roundups, etc
            'total': 0,
            'by_pattern': {},         # pattern → count
        }

        for r in self.rows:
            # Use pre-computed genre — only process rows still Uncategorized
            if r.get('_genre', 'Uncategorized') != 'Uncategorized':
                continue

            breakdown['total'] += 1
            rating = r.get('rating', '')
            title = r.get('title', '')
            preview = ((r.get('tail') or '')[:150] or '').replace('\n', ' ')
            artists = self._extract_artists_from_row(r)
            if artists:
                artist = artists[0]
                # Check if this artist is known but classification missed it
                if artist in CURATED_ARTIST_GENRES:
                    # Known artist! This means classification hit a gap
                    sug = CURATED_ARTIST_GENRES[artist]
                    if artist not in breakdown['known_artists']:
                        breakdown['known_artists'][artist] = {
                            'count': 0, 'sample_songs': [], 'suggested_genre': sug
                        }
                    breakdown['known_artists'][artist]['count'] += 1
                    if len(breakdown['known_artists'][artist]['sample_songs']) < 3:
                        breakdown['known_artists'][artist]['sample_songs'].append(title[:60])
                else:
                    # Unknown artist — needs classification
                    if artist not in breakdown['unknown_artists']:
                        breakdown['unknown_artists'][artist] = {
                            'count': 0, 'sample_songs': []
                        }
                    breakdown['unknown_artists'][artist]['count'] += 1
                    if len(breakdown['unknown_artists'][artist]['sample_songs']) < 3:
                        breakdown['unknown_artists'][artist]['sample_songs'].append(title[:60])
            else:
                # No extractable artist
                if not title.strip() or _is_meta_title(title):
                    breakdown['meta_entries'].append({'title': title[:60], 'rating': rating})
                else:
                    # Try to determine what pattern this title uses
                    pattern = 'other'
                    if '–' in title or '-' in title:
                        pattern = 'dash_title'
                    elif re.search(r'\d{4}', title):
                        pattern = 'year_only'
                    elif title.startswith('"') or title.startswith('['):
                        pattern = 'quoted_or_marked'
                    elif re.search(r'\s+by\s+', title, re.I):
                        pattern = 'by_keyword'

                    breakdown['by_pattern'][pattern] = breakdown['by_pattern'].get(pattern, 0) + 1
                    breakdown['no_artist'].append({
                        'title': title[:60],
                        'preview': preview[:100],
                        'rating': rating,
                        'pattern': pattern
                    })

        # Sort groups by count descending
        for key in ['known_artists', 'unknown_artists']:
            sorted_items = sorted(breakdown[key].items(), key=lambda x: -x[1]['count'])
            breakdown[key] = dict(sorted_items[:50])  # Keep top 50

        # Summarize for quick scanning
        breakdown['summary'] = {
            'total_uncategorized': breakdown['total'],
            'by_known_artists': sum(v['count'] for v in breakdown['known_artists'].values()),
            'by_unknown_artists': sum(v['count'] for v in breakdown['unknown_artists'].values()),
            'no_artist_count': len(breakdown['no_artist']),
            'meta_count': len(breakdown['meta_entries']),
        }

        return breakdown

    # Ban List
    # ---------

    def _load_ban_list(self):
        """Load the ban list from data/ban_list.json.
        Schema: {"genres": ["Eurovision"], "artists": [], "songs": []}
        Missing keys default to empty lists."""
        try:
            with open(self.ban_list_path, "r", encoding="utf-8") as f:
                d = _json.load(f)
            self.ban_list = {
                "genres": [g.lower() for g in (d.get("genres") or [])],
                "artists": [a.lower() for a in (d.get("artists") or [])],
                "songs": [s.lower() for s in (d.get("songs") or [])],
            }
        except (FileNotFoundError, _json.JSONDecodeError):
            self.ban_list = {"genres": [], "artists": [], "songs": []}

    def _is_banned(self, artist: str = "", song: str = "", genre: str = "") -> bool:
        """Check if an artist, song, or genre is in the ban list.
        Returns True if ANY of the provided values match.
        Matching is case-insensitive with exact and substring checks.

        Song bans are stored either as a bare title ("Karma Police") or as a
        combined "Artist \u2013 Song" string (what the Ignore button sends). So the
        provided (artist, song) pair is matched against BOTH forms \u2014 otherwise a
        song ignored from a challenge would keep reappearing in the results."""
        if not artist and not song and not genre:
            return False

        def norm(t: str) -> str:
            return (t or "").lower().strip()

        na = norm(artist)
        ns = norm(song)
        ng = norm(genre)
        bl = self.ban_list

        # Genres
        if ng:
            for b in bl["genres"]:
                b = norm(b)
                if b and (b == ng or b in ng or ng in b):
                    return True

        # Artists
        if na:
            for b in bl["artists"]:
                b = norm(b)
                if b and (b == na or b in na or na in b):
                    return True

        # Songs \u2014 match a bare title and/or an "artist \u2013 song" compound entry.
        if ns:
            def _squash(t: str) -> str:
                """Normalize dashes and whitespace so e.g. 'A \u2013 B' == 'A - B'."""
                t = re.sub(r"\s*[\u2014\u2013-]\s*", " ", t)
                return re.sub(r"\s+", " ", t).strip()

            bs = _squash(ns)
            compounds = [bs]
            if na and ns:
                compounds.append(_squash(f"{na} \u2013 {ns}"))
                compounds.append(_squash(f"{na} - {ns}"))

            for b in bl["songs"]:
                if not b:
                    continue
                bsq = _squash(norm(b))
                if not bsq:
                    continue
                for cand in compounds:
                    if cand and (bsq == cand or bsq in cand or cand in bsq):
                        return True
        return False

    def check_recs(self, recs: List[Dict]) -> List[Dict]:
        """Tag each recommendation as already_owned True/False using the hash set.
        Also tags favorite_adjacent True if the rec artist is one of your personal
        favorite artists or shares a genre with one."""
        # Build a set of favorite artists and their genres for O(1) lookup
        fav_artists = set(FAVORITE_ARTISTS.keys())
        fav_genres = set()
        for artist in FAVORITE_ARTISTS:
            g = CURATED_ARTIST_GENRES.get(artist)
            if g:
                fav_genres.add(g)
            canon = self._artist_case(artist)
            if canon in self.all_artists:
                g2 = self.all_artists[canon].get('genre')
                if g2 and g2 != 'Uncategorized':
                    fav_genres.add(g2)

        checked = []
        for rec in recs:
            dup = self.check_song_exists(rec.get('artist', ''), rec.get('song', ''))
            is_fav_adjacent = False
            # Direct match: rec artist is a favorite
            if rec.get('artist') in fav_artists:
                is_fav_adjacent = True
            else:
                # Genre match: rec artist shares a genre with a favorite
                rec_genre = None
                rec_canon = self._artist_case(rec.get('artist', ''))
                if rec_canon in self.all_artists:
                    rec_genre = self.all_artists[rec_canon].get('genre')
                elif rec.get('artist') in CURATED_ARTIST_GENRES:
                    rec_genre = CURATED_ARTIST_GENRES[rec['artist']]
                if rec_genre and rec_genre in fav_genres and rec_genre != 'Uncategorized':
                    is_fav_adjacent = True
            # Resolve release year from cache for display on the card.
            year = rec.get('year') or self._release_year_for(
                f"{rec.get('artist', '')} – {rec.get('song', '')}"
            )
            checked.append({
                **rec,
                'already_owned': dup['exists'],
                'favorite_adjacent': is_fav_adjacent,
                'year': year,
            })
        return checked

    def _build_dynamic_categories(self) -> Dict:
        """Build recommendation categories dynamically from the user's taste fingerprint.
        
        Uses top influences, genre fingerprint, and artist affinity to generate
        personalized recommendation groups. Falls back to empty dict if insufficient data.
        """
        import math
        
        # 1. Build taste profile from rated songs
        positive_songs = [r for r in self.rated_entries if int(r.get('rating', 0)) >= 75]
        if len(positive_songs) < 20:
            return {}  # Not enough data for dynamic recs
        
        # Genre affinity: genre → sum of ratings
        genre_ratings = defaultdict(list)
        for r in positive_songs:
            g = r.get('_genre', 'Uncategorized')
            genre_ratings[g].append(int(r['rating']))
        
        # Artist affinity: artist → avg rating, song count
        artist_data = defaultdict(lambda: {'ratings': [], 'genres': set()})
        for r in positive_songs:
            artists = self._extract_artists_from_row(r)
            rating = int(r['rating'])
            genre = r.get('_genre', 'Uncategorized')
            for a in artists:
                artist_data[a]['ratings'].append(rating)
                artist_data[a]['genres'].add(genre)
        
        # Top genres by total weight
        genre_weights = {g: sum(rs) for g, rs in genre_ratings.items()}
        top_genres = sorted(genre_weights.items(), key=lambda x: -x[1])[:6]
        
        # Top influences (already computed in fingerprint)
        fp = self.get_taste_fingerprint()
        top_influences = fp.get('top_influences', [])[:8]
        influence_names = {inf['artist'] for inf in top_influences}
        
        # Build owned set for dedup
        self._build_song_index()
        owned = self.known_sigs
        
        # Artist avg lookup
        artist_avg = {}
        for a, info in artist_data.items():
            if info['ratings']:
                artist_avg[a] = sum(info['ratings']) / len(info['ratings'])
        
        categories = {}
        
        # --- Category 1: Top Influence Deep Cuts ---
        # For each top influence, find songs by similar artists in the challenge DB
        influence_cats = []
        for inf in top_influences[:4]:
            artist = inf['artist']
            avg = inf['avg_rating']
            genres = set(inf.get('genres', []))
            if avg < 80 or inf['song_count'] < 2:
                continue
            # Find challenge DB songs in matching genres
            candidates = []
            for c in CHALLENGE_DB:
                c_artist = (c.get('artist') or '').strip()
                c_song = (c.get('song') or '').strip()
                if not c_artist or not c_song:
                    continue
                sig = self._normalize_sig(f"{c_artist} {c_song}")
                if sig in owned:
                    continue
                # Genre match — skip if influence genre is Uncategorized (too broad)
                raw_g = (c.get('genre') or '').strip()
                c_class = GENRE_ALIAS_TO_CLASS.get(raw_g, 'Uncategorized')
                meaningful_genres = genres - {'Uncategorized'}
                if not meaningful_genres:
                    continue  # Can't match if influence has no real genre
                genre_match = c_class in meaningful_genres or any(g in c_class for g in meaningful_genres)
                if not genre_match:
                    continue
                # Score: genre affinity + influence proximity + acclaim
                ga = genre_weights.get(c_class, 0) / max(genre_weights.values()) if genre_weights else 0
                aa = (artist_avg.get(c_artist, 50)) / 100.0 if c_artist in artist_avg else 0.3
                q = (c.get('listen_score') or 60) / 100.0
                score = 0.40 * ga + 0.35 * aa + 0.25 * q
                candidates.append({
                    'artist': c_artist, 'song': c_song,
                    'score': round(score, 3),
                    'reason': f"Similar to {artist} (your #{top_influences.index(inf)+1} influence, avg {avg:.0f}) · {raw_g or c_class} · acclaim {int(q*100)}/100",
                    'genre': raw_g or c_class,
                    'already_owned': False,
                    'year': c.get('year'),
                })
            candidates.sort(key=lambda x: -x['score'])
            if candidates:
                influence_cats.append((
                    f"Because you love {artist}",
                    {'artists': [artist], 'recommendations': candidates[:5]}
                ))
        
        # Add top 3 influence-based categories
        for name, data in influence_cats[:3]:
            categories[name] = data
        
        # --- Category 2: Genre-based picks from top genres ---
        for genre, weight in top_genres[:3]:
            if genre in ('Uncategorized', 'META/Other'):
                continue
            genre_avg = sum(genre_ratings[genre]) / len(genre_ratings[genre])
            candidates = []
            for c in CHALLENGE_DB:
                c_artist = (c.get('artist') or '').strip()
                c_song = (c.get('song') or '').strip()
                if not c_artist or not c_song:
                    continue
                sig = self._normalize_sig(f"{c_artist} {c_song}")
                if sig in owned:
                    continue
                raw_g = (c.get('genre') or '').strip()
                c_class = GENRE_ALIAS_TO_CLASS.get(raw_g, 'Uncategorized')
                if c_class != genre and genre.lower() not in c_class.lower():
                    continue
                ga = weight / max(genre_weights.values()) if genre_weights else 0
                aa = (artist_avg.get(c_artist, 50)) / 100.0 if c_artist in artist_avg else 0.3
                q = (c.get('listen_score') or 60) / 100.0
                score = 0.45 * ga + 0.25 * aa + 0.30 * q
                candidates.append({
                    'artist': c_artist, 'song': c_song,
                    'score': round(score, 3),
                    'reason': f"You rate {genre} {genre_avg:.0f}/100 on average · {raw_g or c_class} · {c.get('tier', 'acclaimed').replace('_', ' ').title()} pick",
                    'genre': raw_g or c_class,
                    'already_owned': False,
                    'year': c.get('year'),
                })
            candidates.sort(key=lambda x: -x['score'])
            if candidates:
                categories[f"🔥 Top {genre} picks"] = {
                    'artists': [a for a, d in artist_data.items() if genre in d['genres']][:5],
                    'recommendations': candidates[:5],
                }
        
        # --- Category 3: Era-based picks ---
        decade_ratings = defaultdict(list)
        for r in positive_songs:
            yr = self._release_year_for(r.get('title', ''))
            if yr:
                decade_ratings[(yr // 10) * 10].append(int(r['rating']))
        if decade_ratings:
            top_decade = max(decade_ratings.items(), key=lambda x: sum(x[1]))[0]
            decade_avg = sum(decade_ratings[top_decade]) / len(decade_ratings[top_decade])
            candidates = []
            for c in CHALLENGE_DB:
                c_artist = (c.get('artist') or '').strip()
                c_song = (c.get('song') or '').strip()
                c_year = c.get('year')
                if not c_artist or not c_song or not c_year:
                    continue
                sig = self._normalize_sig(f"{c_artist} {c_song}")
                if sig in owned:
                    continue
                c_decade = (c_year // 10) * 10
                if c_decade != top_decade:
                    continue
                q = (c.get('listen_score') or 60) / 100.0
                score = 0.5 * q + 0.3 * (decade_avg / 100.0) + 0.2 * 0.5
                candidates.append({
                    'artist': c_artist, 'song': c_song,
                    'score': round(score, 3),
                    'reason': f"From the {top_decade}s, which you rate {decade_avg:.0f}/100 · {c.get('tier', 'acclaimed').replace('_', ' ').title()} pick",
                    'genre': (c.get('genre') or 'Uncategorized').strip(),
                    'already_owned': False,
                    'year': c_year,
                })
            candidates.sort(key=lambda x: -x['score'])
            if candidates:
                categories[f"📅 From the {top_decade}s"] = {
                    'artists': [],
                    'recommendations': candidates[:5],
                }
        
        # --- Category 4: Cross-genre wildcards ---
        # Songs from genres you don't normally listen to but are highly acclaimed
        my_genres = {g for g in genre_weights}
        # A genre you've rated heavily below neutral is a miss, not a 'blind spot'
        # to explore — keep those out of wildcard discovery.
        net_pull = self._genre_net_affinity()
        disliked_genres = {g for g, p in net_pull.items() if p <= -0.15}
        wildcards = []
        for c in CHALLENGE_DB:
            c_artist = (c.get('artist') or '').strip()
            c_song = (c.get('song') or '').strip()
            if not c_artist or not c_song:
                continue
            sig = self._normalize_sig(f"{c_artist} {c_song}")
            if sig in owned:
                continue
            raw_g = (c.get('genre') or '').strip()
            c_class = GENRE_ALIAS_TO_CLASS.get(raw_g, 'Uncategorized')
            if c_class in my_genres or c_class in disliked_genres:
                continue
            q = (c.get('listen_score') or 60) / 100.0
            if q < 0.85:  # Only highly acclaimed for wildcards
                continue
            wildcards.append({
                'artist': c_artist, 'song': c_song,
                'score': round(q * 0.8, 3),
                'reason': f"Outside your usual {', '.join(list(my_genres)[:3])} · {raw_g or c_class} · {c.get('tier', 'acclaimed').replace('_', ' ').title()} ({int(q*100)}/100)",
                'genre': raw_g or c_class,
                'already_owned': False,
                'year': c.get('year'),
            })
        wildcards.sort(key=lambda x: -x['score'])
        if wildcards:
            categories['🌍 Cross-genre discoveries'] = {
                'artists': [],
                'recommendations': wildcards[:5],
            }
        
        # Cross-category dedup: remove songs that appear in multiple categories
        seen_songs = set()
        for cat_name, cat_data in list(categories.items()):
            deduped = []
            for r in cat_data.get('recommendations', []):
                key = f"{r['artist'].lower()}|{r['song'].lower()}"
                if key not in seen_songs:
                    seen_songs.add(key)
                    deduped.append(r)
            cat_data['recommendations'] = deduped
        
        # Remove empty categories
        categories = {k: v for k, v in categories.items() if v.get('recommendations')}
        
        return categories

    def get_recommendations(self, style: str = 'all') -> Dict:
        """Generate song recommendations based on taste profile.
        Every recommendation is tagged with already_owned=True/False via O(1) hash lookup.
        """
        # 1. Dynamic categories from taste fingerprint
        rec_categories = self._build_dynamic_categories()
        if not rec_categories:
            # Fallback: static hand-curated categories
            rec_categories = {
            'If you love Lindsey Stirling & Taylor Davis': {
                'artists': ['Lindsey Stirling', 'Taylor Davis', 'The Piano Guys'],
                'recommendations': self.check_recs([
                    {'artist': 'Apocalyptica', 'song': 'Nothing Else Matters', 'reason': 'Cellos doing metal — combines your love of instrumental prowess and rock'},
                    {'artist': '2CELLOS', 'song': 'Thunderstruck', 'reason': 'You rated their work well; this is their signature piece'},
                    {'artist': 'David Garrett', 'song': 'He\'s a Pirate (Violin Cover)', 'reason': 'You love the Pirates theme, and Garrett is a virtuoso violinist'},
                    {'artist': 'Tina Guo', 'song': 'Game of Thrones Medley', 'reason': 'Epic cello covers similar to Lindsey Stirling\'s style'},
                    {'artist': 'Simply Three', 'song': 'Palladio', 'reason': 'You rated their work 99-100; this is one of their best'},
                    {'artist': 'Two Steps From Hell', 'song': 'Heart of Courage', 'reason': 'Epic trailer-core built around bold strings — perfect if you love Stirling\'s cinematic side'},
                    {'artist': 'Lindsey Stirling', 'song': 'Shatter Me', 'reason': 'Stirling\'s crossover masterpiece — electric violin meets a soaring chorus'},
                ])
            },
            'If you love electro-swing & disco': {
                'artists': ['Caravan Palace', 'Parov Stelar', 'Daft Punk', 'Earth, Wind and Fire'],
                'recommendations': self.check_recs([
                    {'artist': 'Jamie Berry', 'song': 'Delight', 'reason': 'Classic electro-swing with the same infectious energy as Booty Swing'},
                    {'artist': 'Swingrowers', 'song': 'That\'s Right!', 'reason': 'Modern electro-swing that rivals Caravan Palace'},
                    {'artist': 'Tape Five', 'song': 'Swing it Like a Monkey', 'reason': 'Playful electro-swing that matches your love of unique/quirky'},
                    {'artist': 'Electric Light Orchestra', 'song': 'Mr. Blue Sky', 'reason': 'Disco orchestral pop — bridges your love of orchestral and groovy'},
                    {'artist': 'Chic', 'song': 'Le Freak', 'reason': 'Essential funk/disco from the golden era you clearly enjoy'},
                    {'artist': 'Caravan Palace', 'song': 'Lone Digger', 'reason': 'Their most hypnotic, danceable track — a must for electro-swing fans'},
                    {'artist': 'Parov Stelar', 'song': 'Catgroove', 'reason': 'The electro-swing anthem that started it all — same energy as Booty Swing'},
                ])
            },
            'If you love Fall Out Boy & rock anthems': {
                'artists': ['Fall Out Boy', 'Muse', 'Queen', 'Within Temptation', 'Nightwish'],
                'recommendations': self.check_recs([
                    {'artist': 'My Chemical Romance', 'song': 'Welcome to the Black Parade', 'reason': 'Theatrical rock anthem in the same vein as Bohemian Rhapsody'},
                    {'artist': 'Panic! At The Disco', 'song': 'Emperor\'s New Clothes', 'reason': 'You liked Death of a Bachelor; this is similarly theatrical'},
                    {'artist': 'Epica', 'song': 'Unleashed', 'reason': 'Symphonic metal that matches your Within Temptation/Nightwish love'},
                    {'artist': 'Poets of the Fall', 'song': 'My Dark Disquiet', 'reason': 'You rated this 96 — they have many more songs at this quality level'},
                    {'artist': 'BEAST IN BLACK', 'song': 'Born Again', 'reason': 'You rated this 95 — they\'re a whole band built on this sound'},
                    {'artist': 'Muse', 'song': 'Knights of Cydonia', 'reason': 'A sprawling, theatrical rock anthem in the same grand tradition as Queen'},
                    {'artist': 'Fall Out Boy', 'song': 'Centuries', 'reason': 'Stadium-sized chorus and quotable hooks — peak pop-rock anthemics'},
                ])
            },
            'If you love Japanese music & Vocaloid': {
                'artists': ['Hatsune Miku', 'Ado', 'LiSA'],
                'recommendations': self.check_recs([
                    {'artist': 'YOASOBI', 'song': 'Idol', 'reason': 'Modern J-pop phenomenon with incredible production — you\'d likely love this'},
                    {'artist': 'Ado', 'song': 'Usseewa', 'reason': 'You rated Ado\'s Odo 96; Usseewa is her breakout hit with raw energy'},
                    {'artist': 'Eve', 'song': 'Kaikai Kitan', 'reason': 'Anime rock with unique production and emotional depth'},
                    {'artist': 'Kenshi Yonezu', 'song': 'KICK BACK', 'reason': 'One of Japan\'s biggest artists — quirky, creative, and well-produced'},
                    {'artist': 'ZUTOMAYO', 'song': 'Byoushin wo Kamu', 'reason': 'Genre-bending Japanese with intricate instrumentation and unique vocals'},
                    {'artist': 'Ado', 'song': 'Odo', 'reason': 'You rated this 96 — electrifying performance that defined modern J-pop'},
                    {'artist': 'Kenshi Yonezu', 'song': 'Lemon', 'reason': 'Japan\'s best-selling digital single ever — huge emotional resonance'},
                ])
            },
            'Undiscovered gems matching your taste': {
                'artists': [],
                'recommendations': self.check_recs([
                    {'artist': 'Hooverphonic', 'song': 'Mad About You', 'reason': 'You rated 2Wicky 100/100 -- more dreamy trip-hop from the same band'},
                    {'artist': 'Kokia', 'song': 'Arigatou', 'reason': 'You rated Kirin 97/100 -- Kokia\'s most beloved song, an ethereal ballad'},
                    {'artist': 'Infected Mushroom', 'song': 'Becoming Insane', 'reason': 'You rated Heavyweight 99/100 -- more psytrance mastery'},
                    {'artist': 'Chase Holfelder', 'song': "Kiss the Girl in Minor Key", 'reason': 'You rated this 96/100 -- many more minor key covers to explore'},
                    {'artist': 'Mariya Takeuchi', 'song': 'Plastic Love', 'reason': 'You rated this 98/100 -- check her album Variety for more city pop gold'},
                    {'artist': 'The Piano Guys', 'song': 'Story of My Life', 'reason': 'Acoustic/classical crossover reimagining modern pop — right up your alley'},
                    {'artist': 'Vitamin String Quartet', 'song': 'Viva La Vida', 'reason': 'Classical strings meet modern pop — a familiar melody in your favorite format'},
                ])
            },
            'If you love Classical & Video Game Soundtracks': {
                'artists': ['Lindsey Stirling', 'Taylor Davis', 'V.K.', 'Simply Three', 'Hans Zimmer'],
                'recommendations': self.check_recs([
                    {'artist': 'Joe Hisaishi', 'song': "One Summer's Day", 'reason': 'Spirited Away theme -- bridges your classical piano love (V.K. 100/100) and film scores'},
                    {'artist': 'Ludovico Einaudi', 'song': 'Nuvole Bianche', 'reason': 'Modern classical masterpiece -- the 21st-century Chopin you need to hear'},
                    {'artist': 'Yann Tiersen', 'song': "Comptine d'un autre ete", 'reason': 'Amelie soundtrack -- delicate piano storytelling for classical/instrumental fans'},
                    {'artist': 'Nobuo Uematsu', 'song': "Aerith's Theme", 'reason': 'Final Fantasy VII -- epic orchestral score that bridges your soundtrack and classical loves'},
                    {'artist': 'Max Richter', 'song': 'On the Nature of Daylight', 'reason': 'Modern classical with cinematic scope -- from Arrival and Shutter Island. You\'d rate 90+'},
                    {'artist': 'Joe Hisaishi', 'song': 'Merry-Go-Round of Life', 'reason': 'Howl\'s Moving Castle theme -- the lush orchestral waltz you\'d love'},
                    {'artist': 'Yoko Shimomura', 'song': 'Dearly Beloved', 'reason': 'Kingdom Hearts\' iconic piano theme -- bridges your pop and score loves'},
                ])
            },
            'If you love Eurovision & International Pop': {
                'artists': ['Loreen', 'Salvador Sobral', 'Duncan Laurence'],
                'recommendations': self.check_recs([
                    {'artist': 'Loreen', 'song': 'Euphoria', 'reason': 'Eurovision 2012 winner -- you rate Eurovision 87/100; widely considered the best entry ever'},
                    {'artist': 'Salvador Sobral', 'song': 'Amar Pelos Dois', 'reason': 'Eurovision 2017 winner -- stunning jazz ballad, won with a record 93% of the final vote'},
                    {'artist': 'Go_A', 'song': 'SHUM', 'reason': 'Ukrainian electro-folk from Eurovision 2021 -- blends your love of electronic and world music'},
                    {'artist': 'Kaarija', 'song': 'Cha Cha Cha', 'reason': 'Eurovision 2023 phenomenon -- Finnish party metal that became a global critical darling'},
                    {'artist': 'Mans Zelmerlow', 'song': 'Heroes', 'reason': 'Eurovision 2015 winner -- stadium-pop anthem that defined mid-2010s Eurovision'},
                    {'artist': 'Måneskin', 'song': 'Zitti e Buoni', 'reason': 'Eurovision 2021 winner -- raw Italian rock that stunned Europe'},
                    {'artist': 'Rosa Linn', 'song': 'Snap', 'reason': 'Eurovision 2022 viral hit -- modern, emotional alt-pop you may have missed'},
                ])
            },
            'If you love City Pop & 80s Japanese Pop': {
                'artists': ['Mariya Takeuchi', 'Tatsuro Yamashita', 'Miki Matsubara', 'Anri', 'Junko Ohashi'],
                'recommendations': self.check_recs([
                    {'artist': 'Tatsuro Yamashita', 'song': 'Christmas Eve', 'reason': 'The definitive city pop ballad — Japan\'s most-played holiday song'},
                    {'artist': 'Miki Matsubara', 'song': 'Stay With Me', 'reason': 'A city pop classic reborn in the streaming era — silky and groovy'},
                    {'artist': 'Anri', 'song': 'Shyness Boy', 'reason': 'Upbeat 80s city pop with that perfect, summery grove'},
                    {'artist': 'Junko Ohashi', 'song': 'Telephone Number', 'reason': 'Smooth, funky city pop from the genre\'s golden era'},
                    {'artist': 'Taeko Onuki', 'song': '4:00 AM', 'reason': 'Sophisticated, jazzy city pop that collectors obsess over'},
                ])
            },

        }

        # 2. Add algorithm-scored picks from challenge DB
        algo_picks = self.get_algorithmic_recommendations(7)
        if algo_picks:
            rec_categories['🎯 Algorithm picks (scored from your taste)'] = {
                'artists': [],
                'recommendations': algo_picks,
            }

        # 3. Run fuzzy dedup on ALL recommendations (dynamic categories
        #    hard-code already_owned=False with only a hash check, which
        #    misses near-duplicates like 'Billie Jean' vs 'Billie Jean '.
        #    check_recs uses the full 5-tier fuzzy matching pipeline.)
        for cat_name, cat_data in rec_categories.items():
            cat_data['recommendations'] = self.check_recs(
                cat_data['recommendations']
            )

        # 4. Filter out songs already in collection, banned songs, and
        #    rating-suppressed artists. The ban layer and the rating layer
        #    converge here: an artist you've rated below ~40/100 across 3+
        #    songs behaves exactly like one you Ignored (see suppression_state),
        #    so low ratings genuinely suppress recommendations instead of just
        #    slightly changing their score.
        suppressed_artists = {
            a.lower().strip() for a in self._auto_suppressed_artists()
        }
        for cat_name, cat_data in rec_categories.items():
            cat_data['recommendations'] = [
                r for r in cat_data['recommendations']
                if not r.get('already_owned', False)
                and r.get('artist', '').lower().strip() not in suppressed_artists
                and not self._is_banned(
                    artist=r.get('artist', ''),
                    song=r.get('song', ''),
                    genre=cat_name,
                )
            ]

        # Remove empty categories so the frontend doesn't render
        # blank sections for genres/artists the user has banned.
        rec_categories = {
            k: v for k, v in rec_categories.items()
            if v.get('recommendations')
        }

        return rec_categories

    # ------------------------------------------------------------------
    # Negative-feedback helpers
    # ------------------------------------------------------------------

    # An artist is 'actively disliked' once they have at least this many rated
    # songs with an average below this threshold. Fewer songs than this is more
    # likely an instant reject / single exposure than a verdict.
    DISLIKE_ARTIST_MIN_COUNT = 3
    DISLIKE_ARTIST_MAX_AVG = 40

    # A genre counts as 'actively disliked' (auto-suppressed) once its net pull
    # drops to or below this and it has at least this many rated songs — a
    # single 1/100 reject is an instant dislike, not a genre verdict.
    SUPPRESS_GENRE_MAX_NET = -0.15
    SUPPRESS_GENRE_MIN_COUNT = 3

    def _genre_net_affinity(self) -> Dict[str, float]:
        """Per-genre net affinity over ALL rated songs, centered at 50.

        Returns {genre: pull} where pull = (avg - 50)/50 damped toward 0 for
        sparse genres (a genre with one 100-rated song should not dominate a
        genre with forty 90s). Unlike the old summed metric, ratings below 50
        produce a NEGATIVE pull, so deliberately disliked genres actively
        demote candidates instead of merely contributing ~0.
        """
        genre_sum: Dict[str, float] = defaultdict(float)
        genre_cnt: Dict[str, int] = defaultdict(int)
        for r in self.rated_entries:
            g = r.get('_genre') or 'Uncategorized'
            genre_sum[g] += int(r['rating'])
            genre_cnt[g] += 1

        pull: Dict[str, float] = {}
        for g, n in genre_cnt.items():
            avg = genre_sum[g] / n
            net = (avg - 50.0) / 50.0          # -1..1, 0 at 'neutral 50'
            conf = n / (n + 5.0)               # sparse genres lean neutral
            pull[g] = net * conf
        pull['Uncategorized'] = 0.0
        return pull

    def _artist_rating_stats(self) -> Dict[str, Dict]:
        """{artist: {'avg': .., 'count': ..}} from all rated rows."""
        stats = {}
        for a, info in self.all_artists.items():
            rs = info.get('ratings') or []
            if rs:
                stats[a] = {'avg': sum(rs) / len(rs), 'count': len(rs)}
        return stats

    def _is_actively_disliked_artist(self, artist: str, stats: Dict[str, Dict]) -> bool:
        s = stats.get(artist)
        if not s:
            return False
        return (s['count'] >= self.DISLIKE_ARTIST_MIN_COUNT and
                s['avg'] < self.DISLIKE_ARTIST_MAX_AVG)

    def _auto_suppressed_artists(self) -> Dict[str, Dict]:
        """Artists your ratings have effectively 'ignored' — rated below
        DISLIKE_ARTIST_MAX_AVG across DISLIKE_ARTIST_MIN_COUNT+ songs.

        These are the rating layer's equivalent of ban-list artist entries:
        get_recommendations() filters them exactly like manual bans, while
        Challenges/Discovery stay acclaim-driven. Returned as
        {artist: {'avg', 'count', 'reason'}} so the UI can explain them.
        """
        stats = self._artist_rating_stats()
        out = {}
        for artist, s in stats.items():
            if self._is_actively_disliked_artist(artist, stats):
                out[artist] = {
                    'avg': round(s['avg'], 1),
                    'count': s['count'],
                    'reason': f"rated {int(round(s['avg']))}/100 across {s['count']} songs",
                }
        return out

    def _auto_suppressed_genres(self) -> Dict[str, Dict]:
        """Genres your ratings have effectively 'ignored' — net pull at or below
        SUPPRESS_GENRE_MAX_NET with SUPPRESS_GENRE_MIN_COUNT+ rated songs.

        These are informational (shown in the Suppress panel and excluded from
        cross-genre wildcards); they demote but never hard-ban, because a genre
        is shared across many artists and Challenges exist to push boundaries.
        """
        pull = self._genre_net_affinity()
        genre_sum: Dict[str, int] = defaultdict(int)
        genre_cnt: Dict[str, int] = defaultdict(int)
        for r in self.rated_entries:
            g = r.get('_genre') or 'Uncategorized'
            genre_sum[g] += int(r['rating'])
            genre_cnt[g] += 1

        out = {}
        for g, p in pull.items():
            n = genre_cnt.get(g, 0)
            if p <= self.SUPPRESS_GENRE_MAX_NET and n >= self.SUPPRESS_GENRE_MIN_COUNT:
                avg = genre_sum[g] / n
                out[g] = {
                    'avg': round(avg, 1),
                    'count': n,
                    'net': round(p, 3),
                    'reason': f"averages {int(round(avg))}/100 across {n} songs",
                }
        return out

    def suppression_state(self) -> Dict[str, Dict]:
        """Everything currently suppressed — manual bans (ban_list) plus the
        rating-derived auto-suppressions. The two layers converge here: an
        artist you rated 1/100 across 20 songs shows up exactly like one you
        hit Ignore on, so the Ignore button and low ratings speak the same
        language."""
        return {
            'manual': self.ban_list,
            'auto': {
                'artists': self._auto_suppressed_artists(),
                'genres': self._auto_suppressed_genres(),
            },
        }

    def get_algorithmic_recommendations(self, limit: int = 5) -> List[Dict]:
        """Algorithm-scored recommendations — an honest alternative to the
        hand-curated catalog. Builds a taste vector from the user's own rated
        rows, scores every candidate in CHALLENGE_DB by
        (0.45 * genre affinity) + (0.30 * artist affinity) + (0.25 * acclaim),
        ranks them, and returns the top NEW options. No hardcoded picks — this
        is pure content-based scoring over the candidate pool.

        Negative feedback is honored two ways:
          * genre pull is average-based and centered at 50, so a genre you rate
            mostly 1/100 scores below zero and demotes its candidates;
          * artists you've actively disliked (>= DISLIKE_ARTIST_MIN_COUNT songs
            averaging below DISLIKE_ARTIST_MAX_AVG) are penalized on top of that.
        """
        # 1) Taste vector from the user's rated rows (same genre scheme as
        #    _classify_row).
        genre_pull = self._genre_net_affinity()
        genre_sum = defaultdict(float)
        genre_cnt = defaultdict(int)
        for r in self.rated_entries:
            g = r.get('_genre') or 'Uncategorized'
            rating = int(r['rating'])
            genre_sum[g] += rating
            genre_cnt[g] += 1

        def g_label(g):
            """Human readable 'you rate X n/100' when we have data."""
            return genre_cnt[g] and int(round(genre_sum[g] / genre_cnt[g])) or None

        # 2) Artist affinity — avg + volume per known artist.
        artist_stats = self._artist_rating_stats()

        # 3) Score every candidate.
        scored = []
        for c in CHALLENGE_DB:
            artist = (c.get('artist') or '').strip()
            song = (c.get('song') or '').strip()
            if not artist or not song:
                continue
            if self.check_song_exists(artist, song).get('exists'):
                continue  # already in collection
            # Map the candidate to the user's genre scheme.
            raw_g = (c.get('genre') or '').strip()
            cand_class = GENRE_ALIAS_TO_CLASS.get(raw_g)
            if not cand_class:
                cand_class = self._classify_row({'title': f"{artist} – {song}"})
            if not cand_class:
                cand_class = 'Uncategorized'
            if self._is_banned(artist=artist, song=song, genre=cand_class):
                continue

            ga = genre_pull.get(cand_class, 0.0)                      # -1..1 genre pull
            s = artist_stats.get(artist)
            if s:
                aa = s['avg'] / 100.0
                if self._is_actively_disliked_artist(artist, artist_stats):
                    aa -= 0.35                                        # demote disliked artists
            else:
                aa = 0.5                                              # unknown artist, neutral
            q = (c.get('listen_score') or 60) / 100.0                # 0..1 acclaim
            score = 0.45 * ga + 0.30 * aa + 0.25 * q

            # Build a computed (not hand-written) reason from what dominated.
            parts = []
            avg_lbl = g_label(cand_class)
            if ga >= 0.35:
                parts.append(f"you rate {cand_class} {avg_lbl}/100 on average")
            elif ga >= 0.12:
                parts.append(f"leans toward your {cand_class} taste")
            elif ga <= -0.12:
                parts.append(f"{cand_class} averages {avg_lbl}/100 for you — usually a miss")
            if s and s['avg'] >= 75:
                parts.append(f"you've rated {artist} {int(round(s['avg']))}/100")
            elif self._is_actively_disliked_artist(artist, artist_stats):
                parts.append(f"you've rated {artist} {int(round(s['avg']))}/100 across {s['count']} songs")
            base = "; ".join(parts) if parts else f"fits your {cand_class} leanings"
            tier_label = (c.get('tier') or 'acclaimed').replace('_', ' ')
            acclaim_txt = tier_label.capitalize() + f" ({int(round(q * 100))}/100)"
            reason = f"{base} · {acclaim_txt} pick"

            scored.append({
                'artist': artist,
                'song': song,
                'genre': raw_g or cand_class,
                'class': cand_class,
                'score': round(score, 3),
                'reason': reason,
                'already_owned': False,
                'year': c.get('year'),
            })

        scored.sort(key=lambda x: x['score'], reverse=True)
        return scored[:limit]

    def get_reverse_me(self) -> Dict:
        """Generate recommendations for 'Reverse Me' — a theoretical listener
        who rates every song (100 - your_rating). Your favorites become their
        hates and vice versa, showing what the engine would recommend to
        someone with exactly opposite taste.
        """
        # Build inverted genre affinities
        genre_ratings_inv = defaultdict(list)
        for entry in self.rated_entries:
            g = entry.get('_genre') or entry.get('genre') or 'Uncategorized'
            rating = int(entry.get('rating') or 0)
            if rating:
                genre_ratings_inv[g].append(100 - rating)

        genre_aff_inv = {}
        for g, rs in genre_ratings_inv.items():
            genre_aff_inv[g] = sum(rs) / len(rs)

        # Build inverted artist averages
        artist_avg_inv = {}
        for artist, info in self.all_artists.items():
            ratings = info.get('ratings', []) or []
            if ratings:
                artist_avg_inv[artist] = sum(100 - r for r in ratings) / len(ratings)

        # Score challenge_db songs against the inverted profile
        scored = []
        self._build_song_index()
        owned = self.known_sigs
        max_aff = max(genre_aff_inv.values()) if genre_aff_inv else 1

        for c in CHALLENGE_DB:
            artist = c.get('artist', '')
            song = c.get('song', '')
            if not artist or not song:
                continue
            sig = self._normalize_sig(f"{artist} {song}")
            if sig in owned:
                continue
            if self.check_song_exists(artist, song).get('exists'):
                continue

            raw_g = (c.get('genre') or '').strip()
            cand_class = GENRE_ALIAS_TO_CLASS.get(raw_g)
            if not cand_class:
                cand_class = self._classify_row({'title': f"{artist} – {song}"})
            if not cand_class:
                cand_class = 'Uncategorized'
            if self._is_banned(artist=artist, song=song, genre=cand_class):
                continue

            ga = genre_aff_inv.get(cand_class, 0.0) / max_aff
            known = artist in artist_avg_inv
            aa = (artist_avg_inv[artist] / 100.0) if known else 0.5
            q = (c.get('listen_score') or 60) / 100.0
            score = 0.45 * ga + 0.30 * aa + 0.25 * q

            # Build a reason explaining the inverted logic
            parts = []
            avg_val = genre_aff_inv.get(cand_class, 0)
            avg_lbl = str(int(round(avg_val)))
            if ga >= 0.5:
                parts.append(f"you rate {cand_class} low ({avg_lbl}/100 inverted)")
            elif ga >= 0.25:
                parts.append(f"inverted: {cand_class} is a blind spot")
            if known and artist_avg_inv[artist] >= 75:
                parts.append(f"you'd rate {artist} ~{int(round(100 - artist_avg_inv[artist]))}/100")
            base = "; ".join(parts) if parts else f"opposite of your {cand_class} taste"
            tier_label = (c.get('tier') or 'acclaimed').replace('_', ' ')
            reason = f"{base} · {tier_label.capitalize()} pick"

            scored.append({
                'artist': artist,
                'song': song,
                'genre': raw_g or cand_class,
                'reason': reason,
                'score': round(score, 3),
                'year': c.get('year'),
            })

        scored.sort(key=lambda x: x['score'], reverse=True)
        top = scored[:20]

        # Find what the 'reverse you' would love most (your worst-rated genres)
        worst_genres = sorted(genre_aff_inv.items(), key=lambda x: -x[1])[:3]
        best_artists_inv = sorted(
            [(a, round(v, 1)) for a, v in artist_avg_inv.items() if v >= 70],
            key=lambda x: -x[1]
        )[:5]

        return {
            'description': 'A theoretical listener who rates every song (100 - your rating). Your favorites become their hates, and your least-liked genres become their favorites.',
            'picks': top,
            'inverted_profile': {
                'top_genres': [{'genre': g, 'inverted_avg': round(v, 1), 'your_avg': int(round(100 - v))} for g, v in worst_genres],
                'favorite_artists': [{'name': a, 'inverted_rating': v, 'your_avg': int(round(100 - v))} for a, v in best_artists_inv],
            },
            'stats': {
                'songs_rated': len(self.rated_entries),
                'avg_rating': round(sum(self.ratings) / len(self.ratings), 1) if self.ratings else 0,
                'reverse_avg': round(100 - (sum(self.ratings) / len(self.ratings)), 1) if self.ratings else 0,
            },
        }

    def get_weekly_discovery(self) -> Dict:
        """Generate a weekly discovery set — excludes songs already in your collection."""
        import random
        random.seed(datetime.now().strftime('%Y-W%W'))
        
        recs = self.get_recommendations()
        
        weekly_picks = []
        seen_songs = set()
        used_alternates = set()
        
        # Gather all recommendations across categories, skip owned ones
        for category, data in recs.items():
            for rec in data['recommendations']:
                key = rec['artist'] + ' - ' + rec['song']
                if key not in seen_songs and not rec.get('already_owned', False):
                    seen_songs.add(key)
                    weekly_picks.append({
                        'artist': rec['artist'],
                        'song': rec['song'],
                        'reason': rec['reason'],
                        'year': rec.get('year'),
                        'category': category,
                        'why_you': self._generate_why_reason(rec['artist'])
                    })
        
        # If we don't have enough fresh picks, grab alternates from what's left
        if len(weekly_picks) < 10:
            for category, data in recs.items():
                for rec in data['recommendations']:
                    key = rec['artist'] + ' - ' + rec['song']
                    if key not in seen_songs and key not in used_alternates:
                        used_alternates.add(key)
                        weekly_picks.append({
                            'artist': rec['artist'],
                            'song': rec['song'],
                            'reason': rec['reason'],
                            'year': rec.get('year'),
                            'category': category,
                            'why_you': self._generate_why_reason(rec['artist']),
                            'note': 'You have a similar song in your collection'
                        })
                        if len(weekly_picks) >= 10:
                            break
                if len(weekly_picks) >= 10:
                    break
        
        random.shuffle(weekly_picks)
        weekly = weekly_picks[:10]
        
        current_month = datetime.now().strftime('%Y-%m')
        recent = [r for r in self.rated_entries if r['date'].startswith(current_month)]
        recent_avg = round(sum(int(r['rating']) for r in recent) / len(recent), 1) if recent else 'N/A'
        
        return {
            'week_of': datetime.now().strftime('%Y-%m-%d'),
            'picks': weekly,
            'stats': {
                'total_songs_rated': len(self.ratings),
                'recent_avg': recent_avg,
                'unique_artists': len(self.all_artists),
            },
            'message': self._generate_weekly_message()
        }

    def _generate_why_reason(self, artist: str) -> str:
        """Generate a personalized reason why an artist might appeal."""
        if artist in self.all_artists:
            info = self.all_artists[self._artist_case(artist)]
            if info['ratings']:
                avg = round(sum(info['ratings'])/len(info['ratings']), 1)
                return f"You've rated {artist} {len(info['ratings'])} time(s) with an average of {avg}/100"
        
        # Check if similar
        for known_artist, info in self.all_artists.items():
            if len(info['ratings']) >= 2:
                avg = round(sum(info['ratings'])/len(info['ratings']), 1)
                if avg >= 85:
                    return f"Similar to {known_artist} (avg {avg}/100 in your ratings)"
        return ""

    # ------------------------------------------------------------------
    # Challenge section -- Critically acclaimed songs outside your zone
    # ------------------------------------------------------------------
    @staticmethod
    def _build_challenge_db():
        """Curated database of critically acclaimed songs.
        Imported from src.challenge_db.CHALLENGE_DB."""
        return CHALLENGE_DB

    def _load_popularity_cache(self) -> Dict:
        """Load cached Spotify popularity scores for challenge songs."""
        # __file__ is src/taste_engine.py, so ../data is the data dir
        cache_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'challenge_popularity.json')
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                return _json.load(f)
        except (FileNotFoundError, _json.JSONDecodeError, OSError):
            return {}

    def get_challenges(self, count: int = 20, mode: str = 'outside_zone',
                       popularity_threshold: int = 85) -> Dict:
        """Get a set of critically acclaimed songs outside your listening zone.
        Filters songs already in your collection, personalizes the challenge reason,
        ranks by how far outside your zone they are, and ensures all 4 tiers are represented.

        Args:
            count: Number of challenges to return (default 20)
            mode: 'outside_zone' (default, most outside first),
                  'opposite_taste' (prioritize genres you rate lowest),
                  'obscure' (songs most people don't know — low popularity), or
                  'artist_blind_spots' (acclaimed songs from genres where you dislike specific artists)
            popularity_threshold: Max popularity score (0-100) for obscure mode.
                                  Only songs at or below this threshold are shown.
                                  Default 50. Ignored for non-obscure modes.
        """
        db = self._build_challenge_db()
        pop_cache = self._load_popularity_cache()

        # Determine which genres you already love (have rated songs in)
        genre_dist = self._get_genre_distribution()
        loved_genres = set()
        for g, data in genre_dist.items():
            if data.get('count', 0) >= 2 and data.get('avg_rating', 0) >= 80:
                loved_genres.add(g)

        # Get genre rankings by your average rating (for opposite-taste mode)
        genre_by_rating = sorted(
            [(g, d['avg_rating']) for g, d in genre_dist.items() if d['count'] >= 2],
            key=lambda x: x[1]
        )
        lowest_rated_genres = {g for g, _ in genre_by_rating[:5]} if genre_by_rating else set()

        # Also check which artists are in collection
        known_artists = set(self.all_artists.keys())

        challenges = []
        for song in db:
            # Skip if song is already in collection
            dup = self.check_song_exists(song['artist'], song['song'])
            if dup['exists']:
                continue

            # Skip banned songs/artists/genres up front so an ignored song never
            # even reaches selection — otherwise it would occupy a dedup slot and
            # get stripped at the end, silently shortening the returned count.
            early_class = GENRE_ALIAS_TO_CLASS.get(song['genre'], song['genre'])
            if self._is_banned(
                artist=song['artist'],
                song=song['song'],
                genre=early_class,
            ):
                continue

            # Personalize: why is this outside your zone?
            artist_known = song['artist'] in known_artists
            genre_loved = song['genre'] in loved_genres
            genre_lowest = GENRE_ALIAS_TO_CLASS.get(song['genre'], song['genre']) in lowest_rated_genres

            if mode == 'opposite_taste' and genre_lowest:
                # Opposite-taste mode: prioritize genres you rate lowest
                # Map the challenge DB genre name to the classification genre name for display
                class_genre = GENRE_ALIAS_TO_CLASS.get(song['genre'], song['genre'])
                outside_score = 5
                zone_note = f"You rate most {class_genre} songs low, but this is widely acclaimed."
            elif not genre_loved and not artist_known:
                outside_score = 3  # Completely outside
                class_genre_tmp = GENRE_ALIAS_TO_CLASS.get(song['genre'], song['genre'])
                gcount = genre_dist.get(class_genre_tmp, {}).get('count', 0)
                if gcount == 0:
                    zone_note = f"No songs in '{song['genre']}' yet — you haven't explored this genre"
                elif class_genre_tmp != song['genre']:
                    # Genre maps to a broader classification bucket — show mapped name
                    zone_note = f"{gcount} songs classified as '{class_genre_tmp}' in your collection (challenge genre: '{song['genre']}')"
                elif gcount == 1:
                    zone_note = f"Only 1 song in '{song['genre']}' in your collection"
                else:
                    zone_note = f"Only {gcount} songs in '{song['genre']}' in your collection"
            elif not genre_loved and artist_known:
                outside_score = 2  # Artist known but genre unexplored
                info = self.all_artists.get(self._artist_case(song['artist']), {})
                avg = round(sum(info.get('ratings', []) or []) / max(len(info.get('ratings', []) or []), 1), 1) if info.get('ratings') else '?'
                zone_note = f"You know {song['artist']} (avg {avg}/100) but haven't explored {song['genre']}"
            else:
                outside_score = 1  # Within your zone
                zone_note = f"You already enjoy {song['genre']} -- this is a widely-loved classic you might've missed"

            # Bonus points for genres completely absent from your data
            # Use class_genre (mapped) for proper matching with classification genre names
            class_genre = GENRE_ALIAS_TO_CLASS.get(song['genre'], song['genre'])
            genre_total = genre_dist.get(class_genre, {}).get('count', 0)
            if genre_total == 0:
                outside_score += 1
                zone_note = f"Brand new genre: '{class_genre}' -- you haven't rated any songs in this genre!"

            challenges.append({
                **song,
                'already_owned': False,
                'outside_score': outside_score,
                'zone_note': zone_note,
                'class_genre': class_genre,
            })
        # Sort by mode
        _pop_min, _pop_max = 0, 100  # defaults for non-obscure modes
        if mode == 'obscure':
            # Obscure mode: sort by popularity ASCENDING (least mainstream first)
            # Uses cached Spotify popularity scores when available.
            tier_obscurity = {'cult': 0, 'classic': 1, 'modern_classic': 2, 'legendary': 3}
            for c in challenges:
                pop_key = f"{c['artist']}|{c['song']}"
                cached = pop_cache.get(pop_key, {})
                # Prefer Spotify popularity, fall back to listen_score estimate
                pop = cached.get('popularity', 0)
                if pop == 0:
                    pop = c.get('listen_score', 50)
                c['popularity'] = pop
                tier_rank = tier_obscurity.get(c.get('tier', ''), 2)
                if pop <= 40:
                    c['zone_note'] = f"Deeply obscure — popularity {pop}/100. Most people have never heard this."
                elif pop <= 60:
                    c['zone_note'] = f"Hidden gem — popularity {pop}/100. Critically acclaimed but rarely mainstream."
                elif pop <= 80:
                    c['zone_note'] = f"Less mainstream than you'd think — popularity {pop}/100."
                else:
                    c['zone_note'] = f"Acclaimed classic — popularity {pop}/100. Might've slipped past you."
                c['_obscurity_rank'] = tier_rank * 10 + (100 - pop)
            # Track popularity range before filtering (for frontend hint)
            all_pops = [c.get('popularity', 50) for c in challenges]
            _pop_min = min(all_pops) if all_pops else 0
            _pop_max = max(all_pops) if all_pops else 100
            # Filter: only keep songs at or below the popularity threshold
            challenges = [c for c in challenges if c.get('popularity', 100) <= popularity_threshold]
            challenges.sort(key=lambda x: x.get('_obscurity_rank', 999))
        elif mode == 'opposite_taste':
            # In opposite-taste mode, sort by: opposite-taste first, then tier prestige, then listen_score
            # Note: use class_genre (mapped) for proper genre matching with classification system
            tier_order = {'legendary': 0, 'modern_classic': 1, 'classic': 2, 'cult': 3}
            challenges.sort(key=lambda x: (
                -x['outside_score'] if x.get('class_genre', x['genre']) in lowest_rated_genres else x['outside_score'],
                tier_order.get(x.get('tier', ''), 4),
                -x.get('listen_score', 0)
            ))
        elif mode == 'artist_blind_spots':
            # Artist Blind Spots: find artists you rated low, then suggest acclaimed
            # songs in the SAME genre from DIFFERENT artists you haven't tried.
            # "You dislike LMFAO (Pop, avg 27), but here's an acclaimed Pop song
            #  from an artist you haven't explored."
            low_artists = []
            for artist_name, artist_data in self.all_artists.items():
                ratings = artist_data.get('ratings', []) or []
                if len(ratings) >= 2:
                    avg = sum(ratings) / len(ratings)
                    if avg < 75:  # Artist you rate below average
                        low_artists.append((artist_name, avg, len(ratings),
                                            artist_data.get('genre', 'Uncategorized')))
            low_artists.sort(key=lambda x: x[1])  # Worst first

            # Build a map: mapped_genre -> list of (disliked_artist, their_avg, raw_genre)
            # Use GENRE_ALIAS_TO_CLASS to normalize both artist and challenge genres
            genre_to_disliked = {}
            for artist_name, avg, cnt, genre in low_artists:
                mapped = GENRE_ALIAS_TO_CLASS.get(genre, genre)
                genre_to_disliked.setdefault(mapped, []).append((artist_name, avg, cnt, genre))

            # Now re-score challenge songs based on artist blind spots
            for c in challenges:
                song_genre = c.get('genre', '')
                song_artist = c.get('artist', '')
                # Map the challenge song genre too
                song_mapped = GENRE_ALIAS_TO_CLASS.get(song_genre, song_genre)
                # Check if this song's genre has artists you dislike (via mapped genre)
                if song_mapped in genre_to_disliked:
                    disliked = genre_to_disliked[song_mapped]
                    # This song is by a DIFFERENT artist in a genre where you dislike some artists
                    # Boost score based on how many disliked artists in this genre
                    artist_avg = self.all_artists.get(self._artist_case(song_artist), {}).get('ratings', [])
                    if artist_avg:
                        a_avg = sum(artist_avg) / len(artist_avg)
                    else:
                        a_avg = None  # Unknown to user — good candidate

                    if a_avg is None:
                        # Artist you haven't tried — high blind spot score
                        c['outside_score'] = 5
                        worst = disliked[0]
                        c['zone_note'] = (
                            f"You rate {worst[0]} low ({worst[1]:.0f}/100) in {song_mapped} — "
                            f"try this acclaimed {song_mapped} artist you haven't explored")
                    elif a_avg < 75:
                        # Another artist you also rate low — lower priority
                        c['outside_score'] = 3
                        c['zone_note'] = (
                            f"Another {song_mapped} artist you rate {a_avg:.0f}/100 — "
                            f"but this is their most acclaimed song")
                    else:
                        # Artist you actually like in this genre — skip
                        c['outside_score'] = 0
                else:
                    c['outside_score'] = 0  # Genre not relevant to blind spots

            # Filter out zero-score and already-owned
            challenges = [c for c in challenges if c['outside_score'] > 0]
            # Sort by: score desc, then listen_score desc (most acclaimed first)
            challenges.sort(key=lambda x: (-x['outside_score'], -x.get('listen_score', 0)))
        else:
            # Default: highest outside score first, then listen_score
            challenges.sort(key=lambda x: (-x['outside_score'], -x.get('listen_score', 0)))

        # Tier-guaranteeing dedup: first ensure every tier has at least 1 entry,
        # then fill the rest by score. This prevents any tier from being invisible.
        deduped = []
        seen_artists = set()
        seen_genres = set()
        tiers_needed = {'legendary', 'modern_classic', 'classic', 'cult'}

        # Phase 1: pick 1 song from each tier that has unowned songs
        for tier_name in ['legendary', 'modern_classic', 'classic', 'cult']:
            tier_candidates = [c for c in challenges if c.get('tier') == tier_name and c['artist'] not in seen_artists]
            if tier_candidates:
                best = tier_candidates[0]
                deduped.append(best)
                seen_artists.add(best['artist'])
                seen_genres.add(best['genre'])

        # Phase 2: fill remaining slots by score (highest outside_score first)
        for c in challenges:
            if len(deduped) >= count:
                break
            if c not in deduped and c['artist'] not in seen_artists:
                deduped.append(c)
                seen_artists.add(c['artist'])
                seen_genres.add(c['genre'])

        # Phase 3: if still under count, allow same-artist repeats
        if len(deduped) < count:
            for c in challenges:
                if len(deduped) >= count:
                    break
                if c not in deduped:
                    deduped.append(c)

        # Group by tier for frontend rendering
        by_tier = {}
        for c in deduped:
            tier = c.get('tier', 'cult')
            if tier not in by_tier:
                by_tier[tier] = []
            by_tier[tier].append(c)

        # Filter out banned genres/artists/songs from challenges
        deduped = [
            c for c in deduped
            if not self._is_banned(
                artist=c.get('artist', ''),
                song=c.get('song', ''),
                genre=GENRE_ALIAS_TO_CLASS.get(c.get('genre', ''), c.get('genre', '')),
            )
        ]

        # Clean up internal fields
        for c in deduped:
            c.pop('_obscurity_rank', None)

        result = {
            'challenges': deduped,
            'by_tier': by_tier,
            'total_available': len([c for c in challenges if not c['already_owned']]),
            'total_db_size': len(db),
            'mode': mode,
            'your_zones': {
                'loved_genres': sorted(loved_genres),
                'lowest_rated_genres': sorted(lowest_rated_genres),
                'known_artists_count': len(known_artists),
            }
        }
        # Include popularity range for obscure mode so frontend can hint
        if mode == 'obscure':
            result['popularity_min'] = _pop_min
            result['popularity_max'] = _pop_max
            result['popularity_threshold'] = popularity_threshold
        return result

    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Genre reclassification — artist propagation, Wikidata, MusicBrainz
    # ------------------------------------------------------------------

    _TITLE_GENRE_SIGNALS = {
        'Classical/Instrumental': ['violin', 'piano', 'symphony', 'orchestra', 'cello', 'sonata',
                                    'concerto', 'nocturne', 'waltz', 'harp', 'flute', 'instrumental'],
        'Rock': ['guitar', 'rock', 'anthem', 'rebel', 'thunder', 'lightning', 'fire'],
        'Electronic/Dance': ['dance', 'techno', 'beat', 'rhythm', 'club', 'bass', 'drop', 'remix'],
        'Pop': ['love', 'heart', 'baby', 'dream', 'star', 'light', 'sun', 'moon', 'beautiful', 'forever'],
        'Jazz/Swing': ['jazz', 'swing', 'blues', 'bossa', 'ragtime'],
        'Disco/Funk': ['disco', 'funk', 'groove', 'boogie', 'fever'],
        'Christmas/Holiday': ['christmas', 'santa', 'jingle', 'snow', 'winter', 'holiday', 'noel'],
        'Metal': ['metal', 'steel', 'iron', 'dark', 'night', 'soul', 'hell', 'satan', 'demon', 'war', 'blood'],
    }

    # Class-level alias so tests can still access engine._genre_alias_to_class
    _genre_alias_to_class = GENRE_ALIAS_TO_CLASS

    @staticmethod
    def _lookup_artist_genre_musicbrainz(artist_name: str) -> list:
        """Look up an artist's genres via the MusicBrainz public API (free, no auth).
        Returns a list of genre tags, or empty list on failure.
        """
        import urllib.request
        import json as _json
        
        try:
            query = urllib.parse.quote(artist_name)
            url = f'https://musicbrainz.org/ws/2/artist/?query=artist:{query}&fmt=json&limit=1'
            req = urllib.request.Request(url, headers={
                'User-Agent': 'TasteScope/1.0 (music-analyzer)',
                'Accept': 'application/json'
            })
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = _json.loads(resp.read().decode('utf-8'))
                artists = data.get('artists', [])
                if artists:
                    tags = artists[0].get('tags', [])
                    return [t['name'] for t in tags]
        except Exception:
            pass
        return []

    def _classify_artist_genre_musicbrainz(self, artist_name: str) -> str:
        """Use MusicBrainz to classify a single artist into one of our genres.
        Maps MusicBrainz tags to our genre taxonomy.
        """
        tags = self._lookup_artist_genre_musicbrainz(artist_name)
        if not tags:
            return 'Uncategorized'
        
        tag_to_genre = self._build_tag_to_genre_map()
        
        scores = defaultdict(int)
        for tag in tags:
            t = tag.lower().strip()
            if t in tag_to_genre:
                scores[tag_to_genre[t]] += 3
            for genre, keywords in self.genre_keywords.items():
                for kw in keywords:
                    if kw in t or t in kw:
                        scores[genre] += 1
                        break
        
        if scores:
            return max(scores, key=scores.get)
        return 'Uncategorized'

    def _build_tag_to_genre_map(self) -> Dict[str, str]:
        """Build reverse mapping from keyword → genre."""
        tag_to_genre = {}
        for genre, keywords in self.genre_keywords.items():
            for kw in keywords:
                tag_to_genre[kw] = genre
        return tag_to_genre

    def _classify_artist_tags(self, tags: list) -> str:
        """Given a list of tag strings, return the best-matching genre."""
        if not tags:
            return 'Uncategorized'
        tag_to_genre = self._build_tag_to_genre_map()
        scores = defaultdict(int)
        for tag in tags:
            t = tag.lower().strip()
            if t in tag_to_genre:
                scores[tag_to_genre[t]] += 3
            for genre, keywords in self.genre_keywords.items():
                for kw in keywords:
                    if kw in t or t in kw:
                        scores[genre] += 1
                        break
        if scores:
            return max(scores, key=scores.get)
        return 'Uncategorized'

    @staticmethod
    def _lookup_artist_genre_wikidata_batch(artist_names: list) -> Dict[str, str]:
        """Batch-lookup artist genres via Wikidata SPARQL — 1 HTTP request for up to ~500 artists.
        Returns {artist_name: genre} mapping for matches found.
        """
        import urllib.request
        import json as _json
        
        if not artist_names:
            return {}
        
        # Deduplicate and filter short names (likely parsing artifacts)
        clean = sorted(set(
            n.strip() for n in artist_names
            if len(n.strip()) > 2 and n.strip().lower() not in ('announcement', 'test', 'artist')
        ))
        
        # SPARQL query: find artists by label, get their genre
        # Use a VALUES block for batch lookup
        values_block = ' '.join(f'"{n.replace(chr(34), "").replace(chr(10), "")}"@en' for n in clean[:200])
        
        sparql_query = f"""
        SELECT ?artistLabel ?genreLabel WHERE {{
          VALUES ?artistLabel {{ {values_block} }}
          {{ ?artist wdt:P31 wd:Q5 }} UNION {{ ?artist wdt:P31 wd:Q215380 }}
          ?artist rdfs:label ?artistLabel .
          ?artist wdt:P136 ?genre .
          ?genre rdfs:label ?genreLabel .
          FILTER(LANG(?genreLabel) = "en")
        }}
        LIMIT 500
        """.strip()
        
        url = 'https://query.wikidata.org/sparql?format=json&query=' + urllib.parse.quote(sparql_query)
        req = urllib.request.Request(url, headers={
            'User-Agent': 'TasteScope/1.0 (music-analyzer)',
            'Accept': 'application/json'
        })
        
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = _json.loads(resp.read().decode('utf-8'))
                results = {}
                for item in data.get('results', {}).get('bindings', []):
                    artist = item.get('artistLabel', {}).get('value', '')
                    genre = item.get('genreLabel', {}).get('value', '')
                    if artist and genre:
                        # Keep the first genre found per artist
                        if artist not in results:
                            results[artist] = genre
                return results
        except Exception:
            pass
        return {}

    def _propagate_artist_genres(self) -> Dict[str, str]:
        """Build artist→genre mapping by propagating keyword-classified genres.
        If ANY song by an artist matched a keyword genre, ALL songs by that
        artist inherit that genre. This is musically valid — artists generally
        make one primary genre.
        
        Also applies title-based heuristics for remaining artists.
        """
        # Step 1: Keyword classification — which artists have classified songs?
        artist_song_genres = defaultdict(lambda: defaultdict(int))
        
        for r in self.rows:
            combined = ((r.get('tail') or '') + ' ' + (r.get('title') or '')).lower()
            artists = self._extract_artists_from_row(r)
            if not artists:
                continue
                
            matched_genre = None
            for genre, keywords in self.genre_keywords.items():
                for kw in keywords:
                    if self._kw_in_text(kw, combined):
                        matched_genre = genre
                        break
                if matched_genre:
                    break
            
            # If keyword didn't match, try title-based heuristics
            if not matched_genre:
                title_lower = (r.get('title') or '').lower()
                for genre, signals in self._TITLE_GENRE_SIGNALS.items():
                    for signal in signals:
                        if signal in title_lower:
                            matched_genre = genre
                            break
                    if matched_genre:
                        break
            
            if matched_genre:
                for artist in artists:
                    artist_song_genres[artist][matched_genre] += 1
        
        # Step 2: For each artist, pick the dominant genre from their classified songs
        artist_genre = {}
        for artist, genre_counts in artist_song_genres.items():
            if genre_counts:
                dominant = max(genre_counts, key=genre_counts.get)
                artist_genre[artist] = dominant
        
        return artist_genre

    def _title_heuristic_classify(self, title: str) -> str:
        """Classify a single song by its title alone using heuristic signals."""
        if not title or not isinstance(title, str):
            return "Uncategorized"
        t = title.lower()
        for genre, signals in self._TITLE_GENRE_SIGNALS.items():
            for signal in signals:
                if signal in t:
                    return genre
        return 'Uncategorized'

    def reclassify_genres(self, use_musicbrainz: bool = False, use_wikidata: bool = True) -> Dict:
        """Re-run genre classification with multiple strategies.
        Returns before/after stats for the genre distribution.
        
        Strategies, in order:
          1. Keyword matching (review text + title)
          2. Title-based heuristics (genre signals in song titles)
          3. Artist-level propagation (if one song by artist = genre, all do)
          4. Wikidata SPARQL batch lookup (fast, no auth, 1 request)
          5. MusicBrainz sequential lookup (slow, rate-limited — only if use_musicbrainz=True)
        """
        # Get old distribution
        old_dist = self._get_genre_distribution()
        old_uncat = old_dist.get('Uncategorized', {}).get('count', 0)
        
        # Force re-initialize keywords
        self._init_genre_keywords()
        
        # --- Strategy 1: Keyword matching + title heuristics → artist propagation ---
        propagated = self._propagate_artist_genres()
        for artist, genre in propagated.items():
            self._cache_artist_genre(artist, genre)   # guarded: skips song titles
        # --- Strategy 2: Curated artist-genre mapping (manually verified) ---
        # Human-curated genres are authoritative and OVERRIDE the propagation
        # vote: a song title containing "dance" or "theme" is not evidence of
        # the artist's genre (e.g. Lindsey Stirling's Christmas album would
        # otherwise label her Christmas/Holiday).
        curated_applied = 0
        for artist, genre in CURATED_ARTIST_GENRES.items():
            if self._artist_genre_cache.get(artist) != genre:
                self._cache_artist_genre(artist, genre)
                curated_applied += 1

        # Re-classify rows with the updated cache so _get_genre_distribution()
        # reflects the new artist→genre mappings
        self._classify_rows()

        new_dist = self._get_genre_distribution()
        new_uncat = new_dist.get('Uncategorized', {}).get('count', 0)
        
        # --- Strategy 3: Wikidata batch lookup for remaining uncategorized artists ---
        wikidata_stats = {'looked_up': 0, 'found': 0, 'reclassified': 0}
        if use_wikidata:
            # Find uncategorized artists (not in cache)
            uncategorized_artists = set()
            for r in self.rows:
                combined = (r.get('tail') or '') + ' ' + (r.get('title') or '')
                t = combined.lower()
                # Check if this song is currently uncategorized
                matched = False
                for genre, keywords in self.genre_keywords.items():
                    for kw in keywords:
                        if kw in t:
                            matched = True
                            break
                    if matched:
                        break
                if not matched:
                    # Also check title heuristics
                    if self._title_heuristic_classify(r.get('title') or '') == 'Uncategorized':
                        artists = self._extract_artists_from_row(r)
                        for a in artists:
                            if a and a not in self._artist_genre_cache and len(a) > 2:
                                uncategorized_artists.add(a)
            
            if uncategorized_artists:
                wikidata_stats['looked_up'] = len(uncategorized_artists)
                wikidata_results = self._lookup_artist_genre_wikidata_batch(list(uncategorized_artists))
                
                # Map Wikidata genres to our taxonomy
                tag_to_genre = self._build_tag_to_genre_map()
                for artist, wikidata_genre in wikidata_results.items():
                    mapped = self._classify_artist_tags([wikidata_genre])
                    if mapped != 'Uncategorized' and artist not in self._artist_genre_cache:
                        if self._cache_artist_genre(artist, mapped):
                            wikidata_stats['found'] += 1
                
                # Count how many songs were reclassified
                for r in self.rows:
                    if not (r.get('tail') or '').lower() or not (r.get('title') or ''):
                        continue
                    combined = ((r.get('tail') or '') + ' ' + (r.get('title') or '')).lower()
                    matched = False
                    for genre, keywords in self.genre_keywords.items():
                        for kw in keywords:
                            if self._kw_in_text(kw, combined):
                                matched = True
                                break
                        if matched:
                            break
                    if not matched:
                        artists = self._extract_artists_from_row(r)
                        for a in artists:
                            if a in wikidata_results:
                                wikidata_stats['reclassified'] += 1
                                break
            
            # Reclassify rows with updated Wikidata cache, then recalculate
            self._classify_rows()
            new_dist = self._get_genre_distribution()
            new_uncat = new_dist.get('Uncategorized', {}).get('count', 0)
        
        # --- Strategy 4: MusicBrainz (slow, sequential) ---
        mb_stats = {'looked_up': 0, 'found': 0, 'reclassified': 0}
        if use_musicbrainz:
            artist_uncat = defaultdict(int)
            for r in self.rows:
                combined = (r.get('tail') or '') + ' ' + (r.get('title') or '')
                t = combined.lower()
                matched = False
                for genre, keywords in self.genre_keywords.items():
                    for kw in keywords:
                        if kw in t:
                            matched = True
                            break
                    if matched:
                        break
                if not matched and self._title_heuristic_classify(r.get('title') or '') == 'Uncategorized':
                    artists = self._extract_artists_from_row(r)
                    for a in artists:
                        if a and a not in self._artist_genre_cache:
                            artist_uncat[a] += 1
            
            sorted_artists = sorted(artist_uncat.items(), key=lambda x: -x[1])[:200]
            for artist_name, cnt in sorted_artists:
                mb_stats['looked_up'] += 1
                genre = self._classify_artist_genre_musicbrainz(artist_name)
                if genre != 'Uncategorized':
                    if self._cache_artist_genre(artist_name, genre):
                        mb_stats['found'] += 1
                        mb_stats['reclassified'] += cnt
            
            # Reclassify rows with updated MusicBrainz cache, then recalculate
            self._classify_rows()
            new_dist = self._get_genre_distribution()
            new_uncat = new_dist.get('Uncategorized', {}).get('count', 0)
        
        # Rebuild artist index so constellation reflects new genres
        self._build_artist_index()
        
        # Save cache to disk for persistence
        self._save_genre_cache()
        
        # Build a summary
        classified = []
        for genre, data in sorted(new_dist.items(), key=lambda x: -x[1]['count']):
            if genre != 'Uncategorized':
                old_count = old_dist.get(genre, {}).get('count', 0)
                classified.append({
                    'genre': genre,
                    'before': old_count,
                    'after': data['count'],
                    'change': data['count'] - old_count,
                })
        
        return {
            'before_uncategorized': old_uncat,
            'after_uncategorized': new_uncat,
            'reduction': old_uncat - new_uncat,
            'categories': len([g for g in new_dist if g != 'Uncategorized']),
            'by_genre': classified,
            'propagation_count': len(propagated),
            'curated_applied': curated_applied,
            'wikidata': wikidata_stats if use_wikidata else None,
            'musicbrainz': mb_stats if use_musicbrainz else None,
        }

    def _save_genre_cache(self, path: str = "data/artist_genre_cache.json"):
        """Persist artist→genre cache to disk so we don't re-fetch every time."""
        import json as _json
        try:
            with open(path, 'w', encoding='utf-8') as f:
                _json.dump(self._artist_genre_cache, f, indent=2)
        except Exception:
            pass

    def _load_genre_cache(self, path: str = "data/artist_genre_cache.json"):
        """Load persisted artist→genre cache from disk."""
        import json as _json2
        try:
            with open(path, 'r', encoding='utf-8') as f:
                cached = _json2.load(f)
                if isinstance(cached, dict):
                    self._artist_genre_cache.update(cached)
        except (FileNotFoundError, _json2.JSONDecodeError):
            pass
        # Build the folded lookup index so cache hits ignore case and
        # hyphen/space variants ('yu-peng chen' → 'Yu-Peng Chen').
        self._rebuild_genre_cache_folded()

    def _rebuild_genre_cache_folded(self):
        """Fold _artist_genre_cache into one genre per artist identity.

        Historical enrichment cached genres under every case-variant spelling
        of an artist, often with contradictory keyword-noise values
        ('Guns N’ Roses': 'J-Pop/Anime' vs "Guns N' Roses": 'Rock'). Since a
        folded lookup must return ONE genre, conflicts resolve by:
          1. A value agreeing with the curated mapping (authoritative)
          2. The value of the variant with the most rated songs
          3. Majority vote, ties → alphabetical (deterministic)
        """
        groups: Dict[str, Dict[str, str]] = defaultdict(dict)
        for k, g in self._artist_genre_cache.items():
            fold_key = self._fold_artist_key(k)
            if fold_key:
                groups[fold_key][k] = g

        def rating_count(raw_key: str) -> int:
            canon = self._artist_case(raw_key)
            info = self.all_artists.get(canon)
            return len(info.get('ratings', [])) if info else 0

        resolved: Dict[str, str] = {}
        for fold_key, variants in groups.items():
            values = set(variants.values())
            if len(values) == 1:
                resolved[fold_key] = next(iter(values))
                continue
            # 1. Curated agreement wins
            curated = None
            for raw in variants:
                curated = self._curated_genre_for(raw)
                if curated is not None:
                    break
            if curated is not None and curated in values:
                resolved[fold_key] = curated
                continue
            # 2. Variant with the most rated songs (needs the artist index;
            # unavailable during __init__ — the post-index rebuild covers it)
            if getattr(self, 'all_artists', None):
                best = max(variants, key=lambda raw: (
                    rating_count(raw), raw,
                ))
                if rating_count(best) > 0:
                    resolved[fold_key] = variants[best]
                    continue
            # 3. Majority vote, ties → alphabetical
            counts: Dict[str, int] = defaultdict(int)
            for g in variants.values():
                counts[g] += 1
            resolved[fold_key] = sorted(
                counts.items(), key=lambda kv: (-kv[1], kv[0]),
            )[0][0]

        self._genre_cache_folded = resolved

    def _generate_weekly_message(self) -> str:
        """Generate a warm, personalized weekly message with musical insight."""
        genre_dist = self._get_genre_distribution()
        recent_month = datetime.now().strftime('%Y-%m')
        recent_count = len([r for r in self.rated_entries if r['date'].startswith(recent_month)])
        total = len(self.ratings)
        genre_by_avg = sorted(
            [(g, d['avg_rating']) for g, d in genre_dist.items() if d['count'] >= 2],
            key=lambda x: -x[1]
        )
        top_loved = genre_by_avg[0] if genre_by_avg else ('Unknown', 0)
        evolution_data = self.get_evolution()
        monthly_avgs = list(evolution_data.get('monthly_avg', {}).values())
        trend = 'rising' if len(monthly_avgs) >= 2 and monthly_avgs[-1] > monthly_avgs[-2] else 'steady'
        if len(monthly_avgs) >= 2 and monthly_avgs[-1] < monthly_avgs[-2] - 2:
            trend = 'exploring'

        if total > 2000:
            msgs = [
                f"You've rated {total} songs, highest genre is {top_loved[0]} ({top_loved[1]}/100). Taste has been {trend}. This month: {recent_count} songs. Fresh picks for your {datetime.now().strftime('%B')} playlist.",
                f"{total} songs deep! Your {top_loved[0]} ear is sharp at {top_loved[1]}/100. Picks lean {trend} this week.",
                f"Musical fingerprint: {top_loved[0]} ({top_loved[1]}/100), {len(genre_dist)} genres. Trend: {trend}.",
            ]
        elif total > 500:
            msgs = [
                f"{total} songs rated! Your {top_loved[0]} affinity ({top_loved[1]}/100) is becoming a signature. Time to explore deeper.",
                f"With {total} songs, your {top_loved[0]} taste ({top_loved[1]}/100) stands out. Next obsession awaits.",
            ]
        else:
            msgs = [
                f"{total} songs rated. Early signs: {top_loved[0]} affinity ({top_loved[1]}/100). Keep exploring!",
                f"Building your taste profile: {total} songs, {top_loved[0]} leading at {top_loved[1]}/100.",
            ]

        import random
        return random.choice(msgs)
    @staticmethod
    def _extract_letter_grade(text: str) -> tuple:
        """Extract letter grade from review text.
        Returns (grade_str, value) tuple, e.g. ('A', 95)."""
        return extract_letter_grade(text)

    @staticmethod
    def _infer_tone_rating(text: str):
        """Infer numeric rating from tone of review text.
        Delegates to backfill.infer_tone_rating."""
        return infer_tone_rating(text)


    def backfill_ratings(self, preview: bool = False, method: str = 'all'):
        """Backfill missing ratings by extracting letter grades and inferring from tone.

        Args:
            preview: If True, return stats without modifying CSV
            method: 'all', 'letter', or 'tone'

        Returns dict with before/after stats and list of changes.
        """
        before_rated = len(self.rated_entries)
        before_avg = round(sum(self.ratings) / len(self.ratings), 1) if self.ratings else 0

        changes = []
        letter_count = 0
        tone_count = 0
        already_rated = 0
        no_match = 0

        for i, r in enumerate(self.rows):
            if r.get('rating'):
                already_rated += 1
                continue

            tail_text = r.get('tail') or ''
            full_text = tail_text + ' ' + (r.get('title') or '')
            new_rating = None
            source = None
            grade_str = None

            # Try letter grade extraction (review text only — titles can have
            # single letters like "Artist A" that falsely match grades)
            if method in ('all', 'letter'):
                g, v = self._extract_letter_grade(tail_text)
                if v is not None:
                    new_rating = v
                    source = 'letter'
                    grade_str = g
                    letter_count += 1

            # Fall back to tone inference (full text — tone words are less ambiguous)
            if new_rating is None and method in ('all', 'tone'):
                tag, v = self._infer_tone_rating(full_text)
                if v is not None:
                    new_rating = v
                    source = f'tone:{tag}' if tag else 'tone'
                    tone_count += 1

            if new_rating is None:
                no_match += 1
                continue

            changes.append({
                'index': i,
                'title': (r.get('title') or '')[:80],
                'old_rating': None,
                'new_rating': new_rating,
                'source': source,
                'grade_str': grade_str,
                'preview': (r.get('tail') or '')[:100].replace('\n', ' ')
            })

            # Apply to CSV if not preview
            if not preview:
                r['rating'] = str(new_rating)

        # Write back to file
        if not preview and changes:
            # Strip internal fields (_genre, etc.) before writing to CSV
            clean_rows = [{k: v for k, v in row.items() if not k.startswith('_')}
                          for row in self.rows]
            # Preserve every column the data actually has (artist/song/... were
            # added by the RYM import; a hardcoded 4-column list would crash or
            # silently drop them).
            fieldnames: List[str] = []
            for row in clean_rows:
                for k in row:
                    if k not in fieldnames:
                        fieldnames.append(k)
            with open(self.csv_path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(clean_rows)

            # Reload engine state
            self._load_data()
            self._classify_rows()  # re-classify with fresh genre cache
            self._build_artist_index()
            self._build_song_index()

        after_rated = len(self.rated_entries) if not preview else before_rated + len(changes)
        after_avg = 0
        if not preview and self.ratings:
            after_avg = round(sum(self.ratings) / len(self.ratings), 1)
        elif preview:
            all_ratings = list(self.ratings) + [c['new_rating'] for c in changes]
            after_avg = round(sum(all_ratings) / len(all_ratings), 1) if all_ratings else 0

        return {
            'preview': preview,
            'before': {'rated': before_rated, 'avg_rating': before_avg, 'total': len(self.rows)},
            'after': {'rated': after_rated, 'avg_rating': after_avg, 'total': len(self.rows)},
            'changes_by_source': {
                'letter_grades': letter_count,
                'tone_inference': tone_count,
                'already_rated': already_rated,
                'no_match': no_match
            },
            'total_changes': len(changes),
            'changes': changes[:50] if preview else []  # Only return full list in preview mode
        }

    # ------------------------------------------------------------------
    # Taste Fingerprint — algorithmic taste prediction
    # ------------------------------------------------------------------

    def get_taste_fingerprint(self) -> Dict:
        """Build a taste fingerprint from your top-rated songs.
        
        Returns a weighted genre vector, weighted year vector, predictability
        score, and a fit scorer for candidate songs.
        
        The fingerprint is computed ONLY from songs rated >= 75 (C or better),
        weighted by how much above 75 each rating is. This captures your
        active preferences rather than everything you've heard.
        """
        import math
        
        # Only consider songs rated 75+ (your positive preferences)
        positive_songs = [r for r in self.rated_entries 
                         if int(r.get('rating', 0)) >= 75]
        
        if not positive_songs:
            return {
                'genre_fingerprint': {},
                'year_fingerprint': {},
                'predictability': {'overall': 0, 'genre_entropy': 0, 'year_entropy': 0},
                'top_influences': [],
                'taste_summary': 'Not enough rated songs (need 75+ rated).',
            }
        
        # ---- 1. Genre Fingerprint (rating-weighted) ----
        genre_ratings = defaultdict(list)  # genre → [ratings]
        genre_song_count = defaultdict(int)
        
        for r in positive_songs:
            genre = r.get('_genre', 'Uncategorized')
            rating = int(r['rating'])
            # Weight = rating - 74 (so 75=1, 100=26). Songs rated exactly 75
            # contribute minimally; 100-rated songs contribute maximally.
            genre_ratings[genre].append(rating)
            genre_song_count[genre] += 1
        
        # Compute weighted genre distribution
        total_weight = sum(sum(rs) for rs in genre_ratings.values())
        genre_fingerprint = {}
        for genre, ratings in sorted(genre_ratings.items(), 
                                      key=lambda x: -sum(x[1])):
            avg = sum(ratings) / len(ratings)
            weight = sum(ratings) / total_weight if total_weight else 0
            genre_fingerprint[genre] = {
                'weight': round(weight, 4),
                'avg_rating': round(avg, 1),
                'song_count': genre_song_count[genre],
                'total_weight': round(sum(ratings), 1),
            }
        
        # ---- 2. Year/Decade Fingerprint (rating-weighted) ----
        decade_ratings = defaultdict(list)  # decade → [ratings]
        year_ratings = defaultdict(list)    # year → [ratings]
        
        for r in positive_songs:
            yr = self._release_year_for(r.get('title', ''))
            rating = int(r['rating'])
            if yr:
                decade = (yr // 10) * 10
                decade_ratings[decade].append(rating)
                year_ratings[yr].append(rating)
        
        total_year_weight = sum(sum(rs) for rs in decade_ratings.values())
        year_fingerprint = {}
        for decade, ratings in sorted(decade_ratings.items()):
            avg = sum(ratings) / len(ratings)
            weight = sum(ratings) / total_year_weight if total_year_weight else 0
            year_fingerprint[str(decade) + 's'] = {
                'weight': round(weight, 4),
                'avg_rating': round(avg, 1),
                'song_count': len(ratings),
            }
        
        # ---- 3. Predictability Score (entropy-based) ----
        # Low entropy = taste is concentrated = predictable
        # High entropy = taste is diverse = hard to predict
        def entropy(weights):
            """Shannon entropy of a probability distribution."""
            probs = [w for w in weights if w > 0]
            if not probs:
                return 0
            return -sum(p * math.log2(p) for p in probs)
        
        genre_weights = [f['weight'] for f in genre_fingerprint.values()]
        year_weights = [f['weight'] for f in year_fingerprint.values()]
        
        genre_entropy = entropy(genre_weights)
        year_entropy = entropy(year_weights)
        
        # Max possible entropy (uniform distribution)
        n_genres = len(genre_weights)
        n_decades = len(year_weights)
        max_genre_entropy = math.log2(n_genres) if n_genres > 1 else 1
        max_year_entropy = math.log2(n_decades) if n_decades > 1 else 1
        
        # Normalize to 0-100 (100 = perfectly predictable, 0 = maximum randomness)
        genre_predictability = round(100 * (1 - genre_entropy / max_genre_entropy), 1) if max_genre_entropy else 50
        year_predictability = round(100 * (1 - year_entropy / max_year_entropy), 1) if max_year_entropy else 50
        overall_predictability = round((genre_predictability * 0.6 + year_predictability * 0.4), 1)
        
        # ---- 3b. Selectivity Score (how picky within each genre) ----
        # High std dev within a genre = selective (love some, dislike others)
        # Low std dev = generous (rate everything similarly)
        # Overall selectivity = weighted average across genres
        genre_selectivity = {}
        selectivity_values = []
        for genre, ratings in genre_ratings.items():
            if len(ratings) < 2:
                continue
            mean = sum(ratings) / len(ratings)
            variance = sum((r - mean) ** 2 for r in ratings) / len(ratings)
            std_dev = math.sqrt(variance)
            # Normalize: 0-15 std dev maps to 0-100 selectivity
            # (15 is roughly max realistic std dev for 0-100 scale)
            sel = min(100, round(std_dev / 15 * 100, 1))
            genre_selectivity[genre] = {
                'selectivity': sel,
                'std_dev': round(std_dev, 1),
                'avg_rating': round(mean, 1),
                'song_count': len(ratings),
                'rating_range': f"{min(ratings)}-{max(ratings)}",
            }
            selectivity_values.append((sel, len(ratings)))  # (score, weight)
        
        # Weighted average (more songs = more weight)
        if selectivity_values:
            total_songs = sum(w for _, w in selectivity_values)
            overall_selectivity = round(
                sum(s * w for s, w in selectivity_values) / total_songs, 1
            ) if total_songs else 0
        else:
            overall_selectivity = 0
        
        # ---- 4. Top Influences (artists driving your taste) ----
        # Dual metric:
        #   influence_score = taste influence (only songs rated >= 75)
        #   exposure_score  = listening exposure (all rated songs)
        _SKIP_INFLUENCE = {'Announcement', 'META', 'Various Artists', 'Various', 'Unknown', 'N/A'}
        _ARTIST_ALIASES = {
            'piano guys': 'The Piano Guys',
            'the piano guys': 'The Piano Guys',
            'cusp of ignition': 'Hoyo-Mix',
            '2econd 2ight 2eer': 'Will Wood',
            'hagali': 'Hagali',
            'ado': 'Ado',
            'lawson': 'Lawson',
        }
        _canonical_names = {}  # lowercase -> canonical casing

        def _resolve_artist(name, genre):
            """Resolve artist name through aliases and canonical merge. Returns None if skipped."""
            if name in _SKIP_INFLUENCE or genre in ('META/Other',):
                return None
            name = _ARTIST_ALIASES.get(name.lower(), name)
            lower = name.lower()
            if lower not in _canonical_names:
                _canonical_names[lower] = name
            return _canonical_names[lower]

        # --- Taste Influence (positive songs only, rating >= 75) ---
        taste_weights = defaultdict(lambda: {'weight': 0, 'genres': set(), 'top_song': '', 'top_rating': 0, '_raw_ratings': []})
        for r in positive_songs:
            artists = self._extract_artists_from_row(r)
            rating = int(r['rating'])
            genre = r.get('_genre', 'Uncategorized')
            for a in artists:
                artist = _resolve_artist(a, genre)
                if not artist:
                    continue
                taste_weights[artist]['weight'] += rating
                taste_weights[artist]['_raw_ratings'].append(rating)
                taste_weights[artist]['genres'].add(genre)
                if rating > taste_weights[artist]['top_rating']:
                    taste_weights[artist]['top_rating'] = rating
                    taste_weights[artist]['top_song'] = r.get('title', '')[:60]

        # --- Exposure (all rated songs) ---
        exposure_weights = defaultdict(lambda: {'_raw_ratings': []})
        for r in self.rated_entries:
            artists = self._extract_artists_from_row(r)
            rating = int(r['rating'])
            genre = r.get('_genre', 'Uncategorized')
            for a in artists:
                artist = _resolve_artist(a, genre)
                if not artist:
                    continue
                exposure_weights[artist]['_raw_ratings'].append(rating)

        # Compute scores for all artists
        all_artist_data = {}  # artist -> merged data
        for artist, data in taste_weights.items():
            ratings = data.get('_raw_ratings', [])
            avg = sum(ratings) / len(ratings) if ratings else 0
            all_artist_data[artist] = {
                'influence_score': round(avg * math.log(len(ratings) + 1), 1) if ratings else 0,
                'song_count': len(ratings),
                'avg_rating': round(avg, 1),
                'genres': list(data['genres']),
                'top_song': data['top_song'],
                'top_rating': data['top_rating'],
                'exposure_score': 0,
                'exposure_count': 0,
            }
        for artist, data in exposure_weights.items():
            ratings = data.get('_raw_ratings', [])
            if not ratings:
                continue
            avg = sum(ratings) / len(ratings)
            exp_score = round(avg * math.log(len(ratings) + 1), 1)
            if artist in all_artist_data:
                all_artist_data[artist]['exposure_score'] = exp_score
                all_artist_data[artist]['exposure_count'] = len(ratings)
            else:
                # Artist only has negative songs (none rated >= 75)
                all_artist_data[artist] = {
                    'influence_score': 0,
                    'song_count': 0,
                    'avg_rating': round(avg, 1),
                    'genres': [],
                    'top_song': '',
                    'top_rating': 0,
                    'exposure_score': exp_score,
                    'exposure_count': len(ratings),
                }

        # Filter: at least 3 songs total (taste or exposure)
        min_songs = 3
        eligible = {a for a, d in all_artist_data.items()
                    if d['song_count'] >= min_songs or d['exposure_count'] >= min_songs}

        # Sort: taste influence first, then exposure-only artists after
        taste_artists = [(a, d) for a, d in all_artist_data.items() if a in eligible and d['influence_score'] > 0]
        exposure_only = [(a, d) for a, d in all_artist_data.items() if a in eligible and d['influence_score'] == 0 and d['exposure_count'] >= min_songs]
        taste_artists.sort(key=lambda x: -x[1]['influence_score'])
        exposure_only.sort(key=lambda x: -x[1]['exposure_score'])
        # Show top 50 taste + up to 30 exposure-only
        top_influences = taste_artists[:50] + exposure_only[:30]

        top_influences_list = []
        for artist, data in top_influences:
            top_influences_list.append({
                'artist': artist,
                'influence_score': data['influence_score'],
                'exposure_score': data['exposure_score'],
                'song_count': data['song_count'],
                'exposure_count': data['exposure_count'],
                'avg_rating': data['avg_rating'],
                'genres': data['genres'],
                'top_song': data['top_song'],
                'top_rating': data['top_rating'],
            })
        
        # ---- 5. Taste Summary ----
        top_genre = max(genre_fingerprint.items(), key=lambda x: x[1]['weight']) if genre_fingerprint else None
        top_decade = max(year_fingerprint.items(), key=lambda x: x[1]['weight']) if year_fingerprint else None
        top_artist = top_influences[0] if top_influences else None
        
        summary_parts = []
        if top_genre:
            summary_parts.append(f"{top_genre[0]} ({top_genre[1]['weight']*100:.0f}% of your taste)")
        if top_decade:
            summary_parts.append(f"{top_decade[0]} ({top_decade[1]['weight']*100:.0f}%)")
        if top_artist:
            summary_parts.append(f"Top influence: {top_artist[0]} (score {top_artist[1]['influence_score']:.0f})")
        
        if overall_predictability > 70:
            summary_parts.append("Your taste is highly predictable — you know what you like!")
        elif overall_predictability > 40:
            summary_parts.append("Your taste is moderately predictable — strong preferences with some diversity.")
        else:
            summary_parts.append("Your taste is hard to predict — very diverse and eclectic!")
        
        return {
            'genre_fingerprint': genre_fingerprint,
            'year_fingerprint': year_fingerprint,
            'predictability': {
                'overall': overall_predictability,
                'genre_entropy': round(genre_entropy, 3),
                'year_entropy': round(year_entropy, 3),
                'genre_predictability': genre_predictability,
                'year_predictability': year_predictability,
                'max_genre_entropy': round(max_genre_entropy, 3),
                'max_year_entropy': round(max_year_entropy, 3),
            },
            'selectivity': {
                'overall': overall_selectivity,
                'by_genre': genre_selectivity,
            },
            'top_influences': top_influences_list,
            'taste_summary': '. '.join(summary_parts) + '.',
            'positive_song_count': len(positive_songs),
            'overall_avg': round(sum(int(r['rating']) for r in positive_songs) / len(positive_songs), 1),
        }

    def get_taste_fit(self, artist: str, song: str, genre: str = '', year: int = None) -> Dict:
        """Score how well a candidate song fits the user's taste fingerprint.
        
        Returns:
          - fit_score: 0-100 (how well it matches)
          - genre_match: which genre dimension contributes most
          - year_match: how close to preferred decades
          - explanation: human-readable explanation
        """
        fingerprint = self.get_taste_fingerprint()
        genre_fp = fingerprint['genre_fingerprint']
        year_fp = fingerprint['year_fingerprint']
        
        if not genre_fp:
            return {'fit_score': 50, 'explanation': 'Insufficient data to score.'}
        
        # ---- Genre match ----
        genre_match_score = 0
        genre_detail = ''
        if genre and genre in genre_fp:
            # The song's genre is in your fingerprint — score by weight
            genre_match_score = genre_fp[genre]['weight'] * 100
            genre_detail = f"{genre} is {genre_fp[genre]['weight']*100:.0f}% of your taste"
        elif genre:
            # Genre not in your fingerprint — check if it's close
            # (e.g., 'Pop' vs 'Synth-Pop')
            for fp_genre, data in genre_fp.items():
                if genre.lower() in fp_genre.lower() or fp_genre.lower() in genre.lower():
                    genre_match_score = data['weight'] * 80  # partial match
                    genre_detail = f"Similar to {fp_genre} ({data['weight']*100:.0f}% of taste)"
                    break
            if not genre_detail:
                genre_match_score = 0
                genre_detail = f"{genre} is not in your usual palette"
        
        # ---- Year match ----
        year_match_score = 50  # default neutral
        year_detail = ''
        if year and year_fp:
            decade = f"{(year // 10) * 10}s"
            if decade in year_fp:
                year_match_score = year_fp[decade]['weight'] * 100
                year_detail = f"{decade} is {year_fp[decade]['weight']*100:.0f}% of your taste"
            else:
                # Find closest decade
                target_decade = (year // 10) * 10
                closest = min(
                    (int(d.rstrip('s')) for d in year_fp.keys()),
                    key=lambda d: abs(d - target_decade)
                )
                gap = abs(target_decade - closest)
                year_match_score = max(0, 50 - gap * 2)
                year_detail = f"{year} is {gap} years from your preferred {closest}s"
        
        # ---- Artist affinity ----
        artist_score = 0
        artist_detail = ''
        artist_lower = artist.lower() if artist else ''
        for inf in fingerprint['top_influences']:
            inf_lower = inf['artist'].lower()
            if artist_lower in inf_lower or inf_lower in artist_lower:
                # Direct match — score by influence rank
                rank = fingerprint['top_influences'].index(inf) + 1
                artist_score = max(0, 100 - (rank - 1) * 5)
                artist_detail = f"{inf['artist']} is your #{rank} influence"
                break
        
        # ---- Combined fit score ----
        # Weight: genre 40%, year 25%, artist 35%
        fit_score = round(
            genre_match_score * 0.40 +
            year_match_score * 0.25 +
            artist_score * 0.35
        )
        fit_score = max(0, min(100, fit_score))
        
        # ---- Explanation ----
        parts = []
        if genre_detail:
            parts.append(genre_detail)
        if year_detail:
            parts.append(year_detail)
        if artist_detail:
            parts.append(artist_detail)
        if not parts:
            parts.append('Insufficient data to make a prediction')
        
        return {
            'fit_score': fit_score,
            'genre_match': round(genre_match_score, 1),
            'year_match': round(year_match_score, 1),
            'artist_match': round(artist_score, 1),
            'explanation': '. '.join(parts) + '.',
            'label': self._fit_label(fit_score),
        }
    
    @staticmethod
    def _fit_label(score: int) -> str:
        """Human-readable label for a fit score."""
        if score >= 90:
            return 'Perfect Fit'
        elif score >= 75:
            return 'Strong Match'
        elif score >= 60:
            return 'Good Fit'
        elif score >= 40:
            return 'Moderate Match'
        elif score >= 20:
            return 'Weak Match'
        else:
            return 'Poor Fit'

    # ------------------------------------------------------------------
    # Outlier Detection
    # ------------------------------------------------------------------

    def get_outliers(self) -> Dict:
        """Statistical outlier detection — songs and artists that break
        your own patterns.  Delegates to src.outliers.detect_outliers().
        """
        from src.outliers import detect_outliers
        return detect_outliers(
            self.rated_entries, self.all_artists, self.ratings,
        )

    # ------------------------------------------------------------------
    # Data hygiene scan — surfaces identity/pollution problems so they
    # get caught automatically instead of by eyeballing the CSV.
    # ------------------------------------------------------------------

    def get_data_hygiene(self) -> Dict:
        """Scan the collection for data-quality problems.

        Categories:
          artist_self_rows  — title == artist == song rows (imported
                              artist-level ratings treated as songs)
          generic_artists   — placeholder names ('Unknown Artist',
                              'Various Artists', 'Test Artist', ...)
          case_variants     — artist spellings differing only by
                              case/punctuation that identity folding merges
          cache_conflicts   — genre-cache fold-groups with contradictory
                              values (resolved at lookup, but worth cleaning)
          duplicate_songs   — same artist+song appearing multiple times
          no_artist         — song rows with no artist at all

        Each finding is informational (no data is modified here); the view
        explains what each means and how it was/would be handled.
        """
        from collections import Counter

        # --- Artist-level rows ------------------------------------------
        self_rows = [
            {
                'title': r.get('title', ''),
                'artist': (r.get('artist') or '').strip(),
                'rating': r.get('rating') or None,
                'date': r.get('date', ''),
            }
            for r in self.rows if self._is_artist_self_row(r)
        ]

        # --- Placeholder artists ----------------------------------------
        generic_counts = Counter()
        for r in self.rows:
            a = (r.get('artist') or '').strip()
            if a and self._is_generic_artist_name(a):
                generic_counts[a] += 1
        generic_artists = [
            {'artist': a, 'count': n} for a, n in generic_counts.most_common()
        ]

        # --- Case-variant groups (what folding merges) -------------------
        variant_counts = defaultdict(Counter)
        for r in self.rows:
            a = (r.get('artist') or '').strip()
            if a and a.lower() != 'announcement' \
                    and not self._is_generic_artist_name(a):
                variant_counts[self._fold_artist_key(a)][a] += 1
        case_variants = [
            {
                'canonical': self._artist_case(k and next(iter(v.keys())) or ''),
                'variants': dict(v.most_common()),
                'rows': sum(v.values()),
            }
            for k, v in sorted(variant_counts.items(), key=lambda kv: -sum(kv[1].values()))
            if len(v) > 1
        ]

        # --- Genre-cache conflicts (contradictory fold-groups) -----------
        cache_conflicts = []
        groups = defaultdict(dict)
        for k, g in self._artist_genre_cache.items():
            fk = self._fold_artist_key(k)
            if fk:
                groups[fk][k] = g
        for fk, variants in groups.items():
            if len(set(variants.values())) > 1:
                cache_conflicts.append({
                    'artist': self._artist_case(next(iter(variants))),
                    'values': variants,
                    'resolved': self._genre_cache_folded.get(fk),
                })
        cache_conflicts.sort(key=lambda c: c['artist'])

        # --- Duplicate songs (same artist+song sig, >1 row) --------------
        # Init-time dedup keeps only the best row in memory, so duplicates
        # are scanned on the RAW disk rows — the report shows what is on
        # disk and notes that load-time merging already handled it.
        raw_rows = self._read_raw_rows()
        # Archived meta posts ('6/18/2018's Spotify') still live in the base
        # CSV by design (excluded at load time); don't re-report them here.
        raw_rows = [
            r for r in raw_rows
            if self._normalize_sig((r.get('title') or '').strip())
            not in self.special_sigs
        ]
        sig_rows = defaultdict(list)
        for r in raw_rows:
            title = (r.get('title') or '').strip()
            if not title:
                continue
            artist = (r.get('artist') or '').strip()
            sig = self._normalize_sig(f"{artist} {title}")
            sig_rows[sig].append({
                'title': title,
                'artist': artist,
                'rating': r.get('rating') or None,
                'date': r.get('date', ''),
            })
        duplicate_songs = [
            {'sig': sig, 'rows': rows}
            for sig, rows in sorted(
                sig_rows.items(),
                key=lambda kv: -len(kv[1]),
            )
            if len(rows) > 1
        ][:20]

        # --- Missing artists ---------------------------------------------
        no_artist = [
            {
                'title': r.get('title', ''),
                'rating': r.get('rating') or None,
                'date': r.get('date', ''),
            }
            for r in raw_rows
            if not (r.get('artist') or '').strip()
            and (r.get('title') or '').strip()
            and (r.get('title') or '').strip().lower() != 'announcement'
        ][:20]

        return {
            'summary': {
                'artist_self_rows': len(self_rows),
                'generic_artist_rows': sum(generic_counts.values()),
                'case_variant_groups': len(case_variants),
                'cache_conflicts': len(cache_conflicts),
                'duplicate_songs': len(duplicate_songs),
                'no_artist_rows': len(no_artist),
            },
            'artist_self_rows': self_rows[:20],
            'generic_artists': generic_artists[:15],
            'case_variants': case_variants[:15],
            'cache_conflicts': cache_conflicts[:15],
            'duplicate_songs': duplicate_songs,
            'no_artist': no_artist,
        }

    def _read_raw_rows(self) -> List[Dict]:
        """Read the raw CSV rows from disk (base + additions overlay),
        bypassing init-time dedup — the hygiene scan reports what is
        actually stored, including rows the engine merges at load."""
        raw: List[Dict] = []
        for path in (self.csv_path, self.additions_path):
            try:
                with open(path, 'r', encoding='utf-8', newline='') as f:
                    raw.extend(list(csv.DictReader(f)))
            except (FileNotFoundError, OSError, ValueError, csv.Error):
                continue
        return raw
