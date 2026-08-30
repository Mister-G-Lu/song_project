"""
Tests for src/outliers.py — statistical outlier detection
"""

import pytest
from src.outliers import detect_outliers, _extract_artists_from_title


# ============================================================
# _extract_artists_from_title
# ============================================================

class TestExtractArtists:
    def test_parentheses_pattern(self):
        assert _extract_artists_from_title('Shape of You (Ed Sheeran, 2017)') == ['Ed Sheeran']

    def test_dash_pattern(self):
        assert _extract_artists_from_title('Radiohead - Karma Police') == ['Radiohead']

    def test_en_dash_pattern(self):
        assert _extract_artists_from_title('Radiohead – Karma Police') == ['Radiohead']

    def test_no_match(self):
        assert _extract_artists_from_title('Just A Song Title') == []

    def test_empty(self):
        assert _extract_artists_from_title('') == []
        assert _extract_artists_from_title(None) == []

    def test_multiple_commas(self):
        result = _extract_artists_from_title('Song (Artist Name, 2020)')
        assert result == ['Artist Name']


# ============================================================
# detect_outliers — empty / minimal data
# ============================================================

class TestDetectOutliersEdgeCases:
    def test_empty_data(self):
        result = detect_outliers([], {}, [])
        assert result['categories'] == {}
        assert result['summary'] == {}

    def test_single_song_no_outliers(self):
        entries = [{'title': 'Song (Artist, 2020)', 'rating': '80', '_genre': 'Pop'}]
        artists = {'Artist': {'ratings': [80], 'genre': 'Pop', 'songs': [{'title': 'Song', 'rating': '80'}]}}
        ratings = [80]
        result = detect_outliers(entries, artists, ratings)
        assert result['summary']['total_songs'] == 1
        # Not enough data for most outlier categories
        assert len(result['categories']['artist_volatility']) == 0


# ============================================================
# detect_outliers — artist volatility
# ============================================================

class TestArtistVolatility:
    def test_volatile_artist_detected(self):
        entries = [
            {'title': 'Good Song (Volatile, 2020)', 'rating': '95', '_genre': 'Rock'},
            {'title': 'Bad Song (Volatile, 2020)', 'rating': '30', '_genre': 'Rock'},
            {'title': 'Mid Song (Volatile, 2020)', 'rating': '60', '_genre': 'Rock'},
        ]
        artists = {
            'Volatile': {
                'ratings': [95, 30, 60],
                'genre': 'Rock',
                'songs': [
                    {'title': 'Good Song', 'rating': '95'},
                    {'title': 'Bad Song', 'rating': '30'},
                    {'title': 'Mid Song', 'rating': '60'},
                ]
            }
        }
        result = detect_outliers(entries, artists, [95, 30, 60])
        vol = result['categories']['artist_volatility']
        assert len(vol) == 1
        assert vol[0]['artist'] == 'Volatile'
        assert vol[0]['spread'] == 65

    def test_stable_artist_not_detected(self):
        entries = [
            {'title': 'Song A (Stable, 2020)', 'rating': '80', '_genre': 'Pop'},
            {'title': 'Song B (Stable, 2020)', 'rating': '85', '_genre': 'Pop'},
        ]
        artists = {
            'Stable': {
                'ratings': [80, 85],
                'genre': 'Pop',
                'songs': [
                    {'title': 'Song A', 'rating': '80'},
                    {'title': 'Song B', 'rating': '85'},
                ]
            }
        }
        result = detect_outliers(entries, artists, [80, 85])
        vol = result['categories']['artist_volatility']
        assert len(vol) == 0


# ============================================================
# detect_outliers — genre rebels
# ============================================================

class TestGenreRebels:
    def test_rebel_detected(self):
        # Genre avg = 50, song rated 80 = 30pts above
        entries = [
            {'title': 'Low1 (A, 2020)', 'rating': '50', '_genre': 'Metal'},
            {'title': 'Low2 (A, 2020)', 'rating': '50', '_genre': 'Metal'},
            {'title': 'Low3 (A, 2020)', 'rating': '50', '_genre': 'Metal'},
            {'title': 'Rebel (B, 2020)', 'rating': '80', '_genre': 'Metal'},
        ]
        artists = {}
        ratings = [50, 50, 50, 80]
        result = detect_outliers(entries, artists, ratings)
        rebels = result['categories']['genre_rebels']
        assert len(rebels) >= 1
        assert rebels[0]['rating'] == 80


# ============================================================
# detect_outliers — guilty pleasures
# ============================================================

class TestGuiltyPleasures:
    def test_guilty_pleasure_detected(self):
        # Genre avg < 70, song rated 85+
        entries = [
            {'title': 'Low1 (A, 2020)', 'rating': '50', '_genre': 'Hip-Hop'},
            {'title': 'Low2 (A, 2020)', 'rating': '60', '_genre': 'Hip-Hop'},
            {'title': 'Low3 (A, 2020)', 'rating': '60', '_genre': 'Hip-Hop'},
            {'title': 'Great One (B, 2020)', 'rating': '90', '_genre': 'Hip-Hop'},
        ]
        ratings = [50, 60, 60, 90]
        result = detect_outliers(entries, {}, ratings)
        gp = result['categories']['guilty_pleasures']
        assert len(gp) >= 1
        assert gp[0]['rating'] == 90

    def test_high_avg_genre_no_guilty_pleasure(self):
        # Genre avg > 85, so a 90 is NOT a guilty pleasure
        entries = [
            {'title': 'High1 (A, 2020)', 'rating': '90', '_genre': 'Classical'},
            {'title': 'High2 (A, 2020)', 'rating': '88', '_genre': 'Classical'},
            {'title': 'High3 (A, 2020)', 'rating': '85', '_genre': 'Classical'},
        ]
        ratings = [90, 88, 85]
        result = detect_outliers(entries, {}, ratings)
        gp = result['categories']['guilty_pleasures']
        assert len(gp) == 0


# ============================================================
# detect_outliers — disappointments
# ============================================================

class TestDisappointments:
    def test_disappointment_detected(self):
        # Genre avg > 85, song rated < 60
        # Need enough high-rated songs so the flop doesn't drag avg below 85
        entries = [
            {'title': 'Great1 (A, 2020)', 'rating': '95', '_genre': 'Metal'},
            {'title': 'Great2 (A, 2020)', 'rating': '90', '_genre': 'Metal'},
            {'title': 'Great3 (A, 2020)', 'rating': '92', '_genre': 'Metal'},
            {'title': 'Great4 (A, 2020)', 'rating': '93', '_genre': 'Metal'},
            {'title': 'Great5 (A, 2020)', 'rating': '91', '_genre': 'Metal'},
            {'title': 'Great6 (A, 2020)', 'rating': '94', '_genre': 'Metal'},
            {'title': 'Great7 (A, 2020)', 'rating': '88', '_genre': 'Metal'},
            {'title': 'Flop (B, 2020)', 'rating': '40', '_genre': 'Metal'},
        ]
        ratings = [95, 90, 92, 93, 91, 94, 88, 40]
        result = detect_outliers(entries, {}, ratings)
        disp = result['categories']['disappointments']
        assert len(disp) >= 1
        assert disp[0]['rating'] == 40


# ============================================================
# detect_outliers — one-hit wonders
# ============================================================

class TestOneHitWonders:
    def test_one_hit_detected(self):
        entries = [
            {'title': 'Hit (Star, 2020)', 'rating': '95', '_genre': 'Pop'},
            {'title': 'Flop1 (Star, 2020)', 'rating': '50', '_genre': 'Pop'},
            {'title': 'Flop2 (Star, 2020)', 'rating': '55', '_genre': 'Pop'},
        ]
        artists = {
            'Star': {
                'ratings': [95, 50, 55],
                'genre': 'Pop',
                'songs': [
                    {'title': 'Hit', 'rating': '95'},
                    {'title': 'Flop1', 'rating': '50'},
                    {'title': 'Flop2', 'rating': '55'},
                ]
            }
        }
        result = detect_outliers(entries, artists, [95, 50, 55])
        ohw = result['categories']['one_hit_wonders']
        assert len(ohw) >= 1
        assert ohw[0]['title'] == 'Hit'


# ============================================================
# detect_outliers — rating surprises
# ============================================================

class TestRatingSurprises:
    def test_above_surprise(self):
        # Overall avg 50, song rated 80 = +30 (above 25-pt threshold)
        entries = [
            {'title': 'A (X, 2020)', 'rating': '50', '_genre': 'Pop'},
            {'title': 'B (X, 2020)', 'rating': '50', '_genre': 'Pop'},
            {'title': 'C (X, 2020)', 'rating': '50', '_genre': 'Pop'},
            {'title': 'D (X, 2020)', 'rating': '50', '_genre': 'Pop'},
            {'title': 'E (X, 2020)', 'rating': '50', '_genre': 'Pop'},
            {'title': 'Surprise (Y, 2020)', 'rating': '80', '_genre': 'Rock'},
        ]
        ratings = [50, 50, 50, 50, 50, 80]
        result = detect_outliers(entries, {}, ratings)
        surprises = result['categories']['rating_surprises']
        above = [s for s in surprises if s['direction'] == 'above']
        assert len(above) >= 1

    def test_below_surprise(self):
        entries = [
            {'title': 'A (X, 2020)', 'rating': '90', '_genre': 'Pop'},
            {'title': 'B (X, 2020)', 'rating': '90', '_genre': 'Pop'},
            {'title': 'Dud (Y, 2020)', 'rating': '40', '_genre': 'Rock'},
        ]
        ratings = [90, 90, 40]
        result = detect_outliers(entries, {}, ratings)
        surprises = result['categories']['rating_surprises']
        below = [s for s in surprises if s['direction'] == 'below']
        assert len(below) >= 1


# ============================================================
# detect_outliers — summary
# ============================================================

class TestSummary:
    def test_summary_fields(self):
        entries = [
            {'title': 'A (X, 2020)', 'rating': '80', '_genre': 'Pop'},
            {'title': 'B (Y, 2020)', 'rating': '60', '_genre': 'Rock'},
        ]
        artists = {
            'X': {'ratings': [80], 'genre': 'Pop', 'songs': [{'title': 'A', 'rating': '80'}]},
            'Y': {'ratings': [60], 'genre': 'Rock', 'songs': [{'title': 'B', 'rating': '60'}]},
        }
        result = detect_outliers(entries, artists, [80, 60])
        s = result['summary']
        assert 'overall_avg' in s
        assert 'total_songs' in s
        assert 'total_artists' in s
        assert s['total_songs'] == 2
        assert s['total_artists'] == 2
        assert s['overall_avg'] == 70.0
