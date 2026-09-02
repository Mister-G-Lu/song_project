#!/usr/bin/env python3
"""Fix CSV rows where the artist column is missing.

Handles patterns like:
  'Song (Artist, Year)' or 'Song?Artist?Year'
  'Artist Song' (no separator)
  'Song | Artist' or 'Song ? Artist' or 'Song ~ Artist'
  'Song -Artist' or 'Song-Artist'
  'Happier -Ed Sheeran'
  'Artist feat. Song' or 'Song (ft. Artist)'
  
Also handles corrupted Unicode (question marks replacing special chars).
"""

import csv
import os
import re
import sys
import json
import io

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

CSV_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'posts_tails.csv')
BACKUP_PATH = CSV_PATH + '.bak_fix_no_artist'
CACHE_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'artist_country_cache.json')

# Load cache to check if extracted names are known artists
cache = {}
try:
    with open(CACHE_PATH, 'r', encoding='utf-8') as f:
        cache = json.load(f)
except:
    pass
ci_cache = {k.lower(): v for k, v in cache.items() if v}

# Known artist names that might appear at start or end of titles
KNOWN_ARTISTS = set(k.lower() for k, v in cache.items() if v)

# Playlists/non-song entries to skip
SKIP_PATTERNS = [
    r'spotify', r'weekly', r'discovery', r'review', r'top 10', 
    r'announcement', r'blog', r'\d+/\d+/\d+', r'youtube',
    r'playlist', r'mix', r'album', r'ep\b'
]

def is_playlist_entry(title):
    """Check if this is a playlist or non-song entry."""
    t = title.lower()
    return any(re.search(p, t) for p in SKIP_PATTERNS)

def extract_artist_from_parens(title):
    """Extract artist from patterns like 'Song (Artist, Year)' or 'Song?Artist?Year'."""
    # Pattern: Song (Artist, Year)
    m = re.search(r'\(([^,)]+),?\s*\d{4}\)', title)
    if m:
        return m.group(1).strip()
    
    # Pattern: Song?Artist?Year (corrupted quotes)
    m = re.search(r'\?([^?]+)\??\s*\(?\d{4}\)?', title)
    if m:
        candidate = m.group(1).strip()
        if len(candidate) > 2 and candidate.lower() in KNOWN_ARTISTS:
            return candidate
    
    # Pattern: Song (from Movie) - extract movie name
    m = re.search(r'\(from ([^)]+)\)', title)
    if m:
        return None  # Movie, not artist
    
    return None

def extract_artist_by_delimiter(title):
    """Extract artist using common delimiters."""
    # Unicode en-dash or em-dash
    for delim in [' – ', '—', ' | ', ' ~ ', ' // ', ' _ ']:
        if delim in title:
            parts = title.split(delim, 1)
            # Try both sides
            for part in parts:
                candidate = part.strip()
                if candidate.lower() in KNOWN_ARTISTS:
                    return candidate
            # Default: right side is usually artist
            return parts[1].strip() if len(parts) > 1 else None
    
    # Question mark delimiters (corrupted quotes)
    # Pattern: Song?Artist?Year
    m = re.match(r'^(.+?)\??([A-Z][^?]{2,})\??.*$', title)
    if m:
        candidate = m.group(2).strip()
        if candidate.lower() in KNOWN_ARTISTS:
            return candidate
    
    return None

def extract_artist_heuristic(title):
    """Try to extract artist using heuristics."""
    # Pattern: 'Happier -Ed Sheeran' (dash without spaces)
    m = re.match(r'^(.+?)\s*[-–—]\s*([A-Z][a-z].+)$', title)
    if m:
        candidate = m.group(2).strip()
        if candidate.lower() in KNOWN_ARTISTS:
            return candidate
    
    # Pattern: 'Artist Song' (no separator, artist is known)
    words = title.split()
    for i in range(1, min(len(words), 5)):
        candidate = ' '.join(words[:i])
        if candidate.lower() in KNOWN_ARTISTS:
            return candidate
        # Also check with common suffixes
        for suffix in ['!', '.', "'s"]:
            test = candidate.rstrip(suffix)
            if test.lower() in KNOWN_ARTISTS:
                return test
    
    # Pattern: 'Song ft. Artist' or 'Song (ft. Artist)'
    m = re.search(r'\(?(?:ft\.?|feat\.?)\s*([^)]+)\)?', title, re.I)
    if m:
        return m.group(1).strip()
    
    # Pattern: 'Song [Artist]' (square brackets)
    m = re.search(r'\[([^\]]+)\]', title)
    if m:
        candidate = m.group(1).strip()
        if candidate.lower() in KNOWN_ARTISTS:
            return candidate
    
    return None

def fix_csv():
    """Fix artist column for all rows."""
    import shutil
    shutil.copy2(CSV_PATH, BACKUP_PATH)
    
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)
    
    fixed = 0
    skipped = 0
    
    for row in rows:
        artist = (row.get('artist') or '').strip()
        if artist:
            continue  # Already has artist
        
        title = row.get('title', '')
        if not title:
            continue
        
        # Skip playlists
        if is_playlist_entry(title):
            skipped += 1
            continue
        
        # Try extraction methods in order
        new_artist = None
        
        # 1. Check if already has dash separator (should have been caught earlier)
        if not new_artist and ' - ' in title:
            parts = title.rsplit(' - ', 1)
            new_artist = parts[1].strip()
        
        if not new_artist and chr(0x2013) in title:  # en-dash
            parts = title.rsplit(chr(0x2013), 1)
            new_artist = parts[1].strip()
        
        # 2. Try parenthetical extraction
        if not new_artist:
            new_artist = extract_artist_from_parens(title)
        
        # 3. Try delimiter extraction
        if not new_artist:
            new_artist = extract_artist_by_delimiter(title)
        
        # 4. Try heuristic extraction
        if not new_artist:
            new_artist = extract_artist_heuristic(title)
        
        if new_artist and len(new_artist) > 1:
            # Clean up the artist name
            new_artist = new_artist.strip('?.!\'"')
            # Remove trailing year
            new_artist = re.sub(r'\s*\(\d{4}\)\s*$', '', new_artist)
            new_artist = re.sub(r'\s*\d{4}\s*$', '', new_artist).strip()
            
            if new_artist and len(new_artist) > 1:
                row['artist'] = new_artist
                fixed += 1
    
    # Write back
    with open(CSV_PATH, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    
    return fixed, skipped

if __name__ == '__main__':
    fixed, skipped = fix_csv()
    print(f'Fixed {fixed} rows, skipped {skipped} playlist entries')
    print(f'Backup saved to: {BACKUP_PATH}')
    
    # Quick coverage check
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        total = 0
        mapped = 0
        unmapped = {}
        for row in reader:
            total += 1
            artist = (row.get('artist') or '').strip()
            if not artist:
                title = row.get('title', '')
                if ' - ' in title:
                    parts = title.rsplit(' - ', 1)
                    artist = parts[1].strip()
                elif chr(0x2013) in title:
                    parts = title.rsplit(chr(0x2013), 1)
                    artist = parts[1].strip()
            
            if artist:
                code = cache.get(artist, '') or ci_cache.get(artist.lower(), '')
                if code:
                    mapped += 1
                else:
                    unmapped[artist] = unmapped.get(artist, 0) + 1
            else:
                unmapped['(no artist)'] = unmapped.get('(no artist)', 0) + 1
        
        print(f'\nAfter fix: {mapped}/{total} ({100*mapped/total:.1f}%)')
        print(f'Remaining unmapped: {len(unmapped)} unique artists')
        top = sorted(unmapped.items(), key=lambda x: -x[1])[:10]
        for name, count in top:
            print(f'  {name}: {count}')
