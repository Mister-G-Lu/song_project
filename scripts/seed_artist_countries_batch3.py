#!/usr/bin/env python3
"""Batch 3: Seed remaining real unmapped artists with country codes."""

import json
import os

COUNTRY_MAP = {
    # US
    'AKA George': 'US', 'Alice Chater': 'UK', 'All Levels at Once': 'US',
    'All Time Low': 'US', "Ariana Grande & Justin Bieber": 'US',
    "Auli'i Cravalho": 'US', 'Ava Max': 'US', 'Aviators': 'US',
    'Before You Exit': 'US', 'Beth Crowley': 'US', 'Beyoncé': 'US',
    'Billy Joel': 'US', 'Black Violin': 'US', 'Break Of Reality': 'US',
    'Break of Reality': 'US', 'Brett Domino': 'US', 'Brittney Spears': 'US',
    'Bruce Springsteen': 'US', 'Caravan Palace': 'FR',
    'Christina Aguilera': 'US', 'David Choi': 'US', 'Dazbee': 'JP',
    'Dolvondo': 'US', 'Earth, Wind and Fire': 'US', 'Ellie Goulding': 'UK',
    'End of Silence': 'US', 'FDVM': 'FR', 'Faouzia': 'CA',
    'Feeder': 'UK', 'Fonzi M': 'US', 'Giovanni Allevi': 'IT',
    'Hagali': 'US', 'Illenium': 'US', 'Infected mushroom': 'IL',
    'Ivy Levan': 'US', 'Jake Manisto': 'US', 'Jessie Ware': 'UK',
    'Jhené Aiko': 'US', 'Jikky Bytt': 'JP', 'Johnathan Young': 'US',
    'Kambido': 'US', 'Kokia': 'JP', 'Krewella': 'US',
    'Loreen': 'SE', 'Lynyrd Skynyrd': 'US', 'LÉON': 'SE',
    'M2U': 'KR', 'Martina McBride': 'US', 'Massive Attack': 'UK',
    'Melanie Martinez': 'US', 'Michael Bublé': 'CA',
    'Michele Mclaughin': 'US', 'Monstaz': 'US', 'Monsune': 'US',
    'Mori Calliope': 'JP', 'My': 'US', 'Nurmat Sadyrov': 'KZ',
    'Olly Murs': 'UK', 'Panic! at the Disco': 'US',
    'Paul McCartney': 'UK', 'Perfume Genius': 'US',
    'Philip Wesley': 'US', 'Plumb': 'US', 'Rachel Platten': 'US',
    'Rafferty': 'UK', 'Rebecca Black': 'US', 'Red': 'US',
    'Rixton': 'UK', 'Rosendale': 'US', 'Seal': 'UK',
    'Set it Off': 'US', 'Simply Three': 'US',
    'Smash Into Pieces': 'SE', 'Stellar': 'KR',
    'Swingrowers': 'IT', 'TLC': 'US', 'Taio Cruz': 'UK',
    'The Chipmunks': 'US', 'The Clash': 'UK',
    'The Glitch Mob': 'US', 'Tobacco': 'US',
    'Tom Cochrane': 'CA', 'Victoria Monét': 'US',
    'Victorious': 'US', 'XXXtenation': 'US',
    'Yohanna': 'IS', 'Young Stoner Life': 'US',
    'Yung Zel': 'US', 'cloudfield': 'DE', 'mr. chris': 'US',
    'Aimee Mann': 'US', 'ALSTROeMERIA': 'JP',
    'BEAST IN BLACK': 'FI', 'BEASTARS': 'JP',
    'BTOB (비투비)': 'KR', 'Carole and Tuesday': 'JP',
    'CircusP': 'JP', 'Daniel Bélanger': 'CA',
    'Eve': 'JP', 'Imy': 'JP', 'Incantation': 'US',
    'Kimi no nawa': 'JP', 'Alice Merton': 'DE',
}

CACHE_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'artist_country_cache.json')

def main():
    cache = json.load(open(CACHE_PATH, 'r', encoding='utf-8'))
    added = 0
    for artist, code in COUNTRY_MAP.items():
        if artist not in cache or not cache[artist]:
            cache[artist] = code
            added += 1

    with open(CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)

    mapped = sum(1 for v in cache.values() if v)
    print(f"Added {added} new mappings")
    print(f"Total cached: {len(cache)}")
    print(f"With country: {mapped}")

if __name__ == '__main__':
    main()
