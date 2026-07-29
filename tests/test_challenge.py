"""Tests for the Challenge recommendation system."""
import pytest
from src.taste_engine import TasteEngine


@pytest.fixture
def engine():
    return TasteEngine('data/posts_tails.csv')


class TestChallengeDB:
    """Test the challenge database integrity."""

    def test_challenge_db_has_entries(self, engine):
        db = engine._build_challenge_db()
        assert len(db) > 100, f"Challenge DB should have 100+ entries, got {len(db)}"
        assert len(db) >= 180, f"Challenge DB should have 180+ entries, got {len(db)}"

    def test_challenge_db_all_have_required_fields(self, engine):
        db = engine._build_challenge_db()
        required = {'artist', 'song', 'genre', 'year', 'acclaim', 'tier', 'listen_score'}
        for entry in db:
            missing = required - set(entry.keys())
            assert not missing, f"Entry {entry.get('artist')} - {entry.get('song')} missing: {missing}"

    def test_challenge_db_valid_tiers(self, engine):
        db = engine._build_challenge_db()
        valid_tiers = {'legendary', 'modern_classic', 'classic', 'cult'}
        for entry in db:
            assert entry['tier'] in valid_tiers, \
                f"Invalid tier '{entry['tier']}' for {entry['artist']} - {entry['song']}"

    def test_challenge_db_valid_listen_scores(self, engine):
        db = engine._build_challenge_db()
        for entry in db:
            assert 1 <= entry['listen_score'] <= 100, \
                f"Invalid listen_score {entry['listen_score']} for {entry['artist']} - {entry['song']}"

    def test_challenge_db_valid_years(self, engine):
        db = engine._build_challenge_db()
        for entry in db:
            assert 1900 <= entry['year'] <= 2030, \
                f"Invalid year {entry['year']} for {entry['artist']} - {entry['song']}"

    def test_challenge_db_all_tiers_represented(self, engine):
        db = engine._build_challenge_db()
        tiers = set(e['tier'] for e in db)
        assert 'legendary' in tiers
        assert 'modern_classic' in tiers
        assert 'classic' in tiers
        assert 'cult' in tiers

    def test_challenge_db_minimum_per_tier(self, engine):
        db = engine._build_challenge_db()
        from collections import Counter
        counts = Counter(e['tier'] for e in db)
        for tier in ['legendary', 'modern_classic', 'classic', 'cult']:
            assert counts[tier] >= 5, f"Tier '{tier}' only has {counts[tier]} entries (min 5)"


class TestGetChallenges:
    """Test the challenge recommendation algorithm."""

    def test_default_mode_returns_24(self, engine):
        result = engine.get_challenges(count=24, mode='outside_zone')
        assert len(result['challenges']) == 24

    def test_opposite_taste_mode_returns_24(self, engine):
        result = engine.get_challenges(count=24, mode='opposite_taste')
        assert len(result['challenges']) == 24

    def test_both_modes_have_all_tiers(self, engine):
        for mode in ['outside_zone', 'opposite_taste']:
            result = engine.get_challenges(count=24, mode=mode)
            tiers = set(result['by_tier'].keys())
            assert 'legendary' in tiers, f"Mode '{mode}' missing legendary"
            assert 'modern_classic' in tiers, f"Mode '{mode}' missing modern_classic"
            assert 'classic' in tiers, f"Mode '{mode}' missing classic"
            assert 'cult' in tiers, f"Mode '{mode}' missing cult"

    def test_no_owned_songs_in_results(self, engine):
        result = engine.get_challenges(count=50, mode='outside_zone')
        for c in result['challenges']:
            dup = engine.check_song_exists(c['artist'], c['song'])
            assert not dup['exists'], \
                f"Challenge includes owned song: {c['artist']} - {c['song']}"

    def test_class_genre_on_all_entries(self, engine):
        result = engine.get_challenges(count=24, mode='outside_zone')
        for c in result['challenges']:
            assert 'class_genre' in c, f"Missing class_genre for {c['artist']} - {c['song']}"

    def test_opposite_taste_targets_lowest_genres(self, engine):
        result = engine.get_challenges(count=24, mode='opposite_taste')
        lowest = result['your_zones']['lowest_rated_genres']
        assert len(lowest) >= 3, f"Expected 3+ lowest genres, got {lowest}"
        # At least some results should have outside_score >= 5 (opposite-taste boost)
        boosted = [c for c in result['challenges'] if c.get('outside_score', 0) >= 5]
        assert len(boosted) >= 2, f"Expected 2+ opposite-taste boosted, got {len(boosted)}"

    def test_lower_count_returns_fewer(self, engine):
        result = engine.get_challenges(count=5, mode='outside_zone')
        assert len(result['challenges']) == 5

    def test_total_available_reported(self, engine):
        result = engine.get_challenges(count=24, mode='outside_zone')
        assert result['total_available'] > 0
        assert result['total_db_size'] > 100

    def test_your_zones_present(self, engine):
        result = engine.get_challenges(count=24, mode='outside_zone')
        zones = result['your_zones']
        assert 'loved_genres' in zones
        assert 'known_artists_count' in zones
        assert 'lowest_rated_genres' in zones

    def test_mode_reflected_in_response(self, engine):
        r1 = engine.get_challenges(count=24, mode='outside_zone')
        r2 = engine.get_challenges(count=24, mode='opposite_taste')
        assert r1['mode'] == 'outside_zone'
        assert r2['mode'] == 'opposite_taste'

    def test_different_modes_different_results(self, engine):
        r1 = engine.get_challenges(count=10, mode='outside_zone')
        r2 = engine.get_challenges(count=10, mode='opposite_taste')
        ids1 = [(c['artist'], c['song']) for c in r1['challenges']]
        ids2 = [(c['artist'], c['song']) for c in r2['challenges']]
        # At least some should differ
        same = set(ids1) & set(ids2)
        assert len(same) < len(ids1), "Modes should return different results"

    def test_eurovision_genre_present(self, engine):
        db = engine._build_challenge_db()
        euro_entries = [e for e in db if e['genre'] == 'Eurovision']
        assert len(euro_entries) >= 3, f"Expected 3+ Eurovision entries, got {len(euro_entries)}"

    def test_challenges_exclude_newly_added_song(self, engine):
        """After adding a challenge-DB song to known_sigs, get_challenges
        should not return it."""
        db = engine._build_challenge_db()
        # Pull the current challenge set and find a song we can add
        before = engine.get_challenges(count=50)
        before_ids = {(c['artist'], c['song']) for c in before['challenges']}

        # Pick any challenge song that is currently shown
        assert len(before['challenges']) > 0, "Need at least one challenge"
        song_to_add = before['challenges'][0]
        artist, song = song_to_add['artist'], song_to_add['song']

        # Sanity check: it should NOT be owned yet
        dup = engine.check_song_exists(artist, song)
        assert not dup['exists'], f"Challenge song should not be owned: {artist} - {song}"

        # Simulate adding the song to the collection
        sig = engine._normalize_sig(f"{artist} {song}")
        engine.known_sigs.add(sig)
        engine.known_titles.add(engine._normalize_sig(f"{song} ({artist})"))

        # Verify check_song_exists now finds it
        after_dup = engine.check_song_exists(artist, song)
        assert after_dup['exists'] is True, \
            f"check_song_exists should find it after adding: {after_dup}"

        # After — song should be excluded from challenges
        after = engine.get_challenges(count=50)
        after_ids = {(c['artist'], c['song']) for c in after['challenges']}
        assert (artist, song) not in after_ids, \
            f"Challenge should exclude newly added song: {artist} - {song}"


class TestChallengeAliases:
    """Test the genre alias mapping."""

    def test_genre_alias_maps_hiphop(self, engine):
        assert engine._genre_alias_to_class.get('Hip-Hop') == 'Rap/Hip-Hop'

    def test_genre_alias_maps_jpop(self, engine):
        assert engine._genre_alias_to_class.get('J-Pop') == 'J-Pop/Anime'

    def test_genre_alias_maps_reggae(self, engine):
        assert engine._genre_alias_to_class.get('Reggae') == 'Reggae/Dub'

    def test_genre_alias_maps_eurovision(self, engine):
        assert engine._genre_alias_to_class.get('Eurovision') == 'Eurovision'

    def test_genre_alias_maps_soul(self, engine):
        assert engine._genre_alias_to_class.get('Soul') == 'R&B/Soul'

    def test_genre_alias_maps_country(self, engine):
        assert engine._genre_alias_to_class.get('Country') == 'Country'

    def test_genre_alias_maps_funk(self, engine):
        assert engine._genre_alias_to_class.get('Funk') == 'Disco/Funk'

    def test_genre_alias_maps_electronic(self, engine):
        assert engine._genre_alias_to_class.get('Electronic') == 'Electronic/Dance'

    def test_genre_alias_maps_anime_rock(self, engine):
        assert engine._genre_alias_to_class.get('Anime Rock') == 'J-Pop/Anime'
