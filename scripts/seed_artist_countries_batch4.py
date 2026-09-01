#!/usr/bin/env python3
"""Batch 4: More known artists that need country codes."""

import json
import os

COUNTRY_MAP = {
    # More known artists from unmapped list
    '2Cellos': 'HR', 'A. Piazzolla': 'AR', 'Alcest': 'FR',
    'Alex & Sierra': 'US', 'Alexandra Stan': 'RO', 'Aloe Blacc': 'US',
    'Andra Day': 'US', 'Andrew Huang': 'CA', 'Andy Grammer': 'US',
    'Animenz': 'DE', 'Anoushka Shankar': 'IN', 'Anthem Lights': 'US',
    'Anouk': 'NL', 'Arash': 'SE', 'Ashe': 'US',
    'Art Blakey': 'US', 'Atlas Sound': 'US', 'Ava Nova': 'DE',
    'B.A.P.': 'KR', 'Bill Wurtz': 'US', 'Bea Miller': 'US',
    'Christina Perri': 'US', 'Faydee': 'AU', 'Marina': 'GR',
    'Olly Murs': 'UK', 'Shawn Mendes': 'CA', 'Camila Cabello': 'US',
    'Parov Stelar': 'AT', 'Sergey Lazarev': 'RU',
    'Måns Zelmerlöw': 'SE', 'Spice Girls': 'UK',
    'Walk the Moon': 'US', 'NateWantsToBattle': 'US',
    'Todrick Hall': 'US', 'Carrie Hope Fletcher': 'GB',
    'Zac Efron': 'US', 'Sammie': 'US',
    'Anthem Lights': 'US', 'V.K.': 'TW',
    'Daniel Bélanger': 'CA', 'Michael Bublé': 'CA',
    'Earth, Wind & Fire': 'US', 'Wakabayashi Mitsur': 'JP',
    'Baby Alice': 'FR', 'Elijah Bossenbroek': 'US',
    'Level 99 Games': 'US',
    'Anders Nilsen': 'NO', 'Archie': 'US',
    'ANTEMASQUE': 'US', 'BFA': 'US', 'BIGMAN': 'US',
    'BLOW': 'US', 'Adam Tell': 'US',
    'Air Afrique (Wind)': 'US', 'Aitana, Nicki Nicole': 'ES',
    'Alma Deutscher': 'GB', 'Alya': 'RU',
    'Angelika Vee': 'US', 'Annette Lee': 'US',
    'Arwen\'s Vigil': 'NZ',
    'Atomized': 'US', 'Austin and the Powers': 'US',
    'Ava Morse': 'US',
    'SAKURA-IRA': 'JP',
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
