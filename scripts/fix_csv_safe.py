#!/usr/bin/env python3
"""Safe CSV artist fixer — only updates the artist column, never adds/removes rows."""

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
USER_AGENT = 'TasteScope/1.0 (music-taste-analyzer; github.com/Mister-G-Lu/song_project)'

def load_cache():
    try:
        with open(CACHE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_cache(cache):
    with open(CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)

def safe_write_csv(fieldnames, rows):
    """Write CSV safely — verify row count matches."""
    with open(CSV_PATH, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    # Verify
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        verify = list(reader)
    assert len(verify) == len(rows), f"Row count mismatch! {len(verify)} != {len(rows)}"
    return len(verify)

def extract_artist(title, cache):
    """Extract artist from title using pattern matching."""
    if not title:
        return ''
    
    # Skip non-song entries
    if re.match(r'^\d+/\d+/\d+', title): return ''
    if re.match(r'^(?:Announcement|Youtube|Review|Weekly|SPOTIFY|Spotify|note|NOTE)', title, re.I): return ''
    
    # Pattern: "Song (Artist, Year)" — with possible missing closing paren
    m = re.match(r'^(.+?)\s*\(([^,)]+),?\s*\d{4}\)?\s*$', title)
    if m:
        artist = m.group(2).strip().rstrip(')')
        if artist and len(artist) > 1 and not re.match(r'^\d+$', artist):
            return artist
    
    # Pattern: "Song [Artist, Year]" or "Song 「Artist」"
    m = re.match(r'^(.+?)\s*[\[「]([^]」]+?)[\]」]\s*\(?(\d{4})\)?\s*$', title)
    if m:
        return m.group(2).strip()
    
    # Pattern: "Song 「Artist」" without year
    m = re.match(r'^(.+?)\s*[\[「]([^]」]+?)[\]」]', title)
    if m:
        return m.group(2).strip()
    
    # Pattern: "Song (Artist)" without year
    m = re.match(r'^(.+?)\s*\(([^)]+)\)\s*$', title)
    if m:
        artist = m.group(2).strip()
        if artist and len(artist) > 1:
            if not re.match(r'^(?:feat\.?|ft\.?|with|from|Theme|Cover|MV|Radio)', artist, re.I):
                if not any(x in artist.lower() for x in ['theme', 'cover', 'remix', 'version', 'mv', 'radio edit']):
                    return artist
    
    # Pattern: "Song – Artist (Year)" or "Song - Artist"
    m = re.match(r'^(.+?)\s*[–—-]\s+(.+?)(?:\s*\(\d{4}\))?\s*$', title)
    if m:
        before = m.group(1).strip()
        after = m.group(2).strip()
        # Clean after
        after_clean = re.sub(r'\s*(?:ft\.?|feat\.?|featuring)\s+.*$', '', after, flags=re.I).strip()
        if after_clean and len(after_clean) > 1:
            if after_clean in cache and cache[after_clean]:
                return after_clean
            if after_clean[0].isupper():
                return after_clean
    
    # Pattern: "Song ft. Artist" or "Song feat. Artist"
    m = re.match(r'^(.+?)\s+(?:ft\.?|feat\.?|featuring)\s+(.+?)(?:\s*\(|$)', title, re.I)
    if m:
        return m.group(2).strip()
    
    # Pattern: "Song by Artist"
    m = re.match(r'^(.+?)\s+by\s+(.+?)(?:\s*\(|$)', title, re.I)
    if m:
        return m.group(2).strip()
    
    # Pattern: "Dirty Work Austin Mahone" — artist at end (2+ capitalized words)
    m = re.match(r'^(.+?)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\s*$', title)
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
    
    original_count = len(rows)
    print(f"Read {original_count} rows, columns: {fieldnames}")
    
    # Phase 1: Fix empty artist columns using pattern matching
    fixed = 0
    for i, row in enumerate(rows):
        if not (row.get('artist') or '').strip():
            title = row.get('title', '')
            artist = extract_artist(title, cache)
            if artist:
                rows[i]['artist'] = artist
                fixed += 1
    
    print(f"Phase 1: Fixed {fixed} rows by pattern matching")
    
    # Save CSV after phase 1
    count = safe_write_csv(fieldnames, rows)
    print(f"CSV written: {count} rows (original: {original_count})")
    
    # Phase 2: Find unmapped artists and look up on MusicBrainz
    unmapped = {}
    for row in rows:
        artist = (row.get('artist') or '').strip()
        if artist and (artist not in cache or not cache[artist]):
            unmapped[artist] = unmapped.get(artist, 0) + 1
    
    print(f"\nPhase 2: {len(unmapped)} unmapped artists ({sum(unmapped.values())} songs)")
    
    # Sort by song count
    to_lookup = sorted(unmapped.items(), key=lambda x: -x[1])
    
    # Only look up top 150 to stay within rate limits
    to_lookup = to_lookup[:150]
    print(f"Looking up top {len(to_lookup)} on MusicBrainz...")
    
    found = 0
    errors = 0
    
    for i, (name, count) in enumerate(to_lookup):
        if i > 0 and i % 10 == 0:
            print(f"  Progress: {i}/{len(to_lookup)} (found={found} errors={errors})")
            save_cache(cache)
        
        code = lookup_musicbrainz(name)
        if code:
            cache[name] = code
            found += 1
            if count >= 2:
                print(f"  FOUND: {name} -> {code} ({count} songs)")
        else:
            cache[name] = ''
            errors += 1
        
        time.sleep(1.2)  # Rate limit
    
    save_cache(cache)
    
    mapped = sum(1 for v in cache.values() if v)
    print(f"\nDone!")
    print(f"Cache: {len(cache)} entries, {mapped} with country")
    print(f"CSV rows: {len(rows)} (unchanged)")

if __name__ == '__main__':
    main()
