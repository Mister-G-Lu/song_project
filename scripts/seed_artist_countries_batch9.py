#!/usr/bin/env python3
"""Batch 9: Seed remaining real artists from structured CSV."""

import json
import os

COUNTRY_MAP = {
    'Auli\'i Cravalho': 'US', 'The Smashing Pumpkins': 'US',
    'adele': 'GB', 'Marina & The Diamonds': 'GB',
    'Christina Perri ft. Ed Sheeran': 'US', 'Yandel ft. Daddy Yankee': 'PR',
    'Owl City ft. Carly Rae Jepsen': 'US', 'kyle xian': 'CA',
    'Voltaire': 'US', 'winky詩': 'JP', 'marie mai': 'CA',
    'Michelle Mclaughin': 'US', 'clocks and clouds': 'DE',
    'jon cozart': 'US', 'Hot Chelle Rae': 'US',
    'Colbie Caillat-Lucky': 'US', 'TryHardNinja': 'US',
    'RyanDan': 'CA', 'Neon Trees': 'US',
    'Idina Menzel': 'US', 'sting': 'GB', 'nf': 'US',
    'Gigi Lai': 'HK', 'The': 'US', 'Ice': 'US',
    'Jenny and Tyler': 'US', 'Ryan Gosling, Emma Stone)': 'US',
    'Grand/Fate/Order OP': 'JP', 'Yama — nemurumachi': 'JP',
    'VersaEmerge': 'US', 'Junky': 'JP',
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
