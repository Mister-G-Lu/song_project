"""
weekly_digest.py — Generate and email your weekly TasteScope digest.

Runs the same TasteEngine as the Flask app against data/posts_tails.csv,
builds a plain-text + HTML email of this week's discovery picks (with your
listened status) plus a few extra recommendations, and sends it via SMTP.

Designed to be scheduled from anywhere:
  - PythonAnywhere Scheduled Tasks (daily is fine — the script skips non-Monday
    by default, so a single free-tier daily task becomes a weekly digest)
  - cron-job.org / local cron / Windows Task Scheduler
  - GitHub Actions: on: schedule: - cron: '0 9 * * 1'

Config via env vars:
  SMTP_HOST   (default smtp.gmail.com)
  SMTP_PORT   (default 587)
  SMTP_USER   — authenticating account, also used as the From address
  SMTP_PASS   — app password (Gmail: Google Account → Security → App passwords)
  MAIL_TO     — recipient address (defaults to SMTP_USER)

Usage:
  python scripts/weekly_digest.py             # generate + send
  python scripts/weekly_digest.py --dry-run   # print the email, don't send
  python scripts/weekly_digest.py --picks 8   # include N weekly picks (default 5)
  python scripts/weekly_digest.py --anyday    # send even when it's not Monday
"""

import argparse
import json
import os
import smtplib
import sys
from datetime import date
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.taste_engine import TasteEngine  # noqa: E402

DIGEST_WEEKDAY = 0  # datetime.weekday(): Monday = 0
LISTENED_PATH = ROOT / "data" / "listened.json"
DEFAULT_CSV = ROOT / "data" / "posts_tails.csv"


def load_listened_sigs() -> set:
    """Normalized sigs of everything marked listened (best-effort)."""
    try:
        data = json.loads(LISTENED_PATH.read_text(encoding="utf-8"))
        store = data.get("listened", {}) if isinstance(data, dict) else {}
        return set(store.keys()) if isinstance(store, dict) else set()
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def spotify_url(artist: str, song: str) -> str:
    return f"https://open.spotify.com/search/{quote(f'{artist} {song}')}"


def _esc(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_digest(engine, picks_count: int = 5):
    """Build (subject, plain_text, html) for the weekly email."""
    listened = load_listened_sigs()
    week = engine.get_weekly_discovery()
    picks = week.get("picks", [])[:picks_count]

    def is_listened(p):
        return engine._normalize_sig(f"{p.get('artist', '')} {p.get('song', '')}") in listened

    flags = [is_listened(p) for p in picks]
    done = sum(1 for f in flags if f)
    unlistened = [p for p, f in zip(picks, flags) if not f]

    week_str = date.today().strftime("%b %d, %Y")
    subject = f"🎵 TasteScope Weekly — {week_str} ({done}/{len(picks)} picks listened)"

    # ---------------- Plain text ----------------
    lines = [
        f"Your TasteScope weekly digest for the week of {week_str}.",
        "",
        "=" * 56,
        "THIS WEEK'S PICKS",
        "=" * 56,
    ]
    for i, (p, flag) in enumerate(zip(picks, flags), 1):
        mark = "✅" if flag else "⬜"
        lines.append(f"{mark} {i}. {p['artist']} — {p['song']}")
        if p.get("reason"):
            lines.append(f"   {p['reason']}")
        lines.append(f"   {spotify_url(p['artist'], p['song'])}")
        lines.append("")

    if unlistened:
        lines.append("Still to listen:")
        lines.append("  " + ", ".join(f"{p['artist']} — {p['song']}" for p in unlistened))
        lines.append("")

    lines.append("=" * 56)
    lines.append("MORE RECOMMENDATIONS")
    lines.append("=" * 56)
    rec_count = 0
    for cat, cat_data in engine.get_recommendations().items():
        for rec in cat_data.get("recommendations", []):
            if rec_count >= 10:
                break
            mark = "✅" if is_listened(rec) else "⬜"
            lines.append(f"{mark} [{cat}] {rec['artist']} — {rec['song']}")
            if rec.get("reason"):
                lines.append(f"   {rec['reason']}")
            rec_count += 1
        if rec_count >= 10:
            break
    lines.append("")
    lines.append("— TasteScope, your personal music intelligence dashboard.")
    text = "\n".join(lines)

    # ---------------- HTML ----------------
    cards = ""
    for i, (p, flag) in enumerate(zip(picks, flags), 1):
        status = "✅ Listened" if flag else "⬜ Not listened yet"
        color = "#1db954" if flag else "#888"
        cards += (
            "<tr><td style='padding:12px 16px;border-bottom:1px solid #eee;'>"
            f"<div style='font-size:12px;color:#888;'>#{i} · {_esc(p.get('category', ''))}</div>"
            f"<div style='font-weight:600;font-size:15px;margin:4px 0;'>{_esc(p['artist'])} — “{_esc(p['song'])}”</div>"
            f"<div style='font-size:13px;color:#666;margin-bottom:6px;'>{_esc(p.get('reason', ''))}</div>"
            f"<a href='{spotify_url(p['artist'], p['song'])}' style='font-size:12px;color:#1db954;text-decoration:none;'>▶ Listen on Spotify</a>"
            f"<span style='font-size:12px;color:{color};margin-left:10px;'>{status}</span>"
            "</td></tr>"
        )

    remaining = ""
    if unlistened:
        remaining = (
            "<p style='font-size:13px;color:#666;'>Still to listen: "
            + ", ".join(f"<strong>{_esc(p['artist'])} — {_esc(p['song'])}</strong>" for p in unlistened)
            + "</p>"
        )

    html = (
        "<div style='font-family:Inter,Helvetica,Arial,sans-serif;max-width:600px;margin:0 auto;padding:24px;'>"
        f"<h2 style='margin:0 0 4px;'>🎵 TasteScope Weekly</h2>"
        f"<p style='margin:0 0 20px;color:#888;font-size:13px;'>Week of {week_str} · "
        f"<strong>{done}/{len(picks)}</strong> picks listened</p>"
        "<table style='width:100%;border-collapse:collapse;background:#fff;border:1px solid #eee;border-radius:8px;'>"
        f"{cards}</table>{remaining}"
        "<p style='font-size:12px;color:#aaa;margin-top:20px;'>— TasteScope, your personal music intelligence dashboard.</p>"
        "</div>"
    )

    return subject, text, html


def send_email(subject: str, text: str, html: str) -> None:
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER", "")
    password = os.environ.get("SMTP_PASS", "")
    mail_to = os.environ.get("MAIL_TO", "") or user

    if not user or not password or not mail_to:
        raise RuntimeError(
            "SMTP not configured. Set SMTP_USER, SMTP_PASS (and optionally "
            "SMTP_HOST / SMTP_PORT / MAIL_TO) env vars. Use --dry-run to "
            "preview the email without sending."
        )

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = mail_to
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")

    with smtplib.SMTP(host, port, timeout=30) as server:
        server.starttls()
        server.login(user, password)
        server.send_message(msg)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate & email the weekly TasteScope digest.")
    parser.add_argument("--dry-run", action="store_true", help="Print the email instead of sending")
    parser.add_argument("--picks", type=int, default=5, help="Number of weekly picks to include (default 5)")
    parser.add_argument("--anyday", action="store_true", help="Send even if today isn't the digest weekday")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    if not args.anyday and date.today().weekday() != DIGEST_WEEKDAY:
        print(f"Not the digest day (today is {date.today().strftime('%A')}); skipping. Use --anyday to force.")
        return

    engine = TasteEngine(str(DEFAULT_CSV))
    subject, text, html = build_digest(engine, picks_count=args.picks)

    if args.dry_run:
        print(subject)
        print("=" * len(subject))
        print(text)
        return

    send_email(subject, text, html)
    recipient = os.environ.get("MAIL_TO", "") or os.environ.get("SMTP_USER", "")
    print(f"Sent weekly digest to {recipient}: {subject}")


if __name__ == "__main__":
    main()
