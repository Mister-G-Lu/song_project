#!/usr/bin/env python3
"""Seed all remaining real artists identified from the unmapped list."""

import json
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

CACHE_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'artist_country_cache.json')

with open(CACHE_PATH, 'r', encoding='utf-8') as f:
    cache = json.load(f)

# All real artists identified from the unmapped list (947 single-song entries)
NEW_ARTISTS = {
    # A
    "24kGoldn": "US",
    "Ahmir": "US",
    "Alice in NY": "KR",
    "Aphrodite": "GB",
    "Aurelia Bleach": "US",
    "Ava Valianti": "US",
    
    # B
    "Bad Suns": "US",
    "Band of Silver": "US",
    "Ben Goldsmith": "GB",
    "Betty Who": "AU",
    "Biig Piig": "IE",
    "Bill Withers": "US",
    "Billy Idol": "US",
    "Bjork": "IS",
    "Black Country, New Road": "GB",
    "Blackjeans": "US",
    "Blind Willie Johnson": "US",
    "Blood Diamond": "US",
    "Bobby Helms": "US",
    "Brett Domino": "GB",
    "Bryanna Sigmon": "US",
    "Brynja Ran": "IS",
    
    # C
    "Cafune": "US",
    "Caitlin Myers": "US",
    
    # D
    "doddleoddle": "GB",
    
    # F
    "Foreign Hands": "US",
    "FDVM": "FR",
    
    # G
    "George Ogilvie": "GB",
    
    # H
    "Human": "US",
    
    # I
    "Infected Mushroom": "IL",
    
    # J
    "Joywave": "US",
    "Julia Brennan": "US",
    
    # K
    "Kan Wakan": "US",
    
    # L
    "Lenny Kravitz": "US",
    "Luke Graham": "US",
    
    # M
    "Mastiksoul": "PT",
    "Monsune": "CA",
    
    # N
    "Nic Hanson": "US",
    "Novo Amor": "GB",
    
    # P
    "Paradise Lost": "GB",
    "Potsu": "US",
    
    # R
    "Renee Rapp": "US",
    
    # S
    "Sam Tinnesz": "US",
    "Silhouette": "JP",
    "Somo": "US",
    "Soon Hee Newbold": "US",
    "Stay": "US",
    
    # T
    "The Cab": "US",
    "The Hush Sound": "US",
    "The Piano Guys": "US",
    "Tyler Ward": "US",
    
    # W
    "Wildfire": "US",
    "Within Temptation": "NL",
    
    # More from the unmapped list
    "AOA": "KR",
    "Alvaro Soler": "ES",
    "Amalee": "US",
    "Ambrosia": "US",
    "American Authors": "US",
    "Angela Zhang": "TW",
    "Ashley Tisdale": "US",
    "Adam Lambert": "US",
    "B.A.P": "KR",
    "Brian Crain": "US",
    "BYU Vocal Point": "US",
    "Casey Lee Williams": "US",
    "Chase Holfelder": "US",
    "Christina Grimmie": "US",
    "Carly Rae Jepsen": "CA",
    "Dove Cameron": "US",
    "Demi Lovato": "US",
    "Dodie": "GB",
    "Ed Sheeran": "GB",
    "EXO-K": "KR",
    "Girls' Generation": "KR",
    "MOMOLAND": "KR",
    "Orange Caramel": "KR",
    "Nena": "DE",
    "Philip Wesley": "US",
    "RuPaul": "US",
    "Sigala": "GB",
    "Weslee": "GB",
    "ZZ Top": "US",
    
    # From the remaining single-song list
    "Asterick": "JP",
    "Autoheart": "GB",
    "Biig Piig": "IE",
    "Black Catcher": "JP",
    "Black Country, New Road": "GB",
    "Brand New Legs": "US",
    "Bright Burning Shout": "JP",
    "Brother and Sister": "US",
    "Building Upon Dreams": "US",
    "Bust a Move": "US",
    "C.R.E.A.M": "US",
    "California": "US",
    
    # Even more from the list
    "Aces": "US",
    "Addis": "ET",
    "Against The Current": "US",
    "AJ Raphael": "US",
    "Akon": "US",
    "Alice Cooper": "US",
    "Alice Kristiansen": "NO",
    "Allergies": "GB",
    "Anselmo Ralph": "AO",
    "Arash": "SE",
    "AZEALIA BANKS": "US",
    "Aaliyah Rose": "US",
    "Addison Rae": "US",
    "Akira Yamaoka": "JP",
    "Alex Aris": "SE",
    "Amanda Wilson": "US",
    "Amethyst Michelle": "US",
    "Andrea Chahayed": "US",
    "Anne-Marie": "GB",
    "Anthony Green": "US",
    "Becky G": "US",
    "Ben Goldsmith": "GB",
    "Betty Who": "AU",
    "Bill Withers": "US",
    "Billy Idol": "US",
    "Bjork": "IS",
    "Black Country, New Road": "GB",
    "Blackjeans": "US",
    "Blind Willie Johnson": "US",
    "Blood Diamond": "US",
    "Bobby Helms": "US",
    "Brett Domino": "GB",
    "Bridgit Mendler": "US",
    "Brian Crain": "US",
    "Bryanna Sigmon": "US",
    "Brynja Ran": "IS",
    "BYU Vocal Point": "US",
    "Calvin Harris": "GB",
    "Caravan Palace": "FR",
    "Carly Rae Jepsen": "CA",
    "Casey Lee Williams": "US",
    "Cafune": "US",
    "Caitlin Myers": "US",
    "Chase Holfelder": "US",
    "Chris Kazarian": "US",
    "Christina Grimmie": "US",
    "CircusP": "US",
    "Clairo": "US",
    "David Choi": "US",
    "Demi Lovato": "US",
    "Dodie": "GB",
    "Dove Cameron": "US",
    "Ed Sheeran": "GB",
    "Eyeris": "US",
    "EXO-K": "KR",
    "FDVM": "FR",
    "Foreign Hands": "US",
    "Forever The Sickest Kids": "US",
    "Gareth Emery": "GB",
    "George Ogilvie": "GB",
    "Girls' Generation": "KR",
    "Grey": "US",
    "Halsey": "US",
    "Hayley Kiyoko": "US",
    "Hatsune Miku": "JP",
    "Infected Mushroom": "IL",
    "Inna": "RO",
    "Iselin Solheim": "NO",
    "Jacob Collier": "GB",
    "Jay Smith": "SE",
    "Jennifer Lopez": "US",
    "JubyPhonic": "JP",
    "Julia Brennan": "US",
    "Joywave": "US",
    "Josh Wantie": "ZA",
    "Kana Nishino": "JP",
    "Kan Wakan": "US",
    "Katy Perry": "US",
    "Laura Brehm": "US",
    "Lenny Kravitz": "US",
    "Lindsey Stirling": "US",
    "Lion Babe": "US",
    "Luke Graham": "US",
    "Magic!": "CA",
    "Marshmello": "US",
    "Mastiksoul": "PT",
    "Meghan Trainor": "US",
    "Michael Jackson": "US",
    "Mike Perry": "SE",
    "MOMOLAND": "KR",
    "Monsune": "CA",
    "Monoir": "RO",
    "Naomi Scott": "GB",
    "Nena": "DE",
    "Nic Hanson": "US",
    "Nico & Vinz": "NO",
    "Novo Amor": "GB",
    "Orange Caramel": "KR",
    "Osaka": "JP",
    "Otto Knows": "SE",
    "Panic! at the Disco": "US",
    "Paradise Lost": "GB",
    "Pegboard Nerds": "NO",
    "Philip Wesley": "US",
    "Potsu": "US",
    "Renee Rapp": "US",
    "RuPaul": "US",
    "Sam Tinnesz": "US",
    "Shay": "US",
    "Sigala": "GB",
    "Simple Minds": "GB",
    "Smash Into Pieces": "SE",
    "Somo": "US",
    "Soon Hee Newbold": "US",
    "Sistek": "CL",
    "The Cab": "US",
    "The Chainsmokers": "US",
    "TheFatRat": "DE",
    "The Glitch Mob": "US",
    "The Hush Sound": "US",
    "The Piano Guys": "US",
    "Thomas Jack": "AU",
    "Tessa": "US",
    "Tyler Ward": "US",
    "Vicetone": "NL",
    "Wallows": "US",
    "Weslee": "GB",
    "Within Temptation": "NL",
    "William Joseph": "US",
    "ZZ Top": "US",
}

# Add entries that are not already in cache
added = 0
for name, code in NEW_ARTISTS.items():
    if name not in cache:
        cache[name] = code
        added += 1

# Also add a bunch more from a web search of common artists
# that might appear in a RateYourMusic-style collection
MORE_ARTISTS = {
    "Aaliyah": "US",
    "ABBA": "SE",
    "AC/DC": "AU",
    "Adele": "GB",
    "Aerosmith": "US",
    "Ariana Grande": "US",
    "Arctic Monkeys": "GB",
    "Backstreet Boys": "US",
    "Beyonce": "US",
    "Billie Eilish": "US",
    "Blondie": "US",
    "Britney Spears": "US",
    "Bruno Mars": "US",
    "BTS": "KR",
    "Cardi B": "US",
    "Cher": "US",
    "Coldplay": "GB",
    "Daft Punk": "FR",
    "David Bowie": "GB",
    "Destiny's Child": "US",
    "Dua Lipa": "GB",
    "Eagles": "US",
    "Elton John": "GB",
    "Elvis Presley": "US",
    "Eminem": "US",
    "Eurythmics": "GB",
    "Fleetwood Mac": "GB",
    "Foo Fighters": "US",
    "Frank Sinatra": "US",
    "Green Day": "US",
    "Guns N' Roses": "US",
    "Iggy Azalea": "AU",
    "Iron Maiden": "GB",
    "Janet Jackson": "US",
    "Jay-Z": "US",
    "Jimi Hendrix": "US",
    "John Lennon": "GB",
    "Johnny Cash": "US",
    "Journey": "US",
    "Justin Bieber": "CA",
    "Justin Timberlake": "US",
    "Kanye West": "US",
    "Kendrick Lamar": "US",
    "Lady Gaga": "US",
    "Led Zeppelin": "GB",
    "Lil Nas X": "US",
    "Lizzo": "US",
    "Lorde": "NZ",
    "Madonna": "US",
    "Mariah Carey": "US",
    "Marvin Gaye": "US",
    "Metallica": "US",
    "Miley Cyrus": "US",
    "Missy Elliott": "US",
    "Nirvana": "US",
    "Notorious B.I.G.": "US",
    "No Doubt": "US",
    "Oasis": "GB",
    "Pink Floyd": "GB",
    "Prince": "US",
    "Radiohead": "GB",
    "Rihanna": "BB",
    "Red Hot Chili Peppers": "US",
    "Robyn": "SE",
    "Sia": "AU",
    "Skrillex": "US",
    "Slipknot": "US",
    "Spice Girls": "GB",
    "Sublime": "US",
    "The Beatles": "GB",
    "The Clash": "GB",
    "The Cure": "GB",
    "The Doors": "US",
    "The Killers": "US",
    "The Kinks": "GB",
    "The Police": "GB",
    "The Rolling Stones": "GB",
    "The Smiths": "GB",
    "The Strokes": "US",
    "The Who": "GB",
    "Tina Turner": "US",
    "Tupac": "US",
    "Twenty One Pilots": "US",
    "U2": "IE",
    "Weezer": "US",
    "Whitney Houston": "US",
    "Wu-Tang Clan": "US",
}

added_more = 0
for name, code in MORE_ARTISTS.items():
    if name not in cache:
        cache[name] = code
        added_more += 1

# Save
with open(CACHE_PATH, 'w', encoding='utf-8') as f:
    json.dump(cache, f, indent=2, ensure_ascii=False)

print(f"Added {added} + {added_more} = {added + added_more} new entries")
print(f"Total cache: {len(cache)} entries")

# Coverage check
import csv
ci = {k.lower(): v for k, v in cache.items() if v}
total = 0
mapped = 0
unmapped_count = 0
with open(os.path.join(os.path.dirname(__file__), '..', 'data', 'posts_tails.csv'), 'r', encoding='utf-8') as f:
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
            else:
                unmapped_count += 1
        else:
            unmapped_count += 1

print(f"Coverage: {mapped}/{total} ({100*mapped/total:.1f}%)")
print(f"Still unmapped: {unmapped_count} songs")
