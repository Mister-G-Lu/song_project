"""
The song → release-year mapping stored in the dataset itself.

`data/posts_tails.csv` gained an appended `release_year` column (see
src/csv_schema.py and scripts/merge_release_years_into_csv.py), so the year is
a property of the row rather than something each reader re-derives from a
cache. These tests pin the schema, the coverage floor, the engine's
prefer-the-column behaviour, and the merge script's idempotency.
"""

import csv
import uuid
from pathlib import Path

import pytest

from src.csv_schema import (
    CSV_COLUMNS,
    CSV_COLUMNS_WITH_YEAR,
    RELEASE_YEAR_COLUMN,
    coerce_release_year,
)
from src.taste_engine import TasteEngine

DATA_CSV = Path(__file__).resolve().parent.parent / "data" / "posts_tails.csv"
ADDITIONS_CSV = DATA_CSV.with_name("posts_tails_additions.csv")

# Frozen floor just under the measured coverage (84.9% of rated rows at the
# time of the merge) so genuine regressions fail without being brittle.
MIN_RATED_COVERAGE = 0.84


def _rows(path):
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        return header, [r for r in reader if r]


@pytest.fixture
def client():
    """Flask test client (same shape as tests/test_app.py uses)."""
    from app import app
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


# ---------------------------------------------------------------------------
# The checked-in dataset
# ---------------------------------------------------------------------------

class TestDatasetSchema:
    def test_base_csv_has_appended_release_year_column(self):
        """The column exists, and it is APPENDED so the old 8 columns keep
        their positions for anything reading the file positionally."""
        header, _ = _rows(DATA_CSV)
        assert header == CSV_COLUMNS_WITH_YEAR
        assert header[:8] == CSV_COLUMNS

    def test_every_row_matches_the_header_width(self):
        header, rows = _rows(DATA_CSV)
        ragged = [(i, len(r)) for i, r in enumerate(rows, start=2)
                  if len(r) != len(header)]
        assert ragged == []

    def test_stored_years_are_plausible(self):
        """Every non-empty cell parses; junk would silently reach the charts."""
        header, rows = _rows(DATA_CSV)
        idx = header.index(RELEASE_YEAR_COLUMN)
        for i, row in enumerate(rows, start=2):
            cell = row[idx]
            if cell.strip():
                assert coerce_release_year(cell) is not None, \
                    f"row {i}: unparseable release_year {cell!r}"

    def test_dataset_files_keep_lf_endings(self):
        """The dataset is LF-only, no BOM, trailing newline — writers in the
        app and the merge script must not sneak CRLF back in."""
        for path in (DATA_CSV, ADDITIONS_CSV):
            raw = path.read_bytes()
            assert b"\r\n" not in raw, f"{path.name} has CRLF line endings"
            assert not raw.startswith(b"\xef\xbb\xbf"), f"{path.name} has a BOM"
            assert raw.endswith(b"\n"), f"{path.name} is missing its final newline"

    def test_additions_csv_matches_the_same_schema(self):
        header, rows = _rows(ADDITIONS_CSV)
        assert header == CSV_COLUMNS_WITH_YEAR
        assert all(len(r) == len(header) for r in rows)

    def test_rated_row_coverage(self):
        engine = TasteEngine()
        rated = engine.rated_entries
        stored = sum(1 for r in rated
                     if coerce_release_year(r.get(RELEASE_YEAR_COLUMN)) is not None)
        assert stored / len(rated) >= MIN_RATED_COVERAGE, \
            f"only {stored}/{len(rated)} rated rows carry a stored year"

    def test_stored_years_agree_with_the_resolver(self):
        """The column is a cache of the same cascade, so the two must not
        disagree — a mismatch means one of them is stale."""
        engine = TasteEngine()
        mismatches = []
        for r in engine.rated_entries:
            stored = coerce_release_year(r.get(RELEASE_YEAR_COLUMN))
            cascaded = TasteEngine._release_year_for(
                r.get("title", ""), r.get("artist", ""))
            if stored is not None and cascaded is not None and stored != cascaded:
                mismatches.append((r.get("title"), stored, cascaded))
        assert mismatches == []


# ---------------------------------------------------------------------------
# Engine behaviour
# ---------------------------------------------------------------------------

def _write_csv(path, header, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)
    return str(path)


class TestEnginePrefersTheStoredColumn:
    def test_stored_year_wins_over_the_cache(self, tmp_path):
        """A hand-corrected cell must beat the enrichment cache."""
        path = _write_csv(tmp_path / "rows.csv", CSV_COLUMNS_WITH_YEAR, [
            ["2024-01-01", "90", "Dancing Queen - ABBA", "", "ABBA",
             "Dancing Queen", "", "", "1999"],
        ])
        engine = TasteEngine(path)
        row = engine.rated_entries[0]
        assert engine._row_release_year(row) == 1999
        assert engine._row_release_year_source(row) == "csv"

    def test_missing_cell_falls_back_to_the_cascade(self, tmp_path):
        path = _write_csv(tmp_path / "rows.csv", CSV_COLUMNS_WITH_YEAR, [
            ["2024-01-01", "90", "Dancing Queen - ABBA", "", "ABBA",
             "Dancing Queen", "", "", ""],
        ])
        engine = TasteEngine(path)
        row = engine.rated_entries[0]
        # The curated challenge DB is the fallback authority for this title.
        assert engine._row_release_year(row) == 1976
        assert engine._row_release_year_source(row) == "db"

    def test_legacy_file_without_the_column_still_resolves(self, tmp_path):
        """Old 8-column files (and old additions overlays) keep working."""
        path = _write_csv(tmp_path / "rows.csv", CSV_COLUMNS, [
            ["2024-01-01", "90", "Dancing Queen - ABBA", "", "ABBA",
             "Dancing Queen", "", ""],
        ])
        engine = TasteEngine(path)
        assert engine._row_release_year(engine.rated_entries[0]) == 1976

    def test_evolution_reports_the_csv_as_a_source(self, tmp_path):
        path = _write_csv(tmp_path / "rows.csv", CSV_COLUMNS_WITH_YEAR, [
            ["2024-01-01", "90", "Some Obscure Song", "", "Nobody", "", "", "", "2011"],
            ["2024-01-02", "80", "Another Obscure Song", "", "Nobody", "", "", "", "2011"],
        ])
        engine = TasteEngine(path)
        coverage = engine.get_evolution()["release_year_coverage"]
        assert coverage["by_source"]["csv"] == 2
        assert coverage["matched"] == 2

    def test_junk_year_cells_are_ignored_and_normalized(self, tmp_path):
        path = _write_csv(tmp_path / "rows.csv", CSV_COLUMNS_WITH_YEAR, [
            ["2024-01-01", "90", "Song One", "", "Artist", "", "", "", "2016.0"],
            ["2024-01-02", "80", "Song Two", "", "Artist", "", "", "", "not a year"],
        ])
        engine = TasteEngine(path)
        years = [engine._row_release_year(r) for r in engine.rated_entries]
        assert years == [2016, None]
        # The cell is normalized in memory ('2016.0' → '2016'), junk → ''
        assert engine.rated_entries[0][RELEASE_YEAR_COLUMN] == "2016"
        assert engine.rated_entries[1][RELEASE_YEAR_COLUMN] == ""

    def test_artist_year_model_uses_the_column(self):
        """The model must see stored years even without a resolver callable."""
        from src.artist_year_model import ArtistYearModel
        entries = [
            {"artist": "Band A", "rating": "90", "title": "Song1",
             "date": "2020-01-01", RELEASE_YEAR_COLUMN: "2010"},
            {"artist": "Band A", "rating": "70", "title": "Song2",
             "date": "2020-06-01", RELEASE_YEAR_COLUMN: "2020"},
        ]
        model = ArtistYearModel()
        model.build(entries, release_year_fn=None)
        assert model.predict("Band A", 2010) > model.predict("Band A", 2020)

    def test_model_accepts_one_and_two_arg_resolvers(self):
        """Older callers pass fn(title); the engine passes (title, artist)."""
        from src.artist_year_model import _extract_entries
        rows = [
            {"artist": "A", "rating": "80", "title": "X (2010)", "date": "2020-01-01"},
            {"artist": "B", "rating": "90", "title": "Y (2015)", "date": "2020-01-02"},
        ]
        one_arg = _extract_entries(rows, lambda title: 2010 if "X" in title else None)
        assert [e["year"] for e in one_arg] == [2010]
        two_arg = _extract_entries(rows, lambda title, artist: 2015 if "Y" in title else None)
        assert [e["year"] for e in two_arg] == [2015]


# ---------------------------------------------------------------------------
# Write paths keep the column alive
# ---------------------------------------------------------------------------

class TestWritePaths:
    def test_quick_add_stores_the_resolved_year(self):
        """The quick-add write path resolves the year once, at write time."""
        import app as app_module
        from app import _append_to_additions, _new_row

        row = _new_row("2026-01-01", "88", "Dancing Queen - ABBA", "")
        assert row[RELEASE_YEAR_COLUMN] == "1976"

        _append_to_additions(row)
        header, rows = _rows(Path(app_module.taste_engine.additions_path))
        assert header == CSV_COLUMNS_WITH_YEAR
        record = dict(zip(header, rows[-1]))
        assert record["title"] == "Dancing Queen - ABBA"
        assert record[RELEASE_YEAR_COLUMN] == "1976"

    def test_add_song_endpoint_writes_a_canonical_row(self, client):
        """Whatever the resolver finds, the row is written under the same
        schema as the base file — never as a short 4-column line."""
        import app as app_module
        title = f"Wholly Unreviewed Song {uuid.uuid4().hex[:8]} (Nova Artist)"
        resp = client.post("/api/add-song", json={"title": title, "rating": 77})
        assert resp.status_code in (200, 201)

        header, rows = _rows(Path(app_module.taste_engine.additions_path))
        assert header == CSV_COLUMNS_WITH_YEAR
        record = dict(zip(header, rows[-1]))
        assert record["title"] == title
        assert record[RELEASE_YEAR_COLUMN] == ""  # unknown song, left blank

    def test_append_migrates_a_legacy_four_column_overlay(self):
        """Appending to an old date,rating,title,tail file must not shift
        columns for every later reader."""
        import app as app_module
        from app import _append_to_additions

        path = Path(app_module.taste_engine.additions_path)
        _write_csv(path, ["date", "rating", "title", "tail"],
                   [["2024-01-01", "70", "Old Row – Artist", "note"]])
        _append_to_additions({"date": "2024-02-02", "rating": "80",
                              "title": "New Row – Artist", "tail": "",
                              RELEASE_YEAR_COLUMN: "1999"})

        header, rows = _rows(path)
        assert header == CSV_COLUMNS_WITH_YEAR
        assert len(rows) == 2
        old = dict(zip(header, rows[0]))
        assert old["rating"] == "70" and old["title"] == "Old Row – Artist"
        new = dict(zip(header, rows[1]))
        assert new[RELEASE_YEAR_COLUMN] == "1999"

    def test_append_keeps_lf_endings(self):
        """Appending must not flip the overlay to CRLF (it did before the
        writer was given an explicit lineterminator)."""
        import app as app_module
        from app import _append_to_additions

        path = Path(app_module.taste_engine.additions_path)
        _append_to_additions({"date": "2026-01-01", "rating": "70",
                              "title": "LF Probe – Artist", "tail": ""})
        raw = path.read_bytes()
        assert b"\r\n" not in raw
        assert raw.endswith(b"\n")

    def test_dedup_write_back_preserves_stored_years(self, tmp_path):
        path = _write_csv(tmp_path / "rows.csv", CSV_COLUMNS_WITH_YEAR, [
            ["2020-01-01", "90", "Song X – Artist A", "", "Artist A", "Song X", "", "", "1991"],
            ["2021-01-01", "80", "Song Y – Artist A", "", "Artist A", "Song Y", "", "", "1994"],
        ])
        engine = TasteEngine(path)
        engine.deduplicate(write_back=True)
        header, rows = _rows(Path(path))
        assert header == CSV_COLUMNS_WITH_YEAR
        years = {dict(zip(header, r))["title"]: dict(zip(header, r))[RELEASE_YEAR_COLUMN]
                 for r in rows}
        assert years == {"Song X – Artist A": "1991", "Song Y – Artist A": "1994"}


# ---------------------------------------------------------------------------
# The merge script
# ---------------------------------------------------------------------------

class TestMergeScript:
    def _merge(self, path, force=False):
        from scripts.merge_release_years_into_csv import merge_file
        return merge_file(Path(path), force=force, dry_run=False)

    def test_fills_missing_years_and_is_idempotent(self, tmp_path):
        path = _write_csv(tmp_path / "rows.csv", CSV_COLUMNS, [
            ["2024-01-01", "90", "Dancing Queen - ABBA", "", "ABBA",
             "Dancing Queen", "", ""],
            ["2024-01-02", "70", "Shape of You", "", "Ed Sheeran",
             "Shape of You", "", ""],
        ])
        stats = self._merge(path)
        assert stats["filled"] == 2
        header, rows = _rows(Path(path))
        assert header == CSV_COLUMNS_WITH_YEAR
        years = [dict(zip(header, r))[RELEASE_YEAR_COLUMN] for r in rows]
        assert years == ["1976", "2017"]

        first_pass = Path(path).read_bytes()
        stats2 = self._merge(path)
        assert stats2["changed"] is False
        assert Path(path).read_bytes() == first_pass

    def test_report_mode_writes_nothing(self, tmp_path):
        from scripts.merge_release_years_into_csv import merge_file
        path = _write_csv(tmp_path / "rows.csv", CSV_COLUMNS, [
            ["2024-01-01", "90", "Dancing Queen - ABBA", "", "ABBA",
             "Dancing Queen", "", ""],
        ])
        before = Path(path).read_bytes()
        stats = merge_file(Path(path), dry_run=True)
        assert stats["filled"] == 1
        assert Path(path).read_bytes() == before

    def test_repairs_an_unquoted_comma_in_the_title(self, tmp_path):
        """A stray comma pushes every later column one slot right; the merge
        puts the title back together instead of exporting shifted data."""
        path = tmp_path / "rows.csv"
        path.write_text(
            "date,rating,title,tail,artist,song,title_original,title_english\n"
            "2026-09-19,75,Jesus, Take the Wheel,,Carrie Underwood,,,\n",
            encoding="utf-8",
        )
        stats = self._merge(path)
        assert stats["repaired"], "split title was not repaired"
        header, rows = _rows(Path(path))
        record = dict(zip(header, rows[0]))
        assert record["title"] == "Jesus, Take the Wheel"
        assert record["artist"] == "Carrie Underwood"
        assert record["song"] == "Jesus, Take the Wheel"
        assert record["tail"] == ""

    def test_leaves_hand_edited_years_alone_without_force(self, tmp_path):
        path = _write_csv(tmp_path / "rows.csv", CSV_COLUMNS_WITH_YEAR, [
            ["2024-01-01", "90", "Dancing Queen - ABBA", "", "ABBA",
             "Dancing Queen", "", "", "1999"],
        ])
        self._merge(path)
        header, rows = _rows(Path(path))
        assert dict(zip(header, rows[0]))[RELEASE_YEAR_COLUMN] == "1999"

        self._merge(path, force=True)
        header, rows = _rows(Path(path))
        assert dict(zip(header, rows[0]))[RELEASE_YEAR_COLUMN] == "1976"

    def test_checked_in_dataset_is_already_merged(self):
        """Running the script against the real dataset is a no-op."""
        from scripts.merge_release_years_into_csv import merge_file
        stats = merge_file(DATA_CSV, dry_run=True)
        assert stats["changed"] is False, \
            f"{stats['filled']} rows would change — re-run the merge script"
