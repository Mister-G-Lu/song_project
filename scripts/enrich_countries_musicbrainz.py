#!/usr/bin/env python3
"""Use MusicBrainz API to look up remaining unmapped artists for country data."""

import json
import os
import sys
import io
import time
import re
import urllib.request
import urllib.parse
import urllib.error

# Fix Windows console encoding
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

CACHE_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'artist_country_cache.json')
USER_AGENT = 'TasteScope/1.0 (music-taste-analyzer)'

# Known real artists that should be looked up
KNOWN_ARTISTS = [
    'Birdy', 'Billy Ocean', 'Bob Marley & The Wailer', 'Bobby McFerrin',
    'Bryce Vine', 'Burak Yeter', 'Calvin Harris', 'Calvin Harris, Dua Lipa',
    'Candy Dulfer', 'Carole King', 'Cassadee Pope', 'Celeste',
    'Chameleon Circuit', 'Charly García', 'Chelsea Jade', 'Chelsea Wolfe',
    'Chris Cornell', 'Chris Lane', 'Christine Welch', 'Cindy Morgan',
    'Citizen Way', 'Claire Rosinkranz', 'Coeur De Pirate', 'Courage My Love',
    'Crash Adams', 'Deerhoof', 'Deftones', 'Denzel Curry',
    "Destiny's Child", 'Dimash Kudaibergen', 'Dodie Clark',
    'Dominic Fike', 'Dorothy', 'Edward Sharpe & The Magnetic Zeros',
    'Ella Eyre', 'Elmiene', 'Elohim', 'Emmelie de Forest',
    'Eric Clapton', 'Estelle', 'Exuma', 'Faun', 'Farid Mammadov',
    'FLO', 'G-Eazy', 'George Ezra', 'Gnarls Barkley',
    'Gregorian', 'Guster', 'Halsey', 'Hans Zimmer', 'Hayley Kiyoko',
    'Hillsong Worship', 'Imagine Dragons', 'Irma Thomas',
    'J Balvin', 'Jack U', 'Jason Mraz', 'Jeff Buckley',
    'Joji', 'Jonas Blue', 'Jonas Brothers', 'Joy Division',
    'Judah & the Lion', 'Justice', 'Kacey Musgraves',
    'Kat Graham', 'Kaytranada', 'Kero Kero Bonito',
    'Kevin MacLeod', 'Kid Cudi', 'Killers', 'Kings of Leon',
    'Kodaline', 'Kygo', 'Lauv', 'Leon Bridges', 'Leonard Cohen',
    'Lights', 'Lizzo', 'Lorde', 'Louis Tomlinson', 'Lucas Graham',
    'Luis Fonsi', 'M.I.A.', 'M83', 'Mac DeMarco',
    'Maggie Rogers', 'Major Lazer', 'Mark Ronson', 'Marshmello',
    'Matt Maeson', 'Meghan Trainor', 'Metro Station', 'Moby',
    'Mumford & Sons', 'N.E.R.D', 'NF', 'Neiked',
    'Niall Horan', 'Nicki Minaj', 'Niki', 'Ofenbach',
    'Omar Apollo', 'Owl City', 'Palaye Royale', 'Passion Pit',
    'Phoebe Ryan', 'Phum Viphurit', 'Porter Robinson',
    'Post Malone', 'Pride', 'Public', 'Quinn XCII',
    'R3HAB', 'Radiohead', 'Rainbow Kitten Surprise',
    'Rex Orange County', 'Rita Ora', 'Robin Schulz',
    'Royal Blood', 'Run the Jewels', 'Ruth B',
    'Sam Fischer', 'Sam Smith', 'Selena Gomez',
    'Shawn Mendes', 'Sleeping At Last', 'Snail\'s House',
    'Sofi Tukker', 'Son Lux', 'St. Lucia',
    'Steam Powered Giraffe', 'Sting', 'Stray Kids',
    'Sufjan Stevens', 'Summer Walker', 'T-Pain',
    'Tash Sultana', 'Tatiana', 'Taylor Swift',
    'The 1975', 'The Antlers', 'The Band CAMINO',
    'The Black Keys', 'The Book of Love', 'The Chainsmokers',
    'The Drums', 'The Fray', 'The Game',
    'The Ink Spots', 'The Japanese House', 'The Kinks',
    'The Lumineers', 'The Naked and Famous', 'The Neighbourhood',
    'The Paper Kites', 'The Walters', 'The xx',
    'Thrice', 'Tom Odell', 'Tones and I',
    'Twenty One Pilots', 'Two Door Cinema Club',
    'Vampire Weekend', 'Walk The Moon', 'Weezer',
    'Wolf Alice', 'X Ambassadors', 'Yungblud',
    'Zedd', 'ZHU',
    'Agnes Obel', 'Alt-J', 'Amaarae', 'Aphex Twin',
    'Arctic Monkeys', 'Balthazar', 'Bastille',
    'Beach House', 'Beck', 'Ben Howard',
    'Billie Eilish', 'Björk', 'Bones UK',
    'Bon Iver', 'Bonobo', 'Brockhampton',
    'Cage the Elephant', 'CamelPhat', 'Cashmere Cat',
    'Childish Gambino', 'Clairo', 'Cradles',
    'Dua Lipa', 'Foals', 'Glass Animals',
    'Hozier', 'IDLES', 'Jai Wolf',
    'JPEGMAFIA', 'Kali Uchis', 'Kaytranada',
    'Kenny Beats', 'King Princess', 'LANY',
    'Mac Miller', 'Mannequin Pussy', 'Mitski',
    'Nao', 'Nothing But Thieves', 'Parcels',
    'Phoebe Bridgers', 'Pink Sweat$', 'Real Estate',
    'Ruel', 'SZA', 'Sam Fender',
    'Tame Impala', 'Thundercat', 'Turnstile',
    'Wet Leg', 'Yves Tumor',
]

def lookup_artist(name):
    """Look up an artist on MusicBrainz and return country code."""
    query = urllib.parse.quote(f'artist:"{name}"')
    url = f'https://musicbrainz.org/ws/2/artist/?query={query}&fmt=json&limit=1'
    
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            if data.get('artists'):
                artist = data['artists'][0]
                # Check if name matches closely
                mb_name = artist.get('name', '').lower()
                if name.lower() in mb_name or mb_name in name.lower():
                    area = artist.get('area', {})
                    if area and area.get('iso-3166-1-codes'):
                        return area['iso-3166-1-codes'][0]
    except Exception as e:
        pass
    return None

def main():
    cache = json.load(open(CACHE_PATH, 'r', encoding='utf-8'))
    
    # Only look up artists not yet in cache
    to_lookup = [a for a in KNOWN_ARTISTS if a not in cache or not cache[a]]
    
    print(f"Looking up {len(to_lookup)} artists on MusicBrainz...")
    found = 0
    
    for i, name in enumerate(to_lookup):
        if i > 0 and i % 10 == 0:
            print(f"  Progress: {i}/{len(to_lookup)} ({found} found)")
            time.sleep(1)  # Rate limit
        
        code = lookup_artist(name)
        if code:
            cache[name] = code
            found += 1
        
        time.sleep(1.1)  # MusicBrainz rate limit: 1 req/sec
    
    # Save cache
    with open(CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)
    
    mapped = sum(1 for v in cache.values() if v)
    print(f"\nDone! Found {found} new country codes")
    print(f"Total cached: {len(cache)}")
    print(f"With country: {mapped}")

if __name__ == '__main__':
    main()
