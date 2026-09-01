#!/usr/bin/env python3
"""Batch 6: More known artists."""

import json
import os

COUNTRY_MAP = {
    # Real artists from unmapped list
    'Birdy': 'UK', 'Billy Ocean': 'GB', 'Bob Marley & The Wailer': 'JM',
    'Bobby McFerrin': 'US', 'Bryce Vine': 'US', 'Burak Yeter': 'TR',
    'Calvin Harris': 'GB', 'Calvin Harris, Dua Lipa': 'GB',
    'Candy Dulfer': 'NL', 'Carole King': 'US', 'Cassadee Pope': 'US',
    'Celeste': 'GB', 'Chameleon Circuit': 'GB', 'Charly García': 'AR',
    'Chelsea Jade': 'NZ', 'Chelsea Wolfe': 'US', 'Chris Cornell': 'US',
    'Chris Lane': 'US', 'Christine Welch': 'US', 'Cindy Morgan': 'US',
    'Citizen Way': 'US', 'Claire Rosinkranz': 'US',
    'Coeur De Pirate': 'CA', 'Courage My Love': 'CA',
    'Crash Adams': 'CA', 'Deerhoof': 'US', 'Deftones': 'US',
    'Denzel Curry': 'US', "Destiny's Child": 'US',
    'Dimash Kudaibergen': 'KZ', 'Dodie Clark': 'GB',
    'Dominic Fike': 'US', 'Dorothy': 'US',
    'Edward Sharpe & The Magnetic Zeros': 'US',
    'Ella Eyre': 'GB', 'Elmiene': 'GB', 'Elohim': 'US',
    'Emmelie de Forest': 'DK', 'Eric Clapton': 'GB',
    'Estelle': 'GB', 'Exuma': 'BS', 'Faun': 'DE',
    'Farid Mammadov': 'AZ', 'FLO': 'GB',
    'G-Eazy': 'US', 'George Ezra': 'GB', 'Gnarls Barkley': 'US',
    'Gregorian': 'DE', 'Guster': 'US', 'Halsey': 'US',
    'Hans Zimmer': 'DE', 'Hayley Kiyoko': 'US',
    'Hillsong Worship': 'AU', 'Imagine Dragons': 'US',
    'Irma Thomas': 'US', 'J Balvin': 'CO',
    'Jack U': 'US', 'Jeff Buckley': 'US', 'Joji': 'JP',
    'Jonas Blue': 'GB', 'Jonas Brothers': 'US', 'Joy Division': 'GB',
    'Judah & the Lion': 'US', 'Justice': 'FR',
    'Kacey Musgraves': 'US', 'Kat Graham': 'US',
    'Kaytranada': 'CA', 'Kero Kero Bonito': 'GB',
    'Kevin MacLeod': 'US', 'Kid Cudi': 'US', 'Killers': 'US',
    'Kings of Leon': 'US', 'Kodaline': 'IE', 'Kygo': 'NO',
    'Lauv': 'US', 'Leon Bridges': 'US', 'Leonard Cohen': 'CA',
    'Lights': 'CA', 'Lizzo': 'US', 'Lorde': 'NZ',
    'Louis Tomlinson': 'GB', 'Lucas Graham': 'DK',
    'Luis Fonsi': 'PR', 'M.I.A.': 'GB', 'M83': 'FR',
    'Mac DeMarco': 'CA', 'Maggie Rogers': 'US',
    'Major Lazer': 'US', 'Mark Ronson': 'GB',
    'Marshmello': 'US', 'Matt Maeson': 'US',
    'Meghan Trainor': 'US', 'Metro Station': 'US',
    'Moby': 'US', 'Mumford & Sons': 'GB',
    'N.E.R.D': 'US', 'NF': 'US', 'Neiked': 'SE',
    'Niall Horan': 'IE', 'Nicki Minaj': 'TT',
    'Niki': 'ID', 'Ofenbach': 'FR',
    'Omar Apollo': 'US', 'Owl City': 'US',
    'Palaye Royale': 'CA', 'Passion Pit': 'US',
    'Phoebe Ryan': 'US', 'Phum Viphurit': 'TH',
    'Porter Robinson': 'US', 'Post Malone': 'US',
    'Quinn XCII': 'US', 'R3HAB': 'NL',
    'Radiohead': 'GB', 'Rainbow Kitten Surprise': 'US',
    'Rex Orange County': 'GB', 'Rita Ota': 'GB',
    'Robin Schulz': 'DE', 'Royal Blood': 'GB',
    'Run the Jewels': 'US', 'Sam Fischer': 'AU',
    'Sam Smith': 'GB', 'Selena Gomez': 'US',
    'Shawn Mendes': 'CA', 'Sleeping At Last': 'US',
    "Snail's House": 'JP', 'Sofi Tukker': 'US',
    'Son Lux': 'US', 'St. Lucia': 'ZA',
    'Steam Powered Giraffe': 'US', 'Stray Kids': 'KR',
    'Sufjan Stevens': 'US', 'Summer Walker': 'US',
    'T-Pain': 'US', 'Tash Sultana': 'AU',
    'Taylor Swift': 'US', 'The 1975': 'GB',
    'The Antlers': 'US', 'The Band CAMINO': 'US',
    'The Black Keys': 'US', 'The Book of Love': 'US',
    'The Chainsmokers': 'US', 'The Drums': 'US',
    'The Fray': 'US', 'The Game': 'US',
    'The Ink Spots': 'US', 'The Japanese House': 'GB',
    'The Kinks': 'GB', 'The Lumineers': 'US',
    'The Naked and Famous': 'NZ', 'The Neighbourhood': 'US',
    'The Paper Kites': 'AU', 'The Walters': 'US',
    'The xx': 'GB', 'Thrice': 'US', 'Tom Odell': 'GB',
    'Tones and I': 'AU', 'Twenty One Pilots': 'US',
    'Two Door Cinema Club': 'GB', 'Vampire Weekend': 'US',
    'Walk The Moon': 'US', 'Weezer': 'US',
    'Wolf Alice': 'GB', 'X Ambassadors': 'US',
    'Yungblud': 'GB', 'Zedd': 'DE', 'ZHU': 'US',
    'Agnes Obel': 'DK', 'Alt-J': 'GB', 'Amaarae': 'GH',
    'Aphex Twin': 'GB', 'Arctic Monkeys': 'GB',
    'Balthazar': 'BE', 'Bastille': 'GB',
    'Beach House': 'US', 'Beck': 'US', 'Ben Howard': 'GB',
    'Billie Eilish': 'US', 'Björk': 'IS', 'Bones UK': 'GB',
    'Bon Iver': 'US', 'Bonobo': 'GB', 'Brockhampton': 'US',
    'Cage the Elephant': 'US', 'CamelPhat': 'GB',
    'Cashmere Cat': 'NO', 'Childish Gambino': 'US',
    'Clairo': 'US', 'Dua Lipa': 'GB', 'Foals': 'GB',
    'Glass Animals': 'GB', 'Hozier': 'IE', 'IDLES': 'GB',
    'Jai Wolf': 'US', 'JPEGMAFIA': 'US',
    'Kali Uchis': 'US', 'Kenny Beats': 'US',
    'King Princess': 'US', 'LANY': 'US',
    'Mac Miller': 'US', 'Mitski': 'US',
    'Nao': 'GB', 'Nothing But Thieves': 'GB',
    'Parcels': 'AU', 'Phoebe Bridgers': 'US',
    'Pink Sweat$': 'US', 'Real Estate': 'US',
    'Ruel': 'AU', 'SZA': 'US', 'Sam Fender': 'GB',
    'Tame Impala': 'AU', 'Thundercat': 'US',
    'Turnstile': 'US', 'Wet Leg': 'GB', 'Yves Tumor': 'US',
    # Additional
    'Arches of Loaf': 'US', 'Blues Creation': 'JP',
    'Blunt': 'US', 'Blackalicious': 'US', 'Blackbriar': 'NL',
    'Blackhole Blitz': 'US', 'Blind Tyler': 'US',
    'Blossom Dearie': 'US', 'Bond': 'GB',
    'Candle': 'US', 'Celebrate Summer': 'US',
    'Charlotte': 'US', 'Cheat Codes': 'US',
    'Chipmunks': 'US', 'Clump': 'US',
    'Cog is Dead': 'US', 'Colors': 'US',
    'Cosmic Lover': 'JP', 'Cowboy Bebop': 'JP',
    'Crosses': 'US', 'Cry Wolf': 'US',
    'DADDY! DADDY! DO!': 'JP', 'DANSU': 'JP',
    'Dami Im': 'AU', 'Dan + Shay, Justin Bieber': 'US',
    'Dark Cat': 'JP', 'Dark Sarah': 'FI',
    'Daughter': 'GB', 'Dead or Alive': 'GB',
    'Deerhoof': 'US', 'Derek Hough': 'US',
    'Diablo Swing Orchestra': 'SE', 'Disturbed': 'US',
    'EVERGLOW': 'KR', 'Earth': 'US',
    'Epic Soul Factory': 'US', 'F.B-17': 'JP',
    'Fangs': 'US', 'Faun': 'DE',
    'FLO': 'GB', 'Brave Enough': 'US',
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
