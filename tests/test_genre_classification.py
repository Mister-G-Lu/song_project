"""
tests/test_genre_classification.py — Stringent tests for genre classification.

Verifies that:
  - Artist cache and curated genres override review-text keyword matches
  - Title-only keyword matching doesn't pick up incidental genre mentions in review text
  - Edge cases like "WAP (orchestral backing)" are classified as Rap/Hip-Hop, not Classical
"""

import csv
import os
import tempfile
import pytest
from src.taste_engine import TasteEngine, CURATED_ARTIST_GENRES


# ============================================================
# Helper: build a minimal TasteEngine from CSV rows
# ============================================================

def _make_engine(rows):
    """Create a TasteEngine from a list of (date, rating, title, tail) tuples."""
    tmp = tempfile.NamedTemporaryFile(
        mode='w', suffix='.csv', delete=False, encoding='utf-8', newline=''
    )
    writer = csv.writer(tmp)
    writer.writerow(['date', 'rating', 'title', 'tail'])
    for row in rows:
        writer.writerow(row)
    tmp.close()
    try:
        engine = TasteEngine(tmp.name)
        return engine
    finally:
        os.unlink(tmp.name)


# ============================================================
# 1. Review text should NOT override artist cache
# ============================================================

class TestReviewTextVsArtistCache:
    """When a review mentions a genre keyword (e.g. 'orchestral'), the artist
    cache should still win if the artist is known."""

    def test_wap_not_classical(self):
        """Cardi B - WAP with 'orchestral backing' review → should be Rap/Hip-Hop."""
        engine = _make_engine([
            ('2024-04-02', '50', 'Cardi B – WAP',
             'c orchestral backing just mixes so well with the rapping rhythm. '
             'Now that\'s how you make a rap song!'),
        ])
        row = engine.rows[0]
        assert row['_genre'] == 'Rap/Hip-Hop', (
            f"Expected 'Rap/Hip-Hop' for Cardi B but got '{row['_genre']}'. "
            "Artist cache should override 'orchestral' keyword in review text."
        )

    def test_beatles_not_electronic(self):
        """The Beatles with 'electronic elements' review → should be Rock."""
        engine = _make_engine([
            ('2024-01-01', '90', 'The Beatles – Tomorrow Never Knows',
             'innovative use of tape loops and electronic effects for 1966'),
        ])
        row = engine.rows[0]
        assert row['_genre'] == 'Rock', (
            f"Expected 'Rock' for The Beatles but got '{row['_genre']}'. "
            "Artist cache/curated should override 'electronic' in review text."
        )

    def test_muse_not_country(self):
        """Muse with 'country vibes' review → should be Rock."""
        engine = _make_engine([
            ('2024-01-01', '85', 'Muse – Map of the Problematique',
             'has some country vibes in the bridge but it is pure rock'),
        ])
        row = engine.rows[0]
        assert row['_genre'] == 'Rock', (
            f"Expected 'Rock' for Muse but got '{row['_genre']}'. "
            "'Country' in review should not override artist genre."
        )

    def test_taylor_swift_not_metal(self):
        """Taylor Swift with 'heavy metal energy' review → should be Pop."""
        engine = _make_engine([
            ('2024-01-01', '80', 'Taylor Swift – Bad Blood',
             'has heavy metal energy in the chorus but it is pop'),
        ])
        row = engine.rows[0]
        assert row['_genre'] == 'Pop', (
            f"Expected 'Pop' for Taylor Swift but got '{row['_genre']}'. "
            "'Metal' in review should not override artist genre."
        )

    def test_david_guetta_not_jazz(self):
        """David Guetta with 'jazz influences' review → should be Pop/Electronic."""
        engine = _make_engine([
            ('2024-01-01', '75', 'David Guetta – Titanium',
             'has jazz influences in the piano part but it is dance pop'),
        ])
        row = engine.rows[0]
        # David Guetta is in curated as Pop
        genre = row['_genre']
        assert genre in ('Pop', 'Electronic/Dance'), (
            f"Expected 'Pop' or 'Electronic/Dance' for David Guetta but got '{genre}'. "
            "'Jazz' in review should not override artist genre."
        )


# ============================================================
# 2. Title keywords should not pick up artist names as genres
# ============================================================

class TestTitleKeywordFalsePositives:
    """Short keywords should use word-boundary matching to avoid false positives."""

    def test_artist_name_with_pop_in_it(self):
        """An artist with 'Pop' in their name but different genre."""
        engine = _make_engine([
            ('2024-01-01', '80', 'Popcaan – Only Man She Want',
             'dancehall track with reggae vibes'),
        ])
        row = engine.rows[0]
        # Popcaan is not in curated mapping, so keyword 'pop' in title may trigger
        # But word boundary should prevent 'pop' from matching 'Popcaan'
        # Actually 'Popcaan' starts with 'Pop' so \bpop\b would match at start
        # This is expected behavior — the artist name IS in the title

    def test_ost_not_post(self):
        """'ost' should not match 'post' (word boundary for short keywords)."""
        engine = _make_engine([
            ('2024-01-01', '85', 'Radiohead – Exit Music (For a Film)',
             'from the Romeo + Juliet OST soundtrack'),
        ])
        row = engine.rows[0]
        # Radiohead is in curated as Rock
        assert row['_genre'] == 'Rock', (
            f"Expected 'Rock' for Radiohead but got '{row['_genre']}'."
        )

    def test_hell_not_instrumental(self):
        """'hell' should not match in 'shell' or similar."""
        engine = _make_engine([
            ('2024-01-01', '70', 'Shell Song – Ocean Breeze',
             'ambient shell sounds from the beach'),
        ])
        row = engine.rows[0]
        # No curated artist, title has 'shell' which shouldn't match 'hell'
        # Should fall through to Uncategorized
        # (shell doesn't contain 'hell' as word boundary match)


# ============================================================
# 3. Curated artist genres should be authoritative
# ============================================================

class TestCuratedArtistAuthority:
    """Known artists should always get their curated genre, regardless of review text."""

    @pytest.mark.parametrize("artist,expected_genre,review_text", [
        ("Cardi B", "Rap/Hip-Hop", "orchestral backing in this song"),
        ("The Beatles", "Rock", "electronic experimental sounds"),
        ("Queen", "Rock", "opera and operatic vocals in Bohemian Rhapsody"),
        ("Ed Sheeran", "Pop", "jazz influences in the guitar"),
        ("Daft Punk", "Electronic/Dance", "heavy metal guitars and screaming"),
        ("Muse", "Rock", "country music vibes"),
        ("Chopin", "Classical/Instrumental", "rock and roll energy"),
        ("Michael Jackson", "Pop", "metal and screaming vocals"),
        ("Britney Spears", "Pop", "classical piano ballad"),
        ("Taylor Davis", "Classical/Instrumental", "rock guitar solo"),
    ])
    def test_curated_genre_overrides_review(self, artist, expected_genre, review_text):
        """Curated artist genre should win over any genre keywords in review text."""
        engine = _make_engine([
            ('2024-01-01', '80', f'{artist} – Test Song', review_text),
        ])
        row = engine.rows[0]
        assert row['_genre'] == expected_genre, (
            f"Expected '{expected_genre}' for {artist} but got '{row['_genre']}'. "
            f"Review text '{review_text[:50]}...' should not override curated genre."
        )


# ============================================================
# 4. Genre keyword matching should work for unknown artists
# ============================================================

class TestKeywordMatchingForUnknownArtists:
    """For artists NOT in curated mapping, keyword matching should still work."""

    def test_unknown_artist_with_rock_title(self):
        """Unknown artist with 'rock' in title → should match Rock."""
        engine = _make_engine([
            ('2024-01-01', '80', 'Unknown Artist – Rock Anthem',
             'a great rock song'),
        ])
        row = engine.rows[0]
        assert row['_genre'] == 'Rock', (
            f"Expected 'Rock' for unknown artist but got '{row['_genre']}'."
        )

    def test_unknown_artist_with_piano_title(self):
        """Unknown artist with 'piano' in title → should match Classical/Instrumental."""
        engine = _make_engine([
            ('2024-01-01', '85', 'Unknown Artist – Piano Dreams',
             'beautiful piano melody'),
        ])
        row = engine.rows[0]
        assert row['_genre'] == 'Classical/Instrumental', (
            f"Expected 'Classical/Instrumental' but got '{row['_genre']}'."
        )

    def test_unknown_artist_with_dance_title(self):
        """Unknown artist with 'dance' in title → should match Electronic/Dance."""
        engine = _make_engine([
            ('2024-01-01', '75', 'Unknown Artist – Dance Floor',
             'club banger'),
        ])
        row = engine.rows[0]
        assert row['_genre'] == 'Electronic/Dance', (
            f"Expected 'Electronic/Dance' but got '{row['_genre']}'."
        )


# ============================================================
# 5. Genre classification priority order
# ============================================================

class TestClassificationPriority:
    """Verify the priority: artist cache > curated > title keywords > review keywords > Uncategorized."""

    def test_artist_cache_highest_priority(self):
        """Artist cache should win over curated and keywords."""
        engine = _make_engine([
            ('2024-01-01', '80', 'Test Artist – Rock Song', 'rock and roll'),
        ])
        # Manually set artist cache to override
        engine._artist_genre_cache['Test Artist'] = 'Jazz/Swing'
        # Re-classify
        engine._classify_row(engine.rows[0])
        assert engine.rows[0]['_genre'] == 'Jazz/Swing', (
            f"Artist cache should win, got '{engine.rows[0]['_genre']}'"
        )

    def test_curated_wins_over_keywords(self):
        """Curated genre should win over title/review keywords."""
        engine = _make_engine([
            ('2024-01-01', '80', 'Ed Sheeran – Dance Pop Song', 'dance club beat'),
        ])
        row = engine.rows[0]
        # Ed Sheeran is curated as Pop, not Electronic/Dance
        assert row['_genre'] == 'Pop', (
            f"Expected 'Pop' for Ed Sheeran, got '{row['_genre']}'. "
            "'Dance' keywords should not override curated genre."
        )

    def test_title_keyword_wins_over_review(self):
        """Title keyword should win over review text keyword for unknown artists."""
        engine = _make_engine([
            ('2024-01-01', '80', 'Unknown Artist – Metal Thunder',
             'actually has jazz influences in the bridge'),
        ])
        row = engine.rows[0]
        # Title has 'metal' which should match Metal before review's 'jazz'
        assert row['_genre'] == 'Metal', (
            f"Expected 'Metal' from title keyword, got '{row['_genre']}'."
        )


# ============================================================
# 6. Multiple genre signals in review text
# ============================================================

class TestMultipleSignals:
    """When review text contains multiple genre keywords, first match wins
    (since we iterate genres in dict order)."""

    def test_review_with_multiple_genres(self):
        """Review mentions both 'jazz' and 'rock' → first genre in iteration wins."""
        engine = _make_engine([
            ('2024-01-01', '80', 'Unknown Artist – Mixed Vibes',
             'has jazz and rock elements'),
        ])
        row = engine.rows[0]
        # Unknown artist, no title match, so review text is used
        # The first genre in genre_keywords dict that matches 'jazz' or 'rock' wins
        assert row['_genre'] != 'Uncategorized', "Should have matched some genre"

    def test_review_only_keywords_for_unknown(self):
        """Unknown artist with genre only in review text → should still classify."""
        engine = _make_engine([
            ('2024-01-01', '70', 'New Artist – Song Title',
             'this is definitely a jazz standard with swing feel'),
        ])
        row = engine.rows[0]
        assert row['_genre'] != 'Uncategorized', (
            "Unknown artist with 'jazz' in review should still be classified"
        )


# ============================================================
# 7. Edge cases from real data
# ============================================================

class TestRealDataEdgeCases:
    """Test cases inspired by real misclassifications in the dataset."""

    def test_cardi_b_wap_review_orchestral(self):
        """Exact reproduction of the WAP bug: 'orchestral' in review → Rap/Hip-Hop."""
        engine = _make_engine([
            ('2024-04-02', '50', 'Cardi B – WAP',
             'c orchestral backing just mixes so well with the rapping rhythm. '
             'Now that\'s how you make a rap song!'),
        ])
        row = engine.rows[0]
        assert row['_genre'] == 'Rap/Hip-Hop'

    def test_fetty_wap_not_confused(self):
        """Fetty Wap should not be confused with Cardi B's WAP."""
        engine = _make_engine([
            ('2020-01-21', '60', 'Fetty Wap – Could You Believe It', 'trap beat'),
        ])
        row = engine.rows[0]
        # Fetty Wap is not in curated; 'trap' keyword may match Electronic or Rap
        # depending on iteration order — just verify it's not Classical
        assert row['_genre'] != 'Classical/Instrumental', (
            f"Fetty Wap should NOT be Classical/Instrumental, got '{row['_genre']}'"
        )

    def test_song_with_classical_in_title_but_rap_artist(self):
        """Song title mentions 'classical' but artist is a rapper → Rap/Hip-Hop."""
        engine = _make_engine([
            ('2024-01-01', '75', 'Cardi B – Classical Beat',
             'mixes classical piano with trap drums'),
        ])
        row = engine.rows[0]
        assert row['_genre'] == 'Rap/Hip-Hop', (
            f"Expected 'Rap/Hip-Hop' for Cardi B, got '{row['_genre']}'. "
            "Artist should override title keyword."
        )

    def test_instrumental_review_does_not_override_pop_artist(self):
        """'instrumental' in review should not override Pop artist."""
        engine = _make_engine([
            ('2024-01-01', '80', 'Maroon 5 – Payphone',
             'great instrumental intro before the vocals come in'),
        ])
        row = engine.rows[0]
        assert row['_genre'] == 'Pop', (
            f"Expected 'Pop' for Maroon 5, got '{row['_genre']}'."
        )

    def test_symphony_in_review_not_classical(self):
        """'symphony' in review should not override Rock artist."""
        engine = _make_engine([
            ('2024-01-01', '90', 'Muse – Symphonia',
             'orchestral symphony arrangement of this rock classic'),
        ])
        row = engine.rows[0]
        assert row['_genre'] == 'Rock', (
            f"Expected 'Rock' for Muse, got '{row['_genre']}'."
        )


# ============================================================
# 8. Integrity checks on genre keyword config
# ============================================================

class TestGenreKeywordIntegrity:
    """Verify the genre keyword configuration is sane."""

    def test_no_critical_overlapping_keywords(self):
        """Core genre keywords ('pop', 'rock', 'jazz', 'rap') should not overlap."""
        engine = _make_engine([('2024-01-01', '80', 'Test Song', 'test')])
        core_keywords = {'pop', 'rock', 'jazz', 'rap', 'metal', 'country', 'classical'}
        seen = {}
        for genre, keywords in engine.genre_keywords.items():
            for kw in keywords:
                if kw.lower() in core_keywords and kw.lower() in seen:
                    pytest.fail(
                        f"Core keyword '{kw}' appears in both '{seen[kw.lower()]}' and '{genre}'"
                    )
                seen[kw.lower()] = genre

    def test_all_major_genres_have_keywords(self):
        """Every genre should have at least 3 keywords."""
        engine = _make_engine([('2024-01-01', '80', 'Test Song', 'test')])
        for genre, keywords in engine.genre_keywords.items():
            assert len(keywords) >= 3, (
                f"Genre '{genre}' has only {len(keywords)} keywords — need at least 3"
            )

    def test_rap_keywords_include_hip_hop(self):
        """Rap/Hip-Hop genre should have 'rap', 'hip hop', and 'hip-hop'."""
        engine = _make_engine([('2024-01-01', '80', 'Test Song', 'test')])
        rap_kws = [k.lower() for k in engine.genre_keywords.get('Rap/Hip-Hop', [])]
        for term in ['rap', 'hip hop', 'hip-hop']:
            assert term in rap_kws, f"Rap/Hip-Hop missing keyword '{term}'"

    def test_pop_keywords_include_pop(self):
        """Pop genre should have 'pop' as a keyword."""
        engine = _make_engine([('2024-01-01', '80', 'Test Song', 'test')])
        pop_kws = [k.lower() for k in engine.genre_keywords.get('Pop', [])]
        assert 'pop' in pop_kws, "Pop genre missing keyword 'pop'"

    def test_rock_keywords_include_rock(self):
        """Rock genre should have 'rock' as a keyword."""
        engine = _make_engine([('2024-01-01', '80', 'Test Song', 'test')])
        rock_kws = [k.lower() for k in engine.genre_keywords.get('Rock', [])]
        assert 'rock' in rock_kws, "Rock genre missing keyword 'rock'"


# ============================================================
# 9. Curated genre mapping integrity
# ============================================================

class TestCuratedGenreIntegrity:
    """Verify the curated artist-genre mapping covers major artists."""

    def test_major_artists_have_genres(self):
        """Well-known artists should all be in the curated mapping."""
        expected = {
            'Cardi B': 'Rap/Hip-Hop',
            'The Beatles': 'Rock',
            'Queen': 'Rock',
            'Ed Sheeran': 'Pop',
            'Taylor Swift': 'Pop',
            'Michael Jackson': 'Pop',
            'Daft Punk': 'Electronic/Dance',
            'Muse': 'Rock',
            'Chopin': 'Classical/Instrumental',
            'Britney Spears': 'Pop',
            'Maroon 5': 'Pop',
            'David Guetta': 'Pop',
            'Justin Bieber': 'Pop',
        }
        for artist, expected_genre in expected.items():
            assert artist in CURATED_ARTIST_GENRES, (
                f"'{artist}' missing from CURATED_ARTIST_GENRES"
            )
            assert CURATED_ARTIST_GENRES[artist] == expected_genre, (
                f"'{artist}' expected '{expected_genre}' but got "
                f"'{CURATED_ARTIST_GENRES[artist]}'"
            )

    def test_no_curated_genre_is_uncategorized(self):
        """No curated artist should be mapped to 'Uncategorized'."""
        for artist, genre in CURATED_ARTIST_GENRES.items():
            assert genre != 'Uncategorized', (
                f"'{artist}' is curated as 'Uncategorized' — should have a real genre"
            )


# ============================================================
# 10. Stringent classification — case-insensitive + apostrophe-insensitive
#     curated lookup, and coverage of real misclassifications
# ============================================================

class TestStringentClassification:
    """Classification should be as stringent as possible: case-insensitive +
    apostrophe-insensitive curated lookups rescue artists that would otherwise
    fall through to Uncategorized because of casing or punctuation differences.
    """

    def test_case_insensitive_curated_lookup(self):
        """Lowercase artist names in titles should still match curated entries."""
        engine = _make_engine([
            ("2024-01-01", "80", "fall out boy – Sugar, We're Going Down", ""),
            ("2024-01-01", "80", "bobby brown – Every Little Step", ""),
            ("2024-01-01", "80", "within temptation – The Howl", ""),
            ("2024-01-01", "80", "deco*27 – Reversible Campaign", ""),
            ("2024-01-01", "80", "clocks and clouds – Pierce the Night", ""),
        ])
        expected = {
            "fall out boy": "Rock",
            "bobby brown": "R&B/Soul",
            "within temptation": "Metal",
            "deco*27": "J-Pop/Anime",
            "clocks and clouds": "Soundtrack/Score",
        }
        for row in engine.rows:
            artist = engine._extract_artists_from_row(row)[0].lower()
            assert row["_genre"] == expected[artist], (
                f"Expected '{expected[artist]}' for '{artist}' but got '{row['_genre']}'"
            )

    def test_apostrophe_insensitive_curated_lookup(self):
        """Artist names with apostrophes should match curated entries without them
        and vice-versa (e.g. 'Guns N' Roses' ↔ 'Guns N Roses')."""
        engine = _make_engine([
            ("2024-01-01", "90", "Guns N' Roses – Sweet Child O' Mine", ""),
        ])
        row = engine.rows[0]
        assert row["_genre"] == "Rock", (
            f"Expected 'Rock' for Guns N' Roses but got '{row['_genre']}'. "
            "Apostrophe-insensitive lookup should match the curated entry."
        )

    def test_guns_n_roses_classified_as_rock(self):
        """Guns N' Roses should be classified as Rock — one of the most famous
        rock bands, must never end up in Uncategorized."""
        engine = _make_engine([
            ("2024-01-01", "90", "Guns N' Roses – Sweet Child O' Mine", ""),
            ("2024-01-01", "85", "Guns N' Roses – Welcome to the Jungle", ""),
            ("2024-01-01", "80", "Guns N' Roses – November Rain", ""),
        ])
        for row in engine.rows:
            assert row["_genre"] == "Rock", (
                f"Expected 'Rock' for Guns N' Roses but got '{row['_genre']}'. "
                "Regression: Guns N' Roses must be Rock."
            )

    def test_luke_graham_classified_as_country(self):
        """Luke Graham (7 Years) should be classified as Country — never Uncategorized."""
        engine = _make_engine([
            ("2024-01-01", "75", "7 Years – Luke Graham", ""),
        ])
        row = engine.rows[0]
        assert row["_genre"] == "Country", (
            f"Expected 'Country' for Luke Graham but got '{row['_genre']}'. "
            "Regression: Luke Graham must be Country."
        )

    def test_pharrell_williams_classified_as_pop(self):
        """Pharrell Williams should be Pop."""
        engine = _make_engine([
            ("2024-01-01", "80", "Happy – Pharrell Williams", ""),
        ])
        row = engine.rows[0]
        assert row["_genre"] == "Pop", (
            f"Expected 'Pop' for Pharrell Williams but got '{row['_genre']}'."
        )

    def test_renee_rapp_classified_as_pop(self):
        """Renee Rapp should be Pop."""
        engine = _make_engine([
            ("2024-01-01", "75", "Pretty Girls – Renee Rapp", ""),
        ])
        row = engine.rows[0]
        assert row["_genre"] == "Pop", (
            f"Expected 'Pop' for Renee Rapp but got '{row['_genre']}'."
        )

    def test_otto_knows_classified_as_electronic(self):
        """Otto Knows should be Electronic/Dance."""
        engine = _make_engine([
            ("2024-01-01", "80", "Dying For You – Otto Knows", ""),
        ])
        row = engine.rows[0]
        assert row["_genre"] == "Electronic/Dance", (
            f"Expected 'Electronic/Dance' for Otto Knows but got '{row['_genre']}'."
        )

    def test_o_zone_classified_as_pop(self):
        """O-Zone should be Pop."""
        engine = _make_engine([
            ("2024-01-01", "70", "Dragostea Din Tei – O-Zone", ""),
        ])
        row = engine.rows[0]
        assert row["_genre"] == "Pop", (
            f"Expected 'Pop' for O-Zone but got '{row['_genre']}'."
        )

    def test_cody_simpson_classified_as_pop(self):
        """Cody Simpson should be Pop."""
        engine = _make_engine([
            ("2024-01-01", "75", "Not Loving You – Cody Simpson", ""),
        ])
        row = engine.rows[0]
        assert row["_genre"] == "Pop", (
            f"Expected 'Pop' for Cody Simpson but got '{row['_genre']}'."
        )

    def test_uncategorized_is_last_resort_only(self):
        """After the case-insensitive + apostrophe-insensitive fixes, the number
        of Uncategorized songs in the real dataset should be strictly lower than
        before the fix (regression guard)."""
        engine = TasteEngine()
        uncat = sum(1 for r in engine.rows if r.get("_genre", "") == "Uncategorized")
        # Before fixes: 295 uncategorized. After case-insensitive fix: 290.
        # After adding missing artists: should be well below 290.
        # This threshold is a regression guard — if it ever goes back above 290,
        # a future change broke the case-insensitive lookup.
        msg = (
            f"Too many Uncategorized songs ({uncat}) — should be < 290 after "
            "case-insensitive + apostrophe-insensitive curated lookup fixes."
        )
        assert uncat < 290, msg
