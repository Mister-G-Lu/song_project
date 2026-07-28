"""
Direct tests for src/backfill.py standalone functions.
Tests the extracted letter-grade and tone-inference functions independently
of the TasteEngine class, demonstrating modular testability.
"""
import pytest
from src.backfill import (
    LETTER_GRADE_MAP,
    extract_letter_grade,
    infer_tone_rating,
)


class TestLetterGradeMap:
    """LETTER_GRADE_MAP should have expected entries."""

    def test_has_all_grades(self):
        assert len(LETTER_GRADE_MAP) == 13
        assert LETTER_GRADE_MAP['A+'] == 98
        assert LETTER_GRADE_MAP['A'] == 95
        assert LETTER_GRADE_MAP['A-'] == 92
        assert LETTER_GRADE_MAP['F'] == 50

    def test_grades_ordered_correctly(self):
        """A+ > A > A- should hold."""
        assert LETTER_GRADE_MAP['A+'] > LETTER_GRADE_MAP['A'] > LETTER_GRADE_MAP['A-']


class TestExtractLetterGrade:
    """Direct tests for extract_letter_grade() — no TasteEngine wrapper."""

    def test_grade_a(self):
        g, v = extract_letter_grade('Score: A')
        assert g == 'A'
        assert v == 95

    def test_grade_a_plus(self):
        g, v = extract_letter_grade('Overall grade: A+ brilliant!')
        assert g == 'A+'
        assert v == 98

    def test_grade_a_minus(self):
        g, v = extract_letter_grade('Rating A- pretty good')
        assert g == 'A-'
        assert v == 92

    def test_grade_b_plus(self):
        g, v = extract_letter_grade('Score: B+ solid enough')
        assert g == 'B+'
        assert v == 88

    def test_grade_f(self):
        g, v = extract_letter_grade('Grade: F. Truly terrible.')
        assert g == 'F'
        assert v == 50

    def test_no_grade(self):
        g, v = extract_letter_grade('This song is just okay.')
        assert g is None
        assert v is None

    def test_empty_string(self):
        g, v = extract_letter_grade('')
        assert g is None
        assert v is None

    def test_no_false_positive_article(self):
        """'a' as an article should NOT match 'A' (case sensitive)."""
        g, v = extract_letter_grade('It was a good song with nice vocals')
        assert g is None
        assert v is None

    def test_grade_in_middle_of_text(self):
        g, v = extract_letter_grade('Really enjoyed this, grade: B- I think')
        assert g == 'B-'
        assert v == 82


class TestInferToneRating:
    """Direct tests for infer_tone_rating() — no TasteEngine wrapper."""

    def test_perfect(self):
        tag, v = infer_tone_rating('A perfect song')
        assert v == 98

    def test_amazing(self):
        tag, v = infer_tone_rating('Absolutely amazing!')
        assert v == 95

    def test_love(self):
        tag, v = infer_tone_rating('I love this song')
        assert v == 93

    def test_great(self):
        tag, v = infer_tone_rating('A really great track')
        assert v == 88

    def test_good(self):
        tag, v = infer_tone_rating('It is a good song')
        assert v == 84

    def test_ok(self):
        tag, v = infer_tone_rating('It was ok I guess')
        assert v == 76

    def test_meh(self):
        tag, v = infer_tone_rating('Meh, it was whatever')
        assert v == 72

    def test_bad(self):
        tag, v = infer_tone_rating('This song is bad')
        assert v == 62

    def test_terrible(self):
        tag, v = infer_tone_rating('Terrible song, awful')
        assert v == 50

    def test_worst(self):
        tag, v = infer_tone_rating('The worst song I have ever heard')
        assert v == 40

    def test_empty(self):
        tag, v = infer_tone_rating('')
        assert tag is None
        assert v is None

    def test_no_match(self):
        tag, v = infer_tone_rating('This is a song about things.')
        assert tag is None
        assert v is None

    def test_disappointed(self):
        tag, v = infer_tone_rating('Disappointing, could be better')
        assert v == 68

    def test_keyword_returned(self):
        """Should return the matched keyword as the first element."""
        tag, v = infer_tone_rating('Incredible! Mind-blowing stuff')
        assert tag is not None
        assert isinstance(tag, str)
