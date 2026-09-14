# RYM ratings import — completed

## Duplicate cleanup update

The O(n) `scripts/check_import_duplicates.py` check has now removed the three
confirmed imported duplicates, preserving their original ratings (93, 1, 82).
All 2,887 pre-import rows were retained unchanged by this cleanup.
Current totals: **5,476 entries, 5,061 rated**. The script recheck finds zero
remaining imported full-artist/song duplicates against the original baseline.
The engine still flags only the pre-existing Ado duplicate, left untouched.

**17 first-side groups remain review-only** (different singles, reissues, or
versions); `rym_post_import_duplicate_candidates.csv` now lists their current
row positions. Cleanup details: `rym_duplicate_cleanup.json`.
Tests: 30 passed (importer and new checker). The previously reported write-back
test failure was not fixed by this targeted cleanup. Suspect TUYU/Mitchie M
blank-rating fills and album-versus-song classification remain separate issues.

The figures and checksum below describe the historical pre-cleanup import/audit.


**Post-import audit found issues requiring review.** See
`rym_post_import_audit.md`: three likely missed duplicate groups and at least
two suspect blank-rating fills. Completion here means the source rows were
processed, not that every match or appended entry is verified clean.

Completed on 2026-09-13 from the user's pasted export, from Ten through
Shiro Sagisu. All **3,091 transcribed rows** were processed.

- **2,592 new entries** added; **41 blank ratings** filled.
- One missing artist credit filled.
- All **2,431 original nonempty ratings preserved**, checked against the
  original Git data. Existing ratings won conflicts.
- Ratings explicitly converted from 1–10 to 0–100 (7 → 70).
- Final dataset: **5,479 entries**, **5,064 rated**.
- All **193 near matches reviewed**: 79 classified as distinct (one duplicate
  collapsed), 102 conservatively kept existing entries, 12 filled blank ratings.
  Ambiguous identities were kept rather than introducing competing ratings;
  this is not a claim that every identity was conclusively verified.

The review decisions are retained in `rym_import_review_decisions.csv`.
Its batch and export-line numbers are historical identifiers. Temporary source
transcriptions, verbose reports, and one-off processing scripts were removed
after completion; this is an audit summary, not an archival copy of the export.
The reusable importer remains at `scripts/import_rym_export.py`, with tests in
`tests/test_import_rym.py`.

No release-year cache backfill was performed. The final pass transcribed only
artist, title, and rating. New entries use the import date, not a historical
listening date. The additions overlay remained unchanged.

Validation at completion: **35 tests passed**, repeat imports proposed no new
writes, and the original CSV header and LF line endings were preserved. The
transcription-parser tests were subsequently removed with that one-off parser.

SHA-256 of `posts_tails.csv` at import completion (also verified during cleanup):
`c7cbc03259199367bdc37ed7e37a7af4aa04987e96045488696400104341e5be`
