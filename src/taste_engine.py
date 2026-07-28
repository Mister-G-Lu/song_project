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
        self._artist_genre_cache: Dict[str, str] = {}  # MusicBrainz artist→genre cache
        self._load_data()
        self._build_artist_index()
        self._init_genre_keywords()
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
                if p and len(p) > 1:
                    results.append(p)
        # Pattern: Artist – Title (with en dash or hyphen)
        m = re.match(r'^([A-Za-z0-9][^–-]+?)\s*[–-]\s+', title)
        if m:
            artist = m.group(1).strip().rstrip(',').strip('"').strip("'")
            if artist and len(artist) > 1 and artist not in results:
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
        Uses three-tier fallback:
          1. Keyword match against review text + title
          2. _artist_genre_cache (populated by MusicBrainz)
          3. Uncategorized
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
        Genre is pre-computed during _build_artist_index for performance.
        """
        nodes = []
        edges = []
        artist_set = set()

        # Build nodes from artists with ratings (genre is pre-cached)
        for artist, info in self.all_artists.items():
            if len(info['ratings']) > 0:
                artist_set.add(artist)
                avg = round(sum(info['ratings']) / len(info['ratings']), 1)
                max_r = max(info['ratings'])
                nodes.append({
                    'id': artist,
                    'name': artist,
                    'avg_rating': avg,
                    'song_count': len(info['ratings']),
                    'max_rating': max_r,
                    'genre': info.get('genre', 'Uncategorized')
                })

        # Build edges: connect artists that appear together in songs
        for r in self.rows:
            artists = self._extract_artists(r['title'])
            for i in range(len(artists)):
                for j in range(i+1, len(artists)):
                    if artists[i] in artist_set and artists[j] in artist_set:
                        edges.append({
                            'source': artists[i],
                            'target': artists[j],
                            'song': r['title'][:40]
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
                    {'artist': 'Portishead', 'song': 'Glory Box', 'reason': 'You rated this 99 — try their album Dummy for more trip-hop perfection'},
                    {'artist': 'Kokia', 'song': 'Kirin', 'reason': 'You rated this 97 — she has many more ethereal songs to explore'},
                    {'artist': 'Mariya Takeuchi', 'song': 'Plastic Love', 'reason': 'You rated this 98 — check her album Variety for more city pop gold'},
                    {'artist': 'Chase Holfelder', 'song': 'Kiss the Girl in Minor Key', 'reason': 'You rated this 96 — he does many minor key pop covers, explore them all'},
                    {'artist': 'Infected Mushroom', 'song': 'Heavyweight', 'reason': 'You rated this 99 — their psychadelic electronic is unmatched'},
                ])
            }
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
    # Challenge section — Critically acclaimed songs outside your zone
    # ------------------------------------------------------------------

    @staticmethod
    def _build_challenge_db():
        """Curated database of critically acclaimed / widely-loved songs
        across diverse genres. Sources: RateYourMusic top charts,
        Rolling Stone 500, critical acclaim, cultural impact.
        """
        return [
            # === Classic Rock / Legendary ===
            {'artist': 'Queen', 'song': 'Bohemian Rhapsody', 'genre': 'Classic Rock', 'year': 1975, 'acclaim': "RS 500, 1B+ streams, genre-defying masterpiece", 'tier': 'legendary', 'listen_score': 99},
            {'artist': 'Led Zeppelin', 'song': 'Stairway to Heaven', 'genre': 'Classic Rock', 'year': 1971, 'acclaim': "Widely considered the greatest rock song ever", 'tier': 'legendary', 'listen_score': 99},
            {'artist': 'Pink Floyd', 'song': 'Comfortably Numb', 'genre': 'Progressive Rock', 'year': 1979, 'acclaim': "RS 500, iconic guitar solos, masterpiece", 'tier': 'legendary', 'listen_score': 98},
            {'artist': 'The Beatles', 'song': 'A Day in the Life', 'genre': 'Classic Rock', 'year': 1967, 'acclaim': "Often ranked #1 song of all time", 'tier': 'legendary', 'listen_score': 99},
            {'artist': 'Fleetwood Mac', 'song': 'Dreams', 'genre': 'Classic Rock', 'year': 1977, 'acclaim': "1B+ streams, iconic production", 'tier': 'classic', 'listen_score': 97},
            {'artist': 'The Rolling Stones', 'song': 'Gimme Shelter', 'genre': 'Classic Rock', 'year': 1969, 'acclaim': "RS 500, one of the greatest rock songs", 'tier': 'legendary', 'listen_score': 98},

            # === Hip-Hop / Rap ===
            {'artist': 'Kendrick Lamar', 'song': 'Alright', 'genre': 'Hip-Hop', 'year': 2015, 'acclaim': "Grammy winner, cultural anthem, 1B+ streams", 'tier': 'modern_classic', 'listen_score': 98},
            {'artist': 'Notorious B.I.G.', 'song': 'Juicy', 'genre': 'Hip-Hop', 'year': 1994, 'acclaim': "RS 500, greatest hip-hop song of all time", 'tier': 'legendary', 'listen_score': 98},
            {'artist': 'Tupac', 'song': 'Changes', 'genre': 'Hip-Hop', 'year': 1998, 'acclaim': "Cultural anthem, iconic message", 'tier': 'legendary', 'listen_score': 97},
            {'artist': 'Outkast', 'song': 'Hey Ya!', 'genre': 'Hip-Hop', 'year': 2003, 'acclaim': "Grammy winner, genre-blending masterpiece", 'tier': 'modern_classic', 'listen_score': 96},
            {'artist': 'Lauryn Hill', 'song': 'Doo Wop (That Thing)', 'genre': 'Hip-Hop/R&B', 'year': 1998, 'acclaim': "Grammy winner, RS 500", 'tier': 'modern_classic', 'listen_score': 97},

            # === Electronic / Experimental ===
            {'artist': 'Daft Punk', 'song': 'One More Time', 'genre': 'Electronic', 'year': 2000, 'acclaim': "1B+ streams, defined a generation of dance music", 'tier': 'modern_classic', 'listen_score': 98},
            {'artist': 'Aphex Twin', 'song': 'Windowlicker', 'genre': 'Electronic/IDM', 'year': 1999, 'acclaim': "Groundbreaking electronic, RS 500", 'tier': 'cult', 'listen_score': 95},
            {'artist': 'Massive Attack', 'song': 'Teardrop', 'genre': 'Trip-Hop', 'year': 1998, 'acclaim': "Defined trip-hop, iconic", 'tier': 'modern_classic', 'listen_score': 97},
            {'artist': 'Boards of Canada', 'song': 'Roygbiv', 'genre': 'Electronic/Ambient', 'year': 1998, 'acclaim': "Influential ambient electronic masterpiece", 'tier': 'cult', 'listen_score': 94},
            {'artist': 'Kraftwerk', 'song': 'The Model', 'genre': 'Electronic', 'year': 1978, 'acclaim': "Pioneered electronic music, hugely influential", 'tier': 'legendary', 'listen_score': 96},

            # === Jazz / Soul / Funk ===
            {'artist': 'Miles Davis', 'song': 'So What', 'genre': 'Jazz', 'year': 1959, 'acclaim': "Greatest jazz album of all time (Kind of Blue)", 'tier': 'legendary', 'listen_score': 99},
            {'artist': 'John Coltrane', 'song': 'My Favorite Things', 'genre': 'Jazz', 'year': 1961, 'acclaim': "Revolutionary jazz, masterpiece", 'tier': 'legendary', 'listen_score': 98},
            {'artist': 'Aretha Franklin', 'song': 'Respect', 'genre': 'Soul', 'year': 1967, 'acclaim': "Cultural anthem, RS 500 #1", 'tier': 'legendary', 'listen_score': 99},
            {'artist': 'Stevie Wonder', 'song': 'Superstition', 'genre': 'Funk/Soul', 'year': 1972, 'acclaim': "1B+ streams, iconic funk", 'tier': 'legendary', 'listen_score': 98},
            {'artist': 'Marvin Gaye', 'song': 'What\'s Going On', 'genre': 'Soul', 'year': 1971, 'acclaim': "RS 500 #1, cultural milestone", 'tier': 'legendary', 'listen_score': 99},

            # === Indie / Alternative ===
            {'artist': 'Radiohead', 'song': 'Paranoid Android', 'genre': 'Alternative Rock', 'year': 1997, 'acclaim': "RS 500, one of the most acclaimed alt songs", 'tier': 'modern_classic', 'listen_score': 98},
            {'artist': 'Arcade Fire', 'song': 'Wake Up', 'genre': 'Indie Rock', 'year': 2004, 'acclaim': "Grammy winner, anthem of a generation", 'tier': 'modern_classic', 'listen_score': 97},
            {'artist': 'LCD Soundsystem', 'song': 'All My Friends', 'genre': 'Indie/Electronic', 'year': 2007, 'acclaim': "Pitchfork #1, critically adored", 'tier': 'cult', 'listen_score': 96},
            {'artist': 'Neutral Milk Hotel', 'song': 'In the Aeroplane Over the Sea', 'genre': 'Indie Folk', 'year': 1998, 'acclaim': "Cult classic, one of the most beloved indie albums", 'tier': 'cult', 'listen_score': 97},
            {'artist': 'Sufjan Stevens', 'song': 'Casimir Pulaski Day', 'genre': 'Indie Folk', 'year': 2005, 'acclaim': "Universally beloved indie masterpiece", 'tier': 'modern_classic', 'listen_score': 96},
            {'artist': 'Talking Heads', 'song': 'Once in a Lifetime', 'genre': 'New Wave/Art Rock', 'year': 1980, 'acclaim': "RS 500, unique and influential", 'tier': 'legendary', 'listen_score': 97},

            # === R&B / Modern Soul ===
            {'artist': 'Frank Ocean', 'song': 'Nights', 'genre': 'R&B', 'year': 2016, 'acclaim': "Genre-defining, critically acclaimed modern classic", 'tier': 'modern_classic', 'listen_score': 97},
            {'artist': 'D\'Angelo', 'song': 'Untitled (How Does It Feel)', 'genre': 'Neo-Soul', 'year': 2000, 'acclaim': "Grammy winner, neo-soul masterpiece", 'tier': 'modern_classic', 'listen_score': 96},
            {'artist': 'Erykah Badu', 'song': 'Didn\'t Cha Know', 'genre': 'Neo-Soul', 'year': 2000, 'acclaim': "Neo-soul classic, influential", 'tier': 'modern_classic', 'listen_score': 95},
            {'artist': 'Sade', 'song': 'Smooth Operator', 'genre': 'R&B/Soul', 'year': 1984, 'acclaim': "Timeless classic, iconic", 'tier': 'classic', 'listen_score': 96},

            # === World / Global ===
            {'artist': 'Fela Kuti', 'song': 'Water No Get Enemy', 'genre': 'Afrobeat', 'year': 1975, 'acclaim': "Afrobeat legend, hugely influential", 'tier': 'legendary', 'listen_score': 97},
            {'artist': 'Buena Vista Social Club', 'song': 'Chan Chan', 'genre': 'Cuban Son', 'year': 1997, 'acclaim': "Grammy winner, revived Cuban music globally", 'tier': 'modern_classic', 'listen_score': 96},
            {'artist': 'Ravi Shankar', 'song': 'Raga Jog', 'genre': 'Indian Classical', 'year': 1960, 'acclaim': "Introduced Indian classical to the West", 'tier': 'legendary', 'listen_score': 95},
            {'artist': 'Cesária Évora', 'song': 'Sodade', 'genre': 'Cape Verdean Morna', 'year': 1992, 'acclaim': "Grammy winner, iconic voice", 'tier': 'cult', 'listen_score': 95},
            {'artist': 'Nusrat Fateh Ali Khan', 'song': 'Allah Hoo', 'genre': 'Qawwali', 'year': 1990, 'acclaim': "Legendary Qawwali singer, transcendent", 'tier': 'legendary', 'listen_score': 98},

            # === Punk / Post-Punk ===
            {'artist': 'The Ramones', 'song': 'Blitzkrieg Bop', 'genre': 'Punk', 'year': 1976, 'acclaim': "Punk anthem, RS 500", 'tier': 'legendary', 'listen_score': 96},
            {'artist': 'Joy Division', 'song': 'Love Will Tear Us Apart', 'genre': 'Post-Punk', 'year': 1980, 'acclaim': "Post-punk masterpiece, RS 500", 'tier': 'legendary', 'listen_score': 98},
            {'artist': 'The Clash', 'song': 'London Calling', 'genre': 'Punk', 'year': 1979, 'acclaim': "RS 500, genre-blending punk masterpiece", 'tier': 'legendary', 'listen_score': 98},

            # === Pop / Singer-Songwriter ===
            {'artist': 'Kate Bush', 'song': 'Running Up That Hill', 'genre': 'Art Pop', 'year': 1985, 'acclaim': "1B+ streams (Stranger Things revival), iconic", 'tier': 'legendary', 'listen_score': 97},
            {'artist': 'David Bowie', 'song': 'Heroes', 'genre': 'Art Rock', 'year': 1977, 'acclaim': "RS 500, one of the greatest songs ever", 'tier': 'legendary', 'listen_score': 99},
            {'artist': 'Björk', 'song': 'Hyperballad', 'genre': 'Art Pop', 'year': 1995, 'acclaim': "Avant-garde pop masterpiece", 'tier': 'modern_classic', 'listen_score': 97},
            {'artist': 'Fiona Apple', 'song': 'Paper Bag', 'genre': 'Art Pop', 'year': 1999, 'acclaim': "Critically adored singer-songwriter masterpiece", 'tier': 'modern_classic', 'listen_score': 95},
            {'artist': 'Tori Amos', 'song': 'Silent All These Years', 'genre': 'Singer-Songwriter', 'year': 1991, 'acclaim': "Debut single, iconic feminist anthem", 'tier': 'modern_classic', 'listen_score': 95},

            # === Metal ===
            {'artist': 'Metallica', 'song': 'One', 'genre': 'Metal', 'year': 1988, 'acclaim': "Grammy winner, thrash metal masterpiece", 'tier': 'legendary', 'listen_score': 97},
            {'artist': 'Black Sabbath', 'song': 'Paranoid', 'genre': 'Metal', 'year': 1970, 'acclaim': "Created heavy metal, RS 500", 'tier': 'legendary', 'listen_score': 98},
            {'artist': 'Tool', 'song': 'Schism', 'genre': 'Progressive Metal', 'year': 2001, 'acclaim': "Grammy winner, complex masterpiece", 'tier': 'modern_classic', 'listen_score': 96},
            {'artist': 'Opeth', 'song': 'Harlequin Forest', 'genre': 'Progressive Death Metal', 'year': 2005, 'acclaim': "Prog metal masterpiece, critically acclaimed", 'tier': 'cult', 'listen_score': 96},

            # === Folk / Country / Americana ===
            {'artist': 'Bob Dylan', 'song': 'Like a Rolling Stone', 'genre': 'Folk Rock', 'year': 1965, 'acclaim': "RS 500 #1, changed songwriting forever", 'tier': 'legendary', 'listen_score': 99},
            {'artist': 'Joni Mitchell', 'song': 'A Case of You', 'genre': 'Folk', 'year': 1971, 'acclaim': "RS 500, one of the greatest songs ever written", 'tier': 'legendary', 'listen_score': 98},
            {'artist': 'Johnny Cash', 'song': 'Hurt', 'genre': 'Country/Folk', 'year': 2002, 'acclaim': "Grammy winner, most iconic cover of all time", 'tier': 'legendary', 'listen_score': 98},
            {'artist': 'Simon & Garfunkel', 'song': 'Bridge Over Troubled Water', 'genre': 'Folk Rock', 'year': 1970, 'acclaim': "Grammy winner, RS 500", 'tier': 'legendary', 'listen_score': 97},

            # === Reggae / Dub ===
            {'artist': 'Bob Marley', 'song': 'Redemption Song', 'genre': 'Reggae', 'year': 1980, 'acclaim': "One of the greatest songs, legendary", 'tier': 'legendary', 'listen_score': 98},
            {'artist': 'Lee \'Scratch\' Perry', 'song': 'Roast Fish & Cornbread', 'genre': 'Dub/Reggae', 'year': 1978, 'acclaim': "Dub pioneer, hugely influential", 'tier': 'cult', 'listen_score': 95},

            # === Latin ===
            {'artist': 'Celia Cruz', 'song': 'La Vida Es Un Carnaval', 'genre': 'Salsa', 'year': 1997, 'acclaim': "Queen of Salsa, cultural icon", 'tier': 'legendary', 'listen_score': 97},
            {'artist': 'Caetano Veloso', 'song': 'Tropicália', 'genre': 'Brazilian Tropicalia', 'year': 1968, 'acclaim': "Founded Tropicalia movement, legendary", 'tier': 'legendary', 'listen_score': 96},
            {'artist': 'Rosalía', 'song': 'Malamente', 'genre': 'Flamenco Pop', 'year': 2018, 'acclaim': "Grammy winner, revolutionized flamenco", 'tier': 'modern_classic', 'listen_score': 96},

            # === Soundtrack / Score ===
            {'artist': 'Hans Zimmer', 'song': 'Time (Inception)', 'genre': 'Film Score', 'year': 2010, 'acclaim': "1B+ streams, one of the most iconic modern scores", 'tier': 'modern_classic', 'listen_score': 98},
            {'artist': 'Ennio Morricone', 'song': 'The Ecstasy of Gold', 'genre': 'Film Score', 'year': 1966, 'acclaim': "One of the greatest film compositions ever", 'tier': 'legendary', 'listen_score': 98},
            {'artist': 'Joe Hisaishi', 'song': 'Merry-Go-Round of Life', 'genre': 'Film Score', 'year': 2004, 'acclaim': "Studio Ghibli, universally beloved", 'tier': 'modern_classic', 'listen_score': 97},

            # === Contemporary / Modern Pop ===
            {'artist': 'Adele', 'song': 'Someone Like You', 'genre': 'Pop', 'year': 2011, 'acclaim': "1B+ streams, Grammy winner, cultural phenomenon", 'tier': 'modern_classic', 'listen_score': 97},
            {'artist': 'Amy Winehouse', 'song': 'Back to Black', 'genre': 'Soul/Pop', 'year': 2006, 'acclaim': "Grammy winner, RS 500, modern classic", 'tier': 'modern_classic', 'listen_score': 97},
            {'artist': 'Lana Del Rey', 'song': 'Video Games', 'genre': 'Indie Pop', 'year': 2011, 'acclaim': "Critically acclaimed, defined a sound", 'tier': 'modern_classic', 'listen_score': 96},
        ]

    TIER_LABELS = {
        'legendary': '🏆 Legendary',
        'modern_classic': '⭐ Modern Classic',
        'classic': '💎 Classic',
        'cult': '🔥 Cult Favorite',
    }

    def get_challenges(self, count: int = 20) -> List[Dict]:
        """Get a set of critically acclaimed songs outside your listening zone.
        Filters songs already in your collection, personalizes the challenge reason,
        and ranks by how far outside your zone they are.
        """
        db = self._build_challenge_db()
        
        # Determine which genres you already love (have rated songs in)
        genre_dist = self._get_genre_distribution()
        loved_genres = set()
        for g, data in genre_dist.items():
            if data.get('count', 0) >= 2 and data.get('avg_rating', 0) >= 80:
                loved_genres.add(g)
        
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
            
            if not genre_loved and not artist_known:
                outside_score = 3  # Completely outside
                zone_note = f"No songs in '{song['genre']}' in your collection"
            elif not genre_loved and artist_known:
                outside_score = 2  # Artist known but genre unexplored
                info = self.all_artists.get(song['artist'], {})
                avg = round(sum(info.get('ratings', []) or []) / max(len(info.get('ratings', []) or []), 1), 1) if info.get('ratings') else '?'
                zone_note = f"You know {song['artist']} (avg {avg}/100) but haven't explored {song['genre']}"
            else:
                outside_score = 1  # Within your zone
                zone_note = f"You already enjoy {song['genre']} — this is a widely-loved classic you might've missed"
            
            # Bonus points for genres completely absent from your data
            genre_total = genre_dist.get(song['genre'], {}).get('count', 0)
            if genre_total == 0:
                outside_score += 1
                zone_note = f"Brand new genre: '{song['genre']}' — you haven't rated any songs in this genre!"
            
            challenges.append({
                **song,
                'already_owned': False,
                'outside_score': outside_score,
                'zone_note': zone_note,
            })
        
        # Sort: highest outside score first (biggest challenge), then listen_score
        challenges.sort(key=lambda x: (-x['outside_score'], -x.get('listen_score', 0)))
        
        # Deduplicate by artist (don't show too many from same artist)
        seen_artists = set()
        deduped = []
        for c in challenges:
            if c['artist'] not in seen_artists or sum(1 for d in deduped if d['genre'] == c['genre']) < 2:
                seen_artists.add(c['artist'])
                deduped.append(c)
            if len(deduped) >= count:
                break
        
        # Group by tier
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
            'your_zones': {
                'loved_genres': sorted(loved_genres),
                'known_artists_count': len(known_artists),
            }
        }

    # ------------------------------------------------------------------
    # Genre reclassification — expanded keywords + MusicBrainz API
    # ------------------------------------------------------------------

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
        
        # Build a reverse mapping: keyword → our genre
        tag_to_genre = {}
        for genre, keywords in self.genre_keywords.items():
            for kw in keywords:
                tag_to_genre[kw] = genre
        
        # Score each genre by matching tags
        scores = defaultdict(int)
        for tag in tags:
            t = tag.lower().strip()
            # Direct match
            if t in tag_to_genre:
                scores[tag_to_genre[t]] += 3
            # Partial match
            for genre, keywords in self.genre_keywords.items():
                for kw in keywords:
                    if kw in t or t in kw:
                        scores[genre] += 1
                        break
        
        if scores:
            return max(scores, key=scores.get)
        return 'Uncategorized'

    def reclassify_genres(self, use_musicbrainz: bool = False) -> Dict:
        """Re-run genre classification with expanded keywords and optional MusicBrainz fallback.
        Returns before/after stats for the genre distribution.
        
        Args:
            use_musicbrainz: If True, uses MusicBrainz API for remaining uncategorized artists.
        """
        # Get old distribution
        old_dist = self._get_genre_distribution()
        old_uncat = old_dist.get('Uncategorized', {}).get('count', 0)
        
        # Force re-initialize keywords (expanded version)
        self._init_genre_keywords()
        
        # Get new distribution with expanded keywords only
        new_dist = self._get_genre_distribution()
        new_uncat = new_dist.get('Uncategorized', {}).get('count', 0)
        
        # Build artist genre cache from MusicBrainz if requested
        mb_stats = {'looked_up': 0, 'found': 0, 'reclassified': 0}
        if use_musicbrainz:
            # Find artists with uncategorized songs
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
                if not matched:
                    artists = self._extract_artists(r['title'])
                    for a in artists:
                        if a and a != 'Announcement':
                            artist_uncat[a] += 1
            
            # Look up top uncategorized artists via MusicBrainz
            sorted_artists = sorted(artist_uncat.items(), key=lambda x: -x[1])[:200]
            for artist_name, cnt in sorted_artists:
                mb_stats['looked_up'] += 1
                genre = self._classify_artist_genre_musicbrainz(artist_name)
                if genre != 'Uncategorized':
                    # Populate the **proper** cache — _get_genre_distribution() uses this
                    self._artist_genre_cache[artist_name] = genre
                    mb_stats['found'] += 1
                    mb_stats['reclassified'] += cnt
            
            # Recalculate with cache fallback
            new_dist = self._get_genre_distribution()
            new_uncat = new_dist.get('Uncategorized', {}).get('count', 0)
        
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
            'musicbrainz': mb_stats if use_musicbrainz else None,
        }

    def _generate_weekly_message(self) -> str:
        """Generate a personalized weekly message."""
        avg = round(sum(self.ratings)/len(self.ratings), 1)
        month = datetime.now().strftime('%B')
        
        messages = [
            f"This week's discoveries are tailored to your {avg}/100 average taste. Happy listening this {month}!",
            f"Based on your {len(self.ratings)} rated songs, here are some fresh tracks for your {month} playlist.",
            f"Your taste has evolved across {len([r for r in self.rows if r['date'] and r['date'][:4] < '2020'])} pre-2020 songs and counting. Time to add more!",
        ]
        return messages[hash(datetime.now().strftime('%W')) % len(messages)]

    # ------------------------------------------------------------------
    # Letter grade extraction & tone-based rating inference (backfill)
    # ------------------------------------------------------------------

    LETTER_GRADE_MAP = {
        'A+': 98, 'A': 95, 'A-': 92,
        'B+': 88, 'B': 85, 'B-': 82,
        'C+': 78, 'C': 75, 'D': 65, 'F': 50,
    }

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
