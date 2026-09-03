"""
Integration tests for app.py Flask API endpoints.
Tests all API routes with a test client.
"""

import json
import pytest
import sys
import os

# Set test mode to avoid stdout encoding issues
os.environ['FLASK_TESTING'] = '1'


@pytest.fixture
def client():
    """Create a test client for the Flask app."""
    from app import app
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


# ============================================================
# Core API Tests
# ============================================================

class TestRootEndpoint:
    """Test the root endpoint serving the frontend."""

    def test_root_returns_html(self, client):
        """Root should return the frontend HTML."""
        resp = client.get('/')
        assert resp.status_code == 200
        assert resp.content_type and 'html' in resp.content_type
        assert b'Music Taste Analyzer' in resp.data or b'TasteScope' in resp.data


class TestStatsEndpoint:
    """Test the /api/stats endpoint."""

    def test_stats_success(self, client):
        """Should return 200 with stats data."""
        resp = client.get('/api/stats')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert 'total_entries' in data
        assert 'rated_entries' in data
        assert 'avg_rating' in data

    def test_stats_values_range(self, client):
        """Stats should have reasonable values."""
        resp = client.get('/api/stats')
        data = json.loads(resp.data)
        assert data['total_entries'] >= 0
        assert 0 <= data['avg_rating'] <= 100
        assert data['min_rating'] <= data['max_rating']

    def test_stats_has_all_fields(self, client):
        """Should contain all expected sections."""
        resp = client.get('/api/stats')
        data = json.loads(resp.data)
        expected = ['rating_distribution', 'genre_distribution', 
                    'top_artists', 'top_songs', 'recent_reviews']
        for field in expected:
            assert field in data, f"Missing field: {field}"


class TestBlindSpotsEndpoint:
    """Test the /api/blind-spots endpoint."""

    def test_blind_spots_success(self, client):
        """Should return 200 with blind spots data."""
        resp = client.get('/api/blind-spots')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert 'top_loved_genres' in data
        assert 'blind_spots' in data

    def test_blind_spots_content(self, client):
        """Should have multiple blind spots."""
        resp = client.get('/api/blind-spots')
        data = json.loads(resp.data)
        assert len(data['blind_spots']) > 0


class TestConstellationEndpoint:
    """Test the /api/constellation endpoint."""

    def test_constellation_success(self, client):
        """Should return 200 with constellation data."""
        resp = client.get('/api/constellation')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert 'nodes' in data
        assert 'edges' in data

    def test_constellation_nodes_have_fields(self, client):
        """Nodes should have required fields."""
        resp = client.get('/api/constellation')
        data = json.loads(resp.data)
        if data['nodes']:
            node = data['nodes'][0]
            assert 'id' in node
            assert 'name' in node
            assert 'avg_rating' in node


class TestEvolutionEndpoint:
    """Test the /api/evolution endpoint."""

    def test_evolution_success(self, client):
        """Should return 200 with evolution data."""
        resp = client.get('/api/evolution')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert 'monthly_avg' in data
        assert 'yearly' in data

    def test_evolution_yearly_stats(self, client):
        """Yearly stats should contain expected fields."""
        resp = client.get('/api/evolution')
        data = json.loads(resp.data)
        for year, info in data['yearly'].items():
            assert 'avg' in info
            assert 'count' in info
            assert 'top_rating' in info


class TestRecommendationsEndpoint:
    """Test the /api/recommendations endpoint."""

    def test_recommendations_success(self, client):
        """Should return 200 with recommendations."""
        resp = client.get('/api/recommendations')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert len(data) > 0

    def test_recommendations_with_style_param(self, client):
        """Should accept style parameter without error."""
        resp = client.get('/api/recommendations?style=chill')
        assert resp.status_code == 200


class TestWeeklyDiscoveryEndpoint:
    """Test the /api/weekly-discovery endpoint."""

    def test_weekly_success(self, client):
        """Should return 200 with weekly discovery."""
        resp = client.get('/api/weekly-discovery')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert 'picks' in data
        assert 'stats' in data
        assert 'message' in data

    def test_weekly_picks_count(self, client):
        """Should return 10 weekly picks."""
        resp = client.get('/api/weekly-discovery')
        data = json.loads(resp.data)
        assert len(data['picks']) == 10


class TestSpotifyStatusEndpoint:
    """Test the /api/spotify-status endpoint."""

    def test_spotify_status_success(self, client):
        """Should return 200 with status info."""
        resp = client.get('/api/spotify-status')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert 'available' in data
        assert 'message' in data
        assert isinstance(data['available'], bool)


class TestSongsEndpoint:
    """Test the /api/songs endpoint."""

    def test_songs_default(self, client):
        """Should return songs with default parameters."""
        resp = client.get('/api/songs')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert 'songs' in data
        assert 'total' in data
        assert len(data['songs']) > 0

    def test_songs_with_limit(self, client):
        """Should respect limit parameter."""
        resp = client.get('/api/songs?limit=3')
        data = json.loads(resp.data)
        assert len(data['songs']) <= 3

    def test_songs_with_min_rating(self, client):
        """Should filter by minimum rating."""
        resp = client.get('/api/songs?min_rating=90')
        data = json.loads(resp.data)
        for song in data['songs']:
            assert song['rating'] >= 90

    def test_songs_sorted_by_rating_desc(self, client):
        """Default sort should be by rating descending."""
        resp = client.get('/api/songs')
        data = json.loads(resp.data)
        songs = data['songs']
        for i in range(len(songs) - 1):
            assert songs[i]['rating'] >= songs[i + 1]['rating']

    def test_songs_sorted_asc(self, client):
        """Should support ascending order."""
        resp = client.get('/api/songs?order=asc&limit=5')
        data = json.loads(resp.data)
        songs = data['songs']
        for i in range(len(songs) - 1):
            assert songs[i]['rating'] <= songs[i + 1]['rating']

    def test_songs_with_search(self, client):
        """Should search by title."""
        resp = client.get('/api/songs?search=love')
        data = json.loads(resp.data)
        for song in data['songs']:
            assert 'love' in song['title'].lower()

    def test_songs_pagination(self, client):
        """Should support offset for pagination."""
        resp1 = client.get('/api/songs?limit=3&offset=0')
        resp2 = client.get('/api/songs?limit=3&offset=3')
        data1 = json.loads(resp1.data)
        data2 = json.loads(resp2.data)
        # Different offsets should return different songs
        if data1['songs'] and data2['songs']:
            assert data1['songs'][0]['title'] != data2['songs'][0]['title']


class TestSearchHistoryEndpoint:
    """Test the /api/search-history endpoint."""

    def test_search_history_no_query(self, client):
        """Should return empty without query."""
        resp = client.get('/api/search-history')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['results'] == []
        assert data['total'] == 0

    def test_search_history_with_query(self, client):
        """Should return results matching query."""
        resp = client.get('/api/search-history?q=love')
        data = json.loads(resp.data)
        assert isinstance(data['results'], list)
        assert data['total'] >= 0

    def test_search_history_case_insensitive(self, client):
        """Search should be case insensitive."""
        resp_lower = client.get('/api/search-history?q=rock')
        resp_upper = client.get('/api/search-history?q=ROCK')
        data_lower = json.loads(resp_lower.data)
        data_upper = json.loads(resp_upper.data)
        assert data_lower['total'] == data_upper['total']


class TestChallengeEndpoint:
    """Test the /api/challenges endpoint."""

    def test_challenges_success(self, client):
        """GET /api/challenges should return challenge data."""
        resp = client.get('/api/challenges')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert 'challenges' in data
        assert 'by_tier' in data
        assert 'total_available' in data

    def test_challenges_respects_count(self, client):
        """count parameter should limit results."""
        resp = client.get('/api/challenges?count=5')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert len(data['challenges']) <= 5

    def test_challenges_no_owned(self, client):
        """No challenge should be flagged as already owned."""
        resp = client.get('/api/challenges')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        for c in data['challenges']:
            assert c.get('already_owned') is False or c.get('already_owned') is None

    def test_challenges_have_zone_notes(self, client):
        """Each challenge should have a personalized zone_note."""
        resp = client.get('/api/challenges')
        data = json.loads(resp.data)
        for c in data['challenges']:
            assert 'zone_note' in c
            assert len(c['zone_note']) > 0


class TestExportEndpoint:
    """Test the /api/export endpoint."""

    def test_export_success(self, client):
        """Should return 200 with export data."""
        resp = client.get('/api/export')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert 'stats' in data
        assert 'blind_spots' in data
        assert 'evolution' in data
        assert 'recommendations' in data


class TestFavoriteArtistsEndpoint:
    """Test the /api/favorite-artists endpoint."""

    def test_favorite_artists_success(self, client):
        """Should return 200 with favorite artists data."""
        resp = client.get('/api/favorite-artists')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert isinstance(data, list)
        assert len(data) > 0

    def test_favorite_artists_fields(self, client):
        """Each entry should have required fields."""
        resp = client.get('/api/favorite-artists')
        data = json.loads(resp.data)
        for fav in data:
            assert 'name' in fav
            assert 'my_rating' in fav
            assert 'genre' in fav
            assert 'in_collection' in fav
            assert isinstance(fav['name'], str)
            assert isinstance(fav['my_rating'], (int, float))

    def test_favorite_artists_michael_jackson_rating(self, client):
        """Michael Jackson should have rating 11.0."""
        resp = client.get('/api/favorite-artists')
        data = json.loads(resp.data)
        mj = [f for f in data if f['name'] == 'Michael Jackson']
        assert len(mj) >= 1
        assert mj[0]['my_rating'] == 11.0


class TestStaticFiles:
    """Test static file serving."""

    def test_static_css(self, client):
        """Should serve CSS files."""
        resp = client.get('/static/css/styles.css')
        assert resp.status_code == 200
        assert resp.content_type and 'css' in resp.content_type

    def test_static_js_utils(self, client):
        """Should serve JS files."""
        resp = client.get('/js/utils.js')
        assert resp.status_code == 200
        assert resp.content_type and 'javascript' in resp.content_type

    def test_static_js_app(self, client):
        """Should serve app.js."""
        resp = client.get('/js/app.js')
        assert resp.status_code == 200

    def test_static_js_quickadd(self, client):
        """Should serve quickadd.js."""
        resp = client.get('/js/quickadd.js')
        assert resp.status_code == 200

    def test_static_not_found(self, client):
        """Should return 404 for missing file."""
        resp = client.get('/static/nonexistent.css')
        assert resp.status_code == 404

    def test_static_css_styles(self, client):
        """Should serve consolidated styles.css with design tokens."""
        resp = client.get('/static/css/styles.css')
        assert resp.status_code == 200
        data = resp.data.decode('utf-8')
        assert '--accent' in data
        assert '--bg-primary' in data
        assert '--accent-rgb' in data


# ============================================================
# Quick-Add API Tests
# ============================================================

class TestAddSongEndpoint:
    """Test the /api/add-song endpoint (POST)."""

    def test_add_song_no_data(self, client):
        """Should return 400 for missing data."""
        resp = client.post('/api/add-song', 
                          data=json.dumps({}),
                          content_type='application/json')
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert 'error' in data

    def test_add_song_missing_title(self, client):
        """Should return 400 for missing title."""
        resp = client.post('/api/add-song',
                          data=json.dumps({'rating': '85'}),
                          content_type='application/json')
        assert resp.status_code == 400

    def test_add_song_minimal(self, client):
        """Should accept minimal valid song data."""
        resp = client.post('/api/add-song',
                          data=json.dumps({'title': 'Test Song (Test Artist, 2024)'}),
                          content_type='application/json')
        assert resp.status_code in (200, 201)
        data = json.loads(resp.data)
        assert 'success' in data
        assert data['success'] is True

    def test_add_song_with_rating(self, client):
        """Should accept song with rating."""
        resp = client.post('/api/add-song',
                          data=json.dumps({
                              'title': 'New Banger (Cool Artist, 2024)',
                              'rating': '92',
                              'notes': 'Great track I discovered through the recommender!'
                          }),
                          content_type='application/json')
        assert resp.status_code in (200, 201)
        data = json.loads(resp.data)
        assert data['success'] is True
        assert 'song' in data
        assert data['song']['rating'] == 92

    def test_add_song_invalid_rating(self, client):
        """Should reject invalid rating values."""
        resp = client.post('/api/add-song',
                          data=json.dumps({
                              'title': 'Bad Rating (Test Artist, 2024)',
                              'rating': 'abc'
                          }),
                          content_type='application/json')
        assert resp.status_code == 400

    def test_add_song_rating_out_of_range(self, client):
        """Should reject out-of-range ratings."""
        resp = client.post('/api/add-song',
                          data=json.dumps({
                              'title': 'Overrated (Test Artist, 2024)',
                              'rating': '150'
                          }),
                          content_type='application/json')
        assert resp.status_code == 400

    def test_add_song_without_rating(self, client):
        """Should accept song without a rating (just noting it for later)."""
        resp = client.post('/api/add-song',
                          data=json.dumps({
                              'title': 'New Discovery (Fresh Artist, 2024)',
                              'notes': 'Need to listen more before rating'
                          }),
                          content_type='application/json')
        assert resp.status_code in (200, 201)
        data = json.loads(resp.data)
        assert data['success'] is True


class TestBatchAddEndpoint:
    """Test the /api/batch-add endpoint (POST)."""

    def test_batch_add_empty(self, client):
        """Should return 400 for empty batch."""
        resp = client.post('/api/batch-add',
                          data=json.dumps({'songs': []}),
                          content_type='application/json')
        assert resp.status_code == 400

    def test_batch_add_no_body(self, client):
        """Should return 400 for missing body."""
        resp = client.post('/api/batch-add',
                          data=json.dumps({}),
                          content_type='application/json')
        assert resp.status_code == 400

    def test_batch_add_multiple(self, client):
        """Should accept multiple songs."""
        resp = client.post('/api/batch-add',
                          data=json.dumps({
                              'songs': [
                                  {'title': 'Song One (Artist A, 2024)', 'rating': '88'},
                                  {'title': 'Song Two (Artist B, 2024)'},
                                  {'title': 'Song Three (Artist C, 2024)', 'rating': '95'},
                              ]
                          }),
                          content_type='application/json')
        assert resp.status_code in (200, 201)
        data = json.loads(resp.data)
        assert data['success'] is True
        assert data['added'] == 3


class TestCheckSongEndpoint:
    """Test the /api/check-song endpoint (POST)."""

    def test_check_song_no_body(self, client):
        """Should return 400 for no body."""
        resp = client.post('/api/check-song',
                          data=json.dumps({}),
                          content_type='application/json')
        assert resp.status_code == 400

    def test_check_song_with_title(self, client):
        """Should accept title field as alternative."""
        resp = client.post('/api/check-song',
                          data=json.dumps({'title': 'Night Vision (Lindsey Stirling, 2014)'}),
                          content_type='application/json')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert 'exists' in data


class TestKnownSongsEndpoint:
    """Test the /api/known-songs endpoint."""

    def test_known_songs_success(self, client):
        """Should return known songs hashes."""
        resp = client.get('/api/known-songs')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert 'count' in data
        assert 'sigs' in data
        assert 'titles' in data
        assert data['count'] > 0


class TestImportSongsEndpoint:
    """Test the /api/import-songs endpoint (POST)."""

    def test_import_songs_no_text(self, client):
        """Should return 400 for no text."""
        resp = client.post('/api/import-songs',
                          data=json.dumps({}),
                          content_type='application/json')
        assert resp.status_code == 400

    def test_import_songs_pipe_format(self, client):
        """Should parse pipe-separated format."""
        resp = client.post('/api/import-songs',
                          data=json.dumps({'text': 'Test Artist - Test Song | 85 | Nice track'}),
                          content_type='application/json')
        assert resp.status_code in (200, 201)
        data = json.loads(resp.data)
        assert data['success'] is True
        assert data['added'] >= 1

    def test_import_songs_multiple_lines(self, client):
        """Should handle multiple lines."""
        text = """Artist One - Song One | 90
Artist Two - Song Two | 80
Artist Three - Song Three | 95
"""
        resp = client.post('/api/import-songs',
                          data=json.dumps({'text': text}),
                          content_type='application/json')
        assert resp.status_code in (200, 201)
        data = json.loads(resp.data)
        assert data['success'] is True

    def test_import_songs_empty_lines(self, client):
        """Should skip empty lines."""
        resp = client.post('/api/import-songs',
                          data=json.dumps({'text': 'Artist - Song | 85\n\n\nAnother - Song | 90'}),
                          content_type='application/json')
        assert resp.status_code in (200, 201)
        data = json.loads(resp.data)
        assert data['success'] is True


class TestBackfillEndpoints:
    """Test the backfill endpoints."""

    def test_backfill_preview_success(self, client):
        """GET /api/backfill-preview should return preview data."""
        resp = client.get('/api/backfill-preview')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert 'preview' in data
        assert data['preview'] is True
        assert 'total_changes' in data
        assert 'changes_by_source' in data

    def test_backfill_preview_with_method(self, client):
        """Should accept method parameter."""
        resp = client.get('/api/backfill-preview?method=letter')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['changes_by_source']['tone_inference'] == 0

    def test_backfill_preview_tone_method(self, client):
        """Tone method should only use tone."""
        resp = client.get('/api/backfill-preview?method=tone')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['changes_by_source']['letter_grades'] == 0

    def test_backfill_ratings_invalid_method(self, client):
        """Should reject invalid method."""
        resp = client.post('/api/backfill-ratings',
                          data=json.dumps({'method': 'invalid'}),
                          content_type='application/json')
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert 'error' in data


class TestSearchSpotifyEndpoint:
    """Test the /api/search-spotify endpoint."""

    def test_search_spotify_no_title(self, client):
        """Should return 400 for missing title."""
        resp = client.get('/api/search-spotify')
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert 'error' in data

    def test_search_spotify_with_title(self, client):
        """Should handle search gracefully (Spotify may not be configured)."""
        resp = client.get('/api/search-spotify?title=Test')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        # Either found data or error message — both are valid responses
        assert isinstance(data, dict)


class TestReclassifyGenresEndpoint:
    """Test the /api/reclassify-genres endpoint (POST)."""

    def test_reclassify_no_body(self, client):
        """With no body, should default to keywords-only."""
        resp = client.post('/api/reclassify-genres',
                          data=json.dumps({}),
                          content_type='application/json')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert 'before_uncategorized' in data
        assert 'after_uncategorized' in data
        assert 'reduction' in data
        assert 'by_genre' in data
        assert data['musicbrainz'] is None

    def test_reclassify_keywords_only(self, client):
        """Keywords-only mode should return valid stats."""
        resp = client.post('/api/reclassify-genres',
                          data=json.dumps({'use_musicbrainz': False}),
                          content_type='application/json')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['reduction'] >= 0
        assert len(data['by_genre']) > 0

    def test_reclassify_with_musicbrainz(self, client):
        """MusicBrainz mode should have mb stats (may be 0 if offline)."""
        resp = client.post('/api/reclassify-genres',
                          data=json.dumps({'use_musicbrainz': True}),
                          content_type='application/json')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['musicbrainz'] is not None
        assert 'looked_up' in data['musicbrainz']
        assert 'found' in data['musicbrainz']

    def test_reclassify_invalid_json_body(self, client):
        """Should still work with invalid JSON (falls back to defaults)."""
        resp = client.post('/api/reclassify-genres',
                          data='not-json',
                          content_type='application/json')
        # Flask's get_json(silent=True) returns None for bad JSON
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert 'before_uncategorized' in data


# ============================================================
# Add-Song Full Lifecycle Tests
# ============================================================

class _CSVHelper:
    """Read/write minimal helper that doesn't pollute test namespaces."""
    @staticmethod
    def remove_row(path, marker):
        import csv as _csv
        with open(path, 'r', encoding='utf-8') as f:
            rows = list(_csv.reader(f))
        kept = [row for row in rows if len(row) > 2 and marker not in row[2]]
        with open(path, 'w', encoding='utf-8', newline='') as f:
            _csv.writer(f).writerows(kept)


class TestAddSongLifecycle:
    """End-to-end lifecycle: add song with rating, verify it appears in
    /api/songs, and confirm the dedup system detects it via check-song.
    Each test adds + cleans up its own song via an autouse fixture."""

    _TEST_TITLE = 'Lifecycle Test (Test Artist, 2025)'
    _TEST_MARKER = 'Lifecycle Test'

    @pytest.fixture(autouse=True)
    def _add_and_cleanup(self, client):
        """Add a test song before each test; remove the row from CSV after."""
        client.post('/api/add-song',
                    data=json.dumps({
                        'title': self._TEST_TITLE,
                        'rating': '85',
                        'notes': 'Integration test song'
                    }),
                    content_type='application/json')
        yield
        # Best-effort cleanup: remove the injected test row from the CSV.
        # Engine is always reloaded in finally to stay in sync.
        try:
            from app import taste_engine
            _CSVHelper.remove_row(taste_engine.csv_path, self._TEST_MARKER)
        except Exception:
            pass
        finally:
            from app import taste_engine as _te
            _te._load_data()
            _te._build_artist_index()
            _te._build_song_index()

    def test_add_with_rating_persists(self, client):
        """After adding a song with rating, searching for it should find it."""
        resp = client.get(f'/api/songs?search={self._TEST_MARKER}')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert len(data['songs']) > 0, \
            f"No songs found searching for '{self._TEST_MARKER}'"
        found = [s for s in data['songs'] if self._TEST_MARKER in s['title']]
        assert len(found) > 0, \
            f"'{self._TEST_MARKER}' not found in search results"
        assert found[0]['rating'] == 85, \
            f"Expected rating 85, got {found[0]['rating']}"

    def test_check_song_detects_new_song(self, client):
        """check-song should return exists=True for the new song."""
        resp = client.post('/api/check-song',
                          data=json.dumps({'title': self._TEST_TITLE}),
                          content_type='application/json')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['exists'] is True, \
            f"check-song should find {self._TEST_TITLE}: {data}"

    def test_known_songs_includes_new_song(self, client):
        """known-sigs should contain the normalized version of the new song."""
        resp = client.get('/api/known-songs')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['count'] > 0
        from src.taste_engine import TasteEngine
        norm = TasteEngine._normalize_sig(self._TEST_TITLE)
        assert any(norm in t for t in data['titles']), \
            f"Normalized sig '{norm}' not in known titles"

    def test_api_responses_are_not_browser_cached(self, client):
        """GET /api/* must send Cache-Control: no-store so the browser never
        serves a stale copy (which made ignored/banned songs "reappear" after
        a restart even though the server excluded them).
        """
        for path in ('/api/challenges', '/api/recommendations', '/api/stats'):
            resp = client.get(path)
            assert resp.status_code == 200
            cc = resp.headers.get('Cache-Control', '').lower()
            assert 'no-store' in cc, f'{path} missing Cache-Control no-store (got {cc!r})'

    def test_recommendations_have_already_owned_flag(self, client):
        """Every recommendation should have a boolean already_owned field."""
        resp = client.get('/api/recommendations')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        total = 0
        for cat_name, cat_data in data.items():
            for rec in cat_data.get('recommendations', []):
                assert 'already_owned' in rec, \
                    f"Missing already_owned in {cat_name}/{rec.get('song', '?')}"
                assert isinstance(rec['already_owned'], bool), \
                    f"already_owned should be bool, got {type(rec['already_owned'])}"
                total += 1
        assert total > 0, "No recommendations to check"

    def test_weekly_picks_have_basic_structure(self, client):
        """Weekly picks exist with all expected fields."""
        # Weekly discovery does not use check_recs() so no already_owned flag.
        # This test just validates the weekly endpoint works after CSV changes.
        resp = client.get('/api/weekly-discovery')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        picks = data.get('picks', [])
        assert len(picks) == 10, f"Expected 10 weekly picks, got {len(picks)}"
        for pick in picks:
            for field in ('artist', 'song', 'reason', 'category'):
                assert field in pick, f"Missing field '{field}' in weekly pick"
        assert 'stats' in data
        assert 'message' in data

    def test_challenges_still_work_after_adding_song(self, client):
        """After adding a song, the challenges endpoint should still return valid data
        without errors, and no challenge should be already_owned (excluded by dedup)."""
        resp = client.get('/api/challenges?count=20')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert 'challenges' in data
        assert len(data['challenges']) > 0
        for c in data['challenges']:
            # The dedup system should have caught any match
            assert 'already_owned' in c
            assert c['already_owned'] is False or c['already_owned'] is None

    def test_recommender_reflects_ownership_after_add(self, client):
        """After adding a song, the recommendations endpoint should still
        return valid data with already_owned flags on every rec."""
        resp = client.get('/api/recommendations')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert len(data) > 0
        for cat_name, cat_data in data.items():
            for rec in cat_data.get('recommendations', []):
                assert 'already_owned' in rec, \
                    f"Missing already_owned in {cat_name}/{rec.get('song', '?')}"
                assert isinstance(rec['already_owned'], bool), \
                    f"already_owned should be bool, got {type(rec['already_owned'])}"


# ============================================================
# Ban List API Tests
# ============================================================

class TestBanListEndpoints:
    """Test ban list add/remove/get endpoints."""

    _TEST_BAN = '__test_ban_item__'

    def test_get_ban_list(self, client):
        """GET /api/ban-list should return the ban list."""
        resp = client.get('/api/ban-list')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert 'songs' in data
        assert 'artists' in data
        assert 'genres' in data

    def test_ban_add_missing_fields(self, client):
        """Should return 400 for missing type or value."""
        resp = client.post('/api/ban-list/add',
                          data=json.dumps({'type': 'songs'}),
                          content_type='application/json')
        assert resp.status_code == 400

    def test_ban_add_invalid_type(self, client):
        """Should return 400 for invalid type."""
        resp = client.post('/api/ban-list/add',
                          data=json.dumps({'type': 'invalid', 'value': 'test'}),
                          content_type='application/json')
        assert resp.status_code == 400

    def test_ban_add_empty_value(self, client):
        """Should return 400 for empty value."""
        resp = client.post('/api/ban-list/add',
                          data=json.dumps({'type': 'songs', 'value': '  '}),
                          content_type='application/json')
        assert resp.status_code == 400

    def test_ban_add_and_remove_cycle(self, client):
        """Add then remove a ban list item."""
        # Add
        resp = client.post('/api/ban-list/add',
                          data=json.dumps({'type': 'songs', 'value': self._TEST_BAN}),
                          content_type='application/json')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert self._TEST_BAN in data['ban_list']['songs']

        # Remove
        resp = client.post('/api/ban-list/remove',
                          data=json.dumps({'type': 'songs', 'value': self._TEST_BAN}),
                          content_type='application/json')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert self._TEST_BAN not in data['ban_list']['songs']

    def test_ban_add_duplicate(self, client):
        """Adding same item twice should not duplicate."""
        resp = client.post('/api/ban-list/add',
                          data=json.dumps({'type': 'songs', 'value': self._TEST_BAN}),
                          content_type='application/json')
        assert resp.status_code == 200
        resp2 = client.post('/api/ban-list/add',
                          data=json.dumps({'type': 'songs', 'value': self._TEST_BAN}),
                          content_type='application/json')
        assert resp2.status_code == 200
        data = json.loads(resp2.data)
        # Should only appear once
        assert data['ban_list']['songs'].count(self._TEST_BAN) == 1
        # Cleanup
        client.post('/api/ban-list/remove',
                   data=json.dumps({'type': 'songs', 'value': self._TEST_BAN}),
                   content_type='application/json')

    def test_ban_remove_missing_fields(self, client):
        """Should return 400 for missing fields on remove."""
        resp = client.post('/api/ban-list/remove',
                          data=json.dumps({}),
                          content_type='application/json')
        assert resp.status_code == 400

    def test_ban_remove_invalid_type(self, client):
        """Should return 400 for invalid type on remove."""
        resp = client.post('/api/ban-list/remove',
                          data=json.dumps({'type': 'bad', 'value': 'x'}),
                          content_type='application/json')
        assert resp.status_code == 400

    def test_ban_add_no_body(self, client):
        """Should return 400 for no JSON body."""
        resp = client.post('/api/ban-list/add',
                          data='not-json',
                          content_type='application/json')
        assert resp.status_code == 400

    def test_ban_remove_no_body(self, client):
        """Should return 400 for no JSON body on remove."""
        resp = client.post('/api/ban-list/remove',
                          data='not-json',
                          content_type='application/json')
        assert resp.status_code == 400


# ============================================================
# Listened Tracking Tests
# ============================================================

class TestListenedEndpoints:
    """Test listened tracking endpoints."""

    def test_get_listened(self, client):
        """GET /api/listened should return entries."""
        resp = client.get('/api/listened')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert 'entries' in data
        assert 'count' in data
        assert isinstance(data['entries'], list)

    def test_mark_listened_no_body(self, client):
        """Should return 400 for no body."""
        resp = client.post('/api/mark-listened',
                          data=json.dumps({}),
                          content_type='application/json')
        # Empty body is accepted by get_json(silent=True) returning None
        # The endpoint checks for body=None and artist/song
        assert resp.status_code == 400

    def test_mark_listened_missing_artist(self, client):
        """Should return 400 for missing artist."""
        resp = client.post('/api/mark-listened',
                          data=json.dumps({'song': 'Test'}),
                          content_type='application/json')
        assert resp.status_code == 400

    def test_mark_listened_missing_song(self, client):
        """Should return 400 for missing song."""
        resp = client.post('/api/mark-listened',
                          data=json.dumps({'artist': 'Test'}),
                          content_type='application/json')
        assert resp.status_code == 400

    def test_mark_listened_and_unlistened(self, client):
        """Mark as listened then unlisten."""
        # Mark listened
        resp = client.post('/api/mark-listened',
                          data=json.dumps({'artist': 'Test Artist', 'song': 'Test Song', 'listened': True}),
                          content_type='application/json')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['success'] is True
        assert data['listened'] is True

        # Unlisten
        resp = client.post('/api/mark-listened',
                          data=json.dumps({'artist': 'Test Artist', 'song': 'Test Song', 'listened': False}),
                          content_type='application/json')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['listened'] is False

    def test_mark_listened_defaults_true(self, client):
        """listened defaults to True if not provided."""
        resp = client.post('/api/mark-listened',
                          data=json.dumps({'artist': 'A', 'song': 'B'}),
                          content_type='application/json')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['listened'] is True
        # Cleanup
        client.post('/api/mark-listened',
                   data=json.dumps({'artist': 'A', 'song': 'B', 'listened': False}),
                   content_type='application/json')

    def test_listened_entries_show_up(self, client):
        """After marking, the entry should appear in GET /api/listened."""
        client.post('/api/mark-listened',
                   data=json.dumps({'artist': 'ListenTest', 'song': 'Track'}),
                   content_type='application/json')
        resp = client.get('/api/listened')
        data = json.loads(resp.data)
        sigs = [e.get('artist', '') for e in data['entries']]
        assert 'ListenTest' in sigs
        # Cleanup
        client.post('/api/mark-listened',
                   data=json.dumps({'artist': 'ListenTest', 'song': 'Track', 'listened': False}),
                   content_type='application/json')


# ============================================================
# Batch Add Edge Cases
# ============================================================

class TestBatchAddEdgeCases:
    """Edge cases for batch-add endpoint."""

    def test_batch_add_with_invalid_rating(self, client):
        """Invalid rating should be skipped, others added."""
        resp = client.post('/api/batch-add',
                          data=json.dumps({'songs': [
                              {'title': 'Good Song (BatchEdge1, 2024)', 'rating': '85'},
                              {'title': 'Bad Rating Song (BatchEdge2, 2024)', 'rating': 'abc'},
                              {'title': 'Range Song (BatchEdge3, 2024)', 'rating': '999'},
                          ]}),
                          content_type='application/json')
        data = json.loads(resp.data)
        # 'abc' causes ValueError -> pass (song added with no rating)
        # '999' causes out-of-range -> error + continue
        # So 2 added (85 + abc) and 1 error (999)
        assert data['added'] == 2
        assert len(data['errors']) >= 1

    def test_batch_add_with_empty_titles(self, client):
        """Entries with empty titles should be skipped."""
        resp = client.post('/api/batch-add',
                          data=json.dumps({'songs': [
                              {'title': '', 'rating': '85'},
                              {'title': '  ', 'rating': '85'},
                              {'title': 'Valid Song (BatchEdge4, 2024)', 'rating': '85'},
                          ]}),
                          content_type='application/json')
        data = json.loads(resp.data)
        assert data['added'] == 1

    def test_batch_add_with_notes(self, client):
        """Songs with notes should include them."""
        resp = client.post('/api/batch-add',
                          data=json.dumps({'songs': [
                              {'title': 'Noted Song (BatchEdge5, 2024)', 'rating': '88', 'notes': 'Great track'},
                          ]}),
                          content_type='application/json')
        data = json.loads(resp.data)
        assert data['added'] == 1


# ============================================================
# Check Song with Artist+Song
# ============================================================

class TestCheckSongWithArtistSong:
    """Test check-song with artist+song fields instead of title."""

    def test_check_song_with_artist_and_song(self, client):
        """Should accept artist and song fields."""
        resp = client.post('/api/check-song',
                          data=json.dumps({'artist': 'Lindsey Stirling', 'song': 'Night Vision'}),
                          content_type='application/json')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert 'exists' in data

    def test_check_song_needs_something(self, client):
        """Should return 400 if neither title nor artist+song provided."""
        resp = client.post('/api/check-song',
                          data=json.dumps({'random': 'field'}),
                          content_type='application/json')
        assert resp.status_code == 400


# ============================================================
# Import Songs Additional Formats
# ============================================================

class TestImportFormats:
    """Test various import text formats."""

    def test_import_rating_at_end(self, client):
        """Should parse 'Title - 85' format."""
        resp = client.post('/api/import-songs',
                          data=json.dumps({'text': 'Artist - Song Title - 85'}),
                          content_type='application/json')
        assert resp.status_code in (200, 201)
        data = json.loads(resp.data)
        assert data['added'] >= 1

    def test_import_rating_slash_format(self, client):
        """Should parse 'Title - 85/100' format."""
        resp = client.post('/api/import-songs',
                          data=json.dumps({'text': 'Some Artist - Cool Song - 85/100'}),
                          content_type='application/json')
        assert resp.status_code in (200, 201)

    def test_import_just_title_no_rating(self, client):
        """Should parse a bare title with no rating."""
        resp = client.post('/api/import-songs',
                          data=json.dumps({'text': 'Mystery Artist - Unknown Song'}),
                          content_type='application/json')
        assert resp.status_code in (200, 201)
        data = json.loads(resp.data)
        assert data['added'] >= 1


# ============================================================
# Outliers Endpoint
# ============================================================

class TestOutliersEndpoint:
    """Test /api/outliers endpoint."""

    def test_outliers_success(self, client):
        resp = client.get('/api/outliers')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert isinstance(data, (dict, list))


# ============================================================
# Geography Endpoint
# ============================================================

class TestGeographyEndpoint:
    """Test /api/geography endpoint."""

    def test_geography_success(self, client):
        resp = client.get('/api/geography')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert 'countries' in data
        assert 'regions' in data
        assert 'blind_spots' in data
        assert 'coverage' in data


# ============================================================
# Uncategorized Breakdown
# ============================================================

class TestUncategorizedBreakdown:
    """Test /api/uncategorized-breakdown endpoint."""

    def test_breakdown_success(self, client):
        resp = client.get('/api/uncategorized-breakdown')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert 'total' in data
        assert 'known_artists' in data
        assert 'unknown_artists' in data
        assert 'meta_entries' in data


# ============================================================
# Dedup Endpoint
# ============================================================

class TestDedupEndpoint:
    """Test /api/dedup endpoint."""

    def test_dedup_returns_success(self, client):
        resp = client.post('/api/deduplicate',
                          data=json.dumps({}),
                          content_type='application/json')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert 'success' in data
        assert 'removed' in data
        assert 'kept' in data
        assert 'dupes' in data


# ============================================================
# Year Conquest Endpoint
# ============================================================

class TestYearConquestEndpoint:
    """Test /api/year-conquest endpoint."""

    def test_conquest_default(self, client):
        resp = client.get('/api/year-conquest')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert 'years' in data
        assert len(data['years']) > 0

    def test_conquest_with_start_year(self, client):
        resp = client.get('/api/year-conquest?start_year=2010')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        for y in data['years']:
            assert y['year'] <= 2010

    def test_conquest_with_count(self, client):
        resp = client.get('/api/year-conquest?count=2')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        for y in data['years']:
            assert len(y['songs']) <= 2

    def test_conquest_songs_have_fields(self, client):
        resp = client.get('/api/year-conquest?count=1')
        data = json.loads(resp.data)
        for y in data['years']:
            for s in y['songs']:
                assert 'artist' in s
                assert 'song' in s
                assert 'acclaim' in s


# ============================================================
# Spotify Endpoint Additional
# ============================================================

class TestSpotifySearch:
    """Test /api/search-spotify with artist param."""

    def test_search_spotify_with_artist(self, client):
        resp = client.get('/api/search-spotify?title=Song&artist=Artist')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert isinstance(data, dict)


# ============================================================
# Recommendations Year Annotation
# ============================================================

class TestRecommendationsYear:
    """Test that recommendations include year field."""

    def test_recommendations_have_year(self, client):
        resp = client.get('/api/recommendations')
        data = json.loads(resp.data)
        year_found = False
        for cat_data in data.values():
            for rec in cat_data.get('recommendations', []):
                assert 'year' in rec, f"Missing year in rec: {rec.get('song')}"
                if rec.get('year') is not None:
                    year_found = True
        assert year_found, "At least some recommendations should have a year"

    def test_weekly_picks_have_year(self, client):
        resp = client.get('/api/weekly-discovery')
        data = json.loads(resp.data)
        for pick in data['picks']:
            assert 'year' in pick, f"Missing year in pick: {pick.get('song')}"

    def test_challenges_have_year(self, client):
        resp = client.get('/api/challenges?count=3')
        data = json.loads(resp.data)
        for c in data['challenges']:
            assert 'year' in c, f"Missing year in challenge: {c.get('song')}"


# ============================================================
# Taste DNA (Fingerprint) Endpoint Tests
# ============================================================

class TestTasteFingerprintEndpoint:
    """Test the /api/taste-fingerprint endpoint."""

    def test_fingerprint_success(self, client):
        """Should return 200 with fingerprint data."""
        resp = client.get('/api/taste-fingerprint')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert isinstance(data, dict)

    def test_fingerprint_has_all_fields(self, client):
        """Should contain all expected sections."""
        resp = client.get('/api/taste-fingerprint')
        data = json.loads(resp.data)
        expected = ['genre_fingerprint', 'year_fingerprint', 'predictability',
                    'top_influences', 'taste_summary', 'positive_song_count', 'overall_avg']
        for field in expected:
            assert field in data, f"Missing field: {field}"

    def test_fingerprint_predictability_range(self, client):
        """Predictability should be between 0 and 100."""
        resp = client.get('/api/taste-fingerprint')
        data = json.loads(resp.data)
        p = data['predictability']
        assert 0 <= p['overall'] <= 100
        assert 0 <= p['genre_predictability'] <= 100
        assert 0 <= p['year_predictability'] <= 100

    def test_fingerprint_genre_weights_sum_to_one(self, client):
        """Genre weights should sum to approximately 1.0."""
        resp = client.get('/api/taste-fingerprint')
        data = json.loads(resp.data)
        total = sum(g['weight'] for g in data['genre_fingerprint'].values())
        assert 0.99 <= total <= 1.01, f"Genre weights sum to {total}, expected ~1.0"

    def test_fingerprint_year_weights_sum_to_one(self, client):
        """Year/decade weights should sum to approximately 1.0."""
        resp = client.get('/api/taste-fingerprint')
        data = json.loads(resp.data)
        total = sum(y['weight'] for y in data['year_fingerprint'].values())
        assert 0.99 <= total <= 1.01, f"Year weights sum to {total}, expected ~1.0"

    def test_fingerprint_top_influences_have_required_fields(self, client):
        """Each influence should have artist, influence_score, genres, top_song, top_rating."""
        resp = client.get('/api/taste-fingerprint')
        data = json.loads(resp.data)
        for inf in data['top_influences']:
            assert 'artist' in inf
            assert 'influence_score' in inf
            assert 'genres' in inf
            assert 'top_song' in inf
            assert 'top_rating' in inf

    def test_fingerprint_positive_song_count_positive(self, client):
        """Should have at least some positive songs (rated >= 75)."""
        resp = client.get('/api/taste-fingerprint')
        data = json.loads(resp.data)
        assert data['positive_song_count'] > 0
        assert data['overall_avg'] > 0


class TestTasteFitEndpoint:
    """Test the /api/taste-fit endpoint."""

    def test_fit_success(self, client):
        """Should return 200 with fit data."""
        resp = client.get('/api/taste-fit?artist=Lindsey+Stirling&song=Crystallize')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert isinstance(data, dict)

    def test_fit_has_all_fields(self, client):
        """Should contain all expected fields."""
        resp = client.get('/api/taste-fit?artist=Test&song=Song')
        data = json.loads(resp.data)
        expected = ['fit_score', 'genre_match', 'year_match', 'artist_match',
                    'explanation', 'label']
        for field in expected:
            assert field in data, f"Missing field: {field}"

    def test_fit_score_range(self, client):
        """Fit score should be between 0 and 100."""
        resp = client.get('/api/taste-fit?artist=Test&song=Song')
        data = json.loads(resp.data)
        assert 0 <= data['fit_score'] <= 100

    def test_fit_with_genre_and_year(self, client):
        """Should handle genre and year parameters."""
        resp = client.get('/api/taste-fit?artist=Lindsey+Stirling&song=Crystallize&genre=Classical%2FInstrumental&year=2012')
        data = json.loads(resp.data)
        assert data['fit_score'] >= 0
        assert data['genre_match'] > 0  # Genre should match

    def test_fit_with_unknown_artist(self, client):
        """Should handle unknown artists gracefully."""
        resp = client.get('/api/taste-fit?artist=Unknown+Artist&song=Song')
        data = json.loads(resp.data)
        assert data['fit_score'] >= 0
        assert isinstance(data['explanation'], str)

    def test_fit_label_matches_score(self, client):
        """Label should match the score range."""
        resp = client.get('/api/taste-fit?artist=Lindsey+Stirling&song=Crystallize&genre=Classical%2FInstrumental&year=2012')
        data = json.loads(resp.data)
        score = data['fit_score']
        label = data['label']
        if score >= 90:
            assert label == 'Perfect Fit'
        elif score >= 75:
            assert label == 'Strong Match'
        elif score >= 60:
            assert label == 'Good Fit'
        elif score >= 40:
            assert label == 'Moderate Match'
        elif score >= 20:
            assert label == 'Weak Match'
        else:
            assert label == 'Poor Fit'

    def test_fit_influential_artist_scores_higher(self, client):
        """A known favorite should score higher than a random artist."""
        resp1 = client.get('/api/taste-fit?artist=Lindsey+Stirling&song=Song&genre=Classical%2FInstrumental&year=2012')
        resp2 = client.get('/api/taste-fit?artist=Random+Nobody&song=Song&genre=Pop&year=2015')
        d1 = json.loads(resp1.data)
        d2 = json.loads(resp2.data)
        assert d1['fit_score'] > d2['fit_score']

    def test_fit_empty_params(self, client):
        """Should handle empty parameters."""
        resp = client.get('/api/taste-fit')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert 'fit_score' in data
