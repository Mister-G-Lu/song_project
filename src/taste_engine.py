"""
taste_engine.py - Core data processing and recommendation engine
Analyzes posts_tails.csv to build taste profiles, find blind spots,
and generate recommendations.
"""

import csv
import json as _json
import re
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
        self._artist_genre_cache: Dict[str, str] = {}  # artist→genre cache (MusicBrainz, Wikidata, propagation)
        self._load_data()
        self._init_genre_keywords()
        self._load_genre_cache()  # load persisted cache before building index
        self._load_ban_list()
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
    # Row-level genre classification — pre-computed once on load
    # ------------------------------------------------------------------

    def _classify_row(self, row: Dict) -> str:
        """Classify a single row into a genre using 4-tier fallback:
          1. Keyword match against review text + title
          2. _artist_genre_cache (populated by MusicBrainz / backfill)
          3. CURATED_ARTIST_GENRES (400+ well-known artists)
          4. 'Uncategorized'
        Stores the result in row['_genre'] for O(1) reuse.
        """
        combined = ((row.get('tail') or '') + ' ' + (row.get('title') or '')).lower()

        # Tier 1: Keyword match
        for genre, keywords in self.genre_keywords.items():
            for kw in keywords:
                if self._kw_in_text(kw, combined):
                    row['_genre'] = genre
                    return genre

        # Tier 2: Artist cache (MusicBrainz, propagation, etc.)
        if self._artist_genre_cache:
            artists = self._extract_artists(row.get('title', ''))
            for artist in artists:
                if artist in self._artist_genre_cache:
                    cached_genre = self._artist_genre_cache[artist]
                    row['_genre'] = cached_genre
                    return cached_genre

        # Tier 3: Curated artist-genre mapping
        artists = self._extract_artists(row.get('title', ''))
        for artist in artists:
            if artist in CURATED_ARTIST_GENRES:
                curated_genre = CURATED_ARTIST_GENRES[artist]
                row['_genre'] = curated_genre
                return curated_genre

        # Tier 4: Uncategorized
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
            
            if reverse_known and not before_is_song:
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

        # Convert defaultdict genre scores to a single primary genre string
        for artist, info in all_artists_info.items():
            genre_scores = info.pop('genre_score', {})
            if genre_scores:
                info['genre'] = max(genre_scores, key=genre_scores.get)
            elif artist in self._artist_genre_cache:
                # Fallback to MusicBrainz cache (adversarial review finding)
                info['genre'] = self._artist_genre_cache[artist]
            elif artist in CURATED_ARTIST_GENRES:
                info['genre'] = CURATED_ARTIST_GENRES[artist]
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
        # Remove all punctuation except hyphens in words
        t = re.sub(r'[^\w\s-]', ' ', t)
        # Collapse whitespace
        t = re.sub(r'\s+', ' ', t).strip()
        return t

    def _build_song_index(self):
        """Build normalized hash sets of all known songs for O(1) duplicate lookup.

        We store two sets:
          known_sigs  — normalized "artist — song" combo for each row
          known_titles — normalized raw title from the CSV (broader match surface)
        """
        sigs: Set[str] = set()
        titles: Set[str] = set()

        for r in self.rows:
            raw = (r.get('title') or '').strip()
            if not raw or raw == 'Announcement':
                continue
            titles.add(self._normalize_sig(raw))

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
    def check_song_exists(self, artist: str, song: str) -> Dict:
        """Check whether an artist+song combo already exists in your collection.
        Returns {'exists': True/False, 'match': 'exact'|'fuzzy'|None, 'title': matching title or None}
        """
        # Exact: normalized combo
        combo_sig = self._normalize_sig(f"{artist} {song}")
        if combo_sig in self.known_sigs:
            return {'exists': True, 'match': 'exact', 'title': f"{artist} – {song}"}

        # Fuzzy: just the song name against known titles
        song_sig = self._normalize_sig(song)
        if song_sig in self.known_titles:
            return {'exists': True, 'match': 'fuzzy', 'title': None}

        # Check each known title for partial overlap
        for known in self.known_titles:
            if song_sig in known or known in song_sig:
                return {'exists': True, 'match': 'fuzzy', 'title': None}

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
            'blind_spots': blind_spots
        }

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

        return {
            'monthly_avg': monthly_avg,
            'yearly': yearly_avg,
            'genre_evolution': genre_evolution,
            'cumulative': cumulative
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
        Matching is case-insensitive with exact and substring checks."""
        if not artist and not song and not genre:
            return False
        na = artist.lower().strip() if artist else ""
        ns = song.lower().strip() if song else ""
        ng = genre.lower().strip() if genre else ""
        bl = self.ban_list
        if ng in bl["genres"]:
            return True
        if na and na in bl["artists"]:
            return True
        if ns and ns in bl["songs"]:
            return True
        if ng:
            for b in bl["genres"]:
                if b and (b in ng or ng in b):
                    return True
        if na:
            for b in bl["artists"]:
                if b and na and (b in na or na in b):
                    return True
        if ns:
            for b in bl["songs"]:
                if b and ns and (b in ns or ns in b):
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
                ])
            },

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

    def get_challenges(self, count: int = 20, mode: str = 'outside_zone') -> Dict:
        """Get a set of critically acclaimed songs outside your listening zone.
        Filters songs already in your collection, personalizes the challenge reason,
        ranks by how far outside your zone they are, and ensures all 4 tiers are represented.

        Args:
            count: Number of challenges to return (default 20)
            mode: 'outside_zone' (default, most outside first) or
                  'opposite_taste' (prioritize genres you rate lowest)
        """
        db = self._build_challenge_db()

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
                zone_note = f"No songs in '{song['genre']}' in your collection"
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
        if mode == 'opposite_taste':
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
        curated_applied = 0
        for artist, genre in CURATED_ARTIST_GENRES.items():
            if artist not in self._artist_genre_cache:
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
