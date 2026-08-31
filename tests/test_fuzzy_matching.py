"""
Tests for cross-script fuzzy duplicate detection.

Verifies that songs with non-Latin characters (Japanese, CJK, etc.)
are correctly matched against their Latin equivalents, and that 95%+
similar titles are flagged as duplicates.
"""

import csv
import os
import tempfile
import pytest
from src.taste_engine import TasteEngine


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def csv_with_mixed_scripts(tmp_path):
    """CSV with songs mixing Latin and non-Latin characters."""
    data = [
        ['date', 'rating', 'title', 'tail'],
        ['2019-02-21', '98', 'Plastic Love (Mariya Takeuchi, 1984)',
         'City pop classic with a great groove. disco funk groovy'],
        ['2020-05-10', '85', 'Flyday Chinatown (Yasuha, 1981)',
         'Japanese city pop banger. synth pop'],
        ['2021-01-15', '90', 'Stay With Me (Miki Matsubara, 1979)',
         'City pop masterpiece. soul jazz fusion'],
        ['2022-03-20', '75', '[MV] IU(아이유) _ Twenty-three(스물셋)',
         'Korean pop ballad. pop ballad'],
        ['2022-06-15', '88', "Girls' Generation 소녀시대 'The Boys'",
         'K-pop classic. pop dance'],
        ['2023-01-01', '80', 'EXO-K 엑소케이 중독 (Overdose)',
         'K-pop dance track. pop dance'],
        ['2023-06-01', '92', 'BTOB (비투비) – WOW',
         'K-pop ballad. pop'],
        ['2023-09-15', '70', 'Karma – CircusP ft. Eyeris (Cover)【JubyPhonic】',
         'Vocaloid cover. electronic'],
        ['2024-01-01', '85', 'Smoke and Mirrors【Jayn】',
         'Electronic track. electronic synth'],
        ['2024-06-01', '95', 'Plastic Love (Mariya Takeuchi)',
         'City pop classic — no year in title'],
        ['2024-08-01', '82', 'Yellow – 神山 羊',
         'J-rock track. rock'],
    ]
    p = tmp_path / 'posts_tails.csv'
    with open(p, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerows(data)
    return str(p)


@pytest.fixture
def engine_mixed(csv_with_mixed_scripts):
    return TasteEngine(csv_path=csv_with_mixed_scripts)


# ============================================================
# _normalize_latin tests
# ============================================================

class TestNormalizeLatin:
    def test_strips_japanese_katakana(self):
        result = TasteEngine._normalize_latin('プラスティック・ラブ')
        assert result == ''

    def test_strips_japanese_with_english(self):
        result = TasteEngine._normalize_latin('プラスティック・ラブ (Plastic Love)')
        assert result == 'plastic love'

    def test_preserves_latin_only(self):
        result = TasteEngine._normalize_latin('Plastic Love')
        assert result == 'plastic love'

    def test_strips_korean(self):
        result = TasteEngine._normalize_latin('아이유 Twenty-three')
        assert result == 'twenty three'

    def test_strips_chinese(self):
        result = TasteEngine._normalize_latin('李玉刚 – 刚好遇见你')
        assert result == ''

    def test_strips_mixed_script_preserves_latin(self):
        result = TasteEngine._normalize_latin('BTOB (비투비) – WOW')
        assert result == 'btob wow'

    def test_strips_special_brackets(self):
        result = TasteEngine._normalize_latin('【Jenny】Battle Against A True Hero')
        assert result == 'jenny battle against a true hero'

    def test_empty_input(self):
        assert TasteEngine._normalize_latin('') == ''

    def test_pure_numbers(self):
        # Year regex strips 4-digit sequences, so '12345' → '5'
        result = TasteEngine._normalize_latin('12345')
        assert result == '5'

    def test_strips_accents(self):
        result = TasteEngine._normalize_latin('café résumé')
        assert result == 'caf r sum'


# ============================================================
# _similar_score tests
# ============================================================

class TestSimilarScore:
    def test_identical(self):
        assert TasteEngine._similar_score('plastic love', 'plastic love') == 1.0

    def test_same_words_different_order(self):
        score = TasteEngine._similar_score('the beatles yesterday', 'beatles yesterday the')
        assert score == 1.0

    def test_different_songs(self):
        score = TasteEngine._similar_score('plastic love', 'galway girl')
        assert score == 0.0

    def test_one_empty(self):
        assert TasteEngine._similar_score('', 'plastic love') == 0.0
        assert TasteEngine._similar_score('plastic love', '') == 0.0

    def test_partial_overlap(self):
        score = TasteEngine._similar_score('city pop love', 'city pop groove')
        assert 0.4 <= score <= 0.6

    def test_subset_low_score(self):
        # 'plastic love' is a subset of 'plastic love mariya takeuchi' → 2/4 = 0.5
        score = TasteEngine._similar_score('plastic love', 'plastic love mariya takeuchi')
        assert score == 0.5


# ============================================================
# check_song_exists: Cross-script matching
# ============================================================

class TestCheckSongCrossScript:
    def test_english_matches_mixed_script_db_entry(self, engine_mixed):
        """'IU Twenty-three' should match '[MV] IU(아이유) _ Twenty-three(스물셋)'."""
        result = engine_mixed.check_song_exists('IU', 'Twenty-three')
        assert result['exists'] is True

    def test_latin_artist_matches_korean_entry(self, engine_mixed):
        """'BTOB WOW' should match 'BTOB (비투비) – WOW'."""
        result = engine_mixed.check_song_exists('BTOB', 'WOW')
        assert result['exists'] is True

    def test_latin_only_matches_mixed_script(self, engine_mixed):
        """'The Boys' should match 'Girls' Generation 소녀시대 The Boys'."""
        result = engine_mixed.check_song_exists('', 'The Boys')
        assert result['exists'] is True

    def test_exact_still_works(self, engine_mixed):
        """Exact matches still work."""
        result = engine_mixed.check_song_exists('Mariya Takeuchi', 'Plastic Love')
        assert result['exists'] is True

    def test_unknown_still_false(self, engine_mixed):
        """Truly unknown songs still return False."""
        result = engine_mixed.check_song_exists('Nobody', 'Totally Made Up Song Title XYZ')
        assert result['exists'] is False

    def test_bare_latin_matches_mixed_script(self, engine_mixed):
        """'smoke and mirrors' should match 'Smoke and Mirrors【Jayn】'."""
        result = engine_mixed.check_song_exists('', 'smoke and mirrors')
        assert result['exists'] is True


# ============================================================
# _build_song_index: Latin titles populated
# ============================================================

class TestBuildSongIndexLatin:
    def test_latin_titles_populated(self, engine_mixed):
        assert len(engine_mixed._latin_titles) > 0

    def test_latin_to_raw_populated(self, engine_mixed):
        assert len(engine_mixed._latin_to_raw) > 0

    def test_raw_to_latin_populated(self, engine_mixed):
        assert len(engine_mixed._raw_to_latin) > 0

    def test_latin_titles_contain_english_parts(self, engine_mixed):
        """Latin titles should contain the English parts of mixed-script entries."""
        latin = engine_mixed._latin_titles
        # Should have entries containing 'btob', 'wow', 'twenty', 'three'
        all_latin_str = ' '.join(latin)
        assert 'btob' in all_latin_str
        assert 'twenty' in all_latin_str


# ============================================================
# check_recs: already_owned via Latin matching
# ============================================================

class TestCheckRecsOwnership:
    def test_mixed_script_rec_marked_owned(self, engine_mixed):
        """A rec with English title matching a DB entry with Korean chars should be tagged."""
        recs = [{'artist': 'BTOB', 'song': 'WOW'}]
        checked = engine_mixed.check_recs(recs)
        assert checked[0]['already_owned'] is True

    def test_unknown_rec_not_owned(self, engine_mixed):
        recs = [{'artist': 'Unknown Artist', 'song': 'Totally Made Up Song XYZ'}]
        checked = engine_mixed.check_recs(recs)
        assert checked[0]['already_owned'] is False


# ============================================================
# Performance: timeout safety
# ============================================================

class TestTimeoutSafety:
    def test_check_song_exists_completes_quickly(self, engine_mixed):
        """check_song_exists should complete well within the timeout."""
        import time
        start = time.monotonic()
        engine_mixed.check_song_exists('Unknown', 'Unknown Song')
        elapsed = time.monotonic() - start
        assert elapsed < 5.0  # Should be way under 10s timeout
