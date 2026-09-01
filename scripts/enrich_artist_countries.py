#!/usr/bin/env python3
"""
enrich_artist_countries.py
Look up each unique artist's country of origin via MusicBrainz API.
Caches results to data/artist_country_cache.json so the live app
can show geographic listening distribution offline.

MusicBrainz API: free, no auth, 1 req/sec rate limit.
Usage:
    python scripts/enrich_artist_countries.py [--limit N] [--report]
"""

import csv
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from typing import Optional

CACHE_PATH = 'data/artist_country_cache.json'
CSV_PATH = 'data/posts_tails.csv'

# ISO country code → friendly name + region
COUNTRY_META = {
    'US': {'name': 'United States', 'region': 'North America'},
    'GB': {'name': 'United Kingdom', 'region': 'Europe'},
    'CA': {'name': 'Canada', 'region': 'North America'},
    'AU': {'name': 'Australia', 'region': 'Oceania'},
    'JP': {'name': 'Japan', 'region': 'Asia'},
    'KR': {'name': 'South Korea', 'region': 'Asia'},
    'DE': {'name': 'Germany', 'region': 'Europe'},
    'FR': {'name': 'France', 'region': 'Europe'},
    'IT': {'name': 'Italy', 'region': 'Europe'},
    'ES': {'name': 'Spain', 'region': 'Europe'},
    'BR': {'name': 'Brazil', 'region': 'South America'},
    'MX': {'name': 'Mexico', 'region': 'North America'},
    'AR': {'name': 'Argentina', 'region': 'South America'},
    'CO': {'name': 'Colombia', 'region': 'South America'},
    'CL': {'name': 'Chile', 'region': 'South America'},
    'SE': {'name': 'Sweden', 'region': 'Europe'},
    'NO': {'name': 'Norway', 'region': 'Europe'},
    'DK': {'name': 'Denmark', 'region': 'Europe'},
    'FI': {'name': 'Finland', 'region': 'Europe'},
    'NL': {'name': 'Netherlands', 'region': 'Europe'},
    'BE': {'name': 'Belgium', 'region': 'Europe'},
    'CH': {'name': 'Switzerland', 'region': 'Europe'},
    'AT': {'name': 'Austria', 'region': 'Europe'},
    'IE': {'name': 'Ireland', 'region': 'Europe'},
    'PT': {'name': 'Portugal', 'region': 'Europe'},
    'PL': {'name': 'Poland', 'region': 'Europe'},
    'CZ': {'name': 'Czech Republic', 'region': 'Europe'},
    'HU': {'name': 'Hungary', 'region': 'Europe'},
    'RO': {'name': 'Romania', 'region': 'Europe'},
    'GR': {'name': 'Greece', 'region': 'Europe'},
    'RU': {'name': 'Russia', 'region': 'Europe'},
    'UA': {'name': 'Ukraine', 'region': 'Europe'},
    'TR': {'name': 'Turkey', 'region': 'Asia'},
    'IN': {'name': 'India', 'region': 'Asia'},
    'CN': {'name': 'China', 'region': 'Asia'},
    'TW': {'name': 'Taiwan', 'region': 'Asia'},
    'TH': {'name': 'Thailand', 'region': 'Asia'},
    'PH': {'name': 'Philippines', 'region': 'Asia'},
    'ID': {'name': 'Indonesia', 'region': 'Asia'},
    'MY': {'name': 'Malaysia', 'region': 'Asia'},
    'SG': {'name': 'Singapore', 'region': 'Asia'},
    'VN': {'name': 'Vietnam', 'region': 'Asia'},
    'ZA': {'name': 'South Africa', 'region': 'Africa'},
    'NG': {'name': 'Nigeria', 'region': 'Africa'},
    'KE': {'name': 'Kenya', 'region': 'Africa'},
    'GH': {'name': 'Ghana', 'region': 'Africa'},
    'EG': {'name': 'Egypt', 'region': 'Africa'},
    'MA': {'name': 'Morocco', 'region': 'Africa'},
    'NZ': {'name': 'New Zealand', 'region': 'Oceania'},
    'IL': {'name': 'Israel', 'region': 'Asia'},
    'LB': {'name': 'Lebanon', 'region': 'Asia'},
    'CU': {'name': 'Cuba', 'region': 'North America'},
    'JM': {'name': 'Jamaica', 'region': 'North America'},
    'TT': {'name': 'Trinidad and Tobago', 'region': 'North America'},
    'PR': {'name': 'Puerto Rico', 'region': 'North America'},
    'DO': {'name': 'Dominican Republic', 'region': 'North America'},
    'VE': {'name': 'Venezuela', 'region': 'South America'},
    'PE': {'name': 'Peru', 'region': 'South America'},
    'EC': {'name': 'Ecuador', 'region': 'South America'},
    'UY': {'name': 'Uruguay', 'region': 'South America'},
    'IS': {'name': 'Iceland', 'region': 'Europe'},
    'HR': {'name': 'Croatia', 'region': 'Europe'},
    'RS': {'name': 'Serbia', 'region': 'Europe'},
    'BG': {'name': 'Bulgaria', 'region': 'Europe'},
    'SK': {'name': 'Slovakia', 'region': 'Europe'},
    'SI': {'name': 'Slovenia', 'region': 'Europe'},
    'LT': {'name': 'Lithuania', 'region': 'Europe'},
    'LV': {'name': 'Latvia', 'region': 'Europe'},
    'EE': {'name': 'Estonia', 'region': 'Europe'},
}


def extract_artists(title: str) -> list:
    """Extract artist names from song title (simplified version of TasteEngine._extract_artists)."""
    if not title:
        return []
    results = []
    # Pattern 1: Title (Artist, Year)
    m = re.search(r'\(([^)]+),\s*\d{4}\)', title)
    if m:
        return [m.group(1).strip()]
    # Pattern 2: Artist – Song
    m = re.match(r'^(.+?)\s*[–-]\s+(.+)$', title)
    if m:
        return [m.group(1).strip().rstrip(',').strip('"').strip("'").strip()]
    # Pattern 3: Song by Artist
    m = re.search(r'\s+by\s+(.+)$', title)
    if m:
        return [m.group(1).strip().rstrip('.').strip('"').strip("'").strip()]
    # Pattern 4: Artist: Song
    m = re.match(r'^([A-Za-z0-9][A-Za-z0-9\s.]+?):\s+', title)
    if m:
        return [m.group(1).strip()]
    return []


def load_cache() -> dict:
    """Load existing country cache from disk."""
    try:
        with open(CACHE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_cache(cache: dict):
    """Persist country cache to disk."""
    with open(CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, indent=2, ensure_ascii=True)


def lookup_artist_country(artist: str) -> Optional[str]:
    """Look up an artist's country of origin via MusicBrainz API.
    Returns ISO country code or None.
    """
    clean = artist.strip().strip('"').strip("'")
    # Strip ft./feat. from artist name
    clean = re.sub(r'\s*[,*]?\s*ft\.?.*$', '', clean, flags=re.I).strip()
    clean = re.sub(r'\s*[,*]?\s*feat\.?.*$', '', clean, flags=re.I).strip()
    if not clean or len(clean) < 2:
        return None

    query = urllib.parse.quote(f'artist:"{clean}"')
    url = f'https://musicbrainz.org/ws/2/artist/?query={query}&fmt=json&limit=3'

    for retry in range(2):
        req = urllib.request.Request(url, headers={
            'User-Agent': 'TasteScope/1.0 (music-analyzer; contact: tastescope@example.com)',
            'Accept': 'application/json'
        })
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))

            for artist_info in data.get('artists', []):
                mb_name = (artist_info.get('name') or '').lower()
                search_name = clean.lower()

                # Accept if names match closely (first result from search is usually correct)
                # Also accept if one contains the other (handles parenthetical suffixes)
                name_match = (
                    mb_name == search_name or
                    mb_name in search_name or
                    search_name in mb_name or
                    # First result from MusicBrainz search is almost always the right artist
                    data.get('artists', [{}])[0] is artist_info
                )

                if not name_match:
                    continue

                # Get country from 'country' field
                country = artist_info.get('country', '')
                if country and len(country) == 2:
                    return country

                # If no country, try area → walk up to country
                area = artist_info.get('area', {})
                if area and area.get('id'):
                    country = walk_area_to_country(area['id'])
                    if country:
                        return country

                # Try begin-area
                begin_area = artist_info.get('begin-area', {})
                if begin_area and begin_area.get('id'):
                    country = walk_area_to_country(begin_area['id'])
                    if country:
                        return country

            return None

        except urllib.error.HTTPError as e:
            if e.code == 503 and retry == 0:
                time.sleep(3)
                continue
            return None
        except Exception:
            return None

    return None


def walk_area_to_country(area_id: str, max_depth: int = 5) -> Optional[str]:
    """Walk up the MusicBrainz area hierarchy to find the country."""
    url = f'https://musicbrainz.org/ws/2/area/{area_id}?inc=area-rels&fmt=json'
    req = urllib.request.Request(url, headers={
        'User-Agent': 'TasteScope/1.0 (music-analyzer; contact: tastescope@example.com)',
        'Accept': 'application/json'
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))

        # Check if this area IS a country
        if data.get('type') == 'Country':
            iso = data.get('iso-3166-1-code-list', [])
            if iso:
                return iso[0]

        # Walk up: find "part of" relationship
        for rel in data.get('relations', []):
            if (rel.get('target-type') == 'area' and
                rel.get('type') == 'part of' and
                rel.get('direction') == 'backward'):
                target = rel.get('area', {})
                if target.get('type') == 'Country':
                    iso = target.get('iso-3166-1-code-list', [])
                    if iso:
                        return iso[0]
                elif max_depth > 0 and target.get('id'):
                    time.sleep(1.1)  # Rate limit
                    return walk_area_to_country(target['id'], max_depth - 1)

    except Exception:
        pass
    return None


def get_unique_artists() -> list:
    """Extract all unique artists from the CSV."""
    artists = set()
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            title = row.get('title', '')
            for artist in extract_artists(title):
                if artist and len(artist) > 1:
                    artists.add(artist)
    return sorted(artists)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Enrich artist database with country data')
    parser.add_argument('--limit', type=int, default=0, help='Limit number of lookups (0=all)')
    parser.add_argument('--report', action='store_true', help='Print report of cached data')
    parser.add_argument('--force', action='store_true', help='Re-fetch even if cached')
    args = parser.parse_args()

    cache = load_cache()

    if args.report:
        print(f'Cached artists: {len(cache)}')
        # Count by region
        region_counts = Counter()
        country_counts = Counter()
        for code in cache.values():
            meta = COUNTRY_META.get(code, {'name': code, 'region': 'Unknown'})
            region_counts[meta['region']] += 1
            country_counts[meta['name']] += 1

        print(f'\nBy region:')
        for region, count in region_counts.most_common():
            print(f'  {region}: {count}')

        print(f'\nTop countries:')
        for country, count in country_counts.most_common(15):
            print(f'  {country}: {count}')

        return

    artists = get_unique_artists()
    print(f'Total unique artists: {len(artists)}')

    # Filter to uncached
    to_lookup = [a for a in artists if a not in cache or args.force]
    if args.limit:
        to_lookup = to_lookup[:args.limit]

    print(f'Artists to look up: {len(to_lookup)}')
    if not to_lookup:
        print('All artists already cached. Use --force to re-fetch.')
        return

    found = 0
    not_found = 0
    for i, artist in enumerate(to_lookup):
        country = lookup_artist_country(artist)
        if country:
            cache[artist] = country
            found += 1
        else:
            cache[artist] = ''  # Mark as looked up but not found
            not_found += 1

        if (i + 1) % 10 == 0:
            print(f'  [{i+1}/{len(to_lookup)}] found={found} not_found={not_found}')
            save_cache(cache)

        # Rate limit: MusicBrainz requires 1 req/sec
        time.sleep(1.1)

    save_cache(cache)
    print(f'\nDone. Found={found}, Not found={not_found}')
    print(f'Total cached: {len(cache)}')


if __name__ == '__main__':
    main()
