"""
discovery.py — Live candidate generation for fresh, new-to-you music.

Why this exists
---------------
Every other suggestion surface in TasteScope (Recommender categories,
Algorithm picks, Challenges, Weekly) scores a *closed* pool: the hand-written
"If you love…" lists plus the ~180-entry challenge_db.json. Once those are
rated they're gone. Professional recommenders spend most of their effort on
*candidate generation* from an open catalog — this module does the poor-man's
version of that, artist-level collaborative filtering:

    your top-rated artists  →  Deezer "related artists"  →  their top tracks
                            →  drop owned / banned / disliked  →  rank + diversify

Data source: Deezer's public REST API (https://api.deezer.com). No key, no
auth, 30-second previews included. (Spotify removed related-artists,
recommendations and previews for new apps on 2024-11-27, which is why the
Spotify path is not used here.) ListenBrainz Labs similar-artists is a second
free source and slots into `fetch_related()` if you want to add it later.

Exploration modes (borrowed from ListenBrainz LB Radio):
    easy   — nearest neighbours' best-known tracks; artists you already like are allowed
    medium — mid-list neighbours, deeper cuts, artists you have NOT rated yet
    hard   — far neighbours, deep cuts, low-fan artists favoured — "challenge me"

Everything network-related goes through a single `fetch(url) -> dict|None`
callable so the engine is fully testable offline, and every remote lookup is
cached on disk (data/discovery_cache.json) with per-type TTLs so a warm run
makes zero requests.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional

DEEZER_API = "https://api.deezer.com"
USER_AGENT = "TasteScope/1.0 (personal music dashboard)"

# Deezer allows ~50 requests / 5 s per IP. Stay well under it.
_MIN_INTERVAL_SEC = 0.12
_last_call = [0.0]
_call_lock = threading.Lock()

# Cache TTLs (seconds)
TTL = {
    "artist_ids": 90 * 86400,
    "related": 30 * 86400,
    "top": 14 * 86400,
    "albums": 1 * 86400,
    "not_found": 7 * 86400,
}

MODES = ("easy", "medium", "hard")

# Which slice of each ranked list a mode looks at. Related artists come back
# ~20 long; top tracks are fetched 25 long.
MODE_WINDOWS = {
    "easy":   {"related": (0, 7),  "tracks": (0, 5),  "allow_known": True},
    "medium": {"related": (4, 14), "tracks": (4, 15), "allow_known": False},
    "hard":   {"related": (10, 20), "tracks": (12, 25), "allow_known": False},
}


DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")


def default_fetch(url: str, timeout: float = 8.0) -> Optional[dict]:
    """GET a JSON document from Deezer, politely throttled. Returns None on
    any failure (network, non-JSON, Deezer error envelope)."""
    with _call_lock:
        wait = _MIN_INTERVAL_SEC - (time.monotonic() - _last_call[0])
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.monotonic()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    if isinstance(data, dict) and "error" in data and "data" not in data:
        return None
    return data


def _norm(name: str) -> str:
    """Loose artist-name key: lowercase, '&'→'and', strip punctuation, collapse spaces."""
    t = (name or "").lower().replace("&", " and ")
    t = re.sub(r"\(.*?\)|\[.*?\]", " ", t)          # (feat. …), [live]
    t = re.sub(r"\b(covered by|cover by|feat\.?|ft\.?|featuring)\b.*$", " ", t)
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _names_match(a: str, b: str) -> bool:
    """Same artist? Exact after normalisation, or a close typo ("Brittney" vs
    "Britney"). Deliberately strict: the artist index contains parse junk like
    "Happy" and a loose match would turn that into Pharrell."""
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if len(na) >= 8 and len(nb) >= 8:
        return difflib.SequenceMatcher(None, na, nb).ratio() >= 0.9
    return False


class DiscoveryEngine:
    """Open-catalog discovery on top of a TasteEngine.

    Parameters
    ----------
    taste : TasteEngine
        Used for seeds (your rated artists), owned/banned checks and genre/year lookups.
    fetch : callable(url) -> dict | None
        HTTP layer. Inject a fake for tests.
    cache_path : str
        JSON file for remote lookups. Missing/corrupt → starts empty.
    log_path : str
        JSON file recording which picks were surfaced (drives the hit-rate stat).
    """

    def __init__(self, taste, fetch: Callable[[str], Optional[dict]] = default_fetch,
                 cache_path: Optional[str] = None,
                 log_path: Optional[str] = None):
        self.taste = taste
        self.fetch = fetch
        # Anchor to the repo's data/ dir so the Flask app, the static exporter
        # and the CI job all share one cache regardless of their cwd.
        self.cache_path = cache_path or os.path.join(DATA_DIR, "discovery_cache.json")
        self.log_path = log_path or os.path.join(DATA_DIR, "discovery_log.json")
        self._lock = threading.Lock()
        self._dirty = False
        self.cache = self._load_json(self.cache_path) or {}
        for k in ("artist_ids", "related", "top", "albums"):
            self.cache.setdefault(k, {})
        self.log = self._load_json(self.log_path) or {"picks": {}}
        self.log.setdefault("picks", {})
        self.last_network_error = False
        self._consecutive_failures = 0
        self.max_failures = 3  # after this many back-to-back failures, stop calling out for this run

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    @staticmethod
    def _load_json(path: str):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None

    def _save(self):
        if not self._dirty:
            return
        try:
            os.makedirs(os.path.dirname(self.cache_path) or ".", exist_ok=True)
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=1)
            self._dirty = False
        except OSError:
            pass

    def _save_log(self):
        try:
            os.makedirs(os.path.dirname(self.log_path) or ".", exist_ok=True)
            with open(self.log_path, "w", encoding="utf-8") as f:
                json.dump(self.log, f, ensure_ascii=False, indent=1)
        except OSError:
            pass

    def _fresh(self, entry: Optional[dict], kind: str) -> bool:
        if not entry or "ts" not in entry:
            return False
        ttl = TTL["not_found"] if entry.get("id") is None and kind == "artist_ids" else TTL[kind]
        return (time.time() - entry["ts"]) < ttl

    # ------------------------------------------------------------------
    # Deezer lookups (all cached)
    # ------------------------------------------------------------------
    def _get(self, path: str, **params) -> Optional[dict]:
        """One Deezer call with a circuit breaker: once `max_failures` calls in
        a row fail (offline box, firewall, Deezer down) we stop trying for the
        rest of this run instead of burning a timeout per seed."""
        if self._consecutive_failures >= self.max_failures:
            self.last_network_error = True
            return None
        url = f"{DEEZER_API}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = self.fetch(url)
        if data is None:
            self.last_network_error = True
            self._consecutive_failures += 1
        else:
            self._consecutive_failures = 0
        return data

    def resolve_artist(self, name: str) -> Optional[dict]:
        """Artist name → {'id','name','nb_fan'} via Deezer search, or None."""
        key = _norm(name)
        if not key:
            return None
        hit = self.cache["artist_ids"].get(key)
        if self._fresh(hit, "artist_ids"):
            return hit if hit.get("id") else None
        data = self._get("/search/artist", q=name, limit=5)
        entry = {"id": None, "ts": time.time()}
        if data and data.get("data"):
            for a in data["data"]:
                if _names_match(a.get("name", ""), name):
                    entry = {"id": a["id"], "name": a["name"], "nb_fan": a.get("nb_fan", 0), "ts": time.time()}
                    break
        elif data is None:
            return None  # network failure: don't negative-cache
        self.cache["artist_ids"][key] = entry
        self._dirty = True
        return entry if entry.get("id") else None

    def fetch_related(self, artist_id: int) -> List[dict]:
        k = str(artist_id)
        hit = self.cache["related"].get(k)
        if self._fresh(hit, "related"):
            return hit["items"]
        data = self._get(f"/artist/{artist_id}/related", limit=20)
        if data is None:
            return hit["items"] if hit else []
        items = [{"id": a["id"], "name": a.get("name", ""), "nb_fan": a.get("nb_fan", 0),
                  "picture": a.get("picture_medium", "")}
                 for a in data.get("data", []) if a.get("id")]
        self.cache["related"][k] = {"ts": time.time(), "items": items}
        self._dirty = True
        return items

    def fetch_top(self, artist_id: int) -> List[dict]:
        k = str(artist_id)
        hit = self.cache["top"].get(k)
        if self._fresh(hit, "top"):
            return hit["items"]
        data = self._get(f"/artist/{artist_id}/top", limit=25)
        if data is None:
            return hit["items"] if hit else []
        items = []
        for t in data.get("data", []):
            if not t.get("id"):
                continue
            items.append({
                "id": t["id"],
                "title": t.get("title_short") or t.get("title", ""),
                "rank": t.get("rank", 0),
                "album": (t.get("album") or {}).get("title", ""),
                "cover": (t.get("album") or {}).get("cover_medium", ""),
                "link": t.get("link", ""),
                "duration": t.get("duration", 0),
                "explicit": bool(t.get("explicit_lyrics")),
            })
        self.cache["top"][k] = {"ts": time.time(), "items": items}
        self._dirty = True
        return items

    def fetch_albums(self, artist_id: int) -> List[dict]:
        k = str(artist_id)
        hit = self.cache["albums"].get(k)
        if self._fresh(hit, "albums"):
            return hit["items"]
        data = self._get(f"/artist/{artist_id}/albums", limit=8)
        if data is None:
            return hit["items"] if hit else []
        items = [{
            "id": a["id"], "title": a.get("title", ""), "release_date": a.get("release_date", ""),
            "record_type": a.get("record_type", ""), "cover": a.get("cover_medium", ""),
            "link": a.get("link", ""), "fans": a.get("fans", 0),
        } for a in data.get("data", []) if a.get("id")]
        self.cache["albums"][k] = {"ts": time.time(), "items": items}
        self._dirty = True
        return items

    # ------------------------------------------------------------------
    # Taste-side helpers
    # ------------------------------------------------------------------
    def _artist_avgs(self) -> Dict[str, dict]:
        """normalized artist name → {'name','avg','count'} from your ratings."""
        out = {}
        for artist, info in self.taste.all_artists.items():
            ratings = info.get("ratings") or []
            if not ratings:
                continue
            out[_norm(artist)] = {"name": artist, "avg": sum(ratings) / len(ratings), "count": len(ratings)}
        return out

    def seeds(self, limit: int = 40) -> List[dict]:
        """Artists that define your taste: 2+ rated songs and avg >= 85, plus
        declared favourites. Weight ∈ [0.3, 1] grows with how much you love them."""
        try:
            from src.genre_data import FAVORITE_ARTISTS
        except Exception:  # pragma: no cover
            FAVORITE_ARTISTS = {}
        avgs = self._artist_avgs()
        seeds: Dict[str, dict] = {}
        for key, a in avgs.items():
            if a["count"] >= 2 and a["avg"] >= 85 and len(a["name"]) >= 3:
                w = min(1.0, max(0.3, (a["avg"] - 70) / 30))
                seeds[key] = {"name": a["name"], "weight": w, "avg": round(a["avg"], 1), "count": a["count"]}
        for fav in FAVORITE_ARTISTS:
            key = _norm(fav)
            if key not in seeds:
                a = avgs.get(key, {})
                seeds[key] = {"name": fav, "weight": 1.0, "avg": round(a.get("avg", 90), 1), "count": a.get("count", 0)}
        # Love matters most, but an artist you rated 7 times at 94 says more
        # about you than one you rated twice at 98.
        ordered = sorted(seeds.values(),
                         key=lambda s: -(s["weight"] * (1 + 0.15 * min(s["count"], 10))))
        return ordered[:limit]

    def _disliked_artists(self, avgs: Dict[str, dict]) -> set:
        """Artists you have rated and clearly don't like (avg < 65, 2+ songs),
        or that you've ignored 2+ songs from — never surface these."""
        out = {k for k, a in avgs.items() if a["count"] >= 2 and a["avg"] < 65}
        ignored = defaultdict(int)
        for s in self.taste.ban_list.get("songs", []):
            m = re.split(r"\s+[\u2013\u2014-]\s+", s, maxsplit=1)
            if len(m) == 2:
                ignored[_norm(m[0])] += 1
        out.update({k for k, n in ignored.items() if n >= 2})
        return out

    def _owned(self, artist: str, song: str) -> bool:
        try:
            return bool(self.taste.check_song_exists(artist, song).get("exists"))
        except Exception:
            return False

    def _year_for(self, artist: str, song: str):
        try:
            return self.taste._release_year_for(f"{artist} \u2013 {song}")
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------
    def discover(self, mode: str = "easy", limit: int = 24, seed: Optional[str] = None,
                 max_seeds: int = 30) -> Dict:
        mode = mode if mode in MODES else "easy"
        win = MODE_WINDOWS[mode]
        self.last_network_error = False
        self._consecutive_failures = 0

        with self._lock:
            avgs = self._artist_avgs()
            disliked = self._disliked_artists(avgs)

            if seed:
                seed_list = [{"name": seed, "weight": 1.0,
                              "avg": round(avgs.get(_norm(seed), {}).get("avg", 0), 1) or None,
                              "count": avgs.get(_norm(seed), {}).get("count", 0)}]
            else:
                seed_list = self.seeds(max_seeds)

            # 1) Expand seeds → candidate artists, accumulating evidence.
            cand: Dict[int, dict] = {}
            seeds_used = []
            for s in seed_list:
                a = self.resolve_artist(s["name"])
                if not a:
                    continue
                related = self.fetch_related(a["id"])
                if not related:
                    continue
                seeds_used.append(s["name"])
                lo, hi = win["related"]
                for rank, r in enumerate(related):
                    if not (lo <= rank < hi):
                        continue
                    rk = _norm(r["name"])
                    if rk in disliked or self.taste._is_banned(artist=r["name"]):
                        continue
                    known = rk in avgs
                    if known and not win["allow_known"]:
                        continue
                    if known and avgs[rk]["avg"] < 80:
                        continue  # tried it, lukewarm — not a "discovery"
                    c = cand.setdefault(r["id"], {
                        "id": r["id"], "name": r["name"], "nb_fan": r.get("nb_fan", 0),
                        "picture": r.get("picture", ""), "score": 0.0, "via": [], "known": known,
                    })
                    proximity = 1.0 - (rank / 25.0)
                    c["score"] += s["weight"] * proximity
                    c["via"].append({"seed": s["name"], "avg": s.get("avg"), "rank": rank})

            if not cand:
                self._save()
                return self._empty(mode, seed, seeds_used)

            # 2) Rank candidate artists. Hard mode rewards obscurity.
            for c in cand.values():
                c["via"].sort(key=lambda v: v["rank"])
                c["n_seeds"] = len({v["seed"] for v in c["via"]})
                c["score"] += 0.25 * (c["n_seeds"] - 1)  # corroboration bonus
                if mode == "hard":
                    fans = max(c.get("nb_fan") or 0, 1)
                    c["score"] += max(0.0, 0.6 - (fans / 500000.0))  # <300k fans gets a lift
                elif mode == "easy":
                    fans = c.get("nb_fan") or 0
                    c["score"] += min(0.3, fans / 2000000.0)

            ranked = sorted(cand.values(), key=lambda c: -c["score"])

            # 3) Turn artists into one track each, with diversity caps.
            picks: List[dict] = []
            per_seed = defaultdict(int)
            tlo, thi = win["tracks"]
            for c in ranked:
                if len(picks) >= limit:
                    break
                top_seed = c["via"][0]["seed"]
                if per_seed[top_seed] >= 4:
                    continue
                tracks = self.fetch_top(c["id"])
                if not tracks:
                    continue
                window = tracks[tlo:thi] or tracks[-5:]
                chosen = None
                for t in window:
                    if self._owned(c["name"], t["title"]):
                        continue
                    if self.taste._is_banned(artist=c["name"], song=t["title"]):
                        continue
                    chosen = t
                    break
                if not chosen:
                    continue
                per_seed[top_seed] += 1
                picks.append(self._pick(c, chosen, mode))

            self._save()
            self._record(picks, mode)
            return {
                "mode": mode,
                "seed": seed,
                "picks": picks,
                "seeds_used": seeds_used,
                "candidates": len(cand),
                "stats": self.stats(),
                "source": "deezer",
                "network_error": self.last_network_error and not picks,
                "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }

    def _pick(self, c: dict, t: dict, mode: str) -> dict:
        via = c["via"][:3]
        via_txt = ", ".join(
            f"{v['seed']}" + (f" (you rate {int(round(v['avg']))})" if v.get("avg") else "")
            for v in via
        )
        n = c["n_seeds"]
        lead = f"{n} of your favourites point here" if n > 1 else "Neighbour of"
        reason = f"{lead}: {via_txt}" if n > 1 else f"Neighbour of {via_txt}"
        if c.get("known"):
            reason = f"Deeper cut from an artist you already rate well · {reason}"
        fans = c.get("nb_fan") or 0
        if mode == "hard" and fans:
            reason += f" · only {fans:,} Deezer fans"
        return {
            "artist": c["name"],
            "song": t["title"],
            "year": self._year_for(c["name"], t["title"]),
            "album": t.get("album", ""),
            "cover": t.get("cover", ""),
            "link": t.get("link", ""),
            "deezer_id": t["id"],
            "popularity": t.get("rank", 0),
            "artist_fans": fans,
            "score": round(c["score"], 3),
            "via": [v["seed"] for v in via],
            "known_artist": bool(c.get("known")),
            "reason": reason,
            "mode": mode,
            "already_owned": False,
        }

    def _empty(self, mode, seed, seeds_used) -> Dict:
        return {
            "mode": mode, "seed": seed, "picks": [], "seeds_used": seeds_used, "candidates": 0,
            "stats": self.stats(), "source": "deezer",
            "network_error": self.last_network_error,
            "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

    # ------------------------------------------------------------------
    # Fresh releases — "new to the world", not just new to you
    # ------------------------------------------------------------------
    def fresh_releases(self, days: int = 90, limit: int = 20, max_artists: int = 40) -> Dict:
        self.last_network_error = False
        self._consecutive_failures = 0
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        avgs = self._artist_avgs()
        # Artists you rate well OR simply listen to a lot.
        orbit = sorted(
            [a for a in avgs.values() if (a["count"] >= 2 and a["avg"] >= 80) or a["count"] >= 4],
            key=lambda a: (-(a["avg"] >= 85), -a["count"], -a["avg"]),
        )[:max_artists]
        out = []
        with self._lock:
            for a in orbit:
                d = self.resolve_artist(a["name"])
                if not d:
                    continue
                for alb in self.fetch_albums(d["id"]):
                    rd = alb.get("release_date") or ""
                    if rd < cutoff or rd > datetime.now().strftime("%Y-%m-%d"):
                        continue
                    if alb.get("record_type") == "compile":
                        continue
                    out.append({
                        "artist": a["name"],
                        "title": alb["title"],
                        "release_date": rd,
                        "record_type": alb.get("record_type", ""),
                        "cover": alb.get("cover", ""),
                        "link": alb.get("link", ""),
                        "deezer_album_id": alb["id"],
                        "your_avg": round(a["avg"], 1),
                        "your_count": a["count"],
                    })
            self._save()
        out.sort(key=lambda r: r["release_date"], reverse=True)
        return {
            "days": days,
            "releases": out[:limit],
            "artists_checked": len(orbit),
            "network_error": self.last_network_error and not out,
            "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

    # ------------------------------------------------------------------
    # Feedback loop: did the picks we surfaced turn into songs you loved?
    # ------------------------------------------------------------------
    def _record(self, picks: List[dict], mode: str):
        if not picks:
            return
        changed = False
        today = datetime.now().strftime("%Y-%m-%d")
        for p in picks:
            sig = self.taste._normalize_sig(f"{p['artist']} {p['song']}")
            if sig not in self.log["picks"]:
                self.log["picks"][sig] = {"artist": p["artist"], "song": p["song"], "mode": mode, "first_seen": today}
                changed = True
        if changed:
            self._save_log()

    def stats(self) -> Dict:
        """Hit rate = surfaced picks that you later saved with a rating >= 80,
        over all surfaced picks you've rated at all. Broken down by mode so you
        can see whether 'hard' actually pays off for you."""
        by_mode = {m: {"surfaced": 0, "rated": 0, "hits": 0} for m in MODES}
        sig_to_rating = {}
        for r in self.taste.rated_entries:
            sig_to_rating[self.taste._normalize_sig(r.get("title") or "")] = int(r["rating"])
        for sig, p in self.log["picks"].items():
            m = p.get("mode", "easy")
            if m not in by_mode:
                continue
            by_mode[m]["surfaced"] += 1
            rating = sig_to_rating.get(sig)
            if rating is None:
                # Title may be stored "Song – Artist" or other order; try the reverse.
                rating = sig_to_rating.get(self.taste._normalize_sig(f"{p['song']} {p['artist']}"))
            if rating is not None:
                by_mode[m]["rated"] += 1
                if rating >= 80:
                    by_mode[m]["hits"] += 1
        total = {k: sum(v[k] for v in by_mode.values()) for k in ("surfaced", "rated", "hits")}
        total["hit_rate"] = round(100 * total["hits"] / total["rated"]) if total["rated"] else None
        for v in by_mode.values():
            v["hit_rate"] = round(100 * v["hits"] / v["rated"]) if v["rated"] else None
        return {"total": total, "by_mode": by_mode}
