#!/usr/bin/env python3
"""
import_rym_export.py — Import songs you rated on RateYourMusic but not here.

Reads an external ratings export (RYM catalog export: CSV, TSV or a Markdown
table), maps its columns onto this project's schema, and merges it into
data/posts_tails.csv — carefully, never at the expense of data already here.

Hard rules (the "pre-existing wins" policy):
  * A row that duplicates an existing entry is never written and never
    overwrites anything. It is reported as `dup_skip` — with both ratings — so
    the difference stays visible even though nothing changes.
  * The only fields this script writes into an *existing* row are empty ones:
    a missing `rating`, a missing `artist`. Gaps, never conflicts.
  * Duplicate detection deliberately includes the exact signature the engine
    uses when it merges the base CSV with the additions overlay
    (``TasteEngine._normalize_sig(title)``), where *the higher rating wins*.
    Anything looser than that rule would let an imported row with a bigger
    number silently replace your original rating. It also goes stricter than
    the engine (artist+song combos, cross-script Latin forms, fuzzy tiers),
    because a near-duplicate row in the base CSV never gets merged away.

Duplicate tiers:
  hard  1 `merge_sig`   normalized full-title equality — the engine's own rule
        2 `combo`       normalized "artist + song" equality
        3 `latin`       ASCII-only normalization (CJK ↔ romanized twins)
  fuzzy 4 `containment` one song name contains the other, same artist
        5 `jaccard`     word-set Jaccard ≥ 0.95, same artist
        6 `typo`        SequenceMatcher ≥ 0.90 on the song name, same artist
  Fuzzy hits are skipped by default and listed under `needs_review`
  (use --fuzzy add to import them anyway; --fuzzy review-only is the default).

Ratings: 0–100 passes through as-is; 6–10 and 1–10 decimals are read as x/10;
0.5–5 is read as RYM stars (×20, i.e. 4★ → 80) unless --scale anchored, which
spreads 1★–5★ across 0–100 the way RYM's own histogram does. Also understands
"4.5/5", "★★★★½", "85/100", letter grades (the project's LETTER_GRADE_MAP) and
RYM's textual notes ("really good"). --scale auto (default) decides per column,
and a column whose values are all ≤ 5 is treated as stars.

Usage
-----
    # 1. Look, change nothing:
    python3 scripts/import_rym_export.py --input ~/Downloads/seldiora-music-export.csv

    # 2. Apply + keep a report of exactly which gaps got covered:
    python3 scripts/import_rym_export.py --input export.csv --apply \
        --report /tmp/rym_import_report.json

    # 3. Also seed release years for the new songs (feeds the year coverage %):
    python3 scripts/import_rym_export.py --input export.csv --apply --years

    # Other knobs: --target additions (write the overlay instead of the base
    # CSV), --scale anchored|linear|out_of_10|as_is, --fuzzy add, --years,
    # --include-unrated, --map rating=My Stars, --dry-run is the default.

Exit codes: 0 ok · 2 unreadable/empty input · 3 --apply refused.
"""

from __future__ import annotations

import argparse
import csv
import difflib
import io
import json
import os
import re
import shutil
import sys
import tempfile
from collections import defaultdict
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Set, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

BASE_CSV = os.path.join(REPO_ROOT, "data", "posts_tails.csv")
ADDITIONS_CSV = os.path.join(REPO_ROOT, "data", "posts_tails_additions.csv")
YEAR_CACHE = os.path.join(REPO_ROOT, "data", "release_year_cache.json")

FIELDS = ["date", "rating", "title", "tail", "artist", "song",
          "title_original", "title_english"]
HARD_TIERS = ("merge_sig", "combo", "combo_latin", "latin")

# ---------------------------------------------------------------------------
# Normalization — intentionally identical to TasteEngine's, so "duplicate"
# means the same thing here and at load time.
# ---------------------------------------------------------------------------


def normalize_sig(text: str) -> str:
    """Mirror of TasteEngine._normalize_sig (lowercase, strip year/feats/punct)."""
    t = (text or "").lower()
    t = re.sub(r'\(?\s*\d{4}\s*\)?', '', t)
    t = re.sub(r'\s+ft\.?\s*|\s+feat\.?\s*|\s+featuring\s*', ' ', t)
    t = re.sub(r'\s+by\s+|\s+and\s+|\s+&\s+|\s+vs\.?\s+', ' ', t)
    t = re.sub(r'[^\w\s-]', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def normalize_latin(text: str) -> str:
    """Mirror of TasteEngine._normalize_latin (ASCII-only, for cross-script)."""
    t = (text or "").lower()
    t = re.sub(r'\(?\s*\d{4}\s*\)?', '', t)
    t = re.sub(r'\s+ft\.?\s*|\s+feat\.?\s*|\s+featuring\s*', ' ', t)
    t = re.sub(r'[^a-z0-9\s]', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def similar_score(a: str, b: str) -> float:
    """Mirror of TasteEngine._similar_score (Jaccard over word sets)."""
    sa, sb = set((a or "").split()), set((b or "").split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


# ---------------------------------------------------------------------------
# Column mapping for arbitrary export layouts
# ---------------------------------------------------------------------------

ALIASES: Dict[str, Set[str]] = {
    "artist": {"artist", "artists", "artist_name", "primary_artist", "primary_artists",
               "performer", "performers", "by", "singer", "band", "interpret",
               "main_artist", "musicians", "credit", "credits", "artist_s"},
    "song": {"song", "songs", "song_title", "track", "tracks", "track_title", "title",
             "song_name", "work", "recording", "piece", "name", "track_name",
             "recording_title", "song_s"},
    "release": {"release", "release_title", "album", "album_title", "record",
                "catalog_name", "lp", "ep", "album_name", "release_name", "release_s"},
    "rating": {"rating", "my_rating", "score", "stars", "my_stars", "grade",
               "mark", "points", "rate", "num_rating", "rating_value", "song_rating"},
    "date": {"date", "date_rated", "rated_date", "rated_on", "date_added", "added",
             "created_at", "modified_at", "review_date", "timestamp", "when", "day",
             "last_rated"},
    "tail": {"review", "comment", "comment_text", "tail", "text", "description",
             "my_review", "note_text", "thoughts", "notes"},
    "genre": {"genre", "genres", "tag", "tags", "style", "styles", "subgenre"},
    "year": {"year", "release_year", "year_of_release", "released", "released_in",
             "orig_year", "original_release_year"},
    "title_original": {"title_original", "original_title", "native_title", "title_ja"},
    "title_english": {"title_english", "english_title", "romanized_title", "romaji",
                      "transliteration", "transliterated_title"},
}

_STAR_CHARS = re.compile(r'[★☆⯨⯩◎○◐½]')


def _canon_header(h: str) -> str:
    h = (h or "").strip().lower().replace('\ufeff', '')
    h = re.sub(r'\(s\)', 's', h)
    h = re.sub(r'[^a-z0-9]+', '_', h).strip('_')
    return h


def map_columns(fieldnames: Iterable[str]) -> Dict[str, str]:
    """Map export headers onto canonical keys → {canonical: original header}."""
    canon = {(_canon_header(f) or f): f for f in fieldnames if f and str(f).strip()}
    mapping: Dict[str, str] = {}
    for key, names in ALIASES.items():
        for cn, orig in canon.items():
            if cn in names and key not in mapping:
                mapping[key] = orig
    # Loose fallback for headers nobody claimed: "My Song Rating", "Date I Rated It".
    # Checked in this order so "rating" wins over "song" for a rating column.
    used = set(mapping.values())
    for key in ("rating", "artist", "song", "date", "year", "genre", "tail"):
        if key in mapping:
            continue
        for cn, orig in canon.items():
            if orig in used or not cn:
                continue
            toks = cn.split("_")
            if key in toks or (key in cn and len(toks) <= 5):
                mapping[key] = orig
                used.add(orig)
                break
    return mapping


# ---------------------------------------------------------------------------
# Rating parsing
# ---------------------------------------------------------------------------

try:  # reuse the project's own letter-grade table when present
    with open(os.path.join(REPO_ROOT, "data", "backfill_data.json"), encoding="utf-8") as _f:
        LETTER_GRADE_MAP: Dict[str, int] = (json.load(_f) or {}).get("letter_grade_map", {})
except Exception:  # pragma: no cover - the script stays usable standalone
    LETTER_GRADE_MAP = {"A+": 98, "A": 95, "A-": 92, "B+": 88, "B": 85, "B-": 82,
                        "C+": 78, "C": 75, "C-": 72, "D+": 68, "D": 65, "D-": 62, "F": 50}

# RYM's textual rating scale.
RYM_TEXT_RATINGS: Dict[str, int] = {
    "super classic": 100, "classic": 95, "modern classic": 95, "instant classic": 95,
    "timeless": 95, "really good": 85, "very good": 85, "pretty good": 78,
    "solid": 78, "good": 72, "liked": 68, "likable": 65, "average": 55,
    "middling": 50, "neutral": 50, "below average": 42, "not good": 35,
    "bad": 28, "horrible": 18, "awful": 15, "terrible": 12, "obscene": 5,
    "unlistenable": 5,
}

SCALES = ("auto", "linear", "anchored", "out_of_10", "as_is")


def _clamp(v: float) -> int:
    return int(max(0, min(100, round(v))))


def _stars_to_100(stars: float, mode: str) -> int:
    if mode == "anchored":   # 1★ → 0, 5★ → 100 (how RYM normalizes its histogram)
        return _clamp((stars - 1.0) / 4.0 * 100)
    return _clamp(stars / 5.0 * 100)   # "linear": 5★ → 100, 2.5★ → 50


def parse_rating(raw, mode: str = "auto") -> Tuple[Optional[int], Optional[str]]:
    """→ (rating on the 0–100 project scale, human note). (None, None) if absent."""
    if raw is None:
        return None, None
    s = str(raw).strip()
    if not s or s.lower() in {"n/a", "na", "-", "none", "null", "?"}:
        return None, None

    if _STAR_CHARS.search(s):
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*/\s*(\d+(?:[.,]\d+)?)", s)
        if m:
            v, den = float(m.group(1).replace(",", ".")), float(m.group(2).replace(",", "."))
            if den > 0:
                return _clamp(v / den * 100), f"stars {v}/{den}"
        stars = s.count("★") + 0.5 * (s.count("½") + s.count("⯨"))
        if stars:
            return _stars_to_100(stars, "anchored" if mode == "anchored" else "linear"), \
                f"glyph stars {stars}"

    m = re.fullmatch(r"\s*([A-Fa-f][+-]?)\s*", s)
    if m and LETTER_GRADE_MAP and m.group(1).upper() in LETTER_GRADE_MAP:
        g = m.group(1).upper()
        return LETTER_GRADE_MAP[g], f"letter grade {g}"

    low = s.lower().strip(" .!")
    if low in RYM_TEXT_RATINGS:
        return RYM_TEXT_RATINGS[low], f'rym note "{low}"'

    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:/|out of|\bof\b)\s*(\d+(?:[.,]\d+)?)", s)
    if m:
        v, den = float(m.group(1).replace(",", ".")), float(m.group(2).replace(",", "."))
        if den <= 0:
            return None, None
        return _clamp(v / den * 100), f"{v:g}/{den:g} scaled"

    m = re.fullmatch(r"\s*(?:[a-z#]{0,8}\s*)?(-?\d+(?:[.,]\d+)?)\s*", s, re.I)
    if not m:
        return None, None
    v = float(m.group(1).replace(",", "."))
    if mode == "as_is":
        return _clamp(v), f"{v:g} as-is"
    if mode == "out_of_10":
        return _clamp(v * 10), f"{v:g}/10"
    if mode in ("linear", "anchored"):
        return _stars_to_100(v, mode), f"RYM stars {v:g} ({mode})"
    # auto: the value's range tells us the scale
    if v > 10:
        return _clamp(v), f"{v:g}/100"
    if v > 5:
        return _clamp(v * 10), f"{v:g}/10"
    if v >= 0.5:
        return _stars_to_100(v, "linear"), f"RYM stars {v:g} (auto)"
    return _clamp(v), f"{v:g}/100"


def detect_scale(values: List[str]) -> Optional[str]:
    """'linear' when the column can only be RYM stars, else None (→ auto)."""
    nums: List[float] = []
    for v in values:
        s = str(v or "").strip()
        if not s:
            continue
        if _STAR_CHARS.search(s) or "/" in s or not re.fullmatch(r"\d+(?:[.,]\d+)?", s):
            return None
        nums.append(float(s.replace(",", ".")))
    if len(nums) >= 3 and max(nums) <= 5.0:
        return "linear"
    return None


# ---------------------------------------------------------------------------
# Export rows
# ---------------------------------------------------------------------------


def split_artists(raw: str) -> List[str]:
    if not raw:
        return []
    parts = re.split(r"\s*(?:,|;|&|/|\bft\.?\b|\bfeat\.?\b|\bwith\b|\bvs\.?\b)\s*",
                     raw, flags=re.I)
    return [p.strip(" -–—,.") for p in parts if p and p.strip(" -–—,.")]


DATE_FORMATS = ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y",
                "%m/%d/%Y", "%d.%m.%Y", "%b %d, %Y", "%d %b %Y", "%Y/%m/%d", "%Y-%m")


def parse_date(raw: str) -> str:
    """Best-effort → YYYY-MM-DD (falls back to today so Evolution stays usable)."""
    s = (raw or "").strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s[:len(fmt) + 6].strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    m = re.search(r"(1[5-9]\d{2}|20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})", s)
    if m:
        y, mo, d = (int(g) for g in m.groups())
        try:
            return datetime(y, mo, d).strftime("%Y-%m-%d")
        except ValueError:
            return f"{y}-{mo:02d}-01"
    m = re.search(r"(1[5-9]\d{2}|20\d{2})-(\d{2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-01"
    return datetime.now().strftime("%Y-%m-%d")


class ImportRow:
    """One candidate row from the external export, in project shape."""

    def __init__(self, mapping: Dict[str, str], record: Dict[str, str], lineno: int = 0):
        get = lambda k: (record.get(mapping.get(k, ""), "") or "").strip() if mapping.get(k) else ""
        self.lineno = lineno
        self.raw = record
        self.artist_raw = get("artist")
        self.artists = split_artists(self.artist_raw)
        self.artist = self.artists[0] if self.artists else ""
        self.song = get("song")
        self.release = get("release")
        self.original = get("title_original")
        self.english = get("title_english")
        self.genre = get("genre")
        self.tail = get("tail")
        raw_date = get("date")
        self.date = parse_date(raw_date)
        self.year = self._parse_year(get("year"))
        self.rating_raw = get("rating")
        self.rating: Optional[int] = None
        self.rating_note: Optional[str] = None

        song_part = self.song or self.original or self.english or self.release or ""
        if not song_part:
            title = self.artist
        elif self.artist and self.artist.lower() in song_part.lower():
            title = song_part
        elif self.artist:
            title = f"{song_part} ({self.artist}{', ' + str(self.year) if self.year else ''})"
        else:
            title = song_part
        self.title = (title or "").strip()
        self.song_clean = re.split(r"\s*[\(–\-]", song_part, maxsplit=1)[0].strip() or song_part
        self.merge_sig = normalize_sig(self.title)
        self.latin_sig = normalize_latin(self.title)
        self.song_sig = normalize_sig(song_part) or self.merge_sig
        self.song_latin = normalize_latin(song_part) or self.latin_sig

    def _parse_year(self, raw: str) -> Optional[int]:
        m = re.search(r"\b(1[5-9]\d{2}|20\d{2})\b", raw or "")
        if m:
            return int(m.group(1))
        m = re.search(r"\(\s*(1[5-9]\d{2}|20\d{2})\s*\)", self.song or "")
        return int(m.group(1)) if m else None

    def artist_tokens(self) -> Set[str]:
        out: Set[str] = set()
        for a in (self.artists or [self.artist]):
            out |= {w for w in normalize_latin(a).split() if len(w) >= 3}
        return out


# ---------------------------------------------------------------------------
# Index over what the project already has
# ---------------------------------------------------------------------------


class ExistingIndex:
    """data/posts_tails.csv (+ overlay), indexed for duplicate lookups."""

    def __init__(self, rows: List[Dict[str, str]]):
        self.rows = rows
        self.by_sig: Dict[str, List[int]] = defaultdict(list)
        self.by_combo: Dict[str, List[int]] = defaultdict(list)
        self.by_latin: Dict[str, List[int]] = defaultdict(list)
        self.song_word: Dict[str, Set[int]] = defaultdict(set)
        self.titles: List[str] = []
        self.song_sigs: List[str] = []
        self.song_latins: List[str] = []
        self.artist_tok: List[Set[str]] = []
        for i, r in enumerate(rows):
            title = (r.get("title") or "").strip()
            self.titles.append(title)
            artist = (r.get("artist") or "").strip()
            song = (r.get("song") or "").strip()
            tok: Set[str] = set()
            for a in split_artists(artist):
                tok |= {w for w in normalize_latin(a).split() if len(w) >= 3}
            self.artist_tok.append(tok)
            if not title or title == "Announcement":
                self.song_sigs.append("")
                self.song_latins.append("")
                continue
            sig = normalize_sig(title)
            self.by_sig[sig].append(i)
            latin = normalize_latin(title)
            self.by_latin[latin].append(i)
            song_part = re.split(r"\s*[\(–\-]", song or title, maxsplit=1)[0].strip() or title
            s_sig = normalize_sig(song_part)
            s_latin = normalize_latin(song_part)
            self.song_sigs.append(s_sig)
            self.song_latins.append(s_latin)
            if artist:
                self.by_combo[normalize_sig(f"{artist} {song_part}")].append(i)
                self.by_combo[normalize_sig(f"{song_part} ({artist})")].append(i)
            for w in {x for x in s_latin.split() if len(x) >= 2}:
                self.song_word[w].add(i)

    # -- duplicate lookups -------------------------------------------------

    def _compat(self, idx: int, cand: ImportRow) -> bool:
        """Same artist (or the project row never recorded one) → comparable."""
        ex = self.artist_tok[idx]
        return not ex or not cand.artist_tokens() or bool(ex & cand.artist_tokens())

    def candidates_for(self, cand: ImportRow) -> Set[int]:
        out: Set[int] = set()
        for w in {x for x in cand.song_latin.split() if len(x) >= 2}:
            out |= self.song_word.get(w, set())
        return out

    def find(self, cand: ImportRow) -> Tuple[Optional[int], Optional[str]]:
        """First matching tier. Hard tiers → skip for good; fuzzy tiers → review."""
        # 1. exactly what TasteEngine._merge_rows / deduplicate() compares
        hits = self.by_sig.get(cand.merge_sig)
        if hits:
            return hits[0], "merge_sig"
        # 2. artist + song combo (both house styles: "Song (Artist)" / "Artist – Song")
        for a in (cand.artists or [cand.artist]):
            if not a:
                continue
            for key in (normalize_sig(f"{a} {cand.song_clean}"),
                        normalize_sig(f"{cand.song_clean} ({a})")):
                hits = self.by_combo.get(key) or self.by_sig.get(key)
                if hits:
                    return hits[0], "combo"
        # 3. Latin-only form of the whole title (CJK ↔ romanized)
        if cand.latin_sig:
            hits = self.by_latin.get(cand.latin_sig)
            if hits:
                return hits[0], "latin"
            for a in (cand.artists or [cand.artist]):
                if a:
                    lc = normalize_latin(f"{a} {cand.song_latin}")
                    if lc and len(lc) >= 5:
                        for idx in self.candidates_for(cand):
                            if self.song_latins[idx] and lc in normalize_latin(self.titles[idx]):
                                return idx, "combo_latin"
        # fuzzy tiers, restricted to rows sharing a word (keeps it O(k))
        for idx in sorted(self.candidates_for(cand)):
            if not self._compat(idx, cand):
                continue
            ex_sig, ex_latin = self.song_sigs[idx], self.song_latins[idx]
            if not ex_sig:
                continue
            if (len(cand.song_sig) >= 4 and len(ex_sig) >= 4
                    and (cand.song_sig in ex_sig or ex_sig in cand.song_sig)):
                return idx, "containment"
            if cand.song_latin and ex_latin and similar_score(cand.song_latin, ex_latin) >= 0.95:
                return idx, "jaccard"
            if cand.song_latin and ex_latin and len(cand.song_latin) >= 4:
                if difflib.SequenceMatcher(None, cand.song_latin, ex_latin).ratio() >= 0.90:
                    return idx, "typo"
        return None, None


# ---------------------------------------------------------------------------
# Reading the export
# ---------------------------------------------------------------------------


def read_table(path: str) -> Tuple[List[str], List[Dict[str, str]]]:
    """Read a CSV / TSV / semicolon / pipe (Markdown) table."""
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        text = f.read()
    if not text.strip():
        return [], []
    sample = "\n".join(text.splitlines()[:20])
    delim = ","
    try:
        delim = csv.Sniffer().sniff(sample, delimiters=",\t;|").delimiter
    except csv.Error:
        counts = {d: sample.count(d) for d in ",\t;|"}
        delim = max(counts, key=counts.get)
    grid = [r for r in csv.reader(io.StringIO(text), delimiter=delim)
            if any((c or "").strip() for c in r)]
    if not grid:
        return [], []
    header_i = 0
    for i, r in enumerate(grid[:5]):
        joined = " ".join((c or "").lower() for c in r)
        if any(k in joined for k in ("artist", "song", "title", "track", "rating")):
            header_i = i
            break
    header = [(h or "").strip() for h in grid[header_i]]
    records: List[Dict[str, str]] = []
    for r in grid[header_i + 1:]:
        if not any((c or "").strip() for c in r):
            continue
        if all(re.fullmatch(r"[-: ]*", (c or "").strip()) for c in r):   # markdown rule row
            continue
        rec = {header[j]: (r[j] or "").strip() for j in range(min(len(header), len(r)))
               if header[j]}
        if not any(rec.values()):
            continue
        records.append(rec)
    return [h for h in header if h], records


# ---------------------------------------------------------------------------
# The import itself (pure: classifies rows, writes nothing)
# ---------------------------------------------------------------------------


def run_import(input_path: str, *, base_rows: List[Dict[str, str]],
               add_rows: Optional[List[Dict[str, str]]] = None, scale: str = "auto",
               fuzzy: str = "skip", include_unrated: bool = False,
               fill_unrated: bool = True, fill_artists: bool = True,
               overrides: Optional[Dict[str, str]] = None) -> Dict:
    header, records = read_table(input_path)
    if not records:
        raise SystemExit(f"error: no usable data rows in {input_path}")
    mapping = map_columns(header)
    for key, col in (overrides or {}).items():
        if col in header:
            mapping[key] = col
        else:
            raise SystemExit(f"error: --map {key}={col}: no such column. Headers: {header}")
    if "song" not in mapping and "artist" not in mapping:
        raise SystemExit(
            "error: could not find a song/title or artist column.\n"
            f"  headers seen: {header}\n"
            "  fix with:  --map song=... --map artist=... --map rating=..."
        )

    index = ExistingIndex(list(base_rows) + list(add_rows or []))
    detected = None if scale != "auto" else detect_scale(
        [r.get(mapping.get("rating", ""), "") for r in records])
    eff_scale = scale if scale != "auto" else (detected or "auto")

    report: Dict = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "input": os.path.abspath(input_path),
        "headers": header,
        "column_map": mapping,
        "scale_mode": eff_scale,
        "star_column_detected": detected == "linear",
        "fuzzy_mode": fuzzy,
        "rows_in_export": len(records),
        "new_rows": [],
        "dup_skip": [],
        "conflicts": [],
        "fills": [],
        "artist_fills": [],
        "needs_review": [],
        "self_dupes": [],
        "no_rating": [],
        "skipped_no_title": 0,
    }

    seen_sigs: Set[str] = set()
    filled: Set[int] = set()          # existing rows already claimed by a fill
    for n, rec in enumerate(records, start=1):
        cand = ImportRow(mapping, rec, n)
        if not cand.merge_sig:
            report["skipped_no_title"] += 1
            continue
        rating, note = parse_rating(cand.rating_raw, eff_scale)
        cand.rating, cand.rating_note = rating, note

        idx, tier = index.find(cand)
        force = idx is not None and tier not in HARD_TIERS and fuzzy == "add"
        if idx is not None and not force:
            existing = index.rows[idx]
            ex_rating = (existing.get("rating") or "").strip()
            if tier in HARD_TIERS:
                if (fill_unrated and not ex_rating and rating is not None
                        and idx not in filled):
                    filled.add(idx)
                    report["fills"].append({
                        "title": index.titles[idx], "rating": rating,
                        "why": "unrated in project, rated on RYM",
                        "raw_rym": cand.rating_raw, "export_line": n,
                        "matched_by": tier,
                    })
                if (fill_artists and not (existing.get("artist") or "").strip()
                        and cand.artist):
                    report["artist_fills"].append({
                        "title": index.titles[idx], "artist": cand.artist,
                        "export_line": n, "matched_by": tier,
                    })
                if rating is not None and ex_rating and str(rating) != ex_rating:
                    report["conflicts"].append({
                        "title": index.titles[idx], "existing_rating": int(ex_rating),
                        "rym_rating": rating, "kept": "existing", "tier": tier,
                        "raw_rym": cand.rating_raw, "export_line": n,
                    })
                report["dup_skip"].append({
                    "title": cand.title, "matched": index.titles[idx], "tier": tier,
                    "rym_rating": rating,
                    "existing_rating": int(ex_rating) if ex_rating else None,
                    "export_line": n,
                })
                continue
            report["needs_review"].append({
                "title": cand.title, "near": index.titles[idx], "tier": tier,
                "rym_rating": rating, "export_line": n,
            })
            continue

        if rating is None and not include_unrated:
            report["no_rating"].append({"title": cand.title, "raw": cand.rating_raw,
                                        "export_line": n})
            continue
        if cand.merge_sig in seen_sigs:
            report["self_dupes"].append({"title": cand.title, "export_line": n})
            continue
        seen_sigs.add(cand.merge_sig)

        report["new_rows"].append({
            "date": cand.date,
            "rating": str(rating) if rating is not None else "",
            "title": cand.title, "tail": cand.tail, "artist": cand.artist,
            "song": cand.song or cand.title, "title_original": cand.original,
            "title_english": cand.english,
            "_year": cand.year, "_note": note, "_line": n, "_genre": cand.genre,
            "_release": cand.release,
        })
    return report


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


def _read_rows(path: str) -> List[Dict[str, str]]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def apply_import(report: Dict, *, target: str = "base", write_years: bool = False,
                 backup: bool = True) -> Dict:
    stats = {"new_songs": 0, "ratings_filled": 0, "artists_filled": 0, "years_cached": 0}
    rows = _read_rows(BASE_CSV)
    fieldnames = [k for k in (FIELDS if not rows else list(rows[0].keys())) if k]

    by_title = defaultdict(list)
    for i, r in enumerate(rows):
        by_title[normalize_sig(r.get("title") or "")].append(i)

    for fill in report.get("fills", []):
        for i in by_title.get(normalize_sig(fill.get("title") or ""), ()):
            r = rows[i]
            if not (r.get("rating") or "").strip():
                r["rating"] = str(fill["rating"])
                r["date"] = r.get("date") or fill.get("date") or \
                    datetime.now().strftime("%Y-%m-%d")
                stats["ratings_filled"] += 1
            break

    for fill in report.get("artist_fills", []):
        for i in by_title.get(normalize_sig(fill.get("title") or ""), ()):
            if not (rows[i].get("artist") or "").strip():
                rows[i]["artist"] = fill["artist"]
                if not (rows[i].get("song") or "").strip():
                    rows[i]["song"] = fill.get("song") or rows[i].get("title") or ""
                stats["artists_filled"] += 1
            break

    new_rows = []
    for nr in report.get("new_rows", []):
        if target == "additions":
            new_rows.append({k: nr.get(k, "") for k in
                             ("date", "rating", "title", "tail")})
        else:
            new_rows.append({k: nr.get(k, "") or "" for k in fieldnames})

    if target == "additions" and new_rows:
        needs_header = not os.path.exists(ADDITIONS_CSV) or os.path.getsize(ADDITIONS_CSV) == 0
        if backup and not needs_header:
            shutil.copy2(ADDITIONS_CSV, ADDITIONS_CSV + ".bak")
        with open(ADDITIONS_CSV, "a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["date", "rating", "title", "tail"],
                               extrasaction="ignore")
            if needs_header:
                w.writeheader()
            w.writerows(new_rows)
        stats["new_songs"] = len(new_rows)
    elif new_rows:
        if backup:
            shutil.copy2(BASE_CSV, BASE_CSV + ".bak")
        out = rows + new_rows
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(BASE_CSV) or ".", suffix=".csv")
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            w.writeheader()
            for r in out:
                w.writerow({k: (r.get(k) or "") for k in fieldnames})
        os.replace(tmp, BASE_CSV)
        stats["new_songs"] = len(new_rows)

    if write_years and report.get("new_rows"):
        cache: Dict[str, int] = {}
        if os.path.exists(YEAR_CACHE):
            try:
                with open(YEAR_CACHE, encoding="utf-8") as f:
                    cache = json.load(f)
            except Exception:
                cache = {}
        added = 0
        for nr in report["new_rows"]:
            year, artist, song = nr.get("_year"), nr.get("artist"), nr.get("song")
            if not (year and artist and song):
                continue
            key = (f"{re.sub(r'[^a-z0-9]', '', artist.lower())}|"
                   f"{re.sub(r'[^a-z0-9]', '', str(song).lower())}")
            if cache.get(key) in (None, "", 0):
                cache[key] = int(year)
                added += 1
        if added:
            if backup:
                shutil.copy2(YEAR_CACHE, YEAR_CACHE + ".bak")
            fd, tmp = tempfile.mkstemp(dir=os.path.dirname(YEAR_CACHE) or ".", suffix=".json")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(cache, f, indent=2, ensure_ascii=True, sort_keys=True)
                f.write("\n")
            os.replace(tmp, YEAR_CACHE)
            stats["years_cached"] = added
    return stats


# ---------------------------------------------------------------------------
# Data-gap accounting
# ---------------------------------------------------------------------------


def gap_metrics(base_rows: List[Dict[str, str]],
                add_rows: Optional[List[Dict[str, str]]] = None) -> Dict:
    """Coverage of the four fields the views actually depend on."""
    rows = list(base_rows) + list(add_rows or [])
    rated = [r for r in rows if (r.get("rating") or "").strip()]
    cache: Dict[str, int] = {}
    if os.path.exists(YEAR_CACHE):
        try:
            with open(YEAR_CACHE, encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            cache = {}
    with_year = with_tail = with_artist = 0
    artists: Set[str] = set()
    for r in rows:
        artist = (r.get("artist") or "").strip()
        if artist:
            with_artist += 1
            artists.add(normalize_sig(artist))
        if r not in rated:
            continue
        title = r.get("title") or ""
        song = (r.get("song") or "").strip()
        if re.search(r"\b(1[5-9]\d{2}|20\d{2})\b", title):
            with_year += 1
        elif artist and song:
            key = (f"{re.sub(r'[^a-z0-9]', '', artist.lower())}|"
                   f"{re.sub(r'[^a-z0-9]', '', song.lower())}")
            if cache.get(key):
                with_year += 1
        if (r.get("tail") or "").strip():
            with_tail += 1
    pct = lambda n, d: round(100 * n / d, 1) if d else 0.0
    return {
        "rows": len(rows),
        "rated": len(rated),
        "unrated": len(rows) - len(rated),
        "rated_pct": pct(len(rated), len(rows)),
        "unique_artists": len(artists),
        "rows_with_artist": with_artist,
        "artist_pct": pct(with_artist, len(rows)),
        "rated_with_year": with_year,
        "year_pct": pct(with_year, len(rated)),
        "rated_with_review_text": with_tail,
        "review_text_pct": pct(with_tail, len(rated)),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Import a RateYourMusic ratings export into data/posts_tails.csv "
                    "without overwriting anything already rated here.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True,
                    help="path to the RYM export (csv/tsv/md), or '-' to read stdin")
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    ap.add_argument("--target", choices=("base", "additions"), default="base",
                    help="where new rows go: base CSV (default) or the additions overlay")
    ap.add_argument("--scale", choices=SCALES, default="auto",
                    help="how to read the rating column (default auto)")
    ap.add_argument("--fuzzy", choices=("skip", "add"), default="skip",
                    help="fuzzy/typo matches: skip and report (default) or import anyway")
    ap.add_argument("--years", action="store_true",
                    help="also seed data/release_year_cache.json from the export's year column")
    ap.add_argument("--include-unrated", action="store_true",
                    help="import export rows that carry no rating")
    ap.add_argument("--no-fill", action="store_true",
                    help="never write into existing rows (skip gap fills)")
    ap.add_argument("--map", action="append", default=[], metavar="KEY=COLUMN",
                    help="override column mapping, e.g. --map rating='My Stars'")
    ap.add_argument("--report", metavar="PATH", help="write the full report as JSON")
    ap.add_argument("--preview", type=int, default=12, help="rows to list per bucket (0 = none)")
    ap.add_argument("--no-backup", action="store_true", help="skip .bak copies")
    args = ap.parse_args(argv)

    if args.input == "-":                      # `pbpaste | … --input -`
        tmp = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8")
        tmp.write(sys.stdin.read())
        tmp.close()
        args.input = tmp.name
    if not os.path.exists(args.input):
        print(f"error: no such file: {args.input}", file=sys.stderr)
        return 2

    overrides = {}
    for spec in args.map:
        if "=" not in spec:
            print(f"error: --map expects key=column, got {spec!r}", file=sys.stderr)
            return 2
        k, v = spec.split("=", 1)
        overrides[k.strip()] = v.strip()

    base_rows, add_rows = _read_rows(BASE_CSV), _read_rows(ADDITIONS_CSV)
    before = gap_metrics(base_rows, add_rows)
    try:
        report = run_import(args.input, base_rows=base_rows, add_rows=add_rows,
                            scale=args.scale, fuzzy=args.fuzzy,
                            include_unrated=args.include_unrated,
                            fill_unrated=not args.no_fill,
                            fill_artists=not args.no_fill, overrides=overrides)
    except SystemExit as e:
        print(e, file=sys.stderr)
        return 2

    n_new = len(report["new_rows"])
    n_fill = len(report["fills"])
    n_artist = len(report["artist_fills"])
    n_conf = len(report["conflicts"])

    print(f"columns seen       : {report['headers']}")
    print(f"columns used       : { {k: v for k, v in report['column_map'].items()} }")
    print(f"rating scale used  : {report['scale_mode']}"
          + ("  (column looked like RYM 0.5–5 stars → ×20)"
             if report["star_column_detected"] else ""))
    print(f"export rows        : {report['rows_in_export']}")
    print(f"new songs          : {n_new}")
    print(f"duplicates skipped : {len(report['dup_skip'])}"
          f"  ({n_conf} rating conflict{'s' if n_conf != 1 else ''} → existing kept)")
    print(f"gap fills          : {n_fill} unrated song{'s' if n_fill != 1 else ''} get a rating,"
          f" {n_artist} get an artist")
    if report["needs_review"]:
        print(f"near matches         : {len(report['needs_review'])}"
              + ("" if args.fuzzy == "add" else "  (skipped; --fuzzy add to import)"))
    if report["no_rating"]:
        print(f"no rating in export  : {len(report['no_rating'])}  (--include-unrated to add anyway)")
    if report["self_dupes"]:
        print(f"export self-dupes    : {len(report['self_dupes'])}")

    if not any((n_new, n_fill, n_artist)):
        print("\nnothing to do — everything in the export is already here and nothing was missing.")
        if args.report:
            _dump(report, args.report)
        return 0

    stats: Dict = {}
    if args.apply:
        stats = apply_import(report, target=args.target, write_years=args.years,
                            backup=not args.no_backup)
        after = gap_metrics(_read_rows(BASE_CSV), _read_rows(ADDITIONS_CSV))
        print("\nAPPLIED")
        for k, v in stats.items():
            print(f"  {k:>18}: {v}")
        print("\nDATA GAPS   before → after")
        for key in ("rows", "rated", "unrated", "rated_pct", "unique_artists",
                    "rows_with_artist", "artist_pct", "rated_with_year", "year_pct",
                    "rated_with_review_text", "review_text_pct"):
            b, a = before.get(key), after.get(key)
            delta = "" if b == a else f"   ({'+' if (a or 0) >= (b or 0) else ''}{round((a or 0) - (b or 0), 1)})"
            print(f"  {key:>21}: {b} → {a}{delta}")
        report["gaps_after"] = after
        report["apply_stats"] = stats
    else:
        print("\ndry run — nothing written. Re-run with --apply to import.")
        if args.preview:
            _preview(report, args.preview)
        print("\nIf this looks right:")
        print(f"  python3 scripts/import_rym_export.py --input {args.input} --apply"
              + (" --years" if args.years else "") + " --report /tmp/rym_import_report.json")

    report["gaps_before"] = before
    if args.report:
        _dump(report, args.report)
    return 0


def _dump(report: Dict, path: str) -> None:
    d = {k: v for k, v in report.items()}
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)
    print(f"\nreport → {path}")


def _preview(report: Dict, limit: int) -> None:
    buckets = (("would ADD", "new_rows"), ("gap FILL", "fills"), ("artist FILL", "artist_fills"),
               ("conflict (existing wins)", "conflicts"), ("duplicate (skipped)", "dup_skip"),
               ("near match (review)", "needs_review"), ("no rating", "no_rating"),
               ("export self-dupe", "self_dupes"))
    for label, key in buckets:
        items = report.get(key) or []
        if not items:
            continue
        print(f"\n{label} — {len(items)}")
        for it in items[:limit]:
            if key == "new_rows":
                print(f"  + {it['rating'] or '?':>3} · {it['title']}  [{it['date']}]"
                      + (f"  ({it['_note']})" if it.get("_note") else ""))
            elif key == "conflicts":
                print(f"  · keep {it['existing_rating']}, ignore RYM {it['rym_rating']}"
                      f" — {it['title']}")
            elif key == "dup_skip":
                print(f"  = {it['title']} ≈ {it['matched']}  [{it['tier']}]")
            elif key == "fills":
                print(f"  ~ {it['title']} → {it['rating']}  ({it['why']})")
            elif key == "artist_fills":
                print(f"  ~ {it['title']} → artist {it['artist']}")
            elif key == "needs_review":
                print(f"  ? {it['title']} ≈ {it['near']}  [{it['tier']}]")
            else:
                print(f"  - {it.get('title')}{'' if it.get('raw') is None else '  (raw: ' + str(it['raw']) + ')'}")
        if len(items) > limit:
            print(f"  … and {len(items) - limit} more")


if __name__ == "__main__":
    raise SystemExit(main())
