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


class TestStaticFiles:
    """Test static file serving."""

    def test_static_css(self, client):
        """Should serve CSS files."""
        resp = client.get('/static/css/style.css')
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

    def test_static_css_style(self, client):
        """Should serve style.css with correct content type."""
        resp = client.get('/static/css/style.css')
        assert resp.status_code == 200
        assert 'Inter' in resp.data.decode('utf-8') or 'font-family' in resp.data.decode('utf-8')


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
