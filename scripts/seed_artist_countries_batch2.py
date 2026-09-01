#!/usr/bin/env python3
"""Batch 2: Seed 328 curated artists with country codes."""

import json
import os

COUNTRY_MAP = {
    # US Pop/Rock
    '3OH!3': 'US', 'Adam Lambert': 'US', 'Alessia Cara': 'US', 'Alexander Jean': 'US',
    'Allie X': 'US', 'Austin Mahone': 'US', 'Baby Keem': 'US', 'Beyonce': 'US',
    'Beyoncé': 'US', 'Bobby Brown': 'US', 'Boy Epic': 'US', 'BoyWithUke': 'US',
    'Brian Crain': 'US', 'Britney Spears': 'US', 'Capital Cities': 'US',
    'Carly Rae Jepson': 'US', 'Charlie Puth': 'US', 'Charlotte Lawrence': 'US',
    'Chase Holfelder': 'US', 'Chris Isaak': 'US', 'Christina Grimmie': 'US',
    'Ciara': 'US', 'Circuit des Yeux': 'US', 'Clara C': 'US', 'Colbie Caillat': 'US',
    'Con Bro Chill': 'US', 'Coolio': 'US', 'Corpse Husband': 'US',
    'Curtis Mayfield': 'US', 'DJ Khaled': 'US', 'DNCE': 'US', 'Damien Dawn': 'US',
    'DamienDawn': 'US', 'Daniel Powter': 'US', 'Daya': 'US', 'Dear Happy': 'US',
    'Dido': 'US', 'Edwin McCain': 'US', 'Eliza Rickman': 'US', 'Elvis Presley': 'US',
    'Erykah Badu': 'US', 'FINNEAS': 'US', 'Fall Out boy': 'US', 'Fickle Friends': 'US',
    'Fifth Harmony': 'US', 'Fleurie': 'US', 'Fort Minor': 'US',
    'Foster The People': 'US', 'Fun': 'US', 'G-easy': 'US',
    'George Harrison': 'US', 'Gorillaz': 'US', 'Gwen Stefani': 'US',
    'Haschak Sisters': 'US', 'I AM THEY': 'US', 'Ingrid Michaelson': 'US',
    'Jack Johnson': 'US', 'Jacob Sartorius': 'US', 'James Arthur': 'US',
    'James Tw': 'US', 'Jason Derulo': 'US', 'Jason Mraz': 'US', 'Jay Z': 'US',
    'Jennifer Lawrence': 'US', 'Jennifer Lopez': 'US', 'Joan Osborne': 'US',
    'Joanna Newsom': 'US', 'Joe Satriani': 'US', 'John Cale': 'US',
    'Jon Bellion': 'US', 'Jon Cozart': 'US', 'Jordan Gagne': 'US',
    'Juice WRLD': 'US', 'Juice Wrld': 'US', 'Karmin': 'US', 'Kat DeLuna': 'US',
    'Kehlani': 'US', 'Kelly Clarkson': 'US', 'Kelly Sweet': 'US',
    'Kevin Leonardo': 'US', 'Khalid': 'US', 'Lady Antebellum': 'US',
    'Lady Gaga': 'US', 'Landon Austin': 'US', 'Lil Uzi Vert': 'US',
    'Lil Wayne': 'US', 'Lord Huron': 'US', 'Loren Allred': 'US',
    'Louis Cole': 'US', 'Macklemore': 'US', 'Macklemore & Ryan Lewis': 'US',
    'Madonna': 'US', 'Malinda': 'US', 'Mat Kearney': 'US', 'Matt Burrows': 'US',
    'Meg Myers': 'US', 'Michael Jackson': 'US', 'Michele McLaughlin': 'US',
    'Miike Snow': 'US', 'Mike Perry': 'US', 'MisterWives': 'US',
    'Misterwives': 'US', 'Ne-Yo': 'US', 'Ne-yo': 'US', 'Nessa Barrett': 'US',
    'Nick Pitera': 'US', 'Nina Simone': 'US', 'No Age': 'US', 'OBB': 'US',
    'OK Go': 'US', 'OTR': 'US', 'Olivia rodrigo': 'US', 'One Republic': 'US',
    'P!nk': 'US', 'Panic at the Disco': 'US', 'Phil Collins': 'US', 'Pink': 'US',
    'Pink Martini': 'US', 'RIELL': 'US', 'Ratt': 'US',
    'Really Slow Motion': 'US', 'Rever Mieux': 'US', 'Revivalists': 'US',
    'RiceGum': 'US', 'Rob thomas': 'US', 'Ruth B.': 'US',
    'Sabrina Claudio': 'US', 'Sam Riegel': 'US', 'Santana': 'US',
    'Sasha Alex Sloan': 'US', 'Seann Bowe': 'US', 'Set If Off': 'US',
    'Skinny Living': 'US', 'Sly & The Family Stone': 'US',
    'Smashing Pumpkins': 'US', 'Sody': 'US', 'Static': 'US',
    'Static P': 'US', 'Static-P': 'US', 'Steve Aoki': 'US',
    'Tessa Violet': 'US', 'The Bangles': 'US', 'The Black Eyed Peas': 'US',
    'The Eagles': 'US', 'The Kid LAROI': 'US',
    'The Kid LAROI, Juice WRLD': 'US', 'The Kid Laroi': 'US',
    'The Monkees': 'US', 'The Offspring': 'US', 'The Score': 'US',
    'The Strokes': 'US', 'The Who': 'US', 'Thirty Seconds To Mars': 'US',
    'Timeflies': 'US', 'Train': 'US', 'Twenty One Pilots': 'US',
    'Two Steps from Hell': 'US', 'Tyler Ward': 'US',
    'Tyler, The Creator': 'US', 'Unlike Pluto': 'US', 'Valeree': 'US',
    'Valgur': 'US', 'Vanic': 'US', 'Victoria Monét': 'US',
    'We the Kings': 'US', 'Weathers': 'US', 'X Ambassador': 'US',
    'X Ambassadors': 'US', 'ZAYDE WOLF': 'US', 'marshmello': 'US',
    'renforshort': 'US', 'sleeping at last': 'US', 'lovelytheband': 'US',
    'Set It Off': 'US',

    # Canada
    'Backstreet boys': 'CA', 'deadmau5': 'CA', 'Alessia Cara': 'CA',
    'Carly Rae Jepson': 'CA', 'Drake': 'CA', 'Tegan and Sara': 'CA',

    # UK
    'Bastille': 'UK', 'Beatles': 'UK', 'Byrds': 'US',
    'Clean Bandit and Mabel': 'UK', 'Coldplay': 'UK',
    'Dave Matthews Band': 'US', 'Delain': 'NL',
    'Dodie': 'UK', 'dodie': 'UK', 'Ed Sheeran': 'UK',
    'Fifth Harmony': 'US', 'Hurts': 'UK', 'James Arthur': 'UK',
    'Lawson': 'UK', 'Muse': 'UK', 'Nerina Pallot': 'UK',
    'Niall Horan': 'IE', 'Pendulum': 'AU', 'Pink': 'US',
    'PENTATONIX': 'US', 'Phil Collins': 'UK', 'Sting': 'UK',
    'Supertramp': 'UK', 'The Prodigy': 'UK', 'The Who': 'UK',
    'T.Rex': 'UK', 'Tove Lo': 'SE', 'Wham!': 'UK',
    'Ward Thomas': 'UK', 'George Harrison': 'UK',

    # Sweden
    'Tove Lo': 'SE', 'Abba': 'SE', 'LÉON': 'SE',
    'Johnossi': 'SE', 'Miike Snow': 'SE',

    # Norway
    'Alexander Rybak': 'NO', 'Didrick': 'NO', 'Alan Walker': 'NO',
    'Aurora': 'NO',

    # Finland
    'Hudson Mohawke': 'GB',

    # Denmark
    'Emmelie De Forest': 'DK',

    # Germany
    'ATC': 'DE', 'E-rotic': 'DE', 'Tiesto': 'NL',
    'Tiga': 'CA', 'Gareth Emery feat. Christina Novelli': 'GB',

    # Netherlands
    'Tiesto': 'NL', 'Delain': 'NL', 'Within Temptation': 'NL',
    'Yellow Magic Orchestra': 'JP',

    # Japan
    'Alstroemeria': 'JP', 'ASLTROeMERIA': 'JP', 'Bradio': 'JP',
    'DECO*27': 'JP', 'Eir Aoi': 'JP', 'Ikimonogakari': 'JP',
    'Joe Hisaishi': 'JP', 'KANA-BOON': 'JP', 'Kajiura Yuki': 'JP',
    'Kana Nishino': 'JP', 'Mai Kuraki': 'JP', 'Mariya Takeuchi': 'JP',
    'Mayu Maeshima': 'JP', 'Miki Matsubara': 'JP', 'Perfume': 'JP',
    'Tatsuya': 'JP', 'TUYU': 'JP', 'Tuyu': 'JP',
    'Yurima': 'JP', 'fujii Kaze': 'JP', 'hiroshi sato': 'JP',
    'ill peach': 'JP',

    # South Korea
    'AOA': 'KR', 'BLACK6IX': 'KR', 'BTOB (비투비)': 'KR',
    'Exo': 'KR', 'VIXX': 'KR', 'Orange caramel': 'KR',
    'Good Boy daisy': 'KR',

    # Australia
    'Guy Sebastian': 'AU', 'Pendulum': 'AU', 'Sheppard': 'AU',
    'Sia': 'AU',

    # New Zealand
    'Lorde': 'NZ', 'Kimbra': 'NZ',

    # Canada
    'Alanis Morissette': 'CA', 'Arcade Fire': 'CA', 'Brian Crain': 'CA',
    'deadmau5': 'CA', 'Drake': 'CA', 'Leonard Cohen': 'CA',
    'Michael Bublé': 'CA', 'Neil Young': 'CA', 'Rush': 'CA',
    'The Weeknd': 'CA', 'Tegan and Sara': 'CA',

    # Ireland
    'Niall Horan': 'IE', 'Sinéad O\'Connor': 'IE',
    'The Cranberries': 'IE', 'U2': 'IE',

    # Iceland
    'Björk': 'IS', 'Of Monsters and Men': 'IS', 'Sigur Rós': 'IS',

    # Italy
    'Ludovico Einaudi': 'IT', 'Pino D\'Angiò': 'IT',

    # France
    'Daft Punk': 'FR', 'M83': 'FR', 'Christine and the Queens': 'FR',

    # Spain
    'Rosalía': 'ES', 'Enrique Iglesias': 'ES',

    # Russia
    'Ani Lorak': 'UA', 't.A.T.u.': 'RU', 'Nu Virgos': 'UA',

    # Ukraine
    'Ani Lorak': 'UA',

    # Brazil
    'Alok': 'BR', 'Anitta': 'BR', 'Sergio Mendes': 'BR',

    # Argentina
    'Gustavo Cerati': 'AR', 'Soda Stereo': 'AR',

    # Colombia
    'Shakira': 'CO', 'Juanes': 'CO', 'J Balvin': 'CO',
    'Carlos Vives': 'CO',

    # Puerto Rico
    'Daddy Yankee': 'PR', 'Bad Bunny': 'PR', 'Ricky Martin': 'PR',
    'Luis Fonsi': 'PR', 'Wisin & Yandel': 'PR', 'Yandel': 'PR',
    'Marc Anthony': 'PR',

    # Jamaica
    'Bob Marley': 'JM', 'Shaggy': 'JM', 'Sean Paul': 'JM',

    # Cuba
    'Buena Vista Social Club': 'CU', 'Gloria Estefan': 'CU',

    # Germany
    'Kraftwerk': 'DE', 'Rammstein': 'DE', 'Scorpions': 'DE',
    'Nena': 'DE',

    # Austria
    'Falco': 'AT',

    # Switzerland
    'DJ Bobo': 'CH',

    # Belgium
    '2 Unlimited': 'BE', 'Technotronic': 'BE',

    # Israel
    'Ofra Haza': 'IL',

    # Nigeria
    'Burna Boy': 'NG', 'Wizkid': 'NG', 'Davido': 'NG',

    # South Africa
    'Black Coffee': 'ZA', 'Die Antwoord': 'ZA',

    # India
    'A.R. Rahman': 'IN', 'Arijit Singh': 'IN', 'Lata Mangeshkar': 'IN',

    # China
    'Jay Chou': 'TW', 'Liu Huan': 'CN', 'Zhou Shen': 'CN',
    'Yu Quan & Huang Zhang': 'CN', 'Xi Shua Shua': 'TW',
    'A-Lin': 'TW',

    # Taiwan
    'Jay Chou': 'TW', 'A-Lin': 'TW', 'S.H.E': 'TW',
    'Jolin Tsai': 'TW',

    # Turkey
    'Tarkan': 'TR',

    # Greece
    'Sakis Rouvas': 'GR',

    # Hungary
    'Republic': 'HU',

    # Poland
    'Dawid Podsiadło': 'PL',

    # Czech Republic
    'Lucie Bílá': 'CZ',

    # Romania
    'Inna': 'RO',

    # Bulgaria
    'Kristian Kostov': 'BG',

    # Macedonia
    'Kaliopi': 'MK',

    # Sweden
    'Robyn': 'SE', 'Avicii': 'SE', 'Europe': 'SE',
    'ABBA': 'SE', 'Roxette': 'SE', 'The Hives': 'SE',
    'First Aid Kit': 'SE', 'Icona Pop': 'SE',

    # Finland
    'HIM': 'FI', 'Nightwish': 'FI', 'Children of Bodom': 'FI',
    'Apocalyptica': 'FI',

    # Denmark
    'Lukas Graham': 'DK', 'Aqua': 'DK', 'Caroline Henderson': 'DK',

    # Norway
    'Kygo': 'NO', 'A-ha': 'NO',

    # Netherlands
    'Armin van Buuren': 'NL', 'Afrojack': 'NL', 'Martin Garrix': 'NL',
    'Tiësto': 'NL', 'Vicetone': 'NL', 'Showtek': 'NL',

    # Belgium
    'Lost Frequencies': 'BE', 'Dualistic': 'BE',

    # More specific artists from the unmapped list
    '4count': 'US', 'Amadeus Electric Quartet': 'US',
    'Amar Sehmbi': 'US', 'Amy Nuttall': 'UK',
    'Anna Blue': 'DE', 'Anna Blue & Damien Dawn': 'DE',
    'Ansel Elgort': 'US', 'Au5': 'US',
    "Auli'i Cravalho": 'US', 'Autoheart': 'UK',
    'Baby Keem': 'US', 'Ben Kidson': 'AU',
    'BoyWithUke': 'US', 'Breath and Bone': 'US',
    'Brictom': 'US', 'Brunuhville': 'US',
    'CVX': 'US', 'Calema': 'FR',
    'Chain smokers': 'US', 'Chipettes': 'US',
    'Clocks and Clouds': 'US', 'Cody Lovass': 'US',
    'Daniel Ingram': 'CA', 'DEELYLE': 'US',
    'DJ Striden': 'SE', 'Echosmith': 'US',
    'Edvin Marton': 'HU', 'F-777': 'US',
    'Fleur East': 'UK', 'Gareth Emery feat. Christina Novelli': 'GB',
    'Hololive': 'JP', 'Jem 77': 'US',
    'Knives At Sea': 'US', 'Korede Bello': 'NG',
    'Kuba Oms': 'CA', 'LACUNA COIL': 'IT',
    'Listz': 'HU', 'Loco Loco': 'US',
    'Lxandra': 'FI', 'MEGHAN TRAINOR': 'US',
    'MKTO': 'US', 'Ne-Yo': 'US',
    'PENTATONIX': 'US', 'Phil Collins': 'UK',
    'Runaground': 'US', 'SaraSinger42': 'US',
    'Sayuri': 'JP', 'Shi Shang Zhi You Mama Hao': 'CN',
    'Sting': 'UK', 'Taylor Davis': 'US',
    'Terminite': 'US', 'The Greatest Showman': 'US',
    'The HU': 'MN', 'The Villain I Appear to Be': 'US',
    'Uncle Acid And The Deadbeats': 'GB',
    'Vox Machina': 'US', 'Wicked': 'US',
    'Zen Zen Sense': 'US',
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
