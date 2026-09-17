"""
Tests for meta-post and mashup exclusion from song statistics.

Meta posts (review recaps, collections, playlists, tournaments) live in
data/posts_tails_special.csv and are excluded at engine load time.
Mashup/medley titles stay in the song set but must never resolve to a
release year (they compile songs that have their own years), so they can
never appear on the Song vs Year chart.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.taste_engine import TasteEngine


def _engine():
    return TasteEngine()


def _special_titles() -> list:
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


# ---------------------------------------------------------------
# Meta posts are completely excluded from the song dataset
# ---------------------------------------------------------------

def test_all_review_round_posts_are_archived():
    """Every Musicord review round, R1 through R12, plus the tourney."""
    engine = _engine()
    titles = {(r.get("title") or "").lower() for r in engine.rows}
    for r in range(1, 13):
        for suffix in ("Reviews!", "reviews!", "Reviews", "reviews"):
            assert f"musicord r{r} {suffix}".lower() not in titles
    assert not any("musicord" in t for t in titles)
    assert not any("musicord tourney" in t for t in titles)


def test_collection_and_playlist_posts_are_archived():
    engine = _engine()
    titles = {(r.get("title") or "").lower() for r in engine.rows}
    for banned in ("curated song reviews", "rap/hip hop song collection",
                   "complete jazz collection", "alphabetical song list",
                   "full country song list", "collection of lesser represented genres",
                   "chill song playlist", "my stance on lofi",
                   "one hit song for each year", "game promotion time!",
                   "artist list and rating", "flaws and motivation compilation"):
        assert banned not in titles, f"meta post leaked into songs: {banned!r}"


def test_meta_titles_live_in_the_special_archive():
    titles = _special_titles()
    lower = {t.lower() for t in titles}
    for expected in ("musicord r10 reviews", "curated song reviews",
                     "one hit song for each year", "full country song list",
                     "rap/hip hop song collection"):
        assert expected in lower, f"{expected!r} missing from archive"


def test_engine_special_sig_count_grew_with_meta_posts():
    engine = _engine()
    assert len(engine.special_sigs) >= 70  # 43 battle + 29 review/meta posts


# ---------------------------------------------------------------
# Mashups are songs but never get a release year
# ---------------------------------------------------------------

def test_mashup_titles_are_flagged():
    assert TasteEngine._is_mashup_title("Mashup of every TheFatRat song ever (Beyond Gaia's Horizon)")
    assert TasteEngine._is_mashup_title("80s Megamix")
    assert TasteEngine._is_mashup_title("The Battle March Medley")
    assert not TasteEngine._is_mashup_title("真夜中のドア / そうして私が (Miki Matsubara)")
    assert not TasteEngine._is_mashup_title("Get You / Japanese Denim")


def test_mashup_never_resolves_to_a_year():
    """Even if the cache held a year for a mashup, the resolver refuses."""
    TasteEngine._release_year_cache.setdefault(
        TasteEngine._release_year_key("TheFatRat", "Mashup of every TheFatRat song ever"), 2020)
    assert TasteEngine._release_year_for(
        "Mashup of every TheFatRat song ever (Beyond Gaia's Horizon)") is None


def test_real_medley_double_a_side_is_not_poisoned_by_prefix_words():
    """'mashup' detection must not swallow songs that merely share words."""
    assert TasteEngine._release_year_for("真夜中のドア / そうして私が (Miki Matsubara)") == 1979
    assert TasteEngine._release_year_for("Hey Jude [The Beatles Again]") == 1968
