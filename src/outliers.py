"""
outliers.py - Statistical outlier detection for TasteScope
Computes songs/artists that break the user's own rating patterns.
"""

from collections import defaultdict
from typing import List, Dict


def detect_outliers(rated_entries: list, all_artists: dict, ratings: list,
                    get_genre_dist_fn=None) -> Dict:
    """Compute all outlier categories and return structured data.

    Categories:
      artist_volatility  – artists with huge rating spread
      genre_rebels       – songs rated far from their genre average
      guilty_pleasures   – high-rated songs in usually-disliked genres
      disappointments    – low-rated songs in usually-loved genres
      one_hit_wonders    – one standout song far above an artist's other tracks
      rating_surprises   – songs 25+ pts away from your overall average
    """
    if not rated_entries or not ratings:
        return {'categories': {}, 'summary': {}}

    overall_avg = sum(ratings) / len(ratings) if ratings else 80

    # Build per-genre avg ratings
    genre_ratings = defaultdict(list)
    for r in rated_entries:
        g = r.get('_genre') or 'Uncategorized'
        if g != 'Uncategorized':
            genre_ratings[g].append(int(r['rating']))
    genre_avgs = {g: sum(rs)/len(rs) for g, rs in genre_ratings.items() if len(rs) >= 3}

    # ---- 1. Artist Volatility ----
    artist_volatility = []
    for artist, info in all_artists.items():
        rs = info.get('ratings', [])
        if len(rs) < 2:
            continue
        spread = max(rs) - min(rs)
        if spread >= 25:
            avg = sum(rs) / len(rs)
            artist_volatility.append({
                'artist': artist,
                'avg_rating': round(avg, 1),
                'min_rating': min(rs),
                'max_rating': max(rs),
                'spread': spread,
                'song_count': len(rs),
                'genre': info.get('genre', 'Uncategorized'),
            })
    artist_volatility.sort(key=lambda x: -x['spread'])

    # ---- 2. Genre Rebels (songs 20+ pts from genre avg) ----
    genre_rebels = []
    for r in rated_entries:
        g = r.get('_genre') or 'Uncategorized'
        if g not in genre_avgs:
            continue
        rating = int(r['rating'])
        diff = rating - genre_avgs[g]
        if abs(diff) >= 20:
            artists = _extract_artists_from_title(r.get('title', ''))
            genre_rebels.append({
                'title': r.get('title', ''),
                'artist': artists[0] if artists else '',
                'rating': rating,
                'genre': g,
                'genre_avg': round(genre_avgs[g], 1),
                'diff': round(diff, 1),
                'direction': 'above' if diff > 0 else 'below',
            })
    genre_rebels.sort(key=lambda x: -abs(x['diff']))

    # ---- 3. Guilty Pleasures (high-rated in low-rated genres) ----
    # Genres you avg <70 but rated a song 85+
    low_avg_genres = {g for g, avg in genre_avgs.items() if avg < 70}
    guilty_pleasures = []
    for r in rated_entries:
        g = r.get('_genre') or 'Uncategorized'
        if g not in low_avg_genres:
            continue
        rating = int(r['rating'])
        if rating >= 85:
            artists = _extract_artists_from_title(r.get('title', ''))
            guilty_pleasures.append({
                'title': r.get('title', ''),
                'artist': artists[0] if artists else '',
                'rating': rating,
                'genre': g,
                'genre_avg': round(genre_avgs.get(g, 0), 1),
            })
    guilty_pleasures.sort(key=lambda x: -x['rating'])

    # ---- 4. Disappointments (low-rated in high-rated genres) ----
    # Genres you avg >85 but rated a song <60
    high_avg_genres = {g for g, avg in genre_avgs.items() if avg > 85}
    disappointments = []
    for r in rated_entries:
        g = r.get('_genre') or 'Uncategorized'
        if g not in high_avg_genres:
            continue
        rating = int(r['rating'])
        if rating < 60:
            artists = _extract_artists_from_title(r.get('title', ''))
            disappointments.append({
                'title': r.get('title', ''),
                'artist': artists[0] if artists else '',
                'rating': rating,
                'genre': g,
                'genre_avg': round(genre_avgs.get(g, 0), 1),
            })
    disappointments.sort(key=lambda x: x['rating'])

    # ---- 5. One-Hit Wonders (one song 20+ pts above artist avg) ----
    one_hit_wonders = []
    for artist, info in all_artists.items():
        rs = info.get('ratings', [])
        if len(rs) < 2:
            continue
        other_avg = sum(rs) / len(rs)
        songs = info.get('songs', [])
        for song in songs:
            sr = int(song.get('rating', 0))
            if sr - other_avg >= 20:
                one_hit_wonders.append({
                    'title': song.get('title', ''),
                    'artist': artist,
                    'rating': sr,
                    'artist_avg': round(other_avg, 1),
                    'diff': round(sr - other_avg, 1),
                    'genre': info.get('genre', 'Uncategorized'),
                })
    one_hit_wonders.sort(key=lambda x: -x['diff'])

    # ---- 6. Rating Surprises (25+ pts from your overall avg) ----
    rating_surprises = []
    for r in rated_entries:
        rating = int(r['rating'])
        diff = rating - overall_avg
        if abs(diff) >= 25:
            artists = _extract_artists_from_title(r.get('title', ''))
            genre = r.get('_genre') or 'Uncategorized'
            rating_surprises.append({
                'title': r.get('title', ''),
                'artist': artists[0] if artists else '',
                'rating': rating,
                'overall_avg': round(overall_avg, 1),
                'diff': round(diff, 1),
                'direction': 'above' if diff > 0 else 'below',
                'genre': genre,
            })
    rating_surprises.sort(key=lambda x: -abs(x['diff']))

    return {
        'categories': {
            'artist_volatility': artist_volatility[:15],
            'genre_rebels': genre_rebels[:20],
            'guilty_pleasures': guilty_pleasures[:15],
            'disappointments': disappointments[:15],
            'one_hit_wonders': one_hit_wonders[:15],
            'rating_surprises': rating_surprises[:20],
        },
        'summary': {
            'overall_avg': round(overall_avg, 1),
            'total_songs': len(rated_entries),
            'total_artists': len([a for a in all_artists if all_artists[a].get('ratings')]),
            'volatile_artists': len(artist_volatility),
            'genre_rebels_count': len(genre_rebels),
            'guilty_pleasures_count': len(guilty_pleasures),
            'disappointments_count': len(disappointments),
            'one_hit_wonders_count': len(one_hit_wonders),
            'surprises_count': len(rating_surprises),
        },
    }


def _extract_artists_from_title(title: str) -> list:
    """Extract artist names from 'Song (Artist, Year)' or 'Artist - Song' patterns."""
    import re
    if not title:
        return []
    # Pattern: "Song Name (Artist, Year)"
    m = re.search(r'\(([^,]+),\s*\d{4}\)', title)
    if m:
        return [m.group(1).strip()]
    # Pattern: "Artist - Song" or "Artist – Song"
    m = re.match(r'^(.+?)\s*[-–—]\s*.+', title)
    if m:
        return [m.group(1).strip()]
    return []
