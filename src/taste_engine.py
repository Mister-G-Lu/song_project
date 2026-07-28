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
from typing import List, Dict, Set
from src.genre_data import GENRE_KEYWORDS, CURATED_ARTIST_GENRES, PARSE_ARTIFACTS
from src.challenge_db import CHALLENGE_DB, GENRE_ALIAS_TO_CLASS
from src.backfill import LETTER_GRADE_MAP, extract_letter_grade, infer_tone_rating


class TasteEngine:
    def __init__(self, csv_path: str = "data/posts_tails.csv"):
        self.csv_path = csv_path
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
        self._build_artist_index()
        self._build_song_index()

    def _load_data(self):
        """Load and parse the CSV file."""
        with open(self.csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            self.rows = list(reader)

        self.rated_entries = [r for r in self.rows if r['rating']]
        self.ratings = [int(r['rating']) for r in self.rated_entries]

    def _extract_artists(self, title: str) -> List[str]:
        """Extract artist names from song title."""
        results = []
        # Pattern: Title (Artist, Year)
        m = re.search(r'\(([^)]+),\s*\d{4}\)', title)
        if m:
            artists_str = m.group(1)
            parts = re.split(r'\s+(?:ft\.|feat\.|featuring|and|&)\s+|\s*,\s*', artists_str)
            for p in parts:
                p = p.strip().strip('"').strip("'")
                if p and len(p) > 1 and p.lower() not in PARSE_ARTIFACTS:
                    results.append(p)
        # Pattern: Artist – Title (with en dash or hyphen)
        m = re.match(r'^([A-Za-z0-9][^–-]+?)\s*[–-]\s+', title)
        if m:
            artist = m.group(1).strip().rstrip(',').strip('"').strip("'")
            if artist and len(artist) > 1 and artist not in results and artist.lower() not in PARSE_ARTIFACTS:
                results.append(artist)
        return results

    def _build_artist_index(self):
        """Build artist-to-ratings mapping, pre-computing genre for each artist."""
        all_artists_info = defaultdict(lambda: {'ratings': [], 'count': 0, 'songs': [], 'genre_score': defaultdict(int)})

        for r in self.rows:
            artists = self._extract_artists(r['title'])
            rating = int(r['rating']) if r['rating'] else None
            combined = (r['tail'] + ' ' + r['title']).lower()
            
            for artist in artists:
                if rating:
                    all_artists_info[artist]['ratings'].append(rating)
                    all_artists_info[artist]['songs'].append({
                        'title': r['title'],
                        'rating': rating,
                        'date': r['date']
                    })
                all_artists_info[artist]['count'] += 1
                
                # Pre-compute genre score during the row iteration (avoids O(n^2) later)
                for genre, keywords in self.genre_keywords.items():
                    for kw in keywords:
                        if kw in combined:
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
        """Classify songs into genres based on review text and compute stats.
        Uses multi-tier fallback:
          1. Keyword match against review text + title
          2. _artist_genre_cache (populated by MusicBrainz)
          3. _CURATED_ARTIST_GENRES (170+ well-known artists)
          4. Uncategorized
        """
        genre_data = defaultdict(lambda: {'count': 0, 'ratings': [], 'songs': []})
        
        for r in self.rows:
            combined = (r['tail'] + ' ' + r['title']).lower()
            rating = int(r['rating']) if r['rating'] else None
            matched = False
            for genre, keywords in self.genre_keywords.items():
                for kw in keywords:
                    if kw in combined:
                        genre_data[genre]['count'] += 1
                        if rating:
                            genre_data[genre]['ratings'].append(rating)
                            genre_data[genre]['songs'].append({
                                'title': r['title'][:60],
                                'rating': rating
                            })
                        matched = True
                        break
                if matched:
                    break
            if not matched:
                # Fallback 2: Check artist genre cache (populated by MusicBrainz)
                cached = False
                if self._artist_genre_cache:
                    artists = self._extract_artists(r['title'])
                    for artist in artists:
                        if artist in self._artist_genre_cache:
                            cached_genre = self._artist_genre_cache[artist]
                            genre_data[cached_genre]['count'] += 1
                            if rating:
                                genre_data[cached_genre]['ratings'].append(rating)
                                genre_data[cached_genre]['songs'].append({
                                    'title': r['title'][:60],
                                    'rating': rating
                                })
                            cached = True
                            break
                # Fallback 3: Check curated artist-genre mapping (covers 170+ well-known artists)
                if not cached:
                    artists = self._extract_artists(r['title'])
                    for artist in artists:
                        if artist in CURATED_ARTIST_GENRES:
                            curated_genre = CURATED_ARTIST_GENRES[artist]
                            genre_data[curated_genre]['count'] += 1
                            if rating:
                                genre_data[curated_genre]['ratings'].append(rating)
                                genre_data[curated_genre]['songs'].append({
                                    'title': r['title'][:60],
                                    'rating': rating
                                })
                            cached = True
                            break
                if not cached:
                    genre_data['Uncategorized']['count'] += 1
                    if rating:
                        genre_data['Uncategorized']['ratings'].append(rating)

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
            tail_preview = r['tail'][:150].replace('\n', ' ')
            songs.append({
                'title': r['title'],
                'rating': int(r['rating']),
                'date': r['date'],
                'preview': tail_preview
            })
        return sorted(songs, key=lambda x: -x['rating'])[:limit]

    def _get_recent_reviews(self, limit: int = 10) -> List[Dict]:
        """Get most recent reviews."""
        recent = sorted(
            [r for r in self.rows if r['title'] != 'Announcement' and r['title']],
            key=lambda x: x['date'],
            reverse=True
        )[:limit]
        result = []
        for r in recent:
            tail_preview = r['tail'][:200].replace('\n', ' ')
            result.append({
                'title': r['title'][:80],
                'rating': int(r['rating']) if r['rating'] else None,
                'date': r['date'],
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

    def get_constellation(self) -> Dict:
        """Build artist similarity network for the constellation view.
        Uses a two-tier edge strategy:
          1. Collaboration edges — artists that appear together in songs
          2. Genre-similarity edges — artists sharing the same genre (ensures
             the graph isn't a sea of isolated dots)
        Genre is pre-computed during _build_artist_index for performance.
        """
        nodes = []
        edges = []
        artist_set = set()
        genre_artists = defaultdict(list)  # genre -> [artist, ...]

        # Build nodes from artists with ratings (genre is pre-cached)
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

        # Tier 1: Collaboration edges (artists appearing together in songs)
        seen_collab = set()
        for r in self.rows:
            artists = self._extract_artists(r['title'])
            for i in range(len(artists)):
                for j in range(i+1, len(artists)):
                    if artists[i] in artist_set and artists[j] in artist_set:
                        key = tuple(sorted([artists[i], artists[j]]))
                        if key not in seen_collab:
                            seen_collab.add(key)
                            edges.append({
                                'source': artists[i],
                                'target': artists[j],
                                'song': r['title'][:40]
                            })

        # Tier 2: Genre-similarity edges (connect artists within the same genre)
        # This ensures every node has at least some connections.
        seen_genre = set()
        for genre, artists in genre_artists.items():
            if len(artists) >= 2:
                # Connect each artist to up to 3 others in the same genre
                for i, artist in enumerate(artists):
                    for j in range(i + 1, min(i + 4, len(artists))):
                        if artist in artist_set and artists[j] in artist_set:
                            key = tuple(sorted([artist, artists[j]]))
                            if key not in seen_genre and key not in seen_collab:
                                seen_genre.add(key)
                                edges.append({
                                    'source': artist,
                                    'target': artists[j],
                                    'song': f"Same genre: {genre}"
                                })

        return {
            'nodes': nodes,
            'edges': edges
        }

    def get_evolution(self) -> Dict:
        """Track taste evolution over time."""
        # Group ratings by month
        monthly = defaultdict(list)
        for r in self.rated_entries:
            month_key = r['date'][:7]  # YYYY-MM
            monthly[month_key].append(int(r['rating']))

        monthly_avg = {}
        for month, ratings in sorted(monthly.items()):
            monthly_avg[month] = round(sum(ratings) / len(ratings), 1)

        # Genre evolution over time
        genre_monthly = defaultdict(lambda: defaultdict(list))
        for r in self.rows:
            if r['rating']:
                month_key = r['date'][:7]
                combined = (r['tail'] + ' ' + r['title']).lower()
                for genre, keywords in self.genre_keywords.items():
                    for kw in keywords:
                        if kw in combined:
                            genre_monthly[genre][month_key].append(int(r['rating']))
                            break
                    else:
                        continue
                    break

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
            year = r['date'][:4]
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
            if r['title'] and r['title'] != 'Announcement':
                if r['rating']:
                    count += 1
                    if count % 25 == 0 or count == 1:
                        cumulative.append({
                            'date': r['date'],
                            'total_songs': count
                        })

        return {
            'monthly_avg': monthly_avg,
            'yearly': yearly_avg,
            'genre_evolution': genre_evolution,
            'cumulative': cumulative
        }

    def check_recs(self, recs: List[Dict]) -> List[Dict]:
        """Tag each recommendation as already_owned True/False using the hash set."""
        checked = []
        for rec in recs:
            dup = self.check_song_exists(rec.get('artist', ''), rec.get('song', ''))
            checked.append({**rec, 'already_owned': dup['exists']})
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
                zone_note = f"Opposite-taste challenge: you rate most {class_genre} songs low, but this is widely acclaimed. Dare to try?"
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
            combined = (r['tail'] + ' ' + r['title']).lower()
            artists = self._extract_artists(r['title'])
            if not artists:
                continue
                
            matched_genre = None
            for genre, keywords in self.genre_keywords.items():
                for kw in keywords:
                    if kw in combined:
                        matched_genre = genre
                        break
                if matched_genre:
                    break
            
            # If keyword didn't match, try title-based heuristics
            if not matched_genre:
                title_lower = r['title'].lower()
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
            self._artist_genre_cache[artist] = genre
        
        # --- Strategy 2: Curated artist-genre mapping (manually verified) ---
        curated_applied = 0
        for artist, genre in CURATED_ARTIST_GENRES.items():
            if artist not in self._artist_genre_cache:
                self._artist_genre_cache[artist] = genre
                curated_applied += 1
        
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
                    if self._title_heuristic_classify(r['title']) == 'Uncategorized':
                        artists = self._extract_artists(r['title'])
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
                    combined = (r['tail'] + ' ' + r['title']).lower()
                    matched = False
                    for genre, keywords in self.genre_keywords.items():
                        for kw in keywords:
                            if kw in combined:
                                matched = True
                                break
                        if matched:
                            break
                    if not matched:
                        artists = self._extract_artists(r['title'])
                        for a in artists:
                            if a in wikidata_results:
                                wikidata_stats['reclassified'] += 1
                                break
            
            # Recalculate
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
                if not matched and self._title_heuristic_classify(r['title']) == 'Uncategorized':
                    artists = self._extract_artists(r['title'])
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
            
            # Recalculate
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
            if r['rating']:
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
                'title': r['title'][:80],
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
                writer.writerows(self.rows)

            # Reload engine state
            self._load_data()
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
