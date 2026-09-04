#!/usr/bin/env python3
"""Add missing favorite artist songs to the CSV database."""

import csv
import sys
from datetime import datetime, timedelta

CSV_PATH = 'data/posts_tails.csv'

# ---- HOYO-MIX songs (Genshin Impact / Honkai) ----
HOYO_SONGS = [
    ("Floating Life", "HOYO-MiX", 100),
    ("Nod-Krai", "HOYO-MiX", 90),
    ("La vaguelette", "HOYO-MiX", 80),
    ("Wildfire", "HOYO-MiX", 80),
    ("Moon Halo", "HOYO-MiX", 80),
    ("TruE", "HOYO-MiX", 80),
    ("Polumnia Omnia", "HOYO-MiX", 80),
    ("Samudrartha", "HOYO-MiX", 80),
    ("Blazing Heart", "HOYO-MiX", 80),
    ("Lullaby of the New Moon", "HOYO-MiX", 80),
    ("Dream Aria", "HOYO-MiX", 80),
    ("Genshin Impact Main Theme", "HOYO-MiX", 80),
    ("Hustle and Bustle of Ormos", "HOYO-MiX", 90),
    ("Sumeru", "HOYO-MiX", 90),
    ("Sumeru Night", "HOYO-MiX", 90),
    ("Sumeru Day", "HOYO-MiX", 90),
    ("Flares of the Blazing Sun", "HOYO-MiX", 90),
    ("Burning Desires", "HOYO-MiX", 80),
    ("If I Can Stop One Heart From Breaking", "HOYO-MiX", 80),
    ("Original Me", "HOYO-MiX", 80),
]

# ---- WILL WOOD songs ----
WILL_WOOD_SONGS = [
    ("Blue Velvet", "Will Wood", 100),
    ("I / Me / Myself", "Will Wood", 90),
    ("The Main Character", "Will Wood", 90),
    ("Laplace's Angel (Hurt People? Hurt People!)", "Will Wood", 90),
    ("Against the Kitchen Floor", "Will Wood", 90),
    ("2econd 2ight 2eer (that was fun, goodbye.)", "Will Wood", 90),
    ("Dr. Sunshine Is Dead", "Will Wood", 90),
    ("Hand Me My Shovel, I'm Going In!", "Will Wood", 90),
    ("6up 5oh Cop-Out (Pro / Con)", "Will Wood", 90),
    ("Suburbia Overture (Vampire Reference)", "Will Wood", 90),
    ("Tomcat Disposables", "Will Wood", 90),
    ("BlackboxWarrior - OK UFSL", "Will Wood", 90),
    ("Normal No More", "Will Wood", 90),
    ("Thermodynamic Lawyer, Esq, G.F.D.", "Will Wood", 90),
    ("Cotard's Solution (Anatta, Dukkha, Anicca)", "Will Wood", 90),
    ("Chemical Overreaction / Compound Fracture", "Will Wood", 90),
]

# ---- LAWRENCE songs (all 50 songs, rated 10/10) ----
LAWRENCE_SONGS = [
    # Breakfast (2016)
    ("Do You Wanna Do Nothing With Me?", "Lawrence", 100),
    ("Alibi", "Lawrence", 100),
    ("Play Around", "Lawrence", 100),
    ("Me & You", "Lawrence", 100),
    ("Where It Started From", "Lawrence", 100),
    ("Cold", "Lawrence", 100),
    ("Shot", "Lawrence", 100),
    ("Come On, Brother", "Lawrence", 100),
    ("Wash Away", "Lawrence", 100),
    ("Misty Morning", "Lawrence", 100),
    ("Superficial", "Lawrence", 100),
    ("Oh No", "Lawrence", 100),
    # Living Room (2018)
    ("More", "Lawrence", 100),
    ("Friend or Enemy", "Lawrence", 100),
    ("Whoever You Are", "Lawrence", 100),
    ("Make a Move", "Lawrence", 100),
    ("Try", "Lawrence", 100),
    ("The Heartburn Song", "Lawrence", 100),
    ("Almost Grown", "Lawrence", 100),
    ("Probably Up", "Lawrence", 100),
    ("Too Easy", "Lawrence", 100),
    ("Limbo", "Lawrence", 100),
    ("The Last Song", "Lawrence", 100),
    ("And Many More", "Lawrence", 100),
    # Hotel TV (2021)
    ("Don't Lose Sight", "Lawrence", 100),
    ("Hotel TV", "Lawrence", 100),
    ("Jet Lag", "Lawrence", 100),
    ("Casualty", "Lawrence", 100),
    ("Freckles", "Lawrence", 100),
    ("Thoughts from the ER (Silver Lining)", "Lawrence", 100),
    ("It's Not All About You", "Lawrence", 100),
    ("Don't Move", "Lawrence", 100),
    ("The Weather", "Lawrence", 100),
    ("False Alarms", "Lawrence", 100),
    ("Figure It Out (A Song Between Siblings)", "Lawrence", 100),
    # Family Business (2024)
    ("Whatcha Want", "Lawrence", 100),
    ("Guy I Used To Be", "Lawrence", 100),
    ("Do", "Lawrence", 100),
    ("Something In The Water", "Lawrence", 100),
    ("Hip Replacement", "Lawrence", 100),
    ("i'm confident that i'm insecure", "Lawrence", 100),
    ("Promotion", "Lawrence", 100),
    ("23", "Lawrence", 100),
    ("Circle Back", "Lawrence", 100),
    ("Death of Me", "Lawrence", 100),
    ("Funeral", "Lawrence", 100),
    ("Family Business", "Lawrence", 100),
    ("Conflict Resolution", "Lawrence", 100),
]


def get_existing_songs(csv_path):
    """Load existing songs to check for duplicates."""
    existing = set()
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            artist = (row.get('artist') or '').strip().lower()
            title = (row.get('title') or '').strip().lower()
            existing.add((artist, title))
    return existing


def add_songs(csv_path, songs):
    """Add songs to CSV. Skip if already exists."""
    existing = get_existing_songs(csv_path)
    added = 0
    skipped = 0

    # Read existing data
    rows = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            rows.append(row)

    # Add new rows
    today = datetime.now().strftime('%Y-%m-%d')
    for song_name, artist, rating in songs:
        # Check duplicate
        key = (artist.lower(), f"{song_name} ({artist})".lower())
        key2 = (artist.lower(), song_name.lower())
        if key in existing or key2 in existing:
            skipped += 1
            continue

        # Create title in "(Song (Artist))" format
        title = f"{song_name} ({artist})"

        row = {
            'date': today,
            'rating': str(rating),
            'title': title,
            'tail': '',
            'artist': artist,
            'song': song_name,
            'title_original': '',
            'title_english': '',
            'artist': artist,
            'song': song_name,
            'title_original': '',
            'title_english': '',
        }
        rows.append(row)
        existing.add((artist.lower(), title.lower()))
        added += 1

    # Write back
    with open(csv_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return added, skipped


if __name__ == '__main__':
    print("Adding Hoyo-Mix songs...")
    a, s = add_songs(CSV_PATH, HOYO_SONGS)
    print(f"  Added {a}, skipped {s}")

    print("Adding Will Wood songs...")
    a, s = add_songs(CSV_PATH, WILL_WOOD_SONGS)
    print(f"  Added {a}, skipped {s}")

    print("Adding Lawrence songs...")
    a, s = add_songs(CSV_PATH, LAWRENCE_SONGS)
    print(f"  Added {a}, skipped {s}")

    # Count totals
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        total = sum(1 for _ in f) - 1  # subtract header
    print(f"\nTotal songs in database: {total}")
