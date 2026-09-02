#!/usr/bin/env python3
"""Fix remaining unmapped artists by extracting from title patterns.

The CSV has many entries where the title format is:
  'Song ? Artist' or 'Song (Artist)' or 'Song [Artist]'
where the ? is a corrupted single-quote.

This script:
1. Re-extracts artist names from titles using improved patterns
2. Seeds known artists with country codes
3. Updates the CSV artist column where possible
"""

import csv
import os
import re
import sys
import json
import shutil

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

CSV_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'posts_tails.csv')
CACHE_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'artist_country_cache.json')
BACKUP_PATH = CSV_PATH + '.bak_fix_remaining'

with open(CACHE_PATH, 'r', encoding='utf-8') as f:
    cache = json.load(f)
ci_cache = {k.lower(): v for k, v in cache.items() if v}

# Comprehensive artist->country mapping for remaining unmapped
FINAL_SEED = {
    # From ft/feat extraction
    "Giga-P": "JP",
    "Rin": "JP",
    "Luka": "JP",
    "Hatsune Miku": "JP",
    "JubyPhonic": "JP",
    "Johnathan Young": "US",
    "Mastiksoul": "PT",
    "Amanda Wilson": "US",
    "Ebbyman": "US",
    "Against The Current": "US",
    "Thomas Jack": "AU",
    "Nico & Vinz": "NO",
    "Sistek": "CL",
    "CircusP": "US",
    "Eyeris": "US",
    "Vicetone": "NL",
    "Tyler Ward": "US",
    "Inna": "RO",
    "Daddy Yankee": "PR",
    "Josh Wantie": "ZA",
    "Meghan Trainor": "US",
    "John Legend": "US",
    "Forever The Sickest Kids": "US",
    "Pegboard Nerds": "NO",
    "Elizaveta": "US",
    "Alan Walker": "NO",
    "Iselin Solheim": "NO",
    "Monoir": "RO",
    "Osaka": "JP",
    "Brianna": "US",
    "Dan + Shay": "US",
    "The Glitch Mob": "US",
    "Swan": "US",
    "Gareth Emery": "GB",
    "Bo Bruce": "GB",
    "TheFatRat": "DE",
    "Laura Brehm": "US",
    "Smash Into Pieces": "SE",
    "Jay Smith": "SE",
    "Otto Knows": "SE",
    "Alex Aris": "SE",
    "Grey": "US",
    "Avril Lavigne": "CA",
    "Anthony Green": "US",
    "Becky G": "US",
    "The Chainsmokers": "US",
    "Halsey": "US",
    "Mike Perry": "SE",
    "Tessa": "US",
    
    # From earlier list - real artists
    "Simple Minds": "GB",
    "Ahmir": "US",
    "Julia Brennan": "US",
    "Luke Graham": "US",
    "Soon Hee Newbold": "US",
    "Auli'i Cravalho": "US",
    "Nic Hanson": "US",
    "Joywave": "US",
    "Renee Rapp": "US",
    "The Cab": "US",
    "Yu Peng Chen": "CN",
    "Paradise Lost": "GB",
    
    # More known artists found in unmapped
    "24kGoldn": "US",
    "AJ Raphael": "US",
    "AZEALIA BANKS": "US",
    "Aaliyah Rose": "US",
    "Addison Rae": "US",
    "Akira Yamaoka": "JP",
    "Akon": "US",
    "Alice Cooper": "US",
    "Alice Kristiansen": "NO",
    "Alvaro Soler": "ES",
    "Amalee": "US",
    "Ambrosia": "US",
    "American Authors": "US",
    "Angela Zhang": "TW",
    "Ashley Tisdale": "US",
    "Potsu": "US",
    "Infected Mushroom": "IL",
    "Anselmo Ralph": "AO",
    "Adam Lambert": "US",
    "Within Temptation": "NL",
    "Sam Tinnesz": "US",
    "FDVM": "FR",
    "Lenny Kravitz": "US",
    "Somo": "US",
    "Carly Rae Jepsen": "CA",
    "Monsune": "CA",
    "AOA": "KR",
    "Weslee": "GB",
    "Sigala": "GB",
    "Novo Amor": "GB",
    "Lion Babe": "US",
    "B.A.P": "KR",
    "EXO-K": "KR",
    "MOMOLAND": "KR",
    "Orange Caramel": "KR",
    "Girls' Generation": "KR",
    "Chase Holfelder": "US",
    "Kan Wakan": "US",
    "BYU Vocal Point": "US",
    "Foreign Hands": "US",
    "George Ogilvie": "GB",
    "Brian Crain": "US",
    "Philip Wesley": "US",
    "Casey Lee Williams": "US",
    "Arash": "SE",
    "Nena": "DE",
    "ZZ Top": "US",
    "Panic! at the Disco": "US",
    "Demi Lovato": "US",
    "Michael Jackson": "US",
    "The Hush Sound": "US",
    "Dove Cameron": "US",
    "The Piano Guys": "US",
    "RuPaul": "US",
    "Danse Macabre": "FR",
    "Caravan Palace": "FR",
    "Katy Perry": "US",
    "Magic!": "CA",
    "David Choi": "US",
    "Kana Nishino": "JP",
    "Christina Grimmie": "US",
    "Austin Mahone": "US",
    "Tessa": "US",
    "Vicetone": "NL",
    "Pitbull": "US",
    "T-Pain": "US",
    "Marshmello": "US",
    "Anne-Marie": "GB",
    "Wallows": "US",
    "Clairo": "US",
    
    # More from the full unmapped list
    "Dodie": "GB",
    "Ed Sheeran": "GB",
    "Lindsey Stirling": "US",
    "William Joseph": "US",
    "Adam Hicks": "US",
    "Bridgit Mendler": "US",
    "Naomi Scott": "GB",
    "Hayley Kiyoko": "US",
    "RuPaul": "US",
    "EXO-K": "KR",
    "Orange Caramel": "KR",
    "MOMOLAND": "KR",
    "B.A.P": "KR",
    "Girls' Generation": "KR",
    "Luvoratory": "JP",
    "nqrse": "JP",
    "Foreign Hands": "US",
    
    # From title patterns - 'Song ? Artist'
    "Skyrim Theme": "",
    
    # Additional entries found
    "Against The Current": "US",
    "TheFatRat": "DE",
    "Avril Lavigne": "CA",
    "The Chainsmokers": "US",
    "Halsey": "US",
    "Calvin Harris": "GB",
    "Ellie Goulding": "GB",
    "Arash": "SE",
    "B.A.P": "KR",
}

def extract_from_title_pattern(title):
    """Extract artist from corrupted-title patterns like 'Song ? Artist'."""
    # Pattern: Song ? Artist (question mark = corrupted quote)
    # The artist is usually after the last ?, before year or end
    parts = re.split(r'\?\s*', title)
    if len(parts) >= 2:
        # Last meaningful part is usually the artist
        for part in reversed(parts):
            part = part.strip()
            # Skip years, parentheses
            if re.match(r'^\(?\d{4}\)?$', part):
                continue
            if re.match(r'^\(?\w+\s*\d{4}\)?$', part):  # e.g. "Magic! 2014"
                continue
            if len(part) > 1:
                return part
    return None

def extract_from_title_parens(title):
    """Extract artist from patterns like 'Song (Artist, Year)' or 'Song (covered by Artist)'."""
    # covered by Artist
    m = re.search(r'\(covered by ([^)]+)\)', title, re.I)
    if m:
        return m.group(1).strip()
    
    # Artist, Year pattern in parens
    m = re.search(r'\(([^,)]+),?\s*\d{4}\)', title)
    if m:
        return m.group(1).strip()
    
    return None

def fix_remaining():
    """Fix remaining artist extractions."""
    shutil.copy2(CSV_PATH, BACKUP_PATH)
    
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)
    
    # First, seed all the new artists
    added = 0
    for name, code in FINAL_SEED.items():
        if name not in cache:
            cache[name] = code
            added += 1
    # Also add lowercase variants
    for name, code in FINAL_SEED.items():
        if code and name.lower() not in ci_cache:
            ci_cache[name.lower()] = code
    
    print(f"Seeded {added} new artist entries")
    
    # Now fix CSV rows
    fixed = 0
    for row in rows:
        artist = (row.get('artist') or '').strip()
        if artist and (artist in cache or artist.lower() in ci_cache):
            continue  # Already mapped
        
        title = row.get('title', '')
        if not title:
            continue
        
        new_artist = None
        
        # Try title pattern extraction
        if not new_artist:
            new_artist = extract_from_title_pattern(title)
        
        if not new_artist:
            new_artist = extract_from_title_parens(title)
        
        if new_artist:
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
    
    # Save updated cache
    with open(CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)
    
    return fixed

if __name__ == '__main__':
    fixed = fix_remaining()
    print(f"Fixed {fixed} CSV rows with new artist extractions")
    
    # Coverage check
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
                    artist = title.rsplit(' - ', 1)[1].strip()
                elif chr(0x2013) in title:
                    artist = title.rsplit(chr(0x2013), 1)[1].strip()
            if artist:
                code = cache.get(artist, '') or ci_cache.get(artist.lower(), '')
                if code:
                    mapped += 1
                else:
                    unmapped[artist] = unmapped.get(artist, 0) + 1
            else:
                unmapped['(no artist)'] = unmapped.get('(no artist)', 0) + 1
        
        print(f"\nCoverage: {mapped}/{total} ({100*mapped/total:.1f}%)")
        print(f"Remaining unmapped: {len(unmapped)} unique artists, {sum(unmapped.values())} songs")
        top = sorted(unmapped.items(), key=lambda x: -x[1])[:15]
        print("\nTop 15 remaining:")
        for name, count in top:
            name_clean = name.encode('ascii','replace').decode('ascii')
            print(f"  {name_clean}: {count}")
