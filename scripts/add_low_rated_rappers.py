#!/usr/bin/env python3
"""Add top-20 famous songs for Playboi Carti, Young Thug, Lil Yachty, Lil Uzi Vert
rated at the lowest possible score (1/100), then re-snapshot recommendations.

Track lists follow Spotify all-time stream counts (kworb.net, 2026-09-04) and
only include tracks where the artist is the LEAD artist (no pure features, so
ownership/genre attribution stays clean).
"""

import csv
import sys
from datetime import datetime

CSV_PATH = 'data/posts_tails.csv'

ARTISTS = [
    ("Playboi Carti", [
        "Magnolia",
        "Sky",
        "Shoota (feat. Lil Uzi Vert)",
        "Location",
        "wokeuplikethis* (feat. Lil Uzi Vert)",
        "ILoveUIHateU",
        "Fell In Luv (feat. Bryson Tiller)",
        "R.I.P.",
        "Long Time - Intro",
        "Vamp Anthem",
        "Foreign",
        "EVIL J0RDAN",
        "New Tank",
        "Stop Breathing",
        "FlatBed Freestyle",
        "Flex",
        "Rockstar Made",
        "Love Hurts (feat. Travis Scott)",
        "New Choppa",
        "On That Time",
    ]),
    ("Young Thug", [
        "Go Crazy (with Chris Brown)",
        "The London (feat. J. Cole & Travis Scott)",
        "pick up the phone (feat. Quavo)",
        "Hot (Remix) [feat. Gunna and Travis Scott]",
        "Relationship (feat. Future)",
        "Bad Bad Bad (feat. Lil Baby)",
        "Hot (feat. Gunna)",
        "Digits",
        "Wyclef Jean",
        "Chanel (Go Get It) [feat. Gunna & Lil Baby]",
        "Check",
        "Best Friend",
        "Oh U Went (feat. Drake)",
        "Livin It Up (with Post Malone & A$AP Rocky)",
        "Sin (feat. Jaden Smith)",
        "With Them",
        "Halftime",
        "High (feat. Elton John)",
        "Stoner",
        "Killed Before",
    ]),
    ("Lil Yachty", [
        "One Night",
        "Yacht Club (feat. Juice WRLD)",
        "NBAYOUNGBOAT",
        "Flex Up (feat. Future & Playboi Carti)",
        "Oprah's Bank Account (feat. DaBaby & Drake)",
        "Coffin",
        "Pardon Me (feat. Future & Mike WiLL Made-It)",
        "66",
        "Poland",
        "Get Dripped (feat. Playboi Carti)",
        "A Cold Sunday",
        "Strike (Holster)",
        "Peek A Boo",
        "Minnesota",
        "T.D (feat. Tierra Whack, A$AP Rocky & Tyler, The Creator)",
        "Hate Me",
        "SOLO STEPPIN CRETE BOY",
        "Split/Whole Time",
        "MICKEY",
        "Sorry Not Sorry",
    ]),
    ("Lil Uzi Vert", [
        "XO Tour Llif3",
        "20 Min",
        "The Way Life Goes (feat. Oh Wonder)",
        "Just Wanna Rock",
        "Money Longer",
        "Erase Your Social",
        "Sanguine Paradise",
        "You Was Right",
        "Myron",
        "Sauce It Up",
        "Neon Guts (feat. Pharrell Williams)",
        "Futsal Shuffle 2020",
        "P2",
        "Homecoming",
        "That Way",
        "New Patek",
        "7AM",
        "Do What I Want",
        "Dark Queen",
        "Ps & Qs",
    ]),
]

RATING = 1  # lowest score in the existing data


def main():
    existing = set()
    rows = []
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            rows.append(row)
            a = (row.get('artist') or '').strip().lower()
            s = (row.get('song') or row.get('title') or '').strip().lower()
            t = (row.get('title') or '').strip().lower()
            existing.add((a, s))
            existing.add((a, t))

    today = datetime.now().strftime('%Y-%m-%d')
    added = 0
    skipped = 0
    for artist, songs in ARTISTS:
        for song in songs:
            key = (artist.lower(), song.lower())
            # also fuzzy check: any existing row where artist matches and the
            # title contains the song's core words
            dup = key in existing
            if not dup:
                for (ea, es) in existing:
                    if ea == artist.lower() and song.lower() in es:
                        dup = True
                        break
            if dup:
                skipped += 1
                print(f'  SKIP (exists): {artist} - {song}')
                continue
            title = f'{song} ({artist})'
            row = {
                'date': today,
                'rating': str(RATING),
                'title': title,
                'tail': 'Low personal taste',
                'artist': artist,
                'song': song,
                'title_original': '',
                'title_english': '',
            }
            rows.append(row)
            existing.add((artist.lower(), song.lower()))
            added += 1

    with open(CSV_PATH, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f'\nAdded {added}, skipped {skipped}')
    print(f'Total rows: {len(rows)}')
    # per-artist count
    from collections import Counter
    c = Counter()
    for r in rows:
        a = (r.get('artist') or '').strip()
        for artist, _ in ARTISTS:
            if a == artist:
                c[artist] += 1
    for artist, _ in ARTISTS:
        print(f'  {artist}: {c[artist]} songs total')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
