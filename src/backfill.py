"""
backfill.py — Backfill rating recovery utilities
Standalone functions and constants extracted from taste_engine.py.
"""
import re
from typing import Dict, Optional, Tuple


# ============================================================
# Letter grade → numeric rating mapping
# ============================================================

LETTER_GRADE_MAP: Dict[str, int] = {
    'A+': 98, 'A': 95, 'A-': 92,
    'B+': 88, 'B': 85, 'B-': 82,
    'C+': 78, 'C': 75, 'C-': 72,
    'D+': 68, 'D': 65, 'D-': 62,
    'F': 50,
}


def extract_letter_grade(text: str) -> Optional[Tuple[str, int]]:
    """Extract a letter grade and its numeric value from review text.
    
    Returns (grade_str, value) tuple, or (None, None) if no grade found.
    Matches grades at word boundaries, handling + and - suffixes correctly.
    """
    if not text:
        return (None, None)

    # Build the regex pattern.
    # Sort by length descending so 'A+' matches before just 'A'.
    # IMPORTANT: Do NOT require trailing \\b after the grade because
    # 'A+' ends with '+' (non-word), and the next space is also non-word —
    # there is no \\b boundary between two non-word characters.
    # We handle this by checking boundary manually.
    grades = sorted(LETTER_GRADE_MAP.keys(), key=len, reverse=True)
    pattern = r'\b(' + '|'.join(re.escape(g) for g in grades) + r')(?:\b|[^a-zA-Z0-9]|$)'

    m = re.search(pattern, text)
    if m:
        grade_str = m.group(1)
        value = LETTER_GRADE_MAP.get(grade_str)
        if value is not None:
            return (grade_str, value)
    return (None, None)


def infer_tone_rating(text: str) -> Optional[Tuple[Optional[str], Optional[int]]]:
    """Infer a numeric rating from the tone of review text.
    
    Returns (matched_keyword, value) tuple, or (None, None) if tone is neutral.
    """
    if not text:
        return (None, None)

    text_lower = text.lower()

    # Strong positive — you loved it
    m = re.search(r'\b(perfect|masterpiece|flawless)\b', text_lower)
    if m:
        return (m.group(1), 98)

    m = re.search(r'\b(incredible|unbelievable|mind.blowing|best\s+(ever|song))\b', text_lower)
    if m:
        return (m.group(1), 97)

    m = re.search(r'\b(amazing|phenomenal|outstanding)\b', text_lower)
    if m:
        return (m.group(1), 95)

    m = re.search(r'\b(love|beautiful|brilliant|gorgeous|stunning)\b', text_lower)
    if m:
        return (m.group(1), 93)

    m = re.search(r'\b(great|excellent|wonderful|awesome|superb|magnificent|epic)\b', text_lower)
    if m:
        return (m.group(1), 88)

    m = re.search(r'\b(good|solid|decent|liked|pleasant|enjoyed|fun|catchy)\b', text_lower)
    if m:
        return (m.group(1), 84)

    m = re.search(r'\b(nice|fine)\b', text_lower)
    if m:
        return (m.group(1), 82)

    # Neutral / mixed
    if re.search(r'\b(ok|okay)\b', text_lower):
        if 'great' not in text_lower and 'love' not in text_lower:
            return ('ok', 76)

    if re.search(r'\b(meh|average|mediocre|middle|fair|alright)\b', text_lower):
        if 'great' not in text_lower and 'love' not in text_lower:
            return ('meh', 72)

    # Slightly negative
    m = re.search(r'\b(disappointed|disappointing|underwhelming|boring|dull|weak)\b', text_lower)
    if m:
        return (m.group(1), 68)

    m = re.search(r'\b(bad|poor)\b', text_lower)
    if m:
        return (m.group(1), 62)

    m = re.search(r'\b(terrible|awful|horrible|dreadful)\b', text_lower)
    if m:
        return (m.group(1), 50)

    # Worst
    m = re.search(r'\b(worst|hate|trash)\b', text_lower)
    if m:
        return (m.group(1), 40)

    return (None, None)
