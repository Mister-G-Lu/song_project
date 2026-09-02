#!/usr/bin/env python3
"""Split collaboration artists and add each individually to the country cache."""

import json
import os

# Split collaborations into individual artists
COLLAB_SPLITS = {
    # Original collab -> [(artist_name, country), ...]
    'Ross Lynch, Jason Evigan & Grace Phipps': [
        ('Ross Lynch', 'US'), ('Jason Evigan', 'US'), ('Grace Phipps', 'US')
    ],
    'peak divide & Rachel Lake': [
        ('peak divide', 'US'), ('Rachel Lake', 'US')
    ],
    'Wallows ft. Clairo': [
        ('Wallows', 'US'), ('Clairo', 'US')
    ],
    'Kenshi Yonezu, Hikaru Utada': [
        ('Kenshi Yonezu', 'JP'), ('Hikaru Utada', 'JP')
    ],
    'Giga-P feat. Rin & Luka, 2014': [
        ('Giga-P', 'JP'), ('Rin', 'JP'), ('Luka', 'JP')
    ],
    # Also fix other collabs that are already mapped but could benefit from splitting
    'Ariana Grande & Justin Bieber': [
        ('Ariana Grande', 'US'), ('Justin Bieber', 'CA')
    ],
    'Calvin Harris, Dua Lipa': [
        ('Calvin Harris', 'GB'), ('Dua Lipa', 'GB')
    ],
    'Dan + Shay, Justin Bieber': [
        ('Dan + Shay', 'US'), ('Justin Bieber', 'CA')
    ],
    'Christina Perri ft. Ed Sheeran': [
        ('Christina Perri', 'US'), ('Ed Sheeran', 'GB')
    ],
    'Yandel ft. Daddy Yankee': [
        ('Yandel', 'PR'), ('Daddy Yankee', 'PR')
    ],
    'Owl City ft. Carly Rae Jepsen': [
        ('Owl City', 'US'), ('Carly Rae Jepsen', 'CA')
    ],
    'Jon Cozart and Dodie': [
        ('Jon Cozart', 'US'), ('Dodie', 'GB')
    ],
    'Mastiksoul Feat. Amanda Wilson & Ebbyman': [
        ('Mastiksoul', 'PT'), ('Amanda Wilson', 'GB'), ('Ebbyman', 'US')
    ],
    'Jason Mraz & Colbie Caillat': [
        ('Jason Mraz', 'US'), ('Colbie Caillat', 'US')
    ],
    'Sigma ft. Birdy': [
        ('Sigma', 'GB'), ('Birdy', 'GB')
    ],
    'Lifehouse feat. Natasha Bedingfield': [
        ('Lifehouse', 'US'), ('Natasha Bedingfield', 'GB')
    ],
    'Pitbull ft. T-Pain': [
        ('Pitbull', 'US'), ('T-Pain', 'US')
    ],
    'Marshmello & Anne-Marie': [
        ('Marshmello', 'US'), ('Anne-Marie', 'GB')
    ],
    'Jon Schmidt & Steven Sharp Nelson': [
        ('Jon Schmidt', 'US'), ('Steven Sharp Nelson', 'US')
    ],
    'Mørland & Debrah Scarlett': [
        ('Mørland', 'NO'), ('Debrah Scarlett', 'NO')
    ],
    'Bastian Baker & Yves Larock': [
        ('Bastian Baker', 'CH'), ('Yves Larock', 'CH')
    ],
    'Daniel Rosty & Sash_S': [
        ('Daniel Rosty', 'US'), ('Sash_S', 'US')
    ],
    'Dionesium x Mr. Chris': [
        ('Dionesium', 'US'), ('Mr. Chris', 'US')
    ],
    'Lilly Wood & The Prick and Robin Schulz': [
        ('Lilly Wood & The Prick', 'FR'), ('Robin Schulz', 'DE')
    ],
    'Mike Perry – Stay Young (ft. Tessa)': [
        ('Mike Perry', 'SE'), ('Tessa', 'US')
    ],
    'Thomas Jack – Rivers (feat. Nico & Vinz)': [
        ('Thomas Jack', 'AU'), ('Nico & Vinz', 'NO')
    ],
    'Sistek – Pitfalls (feat. Tudor & Amy J. Pryce)': [
        ('Sistek', 'US'), ('Tudor', 'US'), ('Amy J. Pryce', 'US')
    ],
    'Karma – CircusP ft. Eyeris (Cover)【JubyPhonic】': [
        ('CircusP', 'JP'), ('Eyeris', 'US')
    ],
    'Some Kind of Beautiful – Tyler Ward ft. Lindsey Stirling': [
        ('Tyler Ward', 'US'), ('Lindsey Stirling', 'US')
    ],
    'Dr. Wily\'s Castle (Mega Man 2) – Violin Cover – Taylor Davis': [
        ('Taylor Davis', 'US')
    ],
    'Lindsey Stirling – Afterglow (ft. Vicetone)': [
        ('Lindsey Stirling', 'US'), ('Vicetone', 'NL')
    ],
    'Yandel "Follow The Leader" Featuring Jennifer Lopez': [
        ('Yandel', 'PR'), ('Jennifer Lopez', 'US')
    ],
    'Shawn Mendes, Camila Cabello': [
        ('Shawn Mendes', 'CA'), ('Camila Cabello', 'US')
    ],
}

CACHE_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'artist_country_cache.json')

def main():
    cache = json.load(open(CACHE_PATH, 'r', encoding='utf-8'))
    added = 0
    
    for collab, artists in COLLAB_SPLITS.items():
        for artist_name, code in artists:
            if artist_name not in cache or not cache[artist_name]:
                cache[artist_name] = code
                added += 1
    
    with open(CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)
    
    mapped = sum(1 for v in cache.values() if v)
    print(f"Added {added} new individual artist mappings")
    print(f"Total cached: {len(cache)}")
    print(f"With country: {mapped}")

if __name__ == '__main__':
    main()
