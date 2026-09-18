"""Tests for the /api/data-hygiene endpoint and engine scan.

The hygiene scan surfaces data-quality problems so they get caught
automatically: artist-level rows (title == artist), placeholder artists,
case-variant identity groups, contradictory genre-cache entries, duplicate
songs, and no-artist rows.
"""

import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.taste_engine import TasteEngine


def _make_csv(rows, path):
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(
            f, fieldnames=['date', 'rating', 'title', 'tail', 'artist', 'song']
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


@pytest.fixture
def hygiene_engine(tmp_path):
    """Engine seeded with one problem of every category."""
    csv_path = str(tmp_path / 'posts_tails.csv')
    rows = [
        # Clean row (curated artist)
        {'date': '2024-01-01', 'rating': '90', 'title': 'Shape of You (Ed Sheeran, 2017)',
         'tail': '', 'artist': 'Ed Sheeran', 'song': 'Shape of You'},
        # Artist-level row: title == artist == song
        {'date': '2026-09-13', 'rating': '70', 'title': 'Zephyr Quartet',
         'tail': '', 'artist': 'Zephyr Quartet', 'song': 'Zephyr Quartet'},
        # Placeholder artist
        {'date': '2024-02-01', 'rating': '60', 'title': 'Mystery Track – Rock Riff',
         'tail': 'rock', 'artist': 'Unknown Artist', 'song': 'Mystery Track'},
        # Case-variant identity group (folded at load)
        {'date': '2024-03-01', 'rating': '85', 'title': 'T1 (One Republic, 2019)',
         'tail': '', 'artist': 'One Republic', 'song': 'T1'},
        {'date': '2024-03-02', 'rating': '80', 'title': 'T2 (OneRepublic, 2020)',
         'tail': '', 'artist': 'OneRepublic', 'song': 'T2'},
        # Duplicate song: same artist+song twice
        {'date': '2024-04-01', 'rating': '75', 'title': 'Dup Song (Dup Artist, 2021)',
         'tail': '', 'artist': 'Dup Artist', 'song': 'Dup Song'},
        {'date': '2024-04-02', 'rating': '95', 'title': 'Dup Song (Dup Artist, 2021)',
         'tail': '', 'artist': 'Dup Artist', 'song': 'Dup Song'},
        # No-artist row
        {'date': '2024-05-01', 'rating': '65', 'title': 'Orphan – No Artist Here',
         'tail': '', 'artist': '', 'song': ''},
    ]
    return TasteEngine(_make_csv(rows, csv_path))


def test_summary_counts_every_category(hygiene_engine):
    h = hygiene_engine.get_data_hygiene()
    s = h['summary']
    assert s['artist_self_rows'] == 1
    assert s['generic_artist_rows'] >= 1
    assert s['case_variant_groups'] >= 1
    assert s['duplicate_songs'] >= 1
    assert s['no_artist_rows'] >= 1
    # Cache conflicts may be 0 on a clean cache — key must exist either way
    assert 'cache_conflicts' in s


def test_artist_self_rows_listed_with_rating(hygiene_engine):
    h = hygiene_engine.get_data_hygiene()
    aardvark = [r for r in h['artist_self_rows'] if r['title'] == 'Zephyr Quartet']
    assert len(aardvark) == 1
    assert aardvark[0]['rating'] == '70'


def test_generic_artists_detected(hygiene_engine):
    h = hygiene_engine.get_data_hygiene()
    names = [g['artist'] for g in h['generic_artists']]
    assert any('unknown artist' in n.lower() for n in names)
    counts = {g['artist']: g['count'] for g in h['generic_artists']}
    assert all(c >= 1 for c in counts.values())


def test_case_variants_reported_with_variants(hygiene_engine):
    h = hygiene_engine.get_data_hygiene()
    onerep = [v for v in h['case_variants']
              if 'onerepublic' in v['canonical'].lower().replace(' ', '')]
    assert len(onerep) == 1, 'both spellings must fold into ONE group'
    group = onerep[0]
    assert group['rows'] == 2
    assert set(group['variants'].keys()) == {'One Republic', 'OneRepublic'}


def test_duplicate_songs_grouped_by_sig(hygiene_engine):
    h = hygiene_engine.get_data_hygiene()
    dups = [d for d in h['duplicate_songs']
            if d['rows'][0]['title'].startswith('Dup Song')]
    assert len(dups) == 1
    assert dups[0]['rows'][0]['artist'] == 'Dup Artist'
    ratings = sorted(r['rating'] for r in dups[0]['rows'])
    assert ratings == ['75', '95']


def test_no_artist_rows_listed(hygiene_engine):
    h = hygiene_engine.get_data_hygiene()
    orphans = [r for r in h['no_artist'] if 'Orphan' in r['title']]
    assert len(orphans) == 1


def test_cache_conflicts_report_resolved_value(hygiene_engine):
    """Contradictory cache variants must report the lookup-resolution."""
    e = hygiene_engine
    e._artist_genre_cache['Fold Artist'] = 'Rock'
    e._artist_genre_cache['fold artist'] = 'Pop'
    e._rebuild_genre_cache_folded()
    h = e.get_data_hygiene()
    conflict = [c for c in h['cache_conflicts']
                if c['artist'].lower() == 'fold artist']
    assert len(conflict) == 1
    assert set(conflict[0]['values'].values()) == {'Rock', 'Pop'}
    assert conflict[0]['resolved'] in {'Rock', 'Pop'}


def test_clean_collection_reports_zero_issues(tmp_path):
    csv_path = str(tmp_path / 'posts_tails.csv')
    rows = [
        {'date': '2024-01-01', 'rating': '90', 'title': 'S1 (Ed Sheeran, 2017)',
         'tail': '', 'artist': 'Ed Sheeran', 'song': 'S1'},
        {'date': '2024-01-02', 'rating': '80', 'title': 'S2 (Ed Sheeran, 2019)',
         'tail': '', 'artist': 'Ed Sheeran', 'song': 'S2'},
    ]
    e = TasteEngine(_make_csv(rows, csv_path))
    h = e.get_data_hygiene()
    assert h['summary']['artist_self_rows'] == 0
    assert h['summary']['generic_artist_rows'] == 0
    assert h['summary']['case_variant_groups'] == 0
    assert h['summary']['duplicate_songs'] == 0
    assert h['summary']['no_artist_rows'] == 0
    assert h['case_variants'] == []
    assert h['duplicate_songs'] == []


def test_data_hygiene_endpoint_disabled_by_default(monkeypatch):
    """The maintainer-only scan must 403 without the DEV_TOOLS flag."""
    import app as app_module
    monkeypatch.delenv('DEV_TOOLS', raising=False)
    app_module.app.config['TESTING'] = True
    with app_module.app.test_client() as client:
        resp = client.get('/api/data-hygiene')
        assert resp.status_code == 403


def test_data_hygiene_endpoint_with_dev_tools(monkeypatch):
    """With DEV_TOOLS set the endpoint returns the scan."""
    import app as app_module
    monkeypatch.setenv('DEV_TOOLS', '1')
    app_module.app.config['TESTING'] = True
    with app_module.app.test_client() as client:
        resp = client.get('/api/data-hygiene')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'summary' in data
        for key in ('artist_self_rows', 'generic_artists', 'case_variants',
                    'cache_conflicts', 'duplicate_songs', 'no_artist'):
            assert key in data


def test_dev_flag_stamped_into_html(monkeypatch):
    """DEV_TOOLS=1 stamps <body class="dev-tools"> so the frontend shows
    the maintainer nav; without it the plain <body> ships."""
    import app as app_module
    app_module.app.config['TESTING'] = True
    with app_module.app.test_client() as client:
        monkeypatch.delenv('DEV_TOOLS', raising=False)
        plain = client.get('/').get_data(as_text=True)
        monkeypatch.setenv('DEV_TOOLS', '1')
        dev = client.get('/').get_data(as_text=True)
    assert 'class="dev-tools"' not in plain
    assert 'class="dev-tools"' in dev
