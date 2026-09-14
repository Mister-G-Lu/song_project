# RYM import summary

Imported the user's pasted RYM export on 2026-09-13, with existing ratings taking
priority. All 3,091 transcribed source rows were processed, including duplicates.

- 2,589 entries retained after removing 3 confirmed imported duplicates.
- 41 blank ratings and one missing artist credit filled.
- Final dataset: 5,476 entries, 5,061 rated.
- All 2,431 originally populated ratings verified unchanged.
- Rating conversion: 1–10 → 0–100 (7 → 70).
- New rows use the import date, not historical listening dates.
- Most final-pass release dates were not transcribed; no year-cache backfill.

## Checks and retained audit

`rym_import_review_decisions.csv` preserves 193 reviewed near matches. Historical
batch/line identifiers refer to the now-removed temporary transcriptions. Some
ambiguous identities were conservatively skipped, not conclusively verified.

`check_import_duplicates.py` removed imported duplicates of Beyoncé — Crazy in
Love, The Chainsmokers — SELFIE, and OneRepublic — If I Lose Myself, retaining
original ratings 93, 1, and 82. All 2,887 pre-import rows were unchanged by cleanup.
A recheck found no imported full-artist/song duplicates against the baseline.
The engine's narrower check still finds one pre-existing Ado duplicate.

`rym_post_import_duplicate_candidates.csv` retains 17 review-only first-side
groups (split singles, reissues, versions). Do not automatically merge these.

## Known issues for follow-up

- Suspect blank fills: TUYU's やっぱり雨は降るんだね rating appears assigned to
  アサガオの散る頃に; Mitchie M's グレイテスト・アイドル album rating appears assigned
  to Freely Tomorrow. Both received 80. Investigate and correct these matches.
- Latin-only matching can discard distinguishing Japanese text. Tighten it
  before future imports; preserving old nonempty ratings does not validate fills.
- The export mixes song and release ratings (albums, EPs, soundtracks). Appended
  entries are not necessarily unique songs or clean song-level training examples.
- At the pre-cleanup audit, the loaded engine year resolver covered 2,727/5,064
  rated entries (53.9%), versus 2,259/2,431 before import (92.9%). Year metadata
  needs enrichment; these resolution counts are not verified release dates.
- 30 targeted importer/checker tests passed after duplicate cleanup. A separate
  existing dedup write-back test failed: `TestCSVRewrite.test_write_back_removes_dupes`
  expected removals after reload but got zero. It was not fixed in this import.

Reusable tools: `scripts/import_rym_export.py`, `scripts/check_import_duplicates.py`.
Use dry-run reports first. The engine's write-back dedup keeps the highest rating,
not necessarily the original, so it is not the policy used for this cleanup.
