"""
taste_engine.py - Core data processing and recommendation engine
Analyzes posts_tails.csv to build taste profiles, find blind spots,
and generate recommendations.
"""

import csv
import json as _json
import os
import re
import time
import urllib.parse
from collections import Counter, defaultdict
from datetime import datetime
from typing import List, Dict, Set, Optional

import networkx as nx
from networkx.algorithms.community import louvain_communities

from src.genre_data import GENRE_KEYWORDS, CURATED_ARTIST_GENRES, PARSE_ARTIFACTS, FAVORITE_ARTISTS
from src.challenge_db import CHALLENGE_DB, GENRE_ALIAS_TO_CLASS
from src.backfill import LETTER_GRADE_MAP, extract_letter_grade, infer_tone_rating


class TasteEngine:
    def __init__(self, csv_path: str = "data/posts_tails.csv"):
        self.csv_path = csv_path
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
        self._load_data()
        self._init_genre_keywords()
        self._load_genre_cache()  # load persisted cache before building index
        self._load_release_year_cache()  # MusicBrainz-enriched song release years
        self._load_ban_list()
        dedup_result = self.deduplicate(write_back=True)
        if dedup_result['removed'] > 0:
            print(f'[dedup] Removed {dedup_result["removed"]} duplicate rows from {self.csv_path}')
        self._classify_rows()      # pre-compute genre for every row (O(n), done once)
        self._build_artist_index()
        self._build_song_index()

    def _load_data(self):
        """Load and parse the CSV file."""
        with open(self.csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            self.rows = list(reader)

        self.rated_entries = [r for r in self.rows if r.get('rating')]
        self.ratings = [int(r['rating']) for r in self.rated_entries]

    # ------------------------------------------------------------------
    # Duplicate detection & removal
    # ------------------------------------------------------------------

    def deduplicate(self, *, write_back: bool = False) -> Dict:
        """Remove duplicate rows by normalized title signature.

        Two rows are duplicates if _normalize_sig(title1) == _normalize_sig(title2).
        Keeps the row with the higher rating; on ties keeps the earlier date.

        Args:
            write_back: If True, rewrite the CSV file without duplicates.

        Returns:
            { 'removed': int, 'kept': int, 'dupes': [{ 'title': str, 'kept': str }] }
        """
        seen: Dict[str, int] = {}  # sig → index in self.rows
        dupes = []
        indices_to_remove = set()

        for i, row in enumerate(self.rows):
            title = (row.get('title') or '').strip()
            if not title or title == 'Announcement':
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
            self._write_csv()

        return {
            'removed': len(dupes),
            'kept': len(self.rows),
            'dupes': dupes,
        }

    def _write_csv(self):
        """Rewrite the CSV file from self.rows."""
        if not self.rows:
            return
        fieldnames = list(self.rows[0].keys())
        # Strip internal _genre and other computed fields
        write_fields = [f for f in fieldnames if not f.startswith('_')]
        with open(self.csv_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=write_fields, extrasaction='ignore')
            writer.writeheader()
            for row in self.rows:
                writer.writerow({k: row.get(k, '') for k in write_fields})

    # ------------------------------------------------------------------
    # Row-level genre classification — pre-computed once on load
    # ------------------------------------------------------------------

    def _classify_row(self, row: Dict) -> str:
        """Classify a single row into a genre using 4-tier fallback:
          1. _artist_genre_cache (MusicBrainz / propagation) — most reliable
          2. CURATED_ARTIST_GENRES (400+ well-known artists) — authoritative
          3. Keyword match against title ONLY (not review text)
          4. Keyword match against review text as last resort
          5. 'Uncategorized'
        Stores the result in row['_genre'] for O(1) reuse.
        """
        artists = self._extract_artists(row.get('title', ''))

        # Tier 1: Artist cache (MusicBrainz, propagation, etc.)
        if self._artist_genre_cache:
            for artist in artists:
                if artist in self._artist_genre_cache:
                    cached_genre = self._artist_genre_cache[artist]
                    row['_genre'] = cached_genre
                    return cached_genre

        # Tier 2: Curated artist-genre mapping
        for artist in artists:
            if artist in CURATED_ARTIST_GENRES:
                curated_genre = CURATED_ARTIST_GENRES[artist]
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

        # Pattern 1: Title (Artist, Year)
        m = re.search(r'\(([^)]+),\s*\d{4}\)', title)
        if m:
            artists_str = m.group(1)
            parts = re.split(r'\s+(?:ft\.|feat\.|featuring|and|&)\s+|\s*,\s*', artists_str)
            for p in parts:
                p = p.strip().strip('"').strip("'")
                if p and len(p) > 1 and p.lower() not in PARSE_ARTIFACTS:
                    results.append(p)

        # Pattern 2: Artist – Song (forward) or Song – Artist (reverse)
        m = re.match(r'^(.+?)\s*[–-]\s+(.+)$', title)
        if m:
            before = m.group(1).strip().rstrip(',').strip('"').strip("'").strip()
            after = m.group(2).strip().rstrip('.').strip('"').strip("'").strip()
            
            # Music-specific keywords that indicate 'before' is the song
            song_indicators = ['theme', 'song', 'anthem', 'ballad', 'medley', 'remix',
                              'cover', 'version', 'suite', 'symphony', 'sonata']
            before_is_song = any(before.lower().endswith(ind) or before.lower().startswith(ind)
                                 for ind in song_indicators) or before.lower() in PARSE_ARTIFACTS
            
            # Try forward (Artist – Song): prefer 'before' as artist if it
            # looks like an artist name (capitalized phrase, not too long)
            candidate_forward = before
            candidate_reverse = after
            
            # Check cache AND curated list for both sides
            forward_known = (candidate_forward in CURATED_ARTIST_GENRES or
                             candidate_forward in self._artist_genre_cache)
            reverse_known = (candidate_reverse in CURATED_ARTIST_GENRES or
                             candidate_reverse in self._artist_genre_cache)
            
            if forward_known and reverse_known:
                # Both sides are known — prefer the one in CURATED_ARTIST_GENRES
                # (curated is more authoritative than the propagated cache)
                forward_curated = candidate_forward in CURATED_ARTIST_GENRES
                reverse_curated = candidate_reverse in CURATED_ARTIST_GENRES
                if forward_curated and not reverse_curated:
                    chosen = candidate_forward
                elif reverse_curated and not forward_curated:
                    chosen = candidate_reverse if not before_is_song else candidate_forward
                else:
                    # Both or neither curated — prefer forward (Artist – Song is more common)
                    chosen = candidate_forward
                if chosen and len(chosen) > 1 and chosen not in results:
                    results.append(chosen)
            elif reverse_known and not before_is_song:
                # Reverse pattern: Song – Artist, and the after part is a known artist
                if candidate_reverse and len(candidate_reverse) > 1 and candidate_reverse not in results:
                    results.append(candidate_reverse)
            elif forward_known:
                # Forward pattern: Artist – Song, and the before part is a known artist
                if candidate_forward and len(candidate_forward) > 1 and candidate_forward not in results:
                    results.append(candidate_forward)
            else:
                # Neither side is known — use heuristics to guess direction
                # Count how many "person-like" words each side has
                def _looks_like_artist_name(n):
                    """Heuristic: name with 2-4 capitalized words looks like artist."""
                    words = n.split()
                    if len(words) < 1 or len(words) > 5:
                        return False
                    cap_words = sum(1 for w in words if w and w[0].isupper())
                    return cap_words >= max(1, len(words) - 1)
                
                forward_artist_score = sum(1 for w in candidate_forward.split() if w and w[0].isupper())
                reverse_artist_score = sum(1 for w in candidate_reverse.split() if w and w[0].isupper())
                forward_words = len(candidate_forward.split())
                reverse_words = len(candidate_reverse.split())
                
                # Determine: which side looks more like an artist name?
                forward_is_artist = _looks_like_artist_name(candidate_forward)
                reverse_is_artist = _looks_like_artist_name(candidate_reverse)
                
                # A short left side (1-3 words) with a longer right side with capital words
                # is likely Song – Artist
                # A proper-name-like left side is likely Artist – Song
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
                    # Left is longer (more song-like), right has capitals (artist-like)
                    choose_reverse = True
                elif before_is_song:
                    choose_reverse = True
                elif len(candidate_forward) >= 30:
                    choose_reverse = True
                else:
                    choose_reverse = False  # Default forward
                
                if choose_reverse:
                    if candidate_reverse and len(candidate_reverse) > 1 and candidate_reverse not in results:
                        results.append(candidate_reverse)
                else:
                    if candidate_forward and len(candidate_forward) > 1 and candidate_forward not in results:
                        results.append(candidate_forward)

        # Pattern 2b: Em dash / no-space dash: "Artist—Song" or "Artist -Song"
        if not results:
            m2b = re.match(r'^(.+?)\u2014(.+)$', title) or re.match(r'^(.+?)-([A-Z].+)$', title)
            if m2b:
                artist = m2b.group(1).strip().strip('"').strip("'").strip()
                if artist and len(artist) > 1 and artist not in results:
                    results.append(artist)

        # Pattern 2c: Middle dot separator: "Artist \u00b7 Song"
        if not results:
            m2c = re.match(r'^(.+?)\s*\u00b7\s+(.+)$', title)
            if m2c:
                artist = m2c.group(1).strip().strip('"').strip("'").strip()
                if artist and len(artist) > 1 and artist not in results:
                    results.append(artist)

        # Pattern 2d: Japanese bracket format: "\u300cArtist\u300d" or "（Artist）"
        if not results:
            m2d = re.search(r'\u300c([^\u300c\u300d]+)\u300d', title)
            if m2d:
                artist = m2d.group(1).strip()
                if artist and len(artist) > 1 and artist not in results:
                    results.append(artist)
            else:
                # Try fullwidth parentheses: "（Artist）"
                m2e = re.search(r'\uff08([^\uff08\uff09]+)\uff09', title)
                if m2e:
                    artist = m2e.group(1).strip()
                    if artist and len(artist) > 1 and artist not in results:
                        results.append(artist)

        # Pattern 2e: Double pipe separator: "Artist || Song"
        if not results:
            m2f = re.match(r'^(.+?)\s*\|\|\s+(.+)$', title)
            if m2f:
                artist = m2f.group(1).strip().strip('"').strip("'").strip()
                if artist and len(artist) > 1 and artist not in results:
                    results.append(artist)

        # Pattern 2f: Artist "Song Title" with title in quotes
        if not results:
            m2g = re.match(r'^(.+?)\s+["\u201c]([^"\u201d]+)["\u201d]', title)
            if m2g:
                artist = m2g.group(1).strip()
                if artist and len(artist) > 1 and artist not in results:
                    results.append(artist)

        # Pattern 3: Song by Artist (unless we already got an artist from dash)
        if not results:
            m2 = re.search(r'\s+by\s+(.+)$', title)
            if m2:
                artist = m2.group(1).strip().strip('"').strip("'").strip('"').rstrip('.').strip()
                if artist and len(artist) > 1 and artist not in results:
                    # Remove leading articles/description
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
        m = re.match(r'^(.*?)\s*\(([^,)]+?)(?:,\s*(19\d{2}|20\d{2}))?\)\s*$', title or '')
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

        # Pattern 6: Japanese brackets: Song「Artist」or「Artist」Song
        # e.g. "Koisuru Kimochi「Kana Nishino」" or 「Yura Hatsuki」Shadows
        m6 = re.search(r'「([^」]+)」', title or '')
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

    @classmethod
    def _release_year_for(cls, title: str) -> Optional[int]:
        """Best-effort release year for a rated song title.
        Resolution order: official challenge database (authoritative), then
        the enrichment cache (MusicBrainz / iTunes results for songs the
        database doesn't have), then the year embedded in the title."""
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
            artists = self._extract_artists(r.get('title', ''))
            rating = int(r['rating']) if r['rating'] else None
            combined = ((r.get('tail') or '') + ' ' + (r.get('title') or '')).lower()
            
            for artist in artists:
                if rating:
                    all_artists_info[artist]['ratings'].append(rating)
                    all_artists_info[artist]['songs'].append({
                        'title': r['title'],
                        'rating': rating,
                        'date': r.get('date', '')
                    })
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
        for artist, info in all_artists_info.items():
            genre_scores = info.pop('genre_score', {})
            if artist in CURATED_ARTIST_GENRES:
                info['genre'] = CURATED_ARTIST_GENRES[artist]
            elif artist in self._artist_genre_cache:
                info['genre'] = self._artist_genre_cache[artist]
            elif genre_scores:
                info['genre'] = max(genre_scores, key=genre_scores.get)
            else:
                info['genre'] = 'Uncategorized'

        self.all_artists = dict(all_artists_info)

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
        """
        t = text.lower()
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
            # (e.g. 'sparkle' ⊂ 'sparkle radwimps')
            for known_latin in self._latin_titles:
                if time.monotonic() - start_time > timeout_sec:
                    return {'exists': False, 'match': None, 'title': None, 'timeout': True}
                if latin_sig in known_latin or known_latin in latin_sig:
                    return {'exists': True, 'match': 'latin', 'title': None}

        # Also try with artist+song combo (Latin-normalized)
        if latin_combo and len(latin_combo) >= 5:
            if latin_combo in self._latin_titles:
                return {'exists': True, 'match': 'latin', 'title': None}
            # Substring check on combo too
            for known_latin in self._latin_titles:
                if time.monotonic() - start_time > timeout_sec:
                    return {'exists': False, 'match': None, 'title': None, 'timeout': True}
                if latin_combo in known_latin or known_latin in latin_combo:
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
            if artist in self.all_artists:
                info = self.all_artists[artist]
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

    def get_constellation(self) -> Dict:
        """Build artist similarity network for the constellation view.
        Uses a multi-tier edge strategy:
          1. Collaboration edges — artists that appear together in songs
          2. Genre-similarity edges — artists sharing the same genre
          3. Rating-pattern edges — artists with similar rating profiles
          4. Community detection (Louvain) — finds natural groupings from the
             edge structure, assigns each artist a community_id so the frontend
             can cluster them visually without needing a genre-based layout.
        """
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
                nodes.append({
                    'id': artist,
                    'name': artist,
                    'avg_rating': avg,
                    'song_count': len(info['ratings']),
                    'max_rating': max_r,
                    'genre': genre
                })
                genre_artists[genre].append(artist)
                artist_ratings_vec[artist] = info['ratings']

        # ---- Edges ----

        # Tier 1: Collaboration edges (artists appearing together in songs)
        seen_collab: Set[tuple] = set()
        for r in self.rows:
            artists = self._extract_artists(r.get('title', ''))
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
        # Group ratings by month
        monthly = defaultdict(list)
        for r in self.rated_entries:
            month_key = (r.get('date') or '')[:7]  # YYYY-MM
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

        # Yearly stats
        yearly = defaultdict(list)
        for r in self.rated_entries:
            year = (r.get('date') or '')[:4]
            yearly[year].append(int(r['rating']))

        yearly_avg = {}
        for year, ratings in sorted(yearly.items()):
            yearly_avg[year] = {
                'avg': round(sum(ratings) / len(ratings), 1),
                'count': len(ratings),
                'top_rating': max(ratings)
            }

        # Cumulative song count
        cumulative = []
        sorted_rows = sorted(self.rows, key=lambda x: x['date'])
        count = 0
        for r in sorted_rows:
            if r.get('title', '') and r.get('title', '') != 'Announcement':
                if r.get('rating'):
                    count += 1
                    if count % 25 == 0 or count == 1:
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
            artists = self._extract_artists(r.get('title', ''))
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
                if title.strip() == 'Announcement' or not title.strip():
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
            if artist in self.all_artists:
                g2 = self.all_artists[artist].get('genre')
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
                if rec.get('artist') in self.all_artists:
                    rec_genre = self.all_artists[rec['artist']].get('genre')
                elif rec.get('artist') in CURATED_ARTIST_GENRES:
                    rec_genre = CURATED_ARTIST_GENRES[rec['artist']]
                if rec_genre and rec_genre in fav_genres and rec_genre != 'Uncategorized':
                    is_fav_adjacent = True
            checked.append({
                **rec,
                'already_owned': dup['exists'],
                'favorite_adjacent': is_fav_adjacent
            })
        return checked

    def get_recommendations(self, style: str = 'all') -> Dict:
        """Generate song recommendations based on taste profile.
        Every recommendation is tagged with already_owned=True/False via O(1) hash lookup.
        """
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
        # Algorithm-scored picks — an honest alternative to the hand-curated
        # categories above. Computed from the user's own ratings over the shared
        # acclaim candidate pool; nothing is hardcoded here. Name starts with
        # "A" so that Flask's JSON_SORT_KEYS (default on) floats it to the top
        # of the response alongside the "If you love…" categories.
        rec_categories = {
            'Algorithm picks (scored · not hand-picked)': {
                'artists': [],
                'recommendations': self.get_algorithmic_recommendations(5),
            },
            **rec_categories,
        }

        # Filter out songs already in collection � backend-level dedup so the
        # frontend never renders an 'already in collection' badge. The recommender
        # shows only fresh, listenable suggestions.
                # Filter out already_owned and banned songs from each category
        for cat_name, cat_data in rec_categories.items():
            cat_data['recommendations'] = [
                r for r in cat_data['recommendations']
                if not r.get('already_owned', False)
                and not self._is_banned(
                    artist=r.get('artist', ''),
                    song=r.get('song', ''),
                    genre=cat_name,
                )
            ]
        return rec_categories

    def get_algorithmic_recommendations(self, limit: int = 5) -> List[Dict]:
        """Algorithm-scored recommendations — an honest alternative to the
        hand-curated catalog. Builds a taste vector from the user's own rated
        rows, scores every candidate in CHALLENGE_DB by
        (0.45 * genre affinity) + (0.30 * artist affinity) + (0.25 * acclaim),
        ranks them, and returns the top NEW options. No hardcoded picks — this
        is pure content-based scoring over the candidate pool.
        """
        # 1) Taste vector from the user's rated rows (same genre scheme as
        #    _classify_row). genre_aff = summed love weight, plus avg + count.
        genre_aff = defaultdict(float)
        genre_sum = defaultdict(float)
        genre_cnt = defaultdict(int)
        for r in self.rated_entries:
            g = r.get('_genre') or 'Uncategorized'
            rating = int(r['rating'])
            genre_aff[g] += rating / 100.0
            genre_sum[g] += rating
            genre_cnt[g] += 1

        def g_label(g):
            """Human readable 'you rate X n/100' when we have data."""
            return genre_cnt[g] and int(round(genre_sum[g] / genre_cnt[g])) or None

        max_aff = max(genre_aff.values()) if genre_aff else 1.0

        # 2) Artist affinity — avg of the user's ratings per known artist.
        artist_avg = {}
        for a, info in self.all_artists.items():
            if info.get('ratings'):
                artist_avg[a] = sum(info['ratings']) / len(info['ratings'])

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

            ga = genre_aff.get(cand_class, 0.0) / max_aff            # 0..1 genre pull
            known = artist in artist_avg
            aa = (artist_avg[artist] / 100.0) if known else 0.5      # 0..1
            q = (c.get('listen_score') or 60) / 100.0                # 0..1 acclaim
            score = 0.45 * ga + 0.30 * aa + 0.25 * q

            # Build a computed (not hand-written) reason from what dominated.
            parts = []
            avg_lbl = g_label(cand_class)
            if ga >= 0.5:
                parts.append(f"you rate {cand_class} {avg_lbl}/100 on average")
            elif ga >= 0.25:
                parts.append(f"leans toward your {cand_class} taste")
            if known and artist_avg[artist] >= 75:
                parts.append(f"you've rated {artist} {int(round(artist_avg[artist]))}/100")
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
            info = self.all_artists[artist]
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

    def get_challenges(self, count: int = 20, mode: str = 'outside_zone') -> Dict:
        """Get a set of critically acclaimed songs outside your listening zone.
        Filters songs already in your collection, personalizes the challenge reason,
        ranks by how far outside your zone they are, and ensures all 4 tiers are represented.

        Args:
            count: Number of challenges to return (default 20)
            mode: 'outside_zone' (default, most outside first),
                  'opposite_taste' (prioritize genres you rate lowest), or
                  'obscure' (songs most people don't know — low popularity)
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
                info = self.all_artists.get(song['artist'], {})
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

        return {
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
            artists = self._extract_artists(r.get('title', ''))
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
            self._artist_genre_cache[artist] = genre        # --- Strategy 2: Curated artist-genre mapping (manually verified) ---
        # Human-curated genres are authoritative and OVERRIDE the propagation
        # vote: a song title containing "dance" or "theme" is not evidence of
        # the artist's genre (e.g. Lindsey Stirling's Christmas album would
        # otherwise label her Christmas/Holiday).
        curated_applied = 0
        for artist, genre in CURATED_ARTIST_GENRES.items():
            if self._artist_genre_cache.get(artist) != genre:
                self._artist_genre_cache[artist] = genre
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
                        artists = self._extract_artists(r.get('title', ''))
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
                        self._artist_genre_cache[artist] = mapped
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
                        artists = self._extract_artists(r.get('title', ''))
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
                    artists = self._extract_artists(r.get('title', ''))
                    for a in artists:
                        if a and a not in self._artist_genre_cache:
                            artist_uncat[a] += 1
            
            sorted_artists = sorted(artist_uncat.items(), key=lambda x: -x[1])[:200]
            for artist_name, cnt in sorted_artists:
                mb_stats['looked_up'] += 1
                genre = self._classify_artist_genre_musicbrainz(artist_name)
                if genre != 'Uncategorized':
                    self._artist_genre_cache[artist_name] = genre
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
            fieldnames = ['date', 'rating', 'title', 'tail']
            with open(self.csv_path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                # Strip internal fields (_genre, etc.) before writing to CSV
                clean_rows = [{k: v for k, v in row.items() if not k.startswith('_')}
                              for row in self.rows]
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
