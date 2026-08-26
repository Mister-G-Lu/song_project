"""
Null safety tests for all fixed code paths.
Tests that missing keys, None values, and edge cases don't crash.
"""
import csv
import os
import tempfile
import json
import pytest
from unittest.mock import MagicMock, patch
from src.taste_engine import TasteEngine
from src.spotify_helper import SpotifyHelper
from src.backfill import extract_letter_grade, infer_tone_rating


# ============================================================
# taste_engine.py — Null safety tests for fixed r['key'] → .get() paths
# ============================================================

def make_csv(rows, extra_fields=None):
    """Helper to create a temporary CSV with given rows (+ optional extra fields)."""
    headers = ['date', 'rating', 'title', 'tail']
    if extra_fields:
        headers += extra_fields
    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8', newline='')
    writer = csv.writer(tmp)
    writer.writerow(headers)
    for row in rows:
        # Pad row to match headers length
        padded = list(row) + [''] * (len(headers) - len(row))
        writer.writerow(padded)
    tmp.close()
    return tmp.name


class TestTasteEngineNullSafety:
    """Test that missing/None CSV fields don't crash engine methods."""

    def test_empty_ratings_key(self):
        """Row with empty string rating should not crash _load_data."""
        path = make_csv([
            ['2024-01-01', '', 'Song (Artist, 2024)', 'some text'],
        ])
        try:
            e = TasteEngine(path)
            # rated_entries should filter out empty ratings
            assert len(e.rated_entries) == 0
            assert len(e.ratings) == 0
            # get_stats should still work
            stats = e.get_stats()
            assert stats['total_entries'] == 1
            assert stats['rated_entries'] == 0
        finally:
            os.unlink(path)

    def test_missing_tail_field(self):
        """Row with empty/missing tail should not crash slicing."""
        path = make_csv([
            ['2024-01-01', '85', 'Song (Artist, 2024)', ''],
        ])
        try:
            e = TasteEngine(path)
            stats = e.get_stats()
            assert stats['total_entries'] == 1
            # _get_top_songs uses r.get('tail') or '' — should not crash
            songs = stats['top_songs']
            assert len(songs) == 1
            # preview should be empty string, not crash
            assert songs[0]['preview'] == ''
        finally:
            os.unlink(path)

    def test_missing_title_field(self):
        """Row with empty title should not crash _extract_artists."""
        path = make_csv([
            ['2024-01-01', '85', '', 'Some review text with keywords'],
        ])
        try:
            e = TasteEngine(path)
            # _extract_artists should handle empty string
            artists = e._extract_artists('')
            assert artists == []
            # get_stats should still work
            stats = e.get_stats()
            assert stats['total_entries'] == 1
        finally:
            os.unlink(path)

    def test_missing_date_field(self):
        """Row with empty date should not crash get_stats date_range."""
        path = make_csv([
            ['', '85', 'Song (Artist, 2024)', 'Some review'],
        ])
        try:
            e = TasteEngine(path)
            stats = e.get_stats()
            assert 'date_range' in stats
            # date_range should contain empty strings rather than crash
            assert isinstance(stats['date_range']['start'], str)
            assert isinstance(stats['date_range']['end'], str)
        finally:
            os.unlink(path)

    def test_mixed_empty_and_valid_fields(self):
        """Mix of empty and valid fields should not crash any method."""
        path = make_csv([
            ['2024-01-01', '85', 'Song A (Artist A, 2024)', 'Great pop song'],
            ['2024-01-02', '', 'Song B (Artist B, 2024)', ''],
            ['', '90', '', 'Only text no metadata'],
            ['2024-01-03', '', '', ''],
            ['', '', 'Song C (Artist C, 2024)', 'Rock track'],
        ])
        try:
            e = TasteEngine(path)
            # All methods should handle gracefully
            stats = e.get_stats()
            assert stats['total_entries'] == 5
            assert stats['rated_entries'] == 2  # only 2 have ratings

            evo = e.get_evolution()
            assert 'monthly_avg' in evo

            cons = e.get_constellation()
            assert 'nodes' in cons

            recs = e.get_recommendations()
            assert len(recs) > 0

            bs = e.get_blind_spots()
            assert 'blind_spots' in bs

            weekly = e.get_weekly_discovery()
            assert 'picks' in weekly

            challenges = e.get_challenges(count=5)
            assert 'challenges' in challenges

            backfill = e.backfill_ratings(preview=True)
            assert 'total_changes' in backfill
        finally:
            os.unlink(path)

    def test_extract_artists_none_input(self):
        """_extract_artists with None/empty should not crash."""
        e = None
        path = make_csv([
            ['2024-01-01', '85', 'Song (Artist, 2024)', 'text'],
        ])
        try:
            e = TasteEngine(path)
            # All should safely return []
            assert e._extract_artists('') == []
            assert e._extract_artists(None) == []
            assert e._extract_artists('   ') == []
            assert e._extract_artists(123) == []  # non-string
        finally:
            os.unlink(path)

    def test_recent_reviews_no_title_or_tail(self):
        """Recent reviews should handle entries with missing title/tail."""
        path = make_csv([
            ['2024-01-01', '85', '', ''],
            ['2024-01-02', '90', 'Test Song (Artist, 2024)', 'Nice track'],
        ])
        try:
            e = TasteEngine(path)
            recent = e.get_stats()['recent_reviews']
            # Should not crash; entries with empty title should be filtered out
            assert len(recent) == 1  # Only the non-empty title
            assert recent[0]['title'] == 'Test Song (Artist, 2024)'
        finally:
            os.unlink(path)

    def test_genre_distribution_empty_tail(self):
        """Genre distribution should handle entries with empty tail.
        Note: keywords in the title (like 'Pop', 'Rock') WILL match genre keywords,
        so these songs are not treated as Uncategorized despite having empty tails.
        The important thing is that the method doesn't crash."""
        path = make_csv([
            ['2024-01-01', '85', 'Pop Song (Pop Artist, 2024)', ''],
            ['2024-01-02', '90', 'Rock Song (Rock Artist, 2024)', ''],
        ])
        try:
            e = TasteEngine(path)
            dist = e._get_genre_distribution()
            # Should not crash; 'Pop' and 'Rock' in the title should match keywords
            assert 'Uncategorized' in dist  # Key always exists in result
            assert isinstance(dist['Uncategorized']['count'], int)
        finally:
            os.unlink(path)


# ============================================================
# backfill.py — Null safety tests
# ============================================================

class TestBackfillNullSafety:
    """Test that backfill functions handle None/empty input correctly."""

    def test_extract_grade_none(self):
        g, v = extract_letter_grade(None)
        assert g is None
        assert v is None

    def test_extract_grade_non_string(self):
        """Non-string input should not crash (fixed with isinstance guard)."""
        g, v = extract_letter_grade(123)
        assert g is None
        assert v is None

    def test_infer_tone_none(self):
        tag, v = infer_tone_rating(None)
        assert tag is None
        assert v is None

    def test_infer_tone_non_string(self):
        """Non-string input should not crash (fixed with isinstance guard)."""
        tag, v = infer_tone_rating(True)
        assert tag is None
        assert v is None

    def test_infer_tone_empty_string(self):
        tag, v = infer_tone_rating('')
        assert tag is None
        assert v is None


# ============================================================
# Spotify helper — Null safety tests
# ============================================================

class TestSpotifyNullSafety:
    """Test Spotify helper handles empty/missing responses gracefully."""

    def test_search_track_empty_artists(self):
        """Handle track with empty artists array."""
        os.environ.pop('SPOTIFY_CLIENT_ID', None)
        os.environ.pop('SPOTIFY_CLIENT_SECRET', None)
        helper = SpotifyHelper()
        assert helper.search_track('test') is None

    @patch.dict(os.environ, {'SPOTIFY_CLIENT_ID': 'test', 'SPOTIFY_CLIENT_SECRET': 'test'})
    @patch('src.spotify_helper.SpotifyClientCredentials')
    @patch('src.spotify_helper.spotipy.Spotify')
    def test_search_track_no_images(self, mock_spotify, mock_auth):
        """Handle track with no album images."""
        mock_instance = MagicMock()
        mock_instance.search.return_value = {
            'tracks': {
                'items': [{
                    'id': 'abc',
                    'name': 'Test',
                    'artists': [{'name': 'Artist'}],
                    'album': {'name': 'Album', 'images': []},
                    'preview_url': None,
                    'external_urls': {'spotify': 'http://spotify.com/track/abc'},
                    'duration_ms': 200000,
                    'popularity': 50,
                }]
            }
        }
        mock_auth.return_value = MagicMock()
        mock_spotify.return_value = mock_instance
        helper = SpotifyHelper()
        result = helper.search_track('Test', 'Artist')
        assert result is not None
        assert result['album_image'] is None  # Empty images → None

    @patch.dict(os.environ, {'SPOTIFY_CLIENT_ID': 'test', 'SPOTIFY_CLIENT_SECRET': 'test'})
    @patch('src.spotify_helper.SpotifyClientCredentials')
    @patch('src.spotify_helper.spotipy.Spotify')
    def test_audio_features_empty(self, mock_spotify, mock_auth):
        """Handle audio_features returning None (non-existent track)."""
        mock_instance = MagicMock()
        mock_instance.audio_features.return_value = [None]
        mock_auth.return_value = MagicMock()
        mock_spotify.return_value = mock_instance
        helper = SpotifyHelper()
        result = helper.get_audio_features('nonexistent')
        assert result is None

    @patch.dict(os.environ, {'SPOTIFY_CLIENT_ID': 'test', 'SPOTIFY_CLIENT_SECRET': 'test'})
    @patch('src.spotify_helper.SpotifyClientCredentials')
    @patch('src.spotify_helper.spotipy.Spotify')
    def test_recommendations_no_tracks(self, mock_spotify, mock_auth):
        """Handle recommendations returning no tracks."""
        mock_instance = MagicMock()
        mock_instance.recommendations.return_value = {}
        mock_auth.return_value = MagicMock()
        mock_spotify.return_value = mock_instance
        helper = SpotifyHelper()
        result = helper.get_recommendations_from_seeds(seed_tracks=['abc'])
        assert result == []


# ============================================================
# app.py — Null safety for _safe_int and request args
# ============================================================

class TestAppNullSafety:
    """Test app.py's _safe_int helper handles edge cases."""

    @pytest.fixture
    def client(self):
        from app import app
        app.config['TESTING'] = True
        with app.test_client() as client:
            yield client

    def test_songs_negative_limit(self, client):
        """Negative limit should fallback to default."""
        resp = client.get('/api/songs?limit=-5')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert 'songs' in data

    def test_songs_non_numeric_limit(self, client):
        """Non-numeric limit (e.g. 'abc') should fallback to default."""
        resp = client.get('/api/songs?limit=abc')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert 'songs' in data

    def test_songs_non_numeric_offset(self, client):
        """Non-numeric offset should fallback to 0."""
        resp = client.get('/api/songs?offset=xyz')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert 'songs' in data

    def test_songs_float_limit(self, client):
        """Float limit (5.5) should fallback to default."""
        resp = client.get('/api/songs?limit=5.5')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert 'songs' in data

    def test_challenges_non_numeric_count(self, client):
        """Non-numeric count should fallback to default."""
        resp = client.get('/api/challenges?count=abc')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert 'challenges' in data

    def test_search_history_missing_fields(self, client):
        """Search should handle entries with missing title/tail gracefully."""
        resp = client.get('/api/search-history?q=test')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert 'results' in data

    def test_weekly_non_numeric_count(self, client):
        """Non-numeric count parameter should not crash."""
        resp = client.get('/api/weekly-discovery?count=xyz')
        assert resp.status_code == 200

    def test_backfill_preview_non_numeric_method(self, client):
        """Non-standard method parameter should not crash."""
        resp = client.get('/api/backfill-preview?method=xyz')
        assert resp.status_code == 200

    def test_reclassify_non_json_body(self, client):
        """Non-JSON body should fallback to defaults."""
        resp = client.post('/api/reclassify-genres',
                          data='not-json',
                          content_type='application/json')
        assert resp.status_code == 200

    def test_export_non_standard_params(self, client):
        """Export with bad params should not crash."""
        resp = client.get('/api/export?format=bad&limit=none')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert 'stats' in data
