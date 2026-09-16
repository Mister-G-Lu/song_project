"""
extract_special_posts.py — Move non-song posts out of the song dataset.

Why this exists
---------------
posts_tails.csv is mostly rated songs, but it also contains two kinds of
"posts" that are not really songs and should not count toward song stats
(Song vs Year, genre breakdowns, blind spots, ...):

  * VS-battle / matchup posts: "Battle of the 96's", "Special Match: X VS Y",
    "Rematch: ..." — head-to-head rating games, not songs.
  * Meta posts about the rating system itself: "Rating System Update",
    "Ratings without a song assigned", "The \"My five rap songs\" argument".

The 2017-2020 posts carry no rating column values (the rating lived in the
post body), so they silently skew averages too.

How it works
------------
This script MOVES matching rows from data/posts_tails.csv into
data/special_posts.csv (same columns + ``special_type`` and ``special_note``
columns) so the data is preserved, not deleted. A leading comment row in
special_posts.csv explains the convention.

Extraction is by an explicit curated title list (exact normalized match),
NOT a regex, so real songs that merely contain "vs" or "battle" stay put:
Kungs vs Cookin' on 3 Burners "This Girl", F-777 "Space Battle",
Jenny's Undertale cover "Battle Against A True Hero", Kokia
"Battle of Destiny", The Pogues "Fairytale of New York / The Battle March
Medley", The Script "Hall of Fame", ...

Idempotent: re-running finds nothing left to move. --dry-run previews.
"""
import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

BASE = ROOT / "data" / "posts_tails.csv"
SPECIAL = ROOT / "data" / "posts_tails_special.csv"

# Columns added to special_posts.csv
EXTRA_COLS = ["special_type", "special_note"]

HEADER_NOTE = (
    "NOTE: Rows in this file are VS-battle/matchup posts and rating-system "
    "meta posts, NOT songs. They were moved here from posts_tails.csv so "
    "they are excluded from song-level statistics (Song vs Year, genre "
    "breakdowns, blind spots). Do not rate-analyze these rows; keep them "
    "for the historical record only. special_type is 'battle' or 'meta'; "
    "special_note is the original title (needed because some battles are "
    "identified by their numbered title)."
)

# VS-battle / matchup posts (exact title match after whitespace strip).
BATTLE_TITLES = [
    "Battle of the 100's",
    "Battle of the 98's",
    "Battle of the 97's",
    "Battle of the 96's",
    "Battle of the 95's",
    "Battle of the 94's",
    "2021: Battle of the 94's",
    "Battle of 92's",
    "Battle of the 91's",
    "Battle of the 90's",
    "Battle of the 89's",
    "Battle of the 88's",
    "Battle of the 87's",
    "Battle of the 86's",
    "Battle of the 85's",
    "Battle of the 84's",
    "Battle of the 83's",
    "Battle of the 82's",
    "Battle of the 81's",
    "Battle of the 80's",
    "Battle of the 72's",
    "My own composition: A Piano Battle of Fire and Ice",
    "Rematch: Hot Air Balloon VS Bottom of the Deep Blue Sea",
    "Special Match/Battle: Refrain (Ian) VS Love (A-Lin)",
    "Rematch: Earth Song (Amadeus String Quartet) VS Fix (Chris Lane)",
    "Special Match: No Time to Die (Billie Eilish) VS Night Vision (Lindsey Stirling)",
    "Special Match: Lapis Lazuli (Eir Aoi) Vs Wish You Were Here (Avril Lavigne)",
    "Special Battle: FLYERS by BRADIO vs Go the Distance (Michael Bolton)",
    "Random matchup: Ulaanbaatar at Night (Tan Wei Wei) vs drivers license (Olivia)",
    "Absurd Matchups: Still Waiting (Jazz Emu) VS Floating Life (Yu Peng Chen)",
    "Special Matchup: Tired of California (Nessa Barrett) VS West Coast (One Republic)",
    "First added songs vs Newest added songs",
    "Ancora's Three Way Battle",
    "Papermoon VS Selfie Face",
    "Walking on Sunshine by Katrina vs Night Moves by Bob Seger",
    "Flower of Hell VS Hana Ni Natte",
]

# Meta posts about the rating system / channel, not songs.
META_TITLES = [
    "Youtube top 10 most viewed review",
    "Each Rating and a Sample song",
    "The \u201cMy five rap songs\u201d argument",
    "The \"My five rap songs\" argument",
    "\u201cContrast\u201d pairs",
    '"Contrast" pairs',
    "Rating System Update",
    "Ratings without a song assigned",
    "My \u201cWinners + Loser's Collection\u201d",
    'My "Winners + Loser\'s Collection"',
    "A song made entirely from videos that people sent via Twitter — Brett Domino + various artists",
]

# Curly vs straight apostrophes both appear in the CSV; match either.
def _variant_titles(t: str):
    yield t
    yield t.replace("'", "\u2019")
    yield t.replace("\u2019", "'")


def _match_key(t: str) -> str:
    return " ".join(t.split()).casefold()


def build_match_keys() -> dict:
    keys = {}
    for t in BATTLE_TITLES:
        for v in _variant_titles(t):
            keys[_match_key(v)] = "battle"
    for t in META_TITLES:
        for v in _variant_titles(t):
            keys[_match_key(v)] = "meta"
    return keys


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true",
                    help="Preview what would move without writing files.")
    args = ap.parse_args()

    with open(BASE, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    keys = build_match_keys()

    keep, move = [], []
    for r in rows:
        t = (r.get("title") or "").strip()
        kind = keys.get(_match_key(t))
        if kind:
            move.append((r, kind))
        else:
            keep.append(r)

    print(f"base rows: {len(rows)}")
    print(f"to move  : {len(move)}  (battle={sum(1 for _, k in move if k == 'battle')}, "
          f"meta={sum(1 for _, k in move if k == 'meta')})")
    for r, kind in move:
        print(f"  [{kind:<6}] {r.get('date', ''):10} [{r.get('rating') or '–':>3}] "
              f"{(r.get('title') or '')[:80]}")

    if args.dry_run or not move:
        if not move:
            print("Nothing to move — already extracted.")
        return

    # Append to special_posts.csv (create with note row + extra columns).
    special_fieldnames = fieldnames + EXTRA_COLS
    existing = 0
    if SPECIAL.exists():
        with open(SPECIAL, encoding="utf-8-sig", newline="") as f:
            existing = sum(1 for _ in csv.reader(f)) - 1  # header + note rows
        with open(SPECIAL, encoding="utf-8-sig", newline="") as f:
            special_fieldnames = next(csv.reader(f))  # preserve existing header
    with open(SPECIAL, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=special_fieldnames)
        if existing == 0 and f.tell() == 0:
            f.write("# " + HEADER_NOTE + "\n")
            w.writeheader()
        for r, kind in move:
            row = {c: r.get(c, "") for c in special_fieldnames}
            row["special_type"] = kind
            row["special_note"] = "auto-extracted; see file header note"
            w.writerow(row)

    # Rewrite the base CSV without the moved rows.
    with open(BASE, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(keep)

    print(f"\nMoved {len(move)} rows -> {SPECIAL.name}")
    print(f"Base CSV now has {len(keep)} rows.")


if __name__ == "__main__":
    main()
