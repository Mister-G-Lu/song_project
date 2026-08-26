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
