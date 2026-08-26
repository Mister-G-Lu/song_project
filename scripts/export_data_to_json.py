"""Export hardcoded Python data structures to JSON files.
Run once to create the JSON data files, then remove the hardcoded data from Python modules.
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.genre_data import GENRE_KEYWORDS, CURATED_ARTIST_GENRES, PARSE_ARTIFACTS, FAVORITE_ARTISTS
from src.challenge_db import CHALLENGE_DB, GENRE_ALIAS_TO_CLASS
from src.backfill import LETTER_GRADE_MAP

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')

def export():
    exports = {
        'genre_keywords.json': GENRE_KEYWORDS,
        'curated_artist_genres.json': CURATED_ARTIST_GENRES,
        'favorite_artists.json': FAVORITE_ARTISTS,
        'parse_artifacts.json': list(PARSE_ARTIFACTS),
        'challenge_db.json': CHALLENGE_DB,
        'genre_alias_to_class.json': GENRE_ALIAS_TO_CLASS,
    }
    
    for filename, data in exports.items():
        path = os.path.join(DATA_DIR, filename)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"  ✓ {filename} ({len(data)} entries)")

    # Backfill letter grade map
    path = os.path.join(DATA_DIR, 'backfill_data.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({
            'letter_grade_map': LETTER_GRADE_MAP
        }, f, indent=2, ensure_ascii=False)
    print(f"  ✓ backfill_data.json")

if __name__ == '__main__':
    export()
