"""
Tests for the special-posts archive (data/posts_tails_special.csv).

VS-battle / matchup posts and rating-system meta posts are posts, not
songs. They are moved out of posts_tails.csv (by
scripts/extract_special_posts.py) and excluded at engine load time so
they never count toward song-level statistics.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.taste_engine import TasteEngine


_normalize_sig = TasteEngine._normalize_sig


def _special_titles() -> list:
    """Parse posts_tails_special.csv the same way the engine does."""
    import csv
    path = Path(__file__).resolve().parent.parent / "data" / "posts_tails_special.csv"
    titles = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = None
        title_idx = 0
        for row in reader:
            if not row or row[0].lstrip().startswith("#"):
                continue
            if header is None:
                header = row
                title_idx = header.index("title") if "title" in header else 0
                continue
            if len(row) > title_idx and (row[title_idx] or "").strip():
                titles.append(row[title_idx].strip())
    return titles


def test_special_posts_file_exists_with_rows():
    titles = _special_titles()
    assert len(titles) >= 40, "archive should hold the ~43 battle/meta posts"


def test_no_battle_or_meta_posts_in_base_csv():
    base = (Path(__file__).resolve().parent.parent / "data" / "posts_tails.csv") \
        .read_text(encoding="utf-8")
    for gone in ("Battle of the 9", "Battle of the 100", "Rating System Update",
                 "Ratings without a song assigned"):
        assert gone not in base, f"'{gone}' should live in the special archive"


def test_engine_excludes_special_sigs():
    engine = TasteEngine()
    assert len(engine.special_sigs) >= 40
    for title in _special_titles():
        sig = _normalize_sig(title)
        assert sig in engine.special_sigs
        for row in engine.rows:
            assert _normalize_sig((row.get("title") or "").strip()) != sig, \
                f"special post leaked into song rows: {title!r}"


def test_real_songs_with_battle_in_title_are_kept():
    engine = TasteEngine()
    titles = {(r.get("title") or "") for r in engine.rows}
    # Curated keep-guards: real songs that merely contain "battle"/"vs"
    assert any("Space Battle" in t for t in titles)
    assert any("Battle Against A True Hero" in t for t in titles)
    assert any("Kungs" in t and "This Girl" in t for t in titles)
    assert any("Battle of Destiny" in t for t in titles)


def test_html_corrupted_rows_were_fixed_in_place():
    engine = TasteEngine()
    titles = {(r.get("title") or "") for r in engine.rows}
    assert any("Havana ft. Young Thug" in t and "<a href" not in t for t in titles)
    assert any("The Faim" in t and "The Alchemist" in t and "<a href" not in t
               for t in titles)
