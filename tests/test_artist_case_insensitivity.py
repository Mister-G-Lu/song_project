"""Case-insensitive artist + song identity tests.

Prevents the 'Yu Peng Chen listed twice (Capitalization!)' bug class:

  1. Artist index folds case variants   ('lindsey stirling' == 'Lindsey Stirling')
  2. Artist index folds hyphen variants ('Yu Peng Chen'    == 'Yu-Peng Chen')
  3. Pure-CJK artists are NOT collapsed into one bucket
  4. check_song_exists matches artist+song case-insensitively
  5. The favorite-artists collection check resolves raw row spellings
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
def case_engine(tmp_path):
    """Engine with deliberately mixed-case and hyphen-variant artists."""
    csv_path = str(tmp_path / 'posts_tails.csv')
    rows = [
        {'date': '2024-01-01', 'rating': 90,
         'title': 'Song One (Lindsey Stirling, 2020)',
         'tail': '', 'artist': 'Lindsey Stirling', 'song': 'Song One'},
        {'date': '2024-01-02', 'rating': 80,
         'title': 'Song Two (lindsey stirling, 2021)',
         'tail': '', 'artist': 'lindsey stirling', 'song': 'Song Two'},
        {'date': '2024-02-01', 'rating': 95,
         'title': 'Floating Life (Yu-Peng Chen, 2020)',
         'tail': '', 'artist': 'Yu-Peng Chen', 'song': 'Floating Life'},
        {'date': '2024-02-02', 'rating': 85,
         'title': 'Hustle and Bustle of Ormos (Yu Peng Chen, 2021)',
         'tail': '', 'artist': 'Yu Peng Chen', 'song': 'Hustle and Bustle of Ormos'},
        {'date': '2024-03-01', 'rating': 70,
         'title': '夜に駆ける (YOASOBI, 2019)',
         'tail': '', 'artist': 'YOASOBI', 'song': '夜に駆ける'},
        {'date': '2024-03-02', 'rating': 75,
         'title': 'ハルカ (YOASOBI, 2021)',
         'tail': '', 'artist': 'YOASOBI', 'song': 'ハルカ'},
    ]
    return TasteEngine(_make_csv(rows, csv_path))


def test_case_variants_merge_to_one_artist(case_engine):
    """'Lindsey Stirling' and 'lindsey stirling' must be one entry."""
    lindseys = [a for a in case_engine.all_artists
                if 'stirling' in a.lower()]
    assert len(lindseys) == 1
    info = case_engine.all_artists[lindseys[0]]
    assert len(info['ratings']) == 2
    assert info['count'] == 2


def test_hyphen_variants_merge_to_one_artist(case_engine):
    """'Yu-Peng Chen' and 'Yu Peng Chen' must be one entry."""
    chens = [a for a in case_engine.all_artists if 'chen' in a.lower()]
    assert len(chens) == 1
    info = case_engine.all_artists[chens[0]]
    assert len(info['ratings']) == 2
    assert info['count'] == 2
    # Canonical display casing: the variant with the most ratings
    assert chens[0] == 'Yu-Peng Chen'


def test_resolver_ignores_case_and_punctuation(case_engine):
    assert case_engine._artist_case('yu-peng chen') == 'Yu-Peng Chen'
    assert case_engine._artist_case('YU PENG CHEN') == 'Yu-Peng Chen'
    assert case_engine._artist_case('LINDSEY STIRLING') in (
        'Lindsey Stirling', 'lindsey stirling')


def test_pure_cjk_artists_not_collapsed(case_engine):
    """Alphanumeric fold would normalize CJK names to '' — must not merge."""
    yoasobi = [a for a in case_engine.all_artists if a == 'YOASOBI']
    assert len(yoasobi) == 1
    # Distinct CJK-only names must stay distinct even with same fold
    assert case_engine._fold_artist_key('夜に駆ける') == '夜に駆ける'


def test_check_song_exists_case_insensitive(case_engine):
    for artist in ('yu-peng chen', 'YU PENG CHEN', 'Yu-Peng Chen'):
        result = case_engine.check_song_exists(artist, 'floating life')
        assert result['exists'] is True, artist
    # A genuinely different song must not match
    assert case_engine.check_song_exists('YoASOBI', 'Completely Different Song')['exists'] is False


def test_favorite_artists_collection_flag_resolves_raw_spelling(
        case_engine, monkeypatch):
    """get_favorite_artists resolves raw-cased config names against the
    folded all_artists index — a lowercase config entry must still find
    'Lindsey Stirling' and report her merged collection stats."""
    import src.taste_engine as te

    monkeypatch.setattr(te, 'FAVORITE_ARTISTS', {'lindsey stirling': 95})
    favs = case_engine.get_favorite_artists()
    assert len(favs) == 1
    entry = favs[0]
    assert entry['in_collection'] is True
    assert entry['song_count'] == 2          # both case variants merged
    assert entry['collection_ratings'] == [90, 80]


def test_artist_self_rows_never_count_as_songs(tmp_path):
    """title == artist == song rows (imported artist-level ratings) must
    count toward artist ratings but never appear as song entries."""
    csv_path = str(tmp_path / 'posts_tails.csv')
    rows = [
        {'date': '2026-09-13', 'rating': '70', 'title': 'Michael Jackson',
         'tail': '', 'artist': 'Michael Jackson', 'song': 'Michael Jackson'},
        {'date': '2026-09-13', 'rating': '80', 'title': 'Aardvark',
         'tail': '', 'artist': 'Aardvark', 'song': 'Aardvark'},
    ]
    e = TasteEngine(_make_csv(rows, csv_path))
    mj = e.all_artists.get('Michael Jackson') or {}
    assert mj.get('ratings') == [70]         # rating still counts for the artist
    assert mj.get('songs') == []             # but not as a song
    assert mj.get('count') == 0
    # And the constellation can never list the artist as their own song
    for artist, info in e.all_artists.items():
        for song in info.get('songs', []):
            assert song['title'].strip().lower() != artist.strip().lower()


def test_generic_artist_names_never_resolve_to_genre(tmp_path):
    """Placeholder names must not inherit genres from cache or curated
    entries — case-insensitive lookups would otherwise leak pollution
    ('unknown artist': 'J-Pop/Anime') into every unattributed row."""
    csv_path = str(tmp_path / 'posts_tails.csv')
    rows = [
        {'date': '2024-01-01', 'rating': '80', 'title': 'Mystery Track – Rock Anthem',
         'tail': 'a great rock song', 'artist': 'Unknown Artist', 'song': 'Mystery Track'},
    ]
    e = TasteEngine(_make_csv(rows, csv_path))
    # Poison the caches with generic-name entries, as past test runs did
    e._artist_genre_cache['unknown artist'] = 'J-Pop/Anime'
    e._rebuild_genre_cache_folded()
    assert e._is_generic_artist_name('Unknown Artist')
    assert e._is_generic_artist_name('[unknown artist]')
    assert e._is_generic_artist_name('Test Artist')
    assert not e._is_generic_artist_name('Neon Skyline')
    assert e._lookup_genre_cached('Unknown Artist') is None
    assert e._curated_genre_for('Unknown Artist') is None
    # Row still classifies via its own title/review keywords → Rock
    assert e.rows[0]['_genre'] == 'Rock'


def test_genre_cache_fold_conflicts_resolve_deterministically(tmp_path):
    """Contradictory cached genres across case-variants must resolve:
    curated agreement first, then the variant with the most ratings."""
    csv_path = str(tmp_path / 'posts_tails.csv')
    rows = [
        {'date': '2024-01-01', 'rating': '90', 'title': 'S1 (Guns N Roses, 2019)',
         'tail': '', 'artist': "Guns N' Roses", 'song': 'S1'},
        {'date': '2024-01-02', 'rating': '85', 'title': 'S2 (Guns N Roses, 2020)',
         'tail': '', 'artist': "Guns N' Roses", 'song': 'S2'},
    ]
    e = TasteEngine(_make_csv(rows, csv_path))
    # Historical junk: curly-apostrophe variant cached with a noise genre
    e._artist_genre_cache['Guns N’ Roses'] = 'J-Pop/Anime'
    e._artist_genre_cache["Guns N' Roses"] = 'Rock'
    e._rebuild_genre_cache_folded()
    # Curated says Rock — the curated-agreeing value must win over the noise
    assert e._lookup_genre_cached('guns n’ roses') == 'Rock'
    assert e._lookup_genre_cached("GUNS N' ROSES") == 'Rock'
