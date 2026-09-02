#!/usr/bin/env python3
"""Background MusicBrainz enrichment — ONLY updates artist_country_cache.json, never touches CSV.
Runs for up to 1 hour or until 80% coverage, whichever comes first.
"""

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

CACHE_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'artist_country_cache.json')
CSV_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'posts_tails.csv')
USER_AGENT = 'TasteScope/1.0 (music-taste-analyzer; github.com/Mister-G-Lu/song_project)'
MAX_SECONDS = 3600  # 1 hour
TARGET_COVERAGE = 0.80

def load_cache():
    try:
        with open(CACHE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_cache(cache):
    with open(CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)

def get_unmapped(cache):
    """Get unmapped artists from CSV."""
    import csv
    unmapped = {}
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            artist = (row.get('artist') or '').strip()
            if artist and (artist not in cache or not cache[artist]):
                unmapped[artist] = unmapped.get(artist, 0) + 1
    return unmapped

def estimate_coverage(cache):
    """Estimate coverage from CSV."""
    import csv
    total = 0
    mapped = 0
    # Build CI index
    ci = {k.lower(): v for k, v in cache.items() if v}
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            total += 1
            artist = (row.get('artist') or '').strip()
            if artist:
                code = cache.get(artist, '') or ci.get(artist.lower(), '')
                if code:
                    mapped += 1
    return mapped / total if total else 0

def lookup_musicbrainz(name):
    """Look up artist on MusicBrainz."""
    clean = name.strip().strip('"').strip("'")
    clean = re.sub(r'\s*[,*]?\s*ft\.?.*$', '', clean, flags=re.I).strip()
    clean = re.sub(r'\s*[,*]?\s*feat\.?.*$', '', clean, flags=re.I).strip()
    if not clean or len(clean) < 2 or len(clean) > 80:
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
        if '503' in str(e) or '429' in str(e):
            return None  # Rate limited, skip
    return None

def main():
    start_time = time.time()
    cache = load_cache()
    
    unmapped = get_unmapped(cache)
    to_lookup = sorted(unmapped.items(), key=lambda x: -x[1])
    
    print(f"Start: {len(to_lookup)} unmapped artists", flush=True)
    print(f"Current coverage: {estimate_coverage(cache)*100:.1f}%", flush=True)
    
    found = 0
    errors = 0
    
    for i, (name, count) in enumerate(to_lookup):
        # Check time limit
        elapsed = time.time() - start_time
        if elapsed > MAX_SECONDS:
            print(f"\nTime limit reached ({elapsed:.0f}s)", flush=True)
            break
        
        # Check coverage target
        current_cov = estimate_coverage(cache)
        if current_cov >= TARGET_COVERAGE:
            print(f"\nTarget coverage reached ({current_cov*100:.1f}%)", flush=True)
            break
        
        if i > 0 and i % 10 == 0:
            elapsed = time.time() - start_time
            print(f"  [{elapsed:.0f}s] Progress: {i}/{len(to_lookup)} (found={found} errors={errors}) coverage={current_cov*100:.1f}%", flush=True)
            save_cache(cache)
        
        code = lookup_musicbrainz(name)
        if code:
            cache[name] = code
            found += 1
            if count >= 2:
                print(f"  FOUND: {name} -> {code} ({count} songs)", flush=True)
        else:
            cache[name] = ''
            errors += 1
        
        time.sleep(1.2)  # MusicBrainz rate limit
    
    save_cache(cache)
    elapsed = time.time() - start_time
    final_cov = estimate_coverage(cache)
    mapped = sum(1 for v in cache.values() if v)
    
    print(f"\nDone in {elapsed:.0f}s", flush=True)
    print(f"Cache: {len(cache)} entries, {mapped} with country", flush=True)
    print(f"Final coverage: {final_cov*100:.1f}%", flush=True)

if __name__ == '__main__':
    main()
