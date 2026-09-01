"""
Tests for Year Conquest endpoint filtering.

Verifies that songs the user has already reviewed (including edge cases
like different formatting, fuzzy matches, and Latin normalization) are
properly excluded from conquest suggestions.
"""

import json
import os
import tempfile
import pytest
from src.taste_engine import TasteEngine


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def csv_with_stairway(tmp_path):
    """CSV with Stairway to Heaven and other edge-case entries."""
    data = [
        ['date', 'rating', 'title', 'tail'],
        ['2020-01-01', '95', 'Stairway To Heaven (Led Zeppelin, 1971)', 'Classic rock epic'],
        ['2020-02-01', '88', 'Rolling in the Deep (Adele, 2011)', 'Powerful pop ballad'],
        ['2020-03-01', '80', 'Bohemian Rhapsody – Queen', 'Opera rock masterpiece'],
        ['2020-04-01', '75', 'Hey Jude - The Beatles', 'Singalong classic'],
        ['2020-05-01', '90', 'Smoke and Mirrors【Jayn】', 'Electronic track'],
        ['2020-06-01', '85', 'Plastic Love (Mariya Takeuchi)', 'City pop classic'],
        ['2020-07-01', '70', 'BTOB (비투비) – WOW', 'K-pop ballad'],
    ]
    p = tmp_path / 'posts_tails.csv'
    with open(p, 'w', newline='', encoding='utf-8') as f:
        import csv
        writer = csv.writer(f)
        writer.writerows(data)
    return str(p)


@pytest.fixture
def conquest_db():
    """Sample conquest database with matching and non-matching songs."""
    return {
        "1971": [
            {"artist": "Led Zeppelin", "song": "Stairway to Heaven", "acclaim": 5},
            {"artist": "Marvin Gaye", "song": "What's Going On", "acclaim": 5},
        ],
        "2011": [
            {"artist": "Adele", "song": "Rolling in the Deep", "acclaim": 5},
            {"artist": "Adele", "song": "Someone Like You", "acclaim": 5},
            {"artist": "Bon Iver", "song": "Holocene", "acclaim": 5},
        ],
        "1975": [
            {"artist": "Queen", "song": "Bohemian Rhapsody", "acclaim": 5},
        ],
        "1968": [
            {"artist": "The Beatles", "song": "Hey Jude", "acclaim": 5},
        ],
        "2016": [
            {"artist": "Jayn", "song": "Smoke and Mirrors", "acclaim": 4},
        ],
        "1984": [
            {"artist": "Mariya Takeuchi", "song": "Plastic Love", "acclaim": 5},
        ],
        "2015": [
            {"artist": "BTOB", "song": "WOW", "acclaim": 4},
        ],
        "2020": [
            {"artist": "Dua Lipa", "song": "Don't Start Now", "acclaim": 4},
            {"artist": "The Weeknd", "song": "Blinding Lights", "acclaim": 5},
        ],
    }


@pytest.fixture
def engine_with_data(csv_with_stairway):
    return TasteEngine(csv_path=csv_with_stairway)


# ============================================================
# Conquest filtering tests
# ============================================================

class TestConquestFiltering:
    """Test that conquest properly filters already-reviewed songs."""

    def test_exact_match_filtered(self, engine_with_data):
        """Songs with exact normalized signature should be filtered."""
        result = engine_with_data.check_song_exists('Led Zeppelin', 'Stairway to Heaven')
        assert result['exists'] is True

    def test_format_variant_filtered(self, engine_with_data):
        """Songs with different formatting should be caught by fuzzy matching."""
        # CSV has 'Rolling in the Deep (Adele, 2011)' — check that 'Adele - Rolling in the Deep' matches
        result = engine_with_data.check_song_exists('Adele', 'Rolling in the Deep')
        assert result['exists'] is True

    def test_reversed_artist_song_filtered(self, engine_with_data):
        """Songs where artist/song order differs should be caught."""
        # CSV has 'Bohemian Rhapsody – Queen' — check reversed
        result = engine_with_data.check_song_exists('Queen', 'Bohemian Rhapsody')
        assert result['exists'] is True

    def test_hyphen_separator_filtered(self, engine_with_data):
        """Songs using different separators should be caught."""
        # CSV has 'Hey Jude - The Beatles'
        result = engine_with_data.check_song_exists('The Beatles', 'Hey Jude')
        assert result['exists'] is True

    def test_latin_normalization_filtered(self, engine_with_data):
        """Songs with CJK characters should match Latin-only queries."""
        # CSV has 'BTOB (비투비) – WOW'
        result = engine_with_data.check_song_exists('BTOB', 'WOW')
        assert result['exists'] is True

    def test_bracket_format_filtered(self, engine_with_data):
        """Songs with special brackets should match clean queries."""
        # CSV has 'Smoke and Mirrors【Jayn】'
        result = engine_with_data.check_song_exists('Jayn', 'Smoke and Mirrors')
        assert result['exists'] is True

    def test_unknown_song_not_filtered(self, engine_with_data):
        """Songs not in the database should NOT be filtered."""
        result = engine_with_data.check_song_exists('Unknown Artist', 'Totally Fake Song XYZ')
        assert result['exists'] is False

    def test_city_pop_filtered(self, engine_with_data):
        """City pop with year in title should match clean query."""
        # CSV has 'Plastic Love (Mariya Takeuchi)'
        result = engine_with_data.check_song_exists('Mariya Takeuchi', 'Plastic Love')
        assert result['exists'] is True


class TestConquestSignatureMatching:
    """Test that _get_reviewed_sigs returns correct signatures."""

    def test_all_formats_produce_sigs(self, csv_with_stairway):
        """All CSV title formats should produce matchable signatures."""
        engine = TasteEngine(csv_path=csv_with_stairway)
        sigs = set()
        for entry in engine.rated_entries:
            title = entry.get('title', '')
            if title:
                sigs.add(engine._normalize_sig(title))
                for artist, song in engine._parse_title_candidates(title):
                    sigs.add(engine._normalize_sig(f"{artist} {song}"))
                    sigs.add(engine._normalize_sig(f"{song} {artist}"))

        # Stairway to Heaven — both orders
        assert 'stairway to heaven led zeppelin' in sigs
        assert 'led zeppelin stairway to heaven' in sigs

        # Adele — both orders
        assert 'rolling in the deep adele' in sigs
        assert 'adele rolling in the deep' in sigs

        # Queen — both orders
        assert 'bohemian rhapsody queen' in sigs
        assert 'queen bohemian rhapsody' in sigs

    def test_conquest_sig_matches_reviewed_sig(self, csv_with_stairway):
        """Conquest key format (artist song) should match reviewed sigs."""
        engine = TasteEngine(csv_path=csv_with_stairway)
        sigs = set()
        for entry in engine.rated_entries:
            title = entry.get('title', '')
            if title:
                sigs.add(engine._normalize_sig(title))
                for artist, song in engine._parse_title_candidates(title):
                    sigs.add(engine._normalize_sig(f"{artist} {song}"))
                    sigs.add(engine._normalize_sig(f"{song} {artist}"))

        # These are the sigs the conquest endpoint generates
        conquest_cases = [
            ('Led Zeppelin', 'Stairway to Heaven'),
            ('Adele', 'Rolling in the Deep'),
            ('Queen', 'Bohemian Rhapsody'),
            ('The Beatles', 'Hey Jude'),
            ('Mariya Takeuchi', 'Plastic Love'),
        ]

        for artist, song in conquest_cases:
            sig = engine._normalize_sig(f"{artist} {song}")
            assert sig in sigs, f"Conquest sig '{sig}' for '{artist} – {song}' not found in reviewed sigs"
