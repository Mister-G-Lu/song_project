#!/usr/bin/env python3
"""
merge_release_years_into_csv.py — store the song → release-year mapping in the
dataset itself.

Why this exists
---------------
The app has always been able to show "Song vs Year" (Evolution) and release-year
blind spots, but that mapping was *derived at runtime* from a cascade:

    1. data/challenge_db.json          (230 hand-curated songs, authoritative)
    2. data/release_year_cache.json    (6k songs enriched from iTunes/MusicBrainz)
    3. a 4-digit year inside the title ("Song (Artist, 2012)")

Nothing was ever written back into data/posts_tails.csv, so the project's main
data file could not answer the simplest question about itself — "what year is
this song from?" — and the answer could drift with the cache.

This script merges that mapping into the CSV as an APPENDED column:

    date,rating,title,tail,artist,song,title_original,title_english,release_year

The column is appended (not inserted) so positional readers of the original
8-column schema keep working, and rows without a value still resolve through
the same cascade — no consumer breaks.

Offline by design: it only reads the caches already committed to the repo. Any
song still unresolved afterwards is reported; `scripts/enrich_release_years.py`
(which needs network) can look those up, and re-running this script picks the
new years up.

Usage (from the project root)
-----------------------------
    python scripts/merge_release_years_into_csv.py --report   # what would change
    python scripts/merge_release_years_into_csv.py            # fill blanks
    python scripts/merge_release_years_into_csv.py --force    # recompute all
"""

import argparse
import csv
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.csv_schema import (  # noqa: E402
    CSV_COLUMNS_WITH_YEAR,
    RELEASE_YEAR_COLUMN,
    coerce_release_year,
)
from src.taste_engine import TasteEngine  # noqa: E402

DEFAULT_FILES = [
    ROOT / "data" / "posts_tails.csv",
    ROOT / "data" / "posts_tails_additions.csv",
]

def read_csv(path: Path):
    """Read a dataset CSV → (header, rows). Empty/missing → (None, [])."""
    if not path.exists():
        return None, []
    with open(path, "r", encoding="utf-8", newline="") as f:
        rows = [r for r in csv.reader(f) if r and any(c.strip() for c in r)]
    if not rows:
        return None, []
    return rows[0], rows[1:]


def repair_row(row, header_len):
    """Rejoin a title split by an unquoted comma.

    '2026-09-19,75,Jesus, Take the Wheel,...' parses as one field too many,
    with the title cut in half. Returns (repaired_row, note) or (row, None)
    when no safe repair applies.
    """
    if len(row) != header_len + 1:
        return row, None
    title = row[2] + "," + row[3]
    repaired = row[:2] + [title] + row[4:]
    if len(repaired) != header_len:
        return row, None
    return repaired, f"rejoined split title → {title!r}"


def merge_file(path: Path, force: bool = False, dry_run: bool = False) -> dict:
    """Fill the release_year column of one CSV. Returns a stats dict.

    Idempotent: a second run finds every stored year already valid and writes
    nothing. Existing values are only recomputed with --force.
    """
    header, rows = read_csv(path)
    stats = {
        "path": str(path),
        "rows": 0,
        "already": 0,
        "filled": 0,
        "unresolved": 0,
        "malformed": 0,
        "repaired": [],
        "unresolved_titles": [],
        "changed": False,
    }
    if header is None:
        stats["missing"] = True
        return stats

    # Canonical columns first, then any extra columns the file already has —
    # so the merge never drops a column somebody added by hand.
    fields = list(header)
    for col in CSV_COLUMNS_WITH_YEAR:
        if col not in fields:
            fields.append(col)
    out_rows = []
    for row in rows:
        repaired, note = repair_row(row, len(header))
        if note:
            stats["repaired"].append(note)
            row = repaired
        if len(row) != len(header):
            stats["malformed"] += 1
            stats["unresolved_titles"].append(
                f"malformed row ({len(row)} fields): {row[:3]}")
            row = (row + [""] * len(header))[: len(header)]

        record = {name: row[i] for i, name in enumerate(header)}
        if note and (record.get("artist") or "").strip() and not (record.get("song") or "").strip():
            # A rejoined title was the song name; keep the structured column
            # in step so artist-based analyses see it without title parsing.
            record["song"] = record["title"]
        stats["rows"] += 1

        existing = coerce_release_year(record.get(RELEASE_YEAR_COLUMN))
        if existing is not None and not force:
            stats["already"] += 1
            record[RELEASE_YEAR_COLUMN] = str(existing)
        else:
            year = TasteEngine._release_year_for(
                record.get("title", ""), record.get("artist", ""))
            if year is None:
                stats["unresolved"] += 1
                if record.get("title"):
                    stats["unresolved_titles"].append(record["title"])
                record[RELEASE_YEAR_COLUMN] = ""
            else:
                if existing != year:
                    stats["filled"] += 1
                record[RELEASE_YEAR_COLUMN] = str(year)

        out_rows.append([record.get(name, "") or "" for name in fields])

    rendered = _render(fields, out_rows)
    if rendered != _render(header, rows):
        stats["changed"] = True
        if not dry_run:
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(rendered)

    return stats


def _render(header, rows) -> str:
    import io

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow([("" if v is None else v) for v in row])
    return buf.getvalue()


def report(stats: dict) -> None:
    name = os.path.basename(stats["path"])
    if stats.get("missing"):
        print(f"{name}: not present — skipped")
        return
    total = stats["rows"] or 1
    print(f"{name}")
    print(f"  rows                 : {stats['rows']}")
    print(f"  year already stored  : {stats['already']}")
    print(f"  year filled in now   : {stats['filled']}")
    print(f"  still unresolved     : {stats['unresolved']} "
          f"({100 * stats['unresolved'] / total:.1f}%)")
    if stats["repaired"]:
        print(f"  malformed rows fixed : {len(stats['repaired'])}")
        for note in stats["repaired"]:
            print(f"    - {note}")
    if stats.get("malformed"):
        print(f"  malformed rows       : {stats['malformed']} (padded)")
    if stats["unresolved_titles"]:
        print("  unresolved (first 10):")
        for title in stats["unresolved_titles"][:10]:
            print(f"    - {title}")
    print(f"  file {'rewritten' if stats['changed'] else 'unchanged'}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Merge the song → release-year mapping into the dataset CSV.")
    parser.add_argument("--report", action="store_true",
                        help="Show what would change without writing anything.")
    parser.add_argument("--force", action="store_true",
                        help="Recompute every row, overwriting stored years.")
    parser.add_argument("--files", nargs="*", default=None,
                        help="CSV files to process (default: base + additions).")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    files = [Path(p) for p in args.files] if args.files else DEFAULT_FILES

    # Load the committed release-year cache once (no network).
    TasteEngine._load_release_year_cache()

    exit_code = 0
    for path in files:
        stats = merge_file(path, force=args.force, dry_run=args.report)
        report(stats)

    if args.report:
        print("\nDry run — nothing was written. Re-run without --report to merge.")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
