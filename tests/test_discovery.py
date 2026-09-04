"""
Tests for src/discovery.py — the open-catalog Discover engine.

Everything runs offline against a fake Deezer (a dict-backed `fetch`) and a
tiny stand-in taste engine, so these tests are fast and deterministic.
"""

import json
import os
import sys
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.discovery import (  # noqa: E402
    MODES,
    DiscoveryEngine,
    _names_match,
    _norm,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------
class FakeTaste:
    """Just enough of TasteEngine for DiscoveryEngine."""

    def __init__(self, artists, owned=(), banned_artists=(), banned_songs=()):
        # artists: {name: [ratings]}
        self.all_artists = {n: {"ratings": list(r), "count": len(r)} for n, r in artists.items()}
        self._owned = {(_norm(a), _norm(s)) for a, s in owned}
        self._banned_artists = {_norm(a) for a in banned_artists}
        self.ban_list = {"artists": list(banned_artists), "songs": list(banned_songs)}
        self.rated_entries = [
            {"title": f"{song} ({artist}, 2020)", "rating": max(r)}
            for artist, r in artists.items()
            for song in ["Old Hit"]
        ]

    # Use the real normaliser so hit-rate matching behaves as in production.
    @staticmethod
    def _normalize_sig(text):
        from src.taste_engine import TasteEngine
        return TasteEngine._normalize_sig(text)

    def check_song_exists(self, artist, song):
        return {"exists": (_norm(artist), _norm(song)) in self._owned}

    def _is_banned(self, artist=None, song=None):
        if artist and _norm(artist) in self._banned_artists:
            return True
        if artist and song:
            return f"{artist} – {song}" in self.ban_list["songs"]
        return False

    def _release_year_for(self, title):
        return None


RECENT = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")


class FakeDeezer:
    """Deterministic graph: every artist A_i is related to A_{i+1..i+20}."""

    def __init__(self, n_artists=60, fail=False):
        self.calls = []
        self.fail = fail
        self.names = {i: f"Artist {i:02d}" for i in range(1, n_artists + 1)}

    def __call__(self, url):
        self.calls.append(url)
        if self.fail:
            return None
        u = urlparse(url)
        q = parse_qs(u.query)
        path = u.path
        if path == "/search/artist":
            name = q["q"][0]
            for i, n in self.names.items():
                if _names_match(n, name):
                    return {"data": [{"id": i, "name": n, "nb_fan": 1000 * i}]}
            return {"data": []}
        if path.endswith("/related"):
            i = int(path.split("/")[2])
            rel = [j for j in range(i + 1, i + 21) if j in self.names]
            return {"data": [{"id": j, "name": self.names[j], "nb_fan": 1000 * j, "picture": ""} for j in rel]}
        if path.endswith("/top"):
            i = int(path.split("/")[2])
            return {"data": [
                {"id": i * 100 + k, "title": f"Track {k}", "title_short": f"Track {k}", "rank": 100000 - k,
                 "album": {"title": f"Album {i}", "cover_medium": f"https://img/{i}.jpg"},
                 "link": f"https://deezer.com/track/{i * 100 + k}", "duration": 200}
                for k in range(25)
            ]}
        if path.endswith("/albums"):
            i = int(path.split("/")[2])
            return {"data": [
                {"id": i * 10, "title": f"New EP {i}", "release_date": RECENT, "record_type": "ep",
                 "cover_medium": "", "link": "", "fans": 5},
                {"id": i * 10 + 1, "title": f"Old LP {i}", "release_date": "1999-01-01", "record_type": "album",
                 "cover_medium": "", "link": "", "fans": 50},
            ]}
        return {"data": []}


@pytest.fixture
def paths(tmp_path):
    return str(tmp_path / "cache.json"), str(tmp_path / "log.json")


@pytest.fixture
def taste():
    # Artists 01-05 are loved (seeds). Artist 10 is disliked. Artist 12 is
    # lukewarm-known. Artist 07 is banned. Artist 03's "Track 0" is owned.
    return FakeTaste(
        artists={
            "Artist 01": [95, 92, 90],
            "Artist 02": [90, 88],
            "Artist 03": [99, 97, 96, 95],
            "Artist 04": [86, 85],
            "Artist 05": [100, 90],
            "Artist 10": [40, 50],
            "Artist 12": [70, 72],
            "Meh Solo": [90],          # only one rating → not a seed
        },
        owned=[("Artist 03", "Track 0"), ("Artist 06", "Track 0"), ("Artist 06", "Track 1")],
        banned_artists=["Artist 07"],
        banned_songs=["Artist 08 – Track 0", "Artist 09 – Track 0", "Artist 09 – Track 1"],
    )


# ---------------------------------------------------------------------------
# Name matching
# ---------------------------------------------------------------------------
class TestNameMatching:
    @pytest.mark.parametrize("a,b,expected", [
        ("Daft Punk", "daft punk", True),
        ("Earth, Wind & Fire", "Earth Wind and Fire", True),
        ("Britney Spears", "Brittney Spears", True),      # near-typo, long name
        ("2CELLOS", "2Cellos", True),
        ("Pharrell Williams", "Happy", False),
        ("Parov Stelar", "Parov Stelar Trio", False),      # substring is NOT a match
        ("ABBA", "ABBX", False),                           # short names need exact match
    ])
    def test_cases(self, a, b, expected):
        assert _names_match(a, b) is expected


# ---------------------------------------------------------------------------
# Seeds
# ---------------------------------------------------------------------------
class TestSeeds:
    def test_seed_selection_and_ordering(self, taste, paths):
        eng = DiscoveryEngine(taste, fetch=FakeDeezer(), cache_path=paths[0], log_path=paths[1])
        names = [s["name"] for s in eng.seeds(limit=100) if s["name"].startswith("Artist")]
        assert {"Artist 01", "Artist 02", "Artist 03", "Artist 04", "Artist 05"} <= set(names)
        assert "Artist 10" not in names and "Artist 12" not in names
        assert "Meh Solo" not in names
        # Loved a lot AND rated often → first.
        assert names[0] == "Artist 03"
        for s in eng.seeds():
            assert 0.3 <= s["weight"] <= 1.0

    def test_limit_respected(self, taste, paths):
        eng = DiscoveryEngine(taste, fetch=FakeDeezer(), cache_path=paths[0], log_path=paths[1])
        assert len(eng.seeds(limit=2)) == 2


# ---------------------------------------------------------------------------
# discover()
# ---------------------------------------------------------------------------
class TestDiscover:
    def test_all_modes_return_picks(self, taste, paths):
        eng = DiscoveryEngine(taste, fetch=FakeDeezer(), cache_path=paths[0], log_path=paths[1])
        for mode in MODES:
            out = eng.discover(mode=mode, limit=10, max_seeds=5)
            assert out["mode"] == mode
            assert out["network_error"] is False
            assert 0 < len(out["picks"]) <= 10
            assert out["seeds_used"]
            for p in out["picks"]:
                for key in ("artist", "song", "cover", "link", "deezer_id", "via", "reason", "mode"):
                    assert key in p, key
                assert p["mode"] == mode

    def test_one_track_per_artist_and_seed_cap(self, taste, paths):
        eng = DiscoveryEngine(taste, fetch=FakeDeezer(), cache_path=paths[0], log_path=paths[1])
        out = eng.discover(mode="medium", limit=24, max_seeds=5)
        artists = [p["artist"] for p in out["picks"]]
        assert len(artists) == len(set(artists))
        top_seed_counts = {}
        for p in out["picks"]:
            top_seed_counts[p["via"][0]] = top_seed_counts.get(p["via"][0], 0) + 1
        assert max(top_seed_counts.values()) <= 4

    def test_filters_owned_banned_disliked(self, taste, paths):
        eng = DiscoveryEngine(taste, fetch=FakeDeezer(), cache_path=paths[0], log_path=paths[1])
        picks = []
        for mode in MODES:
            picks += eng.discover(mode=mode, limit=48, max_seeds=5)["picks"]
        by_artist = {p["artist"]: p for p in picks}
        assert "Artist 07" not in by_artist            # banned artist
        assert "Artist 10" not in by_artist            # disliked (avg < 65)
        assert "Artist 09" not in by_artist            # 2 ignored songs → disliked
        assert "Artist 12" not in by_artist            # known + lukewarm
        if "Artist 06" in by_artist:                   # owned tracks skipped, next one chosen
            assert by_artist["Artist 06"]["song"] not in ("Track 0", "Track 1")
        if "Artist 08" in by_artist:
            assert by_artist["Artist 08"]["song"] != "Track 0"

    def test_easy_mode_allows_loved_known_artists_others_do_not(self, taste, paths):
        eng = DiscoveryEngine(taste, fetch=FakeDeezer(), cache_path=paths[0], log_path=paths[1])
        easy = eng.discover(mode="easy", limit=48, max_seeds=5)["picks"]
        hard = eng.discover(mode="hard", limit=48, max_seeds=5)["picks"]
        assert any(p["known_artist"] for p in easy)
        assert not any(p["known_artist"] for p in hard)
        # Seeds themselves (Artist 02..05) are neighbours of Artist 01 — allowed in easy only.
        assert not any(p["artist"] in ("Artist 02", "Artist 03") for p in hard)

    def test_seed_explore(self, taste, paths):
        eng = DiscoveryEngine(taste, fetch=FakeDeezer(), cache_path=paths[0], log_path=paths[1])
        out = eng.discover(mode="medium", limit=8, seed="Artist 30")
        assert out["seed"] == "Artist 30"
        assert out["seeds_used"] == ["Artist 30"]
        assert out["picks"]
        assert all(p["via"] == ["Artist 30"] for p in out["picks"])

    def test_unknown_seed_gives_empty_not_error(self, taste, paths):
        eng = DiscoveryEngine(taste, fetch=FakeDeezer(), cache_path=paths[0], log_path=paths[1])
        out = eng.discover(mode="easy", seed="Nobody Ever Heard Of")
        assert out["picks"] == []
        assert out["network_error"] is False

    def test_invalid_mode_falls_back_to_easy(self, taste, paths):
        eng = DiscoveryEngine(taste, fetch=FakeDeezer(), cache_path=paths[0], log_path=paths[1])
        assert eng.discover(mode="ultra", limit=3, max_seeds=2)["mode"] == "easy"


# ---------------------------------------------------------------------------
# Cache, persistence, circuit breaker
# ---------------------------------------------------------------------------
class TestCacheAndResilience:
    def test_warm_cache_makes_zero_calls_and_persists(self, taste, paths):
        dz = FakeDeezer()
        eng = DiscoveryEngine(taste, fetch=dz, cache_path=paths[0], log_path=paths[1])
        first = eng.discover(mode="easy", limit=10, max_seeds=5)
        cold_calls = len(dz.calls)
        assert cold_calls > 0
        assert os.path.exists(paths[0]) and os.path.exists(paths[1])

        # A brand-new engine reading the same cache file needs no network.
        dz2 = FakeDeezer()
        eng2 = DiscoveryEngine(taste, fetch=dz2, cache_path=paths[0], log_path=paths[1])
        second = eng2.discover(mode="easy", limit=10, max_seeds=5)
        assert dz2.calls == []
        assert [p["artist"] for p in second["picks"]] == [p["artist"] for p in first["picks"]]

    def test_offline_circuit_breaker(self, taste, paths):
        dz = FakeDeezer(fail=True)
        eng = DiscoveryEngine(taste, fetch=dz, cache_path=paths[0], log_path=paths[1])
        out = eng.discover(mode="easy", limit=10, max_seeds=30)
        assert out["picks"] == []
        assert out["network_error"] is True
        # 30 seeds, but we stop knocking after max_failures consecutive misses.
        assert len(dz.calls) == eng.max_failures

    def test_offline_does_not_negative_cache(self, taste, paths):
        dz = FakeDeezer(fail=True)
        eng = DiscoveryEngine(taste, fetch=dz, cache_path=paths[0], log_path=paths[1])
        eng.discover(mode="easy", limit=5, max_seeds=3)
        assert eng.cache["artist_ids"] == {}
        # Back online → same engine recovers.
        dz.fail = False
        assert eng.discover(mode="easy", limit=5, max_seeds=3)["picks"]

    def test_corrupt_cache_file_is_ignored(self, taste, paths):
        with open(paths[0], "w") as f:
            f.write("{not json")
        eng = DiscoveryEngine(taste, fetch=FakeDeezer(), cache_path=paths[0], log_path=paths[1])
        assert eng.discover(mode="easy", limit=3, max_seeds=2)["picks"]


# ---------------------------------------------------------------------------
# Fresh releases + hit-rate stats
# ---------------------------------------------------------------------------
class TestFreshAndStats:
    def test_fresh_releases_filters_by_window(self, taste, paths):
        eng = DiscoveryEngine(taste, fetch=FakeDeezer(), cache_path=paths[0], log_path=paths[1])
        out = eng.fresh_releases(days=90, limit=20)
        assert out["network_error"] is False
        assert out["artists_checked"] > 0
        titles = [r["title"] for r in out["releases"]]
        assert titles and all(t.startswith("New EP") for t in titles)
        for r in out["releases"]:
            assert {"artist", "title", "release_date", "record_type", "your_avg"} <= set(r)

    def test_fresh_releases_offline(self, taste, paths):
        eng = DiscoveryEngine(taste, fetch=FakeDeezer(fail=True), cache_path=paths[0], log_path=paths[1])
        out = eng.fresh_releases(days=30)
        assert out["releases"] == [] and out["network_error"] is True

    def test_stats_track_hit_rate(self, taste, paths):
        eng = DiscoveryEngine(taste, fetch=FakeDeezer(), cache_path=paths[0], log_path=paths[1])
        picks = eng.discover(mode="hard", limit=4, max_seeds=3)["picks"]
        assert len(picks) >= 2
        s = eng.stats()
        assert s["by_mode"]["hard"]["surfaced"] == len(picks)
        assert s["total"]["rated"] == 0 and s["total"]["hit_rate"] is None

        # User later rates two surfaced picks: one hit, one miss.
        taste.rated_entries.append({"title": f"{picks[0]['song']} ({picks[0]['artist']}, 2024)", "rating": 90})
        taste.rated_entries.append({"title": f"{picks[1]['artist']} – {picks[1]['song']}", "rating": 60})
        s = eng.stats()
        assert s["by_mode"]["hard"]["rated"] == 2
        assert s["by_mode"]["hard"]["hits"] == 1
        assert s["total"]["hit_rate"] == 50

    def test_log_file_is_json(self, taste, paths):
        eng = DiscoveryEngine(taste, fetch=FakeDeezer(), cache_path=paths[0], log_path=paths[1])
        eng.discover(mode="easy", limit=3, max_seeds=2)
        with open(paths[1]) as f:
            data = json.load(f)
        assert "picks" in data and data["picks"]


# ---------------------------------------------------------------------------
# Flask endpoints (fake network injected into the app's engine)
# ---------------------------------------------------------------------------
@pytest.fixture
def client(tmp_path, monkeypatch):
    os.environ["FLASK_TESTING"] = "1"
    import app as app_module

    dz = FakeDeezer()
    eng = DiscoveryEngine(app_module.taste_engine, fetch=dz,
                          cache_path=str(tmp_path / "c.json"), log_path=str(tmp_path / "l.json"))
    monkeypatch.setattr(app_module, "discovery", eng)
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        yield c


class TestDiscoverEndpoints:
    def test_discover_endpoint_shape_and_clamping(self, client):
        resp = client.get("/api/discover?mode=hard&limit=999")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["mode"] == "hard"
        assert len(data["picks"]) <= 48
        assert "stats" in data and "seeds_used" in data
        for p in data["picks"]:
            assert "listened" in p  # annotated like every other suggestion surface

    def test_discover_bad_mode_and_seed(self, client):
        data = client.get("/api/discover?mode=nope&seed=Artist%2020&limit=3").get_json()
        assert data["mode"] == "easy"
        assert data["seed"] == "Artist 20"

    def test_fresh_releases_endpoint(self, client):
        data = client.get("/api/fresh-releases?days=1000&limit=5").get_json()
        assert data["days"] == 365          # clamped
        assert len(data["releases"]) <= 5
