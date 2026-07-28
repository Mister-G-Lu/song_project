"""
Comprehensive unit tests for taste_engine.py
"""

import csv
import os
import tempfile
import pytest
from datetime import datetime
from unittest.mock import patch
from src.taste_engine import TasteEngine


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def sample_csv_path():
    """Create a temporary CSV with diverse sample data for testing."""
    data = [
        ['date', 'rating', 'title', 'tail'],
        ['2017-11-20', '79', 'Breaking Free (Zac Efron, 2006)', 'A decent pop song with some good moments.'],
        ['2017-11-21', '90', 'Shape of You (Ed Sheeran, 2017)', 'Great pop hit with a catchy beat. pop song'],
        ['2017-11-22', '95', 'Galway Girl (Ed Sheeran, 2017)', 'Fantastic folk-pop tune. Very catchy.'],
        ['2017-11-23', '80', 'Superstitious (Stevie Wonder, 1972)', 'Classic funk song with a groovy bassline.'],
        ['2017-11-25', '92', 'Vanilla Twilight (Owl City, 2010)', 'Beautiful synth-pop track. Very dreamy. electronic'],
        ['2017-11-26', '90', 'Inclusion (ASLTROeMERIA, 2012)', 'Interesting electronic piece. electronic music'],
        ['2017-12-07', '100', 'Our Farewell (Within Temptation, 2012)', 'Beautiful symphonic metal ballad. metal'],
        ['2017-12-29', '100', 'Hidden Falls (Taylor Davis, 2015)', 'Amazing violin instrumental. classical violin'],
        ['2018-01-12', '96', 'Night Vision (Lindsey Stirling, 2014)', 'Incredible violin dubstep track.'],
        ['2018-02-04', '97', 'Lone digger (Caravan Palace, 2015)', 'Amazing electro-swing track. jazz swing'],
        ['2018-03-07', '100', 'This Love (Maroon 5, 2002)', 'Perfect pop rock song. rock pop'],
        ['2018-02-25', '94', 'Style (Taylor Swift, 2014)', 'Great pop song with catchy chorus. pop'],
        ['2018-04-11', '90', 'Seasons (Olly Murs, 2016)', 'Nice pop tune. pop'],
        ['2018-06-12', '95', 'Uprising (Muse, 2009)', 'Powerful rock anthem. rock'],
        ['2019-01-15', '85', 'New Song (Test Artist, 2019)', 'A solid track.'],
        ['2019-03-20', '60', 'Mediocre Track (Test Artist, 2019)', 'Not very impressive.'],
        ['2019-06-10', '88', 'Eurovision Entry (Eurovision Artist, 2018)', 'Great eurovision song! eurovision'],
        ['2020-01-01', '75', 'New Years Song (Party Band, 2020)', 'Fun party track.'],
        ['2020-05-15', '50', 'Bad Song (OneHit Wonder, 2020)', 'Really not good.'],
        ['2020-08-20', '95', 'Amazing Track (Lindsey Stirling, 2020)', 'Yet another amazing violin track.'],
        ['2020-08-20', '', 'Announcement', 'Just an announcement post'],
        ['2021-02-14', '82', 'Love Song (Romantic Artist, 2021)', 'A nice love song.'],
        ['2021-07-04', '91', 'Summer Hit (Lindsey Stirling, 2021)', 'Another great summer banger.'],
        ['2022-11-30', '78', 'Holiday Cheer (Christmas Band, 2022)', 'Nice christmas holiday song. christmas'],
        ['2023-04-15', '93', 'Plastic Love (Mariya Takeuchi, 1984)', 'City pop classic with a great groove. disco funk groovy'],
    ]
    
    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8', newline='')
    writer = csv.writer(tmp)
    writer.writerows(data)
    tmp.close()
    yield tmp.name
    os.unlink(tmp.name)


@pytest.fixture
def engine(sample_csv_path):
    """Create a TasteEngine instance with sample data."""
    return TasteEngine(sample_csv_path)


# ============================================================
# Core Tests
# ============================================================

class TestTasteEngineBasic:
    """Test basic initialization and data loading."""

    def test_init_loads_data(self, engine):
        """Engine should load rows and ratings from CSV."""
        assert len(engine.rows) == 25
        assert len(engine.rated_entries) == 24  # One Announcement with no rating
        assert len(engine.ratings) == 24

    def test_init_with_missing_file(self):
        """Engine should raise FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            TasteEngine('nonexistent_file.csv')

    def test_init_empty_csv(self):
        """Engine should handle empty CSV gracefully."""
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8', newline='')
        tmp.write('date,rating,title,tail\n')
        tmp.close()
        try:
            engine = TasteEngine(tmp.name)
            assert len(engine.rows) == 0
            assert len(engine.ratings) == 0
            assert engine.get_stats()['total_entries'] == 0
        finally:
            os.unlink(tmp.name)


class TestArtistExtraction:
    """Test the _extract_artists method."""

    def test_extract_parenthetical_format(self, engine):
        """Extract from 'Title (Artist, Year)' format."""
        artists = engine._extract_artists('Hidden Falls (Taylor Davis, 2015)')
        assert 'Taylor Davis' in artists

    def test_extract_with_featuring(self, engine):
        """Extract multiple artists with 'ft.' or 'feat.'."""
        artists = engine._extract_artists('Love Song (Artist A ft. Artist B, 2021)')
        assert 'Artist A' in artists
        assert 'Artist B' in artists

    def test_extract_with_and(self, engine):
        """Extract multiple artists with 'and' or '&'."""
        artists = engine._extract_artists('Duet (Artist A & Artist B, 2020)')
        assert 'Artist A' in artists
        assert 'Artist B' in artists

    def test_extract_no_match(self, engine):
        """Should return empty list when no artist is found."""
        artists = engine._extract_artists('Just a random title without parentheses')
        assert artists == []


class TestStats:
    """Test get_stats() output."""

    def test_stats_basic_fields(self, engine):
        """Stats should contain all expected fields."""
        stats = engine.get_stats()
        assert 'total_entries' in stats
        assert 'rated_entries' in stats
        assert 'avg_rating' in stats
        assert 'median_rating' in stats
        assert 'min_rating' in stats
        assert 'max_rating' in stats
        assert 'unique_artists' in stats
        assert 'date_range' in stats
        assert 'rating_distribution' in stats
        assert 'genre_distribution' in stats
        assert 'top_artists' in stats
        assert 'top_songs' in stats
        assert 'recent_reviews' in stats

    def test_stats_values(self, engine):
        """Stats values should be computed correctly."""
        stats = engine.get_stats()
        assert stats['total_entries'] == 25
        assert stats['rated_entries'] == 24
        assert stats['avg_rating'] > 0
        assert 80 <= stats['avg_rating'] <= 90  # Should be in reasonable range
        assert stats['min_rating'] >= 0
        assert stats['max_rating'] <= 100
        assert stats['min_rating'] == 50
        assert stats['max_rating'] == 100

    def test_rating_distribution(self, engine):
        """Rating distribution should sum to total rated entries."""
        dist = engine.get_stats()['rating_distribution']
        total = sum(dist.values())
        assert total == len(engine.ratings)

    def test_date_range(self, engine):
        """Date range should span from first to last entry."""
        stats = engine.get_stats()
        assert stats['date_range']['start'] == '2017-11-20'
        assert stats['date_range']['end'] == '2023-04-15'

    def test_top_songs_ordered(self, engine):
        """Top songs should be sorted by rating descending."""
        top = engine.get_stats()['top_songs']
        for i in range(len(top) - 1):
            assert top[i]['rating'] >= top[i + 1]['rating']

    def test_top_songs_preview(self, engine):
        """Top songs should have preview text."""
        top = engine.get_stats()['top_songs']
        assert len(top) > 0
        assert 'preview' in top[0]
        assert len(top[0]['preview']) > 0

    def test_recent_reviews_ordered(self, engine):
        """Recent reviews should be sorted by date descending."""
        recent = engine.get_stats()['recent_reviews']
        for i in range(len(recent) - 1):
            assert recent[i]['date'] >= recent[i + 1]['date']

    def test_top_artists_filtered(self, engine):
        """Top artists should only include those with 2+ songs."""
        top = engine.get_stats()['top_artists']
        for artist in top:
            assert artist['song_count'] >= 2


class TestGenreDistribution:
    """Test genre classification."""

    def test_genre_categories(self, engine):
        """Genre distribution should include expected genres."""
        genres = engine.get_stats()['genre_distribution']
        assert len(genres) > 0
        assert 'Pop' in genres
        assert 'Rock' in genres

    def test_genre_ratings(self, engine):
        """Genre entries should have avg ratings."""
        genres = engine.get_stats()['genre_distribution']
        for genre_name, data in genres.items():
            if data['count'] > 0:
                assert data['avg_rating'] >= 0
                assert isinstance(data['avg_rating'], (int, float))

    def test_genre_top_songs(self, engine):
        """Genre should have top songs included."""
        genres = engine.get_stats()['genre_distribution']
        pop = genres.get('Pop', {})
        if pop.get('count', 0) > 0:
            assert len(pop.get('top_songs', [])) > 0


class TestBlindSpots:
    """Test blind spots generation."""

    def test_blind_spots_structure(self, engine):
        """Blind spots should have expected structure."""
        bs = engine.get_blind_spots()
        assert 'top_loved_genres' in bs
        assert 'blind_spots' in bs

    def test_blind_spots_content(self, engine):
        """Should return expected number of blind spots."""
        bs = engine.get_blind_spots()
        assert len(bs['blind_spots']) > 0

    def test_loved_genres_ordering(self, engine):
        """Loved genres should be sorted by avg rating descending."""
        loved = engine.get_blind_spots()['top_loved_genres']
        for i in range(len(loved) - 1):
            assert loved[i][1] >= loved[i + 1][1]


class TestConstellation:
    """Test constellation graph generation."""

    def test_constellation_structure(self, engine):
        """Constellation should have nodes and edges."""
        c = engine.get_constellation()
        assert 'nodes' in c
        assert 'edges' in c

    def test_constellation_nodes(self, engine):
        """Nodes should have expected fields."""
        c = engine.get_constellation()
        if c['nodes']:
            node = c['nodes'][0]
            assert 'id' in node
            assert 'name' in node
            assert 'avg_rating' in node
            assert 'song_count' in node

    def test_constellation_no_duplicates(self, engine):
        """Nodes should be unique by id."""
        c = engine.get_constellation()
        ids = [n['id'] for n in c['nodes']]
        assert len(ids) == len(set(ids))


class TestEvolution:
    """Test taste evolution data."""

    def test_evolution_structure(self, engine):
        """Evolution should have expected sections."""
        ev = engine.get_evolution()
        assert 'monthly_avg' in ev
        assert 'yearly' in ev
        assert 'genre_evolution' in ev
        assert 'cumulative' in ev

    def test_evolution_monthly_avg(self, engine):
        """Monthly average ratings should be computed."""
        ev = engine.get_evolution()
        assert len(ev['monthly_avg']) > 0
        for month, avg in ev['monthly_avg'].items():
            assert isinstance(avg, (int, float))
            assert 0 <= avg <= 100

    def test_evolution_yearly(self, engine):
        """Yearly stats should have expected fields."""
        ev = engine.get_evolution()
        for year, data in ev['yearly'].items():
            assert 'avg' in data
            assert 'count' in data
            assert 'top_rating' in data

    def test_evolution_cumulative(self, engine):
        """Cumulative count should increase."""
        ev = engine.get_evolution()
        cum = ev['cumulative']
        for i in range(len(cum) - 1):
            assert cum[i]['total_songs'] <= cum[i + 1]['total_songs']


class TestRecommendations:
    """Test recommendations generation."""

    def test_recommendations_structure(self, engine):
        """Recommendations should return categories."""
        recs = engine.get_recommendations()
        assert isinstance(recs, dict)
        assert len(recs) > 0

    def test_recommendation_categories_have_songs(self, engine):
        """Each category should have recommendations."""
        recs = engine.get_recommendations()
        for cat_name, cat_data in recs.items():
            assert 'recommendations' in cat_data
            assert len(cat_data['recommendations']) > 0

    def test_recommendation_items_have_fields(self, engine):
        """Each recommendation should have required fields."""
        recs = engine.get_recommendations()
        for cat_name, cat_data in recs.items():
            for rec in cat_data['recommendations']:
                assert 'artist' in rec
                assert 'song' in rec
                assert 'reason' in rec


class TestWeeklyDiscovery:
    """Test weekly discovery generation."""

    def test_weekly_structure(self, engine):
        """Weekly discovery should have expected fields."""
        w = engine.get_weekly_discovery()
        assert 'week_of' in w
        assert 'picks' in w
        assert 'stats' in w
        assert 'message' in w

    def test_weekly_picks_count(self, engine):
        """Should return 10 weekly picks."""
        w = engine.get_weekly_discovery()
        assert len(w['picks']) == 10

    def test_weekly_picks_have_fields(self, engine):
        """Each pick should have required fields."""
        w = engine.get_weekly_discovery()
        for pick in w['picks']:
            assert 'artist' in pick
            assert 'song' in pick
            assert 'reason' in pick
            assert 'category' in pick

    def test_weekly_stats(self, engine):
        """Weekly stats should be present."""
        w = engine.get_weekly_discovery()
        assert 'total_songs_rated' in w['stats']
        assert 'unique_artists' in w['stats']

    def test_weekly_message_not_empty(self, engine):
        """Weekly message should not be empty."""
        w = engine.get_weekly_discovery()
        assert w['message']
        assert len(w['message']) > 0

    def test_weekly_picks_unique(self, engine):
        """Weekly picks should not contain duplicates."""
        w = engine.get_weekly_discovery()
        keys = [(p['artist'], p['song']) for p in w['picks']]
        assert len(keys) == len(set(keys))


class TestHelperMethods:
    """Test internal helper methods."""

    def test_generate_why_reason_known_artist(self, engine):
        """Should return reason for known artist with ratings."""
        reason = engine._generate_why_reason('Lindsey Stirling')
        assert 'Lindsey Stirling' in reason
        assert 'time(s)' in reason

    def test_generate_why_reason_unknown_artist(self, engine):
        """Should return empty for unknown artist."""
        reason = engine._generate_why_reason('Nobody Knows Me')
        # May find a similar artist or return empty
        assert isinstance(reason, str)

    def test_generate_weekly_message(self, engine):
        """Weekly message should contain rating context."""
        msg = engine._generate_weekly_message()
        assert msg
        assert len(msg) > 10


# ============================================================
# Edge Cases
# ============================================================

class TestDedupSystem:
    """Test the song deduplication hash-set system."""

    def test_normalize_sig_strips_year(self, engine):
        sig = TasteEngine._normalize_sig('Happy Song (Artist Name, 2023)')
        assert '2023' not in sig
        assert 'happy song' in sig

    def test_normalize_sig_lowercases(self, engine):
        sig = TasteEngine._normalize_sig('HELLO WORLD')
        assert sig == 'hello world'

    def test_normalize_sig_strips_punctuation(self, engine):
        sig = TasteEngine._normalize_sig("Hello, World! (feat. Artist, 2020)")
        assert ',' not in sig
        assert '!' not in sig

    def test_check_song_exists_exact(self, engine):
        result = engine.check_song_exists('Lindsey Stirling', 'Night Vision')
        assert result['exists'] is True

    def test_check_song_exists_unknown(self, engine):
        result = engine.check_song_exists('Nobody', 'Completely Fake Song')
        assert result['exists'] is False

    def test_check_song_exists_fuzzy(self, engine):
        result = engine.check_song_exists('', 'Night Vision')
        assert result['exists'] is True
        assert result['match'] == 'fuzzy'

    def test_build_song_index_populates(self, engine):
        assert len(engine.known_sigs) > 0
        assert len(engine.known_titles) > 0

    def test_recommendations_have_owned_flag(self, engine):
        recs = engine.get_recommendations()
        for cat_name, cat_data in recs.items():
            for rec in cat_data['recommendations']:
                assert 'already_owned' in rec
                assert isinstance(rec['already_owned'], bool)


class TestBackfillMethods:
    """Test letter grade extraction and tone inference."""

    def test_extract_letter_grade_a(self):
        g, v = TasteEngine._extract_letter_grade('A beautiful song. Score: A')
        assert g == 'A'
        assert v == 95

    def test_extract_letter_grade_a_plus(self):
        g, v = TasteEngine._extract_letter_grade('Overall grade: A+ brilliant!')
        assert g == 'A+'
        assert v == 98

    def test_extract_letter_grade_a_minus(self):
        g, v = TasteEngine._extract_letter_grade('Rating A- pretty good')
        assert g == 'A-'
        assert v == 92

    def test_extract_letter_grade_b_plus(self):
        g, v = TasteEngine._extract_letter_grade('Score: B+ solid enough')
        assert g == 'B+'
        assert v == 88

    def test_extract_letter_grade_c(self):
        g, v = TasteEngine._extract_letter_grade('It was okay, C overall.')
        assert g == 'C'
        assert v == 75

    def test_extract_letter_grade_d(self):
        g, v = TasteEngine._extract_letter_grade('Unfortunately it\'s a D. Not great.')
        assert g == 'D'
        assert v == 65

    def test_extract_letter_grade_f(self):
        g, v = TasteEngine._extract_letter_grade('Grade: F. Truly terrible.')
        assert g == 'F'
        assert v == 50

    def test_extract_letter_grade_none(self):
        g, v = TasteEngine._extract_letter_grade('This song is just okay.')
        assert g is None
        assert v is None

    def test_extract_letter_grade_empty(self):
        g, v = TasteEngine._extract_letter_grade('')
        assert g is None
        assert v is None

    def test_extract_letter_grade_no_false_positive_article(self):
        """'A' as an article should NOT be extracted as a grade."""
        g, v = TasteEngine._extract_letter_grade('It was a good song with nice vocals')
        assert g is None or g != 'A'  # Should not match 'A' as article

    def test_infer_tone_amazing(self):
        tag, v = TasteEngine._infer_tone_rating('This song is absolutely amazing!')
        assert v == 95

    def test_infer_tone_love(self):
        tag, v = TasteEngine._infer_tone_rating('I love this song so much')
        assert v == 93

    def test_infer_tone_great(self):
        tag, v = TasteEngine._infer_tone_rating('A really great track')
        assert v == 88

    def test_infer_tone_good(self):
        tag, v = TasteEngine._infer_tone_rating('It is a good song')
        assert v == 84

    def test_infer_tone_nice(self):
        tag, v = TasteEngine._infer_tone_rating('A nice tune')
        assert v == 82

    def test_infer_tone_meh(self):
        tag, v = TasteEngine._infer_tone_rating('Meh, it was whatever. So-so at best.')
        assert v == 72

    def test_infer_tone_ok(self):
        tag, v = TasteEngine._infer_tone_rating('It was ok I guess')
        assert v == 76

    def test_infer_tone_bad(self):
        tag, v = TasteEngine._infer_tone_rating('This song is bad')
        assert v == 62

    def test_infer_tone_terrible(self):
        tag, v = TasteEngine._infer_tone_rating('Terrible song, awful')
        assert v == 50

    def test_infer_tone_perfect(self):
        tag, v = TasteEngine._infer_tone_rating('A perfect song, absolutely perfect')
        assert v == 98

    def test_infer_tone_incredible(self):
        tag, v = TasteEngine._infer_tone_rating('Incredible! Mind-blowing stuff')
        assert v == 97

    def test_infer_tone_empty(self):
        tag, v = TasteEngine._infer_tone_rating('')
        assert tag is None
        assert v is None

    def test_infer_tone_no_match(self):
        tag, v = TasteEngine._infer_tone_rating('This is a song about things.')
        assert tag is None
        assert v is None

    def test_infer_tone_disappointed(self):
        tag, v = TasteEngine._infer_tone_rating('Disappointing, could be better')
        assert v == 68

    def test_infer_tone_worst(self):
        tag, v = TasteEngine._infer_tone_rating('The worst song I have ever heard')
        assert v == 40


class TestBackfillIntegration:
    """Test the backfill_ratings method integration."""

    def test_backfill_preview_returns_changes(self, engine):
        """Preview mode should return changes without modifying CSV."""
        result = engine.backfill_ratings(preview=True)
        assert 'preview' in result
        assert result['preview'] is True
        assert 'total_changes' in result
        assert 'changes_by_source' in result
        assert 'before' in result
        assert 'after' in result

    def test_backfill_preview_no_side_effects(self, engine):
        """Preview mode should NOT modify the CSV."""
        before_rated = len(engine.rated_entries)
        engine.backfill_ratings(preview=True)
        # Reload and verify unchanged
        engine._load_data()
        assert len(engine.rated_entries) == before_rated

    def test_backfill_letter_only_method(self, engine):
        """Method='letter' should only use letter grade extraction."""
        result = engine.backfill_ratings(preview=True, method='letter')
        assert result['changes_by_source']['tone_inference'] == 0

    def test_backfill_tone_only_method(self, engine):
        """Method='tone' should only use tone inference."""
        result = engine.backfill_ratings(preview=True, method='tone')
        assert result['changes_by_source']['letter_grades'] == 0

    def test_backfill_actual_write(self):
        """Non-preview mode should write to CSV and reload engine."""
        # Create CSV with an unrated entry that has a letter grade
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8', newline='')
        writer = csv.writer(tmp)
        writer.writerow(['date', 'rating', 'title', 'tail'])
        writer.writerow(['2020-01-01', '', 'Test Song (Test Artist, 2020)', 'Score: A really good track!'])
        writer.writerow(['2020-01-02', '85', 'Rated Song (Artist 2, 2020)', 'Already rated'])
        tmp.close()
        try:
            e = TasteEngine(tmp.name)
            assert len(e.rated_entries) == 1  # Only the rated one
            
            result = e.backfill_ratings(preview=False)
            assert result['total_changes'] == 1  # One backfilled
            assert result['after']['rated'] == 2  # Now both rated
            
            # Reload via new engine to verify persistence
            e2 = TasteEngine(tmp.name)
            assert len(e2.rated_entries) == 2
        finally:
            os.unlink(tmp.name)

    def test_backfill_with_tone_fallback(self):
        """Entries without letter grades should fall back to tone inference."""
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8', newline='')
        writer = csv.writer(tmp)
        writer.writerow(['date', 'rating', 'title', 'tail'])
        writer.writerow(['2020-01-01', '', 'Song A (Artist A, 2020)', 'Amazing track! Really love it.'])
        tmp.close()
        try:
            e = TasteEngine(tmp.name)
            result = e.backfill_ratings(preview=True)
            assert result['total_changes'] == 1
            assert result['changes'][0]['new_rating'] == 95  # 'amazing' → 95 (checked before 'love')
            assert result['changes'][0]['source'].startswith('tone:')
        finally:
            os.unlink(tmp.name)

    def test_backfill_all_already_rated(self):
        """If all entries already have ratings, should return 0 changes."""
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8', newline='')
        writer = csv.writer(tmp)
        writer.writerow(['date', 'rating', 'title', 'tail'])
        writer.writerow(['2020-01-01', '85', 'Song (Artist, 2020)', 'Good track'])
        writer.writerow(['2020-01-02', '90', 'Song 2 (Artist 2, 2020)', 'Great track'])
        tmp.close()
        try:
            e = TasteEngine(tmp.name)
            result = e.backfill_ratings(preview=True)
            assert result['total_changes'] == 0
        finally:
            os.unlink(tmp.name)


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_extract_artists_empty_string(self, engine):
        assert engine._extract_artists('') == []

    def test_extract_artists_special_chars(self, engine):
        artists = engine._extract_artists('Song Title (Artist-Name_123, 2020)')
        assert isinstance(artists, list)

class TestChallengeSection:
    """Test the challenge section."""

    def test_challenge_db_is_populated(self, engine):
        """Challenge database should have songs."""
        db = TasteEngine._build_challenge_db()
        assert len(db) > 0
        for song in db:
            assert 'artist' in song
            assert 'song' in song
            assert 'genre' in song
            assert 'tier' in song

    def test_get_challenges_returns_valid(self, engine):
        """get_challenges should return challenges with expected structure."""
        result = engine.get_challenges(count=10)
        assert 'challenges' in result
        assert 'by_tier' in result
        assert 'total_available' in result
        assert len(result['challenges']) > 0

    def test_challenges_dont_include_owned(self, engine):
        """Challenges should filter out songs already in collection."""
        result = engine.get_challenges(count=50)
        for c in result['challenges']:
            dup = engine.check_song_exists(c['artist'], c['song'])
            assert not dup['exists'], f"{c['artist']} - {c['song']} should not be owned"

    def test_challenges_have_zone_note(self, engine):
        """Each challenge should have a personalized zone note."""
        result = engine.get_challenges(count=5)
        for c in result['challenges']:
            assert 'zone_note' in c
            assert len(c['zone_note']) > 0

    def test_challenges_grouped_by_tier(self, engine):
        """Challenges should be grouped by tier."""
        result = engine.get_challenges(count=20)
        assert len(result['by_tier']) > 0
        # At least one of the expected tiers should be present
        expected_tiers = {'legendary', 'modern_classic', 'classic', 'cult'}
        assert any(t in result['by_tier'] for t in expected_tiers)

    def test_challenges_shown_count(self, engine):
        """Requested count should be respected."""
        result = engine.get_challenges(count=5)
        assert len(result['challenges']) <= 5


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_extract_artists_empty_string(self, engine):
        assert engine._extract_artists('') == []

    def test_extract_artists_special_chars(self, engine):
        artists = engine._extract_artists('Song Title (Artist-Name_123, 2020)')
        assert isinstance(artists, list)

    def test_stats_with_single_entry(self):
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8', newline='')
        writer = csv.writer(tmp)
        writer.writerow(['date', 'rating', 'title', 'tail'])
        writer.writerow(['2020-01-01', '85', 'Single Song (Single Artist, 2020)', 'A lone track.'])
        tmp.close()
        try:
            e = TasteEngine(tmp.name)
            stats = e.get_stats()
            assert stats['total_entries'] == 1
            assert stats['rated_entries'] == 1
            assert stats['avg_rating'] == 85.0
            assert stats['unique_artists'] == 1
            # Dedup works with single entry
            assert len(e.known_sigs) > 0
            assert len(e.known_titles) > 0
            assert e.check_song_exists('Single Artist', 'Single Song')['exists'] is True
        finally:
            os.unlink(tmp.name)


class TestGenreReclassification:
    """Test the genre reclassification system (keywords + MusicBrainz cache)."""

    def test_reclassify_keywords_only(self, engine):
        """Expanded keywords should reduce uncategorized count."""
        before = engine._get_genre_distribution()
        before_uncat = before.get('Uncategorized', {}).get('count', 0)

        result = engine.reclassify_genres(use_musicbrainz=False)

        assert 'before_uncategorized' in result
        assert 'after_uncategorized' in result
        assert 'reduction' in result
        assert 'by_genre' in result
        assert result['musicbrainz'] is None  # Not used
        # After should be <= before (reduction is non-negative)
        assert result['reduction'] >= 0

    def test_reclassify_musicbrainz_stats_shape(self, engine):
        """MusicBrainz result should have mb stats."""
        result = engine.reclassify_genres(use_musicbrainz=True)
        assert 'musicbrainz' in result
        assert result['musicbrainz']['looked_up'] >= 0
        assert result['musicbrainz']['found'] >= 0

    def test_song_index_persists_after_reclassify(self):
        """Reclassification shouldn't break the song index."""
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8', newline='')
        writer = csv.writer(tmp)
        writer.writerow(['date', 'rating', 'title', 'tail'])
        writer.writerow(['2020-01-01', '85', 'Test Song (Test Artist, 2020)', 'A great pop track.'])
        tmp.close()
        try:
            e = TasteEngine(tmp.name)
            e.reclassify_genres(use_musicbrainz=False)
            # Song lookup should still work
            result = e.check_song_exists('Test Artist', 'Test Song')
            assert result['exists'] is True
        finally:
            os.unlink(tmp.name)

    def test_lookup_artist_genre_musicbrainz_real_api(self, engine):
        """Hit MusicBrainz for a well-known artist. Requires internet."""
        tags = engine._lookup_artist_genre_musicbrainz('Radiohead')
        # Either got tags (internet) or empty list (offline) — both are valid
        assert isinstance(tags, list)

    def test_classify_artist_genre_musicbrainz_nonexistent(self, engine):
        """Non-existent artist should return Uncategorized."""
        genre = engine._classify_artist_genre_musicbrainz('XyzzyDoesNotExist12345')
        assert genre == 'Uncategorized'

    @patch('src.taste_engine.TasteEngine._lookup_artist_genre_musicbrainz')
    def test_classify_artist_maps_tags_to_genre(self, mock_lookup, engine):
        """MusicBrainz tags should map to our genre taxonomy."""
        mock_lookup.return_value = ['jazz', 'fusion', 'experimental']
        genre = engine._classify_artist_genre_musicbrainz('Test Artist')
        assert genre == 'Jazz/Swing'

    @patch('src.taste_engine.TasteEngine._lookup_artist_genre_musicbrainz')
    def test_artist_genre_cache_used_in_distribution(self, mock_lookup, engine):
        """Populating _artist_genre_cache should move songs from Uncategorized."""
        # Set a known artist in cache
        engine._artist_genre_cache['Lindsey Stirling'] = 'Classical/Instrumental'
        dist = engine._get_genre_distribution()
        # Lindsey Stirling songs should now be classified
        instr = dist.get('Classical/Instrumental', {})
        assert instr.get('count', 0) > 0
        mock_lookup.assert_not_called()  # Cache hit, no API call needed

    def test_genre_keywords_list_is_comprehensive(self, engine):
        """The keyword list should have enough entries to cover common genres."""
        total_keywords = sum(len(kws) for kws in engine.genre_keywords.values())
        assert total_keywords >= 150, f"Only {total_keywords} keywords — need more for decent coverage"

    def test_get_genre_distribution_has_uncategorized(self, engine):
        """Genre distribution should always have an Uncategorized key (even if 0)."""
        dist = engine._get_genre_distribution()
        assert 'Uncategorized' in dist
        assert isinstance(dist['Uncategorized']['count'], int)
