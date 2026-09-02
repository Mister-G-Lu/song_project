#!/usr/bin/env python3
"""Seed remaining real artists from the unmapped list."""

import json
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

CACHE_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'artist_country_cache.json')

with open(CACHE_PATH, 'r', encoding='utf-8') as f:
    cache = json.load(f)

# Real artists identified from the unmapped list
new_artists = {
    # Multi-song artists (2+ songs)
    "Yu Peng Chen": "CN",
    "Nic Hanson": "US",
    "Auli'i Cravalho": "US",
    "The Cab": "US",
    "doddleoddle": "GB",
    "Joywave": "US",
    "Renee Rapp": "US",
    "Paradise Lost": "GB",
    
    # Single-song real artists
    "24kGoldin": "US",
    "4everfreebrony": "US",
    "AJ Raphael": "US",
    "AZEALIA BANKS": "US",
    "Aaliyah Rose": "US",
    "Addison Rae": "US",
    "Ahmir": "US",
    "Aimee Carty": "US",
    "Akira Yamaoka": "JP",
    "Akon": "US",
    "Alessia Nicole": "US",
    "Alice Cooper": "US",
    "Alice Kristiansen": "NO",
    "Alvaro Soler": "ES",
    "Amalee": "US",
    "Amalie": "US",
    "Ambrosia": "US",
    "American Authors": "US",
    "Amethyst Michelle": "US",
    "Andrea Chahayed": "US",
    "Angela Zhang": "TW",
    "Ashley Tisdale": "US",
    "2Wicky": "CH",
    "4realares": "BR",
    
    # More from the list
    "Potsu": "US",
    "Infected Mushroom": "IL",
    "Unica mulher": "AO",
    "Anselmo Ralph": "AO",
    "Adam Lambert": "US",
    "Jilian": "US",
    "Within Temptation": "NL",
    "Sam Tinnesz": "US",
    "FDVM": "FR",
    "Lenny Kravitz": "US",
    "Somo": "US",
    "Carly Rae Jepsen": "CA",
    "Monsune": "CA",
    "AOA": "KR",
    "Weslee": "GB",
    "Sigala": "GB",
    "Novo Amor": "GB",
    "Lion Babe": "US",
    "B.A.P": "KR",
    "EXO-K": "KR",
    "MOMOLAND": "KR",
    "Orange Caramel": "KR",
    "Girls' Generation": "KR",
    "Chase Holfelder": "US",
    "Kan Wakan": "US",
    "BYU Vocal Point": "US",
    "Foreign Hands": "US",
    "George Ogilvie": "GB",
    "Brian Crain": "US",
    "Philip Wesley": "US",
    "Casey Lee Williams": "US",
    "Philip Wesleys": "US",
    "Arash": "SE",
    "Nena": "DE",
    "ZZ Top": "US",
    "Panic! at the Disco": "US",
    "Demi Lovato": "US",
    "Michael Jackson": "US",
    "Taylor Swift": "US",
    "The Hush Sound": "US",
    "Dove Cameron": "US",
    "The Piano Guys": "US",
    "RuPaul": "US",
    "Brian Crain": "US",
    "The Myth": "CN",
    
    # From earlier single-song that are real
    "Johnathan Young": "US",
    "Auli'i Cravalho": "US",
    
    # Songs that are actually artist names
    "Silhouette": "JP",
    "Human": "US",
    "Wildfire": "US",
    "Closer": "US",
    "King": "US",
    "Stay": "US",
    "Faded": "NO",
    
    # From remaining list
    "4/16/18": "",
    "A Bailar Calypso": "",
    "A Good Song Never Dies": "",
    "A Little Messed Up": "",
    "A Whole New World": "",
    "AI Bob": "",
    "Absurd Matchups": "",
    "Abyssal Zone": "",
    "Aces": "",
    "Addis": "",
    "Age": "",
    "Allergies": "",
    "Almost Touch Me": "",
    "Ambiguous": "",
    "American Dream": "",
    "Another World": "",
    "Anybody But You": "",
    "Anything But This": "",
    "Aphrodite": "",
    "Apple Tree": "",
}

# Only add entries that aren't already in cache
added = 0
skipped = 0
for name, code in new_artists.items():
    if name not in cache:
        cache[name] = code
        added += 1
    else:
        skipped += 1

# Save
with open(CACHE_PATH, 'w', encoding='utf-8') as f:
    json.dump(cache, f, indent=2, ensure_ascii=False)

print(f"Added {added} new artist->country entries, skipped {skipped} already present")
print(f"Total cache entries: {len(cache)}")

# Quick coverage check
import csv
ci = {k.lower(): v for k, v in cache.items() if v}
total = 0
mapped = 0
with open(os.path.join(os.path.dirname(__file__), '..', 'data', 'posts_tails.csv'), 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        total += 1
        artist = (row.get('artist') or '').strip()
        if not artist:
            title = row.get('title', '')
            if ' - ' in title:
                artist = title.rsplit(' - ', 1)[1].strip()
            elif chr(0x2013) in title:
                artist = title.rsplit(chr(0x2013), 1)[1].strip()
        if artist:
            code = cache.get(artist, '') or ci.get(artist.lower(), '')
            if code:
                mapped += 1

print(f"Coverage: {mapped}/{total} ({100*mapped/total:.1f}%)")
