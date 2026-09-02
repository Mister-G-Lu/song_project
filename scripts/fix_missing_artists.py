#!/usr/bin/env python3
"""Fix missing artist entries in CSV using improved heuristics.

Targets the 1,217 rows where the artist column is empty.
Uses more aggressive pattern matching and MusicBrainz lookups.
"""

import csv
import json
import os
import re
import sys
import io
import time
import urllib.request
import urllib.parse

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

CSV_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'posts_tails.csv')
CACHE_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'artist_country_cache.json')
USER_AGENT = 'TasteScope/1.0 (music-taste-analyzer)'

def load_cache():
    try:
        with open(CACHE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_cache(cache):
    with open(CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)

def improved_extract(title, cache):
    """More aggressive artist extraction from title."""
    if not title:
        return ''
    
    # Pattern: "Song (Artist, Year)" but with missing closing paren
    m = re.match(r'^(.+?)\s*\(([^)]+?),?\s*\d{4}\)?\s*$', title)
    if m:
        artist = m.group(2).strip()
        # Clean up trailing parens
        artist = re.sub(r'\s*\)\s*$', '', artist)
        if artist and len(artist) > 1:
            return artist
    
    # Pattern: "Song [Artist, Year]"
    m = re.match(r'^(.+?)\s*\[([^}\]]+?),?\s*\d{4}\]?\s*$', title)
    if m:
        artist = m.group(2).strip()
        artist = re.sub(r'\s*\]\s*$', '', artist)
        if artist and len(artist) > 1:
            return artist
    
    # Pattern: "Artist Song (Year)" — no separator, just space before year
    m = re.match(r'^(.+?)\s+(\w[\w\s]*?)\s*\(?(\d{4})\)?\s*$', title)
    if m:
        # Could be "Artist Song (Year)" or "Song Artist (Year)"
        pass
    
    # Pattern: "Song – Artist (Year)" — dash with year at end
    m = re.match(r'^(.+?)\s*[–-]\s+(.+?)\s*\(?\d{4}\)?\s*$', title)
    if m:
        before = m.group(1).strip()
        after = m.group(2).strip()
        # Check if after looks like an artist (in cache)
        if after in cache and cache[after]:
            return after
        if before in cache and cache[before]:
            return before
    
    # Pattern: "Song – Artist" without year
    m = re.match(r'^(.+?)\s*[–-]\s+(.+?)\s*$', title)
    if m:
        before = m.group(1).strip()
        after = m.group(2).strip()
        if after in cache and cache[after]:
            return after
        if before in cache and cache[before]:
            return before
    
    # Pattern: "Artist: Song"
    m = re.match(r'^([A-Z][\w\s.]+?):\s+(.+)$', title)
    if m:
        artist = m.group(1).strip()
        if artist in cache and cache[artist]:
            return artist
    
    # Pattern: "Song by Artist"
    m = re.match(r'^(.+?)\s+by\s+(.+?)(?:\s*\(|$)', title, re.I)
    if m:
        return m.group(2).strip()
    
    # Pattern: "Song ft. Artist" or "Song feat. Artist"
    m = re.match(r'^(.+?)\s+(?:ft\.?|feat\.?|featuring)\s+(.+?)(?:\s*\(|$)', title, re.I)
    if m:
        return m.group(2).strip()
    
    # Pattern: "Song (with Artist)"
    m = re.match(r'^(.+?)\s*\(with\s+(.+?)\)', title, re.I)
    if m:
        return m.group(2).strip()
    
    return ''

def lookup_musicbrainz(name, cache):
    """Look up artist on MusicBrainz."""
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
                for artist in data['artists']:
                    mb_name = artist.get('name', '').lower()
                    clean_lower = clean.lower()
                    if (clean_lower in mb_name or mb_name in clean_lower or
                        len(set(clean_lower.split()) & set(mb_name.split())) >= 1):
                        area = artist.get('area', {})
                        if area and area.get('iso-3166-1-codes'):
                            return area['iso-3166-1-codes'][0]
                        begin_area = artist.get('begin-area', {})
                        if begin_area and begin_area.get('iso-3166-1-codes'):
                            return begin_area['iso-3166-1-codes'][0]
    except Exception as e:
        pass
    return None

def main():
    cache = load_cache()
    
    # Read CSV
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)
    
    # Find rows needing fixes
    needs_fix = []
    for i, row in enumerate(rows):
        artist = (row.get('artist') or '').strip()
        if not artist:
            needs_fix.append(i)
    
    print(f"Rows needing artist: {len(needs_fix)}")
    
    # Phase 1: Try improved heuristics
    fixed_heuristic = 0
    for idx in needs_fix:
        title = rows[idx].get('title', '')
        artist = improved_extract(title, cache)
        if artist:
            rows[idx]['artist'] = artist
            fixed_heuristic += 1
    
    print(f"Fixed by heuristics: {fixed_heuristic}")
    
    # Phase 2: MusicBrainz lookups for remaining unmapped
    still_needs = [i for i in needs_fix if not (rows[i].get('artist') or '').strip()]
    print(f"Still need artist: {len(still_needs)}")
    
    # Also find unmapped artists in existing rows
    unmapped_artists = {}
    for row in rows:
        artist = (row.get('artist') or '').strip()
        if artist and (artist not in cache or not cache[artist]):
            unmapped_artists[artist] = unmapped_artists.get(artist, 0) + 1
    
    print(f"Unmapped existing artists: {len(unmapped_artists)}")
    
    # Sort by song count
    to_lookup = sorted(unmapped_artists.items(), key=lambda x: -x[1])
    
    print(f"\nLooking up {len(to_lookup)} unmapped artists on MusicBrainz...")
    found = 0
    for i, (name, count) in enumerate(to_lookup):
        if i > 0 and i % 10 == 0:
            print(f"  Progress: {i}/{len(to_lookup)} (found={found})")
            save_cache(cache)
        
        code = lookup_musicbrainz(name, cache)
        if code:
            cache[name] = code
            found += 1
            if count >= 2:
                print(f"  FOUND: {name} -> {code} ({count} songs)")
        else:
            cache[name] = ''
        
        time.sleep(1.2)  # Rate limit
    
    save_cache(cache)
    
    # Write updated CSV
    with open(CSV_PATH, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    
    mapped = sum(1 for v in cache.values() if v)
    print(f"\nDone!")
    print(f"Cache: {len(cache)} entries, {mapped} with country")
    print(f"CSV fixed: {fixed_heuristic} rows by heuristics")

if __name__ == '__main__':
    main()
