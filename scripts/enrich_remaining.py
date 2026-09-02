#!/usr/bin/env python3
"""Enrich remaining unmapped artists via MusicBrainz API.

Looks up ALL artists from the CSV that aren't in the country cache yet,
with rate limiting (1 req/sec) and a 1-hour timeout.
"""

import csv
import json
import os
import re
import sys
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
MAX_SECONDS = 3600  # 1 hour
TARGET_COVERAGE = 0.80

COUNTRY_NAME_TO_CODE = {
    'United States': 'US', 'United Kingdom': 'GB', 'Canada': 'CA',
    'Australia': 'AU', 'Japan': 'JP', 'South Korea': 'KR',
    'Germany': 'DE', 'France': 'FR', 'Italy': 'IT', 'Spain': 'ES',
    'Netherlands': 'NL', 'Sweden': 'SE', 'Norway': 'NO', 'Denmark': 'DK',
    'Finland': 'FI', 'Iceland': 'IS', 'Ireland': 'IE', 'Belgium': 'BE',
    'Switzerland': 'CH', 'Austria': 'AT', 'Portugal': 'PT', 'Poland': 'PL',
    'Brazil': 'BR', 'Argentina': 'AR', 'Mexico': 'MX', 'Colombia': 'CO',
    'Chile': 'CL', 'New Zealand': 'NZ', 'South Africa': 'ZA', 'Nigeria': 'NG',
    'Israel': 'IL', 'Turkey': 'TR', 'India': 'IN', 'China': 'CN',
    'Taiwan': 'TW', 'Thailand': 'TH', 'Philippines': 'PH', 'Indonesia': 'ID',
    'Malaysia': 'MY', 'Singapore': 'SG', 'Vietnam': 'VN', 'Hong Kong': 'HK',
    'Puerto Rico': 'PR', 'Jamaica': 'JM', 'Cuba': 'CU', 'Trinidad and Tobago': 'TT',
    'Russia': 'RU', 'Ukraine': 'UA', 'Romania': 'RO', 'Hungary': 'HU',
    'Czech Republic': 'CZ', 'Slovakia': 'SK', 'Croatia': 'HR', 'Serbia': 'RS',
    'Bulgaria': 'BG', 'Slovenia': 'SI', 'Lithuania': 'LT', 'Latvia': 'LV',
    'Estonia': 'EE', 'Greece': 'GR', 'Georgia': 'GE', 'Armenia': 'AM',
    'Azerbaijan': 'AZ', 'Lebanon': 'LB', 'Jordan': 'JO', 'Egypt': 'EG',
    'Morocco': 'MA', 'Tunisia': 'TN', 'Kenya': 'KE', 'Tanzania': 'TZ',
    'Ghana': 'GH', 'Senegal': 'SN', 'Peru': 'PE', 'Ecuador': 'EC',
    'Venezuela': 'VE', 'Uruguay': 'UY', 'Paraguay': 'PY', 'Bolivia': 'BO',
    'Costa Rica': 'CR', 'Panama': 'PA', 'Honduras': 'HN', 'Guatemala': 'GT',
    'El Salvador': 'SV', 'Nicaragua': 'NI', 'Dominican Republic': 'DO',
    'Mongolia': 'MN', 'Kazakhstan': 'KZ', 'Pakistan': 'PK', 'Bangladesh': 'BD',
    'Sri Lanka': 'LK', 'Nepal': 'NP', 'Cambodia': 'KH', 'Laos': 'LA',
    'Myanmar': 'MM', 'Papua New Guinea': 'PG', 'Fiji': 'FJ',
    'Moldova': 'MD', 'Belarus': 'BY', 'Cyprus': 'CY', 'Malta': 'MT',
    'Luxembourg': 'LU', 'Monaco': 'MC', 'Liechtenstein': 'LI', 'Andorra': 'AD',
    'San Marino': 'SM', 'Albania': 'AL', 'Bosnia and Herzegovina': 'BA',
    'Montenegro': 'ME', 'Macedonia': 'MK', 'Kosovo': 'XK',
}


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
    """Get all unmapped artist names from the CSV, with song counts."""
    ci = {k.lower(): v for k, v in cache.items() if v}
    unmapped = {}
    
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            artist = (row.get('artist') or '').strip()
            if not artist:
                title = row.get('title', '')
                if ' - ' in title:
                    artist = title.rsplit(' - ', 1)[1].strip()
                elif chr(0x2013) in title:
                    artist = title.rsplit(chr(0x2013), 1)[1].strip()
            if artist:
                code = cache.get(artist, '') or ci.get(artist.lower(), '')
                if not code:
                    unmapped[artist] = unmapped.get(artist, 0) + 1
    
    return unmapped


def estimate_coverage(cache):
    ci = {k.lower(): v for k, v in cache.items() if v}
    total = 0
    mapped = 0
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
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
                code = cache.get(artist, '') or ci.get(artist.lower(), '')
                if code:
                    mapped += 1
    return mapped / total if total else 0


def lookup_artist(name):
    """Look up artist on MusicBrainz, then area for ISO code."""
    clean = name.strip().strip('"').strip("'")
    # Remove feat./ft. suffixes
    clean = re.sub(r'\s*[,*]?\s*ft\.?.*$', '', clean, flags=re.I).strip()
    clean = re.sub(r'\s*[,*]?\s*feat\.?.*$', '', clean, flags=re.I).strip()
    # Remove HTML tags
    clean = re.sub(r'<[^>]+>', '', clean).strip()
    # Remove dates in parens
    clean = re.sub(r'\s*\(\d{4}\)\s*$', '', clean).strip()
    # Remove 'covered by' prefix
    clean = re.sub(r'^covered\s+by\s+', '', clean, flags=re.I).strip()
    # Remove brackets
    clean = re.sub(r'[\[\]【】『』]', '', clean).strip()
    
    if not clean or len(clean) < 2 or len(clean) > 80:
        return None
    
    # Skip obvious non-artist entries
    skip_patterns = [
        r'^\d+/\d+',  # dates
        r'^\d+$',  # pure numbers
        r'weekly', r'discovery', r'review', r'playlist',
        r'announcement', r'blog', r'youtube', r'project',
        r'click', r'game', r'video', r'movie',
    ]
    if any(re.search(p, clean.lower()) for p in skip_patterns):
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
                    # Name similarity check
                    if (clean_lower in mb_name or mb_name in clean_lower or
                        len(set(clean_lower.split()) & set(mb_name.split())) >= 1):
                        # Check area directly
                        area = artist.get('area', {})
                        codes = area.get('iso-3166-1-codes', [])
                        if codes:
                            return codes[0]
                        # Check begin-area
                        begin_area = artist.get('begin-area', {})
                        codes = begin_area.get('iso-3166-1-codes', [])
                        if codes:
                            return codes[0]
                        # Try name mapping
                        area_name = area.get('name', '')
                        if area_name in COUNTRY_NAME_TO_CODE:
                            return COUNTRY_NAME_TO_CODE[area_name]
                        return None
    except Exception as e:
        if '503' in str(e) or '429' in str(e):
            return None
    return None


def main():
    start_time = time.time()
    cache = load_cache()
    
    unmapped = get_unmapped_artists(cache)
    # Sort by song count (most songs first)
    to_lookup = sorted(unmapped.items(), key=lambda x: -x[1])
    
    print(f"Start: {len(to_lookup)} unmapped artists, {sum(unmapped.values())} songs", flush=True)
    print(f"Current coverage: {estimate_coverage(cache)*100:.1f}%", flush=True)
    
    found = 0
    errors = 0
    looked_up = set()
    
    for i, (name, count) in enumerate(to_lookup):
        elapsed = time.time() - start_time
        if elapsed > MAX_SECONDS:
            print(f"\nTime limit reached ({elapsed:.0f}s)", flush=True)
            break
        
        current_cov = estimate_coverage(cache)
        if current_cov >= TARGET_COVERAGE:
            print(f"\nTarget coverage reached ({current_cov*100:.1f}%)", flush=True)
            break
        
        # Skip if already looked up (case-insensitive)
        if name.lower() in looked_up:
            continue
        looked_up.add(name.lower())
        
        # Progress report every 20 lookups
        if i > 0 and i % 20 == 0:
            elapsed = time.time() - start_time
            print(f"  [{elapsed:.0f}s] {i}/{len(to_lookup)} (found={found} errors={errors}) coverage={estimate_coverage(cache)*100:.1f}%", flush=True)
            save_cache(cache)
        
        code = lookup_artist(name)
        if code:
            cache[name] = code
            found += 1
            if count >= 2:
                print(f"  FOUND: {name} -> {code} ({count} songs)", flush=True)
        else:
            cache[name] = ''
            errors += 1
        
        time.sleep(1.2)
    
    save_cache(cache)
    elapsed = time.time() - start_time
    final_cov = estimate_coverage(cache)
    mapped = sum(1 for v in cache.values() if v)
    
    print(f"\nDone in {elapsed:.0f}s", flush=True)
    print(f"Cache: {len(cache)} entries, {mapped} with country", flush=True)
    print(f"Final coverage: {final_cov*100:.1f}%", flush=True)
    print(f"Found: {found} new, Errors: {errors}", flush=True)


if __name__ == '__main__':
    main()
