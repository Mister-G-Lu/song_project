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
                if p and len(p) > 1 and p.lower() not in self._PARSE_ARTIFACTS:
                    results.append(p)
        # Pattern: Artist – Title (with en dash or hyphen)
        m = re.match(r'^([A-Za-z0-9][^–-]+?)\s*[–-]\s+', title)
        if m:
            artist = m.group(1).strip().rstrip(',').strip('"').strip("'")
            if artist and len(artist) > 1 and artist not in results and artist.lower() not in self._PARSE_ARTIFACTS:
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
            elif artist in self._CURATED_ARTIST_GENRES:
                info['genre'] = self._CURATED_ARTIST_GENRES[artist]
            else:
                info['genre'] = 'Uncategorized'

        self.all_artists = dict(all_artists_info)

    def _init_genre_keywords(self):
        """Initialize genre keyword mapping for classification."""
        self.genre_keywords = {
            'Pop': ['pop', 'pop hit', 'pop song', 'mainstream pop', 'pop rock', 'pop punk',
                    'power pop', 'synth-pop', 'synth pop', 'dance pop', 'teen pop', 'bubblegum pop',
                    'electropop', 'folk-pop', 'art pop', 'dream pop', 'jangle pop'],
            'Rock': ['rock', 'rock song', 'alternative rock', 'punk rock', 'hard rock', 'soft rock',
                     'indie rock', 'classic rock', 'progressive rock', 'prog rock', 'art rock',
                     'garage rock', 'blues rock', 'southern rock', 'stoner rock', 'post-rock',
                     'post rock', 'math rock', 'psychedelic rock', 'psychedelic', 'emo', 'pop punk'],
            'Classical/Instrumental': ['classical', 'piano', 'orchestra', 'orchestral', 'instrumental',
                                       'violin', 'symphony', 'cello', 'harp', 'flute', 'trumpet',
                                       'chamber', 'opera', 'operatic', 'concerto', 'sonata', 'nocturne',
                                       'symphonic', 'baroque', 'choral', 'choir', 'string quartet'],
            'Electronic/Dance': ['electronic', 'dubstep', 'edm', 'synth', 'electronic dance', 'techno',
                                 'house', 'trance', 'drum and bass', 'drum & bass', 'drumstep',
                                 'idm', 'ambient', 'chillstep', 'electronica', 'glitch', 'glitch hop',
                                 'trap', 'future bass', 'moombah', 'big room', 'progressive house',
                                 'deep house', 'tropical house', 'hardstyle', 'dance', 'club',
                                 'rave', 'breakbeat', 'breakcore'],
            'J-Pop/Anime': ['j-pop', 'jpop', 'vocaloid', 'hatsune', 'anime', 'japanese', 'jp',
                            'j rock', 'j-rock', 'city pop', 'shibuya-kei', 'utaite',
                            'vocalo', 'kagamine', 'megurine', 'ia', 'yowane'],
            'K-Pop': ['k-pop', 'kpop', 'korean', 'k-dance', 'korean pop', 'korean dance'],
            'Jazz/Swing': ['jazz', 'swing', 'electro-swing', 'big band', 'bebop', 'cool jazz',
                           'fusion', 'latin jazz', 'bossa nova', 'bossa', 'ragtime', 'dixieland',
                           'swing revival', 'nu jazz', 'acid jazz', 'smooth jazz'],
            'Disco/Funk': ['disco', 'funk', 'groovy', 'groove', 'boogie', 'funk rock',
                           'p-funk', 'g-funk', 'nu-disco', 'disco house', 'funky'],
            'Indie/Alternative': ['indie', 'alternative indie', 'indie pop', 'indie rock',
                                   'alternative', 'alt rock', 'lo-fi', 'lo fi', 'lofi',
                                   'shoegaze', 'dream pop', 'noise pop', 'post-punk',
                                   'post punk', 'new wave', 'britpop', 'brit pop',
                                   'grunge', 'college rock'],
            'Metal': ['metal', 'heavy metal', 'symphonic metal', 'thrash metal', 'death metal',
                      'black metal', 'power metal', 'progressive metal', 'prog metal',
                      'doom metal', 'sludge metal', 'nu metal', 'metalcore', 'metal core',
                      'deathcore', 'djent', 'folk metal', 'gothic metal', 'glam metal',
                      'hair metal', 'speed metal'],
            'Rap/Hip-Hop': ['rap', 'hip hop', 'hip-hop', 'hiphop', 'trap', 'drill',
                            'gangsta rap', 'conscious rap', 'boom bap', 'old school hip hop',
                            'mumble rap', 'cloud rap', 'emo rap', 'southern rap',
                            'east coast', 'west coast', 'crunk', 'g-funk'],
            'Folk/Acoustic': ['folk', 'acoustic', 'singer-songwriter', 'singer songwriter',
                              'americana', 'bluegrass', 'country folk', 'indie folk',
                              'neofolk', 'traditional folk', 'folk rock', 'protest song',
                              'ballad', 'campfire', 'strumming', 'ukulele', 'mandolin', 'banjo'],
            'Eurovision': ['eurovision', 'euro vision', 'song contest'],
            'Christmas/Holiday': ['christmas', 'xmas', 'holiday', 'santa', 'jingle',
                                  'noel', 'winter wonderland', 'snow', 'silver bells'],
            'Soundtrack/Score': ['soundtrack', 'theme', 'score', 'ost', 'original soundtrack',
                                 'film score', 'movie theme', 'video game', 'game soundtrack',
                                 'title theme', 'ending theme', 'opening theme', 'insert song',
                                 'licensed', 'music from', 'as heard in'],
            'R&B/Soul': ['rnb', 'r&b', 'soul', 'motown', 'neo soul', 'neo-soul',
                         'new jack swing', 'quiet storm', 'rhythm and blues',
                         'contemporary r&b', 'blue eyed soul', 'philly soul', 'beach', 'doo wop'],
            'Country': ['country', 'country music', 'country pop', 'country rock',
                        'outlaw country', 'alt country', 'alt-country', 'red dirt',
                        'honky tonk', 'bluegrass', 'americana', 'cowboy', 'tennessee'],
            'A Cappella': ['a cappella', 'acapella', 'vocal only', 'vocal harmony',
                           'barbershop', 'choir', 'madrigal', 'vocal band'],
            'Latin': ['latin', 'reggaeton', 'salsa', 'merengue', 'bachata', 'cumbia',
                      'reggae', 'reggaeton', 'latin pop', 'latin rock', 'mambo',
                      'tango', 'flamenco', 'rumba', 'spanish language', 'en español'],
            'Punk': ['punk', 'punk rock', 'hardcore punk', 'pop punk', 'skate punk',
                     'anarcho punk', 'street punk', 'oi', 'post-hardcore',
                     'hardcore', 'screamo', 'crust', 'd-beat'],
            'Reggae/Dub': ['reggae', 'dub', 'ska', 'dancehall', 'reggaeton',
                           'roots reggae', 'lovers rock', 'rocksteady', 'two tone'],
            'Blues': ['blues', 'delta blues', 'chicago blues', 'electric blues',
                      'texas blues', 'jump blues', 'piedmont blues', 'bluegrass'],
        }

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
    LETTER_GRADE_MAP = {
        'A+': 98, 'A': 95, 'A-': 92,
        'B+': 88, 'B': 85, 'B-': 82,
        'C+': 78, 'C': 75, 'C-': 72,
        'D+': 68, 'D': 65, 'D-': 62,
        'F': 50,
    }


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
                        if artist in self._CURATED_ARTIST_GENRES:
                            curated_genre = self._CURATED_ARTIST_GENRES[artist]
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
        """Curated database of critically acclaimed / widely-loved songs
        across diverse genres. Sources: RateYourMusic top charts,
        Rolling Stone 500, Pitchfork, Grammy winners, cultural impact.
        Expanded to 200+ entries across 20+ genres and 4 tiers
        with opposite-taste targeting for maximum challenge diversity.
        """
        return [
            {'artist': "Queen", 'song': "Bohemian Rhapsody", 'genre': "Classic Rock", 'year': 1975, 'acclaim': "RS 500, 1B+ streams, genre-defying masterpiece", 'tier': "legendary", 'listen_score': 99},
            {'artist': "Led Zeppelin", 'song': "Stairway to Heaven", 'genre': "Classic Rock", 'year': 1971, 'acclaim': "Widely considered the greatest rock song ever", 'tier': "legendary", 'listen_score': 99},
            {'artist': "Pink Floyd", 'song': "Comfortably Numb", 'genre': "Progressive Rock", 'year': 1979, 'acclaim': "RS 500, iconic guitar solos, masterpiece", 'tier': "legendary", 'listen_score': 98},
            {'artist': "The Beatles", 'song': "A Day in the Life", 'genre': "Classic Rock", 'year': 1967, 'acclaim': "Often ranked #1 song of all time", 'tier': "legendary", 'listen_score': 99},
            {'artist': "The Rolling Stones", 'song': "Gimme Shelter", 'genre': "Classic Rock", 'year': 1969, 'acclaim': "RS 500, one of the greatest rock songs", 'tier': "legendary", 'listen_score': 98},
            {'artist': "The Who", 'song': "Baba O'Riley", 'genre': "Classic Rock", 'year': 1971, 'acclaim': "RS 500, iconic rock anthem", 'tier': "legendary", 'listen_score': 97},
            {'artist': "Bruce Springsteen", 'song': "Born to Run", 'genre': "Classic Rock", 'year': 1975, 'acclaim': "RS 500, the ultimate rock anthem", 'tier': "legendary", 'listen_score': 98},
            {'artist': "The Doors", 'song': "Riders on the Storm", 'genre': "Classic Rock", 'year': 1971, 'acclaim': "RS 500, haunting masterpiece", 'tier': "legendary", 'listen_score': 96},
            {'artist': "Jimi Hendrix", 'song': "All Along the Watchtower", 'genre': "Classic Rock", 'year': 1968, 'acclaim': "RS 500, greatest cover of all time", 'tier': "legendary", 'listen_score': 98},
            {'artist': "The Eagles", 'song': "Hotel California", 'genre': "Classic Rock", 'year': 1977, 'acclaim': "1B+ streams, iconic guitar solos", 'tier': "legendary", 'listen_score': 97},
            {'artist': "AC/DC", 'song': "Back in Black", 'genre': "Classic Rock", 'year': 1980, 'acclaim': "One of the best-selling songs ever", 'tier': "legendary", 'listen_score': 97},
            {'artist': "Dire Straits", 'song': "Sultans of Swing", 'genre': "Classic Rock", 'year': 1978, 'acclaim': "RS 500, masterful guitar work", 'tier': "legendary", 'listen_score': 96},
            {'artist': "U2", 'song': "With or Without You", 'genre': "Classic Rock", 'year': 1987, 'acclaim': "RS 500, iconic anthem", 'tier': "legendary", 'listen_score': 97},
            {'artist': "Fleetwood Mac", 'song': "Dreams", 'genre': "Classic Rock", 'year': 1977, 'acclaim': "1B+ streams, iconic production", 'tier': "classic", 'listen_score': 97},
            {'artist': "Kendrick Lamar", 'song': "Alright", 'genre': "Hip-Hop", 'year': 2015, 'acclaim': "Grammy winner, cultural anthem, 1B+ streams", 'tier': "modern_classic", 'listen_score': 98},
            {'artist': "Notorious B.I.G.", 'song': "Juicy", 'genre': "Hip-Hop", 'year': 1994, 'acclaim': "RS 500, greatest hip-hop song of all time", 'tier': "legendary", 'listen_score': 98},
            {'artist': "Tupac", 'song': "Changes", 'genre': "Hip-Hop", 'year': 1998, 'acclaim': "Cultural anthem, iconic message", 'tier': "legendary", 'listen_score': 97},
            {'artist': "Outkast", 'song': "Hey Ya!", 'genre': "Hip-Hop", 'year': 2003, 'acclaim': "Grammy winner, genre-blending masterpiece", 'tier': "modern_classic", 'listen_score': 96},
            {'artist': "Lauryn Hill", 'song': "Doo Wop (That Thing)", 'genre': "Hip-Hop/R&B", 'year': 1998, 'acclaim': "Grammy winner, RS 500", 'tier': "modern_classic", 'listen_score': 97},
            {'artist': "Nas", 'song': "N.Y. State of Mind", 'genre': "Hip-Hop", 'year': 1994, 'acclaim': "RS 500, lyrical masterpiece", 'tier': "legendary", 'listen_score': 97},
            {'artist': "Wu-Tang Clan", 'song': "C.R.E.A.M.", 'genre': "Hip-Hop", 'year': 1993, 'acclaim': "RS 500, iconic hip-hop track", 'tier': "legendary", 'listen_score': 97},
            {'artist': "A Tribe Called Quest", 'song': "Can I Kick It?", 'genre': "Hip-Hop", 'year': 1990, 'acclaim': "RS 500, jazz-rap masterpiece", 'tier': "legendary", 'listen_score': 95},
            {'artist': "Dr. Dre", 'song': "Still D.R.E.", 'genre': "Hip-Hop", 'year': 1999, 'acclaim': "Iconic West Coast hip-hop anthem", 'tier': "legendary", 'listen_score': 96},
            {'artist': "Jay-Z", 'song': "99 Problems", 'genre': "Hip-Hop", 'year': 2003, 'acclaim': "Grammy winner, iconic", 'tier': "modern_classic", 'listen_score': 96},
            {'artist': "Kanye West", 'song': "Runaway", 'genre': "Hip-Hop", 'year': 2010, 'acclaim': "Critically acclaimed masterpiece", 'tier': "modern_classic", 'listen_score': 97},
            {'artist': "MF DOOM", 'song': "Rapp Snitch Knishes", 'genre': "Hip-Hop", 'year': 2004, 'acclaim': "Cult classic, underground legend", 'tier': "cult", 'listen_score': 95},
            {'artist': "Missy Elliott", 'song': "Get Ur Freak On", 'genre': "Hip-Hop/R&B", 'year': 2001, 'acclaim': "Grammy winner, groundbreaking", 'tier': "modern_classic", 'listen_score': 96},
            {'artist': "Daft Punk", 'song': "One More Time", 'genre': "Electronic", 'year': 2000, 'acclaim': "1B+ streams, defined a generation of dance music", 'tier': "modern_classic", 'listen_score': 98},
            {'artist': "Aphex Twin", 'song': "Windowlicker", 'genre': "Electronic/IDM", 'year': 1999, 'acclaim': "Groundbreaking electronic, RS 500", 'tier': "cult", 'listen_score': 95},
            {'artist': "Massive Attack", 'song': "Teardrop", 'genre': "Trip-Hop", 'year': 1998, 'acclaim': "Defined trip-hop, iconic", 'tier': "modern_classic", 'listen_score': 97},
            {'artist': "Boards of Canada", 'song': "Roygbiv", 'genre': "Electronic/Ambient", 'year': 1998, 'acclaim': "Influential ambient electronic masterpiece", 'tier': "cult", 'listen_score': 94},
            {'artist': "Kraftwerk", 'song': "The Model", 'genre': "Electronic", 'year': 1978, 'acclaim': "Pioneered electronic music, hugely influential", 'tier': "legendary", 'listen_score': 96},
            {'artist': "Burial", 'song': "Archangel", 'genre': "Electronic", 'year': 2007, 'acclaim': "Defined a decade of UK electronic music", 'tier': "cult", 'listen_score': 97},
            {'artist': "Flying Lotus", 'song': "Never Catch Me", 'genre': "Electronic/Jazz", 'year': 2014, 'acclaim': "Genre-defying electronic masterpiece", 'tier': "cult", 'listen_score': 95},
            {'artist': "Jon Hopkins", 'song': "Immunity", 'genre': "Electronic", 'year': 2013, 'acclaim': "Modern electronic masterpiece", 'tier': "cult", 'listen_score': 96},
            {'artist': "Caribou", 'song': "Can't Do Without You", 'genre': "Electronic", 'year': 2014, 'acclaim': "Critically adored electronic pop", 'tier': "cult", 'listen_score': 95},
            {'artist': "Bonobo", 'song': "Kerala", 'genre': "Electronic", 'year': 2017, 'acclaim': "Modern electronic classic", 'tier': "cult", 'listen_score': 94},
            {'artist': "Four Tet", 'song': "Love Cry", 'genre': "Electronic", 'year': 2010, 'acclaim': "Influential electronic masterpiece", 'tier': "cult", 'listen_score': 95},
            {'artist': "The Chemical Brothers", 'song': "Hey Boy Hey Girl", 'genre': "Electronic/Dance", 'year': 1999, 'acclaim': "RS 500, iconic dance anthem", 'tier': "cult", 'listen_score': 96},
            {'artist': "Fatboy Slim", 'song': "Right Here, Right Now", 'genre': "Electronic/Dance", 'year': 1998, 'acclaim': "Iconic dance track, cultural touchstone", 'tier': "cult", 'listen_score': 95},
            {'artist': "Justice", 'song': "D.A.N.C.E.", 'genre': "Electronic/House", 'year': 2007, 'acclaim': "Grammy winner, modern dance classic", 'tier': "cult", 'listen_score': 96},
            {'artist': "Thom Yorke", 'song': "Hearing Damage", 'genre': "Electronic", 'year': 2009, 'acclaim': "Haunting electronic masterpiece", 'tier': "cult", 'listen_score': 95},
            {'artist': "Miles Davis", 'song': "So What", 'genre': "Jazz", 'year': 1959, 'acclaim': "Greatest jazz album of all time (Kind of Blue)", 'tier': "legendary", 'listen_score': 99},
            {'artist': "John Coltrane", 'song': "My Favorite Things", 'genre': "Jazz", 'year': 1961, 'acclaim': "Revolutionary jazz, masterpiece", 'tier': "legendary", 'listen_score': 98},
            {'artist': "Aretha Franklin", 'song': "Respect", 'genre': "Soul", 'year': 1967, 'acclaim': "Cultural anthem, RS 500 #1", 'tier': "legendary", 'listen_score': 99},
            {'artist': "Stevie Wonder", 'song': "Superstition", 'genre': "Funk/Soul", 'year': 1972, 'acclaim': "1B+ streams, iconic funk", 'tier': "legendary", 'listen_score': 98},
            {'artist': "Marvin Gaye", 'song': "What's Going On", 'genre': "Soul", 'year': 1971, 'acclaim': "RS 500 #1, cultural milestone", 'tier': "legendary", 'listen_score': 99},
            {'artist': "Nina Simone", 'song': "Feeling Good", 'genre': "Jazz/Soul", 'year': 1965, 'acclaim': "Iconic, 1B+ streams, timeless", 'tier': "legendary", 'listen_score': 98},
            {'artist': "James Brown", 'song': "I Got You (I Feel Good)", 'genre': "Funk", 'year': 1965, 'acclaim': "Godfather of Soul, iconic", 'tier': "legendary", 'listen_score': 97},
            {'artist': "Ray Charles", 'song': "Georgia on My Mind", 'genre': "Soul", 'year': 1960, 'acclaim': "RS 500, timeless classic", 'tier': "legendary", 'listen_score': 97},
            {'artist': "Etta James", 'song': "At Last", 'genre': "Soul", 'year': 1960, 'acclaim': "Timeless classic, iconic", 'tier': "legendary", 'listen_score': 97},
            {'artist': "Charles Mingus", 'song': "Moanin'", 'genre': "Jazz", 'year': 1959, 'acclaim': "Jazz masterpiece", 'tier': "legendary", 'listen_score': 96},
            {'artist': "Herbie Hancock", 'song': "Chameleon", 'genre': "Jazz/Funk", 'year': 1973, 'acclaim': "Jazz-funk masterpiece", 'tier': "legendary", 'listen_score': 96},
            {'artist': "Earth, Wind and Fire", 'song': "September", 'genre': "Funk", 'year': 1978, 'acclaim': "1B+ streams, timeless funk party anthem", 'tier': "legendary", 'listen_score': 98},
            {'artist': "Radiohead", 'song': "Paranoid Android", 'genre': "Alternative Rock", 'year': 1997, 'acclaim': "RS 500, one of the most acclaimed alt songs", 'tier': "modern_classic", 'listen_score': 98},
            {'artist': "Arcade Fire", 'song': "Wake Up", 'genre': "Indie Rock", 'year': 2004, 'acclaim': "Grammy winner, anthem of a generation", 'tier': "modern_classic", 'listen_score': 97},
            {'artist': "LCD Soundsystem", 'song': "All My Friends", 'genre': "Indie/Electronic", 'year': 2007, 'acclaim': "Pitchfork #1, critically adored", 'tier': "cult", 'listen_score': 96},
            {'artist': "Neutral Milk Hotel", 'song': "In the Aeroplane Over the Sea", 'genre': "Indie Folk", 'year': 1998, 'acclaim': "Cult classic, one of the most beloved indie albums", 'tier': "cult", 'listen_score': 97},
            {'artist': "Sufjan Stevens", 'song': "Casimir Pulaski Day", 'genre': "Indie Folk", 'year': 2005, 'acclaim': "Universally beloved indie masterpiece", 'tier': "modern_classic", 'listen_score': 96},
            {'artist': "Talking Heads", 'song': "Once in a Lifetime", 'genre': "New Wave/Art Rock", 'year': 1980, 'acclaim': "RS 500, unique and influential", 'tier': "legendary", 'listen_score': 97},
            {'artist': "Modest Mouse", 'song': "Float On", 'genre': "Indie Rock", 'year': 2004, 'acclaim': "Indie anthem, universally loved", 'tier': "modern_classic", 'listen_score': 95},
            {'artist': "The Strokes", 'song': "Reptilia", 'genre': "Indie Rock", 'year': 2003, 'acclaim': "RS 500, indie rock anthem", 'tier': "modern_classic", 'listen_score': 96},
            {'artist': "Bon Iver", 'song': "Holocene", 'genre': "Indie Folk", 'year': 2011, 'acclaim': "Grammy winner, breathtaking", 'tier': "modern_classic", 'listen_score': 97},
            {'artist': "Vampire Weekend", 'song': "Oxford Comma", 'genre': "Indie Pop", 'year': 2008, 'acclaim': "Quirky indie classic", 'tier': "modern_classic", 'listen_score': 94},
            {'artist': "The Smiths", 'song': "There Is a Light That Never Goes Out", 'genre': "Indie Rock", 'year': 1986, 'acclaim': "RS 500, indie masterpiece", 'tier': "legendary", 'listen_score': 98},
            {'artist': "Pixies", 'song': "Where Is My Mind?", 'genre': "Alternative Rock", 'year': 1988, 'acclaim': "RS 500, hugely influential", 'tier': "legendary", 'listen_score': 97},
            {'artist': "Frank Ocean", 'song': "Nights", 'genre': "R&B", 'year': 2016, 'acclaim': "Genre-defining, critically acclaimed modern classic", 'tier': "modern_classic", 'listen_score': 97},
            {'artist': "D'Angelo", 'song': "Untitled (How Does It Feel)", 'genre': "Neo-Soul", 'year': 2000, 'acclaim': "Grammy winner, neo-soul masterpiece", 'tier': "modern_classic", 'listen_score': 96},
            {'artist': "Erykah Badu", 'song': "Didn't Cha Know", 'genre': "Neo-Soul", 'year': 2000, 'acclaim': "Neo-soul classic, influential", 'tier': "modern_classic", 'listen_score': 95},
            {'artist': "Sade", 'song': "Smooth Operator", 'genre': "R&B/Soul", 'year': 1984, 'acclaim': "Timeless classic, iconic", 'tier': "classic", 'listen_score': 96},
            {'artist': "Solange", 'song': "Cranes in the Sky", 'genre': "R&B", 'year': 2016, 'acclaim': "Grammy winner, modern R&B masterpiece", 'tier': "modern_classic", 'listen_score': 96},
            {'artist': "Anderson .Paak", 'song': "Come Down", 'genre': "R&B/Funk", 'year': 2016, 'acclaim': "Modern funk-soul masterpiece", 'tier': "modern_classic", 'listen_score': 95},
            {'artist': "Jill Scott", 'song': "Golden", 'genre': "Neo-Soul", 'year': 2000, 'acclaim': "Neo-soul classic, beloved", 'tier': "modern_classic", 'listen_score': 95},
            {'artist': "Maxwell", 'song': "Pretty Wings", 'genre': "Neo-Soul", 'year': 2009, 'acclaim': "Grammy winner, modern soul masterpiece", 'tier': "modern_classic", 'listen_score': 95},
            {'artist': "Al Green", 'song': "Let's Stay Together", 'genre': "Soul", 'year': 1971, 'acclaim': "RS 500, timeless soul classic", 'tier': "legendary", 'listen_score': 98},
            {'artist': "Fela Kuti", 'song': "Water No Get Enemy", 'genre': "Afrobeat", 'year': 1975, 'acclaim': "Afrobeat legend, hugely influential", 'tier': "legendary", 'listen_score': 97},
            {'artist': "Buena Vista Social Club", 'song': "Chan Chan", 'genre': "Cuban Son", 'year': 1997, 'acclaim': "Grammy winner, revived Cuban music globally", 'tier': "modern_classic", 'listen_score': 96},
            {'artist': "Ravi Shankar", 'song': "Raga Jog", 'genre': "Indian Classical", 'year': 1960, 'acclaim': "Introduced Indian classical to the West", 'tier': "legendary", 'listen_score': 95},
            {'artist': "Nusrat Fateh Ali Khan", 'song': "Allah Hoo", 'genre': "Qawwali", 'year': 1990, 'acclaim': "Legendary Qawwali singer, transcendent", 'tier': "legendary", 'listen_score': 98},
            {'artist': "Youssou N'Dour", 'song': "7 Seconds", 'genre': "Afropop", 'year': 1994, 'acclaim': "Introduced African pop to the world", 'tier': "legendary", 'listen_score': 96},
            {'artist': "Ali Farka Tour\u00e9", 'song': "Ai Du", 'genre': "Malian Blues", 'year': 1992, 'acclaim': "African blues legend, Grammy winner", 'tier': "legendary", 'listen_score': 95},
            {'artist': "Salif Keita", 'song': "Soro", 'genre': "Afropop", 'year': 1987, 'acclaim': "Golden voice of Africa, legendary", 'tier': "legendary", 'listen_score': 95},
            {'artist': "Seu Jorge", 'song': "Life on Mars?", 'genre': "Brazilian", 'year': 2004, 'acclaim': "Stunning Portuguese Bowie cover from The Life Aquatic", 'tier': "cult", 'listen_score': 96},
            {'artist': "Tinariwen", 'song': "Amassakoul", 'genre': "Tuareg Blues", 'year': 2002, 'acclaim': "Desert blues, Grammy winner", 'tier': "cult", 'listen_score': 94},
            {'artist': "Mulatu Astatke", 'song': "Y\u00e8gell\u00e9 Tezeta", 'genre': "Ethio-Jazz", 'year': 1974, 'acclaim': "Father of Ethio-jazz, unique masterpiece", 'tier': "cult", 'listen_score': 95},
            {'artist': "Ces\u00e1ria \u00c9vora", 'song': "Sodade", 'genre': "Cape Verdean Morna", 'year': 1992, 'acclaim': "Grammy winner, iconic voice", 'tier': "cult", 'listen_score': 95},
            {'artist': "The Ramones", 'song': "Blitzkrieg Bop", 'genre': "Punk", 'year': 1976, 'acclaim': "Punk anthem, RS 500", 'tier': "legendary", 'listen_score': 96},
            {'artist': "Joy Division", 'song': "Love Will Tear Us Apart", 'genre': "Post-Punk", 'year': 1980, 'acclaim': "Post-punk masterpiece, RS 500", 'tier': "legendary", 'listen_score': 98},
            {'artist': "The Clash", 'song': "London Calling", 'genre': "Punk", 'year': 1979, 'acclaim': "RS 500, genre-blending punk masterpiece", 'tier': "legendary", 'listen_score': 98},
            {'artist': "Sex Pistols", 'song': "God Save the Queen", 'genre': "Punk", 'year': 1977, 'acclaim': "Defining punk anthem, cultural shockwave", 'tier': "legendary", 'listen_score': 96},
            {'artist': "Dead Kennedys", 'song': "Holiday in Cambodia", 'genre': "Hardcore Punk", 'year': 1980, 'acclaim': "Punk masterpiece, politically charged", 'tier': "legendary", 'listen_score': 96},
            {'artist': "The Cure", 'song': "Pictures of You", 'genre': "Post-Punk", 'year': 1989, 'acclaim': "Post-punk masterpiece", 'tier': "legendary", 'listen_score': 97},
            {'artist': "Kate Bush", 'song': "Running Up That Hill", 'genre': "Art Pop", 'year': 1985, 'acclaim': "1B+ streams (Stranger Things revival), iconic", 'tier': "legendary", 'listen_score': 97},
            {'artist': "David Bowie", 'song': "Heroes", 'genre': "Art Rock", 'year': 1977, 'acclaim': "RS 500, one of the greatest songs ever", 'tier': "legendary", 'listen_score': 99},
            {'artist': "Bj\u00f6rk", 'song': "Hyperballad", 'genre': "Art Pop", 'year': 1995, 'acclaim': "Avant-garde pop masterpiece", 'tier': "modern_classic", 'listen_score': 97},
            {'artist': "Fiona Apple", 'song': "Paper Bag", 'genre': "Art Pop", 'year': 1999, 'acclaim': "Critically adored singer-songwriter masterpiece", 'tier': "modern_classic", 'listen_score': 95},
            {'artist': "Tori Amos", 'song': "Silent All These Years", 'genre': "Singer-Songwriter", 'year': 1991, 'acclaim': "Debut single, iconic feminist anthem", 'tier': "modern_classic", 'listen_score': 95},
            {'artist': "Prince", 'song': "Purple Rain", 'genre': "Pop/Rock", 'year': 1984, 'acclaim': "RS 500, iconic masterpiece", 'tier': "legendary", 'listen_score': 99},
            {'artist': "ABBA", 'song': "Dancing Queen", 'genre': "Pop", 'year': 1976, 'acclaim': "RS 500, timeless pop perfection", 'tier': "legendary", 'listen_score': 97},
            {'artist': "Cyndi Lauper", 'song': "Time After Time", 'genre': "Pop", 'year': 1983, 'acclaim': "RS 500, iconic 80s ballad", 'tier': "classic", 'listen_score': 96},
            {'artist': "Tears for Fears", 'song': "Everybody Wants to Rule the World", 'genre': "Pop", 'year': 1985, 'acclaim': "1B+ streams, 80s pop perfection", 'tier': "classic", 'listen_score': 96},
            {'artist': "George Michael", 'song': "Careless Whisper", 'genre': "Pop", 'year': 1984, 'acclaim': "1B+ streams, iconic sax riff", 'tier': "classic", 'listen_score': 96},
            {'artist': "Whitney Houston", 'song': "I Wanna Dance with Somebody", 'genre': "Pop", 'year': 1987, 'acclaim': "Pop perfection, iconic", 'tier': "classic", 'listen_score': 95},
            {'artist': "Metallica", 'song': "One", 'genre': "Metal", 'year': 1988, 'acclaim': "Grammy winner, thrash metal masterpiece", 'tier': "legendary", 'listen_score': 97},
            {'artist': "Black Sabbath", 'song': "Paranoid", 'genre': "Metal", 'year': 1970, 'acclaim': "Created heavy metal, RS 500", 'tier': "legendary", 'listen_score': 98},
            {'artist': "Tool", 'song': "Schism", 'genre': "Progressive Metal", 'year': 2001, 'acclaim': "Grammy winner, complex masterpiece", 'tier': "modern_classic", 'listen_score': 96},
            {'artist': "Opeth", 'song': "Harlequin Forest", 'genre': "Progressive Death Metal", 'year': 2005, 'acclaim': "Prog metal masterpiece, critically acclaimed", 'tier': "cult", 'listen_score': 96},
            {'artist': "Iron Maiden", 'song': "The Trooper", 'genre': "Heavy Metal", 'year': 1983, 'acclaim': "Metal anthem, iconic", 'tier': "legendary", 'listen_score': 97},
            {'artist': "Slayer", 'song': "Raining Blood", 'genre': "Thrash Metal", 'year': 1986, 'acclaim': "Thrash metal masterpiece", 'tier': "legendary", 'listen_score': 96},
            {'artist': "Mastodon", 'song': "Blood and Thunder", 'genre': "Progressive Metal", 'year': 2004, 'acclaim': "Modern metal masterpiece", 'tier': "cult", 'listen_score': 95},
            {'artist': "Gojira", 'song': "Flying Whales", 'genre': "Progressive Metal", 'year': 2005, 'acclaim': "Modern metal classic", 'tier': "cult", 'listen_score': 95},
            {'artist': "Bob Dylan", 'song': "Like a Rolling Stone", 'genre': "Folk Rock", 'year': 1965, 'acclaim': "RS 500 #1, changed songwriting forever", 'tier': "legendary", 'listen_score': 99},
            {'artist': "Joni Mitchell", 'song': "A Case of You", 'genre': "Folk", 'year': 1971, 'acclaim': "RS 500, one of the greatest songs ever written", 'tier': "legendary", 'listen_score': 98},
            {'artist': "Johnny Cash", 'song': "Hurt", 'genre': "Country/Folk", 'year': 2002, 'acclaim': "Grammy winner, most iconic cover of all time", 'tier': "legendary", 'listen_score': 98},
            {'artist': "Simon & Garfunkel", 'song': "Bridge Over Troubled Water", 'genre': "Folk Rock", 'year': 1970, 'acclaim': "Grammy winner, RS 500", 'tier': "legendary", 'listen_score': 97},
            {'artist': "Leonard Cohen", 'song': "Hallelujah", 'genre': "Folk", 'year': 1984, 'acclaim': "RS 500, one of the most covered songs ever", 'tier': "legendary", 'listen_score': 98},
            {'artist': "Nick Drake", 'song': "Pink Moon", 'genre': "Folk", 'year': 1972, 'acclaim': "Cult classic, deeply beloved", 'tier': "cult", 'listen_score': 97},
            {'artist': "Dolly Parton", 'song': "Jolene", 'genre': "Country", 'year': 1973, 'acclaim': "RS 500, iconic country classic", 'tier': "legendary", 'listen_score': 97},
            {'artist': "John Prine", 'song': "Angel from Montgomery", 'genre': "Folk/Americana", 'year': 1971, 'acclaim': "RS 500, beloved folk masterpiece", 'tier': "legendary", 'listen_score': 97},
            {'artist': "Townes Van Zandt", 'song': "Pancho and Lefty", 'genre': "Folk/Americana", 'year': 1972, 'acclaim': "Songwriting masterpiece", 'tier': "legendary", 'listen_score': 96},
            {'artist': "Gillian Welch", 'song': "Look at Miss Ohio", 'genre': "Folk/Americana", 'year': 2003, 'acclaim': "Modern folk masterpiece", 'tier': "cult", 'listen_score': 95},
            {'artist': "The Carter Family", 'song': "Wildwood Flower", 'genre': "Country/Folk", 'year': 1928, 'acclaim': "Pioneers of country music, legendary", 'tier': "legendary", 'listen_score': 93},
            {'artist': "Bob Marley", 'song': "Redemption Song", 'genre': "Reggae", 'year': 1980, 'acclaim': "One of the greatest songs, legendary", 'tier': "legendary", 'listen_score': 98},
            {'artist': "Lee 'Scratch' Perry", 'song': "Roast Fish & Cornbread", 'genre': "Dub/Reggae", 'year': 1978, 'acclaim': "Dub pioneer, hugely influential", 'tier': "cult", 'listen_score': 95},
            {'artist': "Peter Tosh", 'song': "Legalize It", 'genre': "Reggae", 'year': 1976, 'acclaim': "Reggae classic, iconic message", 'tier': "legendary", 'listen_score': 96},
            {'artist': "Toots and the Maytals", 'song': "Pressure Drop", 'genre': "Reggae", 'year': 1969, 'acclaim': "Reggae classic, hugely influential", 'tier': "legendary", 'listen_score': 96},
            {'artist': "Burning Spear", 'song': "Marcus Garvey", 'genre': "Reggae", 'year': 1975, 'acclaim': "Roots reggae masterpiece", 'tier': "legendary", 'listen_score': 95},
            {'artist': "Desmond Dekker", 'song': "Israelites", 'genre': "Ska/Reggae", 'year': 1968, 'acclaim': "First reggae song to hit #1 in UK", 'tier': "legendary", 'listen_score': 95},
            {'artist': "Jimmy Cliff", 'song': "Many Rivers to Cross", 'genre': "Reggae", 'year': 1969, 'acclaim': "RS 500, soulful reggae masterpiece", 'tier': "legendary", 'listen_score': 96},
            {'artist': "Celia Cruz", 'song': "La Vida Es Un Carnaval", 'genre': "Salsa", 'year': 1997, 'acclaim': "Queen of Salsa, cultural icon", 'tier': "legendary", 'listen_score': 97},
            {'artist': "Caetano Veloso", 'song': "Tropic\u00e1lia", 'genre': "Brazilian Tropicalia", 'year': 1968, 'acclaim': "Founded Tropicalia movement, legendary", 'tier': "legendary", 'listen_score': 96},
            {'artist': "Rosal\u00eda", 'song': "Malamente", 'genre': "Flamenco Pop", 'year': 2018, 'acclaim': "Grammy winner, revolutionized flamenco", 'tier': "modern_classic", 'listen_score': 96},
            {'artist': "Bad Bunny", 'song': "Tit\u00ed Me Pregunt\u00f3", 'genre': "Reggaeton", 'year': 2022, 'acclaim': "Most streamed artist globally, cultural phenomenon", 'tier': "modern_classic", 'listen_score': 95},
            {'artist': "Shakira", 'song': "Ojos As\u00ed", 'genre': "Latin Pop", 'year': 1998, 'acclaim': "Iconic Latin crossover, Grammy winner", 'tier': "classic", 'listen_score': 96},
            {'artist': "Ricky Martin", 'song': "Mar\u00eda", 'genre': "Latin Pop", 'year': 1995, 'acclaim': "Latin pop explosion, worldwide hit", 'tier': "classic", 'listen_score': 95},
            {'artist': "Man\u00e1", 'song': "Rayando el Sol", 'genre': "Latin Rock", 'year': 1990, 'acclaim': "Biggest Latin rock band ever", 'tier': "classic", 'listen_score': 95},
            {'artist': "Carlos Santana", 'song': "Smooth", 'genre': "Latin Rock", 'year': 1999, 'acclaim': "Grammy winner, most iconic Latin rock song", 'tier': "modern_classic", 'listen_score': 97},
            {'artist': "Luis Fonsi", 'song': "Despacito", 'genre': "Latin Pop", 'year': 2017, 'acclaim': "Most streamed song ever, cultural phenomenon", 'tier': "modern_classic", 'listen_score': 94},
            {'artist': "Hans Zimmer", 'song': "Time (Inception)", 'genre': "Film Score", 'year': 2010, 'acclaim': "1B+ streams, one of the most iconic modern scores", 'tier': "modern_classic", 'listen_score': 98},
            {'artist': "Ennio Morricone", 'song': "The Ecstasy of Gold", 'genre': "Film Score", 'year': 1966, 'acclaim': "One of the greatest film compositions ever", 'tier': "legendary", 'listen_score': 98},
            {'artist': "Joe Hisaishi", 'song': "Merry-Go-Round of Life", 'genre': "Film Score", 'year': 2004, 'acclaim': "Studio Ghibli, universally beloved", 'tier': "modern_classic", 'listen_score': 97},
            {'artist': "John Williams", 'song': "The Imperial March", 'genre': "Film Score", 'year': 1980, 'acclaim': "Most iconic film theme ever", 'tier': "legendary", 'listen_score': 97},
            {'artist': "Vangelis", 'song': "Blade Runner Blues", 'genre': "Film Score", 'year': 1982, 'acclaim': "Sci-fi soundtrack masterpiece", 'tier': "modern_classic", 'listen_score': 96},
            {'artist': "Clint Mansell", 'song': "Lux Aeterna", 'genre': "Film Score", 'year': 2000, 'acclaim': "Modern classical, widely used in media", 'tier': "modern_classic", 'listen_score': 96},
            {'artist': "Yoko Kanno", 'song': "Tank!", 'genre': "Anime Score", 'year': 1998, 'acclaim': "Cowboy Bebop, iconic jazz anime score", 'tier': "cult", 'listen_score': 97},
            {'artist': "Adele", 'song': "Someone Like You", 'genre': "Pop", 'year': 2011, 'acclaim': "1B+ streams, Grammy winner, cultural phenomenon", 'tier': "modern_classic", 'listen_score': 97},
            {'artist': "Amy Winehouse", 'song': "Back to Black", 'genre': "Soul/Pop", 'year': 2006, 'acclaim': "Grammy winner, RS 500, modern classic", 'tier': "modern_classic", 'listen_score': 97},
            {'artist': "Lana Del Rey", 'song': "Video Games", 'genre': "Indie Pop", 'year': 2011, 'acclaim': "Critically acclaimed, defined a sound", 'tier': "modern_classic", 'listen_score': 96},
            {'artist': "Billie Eilish", 'song': "Everything I Wanted", 'genre': "Pop", 'year': 2019, 'acclaim': "Grammy winner, modern masterpiece", 'tier': "modern_classic", 'listen_score': 96},
            {'artist': "Lorde", 'song': "Royals", 'genre': "Art Pop", 'year': 2013, 'acclaim': "Grammy winner, changed pop music", 'tier': "modern_classic", 'listen_score': 95},
            {'artist': "Olivia Rodrigo", 'song': "deja vu", 'genre': "Pop", 'year': 2021, 'acclaim': "Grammy winner, songwriting phenomenon", 'tier': "modern_classic", 'listen_score': 94},
            {'artist': "Tyler, The Creator", 'song': "EARFQUAKE", 'genre': "Pop/Rap", 'year': 2019, 'acclaim': "Genre-bending, critically adored", 'tier': "modern_classic", 'listen_score': 96},
            {'artist': "Childish Gambino", 'song': "Redbone", 'genre': "Funk/R&B", 'year': 2016, 'acclaim': "RS 500, modern funk classic", 'tier': "modern_classic", 'listen_score': 96},
            {'artist': "Mitski", 'song': "Nobody", 'genre': "Indie Pop", 'year': 2018, 'acclaim': "Critically adored indie pop", 'tier': "modern_classic", 'listen_score': 95},
            {'artist': "Phoebe Bridgers", 'song': "Motion Sickness", 'genre': "Indie Folk", 'year': 2017, 'acclaim': "Grammy-nominated, indie phenomenon", 'tier': "modern_classic", 'listen_score': 95},
            {'artist': "BTS", 'song': "Spring Day", 'genre': "K-Pop", 'year': 2017, 'acclaim': "Most beloved K-pop song ever, cultural phenomenon", 'tier': "modern_classic", 'listen_score': 96},
            {'artist': "BLACKPINK", 'song': "Kill This Love", 'genre': "K-Pop", 'year': 2019, 'acclaim': "Global K-pop phenomenon, 1B+ streams", 'tier': "modern_classic", 'listen_score': 94},
            {'artist': "PSY", 'song': "Gangnam Style", 'genre': "K-Pop", 'year': 2012, 'acclaim': "First video to hit 1B views, global phenomenon", 'tier': "modern_classic", 'listen_score': 93},
            {'artist': "TWICE", 'song': "Feel Special", 'genre': "K-Pop", 'year': 2019, 'acclaim': "K-pop masterpiece, beloved by fans worldwide", 'tier': "modern_classic", 'listen_score': 94},
            {'artist': "NewJeans", 'song': "Ditto", 'genre': "K-Pop", 'year': 2022, 'acclaim': "Modern K-pop classic, critically adored", 'tier': "modern_classic", 'listen_score': 95},
            {'artist': "Burna Boy", 'song': "Last Last", 'genre': "Afrobeats", 'year': 2022, 'acclaim': "Grammy winner, global Afrobeats ambassador", 'tier': "cult", 'listen_score': 96},
            {'artist': "Wizkid", 'song': "Essence (feat. Tems)", 'genre': "Afrobeats", 'year': 2020, 'acclaim': "Breakthrough Afrobeats hit, Grammy-nominated", 'tier': "cult", 'listen_score': 96},
            {'artist': "Tems", 'song': "Free Mind", 'genre': "Afrobeats/R&B", 'year': 2022, 'acclaim': "Grammy winner, soulful masterpiece", 'tier': "cult", 'listen_score': 95},
            {'artist': "Davido", 'song': "Fall", 'genre': "Afrobeats", 'year': 2019, 'acclaim': "Most Shazamed Afrobeats song ever", 'tier': "cult", 'listen_score': 94},
            {'artist': "Rema", 'song': "Calm Down", 'genre': "Afrobeats", 'year': 2022, 'acclaim': "1B+ streams, biggest Afrobeats song ever", 'tier': "cult", 'listen_score': 94},
            {'artist': "Ang\u00e9lique Kidjo", 'song': "Batonga", 'genre': "Afropop", 'year': 1991, 'acclaim': "Grammy winner, African music icon", 'tier': "cult", 'listen_score': 95},
            {'artist': "Sophie", 'song': "Immaterial", 'genre': "Hyperpop", 'year': 2018, 'acclaim': "Genre-defining hyperpop masterpiece", 'tier': "cult", 'listen_score': 95},
            {'artist': "Arca", 'song': "Riquiqu\u00ed", 'genre': "Avant-Garde", 'year': 2020, 'acclaim': "Experimental masterpiece, influential", 'tier': "cult", 'listen_score': 93},
            {'artist': "Death Grips", 'song': "Get Got", 'genre': "Experimental Hip-Hop", 'year': 2012, 'acclaim': "Punk-meets-hip-hop, genuinely unique", 'tier': "cult", 'listen_score': 95},
            {'artist': "100 gecs", 'song': "Money Machine", 'genre': "Hyperpop", 'year': 2019, 'acclaim': "Wildly original, defined hyperpop", 'tier': "cult", 'listen_score': 94},
            {'artist': "JPEGMAFIA", 'song': "Baby I'm Bleeding", 'genre': "Experimental Hip-Hop", 'year': 2018, 'acclaim': "Bold, abrasive, critically adored", 'tier': "cult", 'listen_score': 94},
            {'artist': "Oneohtrix Point Never", 'song': "Replica", 'genre': "Experimental Electronic", 'year': 2011, 'acclaim': "Groundbreaking experimental electronic", 'tier': "cult", 'listen_score': 94},
        # === Eurovision ===  User rates Eurovision avg 87.3/100 (their 4th highest-rated genre)
        {'artist': 'Loreen', 'song': 'Euphoria', 'genre': 'Eurovision', 'year': 2012, 'acclaim': 'Eurovision winner, iconic modern classic, 500M+ streams', 'tier': 'modern_classic', 'listen_score': 97},
        {'artist': 'Mans Zelmerlow', 'song': 'Heroes', 'genre': 'Eurovision', 'year': 2015, 'acclaim': 'Eurovision winner, stadium anthem', 'tier': 'modern_classic', 'listen_score': 96},
        {'artist': 'Alexander Rybak', 'song': 'Fairytale', 'genre': 'Eurovision', 'year': 2009, 'acclaim': 'Eurovision winner, record-breaking 387 points', 'tier': 'classic', 'listen_score': 95},
        {'artist': 'Duncan Laurence', 'song': 'Arcade', 'genre': 'Eurovision', 'year': 2019, 'acclaim': 'Eurovision winner, global hit, 500M+ streams', 'tier': 'modern_classic', 'listen_score': 95},
        {'artist': 'Salvador Sobral', 'song': 'Amar Pelos Dois', 'genre': 'Eurovision', 'year': 2017, 'acclaim': 'Eurovision winner, stunning jazz ballad', 'tier': 'modern_classic', 'listen_score': 97},
        # === J-Pop / Anime ===  User has 410 J-Pop/Anime songs (their 3rd biggest genre)
        {'artist': 'YOASOBI', 'song': 'Idol', 'genre': 'J-Pop', 'year': 2023, 'acclaim': 'Record-breaking J-pop hit, 400M+ streams', 'tier': 'modern_classic', 'listen_score': 96},
        {'artist': 'TK from Ling Tosite Sigure', 'song': 'Unravel', 'genre': 'Anime Rock', 'year': 2014, 'acclaim': 'Tokyo Ghoul OP, iconic anime rock', 'tier': 'cult', 'listen_score': 97},
        {'artist': 'RADWIMPS', 'song': 'Sparkle', 'genre': 'J-Pop', 'year': 2016, 'acclaim': 'Your Name theme, beloved worldwide', 'tier': 'modern_classic', 'listen_score': 96},
        {'artist': 'Kenshi Yonezu', 'song': 'Lemon', 'genre': 'J-Pop', 'year': 2018, 'acclaim': 'Most streamed Japanese song ever, cultural phenomenon', 'tier': 'modern_classic', 'listen_score': 95},
        # === Holiday / Christmas ===  User has 28 Christmas songs
        {'artist': 'Mariah Carey', 'song': 'All I Want for Christmas Is You', 'genre': 'Christmas/Holiday', 'year': 1994, 'acclaim': '1B+ streams, the most iconic Christmas song ever', 'tier': 'classic', 'listen_score': 97},
        {'artist': 'Wham!', 'song': 'Last Christmas', 'genre': 'Christmas/Holiday', 'year': 1984, 'acclaim': '1B+ streams, timeless holiday classic', 'tier': 'classic', 'listen_score': 96},
        {'artist': 'Bing Crosby', 'song': 'White Christmas', 'genre': 'Christmas/Holiday', 'year': 1942, 'acclaim': 'Best-selling single of all time, Guinness World Record', 'tier': 'legendary', 'listen_score': 98},
        ]


    TIER_LABELS = {
        'legendary': '🏆 Legendary',
        'modern_classic': '⭐ Modern Classic',
        'classic': '💎 Classic',
        'cult': '🔥 Cult Favorite',
    }


    # Map challenge DB genre names to classification genre names
    # so opposite-taste mode can correctly match songs to the user's
    # lowest-rated classification genres (which use different naming).
    _genre_alias_to_class = {
        'A Cappella': 'A Cappella',
        'Alternative': 'Indie/Alternative',
        'Alternative Rock': 'Rock',
        'Anime': 'J-Pop/Anime',
        'Anime Score': 'Soundtrack/Score',
        'Art Pop': 'Pop',
        'Art Rock': 'Rock',
        'Bachata': 'Latin',
        'Black Metal': 'Metal',
        'Blues': 'Blues',
        'Blues Rock': 'Rock',
        'Bossa Nova': 'Jazz/Swing',
        'Brazilian': 'Latin',
        'Brazilian Tropicalia': 'Latin',
        'Britpop': 'Indie/Alternative',
        'Christmas/Holiday': 'Christmas/Holiday',
        'City Pop': 'J-Pop/Anime',
        'Classic Rock': 'Rock',
        'Classical': 'Classical/Instrumental',
        'Country': 'Country',
        'Country/Folk': 'Folk/Acoustic',
        'Country/Rock': 'Country',
        'Cuban Son': 'Latin',
        'Cumbia': 'Latin',
        'Dance': 'Electronic/Dance',
        'Dance Pop': 'Pop',
        'Dancehall': 'Reggae/Dub',
        'Death Metal': 'Metal',
        'Disco': 'Disco/Funk',
        'Drill': 'Rap/Hip-Hop',
        'Dub/Reggae': 'Reggae/Dub',
        'Electronic': 'Electronic/Dance',
        'Electronic/Ambient': 'Electronic/Dance',
        'Electronic/Dance': 'Electronic/Dance',
        'Electronic/House': 'Electronic/Dance',
        'Electronic/IDM': 'Electronic/Dance',
        'Electronic/Jazz': 'Jazz/Swing',
        'Electropop': 'Pop',
        'Ethio-Jazz': 'Jazz/Swing',
        'Eurovision': 'Eurovision',
        'Experimental Electronic': 'Electronic/Dance',
        'Experimental Hip-Hop': 'Rap/Hip-Hop',
        'Film Score': 'Soundtrack/Score',
        'Flamenco Pop': 'Latin',
        'Folk': 'Folk/Acoustic',
        'Folk Rock': 'Rock',
        'Folk/Americana': 'Folk/Acoustic',
        'Funk': 'Disco/Funk',
        'Funk/R&B': 'Disco/Funk',
        'Funk/Soul': 'R&B/Soul',
        'Game Soundtrack': 'Soundtrack/Score',
        'Garage Rock': 'Rock',
        'Grime': 'Rap/Hip-Hop',
        'Grunge': 'Indie/Alternative',
        'Hardcore Punk': 'Punk',
        'Heavy Metal': 'Metal',
        'Hip-Hop': 'Rap/Hip-Hop',
        'Hip-Hop/R&B': 'Rap/Hip-Hop',
        'House': 'Electronic/Dance',
        'Indian Classical': 'Classical/Instrumental',
        'Indie': 'Indie/Alternative',
        'Indie Folk': 'Indie/Alternative',
        'Indie Pop': 'Pop',
        'Indie Rock': 'Rock',
        'Indie/Electronic': 'Indie/Alternative',
        'Instrumental': 'Classical/Instrumental',
        'J Rock': 'J-Pop/Anime',
        'J-Pop': 'J-Pop/Anime',
        'J-Pop/Anime': 'J-Pop/Anime',
        'Jazz': 'Jazz/Swing',
        'Jazz/Funk': 'Jazz/Swing',
        'Jazz/Soul': 'Jazz/Swing',
        'Jazz/Swing': 'Jazz/Swing',
        'K-Pop': 'K-Pop',
        'Latin': 'Latin',
        'Latin Jazz': 'Jazz/Swing',
        'Latin Pop': 'Latin',
        'Latin Rock': 'Rock',
        'Lovers Rock': 'Reggae/Dub',
        'Malian Blues': 'Blues',
        'Mambo': 'Latin',
        'Metal': 'Metal',
        'Motown': 'R&B/Soul',
        'Neo-Soul': 'R&B/Soul',
        'New Wave': 'Punk',
        'New Wave/Art Rock': 'Rock',
        'Nu Metal': 'Metal',
        'Nu-Disco': 'Disco/Funk',
        'OST': 'Soundtrack/Score',
        'Pop': 'Pop',
        'Pop Punk': 'Punk',
        'Pop/Rap': 'Rap/Hip-Hop',
        'Pop/Rock': 'Rock',
        'Post-Punk': 'Punk',
        'Post-Rock': 'Rock',
        'Power Metal': 'Metal',
        'Progressive Death Metal': 'Metal',
        'Progressive Metal': 'Metal',
        'Progressive Rock': 'Rock',
        'Psychedelic Rock': 'Rock',
        'Punk': 'Punk',
        'Punk Rock': 'Punk',
        'R&B': 'R&B/Soul',
        'R&B/Funk': 'R&B/Soul',
        'R&B/Soul': 'R&B/Soul',
        'Rap': 'Rap/Hip-Hop',
        'Reggae': 'Reggae/Dub',
        'Reggaeton': 'Reggae/Dub',
        'Rock': 'Rock',
        'Salsa': 'Latin',
        'Score': 'Soundtrack/Score',
        'Shibuya-kei': 'J-Pop/Anime',
        'Shoegaze': 'Indie/Alternative',
        'Singer-Songwriter': 'Folk/Acoustic',
        'Ska': 'Reggae/Dub',
        'Ska/Reggae': 'Reggae/Dub',
        'Soul': 'R&B/Soul',
        'Soul/Pop': 'R&B/Soul',
        'Soundtrack': 'Soundtrack/Score',
        'Swing': 'Jazz/Swing',
        'Symphonic Metal': 'Metal',
        'Synth-pop': 'Pop',
        'Tango': 'Latin',
        'Techno': 'Electronic/Dance',
        'Teen Pop': 'Pop',
        'Thrash Metal': 'Metal',
        'Trap': 'Rap/Hip-Hop',
        'Tuareg Blues': 'Blues',
        'Video Game': 'Soundtrack/Score',
        'Vocaloid': 'J-Pop/Anime',
        'Anime Rock': 'J-Pop/Anime',
    }

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
            genre_lowest = self._genre_alias_to_class.get(song['genre'], song['genre']) in lowest_rated_genres

            if mode == 'opposite_taste' and genre_lowest:
                # Opposite-taste mode: prioritize genres you rate lowest
                # Map the challenge DB genre name to the classification genre name for display
                class_genre = self._genre_alias_to_class.get(song['genre'], song['genre'])
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
            class_genre = self._genre_alias_to_class.get(song['genre'], song['genre'])
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

    # Curated genre mapping for well-known artists that Wikidata/MusicBrainz may miss.
    _CURATED_ARTIST_GENRES = {
        # Pop
        'Taylor Swift': 'Pop', 'Katy Perry': 'Pop', 'Selena Gomez': 'Pop', 'Justin Bieber': 'Pop',
        'Ariana Grande': 'Pop', 'Miley Cyrus': 'Pop', 'Demi Lovato': 'Pop', 'Lady Gaga': 'Pop',
        'Bruno Mars': 'Pop', 'Rihanna': 'Pop', 'Beyoncé': 'Pop', 'P!nk': 'Pop', 'Pink': 'Pop',
        'Adele': 'Pop', 'Ed Sheeran': 'Pop', 'Sam Smith': 'Pop', 'Shawn Mendes': 'Pop',
        'Charlie Puth': 'Pop', 'Maroon 5': 'Pop', 'OneRepublic': 'Pop', 'Coldplay': 'Pop',
        'Avril Lavigne': 'Pop', 'Kelly Clarkson': 'Pop', 'Christina Perri': 'Pop',
        'Jason Derulo': 'Pop', 'David Guetta': 'Pop', 'Calvin Harris': 'Pop',
        'Michael Jackson': 'Pop', 'Madonna': 'Pop', 'Britney Spears': 'Pop',
        
        # Rock
        'Linkin Park': 'Rock', 'Imagine Dragons': 'Rock', 'Fall Out Boy': 'Rock',
        'Muse': 'Rock', 'Foo Fighters': 'Rock', 'Green Day': 'Rock', 'Red Hot Chili Peppers': 'Rock',
        'Pink Floyd': 'Rock', 'Queen': 'Rock', 'Led Zeppelin': 'Rock', 'Nirvana': 'Rock',
        'The Beatles': 'Rock', 'The Rolling Stones': 'Rock', 'U2': 'Rock',
        'Thirty Seconds to Mars': 'Rock', 'Paramore': 'Rock', 'My Chemical Romance': 'Rock',
        'Set It Off': 'Rock', 'Set If Off': 'Rock',  # handle the typo
        'Panic! At The Disco': 'Rock', 'Panic at the Disco': 'Rock',
        'Three Days Grace': 'Rock', 'Skillet': 'Rock', 'Breaking Benjamin': 'Rock',
        
        # R&B/Soul
        'Stevie Wonder': 'R&B/Soul', 'Frank Ocean': 'R&B/Soul', 'Amy Winehouse': 'R&B/Soul',
        'The Weeknd': 'R&B/Soul', 'Alicia Keys': 'R&B/Soul', 'John Legend': 'R&B/Soul',
        'Usher': 'R&B/Soul', 'Chris Brown': 'R&B/Soul',
        
        # Rap/Hip-Hop
        'Eminem': 'Rap/Hip-Hop', 'Kendrick Lamar': 'Rap/Hip-Hop', 'Drake': 'Rap/Hip-Hop',
        'Kanye West': 'Rap/Hip-Hop', 'Jay-Z': 'Rap/Hip-Hop', 'Lil Wayne': 'Rap/Hip-Hop',
        'Juice WRLD': 'Rap/Hip-Hop', 'Juice Wrld': 'Rap/Hip-Hop',
        'The Black Eyed Peas': 'Rap/Hip-Hop', 'Black Eyed Peas': 'Rap/Hip-Hop',
        'Nicki Minaj': 'Rap/Hip-Hop', 'Cardi B': 'Rap/Hip-Hop',
        
        # Country
        'Johnny Cash': 'Country', 'Dolly Parton': 'Country', 'Willie Nelson': 'Country',
        'Taylor Swift': 'Pop',  # overridden above, but country-era TS
        'Carrie Underwood': 'Country', 'Luke Bryan': 'Country', 'Florida Georgia Line': 'Country',
        
        # Latin
        'Ricky Martin': 'Latin', 'Shakira': 'Latin', 'Jennifer Lopez': 'Latin', 'J Balvin': 'Latin',
        'Bad Bunny': 'Latin', 'Rosalía': 'Latin', 'Enrique Iglesias': 'Latin',
        
        # Electronic/Dance
        'Daft Punk': 'Electronic/Dance', 'Avicii': 'Electronic/Dance', 'Skrillex': 'Electronic/Dance',
        'deadmau5': 'Electronic/Dance', 'Marshmello': 'Electronic/Dance', 'Zedd': 'Electronic/Dance',
        'Kygo': 'Electronic/Dance', 'Martin Garrix': 'Electronic/Dance',
        
        # J-Pop/Anime
        'Ado': 'J-Pop/Anime', 'LiSA': 'J-Pop/Anime', 'YOASOBI': 'J-Pop/Anime', 'Eve': 'J-Pop/Anime',
        'Kenshi Yonezu': 'J-Pop/Anime', 'ZUTOMAYO': 'J-Pop/Anime', 'ReoNa': 'J-Pop/Anime',
        'Aimer': 'J-Pop/Anime', 'ClariS': 'J-Pop/Anime',
        
        # Classical/Instrumental
        'Chopin': 'Classical/Instrumental', 'Bach': 'Classical/Instrumental',
        'Beethoven': 'Classical/Instrumental', 'Mozart': 'Classical/Instrumental',
        'Vivaldi': 'Classical/Instrumental', 'Ludovico Einaudi': 'Classical/Instrumental',
        'Yiruma': 'Classical/Instrumental', 'Lindsey Stirling': 'Classical/Instrumental',
        'Taylor Davis': 'Classical/Instrumental', 'The Piano Guys': 'Classical/Instrumental',
        'Philip Wesley': 'Classical/Instrumental', 'Michele McLaughlin': 'Classical/Instrumental',
        'Brian Crain': 'Classical/Instrumental',
        
        # Jazz/Swing
        'Louis Armstrong': 'Jazz/Swing', 'Michael Bublé': 'Jazz/Swing', 'Michael Buble': 'Jazz/Swing',
        'Frank Sinatra': 'Jazz/Swing', 'Ella Fitzgerald': 'Jazz/Swing', 'Duke Ellington': 'Jazz/Swing',
        'Miles Davis': 'Jazz/Swing', 'John Coltrane': 'Jazz/Swing',
        
        # Indie/Alternative
        'Vance Joy': 'Indie/Alternative', 'Tove Lo': 'Indie/Alternative', 'James Blake': 'Indie/Alternative',
        'Bon Iver': 'Indie/Alternative', 'Alt-J': 'Indie/Alternative', 'Glass Animals': 'Indie/Alternative',
        'OK Go': 'Indie/Alternative', 'Capital Cities': 'Indie/Alternative',
        
        # Folk/Acoustic
        'Simon & Garfunkel': 'Folk/Acoustic', 'Bob Dylan': 'Folk/Acoustic', 'Joni Mitchell': 'Folk/Acoustic',
        
        # Metal
        'Metallica': 'Metal', 'Black Sabbath': 'Metal', 'Iron Maiden': 'Metal', 'Slipknot': 'Metal',
        'System of a Down': 'Metal', 'Nightwish': 'Metal', 'Within Temptation': 'Metal',
        
        # Disco/Funk
        'Earth Wind and Fire': 'Disco/Funk', 'Earth, Wind and Fire': 'Disco/Funk',
        'KC and the Sunshine Band': 'Disco/Funk', 'Chic': 'Disco/Funk',
        
        # Soundtrack/Score
        'Hans Zimmer': 'Soundtrack/Score', 'John Williams': 'Soundtrack/Score',
        'Daniel Ingram': 'Soundtrack/Score', 'Joe Hisaishi': 'Soundtrack/Score',
        'Yoko Shimomura': 'Soundtrack/Score', 'Nobuo Uematsu': 'Soundtrack/Score',
        
        # K-Pop
        'PSY': 'K-Pop', 'BTS': 'K-Pop', 'BLACKPINK': 'K-Pop', 'TWICE': 'K-Pop',
        
        # Punk
        'Blink-182': 'Punk', 'Green Day': 'Rock', 'The Ramones': 'Punk',
        'Sum 41': 'Punk', 'The Offspring': 'Punk',
        
        # Additional artists from uncategorized list
        'Lawson': 'Pop', 'Justin Timberlake': 'Pop', 'A-ha': 'Pop',
        'Rob Thomas': 'Pop', 'Mike Perry': 'Pop', 'Capital Cities': 'Pop',
        'Unlike Pluto': 'Electronic/Dance', 'Gareth Emery': 'Electronic/Dance',
        'Con Bro Chill': 'Electronic/Dance', 'Didrick': 'Electronic/Dance',
        'Zhou Shen': 'J-Pop/Anime', 'Sayuri': 'J-Pop/Anime',
        'Auli\u02bbi Cravalho': 'Soundtrack/Score', 'The Greatest Showman': 'Soundtrack/Score',
        'Daniel Ingram': 'Soundtrack/Score',
        'We the Kings': 'Rock', 'Tiga': 'Electronic/Dance',
        'Korede Bello': 'R&B/Soul', 'Kelly Sweet': 'Pop',
        'ZAYDE WOLF': 'Rock', 'Fifth Harmony': 'Pop',
        'The Score': 'Rock', 'Anna Blue': 'Pop',
        'Landon Austin': 'Pop', 'Damien Dawn': 'Electronic/Dance',
        'Zen Zen Sense': 'Electronic/Dance', 'Incantation': 'Metal',
        'The Villain I Appear to Be': 'Rock', 'BLACK6IX': 'J-Pop/Anime',
        'Jennifer Lawrence': 'Pop', 'ATC': 'Electronic/Dance',
        'Boy Epic': 'Rock', 'Edvin Marton': 'Classical/Instrumental',
        'Tessa Violet': 'Indie/Alternative', 'Imy': 'Pop',
        'Owl City': 'Pop',
        
        # Handle multi-artist feat patterns
        'Gareth Emery feat. Christina Novelli': 'Electronic/Dance',
        'Christina Novelli': 'Electronic/Dance',
        'Christina Perri ft. Ed Sheeran': 'Pop',
        'Jon Cozart and Dodie': 'Pop', 'Dodie': 'Pop',
        'Anna Blue & Damien Dawn': 'Pop',
        'Yu Quan & Huang Zhang': 'Pop',
        'DJ Striden': 'Electronic/Dance',

        # Additional known artists
        'Chase Holfelder': 'Pop', 'Karmin': 'Pop', 'Nick Pitera': 'Pop',
        'sleeping at last': 'Indie/Alternative', 'Sleeping at Last': 'Indie/Alternative',
        'Alan Walker': 'Electronic/Dance', 'Kungs': 'Electronic/Dance',
        'Kana Nishino': 'J-Pop/Anime', 'Auli\'i Cravalho': 'Soundtrack/Score',
        'One Republic': 'Pop',  # typo alias for OneRepublic
        'Revivalists': 'Indie/Alternative', 'I AM THEY': 'Pop',
        'Mat Kearney': 'Pop', 'The Script': 'Rock',
        'Pentatonix': 'A Cappella', 'Owl City': 'Pop',
        'F-777': 'Electronic/Dance', 'The Score': 'Rock',
        'Weathers': 'Rock', 'Victorious': 'Pop',
        'Brunuhville': 'Classical/Instrumental',
        'Tessa Violet': 'Indie/Alternative', 'lovelytheband': 'Indie/Alternative',
        '3OH!3': 'Pop', 'Landon Austin': 'Pop',
        'Damien Dawn': 'Electronic/Dance',
        'Yandel': 'Latin', 'Kristian Kostov': 'Pop',
        'Emmelie De Forest': 'Eurovision', 'Yohanna': 'Eurovision',
        'Clara C': 'Indie/Alternative', 'Imy': 'J-Pop/Anime',
        'CircusP': 'J-Pop/Anime', 'Jon Cozart': 'Pop',
        '4count': 'A Cappella', 'OBB': 'Pop',
        'Jake Manisto': 'Pop', 'Dolvondo': 'Pop',
        'Kuba Oms': 'Folk/Acoustic', 'Vanic': 'Electronic/Dance',

        # Test data — classify as Pop (reasonable default)
        'Test Artist': 'Pop', 'Cool Artist': 'Pop', 'Fresh Artist': 'Pop',
        'Artist A': 'Pop', 'Artist B': 'Pop', 'Artist C': 'Pop',
        'Artist One': 'Pop', 'Artist Two': 'Pop', 'Artist Three': 'Pop',
        'Artist': 'Pop', 'Another': 'Pop',
    }

    # Song titles that get mis-parsed as artist names — filter these out
    _PARSE_ARTIFACTS = {
        'paparazzi', 'on the floor', 'bad romance', 'wicked game', 'monsters',
        'stampede', 'reflections', 'the winner takes it all', 'remember the name',
        '7 years', 'life might take us', 'dont you forget about me', 
        'god rest ye merry gentlemen', 'kiss the girl in minor key',
        'we shall never surrender', 'americas cup', 'forgotten city',
        'detective detective', 'wannabe', 'jenny', 'tyler', 'new romantics',
        '6/10', 'papa ya', 'storms end', 'fluttershys lament', 'brain crain',
        'life might take us', 'the winner takes it all'
    }

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
        for artist, genre in self._CURATED_ARTIST_GENRES.items():
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
    def _extract_letter_grade(text: str):
        """Extract letter grade (A+ through F) from review text.
        Returns (grade_str, numeric_value) or (None, None).
        """
        if not text:
            return None, None
        # Try explicit patterns first: "Score: A+", "Rating A-", "A+" at end of sentence, etc.
        patterns = [
            r'(?:score|rating|grade)[:\s]*([A-F][+-]?)',
            r'([A-F][+-]?)\s*(?:/\s*[A-F]|out of|grade)',
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                g = m.group(1).upper()
                if g in TasteEngine.LETTER_GRADE_MAP:
                    return g, TasteEngine.LETTER_GRADE_MAP[g]

        # Broader: isolated letter grades with sentence-final or parenthetical position
        # Look for grades that appear as standalone tokens (not part of words)
        for m in re.finditer(r'\b([A-F][+-]?)\b', text):
            g = m.group(1).upper()
            if g in TasteEngine.LETTER_GRADE_MAP:
                # Avoid false positives: 'A' as article, 'A' in mid-sentence without context
                # Accept if: preceded by score/rating/grade context, at end of sentence,
                # in parentheses, or a plus/minus grade
                ctx_before = text[max(0, m.start()-20):m.start()].lower()
                ctx_after = text[m.end():m.end()+10].lower()
                is_plus_minus = len(g) > 1  # A+, B- are unambiguous
                has_context = any(kw in ctx_before for kw in ['score', 'rating', 'grade', 'got ', 'gave ', 'is ', 'was ', 'overall'])
                is_end = m.end() >= len(text) - 2 or text[m.end():m.end()+2] in ('. ', '! ', ')', '\n')
                if is_plus_minus or has_context or is_end:
                    return g, TasteEngine.LETTER_GRADE_MAP[g]

        return None, None

    @staticmethod
    def _infer_tone_rating(text: str):
        """Infer a numerical rating from tone/sentiment in review text.
        Returns (method_tag, rating) or (None, None).

        Tone tiers (from user's description):
          "meh" / "ok" → C (75)
          "good" / "like" → B (85)
          "amazing" / "awesome" / "really cool" → A or A+ (95)
        """
        if not text:
            return None, None
        t = text.lower()

        # --- Positive tone (High) ---
        if any(kw in t for kw in ['all time favorite', 'one of my favorites', 'absolute masterpiece', 'perfect 10']):
            return 'tone:masterpiece', 100
        if any(kw in t for kw in ['perfect song', 'absolutely perfect', 'couldn\'t be better', 'pure perfection']):
            return 'tone:perfect', 98
        if any(kw in t for kw in ['incredible', 'mind-blowing', 'blows my mind', 'stunning']):
            return 'tone:incredible', 97
        if any(kw in t for kw in ['amazing', 'absolutely love', 'all-time great']):
            return 'tone:amazing', 95
        if any(kw in t for kw in ['awesome', 'fantastic', 'phenomenal', 'outstanding', 'brilliant']):
            return 'tone:awesome', 94
        if 'love' in t and 'love song' not in t and 'lover' not in t:
            return 'tone:love', 93
        if any(kw in t for kw in ['beautiful', 'gorgeous', 'wonderful', 'excellent']):
            return 'tone:beautiful', 92
        if any(kw in t for kw in ['loved it', 'loved this', 'really love', 'one of my fav']):
            return 'tone:loved', 91

        # --- Positive tone (Medium-High) ---
        if any(kw in t for kw in ['really good', 'very good', 'really great', 'pretty great', 'quite good']):
            return 'tone:really_good', 88
        if any(kw in t for kw in ['great', 'terrific', 'superb', 'really like']):
            return 'tone:great', 88
        if any(kw in t for kw in ['really cool', 'cool song', 'that\'s cool', 'pretty cool']):
            return 'tone:cool', 86
        if any(kw in t for kw in ['good song', 'pretty good', 'quite nice', 'liked it', 'liked this']):
            return 'tone:good', 84
        if any(kw in t for kw in ['nice', 'solid', 'decent', 'fine', 'pleasant', 'enjoyable']):
            return 'tone:nice', 82
        if any(kw in t for kw in ['not bad', 'pretty nice', 'alright', 'okay i guess']):
            return 'tone:not_bad', 78

        # --- Neutral / Mixed ---
        if any(kw in t for kw in ['okay', 'ok ', "it's ok", "that's ok"]):
            return 'tone:ok', 76
        if any(kw in t for kw in ['average', 'mediocre', 'mid', 'so-so', 'meh', 'whatever']):
            return 'tone:meh', 72
        if any(kw in t for kw in ['disappointed', 'disappointing', 'could be better', 'not great']):
            return 'tone:disappointed', 68
        if any(kw in t for kw in ['boring', 'dull', 'uninteresting', 'forgettable', 'skip']):
            return 'tone:boring', 65

        # --- Negative ---
        if any(kw in t for kw in ['bad', 'not good', 'poor', 'weak song', 'weakest']):
            return 'tone:bad', 62
        if any(kw in t for kw in ['terrible', 'awful', 'horrible', 'dreadful']):
            return 'tone:terrible', 50
        if any(kw in t for kw in ['worst', 'garbage', 'trash', 'hate']):
            return 'tone:worst', 40

        return None, None

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

            combined = (r.get('tail') or '') + ' ' + (r.get('title') or '')
            new_rating = None
            source = None
            grade_str = None

            # Try letter grade extraction
            if method in ('all', 'letter'):
                g, v = self._extract_letter_grade(combined)
                if v is not None:
                    new_rating = v
                    source = 'letter'
                    grade_str = g
                    letter_count += 1

            # Fall back to tone inference
            if new_rating is None and method in ('all', 'tone'):
                tag, v = self._infer_tone_rating(combined)
                if v is not None:
                    new_rating = v
                    source = tag
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
