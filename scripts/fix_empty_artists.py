#!/usr/bin/env python3
"""Fix CSV rows with empty artist column by re-parsing titles with aggressive patterns."""
import csv, re, sys, os

CSV_PATH = 'data/posts_tails.csv'

# Patterns that strongly indicate "Artist" in the title
# (artist name follows the separator)
AGGRESSIVE_PATTERNS = [
    # "Title- Artist" (dash with or without spaces)
    (re.compile(r'^(.+?)\s*[-–—]\s*(.+)$'), 2),
    # "Title · Artist" or "Title • Artist"
    (re.compile(r'^(.+?)\s*[·•]\s*(.+)$'), 2),
    # "Title「Artist」" or "Title【Artist】"
    (re.compile(r'^(.+?)\s*[「『【](.+?)[」』】]'), 2),
    # "Title » Artist"
    (re.compile(r'^(.+?)\s*»\s*(.+)$'), 2),
    # "Title\" Artist" (corrupted quote then artist)
    (re.compile(r'^(.+?)\s*["""]\s*(.+)$'), 2),
]

# Known song titles that should NOT be treated as artists
SONG_TITLE_BLACKLIST = {
    'spotify', 'weekly discovery', 'top 10', 'review', 'piano song',
    'dance of death', 'from the greatest showman', 'from the myth',
    'soundtrack', 'theme', 'opening', 'ending',
}

def is_likely_song_title(text):
    """Check if text looks more like a song title than an artist name."""
    t = text.lower().strip()
    # Date-like entries
    if re.match(r'^\d{1,2}/\d{1,2}(/\d{2,4})?$', t):
        return True
    # "spotify" entries
    if 'spotify' in t or 'weekly discovery' in t:
        return True
    # Very short or numeric
    if len(t) < 2 or t.isdigit():
        return True
    return False

def aggressive_parse(title):
    """Try to extract artist from a title that failed normal parsing."""
    if not title:
        return None

    for pattern, group in AGGRESSIVE_PATTERNS:
        m = pattern.search(title)
        if m:
            candidate = m.group(group).strip().strip('"').strip("'")
            other = m.group(3 - group).strip()
            # Skip if the "artist" looks like a song title
            if is_likely_song_title(candidate):
                continue
            # Skip if the "song" part looks like an artist
            if is_likely_song_title(other):
                continue
            # Skip very short candidates
            if len(candidate) < 2:
                continue
            return candidate

    return None

def main():
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    fixed = 0
    for row in rows:
        if row.get('artist', '').strip():
            continue
        title = row.get('title', '')
        artist = aggressive_parse(title)
        if artist:
            row['artist'] = artist
            fixed += 1

    with open(CSV_PATH, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)

    print(f'Fixed {fixed} rows with empty artist column')

if __name__ == '__main__':
    main()
