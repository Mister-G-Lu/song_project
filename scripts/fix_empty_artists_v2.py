#!/usr/bin/env python3
"""Fix remaining empty artist rows with aggressive pattern matching."""
import csv, re, os

CSV_PATH = 'data/posts_tails.csv'

# Non-song entries to mark as 'Announcement' (will be filtered by TasteEngine)
NON_SONG_PATTERNS = [
    r'^Announcement',
    r"'s Weekly Discovery",
    r"'s Spotify",
    r'Youtube top \d+',
    r'^Battle of the',
    r'^Musicord ',
    r'^Music Personality',
    r'^Curated Song',
    r'^First added songs',
    r'^Ancora.*Battle',
    r'^various.*review',
    r'^Worldwide Listening',
    r'^Papermoon VS',
    r'^Lindsey Stirling.*Review',
    r'^Complete .* Collection',
    r'^Rap/Hip hop',
    r'^Alphabetical',
    r'^Flower of Hell VS',
    r'^my "chill',
    r'^full country',
    r'^Game Promotion',
    r'^one hit song',
    r'^Favorite Artists',
    r'^Chat GPT',
    r'^Scissor Seven Opening',
    r'^Dot Hack Sign',
    r'^Fate/Zero OP',
    r'^Amphibia Theme',
    r'^Sheet Music Boss',
    r'^Never Shall Forget',
    r'^RED ~ What You Keep',
    r'^"Contrast" pairs',
    r'^Mashup of every',
    r'^Mr Melodramatic',
]

# Artist extraction patterns: (regex, artist_group)
EXTRACT_PATTERNS = [
    # 『Song』by Artist or 「Song」by Artist
    (re.compile(r'『(.+?)』\s*by\s+(.+)'), 2),
    (re.compile(r'「(.+?)」\s*by\s+(.+)'), 2),
    # 【Artist】Song
    (re.compile(r'【([^】]+)】'), 1),
    # [Artist] Song
    (re.compile(r'\[([^\]]+)\]\s+'), 1),
    # Song (Artist) — without comma before year
    (re.compile(r'^(.+?)\s*\(([^,)]+)\)\s*$'), 2),
    # "Song", Artist
    (re.compile(r'^"[^"]*"\s*,\s*(.+)$'), 1),
    # Artist\t"Song" (tab separated)
    (re.compile(r'^([^\t]+)\t'), 1),
    # Song ／ Artist
    (re.compile(r'(.+)\s*／\s*(.+)'), 2),
    # Song by Artist
    (re.compile(r'^(.+?)\s+by\s+(.+)$', re.I), 2),
    # TitleArtist (no separator, last known word pattern)
    # "Bad Blood Taylor Swift" → Taylor Swift
]

# Manual fixes for hard-to-parse titles
MANUAL_FIXES = {
    'Boop (Casey Lee Williams)': 'Casey Lee Williams',
    'Not All Heroes Wear Capes': '',
    'when || dodie': 'dodie',
    'This Is Me (from The Greatest Showman)': '',
    '人中之龙 (Piano Song)': '',
    'Danse Macabre (Dance of Death)': '',
    'Dirty Work Austin Mahone': 'Austin Mahone',
    'Funky Monday': '',
    'Anybody\'s You" Christina Grimmie': 'Christina Grimmie',
    'Phantom of the Opera Lindsey Stirling': 'Lindsey Stirling',
    'Girls\' Generation 소녀시대 \'The Boys\'': 'Girls\' Generation',
    'Bad Blood Taylor Swift': 'Taylor Swift',
    'What a girl is Dove Cameron': 'Dove Cameron',
    'Battle of the 98\'s': '',
    'Battle of the 96\'s': '',
    'Battle of the 95\'s': '',
    'Battle of 92\'s': '',
    'Battle of the 91\'s': '',
    'Battle of the 90\'s': '',
    'Battle of the 88\'s': '',
    'Battle of the 87\'s': '',
    'Battle of the 85\'s': '',
    'Battle of the 84\'s': '',
    'Battle of the 86\'s': '',
    'Battle of the 100\'s': '',
    'Battle of the 83\'s': '',
    'Battle of the 82\'s': '',
    'Battle of the 81\'s': '',
    'Battle of the 80\'s': '',
    'Battle of the 72\'s': '',
    'Battle of the 89\'s': '',
    'Battle of the 97\'s': '',
    'Battle of the 70\'s': '',
    'Battle of the 60\'s': '',
    'Battle of the 50\'s': '',
    'Battle of the 40\'s': '',
    'Battle of the 30\'s': '',
    'Battle of the 20\'s': '',
    'Battle of the 10\'s': '',
    'Gong Xi Gong Xi': '',
    'Marine Corp Hymn': '',
    'Amen, Brother': '',
    'Ballad of Robin Hood': '',
    'Karma (is a Bitch)': '',
    'Teach The World To Sing (In Perfect Harmony)': 'New Seekers',
    'Mr Blobby", Mr Blobby': 'Mr Blobby',
    'Kimiro Iro Utsuri': '',
    'Late Night Tales': '',
    'Hidden Falls': '',
    'cafe de Touhou': '',
}

def is_non_song(title):
    for pat in NON_SONG_PATTERNS:
        if re.match(pat, title, re.I):
            return True
    return False

def extract_artist(title):
    # Check manual fixes first
    for key, val in MANUAL_FIXES.items():
        if key in title:
            return val
    
    for pattern, group in EXTRACT_PATTERNS:
        m = pattern.search(title)
        if m:
            candidate = m.group(group).strip().strip('"').strip("'")
            # Skip if it's clearly not an artist
            if any(x in candidate.lower() for x in ['spotify', 'weekly', 'review', 'collection', 'battle', 'challenge', 'playlist', 'from the', 'piano song']):
                continue
            if len(candidate) >= 2:
                return candidate
    return ''

def main():
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    fixed = 0
    for row in rows:
        if row.get('artist', '').strip():
            continue
        title = row.get('title', '').strip()
        if not title:
            continue
        
        if is_non_song(title):
            row['artist'] = 'Announcement'
            fixed += 1
            continue
        
        artist = extract_artist(title)
        if artist:
            row['artist'] = artist
            fixed += 1

    with open(CSV_PATH, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)

    print(f'Fixed {fixed} rows')

if __name__ == '__main__':
    main()
