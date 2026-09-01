#!/usr/bin/env python3
"""Background MusicBrainz API enrichment for artist countries.

Usage:
    python scripts/enrich_countries_bg.py [--limit N]

Looks up unmapped artists via MusicBrainz API (1 req/sec rate limit).
Saves progress incrementally so it can be restarted.
"""

import json
import os
import sys
import io
import time
import re
import unicodedata
import urllib.request
import urllib.parse

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

CACHE_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'artist_country_cache.json')
CSV_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'posts_tails.csv')
USER_AGENT = 'TasteScope/1.0 (music-taste-analyzer; contact: github.com/Mister-G-Lu/song_project)'

def load_cache():
    try:
        with open(CACHE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_cache(cache):
    with open(CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)

def get_unmapped_artists(cache):
    """Extract artist names from CSV that are not yet in cache."""
    import csv
    artists = {}
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            title = row.get('title', '')
            # Pattern 1: "Song Name (Artist, Year)"
            m = re.search(r'\(([^)]+),\s*\d{4}\)', title)
            if m:
                artist = m.group(1).strip()
                if artist and len(artist) > 1 and (artist not in cache or not cache[artist]):
                    artists[artist] = artists.get(artist, 0) + 1
                continue
            # Pattern 2: "Artist – Song" or "Song – Artist"
            m = re.match(r'^(.+?)\s*[–-]\s+(.+)$', title)
            if m:
                before = m.group(1).strip()
                after = m.group(2).strip().rstrip('.').strip()
                for name in [before, after]:
                    if name and len(name) > 1 and (name not in cache or not cache[name]):
                        artists[name] = artists.get(name, 0) + 1
    return artists

def lookup_artist(name):
    """Look up an artist on MusicBrainz and return country code."""
    # Clean the name
    clean = name.strip().strip('"').strip("'")
    clean = re.sub(r'\s*[,*]?\s*ft\.?.*$', '', clean, flags=re.I).strip()
    clean = re.sub(r'\s*[,*]?\s*feat\.?.*$', '', clean, flags=re.I).strip()
    if not clean or len(clean) < 2:
        return None
    
    query = urllib.parse.quote(f'artist:"{clean}"')
    url = f'https://musicbrainz.org/ws/2/artist/?query={query}&fmt=json&limit=3'
    
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            if data.get('artists'):
                # Try to find best match
                for artist in data['artists']:
                    mb_name = artist.get('name', '').lower()
                    clean_lower = clean.lower()
                    # Check for close name match
                    if (clean_lower in mb_name or mb_name in clean_lower or
                        unicodedata.normalize('NFC', clean_lower) == unicodedata.normalize('NFC', mb_name)):
                        area = artist.get('area', {})
                        if area and area.get('iso-3166-1-codes'):
                            return area['iso-3166-1-codes'][0]
                        # Try begin-area
                        begin_area = artist.get('begin-area', {})
                        if begin_area and begin_area.get('iso-3166-1-codes'):
                            return begin_area['iso-3166-1-codes'][0]
    except Exception as e:
        print(f'  Error looking up {name}: {e}')
    return None

def main():
    limit = 500
    if '--limit' in sys.argv:
        idx = sys.argv.index('--limit')
        if idx + 1 < len(sys.argv):
            limit = int(sys.argv[idx + 1])
    
    cache = load_cache()
    unmapped = get_unmapped_artists(cache)
    
    # Sort by song count (most songs first)
    sorted_artists = sorted(unmapped.items(), key=lambda x: -x[1])
    
    print(f"Unmapped artists: {len(sorted_artists)}")
    print(f"Will look up top {limit}")
    
    found = 0
    not_found = 0
    errors = 0
    
    for i, (name, count) in enumerate(sorted_artists[:limit]):
        if i > 0 and i % 20 == 0:
            print(f"  Progress: {i}/{min(limit, len(sorted_artists))} (found={found} not_found={not_found} errors={errors})")
            save_cache(cache)
        
        code = lookup_artist(name)
        if code:
            cache[name] = code
            found += 1
            if count >= 2:
                print(f"  FOUND: {name} -> {code} ({count} songs)")
        else:
            cache[name] = ''  # Mark as looked up
            not_found += 1
        
        time.sleep(1.1)  # MusicBrainz rate limit
    
    save_cache(cache)
    mapped = sum(1 for v in cache.values() if v)
    print(f"\nDone! Found {found} new country codes")
    print(f"Total cached: {len(cache)}")
    print(f"With country: {mapped}")

if __name__ == '__main__':
    main()
