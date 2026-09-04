# Design Decisions

A log of notable design decisions and their rationale. Entries are appended
over time so future changes are made with context instead of surprise.

---

## ADR-001 — Deprecate number-key view navigation

**Date:** 2026-07-31
**Status:** Deprecated (code removed)

**Decision:** Remove the keyboard shortcut that used number keys `1`–`8` to
jump between the sidebar views (Dashboard, Recommender, Blind Spots, etc.).

**Why:**
- The global `keydown` handler in `app.js` had **no input guard**, so typing
  digits into the quick-add modal hijacked navigation. Entering a rating like
  `85` or a song title containing numbers (e.g. "1, 2, 3") silently switched
  views mid-typing and lost focus.
- The sidebar buttons are one click away; a numeric quick-jump added little
  value and caused real friction exactly where users type the most (the
  "Add a song you just heard" flow).

**What changed:**
- Removed the `1`–`8` keydown handler from `static/js/app.js` (replaced with a
  comment explaining why).
- The `A` quick-add shortcut in `static/js/quickadd.js` was **kept** — it
  already guards against typing in inputs (`INPUT`/`TEXTAREA`/`SELECT`).
- `VALID_VIEWS` remains in `static/js/utils.js` — it's still used by
  `switchView()` for validation, just no longer for key mapping.

**Alternative considered:** Add an input-focused guard to the number handler
(same as the `A` shortcut). Rejected: the feature was judged unnecessary —
per the user, "it is easy to click [the sidebar] so no reason for this weird
ability."

---

## ADR-002 — Listened tracking lives in a JSON file, not a database

**Date:** 2026-08-25
**Status:** Accepted

**Decision:** Track listened/not-listened state for recommended songs in
`data/listened.json` — a plain dict keyed by the normalized `artist + song`
signature — exposed through `GET /api/listened` and `POST /api/mark-listened`,
and annotated onto recommendations, weekly picks, and challenges as a
`listened` boolean. The weekly digest email (`scripts/weekly_digest.py`) reads
the same file to report which picks you've already listened to.

**Why:**
- The project's source of truth is already git-friendly, human-readable files
  (CSV for songs, JSON for the ban list / challenge DB). A JSON store keeps
  that consistency — no schema, no migrations, diffable, committable.
- Keys use `TasteEngine._normalize_sig`, the same normalization as the dedup
  layer, so a song marked listened in the Weekly view matches the same
  recommendation in the Recommender (and vice versa).
- At personal scale (hundreds of entries max) the file is tiny; the read cost
  of loading it per request is negligible.

**Alternative considered:** SQLite via the stdlib. Rejected: the ban list
already proves the JSON-file pattern at this scale; SQLite adds a binary file
that is harder to diff and reason about in git.

**Consequence:** the GitHub Pages static snapshot carries a frozen copy of the
listened state (annotated at build time by `scripts/export_static.py`).
Toggling is a write action and is disabled there, exactly like the other
read-only edits — the live app (or the local one) is where listened state
changes.

---

## ADR-003 — Future: Levenshtein/SequenceMatcher tier for cross-script dedup

**Date:** 2026-08-30
**Status:** Proposed (not yet implemented)

**Decision:** Add `difflib.SequenceMatcher` (Python stdlib, zero dependencies)
as an additional similarity tier in `check_song_exists`, below the existing
Jaccard word-set similarity.

**Why:**
- Jaccard (word-set overlap) works well for multi-word titles but is blind to
typo-level character differences: "Plastik Love" vs "Plastic Love" scores 0.0
Jaccard (different word sets) but 0.91 SequenceMatcher (only 1 char off).
- `difflib.SequenceMatcher` is stdlib — no pip install required, no new
dependency to maintain.
- Industry best practice (from data engineering literature): Levenshtein /
Jaro-Winkler / SequenceMatcher are the standard character-level fuzzy match
algorithms. Jaccard is a word-level complement.
- Spotify Dedup uses title + artist + duration matching. We can't do duration
(no duration in CSV), but character-level similarity fills part of that gap.

**Proposed implementation:**
```python
# In check_song_exists, after Jaccard tier:
from difflib import SequenceMatcher

for known_title in self.known_titles:
    score = SequenceMatcher(None, latin_sig, known_title).ratio()
    if score >= 0.90:
        return {'exists': True, 'match': 'levenshtein', 'title': None}
```

Threshold: 0.90 (slightly lower than Jaccard's 0.95 because SequenceMatcher
is character-level and naturally scores lower for partial overlaps).

**What was NOT implemented and why:**
- **Duration-based dedup**: CSV has no duration data. Would require Spotify API
calls per comparison — too slow and adds API dependency.
- **Soundex/phonetic matching**: Not installed (`rapidfuzz`, `jellyfish`).
Soundex is English-centric and won't help with CJK/Cyrillic/Arabic scripts.
Would need a pip install for marginal benefit over SequenceMatcher.
- **ISRC codes**: Not available in our CSV data format.

**Research backing:**
- Spotify community confirms Japanese/romanized duplicates slip through their
system (they rely on ISRC + metadata URIs, not title strings).
- ICMR 2023 cross-language music recommendation paper uses collaborative
filtering, not title matching, for cross-language dedup.
- String normalization best practices: lowercase → strip diacritics → remove
filler words → remove non-word chars → apply similarity algorithm. Our
`_normalize_latin` already handles most of this pipeline.

---

## ADR-004 — Discover view: open-catalog candidates from Deezer, not Spotify

**Date:** 2026-09-02
**Status:** Accepted

**Decision:** Add a single **Discover** view backed by `src/discovery.py`,
which generates candidates from an *open* catalog: your top-rated artists →
Deezer "related artists" → their top tracks, minus anything you own / ignored /
clearly dislike. Difficulty (`easy` / `medium` / `hard`) controls how far out
in the graph and how deep in the track list we look, in the spirit of
ListenBrainz Radio's modes. The same module powers "new releases from your
artists" and a per-mode hit-rate log (`data/discovery_log.json`).

**Why Deezer:** Spotify removed `recommendations`, `audio-features`,
`related-artists` and 30-second previews for all apps created after
2024-11-27 with no replacement. Deezer's REST API needs no key, has a
related-artists graph, top tracks, album release dates, cover art and previews
(fetched client-side via JSONP so they also work on GitHub Pages). ListenBrainz
Labs similar-artists is a free second source that can slot into
`fetch_related()` later.

**Why not add feedback buttons (👍/👎):** the rating you give when you save a
song is already the strongest possible signal; a separate thumb would be a
second thing to click and a second store to reconcile. Instead, the engine
logs what it surfaced and reports "hit rate" (surfaced picks later rated 80+)
per mode, so you can see whether `hard` actually pays off.

**Resilience:** every lookup is cached on disk with TTLs
(`data/discovery_cache.json`, refreshed and committed weekly by CI); a circuit
breaker stops calling out after 3 consecutive failures so an offline machine
gets an instant empty result instead of a 30-second stall. Network failures
are never negative-cached.

**UI simplification done at the same time (keep the site compact):**
- The **Weekly** sidebar view was folded into Discover as a collapsed
  "This week's curated picks" panel — it was a reshuffle of the Recommender pool,
  not a separate source, so it didn't merit its own nav item.
- Removed the Evolution **Yearly Overview** table and the **Cumulative Songs**
  chart. Per-year average ratings mostly reflect *what you happened to review*
  that year, not a change in taste; the summary cards + trend line already
  carry the signal.
- Removed the dead **Spotify banner** on Recommender and the stale hidden
  `#view-outliers` section (it duplicated the dashboard panel's element IDs).
- `spotify_helper.get_audio_features` / `get_recommendations_from_seeds` are
  kept for backwards compatibility but documented as deprecated.

