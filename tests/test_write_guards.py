"""Write-time submission screening (server-side duplicate/hygiene guards).

The data-hygiene cleanup (scripts/clean_hygiene_findings.py) drove findings to
zero, but the write endpoints could still re-introduce the same problem rows:
case-variant artists ("yu peng chen" vs "Yu-Peng Chen"), artist-level rows
("Weezer - Weezer"), and duplicates in batch/import (which had no dedup at
all). These tests pin the guard behavior at the API boundary.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def client():
    """Create a test client for the Flask app (same isolation contract as
    test_app.py's client — the autouse _hermetic_data fixture in conftest.py
    swaps the engine to a throwaway CSV copy for the session)."""
    from app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


class TestAddSongScreening:
    """/api/add-song must block problem submissions before they hit the CSV."""

    def _post(self, client, title):
        return client.post('/api/add-song',
                           data=json.dumps({'title': title, 'rating': '80'}),
                           content_type='application/json')

    def test_artist_level_row_rejected(self, client):
        """title==artist (self-titled album row) must not enter song stats."""
        resp = self._post(client, 'Screen Test Artist - Screen Test Artist')
        assert resp.status_code == 422
        data = json.loads(resp.data)
        assert data['success'] is False
        assert data['reason'] == 'artist_level'

    def test_case_variant_of_known_artist_is_canonicalized(self, client):
        """'lindsey stirling - ...' must be rewritten to the canonical
        display spelling, not stored as a new case variant."""
        resp = self._post(client, 'Qxzymborg Reliquary (lindsey stirling, 2024)')
        assert resp.status_code == 201
        data = json.loads(resp.data)
        assert data['success'] is True
        # Canonicalization applied — Lindsey Stirling is a well-known artist
        # with 62+ rows in the real dataset.
        assert data['song']['title'] == 'Qxzymborg Reliquary (Lindsey Stirling, 2024)'

    def test_special_post_title_rejected(self, client):
        """VS-battle/meta titles archived to posts_tails_special.csv must be
        refused, not re-added."""
        # 'Youtube top 10 most viewed review' lives in the special archive.
        resp = self._post(client, 'Youtube top 10 most viewed review')
        assert resp.status_code == 422
        data = json.loads(resp.data)
        assert data['reason'] == 'special_post'

    def test_fresh_song_still_added(self, client):
        """A genuinely new song passes screening unmodified."""
        resp = self._post(client, 'Xylophonic Wubstep Meridian (Zyxphona, 2024)')
        assert resp.status_code == 201
        data = json.loads(resp.data)
        assert data['success'] is True
        assert data['song']['title'] == 'Xylophonic Wubstep Meridian (Zyxphona, 2024)'


class TestBatchAddScreening:
    """batch-add previously had NO dedup — every song in a batch was saved."""

    def test_duplicate_in_batch_is_skipped_not_saved(self, client):
        """A song already in the collection must be reported as a duplicate,
        not silently appended."""
        resp = client.post('/api/batch-add',
                           data=json.dumps({'songs': [
                               {'title': 'Zymurgical Quasar Nectar (Fictitious, 2024)', 'rating': '70'},
                           ]}),
                           content_type='application/json')
        assert resp.status_code in (200, 201)
        first = json.loads(resp.data)
        assert first['added'] == 1

        # Same song again (different casing/spacing) — must be skipped.
        resp2 = client.post('/api/batch-add',
                            data=json.dumps({'songs': [
                                {'title': 'zymurgical quasar nectar (fictitious, 2024)', 'rating': '71'},
                            ]}),
                            content_type='application/json')
        data = json.loads(resp2.data)
        assert data['added'] == 0
        assert any('already exists' in e for e in data['errors'])

    def test_artist_level_rows_never_saved(self, client):
        resp = client.post('/api/batch-add',
                           data=json.dumps({'songs': [
                               {'title': 'Batch Self Titled - Batch Self Titled'},
                           ]}),
                           content_type='application/json')
        data = json.loads(resp.data)
        assert data['added'] == 0
        assert any('artist-level' in e for e in data['errors'])


class TestImportSongsScreening:
    """import-songs previously appended every line with no dedup at all."""

    def test_import_dedups_against_collection(self, client):
        text = "Qwertyuiop Asdfghjkl | 85\nZxcvbnm Poiuytrewq | 75\n"
        resp = client.post('/api/import-songs',
                           data=json.dumps({'text': text}),
                           content_type='application/json')
        data = json.loads(resp.data)
        assert data['added'] == 2

        # Re-import the same line — must be counted as a duplicate error.
        resp2 = client.post('/api/import-songs',
                            data=json.dumps({'text': 'Qwertyuiop Asdfghjkl | 85\n'}),
                            content_type='application/json')
        data2 = json.loads(resp2.data)
        assert data2['added'] == 0
        assert any('already exists' in e for e in data2['errors'])

    def test_import_blocks_artist_level_lines(self, client):
        resp = client.post('/api/import-songs',
                           data=json.dumps({'text': 'Import Self Row - Import Self Row | 80\n'}),
                           content_type='application/json')
        data = json.loads(resp.data)
        assert data['added'] == 0
        assert any('artist-level' in e for e in data['errors'])
