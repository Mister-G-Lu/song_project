"""
Tests for scripts/import_rym_export.py — the RateYourMusic importer.

Covers the two things that must never go wrong:
  * a duplicate must never overwrite an existing rating ("pre-existing wins")
  * the duplicate definition must match TasteEngine's own merge/dedup rule
"""
import csv
import json
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from scripts.import_rym_export import (  # noqa: E402
    ImportRow, apply_import, detect_scale, gap_metrics, map_columns, normalize_sig,
    parse_rating, read_table, run_import,
)


FIELDS = ['date', 'rating', 'title', 'tail', 'artist', 'song',
          'title_original', 'title_english']


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def row(title, rating='', artist='', song='', date='2024-01-01', tail='', **kw):
    r = {'date': date, 'rating': str(rating), 'title': title, 'tail': tail,
         'artist': artist, 'song': song, 'title_original': '', 'title_english': ''}
    r.update(kw)
    return r


def write_export(path, header, records):
    with open(path, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(records)
    return str(path)


def import_from(path, header, records, base_rows, add_rows=(), **kw):
    """path is the file the export should be written to (parent dirs created)."""
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    p = write_export(path, header, records)
    return run_import(p, base_rows=base_rows, add_rows=list(add_rows), **kw)


# ---------------------------------------------------------------------------
# Column mapping + rating parsing
# ---------------------------------------------------------------------------

def test_map_columns_handles_rym_headers():
    m = map_columns(['artist_name', 'release_title', 'track_title', 'rating',
                      'date_rated', 'review'])
    assert m['artist'] == 'artist_name'
    assert m['song'] == 'track_title'
    assert m['release'] == 'release_title'
    assert m['rating'] == 'rating'
    assert m['date'] == 'date_rated'
    assert m['tail'] == 'review'


def test_map_columns_loose_fallback():
    m = map_columns(['Artist', 'My Song Rating', 'Date I Rated It'])
    assert m['artist'] == 'Artist'
    assert m['rating'] == 'My Song Rating'


def test_parse_rating_scales():
    assert parse_rating('85', 'auto')[0] == 85
    assert parse_rating('85/100', 'auto')[0] == 85
    assert parse_rating('9/10', 'auto')[0] == 90
    assert parse_rating('4', 'out_of_10')[0] == 40
    assert parse_rating('4', 'as_is')[0] == 4
    assert parse_rating('4', 'linear')[0] == 80        # 4 RYM stars
    assert parse_rating('4', 'anchored')[0] == 75       # 1★..5★ spread to 0..100
    assert parse_rating('4.5', 'linear')[0] == 90
    assert parse_rating('3.5', 'linear')[0] == 70
    assert parse_rating('★★★★☆', 'auto')[0] == 80
    assert parse_rating('★★★★½', 'auto')[0] == 90
    assert parse_rating('B+', 'auto')[0] == 88          # project letter-grade map
    assert parse_rating('really good', 'auto')[0] == 85
    assert parse_rating('', 'auto')[0] is None
    assert parse_rating('n/a', 'auto')[0] is None


def test_star_column_detection():
    assert detect_scale(['5', '4.5', '3', '4']) == 'linear'
    assert detect_scale(['70', '80', '85']) is None    # already 0-100
    assert detect_scale(['4/5', '3/5', '5/5']) is None  # explicit → parser handles it
    assert detect_scale(['4', '4']) is None            # too few values to be sure


# ---------------------------------------------------------------------------
# Duplicate tiers and the "existing wins" rule
# ---------------------------------------------------------------------------

BASE = [
    row('Ado – Value', 70, artist='Ado', song='Value'),
    row('Shape of You (Ed Sheeran, 2017)', 90, artist='Ed Sheeran', song='Shape of You'),
    row('Senbonzakura (Hatsune Miku, 2012)', '', artist='Hatsune Miku', song='Senbonzakura'),
    row('Plastic Love (Mariya Takeuchi, 1984)', 95, artist='Mariya Takeuchi', song='Plastic Love'),
    row('Some Song (Mystery Artist, 2020)', 60, artist='', song='Some Song'),
]


def test_conflict_keeps_preexisting_rating(tmp_path):
    """70 in the project vs 80 on RYM → the project's 70 stays, nothing is written."""
    rep = import_from(tmp_path / 'export.csv', ['artist', 'song', 'rating'],
                      [['Ado', 'Value', '80']], BASE)
    assert rep['new_rows'] == []
    assert rep['conflicts'][0]['existing_rating'] == 70
    assert rep['conflicts'][0]['rym_rating'] == 80
    assert rep['conflicts'][0]['kept'] == 'existing'
    assert rep['dup_skip'][0]['tier'] in ('merge_sig', 'combo')


def test_identical_dup_is_skipped_without_noise(tmp_path):
    rep = import_from(tmp_path / 'export.csv', ['artist', 'song', 'rating'],
                      [['Ed Sheeran', 'Shape of You', '90']], BASE)
    assert rep['new_rows'] == []
    assert rep['conflicts'] == []
    assert len(rep['dup_skip']) == 1


def test_rating_rewritten_when_project_format_differs(tmp_path):
    """'Shape of You' vs 'Shape of You (Ed Sheeran, 2017)' — same song, year/artist differ."""
    rep = import_from(tmp_path / 'export.csv', ['artist', 'song', 'rating', 'year'],
                      [['Ed Sheeran', 'Shape of You', '5', '2017']], BASE)
    assert rep['new_rows'] == []
    assert rep['dup_skip'][0]['tier'] in ('merge_sig', 'combo', 'jaccard')


def test_unrated_row_gets_filled(tmp_path):
    rep = import_from(tmp_path / 'export.csv', ['artist', 'song', 'rating'],
                      [['Hatsune Miku', 'Senbonzakura', '4']], BASE)
    assert rep['new_rows'] == []
    assert rep['fills'][0]['title'] == 'Senbonzakura (Hatsune Miku, 2012)'
    assert rep['fills'][0]['rating'] == 80   # 4 stars ×20


def test_empty_artist_field_backfilled(tmp_path):
    rep = import_from(tmp_path / 'export.csv', ['artist', 'song', 'rating'],
                      [['Mystery Artist', 'Some Song', '60']], BASE)
    assert rep['artist_fills'][0]['artist'] == 'Mystery Artist'
    assert rep['new_rows'] == []


def test_cross_script_duplicate(tmp_path):
    rep = import_from(tmp_path / 'export.csv', ['artist', 'song'],
                      [['Mariya Takeuchi', 'プラスティック・ラブ Plastic Love']], BASE)
    assert rep['new_rows'] == []
    assert rep['dup_skip'][0]['tier'] in ('latin', 'combo_latin', 'merge_sig', 'jaccard')


def test_genuinely_new_song_is_added(tmp_path):
    rep = import_from(tmp_path / 'export.csv', ['artist', 'song', 'rating', 'year', 'date_rated'],
                      [['YOASOBI', 'Heroku', '4.5', '2021', '2021-08-01']], BASE)
    assert len(rep['new_rows']) == 1
    new = rep['new_rows'][0]
    assert new['rating'] == '90'
    assert new['title'] == 'Heroku (YOASOBI, 2021)'
    assert new['artist'] == 'YOASOBI'
    assert new['date'] == '2021-08-01'
    assert new['_year'] == 2021


def test_fuzzy_match_skipped_by_default_and_forced_on_request(tmp_path):
    header = ['artist', 'song', 'rating']
    recs = [['Ed Sheeran', 'Shapes of You', '90']]
    skipped = import_from(tmp_path / 'a.csv', header, recs, BASE)
    assert skipped['new_rows'] == [] and len(skipped['needs_review']) == 1
    forced = import_from(tmp_path / 'b.csv', header, recs, BASE, fuzzy='add')
    assert forced['new_rows'][0]['title'] == 'Shapes of You (Ed Sheeran)'
    assert len(forced['new_rows']) == 1


def test_export_self_duplicate_collapse(tmp_path):
    rep = import_from(tmp_path / 'export.csv', ['artist', 'song', 'rating'],
                      [['YOASOBI', 'Heroku', '4.5'], ['YOASOBI', 'Heroku', '4.5']], BASE)
    assert len(rep['new_rows']) == 1
    assert len(rep['self_dupes']) == 1


def test_unrated_export_rows_need_opt_in(tmp_path):
    header = ['artist', 'song']
    recs = [['New Artist', 'Brand New Track']]
    assert import_from(tmp_path / 'a.csv', header, recs, BASE)['new_rows'] == []
    assert import_from(tmp_path / 'b.csv', header, recs, BASE,
                       include_unrated=True)['new_rows']


def test_additions_overlay_is_deduped_against_too(tmp_path):
    """The engine merges the overlay into the base, so a row living only in
    additions must count as a duplicate as well."""
    adds = [row('Bonus Song (New Kid, 2025)', 66, artist='New Kid', song='Bonus Song')]
    rep = import_from(tmp_path / 'export.csv', ['artist', 'song', 'rating'],
                      [['New Kid', 'Bonus Song', '95']], BASE, add_rows=adds)
    assert rep['new_rows'] == []
    assert rep['conflicts'][0]['kept'] == 'existing'   # the 66 wins, RYM's 95 is ignored
    assert rep['conflicts'][0]['existing_rating'] == 66


# ---------------------------------------------------------------------------
# Parity with the engine's own normalization (this is the safety property)
# ---------------------------------------------------------------------------

def test_normalize_sig_matches_taste_engine():
    pytest.importorskip('networkx')
    from src.taste_engine import TasteEngine
    for s in ['Plastic Love (Mariya Takeuchi, 1984)', 'Ado – Value',
              'Katy Perry – California Gurls ft. Snoop Dogg',
              'Welcome to the Club, (2011)', 'Some Song (feat. Nobody) 2020']:
        assert normalize_sig(s) == TasteEngine._normalize_sig(s)
    assert detect_scale(['1', '2', '3']) == 'linear'


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def test_apply_import_writes_only_new_rows(tmp_path, monkeypatch):
    base = tmp_path / 'posts_tails.csv'
    with open(base, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in BASE:
            w.writerow(r)
    year_cache = tmp_path / 'years.json'
    monkeypatch.setattr('scripts.import_rym_export.BASE_CSV', str(base))
    monkeypatch.setattr('scripts.import_rym_export.ADDITIONS_CSV',
                        str(tmp_path / 'posts_tails_additions.csv'))
    monkeypatch.setattr('scripts.import_rym_export.YEAR_CACHE', str(year_cache))

    rep = import_from(tmp_path / 'e.csv',
                      ['artist', 'song', 'rating', 'year'],
                      [['YOASOBI', 'Heroku', '4.5', '2021'],
                       ['Ado', 'Value', '80']], BASE)
    stats = apply_import(rep, target='base', write_years=True, backup=False)
    assert stats['new_songs'] == 1
    assert stats['years_cached'] == 1

    rows = list(csv.DictReader(open(base, encoding='utf-8')))
    assert len(rows) == 6
    assert rows[-1]['title'] == 'Heroku (YOASOBI, 2021)' and rows[-1]['rating'] == '90'
    ado = [r for r in rows if r['artist'] == 'Ado'][0]
    assert ado['rating'] == '70', 'RYM 80 must not clobber the project 70'
    assert json.loads(year_cache.read_text(encoding='utf-8'))['yoasobi|heroku'] == 2021


def test_apply_import_additions_target(tmp_path, monkeypatch):
    adds = tmp_path / 'posts_tails_additions.csv'
    monkeypatch.setattr('scripts.import_rym_export.BASE_CSV', str(tmp_path / 'posts_tails.csv'))
    monkeypatch.setattr('scripts.import_rym_export.ADDITIONS_CSV', str(adds))
    (tmp_path / 'posts_tails.csv').write_text('date,rating,title,tail,artist,song,title_original,title_english\n',
                                              encoding='utf-8')
    rep = import_from(tmp_path / 'e.csv', ['artist', 'song', 'rating'],
                      [['YOASOBI', 'Heroku', '90']], [])
    stats = apply_import(rep, target='additions', write_years=False, backup=False)
    assert stats['new_songs'] == 1
    lines = adds.read_text(encoding='utf-8').strip().splitlines()
    assert lines[0] == 'date,rating,title,tail'
    assert len(lines) == 2


def test_read_table_handles_tsv_and_markdown(tmp_path):
    p = tmp_path / 'e.tsv'
    p.write_text('artist\tsong\trating\nAdo\tValue\t70\n', encoding='utf-8')
    header, recs = read_table(str(p))
    assert header == ['artist', 'song', 'rating'] and recs[0]['song'] == 'Value'

    p2 = tmp_path / 'e.md'
    p2.write_text('| artist | song | rating |\n|---|---|---|\n| Ado | Value | 70 |\n',
                  encoding='utf-8')
    header2, recs2 = read_table(str(p2))
    assert 'artist' in header2 and recs2[0]['rating'] == '70'


def test_import_row_title_style():
    mapping = {'artist': 'artist', 'song': 'song', 'year': 'year', 'rating': 'rating'}
    cand = ImportRow(mapping, {'artist': 'Ado', 'song': 'Value', 'year': '2023',
                               'rating': '70'}, 2)
    assert cand.title == 'Value (Ado, 2023)'
    cand2 = ImportRow({'artist': 'artist', 'song': 'song'},
                      {'artist': 'Ado', 'song': 'Ado – Value'}, 3)
    assert cand2.title == 'Ado – Value', 'do not double the artist when the title already has it'


def test_gap_metrics_counts():
    g = gap_metrics(BASE, [])
    assert g['rows'] == 5 and g['rated'] == 4 and g['unrated'] == 1
    assert g['rated_pct'] == 80.0
