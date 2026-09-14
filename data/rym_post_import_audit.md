# RYM post-import audit

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


Read-only audit comparing current `data/posts_tails.csv` against `HEAD` (pre-import data).
No ratings or rows were changed by this audit. Counts below are CSV entries, not
verified unique songs. The export mixes albums, EPs, soundtracks, singles, and reissues.

## Duplicate checks

Ran the actual `TasteEngine.deduplicate(write_back=False)` on isolated in-memory
copies of the raw before/after CSV rows (bypassing startup's prior merge).

- Before: 1 duplicate removed in memory; 2,886 kept.
- After: 1 duplicate removed in memory; 5,478 kept.
- Both report the same pre-existing `Ado – I'm a Controversy` duplicate.
- Thus the import adds no collisions under the engine's normalized-full-title rule.
  This does NOT prove song-level uniqueness.

A supplementary artist+song check folds accents, punctuation, whitespace and a
leading artist `The`. It found **3 likely duplicate groups involving imports**:

| Original entry | Original rating | Imported entry | Imported rating |
|---|---:|---|---:|
| One Republic – If I Lose Myself | 82 | If I Lose Myself (OneRepublic) | 60 |
| Beyonce – Crazy in Love | 93 | Crazy in Love (Beyoncé, 2003) | 70 |
| Chain smokers – SELFIE | 1 | #SELFIE (The Chainsmokers) | 10 |

A further check comparing the first title before ` / ` found **20 candidate
groups**, including those three. These are NOT 20 confirmed duplicates: some
are different recordings or releases. Examples include multiple Beach Boys
`Good Vibrations` singles, ABBA `Waterloo` versus `Waterloo / Watch Out`, and
Twenty One Pilots' studio `Heathens` versus a livestream release.

Full candidates: `rym_post_import_duplicate_candidates.csv`. CSV row numbers
refer to parsed records including the header, not physical lines (reviews can
span lines). The two check categories overlap; do not sum their group counts.

Do not auto-apply the engine's write-back dedup: its policy keeps the HIGHER
rating, not the pre-existing rating requested for this import. Any expanded
cleanup must explicitly retain original entries and review recording identity.

## What the import covered

| Measure | Before | After |
|---|---:|---:|
| Entries | 2,887 | 5,479 |
| Rated entries | 2,431 | 5,064 |
| Blank ratings | 456 | 415 |

- 2,592 entries appended and 41 previously blank ratings populated.
- All 2,431 originally populated ratings verified unchanged again.
- The 41 fills cover about 9% of the original blank-rating backlog, not all of it.
- Examples of filled entries: Sam Cooke — A Change Is Gonna Come (80),
  Tracy Chapman — Fast Car (80), Eminem — Stan (70), Japanese Breakfast —
  Be Sweet (70), Rebecca Black — Crumbs (80), and Interpol — Obstacle 1 (60).
  Some other fills require correction/review, as noted below.
- Largest appended artist-label groups: Taylor Swift (18), Radiohead (15),
  The Beatles (11), Avril Lavigne (11), The Weeknd (11), Coldplay (10),
  Lana Del Rey (10), Carly Rae Jepsen (10), Björk (9), The Cure (9), Daft Punk (9).
  These describe breadth added, not necessarily previously unheard songs.
- The import includes non-song releases such as Radiohead's Kid A/OK Computer,
  Carly Rae Jepsen's E·MO·TION, game soundtracks, and Various Artists compilations.
  Release ratings should not automatically become individual-track ratings.

## Data-quality issues discovered

At least two mechanically filled ratings appear to have matched different works:

- Pasted TUYU `やっぱり雨は降るんだね` (8) versus the existing
  `Tuyu — アサガオの散る頃に`, which received 80.
- Pasted Mitchie M feat. 初音ミク `グレイテスト・アイドル` (8) versus the existing
  `Mitchie M – Freely Tomorrow`, which received 80.

The importer's ASCII/Latin matching can discard the distinguishing Japanese
text and then treat the artist name as enough evidence. This requires a fix
and a review of the affected matches; unchanged original nonempty ratings and
passing importer tests did not establish that blank-rating fills were correct.

## Remaining metadata gaps

With the engine's persisted release-year cache explicitly loaded, using its
current `_release_year_for` resolver on raw rated CSV entries:

- Before: 2,259 / 2,431 resolve a year (92.9%).
- After: 2,727 / 5,064 resolve a year (53.9%).
- Appended entries alone: 428 / 2,592 resolve a year (16.5%).

These are resolution counts, not externally verified release dates. The cache
also contains some very early years, so a decade-level conclusion needs further
validation. Most of the final transcription omitted release dates; this import
expanded the year-enrichment backlog rather than solving it.

All appended rows have the import date 2026-09-13. That is not their listening
history and may produce an artificial spike in date-based charts. Genre/country
coverage was not independently audited here, so no claim of quantified genre
or geographic gap closure is made.

## Tests

Ran `tests/test_dedup.py` and `tests/test_import_rym.py`: **43 passed, 1 failed**.
The failing test is `TestCSVRewrite.test_write_back_removes_dupes`: after reload,
`deduplicate(write_back=True)` reports zero removals where the test expects at
least one. It uses a synthetic temporary CSV, not the imported dataset. This
failure should be investigated before using a destructive dedup workflow.

## Recommended next action

Keep the original ratings; fix the three likely duplicate groups, investigate
and undo incorrect blank-rating fills, tighten Unicode-aware identity matching,
and separate release-level ratings from song-level ratings before using the
new rows as clean recommendation-training data. Preserve the original export
for a later release-year enrichment pass if available.
