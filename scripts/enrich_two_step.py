#!/usr/bin/env python3
"""Two-step MusicBrainz enrichment: artist lookup → area lookup for ISO codes."""

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
MAX_SECONDS = 3600
TARGET_COVERAGE = 0.80

# Country name to ISO code mapping (for when area lookup fails)
COUNTRY_NAME_TO_CODE = {
    'United States': 'US', 'United Kingdom': 'GB', 'Canada': 'CA',
    'Australia': 'AU', 'Japan': 'JP', 'South Korea': 'KR',
    'Germany': 'DE', 'France': 'FR', 'Italy': 'IT', 'Spain': 'ES',
    'Netherlands': 'NL', 'Sweden': 'SE', 'Norway': 'NO', 'Denmark': 'DK',
    'Finland': 'FI', 'Iceland': 'IS', 'Ireland': 'IE', 'Belgium': 'BE',
    'Switzerland': 'CH', 'Austria': 'AT', 'Portugal': 'PT', 'Poland': 'PL',
    'Czech Republic': 'CZ', 'Hungary': 'HU', 'Romania': 'RO',
    'Brazil': 'BR', 'Argentina': 'AR', 'Mexico': 'MX', 'Colombia': 'CO',
    'Chile': 'CL', 'Peru': 'PE', 'New Zealand': 'NZ',
    'South Africa': 'ZA', 'Nigeria': 'NG', 'Ghana': 'GH',
    'Israel': 'IL', 'Turkey': 'TR', 'India': 'IN', 'China': 'CN',
    'Taiwan': 'TW', 'Thailand': 'TH', 'Philippines': 'PH',
    'Indonesia': 'ID', 'Malaysia': 'MY', 'Singapore': 'SG',
    'Vietnam': 'VN', 'Hong Kong': 'HK', 'Puerto Rico': 'PR',
    'Jamaica': 'JM', 'Cuba': 'CU', 'Trinidad and Tobago': 'TT',
    'Kazakhstan': 'KZ', 'Ukraine': 'UA', 'Russia': 'RU',
    'Bulgaria': 'BG', 'Slovakia': 'SK', 'Slovenia': 'SI',
    'Croatia': 'HR', 'Serbia': 'RS', 'Lithuania': 'LT',
    'Latvia': 'LV', 'Estonia': 'EE', 'Cyprus': 'CY',
    'Malta': 'MT', 'Luxembourg': 'LU', 'Monaco': 'MC',
    'Liechtenstein': 'LI', 'Andorra': 'AD', 'San Marino': 'SM',
    'Vatican City': 'VA', 'Greece': 'GR', 'Macedonia': 'MK',
    'Albania': 'AL', 'Bosnia and Herzegovina': 'BA', 'Montenegro': 'ME',
    'Kosovo': 'XK', 'Moldova': 'MD', 'Belarus': 'BY',
    'Georgia': 'GE', 'Armenia': 'AM', 'Azerbaijan': 'AZ',
    'Lebanon': 'LB', 'Jordan': 'JO', 'Iraq': 'IQ',
    'Iran': 'IR', 'Saudi Arabia': 'SA', 'United Arab Emirates': 'AE',
    'Egypt': 'EG', 'Morocco': 'MA', 'Tunisia': 'TN',
    'Algeria': 'DZ', 'Kenya': 'KE', 'Tanzania': 'TZ',
    'Ethiopia': 'ET', 'Uganda': 'UG', 'Senegal': 'SN',
    'Cameroon': 'CM', 'Ivory Coast': 'CI', 'Mali': 'ML',
    'Burkina Faso': 'BF', 'Niger': 'NE', 'Chad': 'TD',
    'Guinea': 'GN', 'Benin': 'BJ', 'Togo': 'TG',
    'Sierra Leone': 'SL', 'Liberia': 'LR', 'Gambia': 'GM',
    'Guinea-Bissau': 'GW', 'Cape Verde': 'CV', 'Mauritania': 'MR',
    'Central African Republic': 'CF', 'Equatorial Guinea': 'GQ',
    'Gabon': 'GA', 'Republic of the Congo': 'CG',
    'Democratic Republic of the Congo': 'CD', 'São Tomé and Príncipe': 'ST',
    'Rwanda': 'RW', 'Burundi': 'BI', 'Somalia': 'SO',
    'Djibouti': 'DJ', 'Eritrea': 'ER', 'Sudan': 'SD',
    'South Sudan': 'SS', 'Libya': 'LY', 'Mauritius': 'MU',
    'Seychelles': 'SC', 'Comoros': 'KM', 'Madagascar': 'MG',
    'Malawi': 'MW', 'Zambia': 'ZM', 'Zimbabwe': 'ZW',
    'Mozambique': 'MZ', 'Angola': 'AO', 'Namibia': 'NA',
    'Botswana': 'BW', 'Lesotho': 'LS', 'Eswatini': 'SZ',
    'Costa Rica': 'CR', 'Panama': 'PA', 'Honduras': 'HN',
    'Guatemala': 'GT', 'El Salvador': 'SV', 'Nicaragua': 'NI',
    'Belize': 'BZ', 'Trinidad': 'TT', 'Barbados': 'BB',
    'Guyana': 'GY', 'Suriname': 'SR', 'French Guiana': 'GF',
    'Uruguay': 'UY', 'Paraguay': 'PY', 'Bolivia': 'BO',
    'Ecuador': 'EC', 'Venezuela': 'VE',
    'Papua New Guinea': 'PG', 'Fiji': 'FJ', 'Samoa': 'WS',
    'Tonga': 'TO', 'Vanuatu': 'VU', 'Solomon Islands': 'SB',
    'Micronesia': 'FM', 'Palau': 'PW', 'Marshall Islands': 'MH',
    'Kiribati': 'KI', 'Nauru': 'NR', 'Tuvalu': 'TV',
    'Mongolia': 'MN', 'Kyrgyzstan': 'KG', 'Uzbekistan': 'UZ',
    'Tajikistan': 'TJ', 'Turkmenistan': 'TM', 'Afghanistan': 'AF',
    'Pakistan': 'PK', 'Bangladesh': 'BD', 'Sri Lanka': 'LK',
    'Nepal': 'NP', 'Bhutan': 'BT', 'Myanmar': 'MM',
    'Cambodia': 'KH', 'Laos': 'LA',
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

def get_unmapped(cache):
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
    import csv
    total = 0
    mapped = 0
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

def lookup_area(area_id):
    """Look up area to get ISO country code."""
    url = f'https://musicbrainz.org/ws/2/area/{area_id}?fmt=json'
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            # Try ISO codes first
            codes = data.get('iso-3166-1-codes', [])
            if codes:
                return codes[0]
            # Try name mapping
            name = data.get('name', '')
            if name in COUNTRY_NAME_TO_CODE:
                return COUNTRY_NAME_TO_CODE[name]
    except Exception:
        pass
    return None

def lookup_artist(name):
    """Look up artist on MusicBrainz, then area for ISO code."""
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
                        # Step 1: Check artist area directly
                        area = artist.get('area', {})
                        codes = area.get('iso-3166-1-codes', [])
                        if codes:
                            return codes[0]
                        # Step 2: Check begin-area
                        begin_area = artist.get('begin-area', {})
                        codes = begin_area.get('iso-3166-1-codes', [])
                        if codes:
                            return codes[0]
                        # Step 3: Look up area by ID
                        area_id = area.get('id')
                        if area_id:
                            code = lookup_area(area_id)
                            if code:
                                return code
                        # Step 4: Try name mapping
                        area_name = area.get('name', '')
                        if area_name in COUNTRY_NAME_TO_CODE:
                            return COUNTRY_NAME_TO_CODE[area_name]
    except Exception as e:
        if '503' in str(e) or '429' in str(e):
            return None
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
        elapsed = time.time() - start_time
        if elapsed > MAX_SECONDS:
            print(f"\nTime limit reached ({elapsed:.0f}s)", flush=True)
            break
        
        current_cov = estimate_coverage(cache)
        if current_cov >= TARGET_COVERAGE:
            print(f"\nTarget coverage reached ({current_cov*100:.1f}%)", flush=True)
            break
        
        if i > 0 and i % 10 == 0:
            elapsed = time.time() - start_time
            print(f"  [{elapsed:.0f}s] Progress: {i}/{len(to_lookup)} (found={found} errors={errors}) coverage={current_cov*100:.1f}%", flush=True)
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

if __name__ == '__main__':
    main()
