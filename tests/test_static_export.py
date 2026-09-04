"""Tests for the GitHub Pages static snapshot export (scripts/export_static.py).

The export must produce a self-contained `docs/` folder:
  * index.html with relative asset paths (works under any Pages subpath)
  * css/ and js/ copied from static/
  * data/config.json that the browser shim uses to detect static mode
  * data/api/*.json covering every read-only endpoint the frontend fetches
  * a full songs dump that supports client-side pagination/search

These tests run the real exporter against the real CSV (same as the Flask app)
and then serve the output over HTTP to prove it's actually browseable.
"""
import http.server
import json
import socketserver
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.export_static import export_static  # noqa: E402

# Every read-only endpoint the frontend fetches must have a snapshot file.
REQUIRED_API_FILES = [
    "stats.json",
    "blind-spots.json",
    "favorite-artists.json",
    "constellation.json",
    "evolution.json",
    "recommendations.json",
    "weekly-discovery.json",
    "challenges.json",
    "challenges-opposite.json",
    "backfill-preview.json",
    "uncategorized-breakdown.json",
    "ban-list.json",
    "spotify-status.json",
    "songs.json",
    "discover-easy.json",
    "discover-medium.json",
    "discover-hard.json",
    "fresh-releases.json",
]


@pytest.fixture(scope="module")
def static_site(tmp_path_factory):
    """Export once per test session into a temp dir."""
    out = tmp_path_factory.mktemp("static_site")
    export_static(out_dir=str(out))
    return out


def _load(static_site, *parts):
    path = static_site.joinpath(*parts)
    assert path.exists(), f"Missing {path}"
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Structure & correctness
# ---------------------------------------------------------------------------

class TestExportStructure:
    def test_index_html_exists_with_relative_paths(self, static_site):
        html = (static_site / "index.html").read_text(encoding="utf-8")
        assert "src=\"js/utils.js\"" in html, "JS asset paths must be relative"
        assert "href=\"css/styles.css\"" in html, "CSS asset paths must be relative"
        # No absolute asset paths may remain
        assert 'src="/js/' not in html
        assert 'href="/css/' not in html

    def test_assets_copied(self, static_site):
        for rel in ["css/styles.css", "js/utils.js", "js/app.js", "js/recommender.js"]:
            assert (static_site / rel).exists(), f"Missing {rel}"

    def test_every_required_api_file_present(self, static_site):
        api = static_site / "data" / "api"
        for name in REQUIRED_API_FILES:
            assert (api / name).exists(), f"Missing data/api/{name}"

    def test_all_api_files_are_valid_json(self, static_site):
        api = static_site / "data" / "api"
        for f in api.glob("*.json"):
            json.loads(f.read_text(encoding="utf-8"))  # raises on bad JSON


class TestExportContent:
    def test_stats_shape(self, static_site):
        stats = _load(static_site, "data", "api", "stats.json")
        for key in ["total_entries", "rated_entries", "avg_rating", "unique_artists"]:
            assert key in stats, f"stats.json missing {key}"
        assert stats["total_entries"] > 0

    def test_recommendations_shape(self, static_site):
        recs = _load(static_site, "data", "api", "recommendations.json")
        assert isinstance(recs, dict) and len(recs) > 0
        for cat in recs.values():
            assert "recommendations" in cat

    def test_challenge_both_modes(self, static_site):
        outside = _load(static_site, "data", "api", "challenges.json")
        opposite = _load(static_site, "data", "api", "challenges-opposite.json")
        assert outside.get("mode") == "outside_zone"
        assert opposite.get("mode") == "opposite_taste"
        assert "by_tier" in outside and "by_tier" in opposite

    def test_songs_dump_full_and_shaped(self, static_site):
        dump = _load(static_site, "data", "api", "songs.json")
        assert dump["total"] == len(dump["songs"]) > 0
        assert any(s.get("rating") is not None for s in dump["songs"]), "dump should include rated songs"
        for s in dump["songs"][:5]:
            for key in ["title", "rating", "date", "preview"]:
                assert key in s, f"songs.json row missing {key}"

    def test_ban_list_shape(self, static_site):
        ban = _load(static_site, "data", "api", "ban-list.json")
        for key in ["genres", "artists", "songs"]:
            assert key in ban

    def test_config_detects_static_mode(self, static_site):
        cfg = _load(static_site, "data", "config.json")
        assert cfg["mode"] == "static"
        assert cfg["counts"]["entries"] > 0


# ---------------------------------------------------------------------------
# Serve the exported site over HTTP and prove it's browseable
# ---------------------------------------------------------------------------

class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # silence request logs
        pass


@pytest.fixture(scope="module")
def static_server(static_site):
    handler = lambda *a, **kw: _QuietHandler(*a, directory=str(static_site), **kw)  # noqa: E731
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as httpd:
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        yield f"http://127.0.0.1:{port}"
        httpd.shutdown()


class TestStaticServing:
    def test_index_and_assets_serve(self, static_server):
        # Python's http.server serves .js as text/javascript (older spec) while
        # some stacks use application/javascript — accept either.
        def js_type_ok(ct):
            return "javascript" in ct or "application/javascript" in ct

        checks = [
            ("/", "text/html"),
            ("/index.html", "text/html"),
            ("/js/utils.js", None),  # handled by js_type_ok
            ("/css/styles.css", "text/css"),
            ("/data/config.json", "application/json"),
        ]
        for path, expected_type in checks:
            with urllib.request.urlopen(static_server + path, timeout=10) as resp:
                assert resp.status == 200, path
                ct = resp.headers.get("Content-Type", "")
                if expected_type is None:
                    assert js_type_ok(ct), f"{path}: unexpected Content-Type {ct!r}"
                else:
                    assert expected_type in ct, f"{path}: got {ct!r}"

    def test_api_snapshots_serve_as_json(self, static_server):
        for name in REQUIRED_API_FILES:
            url = f"{static_server}/data/api/{name}"
            with urllib.request.urlopen(url, timeout=10) as resp:
                assert resp.status == 200, name
                json.loads(resp.read().decode("utf-8"))  # must parse

    def test_unknown_path_404s(self, static_server):
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(static_server + "/nope.json", timeout=10)
        assert exc.value.code == 404

    def test_export_never_writes_to_its_csv(self, tmp_path):
        """Exporting must never write to the CSV it reads (read-only snapshot).
        Uses an isolated copy so the test is immune to concurrent writers
        (preview server / parallel test runs appending to the shared CSV).
        """
        import shutil

        tmp_csv = tmp_path / "posts_tails.csv"
        shutil.copy2(ROOT / "data" / "posts_tails.csv", tmp_csv)

        from src.taste_engine import TasteEngine
        engine = TasteEngine(str(tmp_csv))
        before = tmp_csv.read_bytes()

        export_static(engine=engine, out_dir=str(tmp_path / "site"))

        after = tmp_csv.read_bytes()
        assert before == after, "export_static mutated the source CSV!"
        # And it must not have touched the real project CSV either.
        assert (ROOT / "data" / "posts_tails.csv").exists()
