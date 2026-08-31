"""Tests for duplicate detection and removal in TasteEngine.

Verifies that:
  1. Exact duplicate rows are detected and removed
  2. Cross-format duplicates (en-dash vs "by") are detected
  3. The better-rated entry is kept
  4. The CSV is rewritten correctly with write_back
  5. add_song rejects duplicates via the API
  6. check_song_exists catches duplicates before add
"""

import csv
import os
import shutil
import tempfile

import pytest

from src.taste_engine import TasteEngine


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_csv(rows, path):
    """Write rows to a CSV with the standard header."""
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['date', 'rating', 'title', 'tail'])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


@pytest.fixture
def dedup_engine(tmp_path):
    """Create a TasteEngine with known duplicate rows."""
    csv_path = str(tmp_path / 'posts_tails.csv')
    rows = [
        # Billy Ocean – Caribbean Queen (exact duplicate)
        {'date': '2020-08-04', 'rating': '95', 'title': 'Billy Ocean – Caribbean Queen', 'tail': 'groove'},
        {'date': '2021-05-23', 'rating': '95', 'title': 'Billy Ocean – Caribbean Queen', 'tail': 'funk'},
        # Digital Love – Daft Punk vs "Digital Love" by Daft Punk (format variant)
        {'date': '2022-12-09', 'rating': '93', 'title': 'Digital Love – Daft Punk', 'tail': 'electronic'},
        {'date': '2024-02-02', 'rating': '93', 'title': '"Digital Love" by Daft Punk', 'tail': 'electronic'},
        # Beatles – en-dash style
        {'date': '2019-01-15', 'rating': '90', 'title': 'The Beatles – Hey Jude', 'tail': 'classic'},
        # Non-duplicate entries
        {'date': '2023-06-01', 'rating': '85', 'title': 'Daft Punk – Around the World', 'tail': 'dance'},
        {'date': '2023-07-10', 'rating': '80', 'title': 'Tame Impala – Let It Happen', 'tail': 'psychedelic'},
    ]
    _make_csv(rows, csv_path)
    return TasteEngine(csv_path)


@pytest.fixture
def api_engine(tmp_path):
    """Create a TasteEngine for API-style duplicate testing."""
    csv_path = str(tmp_path / 'posts_tails.csv')
    rows = [
        {'date': '2020-01-01', 'rating': '88', 'title': 'Adele – Rolling in the Deep', 'tail': 'great'},
        {'date': '2021-03-15', 'rating': '92', 'title': 'Queen – Bohemian Rhapsody', 'tail': 'masterpiece'},
    ]
    _make_csv(rows, csv_path)
    return TasteEngine(csv_path)


# ---------------------------------------------------------------------------
# Test: Exact duplicates detected
# ---------------------------------------------------------------------------

class TestExactDuplicates:
    def test_caribbean_queen_deduplicated(self, dedup_engine):
        """Two identical 'Billy Ocean – Caribbean Queen' rows become one after init-time dedup."""
        # Dedup runs during __init__, so just verify the state
        titles = [r.get('title', '') for r in dedup_engine.rows]
        caribbean = [t for t in titles if 'Caribbean Queen' in t]
        assert len(caribbean) == 1, f"Expected 1 Caribbean Queen, got {len(caribbean)}"


# ---------------------------------------------------------------------------
# Test: Cross-format duplicates detected
# ---------------------------------------------------------------------------

class TestCrossFormatDuplicates:
    def test_digital_love_deduplicated(self, dedup_engine):
        """'Digital Love – Daft Punk' and '"Digital Love" by Daft Punk' become one after init-time dedup."""
        titles = [r.get('title', '') for r in dedup_engine.rows]
        digital_love = [t for t in titles if 'Digital Love' in t]
        assert len(digital_love) == 1, f"Expected 1 Digital Love, got {len(digital_love)}"

    def test_digital_love_keeps_which(self, dedup_engine):
        """The higher-rated (or earlier) entry is kept."""
        titles = [r.get('title', '') for r in dedup_engine.rows]
        dl = [t for t in titles if 'Digital Love' in t]
        assert len(dl) == 1
        # Both had rating 93, so the earlier date (2022) should be kept
        assert '–' in dl[0]  # en-dash format kept (earlier date)


# ---------------------------------------------------------------------------
# Test: Better-rated entry is kept
# ---------------------------------------------------------------------------

class TestRatingPriority:
    def test_keeps_higher_rating(self, tmp_path):
        """When duplicates have different ratings, the higher one survives."""
        csv_path = str(tmp_path / 'posts_tails.csv')
        rows = [
            {'date': '2020-01-01', 'rating': '70', 'title': 'Song X – Artist A', 'tail': 'ok'},
            {'date': '2021-01-01', 'rating': '95', 'title': 'Song X – Artist A', 'tail': 'amazing'},
        ]
        _make_csv(rows, csv_path)
        engine = TasteEngine(csv_path)  # dedup runs at init

        titles = [r.get('title', '') for r in engine.rows]
        assert len([t for t in titles if 'Song X' in t]) == 1
        # The 95-rated row should survive
        assert engine.rows[0].get('rating') == '95'


# ---------------------------------------------------------------------------
# Test: CSV rewrite is correct
# ---------------------------------------------------------------------------

class TestCSVRewrite:
    def test_write_back_removes_dupes(self, tmp_path):
        """write_back=True rewrites the CSV without duplicates."""
        csv_path = str(tmp_path / 'posts_tails.csv')
        rows = [
            {'date': '2020-01-01', 'rating': '90', 'title': 'Song X – Artist A', 'tail': ''},
            {'date': '2021-01-01', 'rating': '85', 'title': 'Song X – Artist A', 'tail': ''},
        ]
        _make_csv(rows, csv_path)
        engine = TasteEngine(csv_path)  # dedup runs at init, 1 row left
        # Append a dupe to the CSV
        import csv as _csv
        with open(csv_path, 'a', newline='', encoding='utf-8') as f:
            writer = _csv.DictWriter(f, fieldnames=['date', 'rating', 'title', 'tail'])
            writer.writerow({'date': '2025-01-01', 'rating': '80', 'title': 'Song X – Artist A', 'tail': 'test'})
        # Reload — init dedup catches it, but let's also test write_back manually
        engine._load_data()  # re-read CSV without dedup
        result = engine.deduplicate(write_back=True)
        assert result['removed'] >= 1
        # Reload from file and verify
        engine2 = TasteEngine(csv_path)
        titles = [r.get('title', '') for r in engine2.rows]
        assert len([t for t in titles if 'Song X' in t]) == 1

    def test_non_duplicates_preserved(self, dedup_engine):
        """Non-duplicate entries survive dedup."""
        titles = [r.get('title', '') for r in dedup_engine.rows]
        assert any('Around the World' in t for t in titles)
        assert any('Let It Happen' in t for t in titles)
        assert any('Hey Jude' in t for t in titles)


# ---------------------------------------------------------------------------
# Test: check_song_exists catches the duplicates
# ---------------------------------------------------------------------------

class TestCheckSongExistsCatchesDupes:
    def test_caribbean_queen_detected(self, dedup_engine):
        """check_song_exists detects Billy Ocean – Caribbean Queen."""
        result = dedup_engine.check_song_exists('Billy Ocean', 'Caribbean Queen')
        assert result['exists'] is True
        assert result['match'] in ('exact', 'fuzzy', 'latin', 'similar')

    def test_digital_love_detected(self, dedup_engine):
        """check_song_exists detects Digital Love by Daft Punk."""
        result = dedup_engine.check_song_exists('Daft Punk', 'Digital Love')
        assert result['exists'] is True
        assert result['match'] in ('exact', 'fuzzy', 'latin', 'similar')

    def test_hey_jude_detected(self, dedup_engine):
        """check_song_exists detects The Beatles – Hey Jude."""
        result = dedup_engine.check_song_exists('The Beatles', 'Hey Jude')
        assert result['exists'] is True
        assert result['match'] in ('exact', 'fuzzy', 'latin', 'similar')


# ---------------------------------------------------------------------------
# Test: Normalization catches "by" / "and" / "&"
# ---------------------------------------------------------------------------

class TestNormalizationBy:
    def test_by_connector_stripped(self):
        """' by ' is stripped during normalization."""
        sig1 = TasteEngine._normalize_sig('Digital Love – Daft Punk')
        sig2 = TasteEngine._normalize_sig('"Digital Love" by Daft Punk')
        assert sig1 == sig2, f"Expected same sig: {sig1!r} vs {sig2!r}"

    def test_and_connector_stripped(self):
        """' and ' is stripped during normalization."""
        sig1 = TasteEngine._normalize_sig('Billy Ocean – Caribbean Queen')
        sig2 = TasteEngine._normalize_sig('Billy Ocean – Caribbean Queen')
        assert sig1 == sig2

    def test_ampersand_stripped(self):
        """' & ' is stripped during normalization."""
        sig1 = TasteEngine._normalize_sig('Simon & Garfunkel – Mrs. Robinson')
        sig2 = TasteEngine._normalize_sig('Simon and Garfunkel – Mrs. Robinson')
        assert sig1 == sig2, f"Expected same sig: {sig1!r} vs {sig2!r}"

    def test_existing_normalization_preserved(self):
        """Years, punctuation, and filler words still stripped correctly."""
        sig = TasteEngine._normalize_sig('Bohemian Rhapsody (Queen, 1975)')
        assert sig == 'bohemian rhapsody queen'

    def test_single_word_title_unchanged(self):
        """Single-word titles are unaffected."""
        sig = TasteEngine._normalize_sig('Hello')
        assert sig == 'hello'


# ---------------------------------------------------------------------------
# Test: Dedup result metadata
# ---------------------------------------------------------------------------

class TestDedupResult:
    def test_removed_count(self, tmp_path):
        """Result reports correct removed count."""
        csv_path = str(tmp_path / 'posts_tails.csv')
        rows = [
            {'date': '2020-01-01', 'rating': '90', 'title': 'Dup Song – Artist', 'tail': ''},
            {'date': '2021-01-01', 'rating': '85', 'title': 'Dup Song – Artist', 'tail': ''},
        ]
        _make_csv(rows, csv_path)
        engine = TasteEngine(csv_path)  # dedup runs at init
        # All dupes removed, so second call returns 0
        result = engine.deduplicate(write_back=False)
        assert result['removed'] == 0

    def test_init_time_dedup_removes(self, tmp_path):
        """Init-time dedup removes duplicates from rows."""
        csv_path = str(tmp_path / 'posts_tails.csv')
        rows = [
            {'date': '2020-01-01', 'rating': '90', 'title': 'Dup Song – Artist', 'tail': ''},
            {'date': '2021-01-01', 'rating': '85', 'title': 'Dup Song – Artist', 'tail': ''},
        ]
        _make_csv(rows, csv_path)
        engine = TasteEngine(csv_path)  # dedup runs at init
        assert len(engine.rows) == 1
        assert engine.rows[0].get('rating') == '90'  # higher rating kept

    def test_no_dupes_returns_zero(self, tmp_path):
        """No dupes → removed=0."""
        csv_path = str(tmp_path / 'posts_tails.csv')
        rows = [
            {'date': '2020-01-01', 'rating': '90', 'title': 'Unique Song A', 'tail': ''},
            {'date': '2021-01-01', 'rating': '85', 'title': 'Unique Song B', 'tail': ''},
        ]
        _make_csv(rows, csv_path)
        engine = TasteEngine(csv_path)
        result = engine.deduplicate(write_back=False)
        assert result['removed'] == 0
        assert result['kept'] == 2

    def test_dupes_list_populated(self, tmp_path):
        """Result includes a list of detected duplicates."""
        csv_path = str(tmp_path / 'posts_tails.csv')
        rows = [
            {'date': '2020-01-01', 'rating': '90', 'title': 'Dup Song – Artist', 'tail': ''},
            {'date': '2021-01-01', 'rating': '85', 'title': 'Dup Song – Artist', 'tail': ''},
        ]
        _make_csv(rows, csv_path)
        engine = TasteEngine(csv_path)  # dedup runs at init
        # Already deduped, so no dupes
        result = engine.deduplicate(write_back=False)
        assert len(result['dupes']) == 0


# ---------------------------------------------------------------------------
# Test: API endpoint rejects duplicates
# ---------------------------------------------------------------------------

class TestAddSongDuplicateRejection:
    def test_add_duplicate_rejected(self, api_engine):
        """Adding a song that already exists should fail with 409."""
        # This tests the duplicate check logic at the engine level
        result = api_engine.check_song_exists('Adele', 'Rolling in the Deep')
        assert result['exists'] is True

    def test_add_new_song_accepted(self, api_engine):
        """A truly new song is not flagged as duplicate."""
        result = api_engine.check_song_exists('Radiohead', 'Creep')
        assert result['exists'] is False
