#!/usr/bin/env python3
"""Fix all missing artist entries in CSV.

Uses pattern matching on titles to extract artist names,
then looks up unknown artists on MusicBrainz (1 req/sec).
Saves progress incrementally.
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
BACKUP_PATH = CSV_PATH + '.bak2'
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

def extract_artist_from_title(title, cache):
    """Extract artist from title using multiple patterns."""
    if not title:
        return ''
    
    # Skip non-song entries
    skip_patterns = [
        r'^\d+/\d+/\d+',  # dates like "6/18/2018's"
        r'^Announcement', r'^Youtube', r'^Review', r'^Weekly',
        r'^SPOTIFY', r'^Spotify', r'^note', r'^NOTE',
    ]
    for pat in skip_patterns:
        if re.match(pat, title, re.I):
            return ''
    
    # Pattern 1: "Song (Artist, Year)" — with possible missing closing paren
    m = re.match(r'^(.+?)\s*\(([^,)]+),?\s*\d{4}\)?\s*$', title)
    if m:
        artist = m.group(2).strip()
        artist = re.sub(r'\s*\)\s*$', '', artist)
        if artist and len(artist) > 1 and not re.match(r'^\d+$', artist):
            return artist
    
    # Pattern 2: "Song [Artist, Year]" or "Song 「Artist」"
    m = re.match(r'^(.+?)\s*[\[「]([^]」]+?)[\]」]\s*\(?(\d{4})\)?\s*$', title)
    if m:
        artist = m.group(2).strip()
        if artist and len(artist) > 1:
            return artist
    
    # Pattern 3: "Song 「Artist」" without year
    m = re.match(r'^(.+?)\s*[\[「]([^]」]+?)[\]」]', title)
    if m:
        artist = m.group(2).strip()
        if artist and len(artist) > 1:
            return artist
    
    # Pattern 4: "Song (Artist)" without year
    m = re.match(r'^(.+?)\s*\(([^)]+)\)\s*$', title)
    if m:
        artist = m.group(2).strip()
        if artist and len(artist) > 1 and not re.match(r'^(?:feat\.?|ft\.?|with|from|Theme|Cover|MV)', artist, re.I):
            # Check if it looks like an artist name (not a description)
            if not any(x in artist.lower() for x in ['theme', 'cover', 'remix', 'version', 'mv']):
                return artist
    
    # Pattern 5: "Song – Artist (Year)" or "Song - Artist"
    m = re.match(r'^(.+?)\s*[–—-]\s+(.+?)(?:\s*\(\d{4}\))?\s*$', title)
    if m:
        before = m.group(1).strip()
        after = m.group(2).strip()
        # Clean after: remove "ft." etc.
        after_clean = re.sub(r'\s*(?:ft\.?|feat\.?|featuring)\s+.*$', '', after, flags=re.I).strip()
        if after_clean and len(after_clean) > 1:
            # Check cache first
            if after_clean in cache and cache[after_clean]:
                return after_clean
            # Check if after_clean looks like an artist (has proper case)
            if after_clean[0].isupper() and not re.match(r'^(?:The |A |An )', after_clean):
                return after_clean
    
    # Pattern 6: "Song ft. Artist" or "Song feat. Artist"
    m = re.match(r'^(.+?)\s+(?:ft\.?|feat\.?|featuring)\s+(.+?)(?:\s*\(|$)', title, re.I)
    if m:
        return m.group(2).strip()
    
    # Pattern 7: "Song by Artist"
    m = re.match(r'^(.+?)\s+by\s+(.+?)(?:\s*\(|$)', title, re.I)
    if m:
        return m.group(2).strip()
    
    # Pattern 8: "Artist Song (Year)" — no separator, artist at start
    m = re.match(r'^([A-Z][\w\s.]+?)\s+(\w[\w\s]*?)\s*\(?(\d{4})\)?\s*$', title)
    if m:
        artist = m.group(1).strip()
        if artist in cache and cache[artist]:
            return artist
    
    # Pattern 9: "Dirty Work Austin Mahone" — artist at end
    m = re.match(r'^(.+?)\s+([A-Z][\w]+(?:\s+[A-Z][\w]+)*)\s*$', title)
    if m:
        artist = m.group(2).strip()
        if artist in cache and cache[artist]:
            return artist
    
    return ''

def lookup_musicbrainz(name):
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
    except Exception:
        pass
    return None

def main():
    cache = load_cache()
    
    # Read CSV
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)
    
    # Phase 1: Fix empty artist columns using title parsing
    fixed = 0
    still_empty = []
    for i, row in enumerate(rows):
        if not (row.get('artist') or '').strip():
            title = row.get('title', '')
            artist = extract_artist_from_title(title, cache)
            if artist:
                rows[i]['artist'] = artist
                fixed += 1
            else:
                still_empty.append(i)
    
    print(f"Phase 1: Fixed {fixed} rows by pattern matching")
    print(f"Phase 1: {len(still_empty)} rows still need artist")
    
    # Phase 2: Find unmapped artists and look up on MusicBrainz
    unmapped = {}
    for row in rows:
        artist = (row.get('artist') or '').strip()
        if artist and (artist not in cache or not cache[artist]):
            unmapped[artist] = unmapped.get(artist, 0) + 1
    
    print(f"\nPhase 2: {len(unmapped)} unmapped artists ({sum(unmapped.values())} songs)")
    
    # Sort by song count
    to_lookup = sorted(unmapped.items(), key=lambda x: -x[1])
    
    print(f"Looking up {len(to_lookup)} artists on MusicBrainz...")
    found = 0
    errors = 0
    
    for i, (name, count) in enumerate(to_lookup):
        if i > 0 and i % 10 == 0:
            print(f"  Progress: {i}/{len(to_lookup)} (found={found} errors={errors})")
            save_cache(cache)
            # Write CSV periodically
            with open(CSV_PATH, 'w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
        
        code = lookup_musicbrainz(name)
        if code:
            cache[name] = code
            found += 1
            if count >= 2:
                print(f"  FOUND: {name} -> {code} ({count} songs)")
        elif code is None:
            cache[name] = ''
            errors += 1
        else:
            cache[name] = ''
        
        time.sleep(1.2)  # Rate limit
    
    # Final save
    save_cache(cache)
    with open(CSV_PATH, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    
    mapped = sum(1 for v in cache.values() if v)
    print(f"\nDone!")
    print(f"Cache: {len(cache)} entries, {mapped} with country")
    print(f"CSV: {fixed} rows fixed by patterns")

if __name__ == '__main__':
    main()
