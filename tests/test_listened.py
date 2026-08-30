"""
Tests for the listened-tracking API (data/listened.json) and its integration
with the recommendations, weekly-discovery, and challenges endpoints.
"""

import json

import pytest

import app as app_module
from app import app


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def _isolate_listened_store(tmp_path, monkeypatch):
    """Point the app at a throwaway store so tests never touch the real
    data/listened.json (which may contain actual listened history)."""
    store = tmp_path / "listened.json"
    monkeypatch.setattr(app_module, "LISTENED_PATH", str(store))
    yield


def _mark(client, artist, song, listened=True):
    return client.post('/api/mark-listened',
                       data=json.dumps({'artist': artist, 'song': song, 'listened': listened}),
                       content_type='application/json')


class TestListenedEndpoint:
    """GET /api/listened + POST /api/mark-listened."""

    def test_listened_empty(self, client):
        resp = client.get('/api/listened')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['entries'] == []
        assert data['count'] == 0

    def test_mark_listened_persists(self, client):
        resp = _mark(client, 'Lindsey Stirling', 'Night Vision')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['success'] is True
        assert data['listened'] is True
        assert data['count'] == 1

        data = json.loads(client.get('/api/listened').data)
        assert data['count'] == 1
        entry = data['entries'][0]
        assert entry['artist'] == 'Lindsey Stirling'
        assert entry['song'] == 'Night Vision'
        assert entry['listened_at']

    def test_mark_twice_is_idempotent(self, client):
        _mark(client, 'A', 'B')
        _mark(client, 'A', 'B')
        data = json.loads(client.get('/api/listened').data)
        assert data['count'] == 1

    def test_unmark_removes(self, client):
        _mark(client, 'A', 'B')
        _mark(client, 'A', 'B', listened=False)
        data = json.loads(client.get('/api/listened').data)
        assert data['count'] == 0

    def test_mark_requires_artist_and_song(self, client):
        resp = client.post('/api/mark-listened',
                           data=json.dumps({'artist': 'A'}),
                           content_type='application/json')
        assert resp.status_code == 400
        resp = client.post('/api/mark-listened',
                           data=json.dumps({'song': 'B'}),
                           content_type='application/json')
        assert resp.status_code == 400

    def test_mark_no_body(self, client):
        resp = client.post('/api/mark-listened',
                           data=json.dumps({}),
                           content_type='application/json')
        assert resp.status_code == 400


class TestListenedAnnotation:
    """Recommendations / weekly picks / challenges carry a `listened` flag."""

    def test_recommendations_have_listened_flag(self, client):
        resp = client.get('/api/recommendations')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        total = 0
        for cat_data in data.values():
            for rec in cat_data.get('recommendations', []):
                assert 'listened' in rec
                assert isinstance(rec['listened'], bool)
                total += 1
        assert total > 0

    def test_weekly_picks_have_listened_flag(self, client):
        resp = client.get('/api/weekly-discovery')
        data = json.loads(resp.data)
        assert len(data['picks']) > 0
        for pick in data['picks']:
            assert 'listened' in pick
            assert isinstance(pick['listened'], bool)

    def test_challenges_have_listened_flag(self, client):
        resp = client.get('/api/challenges')
        data = json.loads(resp.data)
        assert len(data['challenges']) > 0
        for c in data['challenges']:
            assert 'listened' in c
            assert isinstance(c['listened'], bool)

    def test_marking_a_pick_flips_its_flag(self, client):
        resp = client.get('/api/weekly-discovery')
        picks = json.loads(resp.data)['picks']
        target = picks[0]
        assert target['listened'] is False

        _mark(client, target['artist'], target['song'], listened=True)

        resp = client.get('/api/weekly-discovery')
        data = json.loads(resp.data)
        marked = [p for p in data['picks']
                  if p['artist'] == target['artist'] and p['song'] == target['song']]
        assert marked
        assert marked[0]['listened'] is True

    def test_marking_flags_matching_rec(self, client):
        """Marking a weekly pick listened should flip the same rec elsewhere."""
        resp = client.get('/api/weekly-discovery')
        target = json.loads(resp.data)['picks'][0]
        _mark(client, target['artist'], target['song'], listened=True)

        resp = client.get('/api/recommendations')
        data = json.loads(resp.data)
        for cat_data in data.values():
            for rec in cat_data.get('recommendations', []):
                if rec['artist'] == target['artist'] and rec['song'] == target['song']:
                    assert rec['listened'] is True
