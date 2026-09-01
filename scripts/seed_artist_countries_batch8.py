#!/usr/bin/env python3
"""Batch 8: Seed artists identified from unmapped title analysis."""

import json
import os

COUNTRY_MAP = {
    'Tonight Alive': 'AU', 'Manian': 'DE', 'Cello Fury': 'US',
    'David Eman': 'US', "Storm's End": 'US', 'IU(아이유)': 'KR',
    'IU': 'KR', 'Marta Jandová & Václav Noid Bárta': 'CZ',
    'Katy Sky': 'US', 'Timeflies': 'US',
    'Callysta': 'FR', 'Marie Mai': 'CA', 'Cody Simpson': 'AU',
    'Carrie Hope Fletcher': 'GB', 'Jeff Williams': 'US',
    'Thomas Sanders': 'US', 'Taylor Davis': 'US',
    'Brain Crain': 'US', 'Pharrell Williams': 'US',
    'Lady Gaga': 'US', 'Beyonce': 'US', 'Ed Sheeran': 'GB',
    'Lindsey Stirling': 'US', 'William Joseph': 'US',
    'Hailee Steinfeld': 'US', 'The Piano Guys': 'US',
    'Vanilla Twilight': 'US', 'Mastiksoul': 'PT',
    'Amanda Wilson': 'GB', 'Ebbyman': 'US',
    'Kara No Kokoro': 'JP',
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
