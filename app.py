"""
app.py - Flask backend for the Music Taste Analyzer & Recommender
"""

import os
import json
import sys
import csv
import re
from datetime import datetime
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from src.taste_engine import TasteEngine
from src.spotify_helper import SpotifyHelper


def _safe_int(value, default):
    """Convert value to int safely, returning default on failure."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)


@app.after_request
def _no_cache_api(resp):
    """Never let browsers cache API responses.

    Without this, the browser's HTTP cache can serve a stale copy of e.g.
    /api/challenges that predates a ban — so an ignored song "reappears"
    after a restart even though the server correctly excluded it. With a
    no-store policy every view always re-fetches fresh state.
    """
    if resp.mimetype == "application/json" and resp.status_code == 200:
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers.pop("Last-Modified", None)
        resp.headers["Expires"] = "0"
    return resp

# Initialize engines
taste_engine = TasteEngine('data/posts_tails.csv')
spotify = SpotifyHelper()

# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    return send_from_directory('templates', 'index.html')

@app.route('/api/stats')
def get_stats():
    """Get overall taste statistics and dashboard data."""
    return jsonify(taste_engine.get_stats())

@app.route('/api/blind-spots')
def get_blind_spots():
    """Get genre blind spots and unexplored musical territory."""
    return jsonify(taste_engine.get_blind_spots())

@app.route('/api/outliers')
def get_outliers():
    """Statistical outlier detection — songs and artists that break your patterns."""
    return jsonify(taste_engine.get_outliers())

@app.route('/api/favorite-artists')
def get_favorite_artists():
    """Get your personal favorite artists with genre info and collection stats.
    Used by the dashboard and recommender to prioritize similar artists."""
    return jsonify(taste_engine.get_favorite_artists())

@app.route('/api/constellation')
def get_constellation():
    """Get artist similarity network data."""
    return jsonify(taste_engine.get_constellation())

@app.route('/api/evolution')
def get_evolution():
    """Get taste evolution over time data."""
    return jsonify(taste_engine.get_evolution())

@app.route('/api/geography')
def get_geography():
    """Get geographic listening distribution."""
    return jsonify(taste_engine.get_geography())

@app.route('/api/recommendations')
def get_recommendations():
    """Get personalized song recommendations."""
    style = request.args.get('style', 'all')
    data = taste_engine.get_recommendations(style)
    for cat_data in data.values():
        _annotate_listened(cat_data.get('recommendations', []))
    return jsonify(data)

@app.route('/api/reverse-me')
def get_reverse_me():
    """Get recommendations for 'Reverse Me' — what someone with opposite taste would enjoy."""
    data = taste_engine.get_reverse_me()
    return jsonify(data)

@app.route('/api/weekly-discovery')
def get_weekly_discovery():
    """Get this week's personalized discovery picks."""
    data = taste_engine.get_weekly_discovery()
    _annotate_listened(data.get('picks', []))
    return jsonify(data)

@app.route('/api/search-spotify')
def search_spotify():
    """Search for a track on Spotify."""
    title = request.args.get('title', '')
    artist = request.args.get('artist', '')
    if not title:
        return jsonify({'error': 'No title provided'}), 400
    
    result = spotify.search_track(title, artist)
    return jsonify(result or {'error': 'Not found or Spotify not configured'})

@app.route('/api/spotify-status')
def spotify_status():
    """Check if Spotify integration is available."""
    return jsonify({
        'available': spotify.is_available(),
        'message': 'Spotify connected!' if spotify.is_available() else 'Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET env vars to enable'
    })

@app.route('/api/songs')
def get_songs():
    """Get all songs with optional filtering."""
    sort_by = request.args.get('sort', 'rating')
    order = request.args.get('order', 'desc')
    limit = _safe_int(request.args.get('limit', 50), 50)
    offset = _safe_int(request.args.get('offset', 0), 0)
    min_rating = request.args.get('min_rating')
    search = request.args.get('search', '')

    all_songs = []
    for r in taste_engine.rated_entries:
        song = {
            'title': r.get('title', ''),
            'rating': int(r['rating']) if r.get('rating') else 0,
            'date': r.get('date', ''),
            'preview': (r.get('tail') or '')[:200].replace('\n', ' ')
        }
        all_songs.append(song)

    # Filter
    if search:
        search_lower = search.lower()
        all_songs = [s for s in all_songs if search_lower in s['title'].lower()]
    
    if min_rating:
        all_songs = [s for s in all_songs if s['rating'] >= int(min_rating)]

    # Sort
    reverse = order == 'desc'
    all_songs.sort(key=lambda x: x.get(sort_by, 0) if isinstance(x.get(sort_by, 0), (int, float)) else str(x.get(sort_by, '')), reverse=reverse)

    total = len(all_songs)
    all_songs = all_songs[offset:offset + limit]

    return jsonify({'songs': all_songs, 'total': total})

@app.route('/api/search-history')
def search_history():
    """Search through review history."""
    query = request.args.get('q', '')
    if not query:
        return jsonify({'results': [], 'total': 0})
    
    results = []
    for r in taste_engine.rows:
        title = r.get('title', '')
        tail = r.get('tail', '')
        if query.lower() in title.lower() or query.lower() in tail.lower():
            results.append({
                'title': title[:80],
                'rating': int(r['rating']) if r.get('rating') else None,
                'date': r.get('date', ''),
                'preview': (tail or '')[:300].replace('\n', ' ')
            })
    
    return jsonify({'results': results[:30], 'total': len(results)})

@app.route('/api/export')
def export_data():
    """Export taste data as JSON."""
    return jsonify({
        'stats': taste_engine.get_stats(),
        'blind_spots': taste_engine.get_blind_spots(),
        'evolution': taste_engine.get_evolution(),
        'recommendations': taste_engine.get_recommendations()
    })


# ---------------------------------------------------------------------------
# Quick-Add API — Add songs you discover to your CSV
# ---------------------------------------------------------------------------

@app.route('/api/add-song', methods=['POST'])
def add_song():
    """Add a song you just listened to. Appends to posts_tails.csv.
    Body: { title, rating?, notes? }
    """
    body = request.get_json(silent=True)
    if not body:
        return jsonify({'error': 'Request body required', 'success': False}), 400

    title = (body.get('title') or '').strip()
    if not title:
        return jsonify({'error': 'title is required', 'success': False}), 400

    raw_rating = body.get('rating', '')
    date = datetime.now().strftime('%Y-%m-%d')
    tail = body.get('notes', '').strip()

    rating_str = ''
    if raw_rating:
        try:
            r = int(raw_rating)
            if r < 0 or r > 100:
                return jsonify({'error': 'rating must be 0–100', 'success': False}), 400
            rating_str = str(r)
        except (ValueError, TypeError):
            return jsonify({'error': 'rating must be an integer 0–100', 'success': False}), 400

    # Check for duplicates before appending
    artists = taste_engine._extract_artists(title)
    artist_name = artists[0] if artists else ''
    song_name = title
    # Try to extract just the song part
    m = re.search(r'^(.+?)\s*[\(\–\-]', title)
    if m:
        song_name = m.group(1).strip()
    dup_check = taste_engine.check_song_exists(artist_name, song_name, timeout_sec=3.0)
    if dup_check.get('exists'):
        existing = dup_check.get('title') or title
        return jsonify({
            'error': f'This song already exists in your collection (matched: {existing}). Duplicate not added.',
            'success': False,
            'duplicate': True,
            'matched_title': existing,
        }), 409

    # Append to CSV
    try:
        with open(taste_engine.csv_path, 'a', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([date, rating_str, title, tail])
    except Exception as e:
        return jsonify({'error': f'Failed to save: {e}', 'success': False}), 500

    # Reload engine so next query picks up the new data
    taste_engine._load_data()
    taste_engine._classify_rows()
    taste_engine._build_artist_index()
    taste_engine._build_song_index()

    return jsonify({
        'success': True,
        'song': {
            'title': title,
            'rating': int(rating_str) if rating_str else None,
            'date': date,
            'notes': tail
        }
    }), 201


@app.route('/api/deduplicate', methods=['POST'])
def deduplicate():
    """Remove duplicate songs from the collection.
    Rewrites the CSV with duplicates removed, keeping the better-rated entry.
    """
    result = taste_engine.deduplicate(write_back=True)
    if result['removed'] > 0:
        # Reload indices after dedup
        taste_engine._classify_rows()
        taste_engine._build_artist_index()
        taste_engine._build_song_index()
    return jsonify({'success': True, **result})


@app.route('/api/batch-add', methods=['POST'])
def batch_add():
    """Add multiple songs at once. Body: { songs: [{ title, rating?, notes? }] }"""
    body = request.get_json(silent=True)
    if not body or 'songs' not in body or not isinstance(body['songs'], list):
        return jsonify({'error': 'Body must contain a songs array', 'success': False}), 400

    songs = body['songs']
    if not songs:
        return jsonify({'error': 'songs array is empty', 'success': False}), 400

    date = datetime.now().strftime('%Y-%m-%d')
    added = 0
    errors = []

    for song in songs:
        title = (song.get('title') or '').strip()
        if not title:
            errors.append('Skipped entry with no title')
            continue

        raw_rating = song.get('rating', '')
        rating_str = ''
        if raw_rating:
            try:
                r = int(raw_rating)
                if 0 <= r <= 100:
                    rating_str = str(r)
                else:
                    errors.append(f'Invalid rating {raw_rating} for "{title[:40]}"')
                    continue
            except (ValueError, TypeError):
                pass

        tail = song.get('notes', '').strip()
        try:
            with open(taste_engine.csv_path, 'a', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([date, rating_str, title, tail])
            added += 1
        except Exception as e:
            errors.append(f'Failed to save "{title[:40]}": {e}')

    # Reload engine
    if added > 0:
        taste_engine._load_data()
        taste_engine._classify_rows()
        taste_engine._build_artist_index()

    return jsonify({
        'success': True,
        'added': added,
        'errors': errors,
        'total_entries': len(taste_engine.rows)
    }), 201 if added > 0 else 200


# ---------------------------------------------------------------------------
# CSV import helper (for pasting entire list of songs)
# ---------------------------------------------------------------------------

@app.route('/api/import-songs', methods=['POST'])
def import_songs():
    """Import songs from a pasted block of text.
    Expects lines like: Artist - Song | 85 | some notes
    or: Title (Artist, Year) | 92 | review text
    """
    body = request.get_json(silent=True)
    if not body or not body.get('text', '').strip():
        return jsonify({'error': 'text field is required', 'success': False}), 400

    lines = body['text'].strip().split('\n')
    date = datetime.now().strftime('%Y-%m-%d')
    added = 0
    errors = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Try parsing formats
        title = line
        rating_str = ''
        notes = ''

        # Format: title | rating | notes
        if '|' in line:
            parts = [p.strip() for p in line.split('|', 2)]
            title = parts[0]
            if len(parts) >= 2:
                try:
                    r = int(parts[1])
                    if 0 <= r <= 100:
                        rating_str = str(r)
                except ValueError:
                    notes = parts[1]  # Could be notes instead
            if len(parts) >= 3:
                notes = parts[2]
        else:
            # Maybe rating is at the end: Title (Artist, Year) - 85
            m = re.search(r'[-–]\s*(\d{1,3})\s*/\s*100\s*$', line)
            if m:
                r = int(m.group(1))
                if 0 <= r <= 100:
                    rating_str = str(r)
                    title = line[:m.start()].strip()

        if not title:
            continue

        # Remove common formatting prefixes
        title = title.lstrip('0123456789.-– ').strip()
        if title.startswith('"') and title.endswith('"'):
            title = title[1:-1]

        try:
            with open(taste_engine.csv_path, 'a', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([date, rating_str, title, notes])
            added += 1
        except Exception as e:
            errors.append(f'Failed for "{title[:40]}": {e}')

    if added > 0:
        taste_engine._load_data()
        taste_engine._classify_rows()
        taste_engine._build_artist_index()
        taste_engine._build_song_index()

    return jsonify({'success': True, 'added': added, 'errors': errors}), 201 if added > 0 else 200


# ---------------------------------------------------------------------------
# Song existence check — O(1) hash lookup
# ---------------------------------------------------------------------------

@app.route('/api/check-song', methods=['POST'])
def check_song():
    """Check if an artist+song combo already exists in your collection.
    Body: { artist, song }  or  { title }
    Uses normalized hash set for O(1) lookup.
    """
    body = request.get_json(silent=True)
    if not body:
        return jsonify({'error': 'Request body required'}), 400

    artist = body.get('artist', '')
    song = body.get('song', '')

    # If only a raw title is given, try to parse it
    if not song and body.get('title'):
        parts = taste_engine._extract_artists(body['title'])
        raw = body['title']
        m = re.search(r'^(.+?)\s*\(', raw)
        song = (m.group(1) if m else raw).strip()
        artist = parts[0] if parts else ''

    if not song:
        return jsonify({'error': 'song or title field required'}), 400

    result = taste_engine.check_song_exists(artist, song)
    return jsonify(result)


@app.route('/api/known-songs')
def known_songs():
    """Return the normalized song signatures for client-side duplicate checking.
    Returns hashes (not raw titles) to keep payload small.
    """
    return jsonify({
        'count': len(taste_engine.known_sigs),
        'sigs': list(taste_engine.known_sigs),
        'titles': list(taste_engine.known_titles)
    })


# ---------------------------------------------------------------------------
# Year Conquest — Top songs per year you haven't reviewed yet
# ---------------------------------------------------------------------------

CONQUEST_PATH = 'data/year_conquest.json'

def _load_year_conquest_db() -> dict:
    """Load the curated year conquest song database."""
    try:
        with open(CONQUEST_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _get_reviewed_sigs() -> set:
    """Get normalized signatures of all songs the user has already reviewed.
    
    Returns BOTH the raw normalized title AND parsed artist|song keys
    so we can match regardless of word order in the CSV.
    """
    sigs = set()
    for entry in taste_engine.rated_entries:
        title = entry.get('title', '')
        if title:
            sigs.add(taste_engine._normalize_sig(title))
            # Also add parsed artist|song so 'Adele Rolling in the Deep'
            # matches 'Rolling in the Deep (Adele)'
            for artist, song in taste_engine._parse_title_candidates(title):
                sigs.add(taste_engine._normalize_sig(f"{artist} {song}"))
                sigs.add(taste_engine._normalize_sig(f"{song} {artist}"))
    return sigs


@app.route('/api/year-conquest')
def get_year_conquest():
    """Get top unreviewed songs grouped by year, starting from a target year.
    Query params:
      start_year (int): year to start from (default 2011)
      count (int): max songs per year (default 5)
    Returns: { years: [{ year, songs: [{artist, song, acclaim}] }] }
    """
    start_year = _safe_int(request.args.get('start_year', 2011), 2011)
    per_year = _safe_int(request.args.get('count', 5), 5)
    per_year = min(per_year, 15)

    db = _load_year_conquest_db()
    reviewed = _get_reviewed_sigs()

    result_years = []
    for year_str, songs in db.items():
        year = int(year_str)
        if year > start_year:
            continue

        unreviewed = []
        for s in songs:
            # Fast path: check normalized signature first (O(1))
            sig = taste_engine._normalize_sig(f"{s['artist']} {s['song']}")
            if sig in reviewed:
                continue

            # Fuzzy path: use check_song_exists for edge cases
            # (different formatting, Latin normalization, etc.)
            result = taste_engine.check_song_exists(
                s['artist'], s['song'], timeout_sec=1.0
            )
            if result['exists']:
                continue

            unreviewed.append(s)
            if len(unreviewed) >= per_year:
                break

        result_years.append({
            'year': year,
            'total_in_db': len(songs),
            'unreviewed_count': len(unreviewed),
            'songs': unreviewed,
        })

    return jsonify({'years': result_years})


# ---------------------------------------------------------------------------
# Challenge Section — Critically acclaimed songs outside your zone
# ---------------------------------------------------------------------------

@app.route('/api/challenges')
def get_challenges():
    """Get a curated set of critically acclaimed songs outside your listening zone.
    Filters by dedup, ranks by how far outside your comfort zone, groups by tier.
    Supports mode=outside_zone (default) or mode=opposite_taste to push lowest-rated genres.
    """
    count = _safe_int(request.args.get('count', 20), 20)
    mode = request.args.get('mode', 'outside_zone')
    popularity_threshold = _safe_int(request.args.get('popularity_threshold', 85), 85)
    popularity_threshold = max(0, min(100, popularity_threshold))  # clamp 0-100
    data = taste_engine.get_challenges(count=count, mode=mode, popularity_threshold=popularity_threshold)
    _annotate_listened(data.get('challenges', []))
    return jsonify(data)


# ---------------------------------------------------------------------------
# Backfill Ratings — Recover missing ratings from letter grades & tone
# ---------------------------------------------------------------------------

@app.route('/api/backfill-preview')
def backfill_preview():
    """Preview what backfilling would do without modifying the CSV.
    Shows before/after stats and the list of changes.
    """
    method = request.args.get('method', 'all')
    # Use cached data — don't re-read from disk
    result = taste_engine.backfill_ratings(preview=True, method=method)
    return jsonify(result)


@app.route('/api/backfill-ratings', methods=['POST'])
def backfill_ratings():
    """Apply backfill: extract letter grades and infer tone ratings,
    write results to CSV, and reload the engine.
    Body: { method?: "all" | "letter" | "tone" }
    """
    body = request.get_json(silent=True) or {}
    method = body.get('method', 'all')
    if method not in ('all', 'letter', 'tone'):
        return jsonify({'error': 'method must be all, letter, or tone'}), 400

    try:
        result = taste_engine.backfill_ratings(preview=False, method=method)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': f'Backfill failed: {e}'}), 500


# ---------------------------------------------------------------------------
# Genre Reclassification — expanded keywords + MusicBrainz API fallback
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Uncategorized Breakdown — detailed analysis of unclassified songs
# ---------------------------------------------------------------------------

@app.route('/api/uncategorized-breakdown')
def get_uncategorized_breakdown():
    """Get a detailed breakdown of all currently uncategorized songs,
    grouped by known artists, unknown artists, no-artist entries, etc.
    Helps users understand what's falling through the cracks and manually
    fix the classification.
    """
    return jsonify(taste_engine.get_uncategorized_breakdown())

@app.route('/api/reclassify-genres', methods=['POST'])
def reclassify_genres():
    """Re-run genre classification with expanded keywords.
    Body: { use_musicbrainz?: bool } — if true, fetches MusicBrainz tags for uncategorized artists.
    Returns before/after stats so the frontend can show what changed.
    """
    body = request.get_json(silent=True) or {}
    use_mb = body.get('use_musicbrainz', False)
    try:
        result = taste_engine.reclassify_genres(use_musicbrainz=use_mb)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': f'Reclassification failed: {e}'}), 500

# ---------------------------------------------------------------------------
# Ban List API — manage blocked genres, artists, and songs
# ---------------------------------------------------------------------------

@app.route('/api/ban-list', methods=['GET'])
def get_ban_list():
    """Get the current ban list."""
    return jsonify(taste_engine.ban_list)


@app.route('/api/ban-list/add', methods=['POST'])
def add_to_ban_list():
    """Add an item to the ban list.
    Body: { type: "genres"|"artists"|"songs", value: "ItemName" }
    """
    body = request.get_json(silent=True)
    if not body or 'type' not in body or 'value' not in body:
        return jsonify({'error': 'Must specify type and value'}), 400

    ban_type = body['type']
    value = body['value'].strip()

    if ban_type not in ('genres', 'artists', 'songs'):
        return jsonify({'error': 'type must be genres, artists, or songs'}), 400
    if not value:
        return jsonify({'error': 'value must not be empty'}), 400

    # Load current ban list
    try:
        with open(taste_engine.ban_list_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {'genres': [], 'artists': [], 'songs': []}

    # Add if not already present (case-insensitive check)
    existing_lower = [v.lower() for v in data.get(ban_type, [])]
    if value.lower() not in existing_lower:
        data.setdefault(ban_type, []).append(value)
        # Save
        with open(taste_engine.ban_list_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        # Reload in engine
        taste_engine._load_ban_list()
        return jsonify({'success': True, 'ban_list': taste_engine.ban_list}), 200
    else:
        return jsonify({'success': True, 'ban_list': taste_engine.ban_list, 'message': 'Already in ban list'}), 200


@app.route('/api/ban-list/remove', methods=['POST'])
def remove_from_ban_list():
    """Remove an item from the ban list.
    Body: { type: "genres"|"artists"|"songs", value: "ItemName" }
    """
    body = request.get_json(silent=True)
    if not body or 'type' not in body or 'value' not in body:
        return jsonify({'error': 'Must specify type and value'}), 400

    ban_type = body['type']
    value = body['value'].strip()

    if ban_type not in ('genres', 'artists', 'songs'):
        return jsonify({'error': 'type must be genres, artists, or songs'}), 400

    try:
        with open(taste_engine.ban_list_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {'genres': [], 'artists': [], 'songs': []}

    # Remove case-insensitively
    lower_value = value.lower()
    original = data.get(ban_type, [])
    data[ban_type] = [v for v in original if v.lower() != lower_value]

    with open(taste_engine.ban_list_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    taste_engine._load_ban_list()

    return jsonify({'success': True, 'ban_list': taste_engine.ban_list}), 200

# ---------------------------------------------------------------------------
# Listened tracking — mark recommended songs as listened / not listened
# ---------------------------------------------------------------------------
# Persists to data/listened.json so it survives restarts and can be committed
# to git like the rest of your taste data. Schema:
#   {"listened": {"<normalized artist+song sig>": {"artist": ..., "song": ..., "listened_at": "YYYY-MM-DD"}}}

LISTENED_PATH = 'data/listened.json'


def _load_listened() -> dict:
    """Load the listened store as {sig: {artist, song, listened_at}}."""
    try:
        with open(LISTENED_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        store = data.get('listened', {}) if isinstance(data, dict) else {}
        return store if isinstance(store, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_listened(store: dict) -> None:
    with open(LISTENED_PATH, 'w', encoding='utf-8') as f:
        json.dump({'listened': store}, f, indent=2, ensure_ascii=False)


def _listened_sig(artist: str, song: str) -> str:
    """Stable signature for an artist+song, matching the dedup normalization."""
    return TasteEngine._normalize_sig(f"{artist} {song}")


def _annotate_listened(items) -> None:
    """Add a `listened` boolean to each rec/pick dict (in place)."""
    store = _load_listened()
    for item in items:
        item['listened'] = _listened_sig(item.get('artist', ''), item.get('song', '')) in store


@app.route('/api/listened')
def get_listened():
    """Get every tracked listened entry."""
    store = _load_listened()
    entries = [
        {
            'sig': sig,
            'artist': v.get('artist', ''),
            'song': v.get('song', ''),
            'listened_at': v.get('listened_at', ''),
        }
        for sig, v in store.items()
    ]
    return jsonify({'entries': entries, 'count': len(entries)})


@app.route('/api/mark-listened', methods=['POST'])
def mark_listened():
    """Mark a recommended song as listened (or un-listened).
    Body: { artist, song, listened?: bool } — listened defaults to true.
    """
    body = request.get_json(silent=True)
    if not body:
        return jsonify({'error': 'Request body required'}), 400

    artist = (body.get('artist') or '').strip()
    song = (body.get('song') or '').strip()
    if not artist or not song:
        return jsonify({'error': 'artist and song are required'}), 400

    listened = bool(body.get('listened', True))
    store = _load_listened()
    sig = _listened_sig(artist, song)

    if listened:
        store[sig] = {
            'artist': artist,
            'song': song,
            'listened_at': datetime.now().strftime('%Y-%m-%d'),
        }
    else:
        store.pop(sig, None)

    _save_listened(store)
    return jsonify({'success': True, 'sig': sig, 'listened': listened, 'count': len(store)})


# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------

@app.route('/static/<path:path>')
def static_files(path):
    return send_from_directory('static', path)

@app.route('/js/<path:path>')
def js_files(path):
    return send_from_directory('static/js', path)

@app.route('/css/<path:path>')
def css_files(path):
    return send_from_directory('static/css', path)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    # Set stdout encoding for Windows compatibility
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass
    
    port = int(os.environ.get('PORT', 5000))
    spotify_status = 'Connected' if spotify.is_available() else 'Not configured (set SPOTIFY env vars)'
    print(f"[Music Taste Analyzer] Running on http://localhost:{port}")
    print(f"  Data: {len(taste_engine.rows)} entries, {len(taste_engine.ratings)} rated songs")
    print(f"  Spotify: {spotify_status}")
    app.run(debug=False, host='0.0.0.0', port=port, threaded=True)
