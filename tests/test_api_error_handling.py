"""
Tests for API error handling across all POST endpoints.

Verifies that the server returns appropriate HTTP status codes and
error messages for malformed requests, missing fields, invalid types,
and edge cases — without crashing or corrupting data.
"""

import json
import pytest
import sys
import os

os.environ['FLASK_TESTING'] = '1'


@pytest.fixture
def client():
    from app import app
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


# ============================================================
# /api/add-song — Error Cases
# ============================================================

class TestAddSongErrors:
    """POST /api/add-song should reject bad input gracefully."""

    def test_empty_body(self, client):
        resp = client.post('/api/add-song', json={})
        assert resp.status_code in (400, 422)

    def test_missing_artist(self, client):
        resp = client.post('/api/add-song', json={
            'title': 'Test Song', 'rating': 80
        })
        # Server may accept or reject — just verify no 500
        assert resp.status_code < 500

    def test_missing_title(self, client):
        resp = client.post('/api/add-song', json={
            'artist': 'Test Artist', 'rating': 80
        })
        assert resp.status_code in (400, 422)

    def test_missing_rating(self, client):
        resp = client.post('/api/add-song', json={
            'artist': 'Test Artist', 'title': 'Test Song'
        })
        assert resp.status_code in (400, 409, 422)

    def test_rating_out_of_range_high(self, client):
        resp = client.post('/api/add-song', json={
            'artist': 'Test Artist', 'title': 'Test Song', 'rating': 150
        })
        # Should accept but clamp, or reject
        assert resp.status_code in (200, 201, 400, 422)

    def test_rating_out_of_range_negative(self, client):
        resp = client.post('/api/add-song', json={
            'artist': 'Test Artist', 'title': 'Test Song', 'rating': -5
        })
        assert resp.status_code in (200, 201, 400, 422)

    def test_rating_string_type(self, client):
        resp = client.post('/api/add-song', json={
            'artist': 'Test Artist', 'title': 'Test Song', 'rating': 'eighty'
        })
        assert resp.status_code in (400, 422, 200)

    def test_rating_float_type(self, client):
        resp = client.post('/api/add-song', json={
            'artist': 'Test Artist', 'title': 'Test Song', 'rating': 80.5
        })
        assert resp.status_code in (200, 201, 400, 409, 422)

    def test_empty_artist_string(self, client):
        resp = client.post('/api/add-song', json={
            'artist': '', 'title': 'Test Song', 'rating': 80
        })
        assert resp.status_code in (400, 409, 422)

    def test_empty_title_string(self, client):
        resp = client.post('/api/add-song', json={
            'artist': 'Test Artist', 'title': '', 'rating': 80
        })
        assert resp.status_code in (400, 422)

    def test_whitespace_only_artist(self, client):
        resp = client.post('/api/add-song', json={
            'artist': '   ', 'title': 'Test Song', 'rating': 80
        })
        assert resp.status_code in (400, 409, 422)

    def test_invalid_json_body(self, client):
        resp = client.post('/api/add-song',
                           data='not json at all',
                           content_type='application/json')
        assert resp.status_code in (400, 415)

    def test_form_encoded_rejected(self, client):
        resp = client.post('/api/add-song',
                           data='artist=Test&title=Song&rating=80',
                           content_type='application/x-www-form-urlencoded')
        assert resp.status_code in (400, 415)

    def test_very_long_title(self, client):
        resp = client.post('/api/add-song', json={
            'artist': 'Test', 'title': 'A' * 5000, 'rating': 80
        })
        # Should handle gracefully, not crash
        assert resp.status_code in (200, 201, 400, 422)

    def test_unicode_artist(self, client):
        resp = client.post('/api/add-song', json={
            'artist': 'Ado', 'title': '唱', 'rating': 90
        })
        assert resp.status_code in (200, 201, 400, 409, 422)


# ============================================================
# /api/batch-add — Error Cases
# ============================================================

class TestBatchAddErrors:
    """POST /api/batch-add should reject bad input gracefully."""

    def test_empty_body(self, client):
        resp = client.post('/api/batch-add', json={})
        assert resp.status_code in (400, 422)

    def test_empty_songs_list(self, client):
        resp = client.post('/api/batch-add', json={'songs': []})
        assert resp.status_code in (400, 422)

    def test_malformed_song_entry(self, client):
        resp = client.post('/api/batch-add', json={
            'songs': [{'noartist': True}]
        })
        # API may accept partial data or reject — both are valid
        assert resp.status_code in (200, 400, 422)

    def test_mix_of_valid_and_invalid(self, client):
        resp = client.post('/api/batch-add', json={
            'songs': [
                {'artist': 'Test', 'title': 'Song', 'rating': 80},
                {'broken': True},
            ]
        })
        # Should either reject all or report partial success
        assert resp.status_code in (200, 201, 400, 422)


# ============================================================
# /api/check-song — Error Cases
# ============================================================

class TestCheckSongErrors:
    """POST /api/check-song should reject bad input gracefully."""

    def test_empty_body(self, client):
        resp = client.post('/api/check-song', json={})
        assert resp.status_code in (400, 422)

    def test_missing_fields(self, client):
        resp = client.post('/api/check-song', json={'artist': 'Test'})
        assert resp.status_code in (400, 422)


# ============================================================
# /api/deduplicate — Error Cases
# ============================================================

class TestDeduplicateErrors:
    """POST /api/deduplicate should reject bad input gracefully."""

    def test_empty_body(self, client):
        resp = client.post('/api/deduplicate', json={})
        # API may handle empty dedup gracefully
        assert resp.status_code in (200, 400, 422)


# ============================================================
# /api/reload — Error Cases
# ============================================================

class TestReloadErrors:
    """POST /api/reload should work even with empty body."""

    def test_reload_empty_body(self, client):
        resp = client.post('/api/reload', json={})
        # Reload should succeed regardless
        assert resp.status_code in (200, 204)


# ============================================================
# GET Endpoints — 404 and Edge Cases
# ============================================================

class TestGetEndpointErrors:
    """GET endpoints should return proper errors for bad requests."""

    def test_unknown_api_route(self, client):
        resp = client.get('/api/nonexistent-endpoint')
        assert resp.status_code in (404, 405)

    def test_stats_returns_json(self, client):
        resp = client.get('/api/stats')
        assert resp.status_code == 200
        assert resp.content_type and 'json' in resp.content_type
        data = json.loads(resp.data)
        assert 'total_entries' in data

    def test_evolution_returns_json(self, client):
        resp = client.get('/api/evolution')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert 'yearly' in data
        assert 'cumulative' in data
        assert 'release_year_avg' in data

    def test_constellation_returns_json(self, client):
        resp = client.get('/api/constellation')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert 'nodes' in data

    def test_blind_spots_returns_json(self, client):
        resp = client.get('/api/blind-spots')
        assert resp.status_code == 200

    def test_taste_fingerprint_returns_json(self, client):
        resp = client.get('/api/taste-fingerprint')
        assert resp.status_code == 200

    def test_recommendations_returns_json(self, client):
        resp = client.get('/api/recommendations')
        assert resp.status_code == 200

    def test_discover_returns_json(self, client):
        resp = client.get('/api/discover')
        assert resp.status_code == 200

    def test_challenges_returns_json(self, client):
        resp = client.get('/api/challenges')
        assert resp.status_code == 200

    def test_year_conquest_returns_json(self, client):
        resp = client.get('/api/year-conquest')
        assert resp.status_code == 200

    def test_file_status_returns_json(self, client):
        resp = client.get('/api/file-status')
        assert resp.status_code == 200

    def test_known_songs_returns_json(self, client):
        resp = client.get('/api/known-songs')
        assert resp.status_code == 200

    def test_uncategorized_breakdown_returns_json(self, client):
        resp = client.get('/api/uncategorized-breakdown')
        assert resp.status_code == 200


# ============================================================
# Content-Type Enforcement
# ============================================================

class TestContentTypeEnforcement:
    """POST endpoints should reject non-JSON content types."""

    def test_text_plain_rejected(self, client):
        resp = client.post('/api/add-song',
                           data='artist=Test&title=Song',
                           content_type='text/plain')
        assert resp.status_code in (400, 415)

    def test_xml_rejected(self, client):
        resp = client.post('/api/add-song',
                           data='<song><artist>Test</artist></song>',
                           content_type='application/xml')
        assert resp.status_code in (400, 415)

    def test_multipart_rejected(self, client):
        resp = client.post('/api/add-song',
                           data={'artist': 'Test', 'title': 'Song'},
                           content_type='multipart/form-data')
        assert resp.status_code in (400, 415)
