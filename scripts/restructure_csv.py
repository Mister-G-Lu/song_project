#!/usr/bin/env python3
"""Restructure CSV to add artist, song, title_original, title_english columns.

Processes existing titles and extracts structured data using:
1. Pattern matching (Song (Artist, Year), Artist – Song, etc.)
2. Country cache lookups for disambiguation
3. Curated artist list for known artists
"""

import csv
import json
import os
import re
import sys
import io
import unicodedata

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

CSV_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'posts_tails.csv')
BACKUP_PATH = CSV_PATH + '.bak'
CACHE_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'artist_country_cache.json')

# Load caches
def load_caches():
    cache = {}
    try:
        with open(CACHE_PATH, 'r', encoding='utf-8') as f:
            cache = json.load(f)
    except:
        pass
    
    # Build CI index
    ci_index = {}
    for k, v in cache.items():
        if v:
            ci_index[k.lower()] = v
    
    return cache, ci_index

def load_curated_genres():
    """Load curated artist-genre mapping."""
    path = os.path.join(os.path.dirname(__file__), '..', 'data', 'curated_artist_genres.json')
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def extract_structured(title, cache, ci_index, curated):
    """Extract artist, song from a title string.
    
    Returns (artist, song, title_original, title_english) tuple.
    """
    artist = ''
    song = ''
    title_original = ''
    title_english = ''
    
    # Detect non-English titles (contains CJK, Cyrillic, etc.)
    has_non_latin = bool(re.search(r'[\u3000-\u9fff\uf900-\ufaff\u0400-\u04ff]', title))
    
    # Pattern 1: "Song Name (Artist, Year)" — most common format
    m = re.match(r'^(.+?)\s*\(([^)]+),\s*(\d{4})\)\s*$', title)
    if m:
        song = m.group(1).strip()
        artist = m.group(2).strip()
        if has_non_latin:
            title_original = title
        return artist, song, title_original, title_english
    
    # Pattern 2: "Song Name [Artist]" or "Song Name {Artist}"
    m = re.match(r'^(.+?)\s*[\[{]([^}\]]+)[\]}]\s*$', title)
    if m:
        song = m.group(1).strip()
        artist = m.group(2).strip()
        if has_non_latin:
            title_original = title
        return artist, song, title_original, title_english
    
    # Pattern 3: "Song Name (Artist)" without year
    m = re.match(r'^(.+?)\s*\(([^)]+)\)\s*$', title)
    if m:
        possible_song = m.group(1).strip()
        possible_artist = m.group(2).strip()
        # Check if second part looks like an artist (in cache or curated)
        if (possible_artist in cache and cache[possible_artist]) or \
           possible_artist in curated or \
           possible_artist in ci_index:
            return possible_artist, possible_song, title_original, title_english
        # Could be "Song (with/feat Artist)" or just "Song (description)"
        if re.match(r'^(?:with|feat\.?|ft\.?|featuring)\s+', possible_artist, re.I):
            return '', possible_song, title_original, title_english
    
    # Pattern 4: "Artist – Song" or "Artist - Song"
    m = re.match(r'^(.+?)\s*[–-]\s+(.+?)(?:,?\s*\d{4})?\s*$', title)
    if m:
        before = m.group(1).strip()
        after = m.group(2).strip().rstrip('.').strip()
        
        # Check which side is more likely the artist
        before_is_artist = (before in cache and cache[before]) or before in curated or before in ci_index
        after_is_artist = (after in cache and cache[after]) or after in curated or after in ci_index
        
        if before_is_artist and not after_is_artist:
            return before, after, title_original, title_english
        elif after_is_artist and not before_is_artist:
            return after, before, title_original, title_english
        elif before_is_artist and after_is_artist:
            # Both look like artists — check which is more common
            before_count = len([k for k in cache if k.lower() == before.lower()])
            after_count = len([k for k in cache if k.lower() == after.lower()])
            if before_count >= after_count:
                return before, after, title_original, title_english
            else:
                return after, before, title_original, title_english
        else:
            # Neither is known — use heuristics
            # Shorter side is usually the song
            if len(before) < len(after):
                return '', title, title_original, title_english
            else:
                return '', title, title_original, title_english
    
    # Pattern 5: "Song by Artist" or "Song ft. Artist"
    m = re.match(r'^(.+?)\s+(?:by|ft\.?|feat\.?|featuring|&|and)\s+(.+?)(?:,?\s*\d{4})?\s*$', title, re.I)
    if m:
        song = m.group(1).strip()
        artist = m.group(2).strip()
        return artist, song, title_original, title_english
    
    # Pattern 6: "Artist: Song"
    m = re.match(r'^(.+?):\s+(.+?)(?:,?\s*\d{4})?\s*$', title)
    if m:
        artist = m.group(1).strip()
        song = m.group(2).strip()
        return artist, song, title_original, title_english
    
    # Pattern 7: [MV] Artist _ Song
    m = re.match(r'^\[MV\]\s*(.+?)\s*_\s*(.+?)(?:,?\s*\d{4})?\s*$', title)
    if m:
        artist = m.group(1).strip()
        song = m.group(2).strip()
        if has_non_latin:
            title_original = title
        return artist, song, title_original, title_english
    
    # No pattern matched — return title as-is
    return '', title, title_original, title_english

def main():
    cache, ci_index = load_caches()
    curated = load_curated_genres()
    
    print(f"Loaded {len(cache)} country cache entries")
    print(f"Loaded {len(curated)} curated artist entries")
    
    # Backup original CSV
    if not os.path.exists(BACKUP_PATH):
        import shutil
        shutil.copy2(CSV_PATH, BACKUP_PATH)
        print(f"Backup created: {BACKUP_PATH}")
    
    # Read original CSV
    rows = []
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            rows.append(row)
    
    print(f"Read {len(rows)} rows")
    
    # Add new columns
    new_fieldnames = fieldnames + ['artist', 'song', 'title_original', 'title_english']
    
    # Process each row
    stats = {'artist_found': 0, 'song_found': 0, 'original_non_latin': 0}
    
    for row in rows:
        title = row.get('title', '')
        artist, song, title_original, title_english = extract_structured(
            title, cache, ci_index, curated
        )
        
        row['artist'] = artist
        row['song'] = song
        row['title_original'] = title_original
        row['title_english'] = title_english
        
        if artist:
            stats['artist_found'] += 1
        if song:
            stats['song_found'] += 1
        if title_original:
            stats['original_non_latin'] += 1
    
    # Write updated CSV
    with open(CSV_PATH, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=new_fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    
    print(f"\nUpdated CSV with new columns:")
    print(f"  Artist found: {stats['artist_found']}/{len(rows)} ({stats['artist_found']/len(rows)*100:.1f}%)")
    print(f"  Song found: {stats['song_found']}/{len(rows)} ({stats['song_found']/len(rows)*100:.1f}%)")
    print(f"  Non-Latin titles: {stats['original_non_latin']}")
    
    # Show sample output
    print(f"\nSample output (first 10 rows with artist):")
    count = 0
    for row in rows:
        if row['artist'] and count < 10:
            print(f"  Artist: {row['artist']:30s} Song: {row['song'][:40]}")
            print(f"    Title: {row['title'][:60]}")
            count += 1

if __name__ == '__main__':
    main()
