#!/usr/bin/env python3
"""Final batch seed of remaining unmapped artists."""

import json
import os

COUNTRY_MAP = {
    'Auli\'i Cravalho': 'US', 'Jon Cozart and Dodie': 'GB',
    'Nathan Wagner': 'US', 'Zach Sobiech': 'US',
    'bill wurtz': 'JP', 'Shinsei Kamattechan': 'JP',
    'Galileo Galilei': 'JP', 'Madlib': 'US',
    'Peter Green': 'GB', 'KEN Mode': 'CA',
    'Tropical Fuck Storm': 'AU', 'Patty Waters': 'US',
    'Lalo Schrifrin': 'AR', 'Tortoise': 'US',
    'The Seatbelts': 'JP', 'The Mars Volta': 'US',
    'Taeko Onuki': 'JP', 'Jean Dawson': 'US',
    'Arman Alif': 'MY', 'X0o0x': 'JP',
    'Ingrid Witt': 'DE', 'echosmith': 'US',
    'maroon 5': 'US', 'rush': 'CA',
    'Peter, Paul, and Mary': 'US', 'Glen Hansard and Markéta Irglová': 'IE',
    'led zeppelin': 'GB', 'Blue October': 'US',
    'fall out boy': 'US', 'Sixpence None The Richer': 'US',
    'R.E.M.': 'US', "Destiny's Child": 'US',
    'Velvet Underground': 'US', 'Grandmaster Flash and the Furious Five': 'US',
    'Semisonic': 'US', 'Dixie Chicks': 'US',
    'Loverboy': 'CA', 'Darius Rucker': 'US',
    'foo fighters': 'US', 'Social Distortion': 'US',
    'supertramp': 'GB', 'Tim McGraw': 'US',
    'Missy Elliott': 'US', 'Sam Cooke': 'US',
    'John Mayer': 'US', 'Joe Jones': 'US',
    'Portugal. The Man': 'US', 'Peter Bjorn and John': 'SE',
    'Steve Miller Band': 'US', 'James Morrison': 'GB',
    'Zager and Evans': 'US', 'Pearl Jam': 'US',
    'George Strait': 'US', 'Oingo Boingo': 'US',
    'JR JR': 'US', 'Magdalena Bay': 'US',
    'Rina Sawayama': 'GB', 'The Wombats': 'GB',
    'hagali': 'JP', 'Kenshi Yonezu': 'JP',
    'Hikaru Utada': 'JP', 'ZUTOMAYO': 'JP',
    'Sly and the Family Stone': 'US', 'Me (Ben E. King)': 'US',
    'Ben E. King': 'US', 'Hatsune Miku': 'JP',
    'Kana Nishino': 'JP', '花譜': 'JP',
    'Yu-peng chen': 'CN', 'Satoshi Kishida': 'JP',
    'Standing On The Corner': 'US', "death's dynamic shroud": 'JP',
    'Poison Girl Friend': 'JP', 'Yoshida Ichiro Untouchable': 'JP',
    '花儿乐队': 'CN', 'ChiliChil': 'JP',
    'Rosa Walton & Hallie Coggins': 'GB', 'Rufus Wainwright': 'CA',
    'Steve Jobs': 'US', 'fun': 'US',
    'colors': 'JP', 'Itoki Hana': 'JP',
    'Bradio': 'JP', 'The Smashing Pumpkins': 'US',
    'adele': 'GB', 'Neon Trees': 'US',
    'Idina Menzel': 'US', 'sting': 'GB',
    'nf': 'US', 'Hot Chelle Rae': 'US',
    'TryHardNinja': 'US', 'RyanDan': 'CA',
    'VersaEmerge': 'US', 'Junky': 'JP',
    'CircusP': 'JP', 'kyle xian': 'CA',
    'winky詩': 'JP', 'marie mai': 'CA',
    'clocks and clouds': 'DE', 'jon cozart': 'US',
    'Michelle Mclaughin': 'US', 'Ross Lynch': 'US',
}

CACHE_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'artist_country_cache.json')

def main():
    cache = json.load(open(CACHE_PATH, 'r', encoding='utf-8'))
    added = 0
    for artist, code in COUNTRY_MAP.items():
        if artist not in cache or not cache[artist]:
            cache[artist] = code
            added += 1

    with open(CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)

    mapped = sum(1 for v in cache.values() if v)
    print(f"Added {added} new mappings")
    print(f"Total cached: {len(cache)}")
    print(f"With country: {mapped}")

if __name__ == '__main__':
    main()
