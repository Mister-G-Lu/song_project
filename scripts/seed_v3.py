#!/usr/bin/env python3
"""Seed country codes for remaining identifiable unmapped artists."""
import json

CACHE_PATH = 'data/artist_country_cache.json'

with open(CACHE_PATH, 'r', encoding='utf-8') as f:
    cache = json.load(f)

new_entries = {
    # From remaining unmapped list
    "Auli'i Cravalho": 'US',
    'Lilly Wood': 'FR',
    'Remady': 'CH',
    'Marta Jandová': 'CZ',
    'Yu Quan': 'CN',
    'Adriana Figueroa': 'CL',
    'IU': 'KR',
    'Casey Lee Williams': 'US',
    'dodie': 'GB',
    'Dove Cameron': 'US',
    'Girls\' Generation': 'KR',
    'Girls\u2019 Generation': 'KR',
    'Christina Grimmie': 'US',
    'Girls\u2019 Generation': 'KR',
    'Lindsey Stirling': 'US',
    'Austin Mahone': 'US',
    'New Seekers': 'GB',
    'Mr Blobby': 'GB',
    'Novo Amor': 'GB',
    'LiSA': 'JP',
    'Shin Sakiura': 'JP',
    'Hatsuki Yura': 'JP',
    'Yura Hatsuki': 'JP',
    'DAZBEE': 'JP',
    'Ado': 'JP',
    'Lowland Jazz': 'JP',
    '\u4e09\u6708\u306e\u30d1\u30f3\u30bf\u30b7\u30a2': 'JP',
    '\u5cf6\u98a8': 'JP',
    '\u795e\u98a8': 'CN',
    'Dschinghis Khan': 'DE',
    'Fujita Maiko': 'JP',
    'DAZBEE': 'JP',
    '\u591a\u591a': 'CN',
    '\u7948Inory': 'CN',
    
    # From the last batch of known real artists
    'Ne-Yo': 'US',
    'Akon': 'SN',
    'Tessa Violet': 'US',
    'Patrick Stump': 'US',
    'Florence + the Machine': 'GB',
    'Florence and the Machine': 'GB',
    'Ray Charles': 'US',
    'The Jackson 5': 'US',
    'Talking Heads': 'US',
    'Måneskin': 'IT',
    'Junko Ohashi': 'JP',
    'Yandel': 'PR',
    'Jennifer Lopez': 'US',
    
    # Known one-word/tricky artists
    'Faded': '',  # Song title, not an artist
    'Stay': '',  # Song title
    'Silhouette': '',  # Song title
    'Any Other Way': '',  # Song title
    'Bye Bye Bye': '',  # Song title (NSYNC)
    'Eye Of The Tiger': '',  # Song title (Survivor)
    'Crazy in Love': '',  # Song title (Beyonce)
    'Never Gonna Give You Up': '',  # Song title (Rick Astley)
    'Sweet Child O\' Mine': '',  # Song title (Guns N Roses)
    'Hey There Delilah': '',  # Song title (Plain White T's)
    'Love Yourself': '',  # Song title (Justin Bieber)
    'Somebody That I Used To Know': '',  # Song title (Gotye)
    'In the Aeroplane Over the Sea': '',  # Album title
    'N.Y. State of Mind': '',  # Song title (Nas)
    'Sittin\' On) The Dock of the Bay': '',  # Song title (Otis Redding)
    'Play That Funky Music': '',  # Song title (Wild Cherry)
    'Unchained Melody': '',  # Song title (Righteous Brothers)
    'La Macarena': '',  # Song title (Los Del Rio)
    'Six Underground': '',  # Song title (Sneaker Pimps)
    'Thong Song': '',  # Song title (Sisqo)
    'Cotton Eye Joe': '',  # Song title (Rednex)
    'stamp on the ground': '',  # Song title (ItaloBrothers)
    'Fight the Power': '',  # Song title (Public Enemy)
    'Walking On A Dream': '',  # Song title (Empire of the Sun)
    'Danger Zone': '',  # Song title (Kenny Loggins)
    'Fire on the Mountain': '',  # Song title (Grateful Dead/Marshall Tucker)
    'Redemption Song': '',  # Song title (Bob Marley)
    'Pocketful of Sunshine': '',  # Song title (Natasha Bedingfield)
    'Mambo No. 5': '',  # Song title (Lou Bega)
    'I Put a Spell on You': '',  # Song title (Screamin' Jay Hawkins)
    'Confide In Me': '',  # Song title (Kylie Minogue)
    'When Doves Cry': '',  # Song title (Prince)
    'Head Over Heels': '',  # Song title (Tears for Fears/Goo Goo Dolls)
    'Stereo Hearts': '',  # Song title (Gym Class Heroes)
    'Run Away': '',  # Song title
    'Lost Umbrella': '',  # Song title (Inabakumori)
    'S-Class': 'KR',  # Stray Kids song → artist
    'ENHYPEN': 'KR',
    'Wellerman': '',  # Song title (sea shanty)
    'DADDY! DADDY! DO!': '',  # Song title (Kaguya-sama)
    'Toss a Coin to Your Witcher': '',  # Song title
    'Blame It On the Boogie': '',  # Song title (The Jacksons)
    'I\'m the alpha': '',  # Song title
    'Gurenge': 'JP',  # LiSA song → Japan
    'NIGHT RUNNING': 'JP',  # AAAMYYY song
    'Shadow Song': '',  # 
    'Rolling in the Deep': '',  # Adele
    'Seven Nation Army': '',  # White Stripes
    'Panini': 'US',  # Lil Nas X song → US
    
    # Real artists that are unmapped
    'FKA Twigs': 'GB',
    'The O\'Reillys And The Paddyhats': 'DE',
    'Xploding Plastix': 'NO',
    'Cowboy Junkie': 'CA',
    'Isaac Hayes': 'US',
    'The Bar-Kays': 'US',
    'Dexys Midnight Runners': 'GB',
    'Lisa Gerrard': 'AU',
    'Victor Wooten': 'US',
    'Elizabeth Cotten': 'US',
    'Israel Kamakawiwo\'ole': 'US',
    'Mountain Goats': 'US',
    'Portishead': 'GB',
    'The Winstons': 'US',
    'half alive': 'US',
    'modernlove': 'IE',
    'ripe': 'US',
    'flor': 'US',
    'La Roux': 'GB',
    'Moses Sumney': 'US',
    'KMFDM': 'DE',
    'Weyes Blood': 'US',
    'Charles Aznavour': 'FR',
    'Sam Ryder': 'GB',
    'Jake Wesley Rogers': 'US',
    'Ellie Dixon': 'GB',
    'Daniel Belanger': 'CA',
    'Liana La Havas': 'GB',
    'Jazz Emu': 'GB',
    'Rina Sawayama': 'JP',
    'ENHYPEN': 'KR',
    'Rufus Wainwright': 'CA',
    'Ahmir': 'US',
    'Lamp': 'JP',
    'Patrick Stump': 'US',
    'Lindsey Stirling': 'US',
    'William Joseph': 'US',
    'Joywave': 'US',
    'Paradise Lost': 'GB',
    'Nic Hanson': 'AU',
    'Ke$ha': 'US',
    'Young Thug': 'US',
    'youngboy never broke again': 'US',
    'Fetty Wap': 'US',
    'Nicki Manaj': 'US',
    'Michelle Branch': 'US',
    'Marilyn Manson': 'US',
    'Phoenix Legend': 'CN',
    'Flo rida': 'US',
    'Vickeblanka': 'JP',
    'Mafumafu': 'JP',
    'Yoasabi': 'JP',
    'Tsuneo Imahori': 'JP',
    'Meaningful Stone': 'KR',
    'kessoku band': 'JP',
    '\u7dd1\u9ec4\u8272\u793e\u4f1a': 'JP',
    'Ryokuoushoku Shakai': 'JP',
    'Yu Peng Chen': 'CN',
    'Owl City': 'US',
    'Carly Rae Jepsen': 'CA',
    'Tyler Ward': 'US',
    'Lifehouse': 'US',
    'Natasha Bedingfield': 'GB',
    'Meghan Trainor': 'US',
    'John Legend': 'US',
    'Gareth Emery': 'GB',
    'Christina Novelli': 'GB',
    'Otto Knows': 'SE',
    'Armin van Buuren': 'NL',
    'Sharon den Adel': 'NL',
    'Sia': 'AU',
    'Diplo': 'US',
    'Labrinth': 'GB',
    'Sigma': 'GB',
    'Birdy': 'GB',
    'Pitbull': 'US',
    'T-Pain': 'US',
    'Yandel': 'PR',
    'Daddy Yankee': 'PR',
    'Christina Perri': 'US',
    'Ed Sheeran': 'GB',
    'Jason Mraz': 'US',
    'Calvin Harris': 'GB',
    'Ellie Goulding': 'GB',
    'CircusP': 'US',
    'Eyeris': 'US',
    'Vicetone': 'NL',
    'Laura Brehm': 'US',
    'Tan WeiWei': 'CN',
    'HangGai band': 'CN',
    '24kGoldn': 'US',
    't.a.t.u': 'RU',
    'Karan Aujla': 'CA',
    'Wang Feng': 'CN',
    '\u5f20\u542b\u97f5': 'CN',
    'Imagine Dragon': 'US',
    'Ro\u00e9lisson Baez': 'HT',
    'Weyes Blood': 'US',
    'Sydney Youngblood': 'US',
    'Emilie-Claire Barlow': 'CA',
}

seeded = 0
for artist, country in new_entries.items():
    if artist not in cache or not cache[artist]:
        cache[artist] = country
        seeded += 1

with open(CACHE_PATH, 'w', encoding='utf-8') as f:
    json.dump(cache, f, ensure_ascii=False, indent=2)

print(f'Seeded {seeded} new entries. Cache now has {len(cache)} entries.')
