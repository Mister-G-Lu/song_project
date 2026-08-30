"""One-off audit fix: merge corrected artist→genre labels into
data/curated_artist_genres.json, then rebuild the genre cache with the
(now correct) priority: curated → cache → keyword vote.

Run from the project root:
    python scripts/fix_curated_genres.py
"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
CURATED = ROOT / "data" / "curated_artist_genres.json"

# Corrections found by auditing every artist node in the constellation.
# Each artist was mislabeled by keyword-voting (song-title words like
# "dance"/"theme"/"metal") or by the propagation step, and the curated
# mapping is the authoritative override.
CORRECTIONS = {
    # --- Pop ---
    "5 Seconds of Summer": "Rock",  # pop rock (also: see Rock below — dedup)
    "Alessia Cara": "Pop",
    "Alexander Jean": "Pop",
    "Alice Merton": "Pop",
    "Allie X": "Pop",
    "Amy Nuttall": "Pop",
    "Ani Lorak": "Pop",
    "Ansel Elgort": "Pop",
    "Ariana Grande & Justin Bieber": "Pop",
    "Backstreet boys": "Pop",
    "Beyonce": "Pop",
    "BoyWithUke": "Pop",
    "Carly Rae Jepson": "Pop",
    "Charlotte Lawrence": "Pop",
    "CHVRCHES": "Pop",
    "Clean Bandit and Mabel": "Pop",
    "Daniel Powter": "Pop",
    "Daya": "Pop",
    "Dear Happy": "Pop",
    "Dido": "Pop",
    "DNCE": "Pop",
    "Echosmith": "Pop",
    "Edwin McCain": "Pop",
    "FINNEAS": "Pop",
    "Fleur East": "Pop",
    "Fleurie": "Pop",
    "Fun": "Pop",
    "Guy Sebastian": "Pop",
    "Gwen Stefani": "Pop",
    "Harry Styles": "Pop",
    "Haschak Sisters": "Pop",
    "James Arthur": "Pop",
    "Jon Bellion": "Pop",
    "Kat DeLuna": "Pop",
    "Loren Allred": "Pop",
    "Meghan Trainor": "Pop",
    "MEGHAN TRAINOR": "Pop",
    "Misterwives": "Pop",
    "MisterWives": "Pop",
    "MKTO": "Pop",
    "Nena": "Pop",
    "Nerina Pallot": "Pop",
    "Nessa Barrett": "Pop",
    "Niall Horan": "Pop",
    "Olivia rodrigo": "Pop",
    "Phil Collins": "Pop",
    "renforshort": "Pop",
    "Ruth B.": "Pop",
    "Sasha Alex Sloan": "Pop",
    "The Kid Laroi": "Pop",
    "The Kid LAROI": "Pop",
    "The Kid LAROI, Juice WRLD": "Pop",
    "Tyler Ward": "Pop",
    "Wham!": "Pop",
    # --- Rock ---
    "A Perfect Circle": "Rock",
    "Beatles": "Rock",
    "Byrds": "Rock",
    "Eagles": "Rock",
    "Fall Out boy": "Rock",
    "Feeder": "Rock",
    "George Harrison": "Rock",
    "Joe Satriani": "Rock",
    "John Cale": "Rock",
    "LACUNA COIL": "Rock",
    "Rob thomas": "Rock",
    "Rush": "Rock",
    "Santana": "Rock",
    "Smashing Pumpkins": "Rock",
    "Supertramp": "Rock",
    "T.Rex": "Rock",
    "The Bangles": "Rock",
    "The Eagles": "Rock",
    "The HU": "Rock",
    "The Monkees": "Rock",
    "The Strokes": "Rock",
    "The Who": "Rock",
    "Thirty Seconds To Mars": "Rock",
    "Tom Cochrane": "Rock",
    "X Ambassador": "Rock",
    # --- Electronic/Dance ---
    "Au5": "Electronic/Dance",
    "Chain smokers": "Electronic/Dance",
    "Grimes": "Electronic/Dance",
    "marshmello": "Electronic/Dance",
    "Massive Attack": "Electronic/Dance",
    "M83": "Electronic/Dance",
    "Porter Robinson": "Electronic/Dance",
    "Static": "Electronic/Dance",
    "Static P": "Electronic/Dance",
    "Steve Aoki": "Electronic/Dance",
    "The Prodigy": "Electronic/Dance",
    "Tiesto": "Electronic/Dance",
    "Yellow Magic Orchestra": "Electronic/Dance",
    # --- Rap/Hip-Hop ---
    "Baby Keem": "Rap/Hip-Hop",
    "Coolio": "Rap/Hip-Hop",
    "Corpse Husband": "Rap/Hip-Hop",
    "DJ Khaled": "Rap/Hip-Hop",
    "G-easy": "Rap/Hip-Hop",
    "Jay Z": "Rap/Hip-Hop",
    "Lil Uzi Vert": "Rap/Hip-Hop",
    "Macklemore": "Rap/Hip-Hop",
    "Macklemore & Ryan Lewis": "Rap/Hip-Hop",
    "RiceGum": "Rap/Hip-Hop",
    "Tyler, The Creator": "Rap/Hip-Hop",
    # --- R&B/Soul ---
    "Bobby Brown": "R&B/Soul",
    "Ciara": "R&B/Soul",
    "Erykah Badu": "R&B/Soul",
    "Jhené Aiko": "R&B/Soul",
    "Kehlani": "R&B/Soul",
    "Khalid": "R&B/Soul",
    "Sabrina Claudio": "R&B/Soul",
    "TLC": "R&B/Soul",
    "Victoria Monét": "R&B/Soul",
    # --- Indie/Alternative ---
    "Autoheart": "Indie/Alternative",
    "Fickle Friends": "Indie/Alternative",
    "Foster The People": "Indie/Alternative",
    "Gorillaz": "Indie/Alternative",
    "Ingrid Michaelson": "Indie/Alternative",
    "Lord Huron": "Indie/Alternative",
    "Meg Myers": "Indie/Alternative",
    "Miike Snow": "Indie/Alternative",
    "Perfume Genius": "Indie/Alternative",
    "Phoebe Bridgers": "Indie/Alternative",
    "St. Vincent": "Indie/Alternative",
    # --- J-Pop/Anime ---
    "Alstroemeria": "J-Pop/Anime",
    "ASLTROeMERIA": "J-Pop/Anime",
    "BEASTARS": "J-Pop/Anime",
    "Bradio": "J-Pop/Anime",
    "Carole and Tuesday": "J-Pop/Anime",
    "DECO*27": "J-Pop/Anime",
    "Eir Aoi": "J-Pop/Anime",
    "Ikimonogakari": "J-Pop/Anime",
    "Kajiura Yuki": "J-Pop/Anime",
    "KANA-BOON": "J-Pop/Anime",
    "Mai Kuraki": "J-Pop/Anime",
    "TUYU": "J-Pop/Anime",
    "Tuyu": "J-Pop/Anime",
    # --- K-Pop ---
    "AOA": "K-Pop",
    "BLACK6IX": "K-Pop",
    "BTOB (비투비)": "K-Pop",
    "Exo": "K-Pop",
    "Girl's Day": "K-Pop",
    "MAMAMOO": "K-Pop",
    "Orange Caramel": "K-Pop",
    "Orange caramel": "K-Pop",
    "Red Velvet": "K-Pop",
    # --- Metal ---
    "Delain": "Metal",
    "Evanescence": "Metal",
    "Ratt": "Metal",
    "Uncle Acid And The Deadbeats": "Metal",
    # --- Jazz/Swing ---
    "Billie Holiday": "Jazz/Swing",
    "Nina Simone": "Jazz/Swing",
    "Pink Martini": "Jazz/Swing",
    # --- Latin ---
    "Daddy Yankee": "Latin",
    "Wisin & Yandel": "Latin",
    # --- Country ---
    "Lady Antebellum": "Country",
    "Ward Thomas": "Country",
    # --- A Cappella ---
    "PENTATONIX": "A Cappella",
    # --- Soundtrack/Score ---
    "Kimi no nawa": "Soundtrack/Score",
    "Two Steps from Hell": "Soundtrack/Score",
    # --- Folk/Acoustic ---
    "Joanna Newsom": "Folk/Acoustic",
    # --- High-rated unlabeled artists (user's A-tier / 90+ misses) ---
    "AC/DC": "Rock",
    "Auli\u2019i Cravalho": "Soundtrack/Score",  # exact node variant (U+2019 right quot); okina form already present
    "Hololive": "J-Pop/Anime",
    "Kegani": "J-Pop/Anime",
    "Listz": "Classical/Instrumental",     # Liszt's Feux Follets (99/100) parsed as "Listz"
    "Mayu Maeshima": "J-Pop/Anime",
    "Miki Matsubara": "J-Pop/Anime",
    "Vox Machina": "Soundtrack/Score",
}


def main():
    curated = json.loads(CURATED.read_text(encoding="utf-8"))
    added = changed = 0
    for artist, genre in CORRECTIONS.items():
        if artist not in curated:
            curated[artist] = genre
            added += 1
        elif curated[artist] != genre:
            print(f"  OVERRIDE {artist}: {curated[artist]} -> {genre}")
            curated[artist] = genre
            changed += 1
    # Keep the file sorted by artist name for stable diffs.
    curated = dict(sorted(curated.items()))
    CURATED.write_text(
        json.dumps(curated, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"added {added}, overrode {changed}; curated now {len(curated)} entries")

    # Rebuild the persisted genre cache with the corrected priority
    # (curated overrides the propagation vote).
    sys.path.insert(0, str(ROOT))
    from src.taste_engine import TasteEngine  # noqa: E402

    engine = TasteEngine(str(ROOT / "data" / "posts_tails.csv"))
    res = engine.reclassify_genres(use_musicbrainz=False, use_wikidata=False)
    print(
        f"reclassify: uncat {res['before_uncategorized']} -> "
        f"{res['after_uncategorized']}, curated_applied={res['curated_applied']}"
    )


if __name__ == "__main__":
    main()
