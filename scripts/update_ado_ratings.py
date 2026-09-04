#!/usr/bin/env python3
"""Update Ado song ratings per user's tier list."""

import csv
import sys
from datetime import datetime

CSV_PATH = 'data/posts_tails.csv'

# User's Ado tier list
ADO_SONGS = {
    # Favorites (100)
    'God-ish': 100,
    'Rebellion': 100,
    "I'm a Controversy": 100,
    'Odo': 100,
    'Ashura-chan': 100,
    'RuLe': 100,
    # Strong (85)
    'Elf': 85,
    'KokoroToIuNaNoFukakai': 85,
    'Darling Dance': 85,
    'Domestic de Violence': 85,
    'Himawari': 85,
    'Unravel': 85,
    'Readymade': 85,
    'Crime and Punishment': 85,
    # Average (70)
    'Fleeting Lullaby': 70,
    'Value': 70,
    'Shoka': 70,
    # Disliked (30)
    '0': 30,
    'Show': 30,
    'Usseewa': 30,
}

today = datetime.now().strftime('%Y-%m-%d')

# Read existing data
rows = []
updated = 0
added = 0

with open(CSV_PATH, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    for row in reader:
        a = row.get('artist', '').strip()
        if a == 'Ado':
            # Extract song name from title
            title = row.get('title', '')
            # Try to extract song name: "Ado – Song Name" or "【Ado】Song Name"
            song_name = None
            for song in ADO_SONGS:
                if song.lower() in title.lower():
                    song_name = song
                    break
            if song_name:
                old_rating = row.get('rating', '')
                new_rating = str(ADO_SONGS[song_name])
                if old_rating != new_rating:
                    row['rating'] = new_rating
                    updated += 1
                    print(f'  Updated: {song_name} {old_rating} -> {new_rating}')
        rows.append(row)

# Add missing songs
existing_songs = set()
for row in rows:
    if row.get('artist', '').strip() == 'Ado':
        title = row.get('title', '').lower()
        for song in ADO_SONGS:
            if song.lower() in title:
                existing_songs.add(song.lower())

for song_name, rating in ADO_SONGS.items():
    if song_name.lower() not in existing_songs:
        title = f"Ado – {song_name}"
        row = {
            'date': today,
            'rating': str(rating),
            'title': title,
            'tail': '',
            'artist': 'Ado',
            'song': song_name,
            'title_original': '',
            'title_english': '',
            'artist': 'Ado',
            'song': song_name,
            'title_original': '',
            'title_english': '',
        }
        rows.append(row)
        added += 1
        print(f'  Added: {song_name} at {rating}')

# Write back
with open(CSV_PATH, 'w', encoding='utf-8', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

print(f'\nUpdated {updated} existing songs, added {added} new songs')
print(f'Total Ado songs: {sum(1 for r in rows if r.get("artist","").strip() == "Ado")}')
