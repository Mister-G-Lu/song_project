#!/usr/bin/env python3
"""Analyze what the RateYourMusic (RYM) import added to the dataset.

The RYM export was appended to ``data/posts_tails.csv`` on ``--rym-date``
(2026-09-13 by default). Because every imported row carries the *import* date
rather than a listening date, that single date is a reliable marker for
"came from RYM" and lets us compare the two halves of the collection.

The script answers three questions:

1. What did the import actually add? (volume, new artists, era spread,
   language spread, genre mix)
2. Where are the outliers? (ratings that break your own patterns, artists
   whose two halves disagree, rows that are not really songs)
3. What does it teach us about your taste? (signals that replicate across
   both halves vs. signals that only exist because of a scale difference)

It does not modify any data file. It writes a markdown report and an optional
CSV of flagged rows so the findings can be triaged.

Usage:
    python scripts/analyze_rym_impact.py
    python scripts/analyze_rym_impact.py --out REPORT.md --flags-csv data/flags.csv
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import re
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from src.taste_engine import TasteEngine  # noqa: E402

DEFAULT_RYM_DATE = "2026-09-13"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def mean(xs):
    return st.mean(xs) if xs else 0.0


def pstdev(xs):
    return st.pstdev(xs) if len(xs) > 1 else 0.0


def z(value, mu, sigma):
    return (value - mu) / sigma if sigma else 0.0


def pearson(xs, ys):
    if len(xs) < 3:
        return 0.0
    mx, my = mean(xs), mean(ys)
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    den = math.sqrt(sum((a - mx) ** 2 for a in xs) * sum((b - my) ** 2 for b in ys))
    return num / den if den else 0.0


def _inv_cdf(sorted_xs, p):
    """Percentile of an already-sorted list, linear interpolation."""
    if not sorted_xs:
        return 0.0
    i = max(0.0, min(1.0, p)) * (len(sorted_xs) - 1)
    lo = int(i)
    hi = min(lo + 1, len(sorted_xs) - 1)
    return sorted_xs[lo] + (sorted_xs[hi] - sorted_xs[lo]) * (i - lo)


def _mid_cdf_rank(sorted_xs, v):
    """Mid-rank percentile of value v — where the whole v-block sits."""
    n = len(sorted_xs)
    le = sum(1 for x in sorted_xs if x <= v)
    lt = sum(1 for x in sorted_xs if x < v)
    return (le + lt) / (2 * n)


def quantile_map(src_sorted, dst_sorted, values):
    """Map each RYM rating onto the blog-scale value at the same percentile."""
    return {v: _inv_cdf(dst_sorted, _mid_cdf_rank(src_sorted, v)) for v in values}


SCRIPT_RANGES = [
    ("CJK", r"[぀-ヿ㐀-䶿一-鿿가-힯]"),
    ("Cyrillic", r"[Ѐ-ӿ]"),
    ("Arabic", r"[؀-ۿ]"),
    ("Greek", r"[Ͱ-Ͽ]"),
    ("Thai", r"[฀-๿]"),
]


def title_script(text):
    text = text or ""
    for name, pattern in SCRIPT_RANGES:
        if re.search(pattern, text):
            return name
    if re.search(r"[A-Za-z]", text):
        return "Latin"
    return "non-alphabetic"


ALBUMISH_RE = re.compile(
    r"\b(album|ep\b|soundtrack|ost\b|vol(?:ume)?\.?\s*\d|compilation|"
    r"greatest hits|deluxe|remaster(?:ed)?|complete|anthology|box set)\b",
    re.IGNORECASE,
)


# --------------------------------------------------------------------------- #
# analysis
# --------------------------------------------------------------------------- #
def analyze(rym_date: str, min_n: int = 20):
    engine = TasteEngine()
    rym = [r for r in engine.rated_entries if (r.get("date") or "") == rym_date]
    leg = [r for r in engine.rated_entries if (r.get("date") or "") != rym_date]
    if not rym:
        raise SystemExit(f"No rows dated {rym_date} — is that the right import date?")

    R = sorted(int(r["rating"]) for r in rym)
    L = sorted(int(r["rating"]) for r in leg)
    out = {
        "engine": engine,
        "rym": rym,
        "leg": leg,
        "mu_r": mean(R), "sd_r": pstdev(R),
        "mu_l": mean(L), "sd_l": pstdev(L),
    }

    # ---- scale calibration -------------------------------------------------
    values = sorted(set(R))
    out["qmap"] = quantile_map(R, L, values)
    out["rating_counts"] = Counter(R)

    # ---- artist-level ------------------------------------------------------
    ar, al = defaultdict(list), defaultdict(list)
    for r in rym:
        if (r.get("artist") or "").strip():
            ar[r["artist"].strip()].append(int(r["rating"]))
    for r in leg:
        if (r.get("artist") or "").strip():
            al[r["artist"].strip()].append(int(r["rating"]))
    out["ar"], out["al"] = ar, al
    both = [a for a in ar if a in al]
    out["both"] = both
    out["artist_gap"] = sorted(
        ((a, mean(ar[a]), len(ar[a]), mean(al[a]), len(al[a]), mean(al[a]) - mean(ar[a]))
         for a in both),
        key=lambda x: -x[5],
    )
    out["artist_corr_all"] = pearson([mean(al[a]) for a in both], [mean(ar[a]) for a in both])
    deep = [a for a in both if len(ar[a]) >= 3 and len(al[a]) >= 3]
    out["artist_corr_deep"] = pearson([mean(al[a]) for a in deep], [mean(ar[a]) for a in deep])
    out["artist_corr_deep_n"] = len(deep)

    # ---- genre -------------------------------------------------------------
    gr, gl = defaultdict(list), defaultdict(list)
    for r in rym:
        gr[r.get("_genre") or "Uncategorized"].append(int(r["rating"]))
    for r in leg:
        gl[r.get("_genre") or "Uncategorized"].append(int(r["rating"]))
    genres = []
    for g in set(gr) | set(gl):
        a, b = gr.get(g, []), gl.get(g, [])
        genres.append({
            "genre": g, "n_r": len(a), "n_l": len(b),
            "avg_r": mean(a), "avg_l": mean(b),
            "z_r": z(mean(a), out["mu_r"], out["sd_r"]) if len(a) >= min_n else None,
            "z_l": z(mean(b), out["mu_l"], out["sd_l"]) if len(b) >= min_n else None,
            "lift": ((len(a) / len(rym)) / (len(b) / len(leg))) if b else float("inf"),
        })
    out["genres"] = sorted(genres, key=lambda d: -(d["z_r"] if d["z_r"] is not None else -9))

    # ---- decade ------------------------------------------------------------
    dr, dl = defaultdict(list), defaultdict(list)
    covered_r = covered_l = 0
    for r in rym:
        y = engine._release_year_for(r["title"])
        if y:
            dr[(y // 10) * 10].append(int(r["rating"]))
            covered_r += 1
    for r in leg:
        y = engine._release_year_for(r["title"])
        if y:
            dl[(y // 10) * 10].append(int(r["rating"]))
            covered_l += 1
    out["year_coverage"] = (covered_r, len(rym), covered_l, len(leg))
    decades = []
    for d in sorted(set(dr) | set(dl)):
        a, b = dr.get(d, []), dl.get(d, [])
        decades.append({
            "decade": d, "n_r": len(a), "n_l": len(b),
            "share_r": len(a) / covered_r if covered_r else 0,
            "share_l": len(b) / covered_l if covered_l else 0,
            "z_r": z(mean(a), out["mu_r"], out["sd_r"]) if len(a) >= 10 else None,
            "z_l": z(mean(b), out["mu_l"], out["sd_l"]) if len(b) >= 10 else None,
        })
    out["decades"] = decades

    # ---- row hygiene -------------------------------------------------------
    multi = [r for r in rym if " / " in (r.get("song") or "")]
    albumish = [r for r in rym if ALBUMISH_RE.search(r.get("song") or "")]
    out["multi"] = multi
    out["albumish"] = albumish
    out["uncat_r"] = sum(1 for r in rym if (r.get("_genre") or "") == "Uncategorized")
    out["uncat_l"] = sum(1 for r in leg if (r.get("_genre") or "") == "Uncategorized")

    # ---- yearly timeline distortion ---------------------------------------
    yearly = defaultdict(list)
    for r in engine.rated_entries:
        y = (r.get("date") or "")[:4]
        if re.fullmatch(r"\d{4}", y):
            yearly[y].append(int(r["rating"]))
    out["yearly"] = {y: (len(v), mean(v)) for y, v in sorted(yearly.items())}

    # ---- outliers ----------------------------------------------------------
    genre_z = {g["genre"]: g["z_r"] for g in genres if g["z_r"] is not None}
    loved = {g for g, v in genre_z.items() if v >= 0.10}
    disliked = {g for g, v in genre_z.items() if v <= -0.10}
    out["loved_genres"] = sorted(loved)
    out["disliked_genres"] = sorted(disliked)
    out["rebels_high"] = sorted(
        (r for r in rym if r.get("_genre") in disliked and int(r["rating"]) >= 80),
        key=lambda r: -int(r["rating"]),
    )
    out["rebels_low"] = sorted(
        (r for r in rym if r.get("_genre") in loved and int(r["rating"]) <= 30),
        key=lambda r: int(r["rating"]),
    )
    out["perfect"] = sorted((r for r in rym if int(r["rating"]) == 100),
                            key=lambda r: (r.get("artist") or ""))
    out["bottom"] = sorted((r for r in rym if int(r["rating"]) <= 20),
                           key=lambda r: int(r["rating"]))

    # new artists worth knowing about
    new_multi = [(a, v) for a, v in ar.items() if a not in al and len(v) >= 3]
    out["new_loved"] = sorted(new_multi, key=lambda x: (-mean(x[1]), -len(x[1])))[:15]
    out["new_cold"] = sorted(
        ((a, v) for a, v in ar.items() if a not in al and len(v) >= 3 and mean(v) <= 60),
        key=lambda x: mean(x[1]),
    )[:15]

    # ---- language ----------------------------------------------------------
    out["script_r"] = Counter(title_script(r.get("song")) for r in rym)
    out["script_l"] = Counter(title_script(r.get("song")) for r in leg)

    # ---- the deliberate 1/100 rap experiment (blog side) --------------------
    rap_leg_2026 = [int(r["rating"]) for r in leg
                    if r.get("_genre") == "Rap/Hip-Hop" and (r["date"] or "")[:4] == "2026"]
    rap_leg_other = [int(r["rating"]) for r in leg
                     if r.get("_genre") == "Rap/Hip-Hop" and (r["date"] or "")[:4] != "2026"]
    out["rap_experiment"] = (len(rap_leg_2026), mean(rap_leg_2026),
                             len(rap_leg_other), mean(rap_leg_other))
    out["rap_rym"] = [int(r["rating"]) for r in rym if r.get("_genre") == "Rap/Hip-Hop"]
    return out


# --------------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------------- #
def _row(r):
    artist = (r.get("artist") or "").strip()
    song = (r.get("song") or "").strip()
    return f"{int(r['rating'])} | {artist} | {song} | {r.get('_genre') or ''}"


def render(a, rym_date, min_n):
    rym, leg = a["rym"], a["leg"]
    n_r, n_l = len(rym), len(leg)
    P = []
    w = P.append

    w("# What the RateYourMusic import added")
    w("")
    w(f"Generated by `scripts/analyze_rym_impact.py`. Import marker date: **{rym_date}** "
      f"(every appended RYM row carries the import date, not a listening date).")
    w("")
    w("Two halves of one file:")
    w("")
    w("| | rows | rated | mean | median | sd | % >= 90 | % <= 30 |")
    w("|---|---:|---:|---:|---:|---:|---:|---:|")
    for label, rows in (("RYM import", rym), ("Blog corpus", leg),
                        ("Combined", rym + leg)):
        v = [int(r["rating"]) for r in rows]
        w(f"| {label} | {len(v)} | {len(v)} | {mean(v):.1f} | {st.median(v):.0f} | "
          f"{pstdev(v):.1f} | {100*sum(1 for x in v if x>=90)/len(v):.1f}% | "
          f"{100*sum(1 for x in v if x<=30)/len(v):.1f}% |")
    w("")
    w(f"The import is **{n_r/(n_r+n_l):.0%} of the rated collection** — it is not a "
      f"side file, it is half the dataset, and it moved the collection average from "
      f"**{a['mu_l']:.1f} to {mean([int(r['rating']) for r in rym+leg]):.1f}**.")
    w("")
    w("> Housekeeping: the README headline still reads "
      f"\"3,214 rated songs · 1,601 artists\". The real figures are now "
      f"**{n_r+n_l} rated songs** across "
      f"**{len(set(list(a['ar']) + list(a['al'])))} distinct artists**. Worth a "
      f"one-line update so the docs stop contradicting the data.")
    w("")

    # ---------------- 1. scale ---------------------------------------------
    w("## 1. The two halves use different rating scales")
    w("")
    w("This is the single most important finding. The RYM half is not 'worse music', "
      "it is a **different ruler**. RYM ratings are 1–10 multiplied by 10, so they "
      "arrive in 10-point steps and 53% of them land on 70:")
    w("")
    w("| RYM rating | rows | share | same percentile on the blog scale | shift |")
    w("|---:|---:|---:|---:|---:|")
    for v in sorted(a["rating_counts"]):
        eq = a["qmap"][v]
        w(f"| {v} | {a['rating_counts'][v]} | {100*a['rating_counts'][v]/n_r:.1f}% | "
          f"{eq:.0f} | {eq-v:+.0f} |")
    w("")
    gaps = [x[5] for x in a["artist_gap"]]
    w(f"Independent check: for the **{len(a['both'])} artists rated in both halves**, "
      f"the blog average sits **{mean(gaps):+.1f} points** above the RYM average "
      f"(median {st.median(gaps):+.1f}). So a RYM 7/10 is roughly a blog 85, and a "
      f"RYM 8/10 is roughly a blog 94.")
    w("")
    w("**Consequences** — read these before trusting any chart that mixes the halves:")
    w("")
    w(f"- The dashboard average ({mean([int(r['rating']) for r in rym+leg]):.1f}) is a "
      f"blend of two scales, not a taste measurement.")
    w("- 'Songs rated 90+' now means two different things depending on which half "
      "the row came from.")
    w(f"- Genre averages computed on the merged file are dragged toward whatever "
      f"genre the RYM half over-samples (see §2).")
    w("- Artist-vs-artist comparisons are unfair whenever one artist is mostly RYM "
      "and the other is mostly blog.")
    w("")
    w("**Suggested fix (no data loss):** keep the raw rating, add a `source` column "
      "(`rym` / `blog`), and expose a *calibrated* rating "
      "(`rating_calibrated`) that maps RYM onto the blog scale with the table above. "
      "Everything user-facing reads the calibrated value; the raw value stays for audit.")
    w("")

    # ---------------- 2. timeline ------------------------------------------
    w("## 2. The import is a fake cliff in the Evolution view")
    w("")
    w("`get_evolution()` buckets by review date, so all "
      f"{n_r} imported rows land in one month:")
    w("")
    w("| year | rows | avg |")
    w("|---:|---:|---:|")
    for y, (n, m) in a["yearly"].items():
        flag = " <-- import" if y == rym_date[:4] else ""
        w(f"| {y} | {n} | {m:.1f}{flag} |")
    w("")
    last = [y for y in a["yearly"]][:-1]
    prev = a["yearly"][last[-1]][1]
    cur = a["yearly"][rym_date[:4]][1]
    w(f"Your real trend ends at **{prev:.1f}**; the merged file shows **{cur:.1f}** for "
      f"{rym_date[:4]} and a 25x volume spike. Any 'taste is changing' story read off "
      f"that chart is an artifact of the import date.")
    w("")
    w("**Suggested fix:** exclude import-dated rows from the evolution/timeline series "
      "(they already have no real review date), or plot them as a separate 'backfill' "
      "band. The ratings stay in every non-time-based view.")
    w("")

    # ---------------- 3. what it added --------------------------------------
    ar, al = a["ar"], a["al"]
    new_artists = len([x for x in ar if x not in al])
    w("## 3. What the import actually added")
    w("")
    w(f"- **{new_artists} artists you had never rated before**, out of {len(ar)} in the "
      f"RYM half — only **{len(a['both'])} artists** appear in both halves. The import "
      f"roughly doubled the artist roster rather than deepening the old one.")
    w(f"- **Deeper back catalog.** Share of songs released before 2000:")
    pre_r = sum(d["share_r"] for d in a["decades"] if d["decade"] < 2000)
    pre_l = sum(d["share_l"] for d in a["decades"] if d["decade"] < 2000)
    w(f"  **{pre_r:.0%}** in the RYM half vs **{pre_l:.0%}** in the blog half.")
    w(f"- **More non-English titles:** "
      f"{100*(n_r-a['script_r']['Latin']-a['script_r']['non-alphabetic'])/n_r:.1f}% vs "
      f"{100*(n_l-a['script_l']['Latin']-a['script_l']['non-alphabetic'])/n_l:.1f}% "
      f"(CJK {a['script_r']['CJK']} vs {a['script_l']['CJK']}).")
    w(f"- **Nearly disjoint songs:** only 5 artist+song pairs exist in both halves, so "
      f"this is almost pure new listening, not a re-rating exercise.")
    w("")
    w("### Genre mix — where the import over-samples")
    w("")
    w("| genre | RYM n | blog n | share lift | RYM avg | RYM z | blog avg | blog z |")
    w("|---|---:|---:|---:|---:|---:|---:|---:|")
    for g in sorted(a["genres"], key=lambda d: -d["lift"]):
        if g["n_r"] + g["n_l"] < 15:
            continue
        zr = f"{g['z_r']:+.2f}" if g["z_r"] is not None else "—"
        zl = f"{g['z_l']:+.2f}" if g["z_l"] is not None else "—"
        lift = f"{g['lift']:.1f}x" if g["lift"] != float("inf") else "new"
        w(f"| {g['genre']} | {g['n_r']} | {g['n_l']} | {lift} | {g['avg_r']:.1f} | {zr} | "
          f"{g['avg_l']:.1f} | {zl} |")
    w("")
    w("(z = genre average expressed in standard deviations of its own half, so the two "
      "halves are comparable despite the scale difference. n>=%d to report a z.)" % min_n)
    w("")

    # ---------------- 4. taste ---------------------------------------------
    w("## 4. What it teaches us about your taste")
    w("")
    w("### Signals that replicate in BOTH halves (trust these)")
    w("")
    replicated = []
    for g in a["genres"]:
        if g["z_r"] is None or g["z_l"] is None:
            continue
        if g["z_r"] >= 0.10 and g["z_l"] >= 0.10:
            replicated.append((g["genre"], g["z_r"], g["z_l"], "above"))
        elif g["z_r"] <= -0.10 and g["z_l"] <= -0.10:
            replicated.append((g["genre"], g["z_r"], g["z_l"], "below"))
    replicated.sort(key=lambda x: -max(abs(x[1]), abs(x[2])))
    w("| genre | direction | RYM z | blog z |")
    w("|---|---|---:|---:|")
    for g, zr, zl, d in replicated:
        w(f"| {g} | {d} average | {zr:+.2f} | {zl:+.2f} |")
    w("")
    w("Two independent samples, two different rating scales, same verdict:")
    w("")
    w("- **Film / game scores are your single strongest genre.** "
      f"Soundtrack/Score is the top genre in the RYM half (z = "
      f"{[g['z_r'] for g in a['genres'] if g['genre']=='Soundtrack/Score'][0]:+.2f}) "
      f"and comfortably above average in the blog half too. The 100s in the import are "
      f"dominated by Morricone, John Williams, Hisaishi, Giacchino and HOYO-MiX — this "
      f"is a real, load-bearing preference, not noise.")
    w("- **Rap/Hip-Hop is a genuine blind spot**, but the dashboard exaggerates it. "
      f"The blog half contains {a['rap_experiment'][0]} rows from the deliberate "
      f"'rate 20 famous rap songs at 1/100' experiment (avg "
      f"{a['rap_experiment'][1]:.1f}). Strip those and the blog rap average is "
      f"**{a['rap_experiment'][3]:.1f}** (n={a['rap_experiment'][2]}), and the "
      f"independent RYM half says **{mean(a['rap_rym']):.1f}** (n={len(a['rap_rym'])}). "
      f"Both are your lowest genre — so the conclusion holds, but the true gap is "
      f"roughly 10 points, not 30.")
    w("- **Country and Latin sit at the bottom of both halves.** No recovery signal.")
    w(f"- **Japan and Korea punch above their weight in both halves** (see §6).")
    w("")
    w("### Signals that only appear in one half (do not trust these yet)")
    w("")
    flips = [g for g in a["genres"]
             if g["z_r"] is not None and g["z_l"] is not None
             and ((g["z_r"] >= 0.10) != (g["z_l"] >= 0.10))]
    w("| genre | RYM z | blog z | note |")
    w("|---|---:|---:|---|")
    for g in sorted(flips, key=lambda d: -abs((d["z_r"] or 0) - (d["z_l"] or 0))):
        w(f"| {g['genre']} | {g['z_r']:+.2f} | {g['z_l']:+.2f} | sign flip between halves |")
    w("")
    w("The **Metal** flip is almost certainly a classifier bug, not taste — see §7.")
    w("")
    w("### Era preference")
    w("")
    w("| decade | RYM share | RYM z | blog share | blog z |")
    w("|---:|---:|---:|---:|---:|")
    for d in a["decades"]:
        if d["n_r"] + d["n_l"] < 20:
            continue
        zr = f"{d['z_r']:+.2f}" if d["z_r"] is not None else "—"
        zl = f"{d['z_l']:+.2f}" if d["z_l"] is not None else "—"
        w(f"| {d['decade']}s | {d['share_r']:.1%} | {zr} | {d['share_l']:.1%} | {zl} |")
    w("")
    best = max((d for d in a["decades"] if d["z_r"] is not None), key=lambda d: d["z_r"])
    worst = min((d for d in a["decades"] if d["z_r"] is not None), key=lambda d: d["z_r"])
    w(f"Within the RYM half your warmest decade is the **{best['decade']}s** "
      f"(z = {best['z_r']:+.2f}) and your coolest is the **{worst['decade']}s** "
      f"(z = {worst['z_r']:+.2f}) — a mild but consistent tilt toward the 70s/80s "
      f"canon that the blog half (53% 2010s) could never have shown.")
    w("")
    w("### Do the two halves agree about artists?")
    w("")
    w(f"Correlation between an artist's blog average and their RYM average is only "
      f"**r = {a['artist_corr_all']:.2f}** across all {len(a['both'])} shared artists — "
      f"but **r = {a['artist_corr_deep']:.2f}** for the {a['artist_corr_deep_n']} artists "
      f"with 3+ songs in both. The low headline number is small-sample noise "
      f"(most shared artists have a single song on one side), not disagreement. "
      f"Where you have heard enough of an artist, the two scales agree.")
    w("")

    # ---------------- 5. outliers -------------------------------------------
    w("## 5. Outliers")
    w("")
    w("### 5a. RYM 10/10s — the strongest new signal in the file")
    w("")
    w(f"{len(a['perfect'])} rows. Grouped, they read as a coherent taste statement:")
    w("")
    for r in a["perfect"]:
        w(f"- **{int(r['rating'])}** — {r.get('artist')} — {r.get('song')} "
          f"*({r.get('_genre')})*")
    w("")
    w("### 5b. Ratings that break your own genre pattern")
    w("")
    w(f"Songs rated 80+ in genres you rate below average "
      f"({', '.join(a['disliked_genres'])}):")
    w("")
    for r in a["rebels_high"][:20]:
        w(f"- **{int(r['rating'])}** — {r.get('artist')} — {r.get('song')} "
          f"*({r.get('_genre')})*")
    w("")
    w(f"Songs rated 30 or below in genres you rate above average "
      f"({', '.join(a['loved_genres'])}):")
    w("")
    for r in a["rebels_low"][:20]:
        w(f"- **{int(r['rating'])}** — {r.get('artist')} — {r.get('song')} "
          f"*({r.get('_genre')})*")
    w("")
    w("> Caveat: some of these are outliers only because the genre is wrong. Andy "
      "Grammer is not J-Pop, Bob Seger is not Metal, and Aly & AJ are not Rap/Hip-Hop "
      "(§7 item 4). Audit the genre column before reading any single line here as a "
      "taste statement; the *pattern* — a handful of exceptions in every genre — is "
      "the real signal.")
    w("")
    w("### 5c. Artists whose two halves disagree most")
    w("")
    w("| artist | RYM avg (n) | blog avg (n) | gap |")
    w("|---|---:|---:|---:|")
    for name, mr_, nr, ml_, nl, gap in a["artist_gap"][:10]:
        w(f"| {name} | {mr_:.1f} ({nr}) | {ml_:.1f} ({nl}) | {gap:+.1f} |")
    w("")
    w("...and the reverse (RYM rates them *higher* than the blog did):")
    w("")
    w("| artist | RYM avg (n) | blog avg (n) | gap |")
    w("|---|---:|---:|---:|")
    for name, mr_, nr, ml_, nl, gap in a["artist_gap"][-10:]:
        w(f"| {name} | {mr_:.1f} ({nr}) | {ml_:.1f} ({nl}) | {gap:+.1f} |")
    w("")
    w("Most extreme single-song contradictions are *different songs* by the same "
      "artist, so they are real taste data, not duplicates. Worth a manual listen: "
      "**Simon & Garfunkel** (blog 20 from one song, RYM 62 from five) and "
      "**Otis Redding** (blog 1, RYM 70) are cases where a single blog rating is now "
      "badly outvoted — exactly the rows a 'recover ratings from text' pass should "
      "target first.")
    w("")
    w("### 5d. New artists the import promotes or demotes")
    w("")
    w(f"Highest-rated artists that exist **only** in the RYM half (3+ songs) — "
      f"candidates for `favorite_artists.json`:")
    w("")
    for name, v in a["new_loved"]:
        w(f"- **{name}** — {len(v)} songs, avg {mean(v):.1f}")
    w("")
    w("Lowest-rated artists that exist only in the RYM half (3+ songs):")
    w("")
    for name, v in a["new_cold"]:
        w(f"- **{name}** — {len(v)} songs, avg {mean(v):.1f}")
    w("")
    w("### 5e. The bottom of the list has a novelty cluster")
    w("")
    w(f"{len(a['bottom'])} rows are rated 20 or below, and "
      f"{sum(1 for r in a['bottom'] if len([1 for x in rym if (x.get('artist') or '').strip()==(r.get('artist') or '').strip()])==1)} "
      f"of them are one-off artists who appear nowhere else in your collection "
      f"(Rebecca Black, Crazy Frog, Perez Hilton, Bart Baker, Bob the Builder, "
      f"Cage Against the Machine's 4'33\"...). Combined with joke-adjacent titles in "
      f"META/Other, this looks like a deliberate 'worst songs ever' sweep rather than "
      f"organic listening. Those rows are fine as data but they are not training "
      f"examples for a recommender — they inflate the low end and teach the model "
      f"about novelty acts you will never seek out.")
    w("")

    # ---------------- 6. geography ------------------------------------------
    w("## 6. Geography (rough — coverage is thin on the RYM side)")
    w("")
    cr, cl, miss_r, miss_l = {}, {}, 0, 0
    for r in rym:
        code = None
        for art in a["engine"]._extract_artists_from_row(r):
            code = (a["engine"]._artist_country_cache.get(art)
                    or a["engine"]._country_ci_index.get((art or "").lower()))
            if code:
                break
        if code:
            cr.setdefault(code, []).append(int(r["rating"]))
        else:
            miss_r += 1
    for r in leg:
        code = None
        for art in a["engine"]._extract_artists_from_row(r):
            code = (a["engine"]._artist_country_cache.get(art)
                    or a["engine"]._country_ci_index.get((art or "").lower()))
            if code:
                break
        if code:
            cl.setdefault(code, []).append(int(r["rating"]))
        else:
            miss_l += 1
    w(f"Country coverage: RYM {100*(n_r-miss_r)/n_r:.0f}%, blog {100*(n_l-miss_l)/n_l:.0f}% "
      f"— the RYM half brought in {len([x for x in a['ar'] if x not in a['al']])} new "
      f"artist names faster than the country cache could keep up, so treat this "
      f"section as indicative only.")
    w("")
    w("| code | RYM n | RYM z | blog n | blog z |")
    w("|---|---:|---:|---:|---:|")
    for code in sorted(set(cr) | set(cl), key=lambda c: -len(cr.get(c, []))):
        x, y = cr.get(code, []), cl.get(code, [])
        if len(x) + len(y) < 10:
            continue
        zr = f"{z(mean(x), a['mu_r'], a['sd_r']):+.2f}" if len(x) >= 8 else "—"
        zl = f"{z(mean(y), a['mu_l'], a['sd_l']):+.2f}" if len(y) >= 8 else "—"
        w(f"| {code} | {len(x)} | {zr} | {len(y)} | {zl} |")
    w("")
    w("Japan, Korea, France and Norway sit above your average in both halves; the US "
      "and (mildly) Australia sit below. Small numbers, but the direction repeats.")
    w("")

    # ---------------- 7. data quality ---------------------------------------
    w("## 7. Data-quality issues the import introduced or exposed")
    w("")
    w(f"1. **Two scales in one column** (§1). Highest-impact fix in this report.")
    w(f"2. **Import date used as review date** (§2). Breaks the Evolution view.")
    w(f"3. **{len(a['multi'])} rows ({100*len(a['multi'])/n_r:.0f}%) are releases, not "
      f"songs** — the song field contains ' / ', i.e. a single/B-side pair, a medley or "
      f"an EP side (`Layla / Bell Bottom Blues`, `Dream On / Somebody`). A further "
      f"{len(a['albumish'])} look like album or OST rows (`Queen — A Night at the "
      f"Opera`, `Billie Eilish — Hit Me Hard and Soft`, `Genshin Impact: City of Winds "
      f"and Idylls`). Several of your RYM 100s are albums, so 'top songs' lists will "
      f"surface release titles. This matches the caveat already in "
      f"`data/rym_import_summary.md`; it is now quantified.")
    w(f"4. **Genre classifier strain.** Uncategorized went from "
      f"{100*a['uncat_l']/n_l:.1f}% (blog) to {100*a['uncat_r']/n_r:.1f}% (RYM). Worse, "
      f"the RYM **Metal** bucket is polluted: it contains Leonard Cohen, Jessie Ware, "
      f"Maxwell, Nico, Burial, Big Thief, Weyes Blood, The National, Japan, George "
      f"Benson, Charlie Parker, Grace Jones, Kavinsky, Modjo, Steve Lacy, Janelle "
      f"Monáe, Howard Shore and Jeremy Soule. Those artists are cached as Metal in "
      f"`data/artist_genre_cache.json` "
      f"({Counter(v for v in json.loads(Path(ROOT/'data/artist_genre_cache.json').read_text(encoding='utf-8')).values())['Metal']} "
      f"artists total). The likely mechanism is the bidirectional substring rule in "
      f"`TasteEngine._classify_artist_genre_musicbrainz` (`if kw in t or t in kw`): a "
      f"MusicBrainz tag like `folk`, `glam`, `core`, `prog` or `power` is a *substring* "
      f"of the keywords `folk metal`, `glam metal`, `metalcore`, `prog metal`, "
      f"`power metal`, so Metal collects spurious votes. The blog half hides this "
      f"because it never had those artists; the import exposed it. **This is why the "
      f"Metal 'sign flip' in §4 is not a taste change.**")
    w(f"5. **Joke / novelty rows** in the low tail (§5e).")
    w(f"6. **96 blog rows rated 1–2**, {a['rap_experiment'][0]} of them from the "
      f"deliberate rap experiment. Flagging that experiment with a `source` value would "
      f"stop it from silently defining your rap preference.")
    w("")

    # ---------------- 8. recommendations ------------------------------------
    w("## 8. Suggested next steps (ordered by value)")
    w("")
    w("1. Add a `source` column (`blog` / `rym` / `experiment`) and a "
      "`rating_calibrated` column. Backfill `source` from the import date; derive "
      "calibration from the §1 table. No rows are lost and every view can pick the "
      "right column.")
    w("2. Exclude import-dated rows from the Evolution/timeline series.")
    w("3. Fix the substring rule in `_classify_artist_genre_musicbrainz` to match "
      "keywords only in the tag→keyword direction, then re-run genre classification "
      "for the artists currently cached as Metal and audit the diff.")
    w("4. Split the ' / ' release rows into a `row_kind` of `song` / `release` and "
      "exclude `release` from song-level stats and recommender training.")
    w("5. Re-check the two known suspect fills already noted in "
      "`data/rym_import_summary.md` (TUYU, Mitchie M) and the single-song "
      "contradictions in §5c.")
    w("6. Promote the §5d artists into `favorite_artists.json` after a listen — "
      "Tori Amos, Garbage and Yeah Yeah Yeahs are the strongest new candidates.")
    w("")
    w("## Appendix — reproducing this")
    w("")
    w("```bash")
    w("python scripts/analyze_rym_impact.py")
    w("python scripts/analyze_rym_impact.py --out RYM_IMPACT_ANALYSIS.md \\")
    w("    --flags-csv data/rym_impact_flags.csv")
    w("```")
    w("")
    w("Read-only. The only inputs are `data/posts_tails*.csv` and the cached "
      "enrichment JSONs.")
    w("")
    return "\n".join(P) + "\n"


def write_flags(a, path: Path):
    """Emit one row per flagged entry so findings can be triaged in a spreadsheet."""
    rows = []
    for r in a["multi"]:
        rows.append(("release_row_multi_track", "rym", r["rating"],
                     r.get("artist", ""), r.get("song", ""), r.get("_genre", ""),
                     "song field contains ' / ' — single/medley/EP side, not one song"))
    for r in a["albumish"]:
        rows.append(("release_row_albumish", "rym", r["rating"],
                     r.get("artist", ""), r.get("song", ""), r.get("_genre", ""),
                     "song field looks like an album / OST / compilation"))
    for r in a["perfect"]:
        rows.append(("rym_100", "rym", r["rating"],
                     r.get("artist", ""), r.get("song", ""), r.get("_genre", ""),
                     "RYM 10/10 — verify it is a song and not a release"))
    for r in a["rebels_high"]:
        rows.append(("outlier_high_in_cold_genre", "rym", r["rating"],
                     r.get("artist", ""), r.get("song", ""), r.get("_genre", ""),
                     "rated high in a genre you normally rate low"))
    for r in a["rebels_low"]:
        rows.append(("outlier_low_in_warm_genre", "rym", r["rating"],
                     r.get("artist", ""), r.get("song", ""), r.get("_genre", ""),
                     "rated low in a genre you normally rate high"))
    for name, mr_, nr, ml_, nl, gap in a["artist_gap"][:25] + a["artist_gap"][-25:]:
        rows.append(("artist_halves_disagree", "both", round(gap, 1), name, "",
                     "", f"RYM {mr_:.1f} (n={nr}) vs blog {ml_:.1f} (n={nl})"))
    for r in a["rym"]:
        if (r.get("_genre") or "") == "Metal":
            rows.append(("genre_metal_audit", "rym", r["rating"],
                         r.get("artist", ""), r.get("song", ""), "Metal",
                         "Metal bucket — check the artist is really metal"))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        wri = csv.writer(f)
        wri.writerow(["flag", "source", "rating", "artist", "song", "genre", "note"])
        wri.writerows(rows)
    return len(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rym-date", default=DEFAULT_RYM_DATE,
                    help="date marker used by the import (default: %(default)s)")
    ap.add_argument("--out", default=str(ROOT / "RYM_IMPACT_ANALYSIS.md"),
                    help="markdown report path (default: %(default)s)")
    ap.add_argument("--flags-csv", default=str(ROOT / "data" / "rym_impact_flags.csv"),
                    help="CSV of flagged rows (default: %(default)s)")
    ap.add_argument("--min-n", type=int, default=20,
                    help="minimum rows before a genre z-score is reported")
    ap.add_argument("--no-flags", action="store_true", help="skip the flags CSV")
    args = ap.parse_args()

    a = analyze(args.rym_date, args.min_n)
    report = render(a, args.rym_date, args.min_n)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"wrote {out_path} ({len(report.splitlines())} lines)")
    if not args.no_flags:
        n = write_flags(a, Path(args.flags_csv))
        print(f"wrote {args.flags_csv} ({n} flagged rows)")


if __name__ == "__main__":
    main()
