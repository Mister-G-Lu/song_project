# Merging song → release year into `posts_tails.csv`

**Question:** the app maps songs to their release year (Evolution's "Song vs
Year", year blind spots, the artist×year model), but that mapping is not in
`data/posts_tails.csv`, the main data source. Can it be merged in?

**Answer: yes — and it now is.** Every row carries a `release_year` column,
merged offline from the existing caches by one idempotent script.

## Where the year used to live

A runtime cascade, no persisted answer:

1. `data/challenge_db.json` — 230 hand-curated songs (authoritative)
2. `data/release_year_cache.json` — 6,128 songs enriched from iTunes/MusicBrainz
3. a 4-digit year inside the title (`"Song (Artist, 2012)"`)

Two problems fell out of that: the CSV could not answer the simplest question
about itself, and callers disagreed with each other — the fast path looked up
`artist|song` while much of the cache was written `song|artist`, so
title-only lookups resolved a different set of songs than artist-aware ones.

## What the merge produced

`data/posts_tails.csv` — `date,rating,title,tail,artist,song,title_original,title_english,release_year`
(the column is **appended**, so readers of the original 8-column schema keep working):

| | before | after |
|---|---|---|
| rated songs with a year (runtime resolution) | 4,046 / 4,972 = 81.4% | — |
| rated songs with a **stored** year | 0 | 4,223 / 4,973 = **84.9%** |
| base-CSV rows with a year | 0 / 5,507 | 4,608 / 5,507 (83.7%) |
| additions overlay | 0 / 59 | 54 / 59 |

The +177 rows over the old runtime number come from three fixes made while
merging:

* **reversed cache keys** (`shapeofyou|edsheeran` was never found when the
  lookup asked for `edsheeran|shapeofyou`) — +177
* **bracket-decorated titles** (`Brightest Light (ft. Josh Wantie)`) — +1
* one row whose unquoted comma (`Jesus, Take the Wheel`) had shifted every
  following column one slot right since it was added

The 750 rated songs (15.1%) that stay blank have no offline source: anime /
Vocaloid / city-pop one-offs, game OSTs, private uploads. They are left empty
rather than guessed.

## Filling the rest

The sandbox this was merged in has no outbound network, so the enrichment step
had to be skipped. On a networked machine:

```bash
python scripts/enrich_release_years.py            # iTunes/MusicBrainz → cache
python scripts/merge_release_years_into_csv.py    # picks the new years up
```

## The script

`scripts/merge_release_years_into_csv.py`

```bash
python scripts/merge_release_years_into_csv.py --report   # dry run + coverage
python scripts/merge_release_years_into_csv.py            # fill blanks only
python scripts/merge_release_years_into_csv.py --force    # recompute every row
```

* **offline** — reads only the committed caches
* **idempotent** — a second run rewrites nothing (verified by test)
* **non-destructive** — fills blanks by default; hand-edited years survive
  unless `--force`; non-year columns are never touched
* writes LF, no BOM, trailing newline (matches the existing files)

## Code changes

| file | change |
|---|---|
| `src/csv_schema.py` *(new)* | canonical columns + `coerce_release_year()` validation (junk/sub-1900/future years are ignored) |
| `src/taste_engine.py` | `_row_release_year()` / `_row_release_year_source()` — stored cell first, cascade second; reversed cache-key fallback; `get_evolution()["release_year_coverage"]["by_source"]` gained `"csv"` |
| `src/artist_year_model.py` | model + backtest read the stored column (and accept 1-arg or 2-arg resolvers) |
| `app.py` | quick-add/batch-add/import resolve the year once and store it; additions writes are schema-aligned (legacy 4-column overlays are migrated, not shifted); `/api/songs` returns `release_year` |
| `scripts/export_static.py` | static songs dump carries `release_year` too |
| `tests/test_release_year_csv.py` *(new)* | 22 tests: schema, coverage floor, column-beats-cache, legacy-file fallback, write paths, merge idempotency + ragged-row repair |
| `README.md`, `DECISIONS.md` (ADR-006) | documented |

## Data-quality fixes that came along

* `2026-09-19,75,Jesus, Take the Wheel,,Carrie Underwood,…` — the unquoted
  comma made the CSV parse title=`Jesus`, tail=` Take the Wheel`,
  artist=`Carrie Underwood`, song=`` — repaired (title rejoined, `song` filled)
* `posts_tails_additions.csv` — two 4-column quick-add rows under an 8-column
  header are now padded/aligned; every row matches the header again
* both files: no ragged rows left (asserted in tests)

## Test status

`python -m pytest -q` → **873 passed, 8 failed**. All 8 failures reproduce on
the pre-change checkout (`git stash`/worktree baseline: 851 passed, same 8
failures) — they are data-dependent tests unrelated to this change, e.g.
`/api/songs?search=love` asserting a title match when the row that matched is
`artist="Love"`, and batch-add tests that re-add fixed titles already in the
test session.
