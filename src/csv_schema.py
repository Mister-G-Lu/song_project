"""
csv_schema.py — the on-disk schema of the review dataset.

`data/posts_tails.csv` (and its `_additions` overlay) are the project's source
of truth. Until now the song → release-year mapping lived only in a runtime
cascade (curated challenge DB → `data/release_year_cache.json` → a year inside
the title), so it could not be inspected or corrected in the CSV itself.

The dataset now stores that answer per row, in an APPENDED `release_year`
column:

    date,rating,title,tail,artist,song,title_original,title_english,release_year

Appending (rather than inserting) keeps every older consumer of the original
8-column schema working positionally, and files that predate the column still
resolve years the old way.

Kept in its own module (rather than in taste_engine) so the model code can use
it without importing the whole engine.
"""

from datetime import datetime
from typing import List, Optional

# The original 8 columns, in file order.
CSV_COLUMNS: List[str] = [
    'date', 'rating', 'title', 'tail',
    'artist', 'song', 'title_original', 'title_english',
]

# The stored release-year column (always last).
RELEASE_YEAR_COLUMN = 'release_year'
CSV_COLUMNS_WITH_YEAR: List[str] = CSV_COLUMNS + [RELEASE_YEAR_COLUMN]

# Release years outside this window are treated as junk. The window is
# deliberately wide — the collection includes 19th-century classical pieces
# (Liszt's "Feux follets", 1847) — so it only rejects actual typos and
# future dates.
MIN_RELEASE_YEAR = 1000


def coerce_release_year(value) -> Optional[int]:
    """Parse a release_year cell → int, or None when absent/junk.

    Accepts '1976', 1976, '1976.0' and ' 1976 '; rejects '', None, booleans,
    arbitrary strings and implausible years (outside MIN_RELEASE_YEAR..now).
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        year = value
    elif isinstance(value, float):
        if not value.is_integer():
            return None
        year = int(value)
    else:
        text = str(value).strip()
        if not text:
            return None
        if text.endswith('.0') and text[:-2].isdigit():
            text = text[:-2]
        if not text.isdigit():
            return None
        year = int(text)
    if not (MIN_RELEASE_YEAR <= year <= datetime.now().year):
        return None
    return year
