#!/usr/bin/env python3
"""Final comprehensive seed + fix for remaining unmapped artists."""
import json, csv, re

CACHE_PATH = 'data/artist_country_cache.json'
CSV_PATH = 'data/posts_tails.csv'

# Load cache
with open(CACHE_PATH, 'r', encoding='utf-8') as f:
    cache = json.load(f)

seeded = 0
new_entries = {
    # Known real artists
    'Kenshi Yonezu, Hikaru Utada': 'JP',  # collab — need to split
    'BTOB': 'KR',
    'IU': 'KR',
    'ENHYPEN': 'KR',
    'Rina Sawayama': 'JP',
    'S3RL': 'GB',
    'Sufjan Stevens': 'US',
    'Yuki Kajiura': 'JP',
    'Nena': 'DE',
    'Yoko Takahashi': 'JP',
    'Edward Sharpe': 'US',
    'The Magnetic Zeros': 'US',
    'Masayoshi Takanaka': 'JP',
    'Boyinaband': 'GB',
    'Meekakitty': 'CA',
    'heyhihello': 'US',
    'Ryan Lewis': 'US',
    'Stone Poneys': 'US',
    'Simon': 'US',
    'Garfunkel': 'US',
    'DMC': 'US',
    'Chubby Checker': 'US',
    'Israel Kamakawiwo\u2019ole': 'US',
    'Polo G': 'US',
    'Paul Anka': 'CA',
    'Odia Coates': 'US',
    'Isaac Hayes': 'US',
    'The Bar-Kays': 'US',
    'Dschinghis Khan': 'DE',
    'Robin Schulz': 'DE',
    'The Prick': 'DE',
    'V\u00e1clav Noid B\u00e1rta': 'CZ',
    'Manu-L': 'CA',
    'Siobhan Miller': 'GB',
    'Bria Lee': 'US',
    'Jimi Cravity': 'KR',
    'Tessa Violet': 'US',
    'Bo Bruce': 'GB',
    'Gareth Emery': 'GB',
    'Rosa Walton': 'GB',
    'Hallie Coggins': 'GB',
    'Lora Lox': 'US',
    'Nathalie Ezmeralda': 'ID',
    'Heiakim': 'KR',
    'Nolimiter': 'US',
    'Camo': 'SE',
    'Silver Maple': 'JP',
    'Troy Young': 'US',
    'EMI//NOVA': 'US',
    'Lora Lox': 'US',
    'Sly': 'US',
    'The Family Stone': 'US',
    'Hyde': 'JP',
    'Kaai Yuki': 'JP',
    'Karan Aujla': 'CA',
    'Desi Crew': 'CA',
    'Dan \u2013 Shay': 'US',
    'Dan + Shay': 'US',
    'The Faim': 'AU',
    'Sara': 'US',
    'Alex': 'US',
    'Sierra': 'US',
    'Jem': 'GB',
    'Nico': 'DE',
    'Vinz': 'NO',
    'Nico & Vinz': 'NO',
    'au/ra': 'GB',
    'Rambupiper (Pied Piper)': 'US',
    'Rina Sawayama (2018)': 'JP',
    'Lindsey Stirling and William Joseph': 'US',
    'Lindsey Stirling and Alex Aris': 'US',
    'Gareth Emery feat. Bo Bruce': 'GB',
    'Tan WeiWei ft.HangGai band': 'CN',
    'Ross Lynch, Jason Evigan': 'US',
    'Kid Laroi and Justin Beiber': 'AU',
    'I DONT KNOW HOW BUT THEY FOUND ME, Tessa Violet': 'US',
    'Sia, Diplo, Labrinth': 'AU',
    '\u5c39\u76f8\u6770\u3001\u4e8e\u6587\u534e': 'CN',
    'Kickberry': 'US',

    # Song titles that should be empty (not real artists)
    'Faded': '',
    'Stay': '',
    'Silhouette': '',
    'Any Other Way': '',
    'Afterglow': '',
    'Rivers': '',
    'Broken': '',
    'Wings': '',
    'One': '',
    'Radio': '',
    'Sad': '',
    'War': '',
    'Rare': '',
    'Yummy': '',
    'DNA': '',
    'Rain': '',
    'Peaches': '',
    'Frozen': '',
    'Break': '',
    'Run Away': '',
    'Sen': '',
    'Love': '',
    'Wet': '',
    '2021': '',
    '2012': '',
    '2013': '',
    '2014': '',
    'TGIF': '',
    'LOSER': '',
    'From The Myth': '',
    '16 Tons': '',

    # Asian artists
    '\u4e09\u6708\u306e\u30d1\u30f3\u30bf\u30b7\u30a2': 'JP',  # 三月のパンタシア
    '\u5c39\u76f8\u6770': 'CN',  # 尹相杰
    '\u4e8e\u6587\u534e': 'CN',  # 于文华
    '\u591a\u591a\u00d7\u7948Inory': 'CN',
    '\u8001\u4e0d\u6b7b\u964d\u4e34\u7684\u95ea\u7535': 'CN',
}

# Apply entries
for artist, country in new_entries.items():
    if artist not in cache or not cache[artist]:
        cache[artist] = country
        seeded += 1

# Save cache
with open(CACHE_PATH, 'w', encoding='utf-8') as f:
    json.dump(cache, f, ensure_ascii=False, indent=2)

print(f'Seeded {seeded} new entries. Cache now has {len(cache)} entries.')
