#!/usr/bin/env python3
"""Smart MusicBrainz enrichment — look up unmapped artists with rate limiting."""
import json, os, re, sys, time, urllib.request, urllib.parse, signal

CACHE_PATH = 'data/artist_country_cache.json'
LOG_PATH = '.freebuff/enrich_smart.log'

# Minimum artist name length
MIN_NAME_LEN = 3

# Song titles / non-artist patterns to skip
SKIP_PATTERNS = [
    r'^\d+(/\d+)?$',  # dates like 4/16/18
    r'^Announcement',
    r'^Battle of',
    r'^Musicord',
    r'^\?+$',
    r'^A fun game',
    r'^Experimenting',
    r'^Current Listening',
    r'^Chat GPT',
    r'^Musicord',
    r'^Alphabetical',
    r'^Complete .* Collection',
    r'^Worldwide Listening',
]

def is_likely_artist(name):
    """Filter out obvious non-artist names."""
    n = name.strip()
    if len(n) < MIN_NAME_LEN:
        return False
    for pat in SKIP_PATTERNS:
        if re.match(pat, n, re.I):
            return False
    # Skip HTML
    if '<' in n or '>' in n or 'href=' in n:
        return False
    # Skip dates
    if re.match(r'^\d{1,2}/\d{1,2}(/\d{2,4})?$', n):
        return False
    return True

def lookup_musicbrainz(artist):
    """Look up artist country via MusicBrainz. Returns ISO code or None."""
    clean = artist.strip().strip('"').strip("'")
    # Strip ft./feat.
    clean = re.sub(r'\s*[,*]?\s*ft\.?.*$', '', clean, flags=re.I).strip()
    clean = re.sub(r'\s*[,*]?\s*feat\.?.*$', '', clean, flags=re.I).strip()
    if not clean or len(clean) < 2:
        return None

    # URL encode the query
    query = urllib.parse.urlencode({
        'query': f'artist:"{clean}"',
        'fmt': 'json',
        'limit': 3
    })
    url = f'https://musicbrainz.org/ws/2/artist/?{query}'

    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'TasteScope/1.0 (tastescope@example.com)',
            'Accept': 'application/json'
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))

        if not data.get('artists'):
            return None

        # Check each result for a match
        for art in data['artists']:
            art_name = art.get('name', '').lower()
            # Fuzzy match — accept if names are similar
            if clean.lower() in art_name or art_name in clean.lower():
                areas = art.get('area', {})
                if areas and areas.get('iso-3166-1-codes'):
                    return areas['iso-3166-1-codes'][0]
                # Try begin-area
                begin = art.get('begin-area', {})
                if begin and begin.get('iso-3166-1-codes'):
                    return begin['iso-3166-1-codes'][0]
                # Try country field
                country = art.get('country', '')
                if country:
                    return country
                return None
        return None
    except Exception as e:
        return None

def main():
    # Load cache
    with open(CACHE_PATH, 'r', encoding='utf-8') as f:
        cache = json.load(f)

    # Build CI index
    ci = {k.lower(): v for k, v in cache.items() if v}

    # Get unmapped artists
    sys.path.insert(0, '.')
    from src.taste_engine import TasteEngine
    te = TasteEngine()

    unmapped = set()
    for r in te.rows:
        artists = te._extract_artists_from_row(r)
        for a in artists:
            a = a.strip()
            if not a or len(a) < MIN_NAME_LEN:
                continue
            code = cache.get(a, '') or ci.get(a.lower(), '')
            if not code and is_likely_artist(a):
                unmapped.add(a)

    print(f'Found {len(unmapped)} unmapped artists to look up')
    with open(LOG_PATH, 'w', encoding='utf-8') as f:
        f.write(f'Started enrichment at {time.strftime("%Y-%m-%d %H:%M:%S")}\n')
        f.write(f'Artists to look up: {len(unmapped)}\n')

    found = 0
    not_found = 0
    errors = 0
    start_time = time.time()
    max_duration = 3600  # 1 hour

    for i, artist in enumerate(sorted(unmapped)):
        # Check timeout
        if time.time() - start_time > max_duration:
            print(f'Time limit reached ({max_duration}s)')
            break

        country = lookup_musicbrainz(artist)
        if country:
            cache[artist] = country
            ci[artist.lower()] = country
            found += 1
            msg = f'  [{i+1}/{len(unmapped)}] FOUND: {artist} -> {country}'
        else:
            cache[artist] = ''  # Mark as looked up
            not_found += 1
            msg = f'  [{i+1}/{len(unmapped)}] miss: {artist}'

        if (i + 1) % 10 == 0:
            elapsed = time.time() - start_time
            print(f'[{i+1}/{len(unmapped)}] found={found} miss={not_found} elapsed={elapsed:.0f}s')
            # Save periodically
            with open(CACHE_PATH, 'w', encoding='utf-8') as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)

        # Rate limit: MusicBrainz allows 1 req/sec
        time.sleep(1.2)

    # Final save
    with open(CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    elapsed = time.time() - start_time
    msg = f'Done: found={found} miss={not_found} elapsed={elapsed:.0f}s'
    print(msg)
    with open(LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(msg + '\n')

if __name__ == '__main__':
    main()
