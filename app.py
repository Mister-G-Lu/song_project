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
from taste_engine import TasteEngine
from spotify_helper import SpotifyHelper

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)

# Initialize engines
taste_engine = TasteEngine('posts_tails.csv')
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

@app.route('/api/constellation')
def get_constellation():
    """Get artist similarity network data."""
    return jsonify(taste_engine.get_constellation())

@app.route('/api/evolution')
def get_evolution():
    """Get taste evolution over time data."""
    return jsonify(taste_engine.get_evolution())

@app.route('/api/recommendations')
def get_recommendations():
    """Get personalized song recommendations."""
    style = request.args.get('style', 'all')
    return jsonify(taste_engine.get_recommendations(style))

@app.route('/api/weekly-discovery')
def get_weekly_discovery():
    """Get this week's personalized discovery picks."""
    return jsonify(taste_engine.get_weekly_discovery())

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
    limit = int(request.args.get('limit', 50))
    offset = int(request.args.get('offset', 0))
    min_rating = request.args.get('min_rating')
    search = request.args.get('search', '')

    all_songs = []
    for r in taste_engine.rated_entries:
        song = {
            'title': r['title'],
            'rating': int(r['rating']),
            'date': r['date'],
            'preview': r['tail'][:200].replace('\n', ' ')
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
        if query.lower() in r['title'].lower() or query.lower() in r['tail'].lower():
            results.append({
                'title': r['title'][:80],
                'rating': int(r['rating']) if r['rating'] else None,
                'date': r['date'],
                'preview': r['tail'][:300].replace('\n', ' ')
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

    # Append to CSV
    try:
        with open(taste_engine.csv_path, 'a', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([date, rating_str, title, tail])
    except Exception as e:
        return jsonify({'error': f'Failed to save: {e}', 'success': False}), 500

    # Reload engine so next query picks up the new data
    taste_engine._load_data()
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
# Challenge Section — Critically acclaimed songs outside your zone
# ---------------------------------------------------------------------------

@app.route('/api/challenges')
def get_challenges():
    """Get a curated set of critically acclaimed songs outside your listening zone.
    Filters by dedup, ranks by how far outside your comfort zone, groups by tier.
    """
    count = int(request.args.get('count', 20))
    return jsonify(taste_engine.get_challenges(count=count))


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
