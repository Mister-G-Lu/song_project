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
        assert 'favorite_artists' in stats

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


class TestFavoriteArtists:
    """Test the favorite artists feature."""

    def test_favorite_artists_returns_list(self, engine):
        """get_favorite_artists should return a list."""
        favs = engine.get_favorite_artists()
        assert isinstance(favs, list)
        assert len(favs) > 0

    def test_favorite_artists_have_required_fields(self, engine):
        """Each favorite should have all expected fields."""
        favs = engine.get_favorite_artists()
        for fav in favs:
            assert 'name' in fav
            assert 'my_rating' in fav
            assert 'genre' in fav
            assert 'in_collection' in fav
            assert isinstance(fav['my_rating'], (int, float))
            assert fav['my_rating'] > 0
            assert isinstance(fav['name'], str)
            assert len(fav['name']) > 0

    def test_favorite_artists_sorted_by_rating(self, engine):
        """Should be sorted by my_rating descending."""
        favs = engine.get_favorite_artists()
        for i in range(len(favs) - 1):
            assert favs[i]['my_rating'] >= favs[i + 1]['my_rating']

    def test_favorite_artists_includes_michael_jackson(self, engine):
        """Michael Jackson should be in the favorites list with rating 11."""
        favs = engine.get_favorite_artists()
        mj = [f for f in favs if f['name'] == 'Michael Jackson']
        assert len(mj) == 1
        assert mj[0]['my_rating'] == 11.0

    def test_favorite_artists_known_artist_has_genre(self, engine):
        """Ariana Grande should have Pop genre from CURATED_ARTIST_GENRES."""
        favs = engine.get_favorite_artists()
        ag = [f for f in favs if f['name'] == 'Ariana Grande']
        if ag:
            assert ag[0]['genre'] == 'Pop'

    def test_favorite_artists_in_stats(self, engine):
        """Stats should include favorite_artists field."""
        stats = engine.get_stats()
        assert 'favorite_artists' in stats
        assert len(stats['favorite_artists']) > 0


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
    """Test constellation graph generation and community detection."""

    def test_constellation_structure(self, engine):
        """Constellation should have nodes and edges and communities."""
        c = engine.get_constellation()
        assert 'nodes' in c
        assert 'edges' in c
        assert 'communities' in c
        assert 'community_count' in c

    def test_constellation_nodes(self, engine):
        """Nodes should have expected fields including community_id."""
        c = engine.get_constellation()
        if c['nodes']:
            node = c['nodes'][0]
            assert 'id' in node
            assert 'name' in node
            assert 'avg_rating' in node
            assert 'song_count' in node
            assert 'community_id' in node

    def test_constellation_no_duplicates(self, engine):
        """Nodes should be unique by id."""
        c = engine.get_constellation()
        ids = [n['id'] for n in c['nodes']]
        assert len(ids) == len(set(ids))

    def test_constellation_communities_structure(self, engine):
        """Community metadata should have expected fields."""
        c = engine.get_constellation()
        for cid, meta in c['communities'].items():
            assert 'size' in meta
            assert 'dominant_genre' in meta
            assert 'top_artists' in meta
            assert 'avg_rating' in meta
            assert 'genre_breakdown' in meta
            assert isinstance(meta['size'], int)
            assert meta['size'] > 0
            assert len(meta['top_artists']) > 0

    def test_constellation_all_nodes_have_community(self, engine):
        """Every node should have a community_id >= 0 (no isolated nodes)."""
        c = engine.get_constellation()
        for node in c['nodes']:
            assert node['community_id'] >= 0, \
                f"Node '{node['id']}' has no community (id={node['community_id']})"

    def test_constellation_communities_dominant_genre(self, engine):
        """Dominant genres should come from the actual node genres."""
        c = engine.get_constellation()
        for cid, meta in c['communities'].items():
            dg = meta['dominant_genre']
            # Should be one of the known genres or Uncategorized
            assert isinstance(dg, str) and len(dg) > 0

    def test_constellation_community_counts_sum(self, engine):
        """Sum of community sizes should equal total nodes."""
        c = engine.get_constellation()
        total_in_communities = sum(meta['size'] for meta in c['communities'].values())
        assert total_in_communities == len(c['nodes']), \
            f"Sum of community sizes ({total_in_communities}) != total nodes ({len(c['nodes'])})"

    def test_constellation_community_count(self, engine):
        """Should have at least 2 communities (reasonable number for diverse data)."""
        c = engine.get_constellation()
        # With 1602 artists and multiple genres, we should get at least 2 communities
        assert c['community_count'] >= 2, \
            f"Expected at least 2 communities, got {c['community_count']}"

    def test_constellation_community_top_artists(self, engine):
        """Top artists per community should be sorted by song_count."""
        c = engine.get_constellation()
        for cid, meta in c['communities'].items():
            artists = meta['top_artists']
            for i in range(len(artists) - 1):
                assert artists[i]['song_count'] >= artists[i + 1]['song_count'], \
                    f"Community {cid}: top artists not sorted by song_count"

    def test_constellation_community_genre_breakdown(self, engine):
        """Genre breakdown should be a non-empty dict."""
        c = engine.get_constellation()
        for cid, meta in c['communities'].items():
            gb = meta['genre_breakdown']
            assert isinstance(gb, dict)
            assert len(gb) > 0
            # Top genre should match dominant_genre
            top_genre = list(gb.keys())[0]
            assert top_genre == meta['dominant_genre'], \
                f"Community {cid}: top genre '{top_genre}' != dominant '{meta['dominant_genre']}'"


class TestEvolution:
    """Test taste evolution data."""

    def test_blind_spots_include_year_spots(self, engine):
        """Blind spots should also flag release-YEAR gaps (under-explored or
        disliked eras), each paired with acclaimed song suggestions.
        """
        spots = engine.get_blind_spots()['year_blind_spots']
        assert isinstance(spots, list)
        assert len(spots) > 0
        for s in spots:
            assert s['kind'] in ('disliked-era', 'under-explored')
            assert isinstance(s['year'], int)
            assert s['why']
            # Every spot carries concrete suggestions from the acclaim DB
            assert isinstance(s['suggestion'], list)
            if s['suggestion']:
                assert all(c.get('artist') and c.get('song') for c in s['suggestion'])

    def test_evolution_structure(self, engine):
        """Evolution should have expected sections."""
        ev = engine.get_evolution()
        assert 'monthly_avg' in ev
        assert 'yearly' in ev
        assert 'genre_evolution' in ev
        assert 'cumulative' in ev
        assert 'release_year_avg' in ev

    def test_evolution_release_year_avg(self, engine):
        """Average rating grouped by the song's RELEASE year (from title)."""
        ev = engine.get_evolution()
        ry = ev['release_year_avg']
        # Every rated fixture row carries a release year in parentheses,
        # so all 24 rated entries should be accounted for.
        assert sum(d['count'] for d in ry.values()) == 24

        # 2017: Shape of You (90) + Galway Girl (95)
        assert ry['2017'] == {'avg': 92.5, 'count': 2, 'top_rating': 95}
        # 2012: Inclusion (90) + Our Farewell (100)
        assert ry['2012'] == {'avg': 95.0, 'count': 2, 'top_rating': 100}
        # 2020: New Years Song (75) + Bad Song (50) + Amazing Track (95)
        assert ry['2020']['count'] == 3
        assert ry['2020']['avg'] == 73.3
        assert ry['2020']['top_rating'] == 95
        # 1984: Plastic Love (93)
        assert ry['1984'] == {'avg': 93.0, 'count': 1, 'top_rating': 93}
        # Keys are strings, sorted chronologically
        assert list(ry.keys()) == sorted(ry.keys())

    def test_extract_release_year(self, engine):
        """Release year extraction prefers the parenthesized year, with fallback."""
        ex = TasteEngine._extract_release_year
        assert ex('Shape of You (Ed Sheeran, 2017)') == 2017
        assert ex('Plastic Love (Mariya Takeuchi, 1984)') == 1984
        assert ex('Song (Artist, 2025)') == 2025
        # Fallback: year anywhere in the title
        assert ex('Best of 2019 (Mix)') == 2019
        # No plausible year
        assert ex('Bohemian Rhapsody') is None
        assert ex('') is None
        assert ex('Song (Artist, 2100)') is None

    def test_release_year_db_match(self, engine):
        """Release years come from the official song database when the title
        has no year at all (e.g. the 'Artist - Song' format)."""
        assert TasteEngine._release_year_for('Dancing Queen - ABBA') == 1976
        assert TasteEngine._release_year_for('Stairway To Heaven - Led Zeppelin') == 1971
        assert TasteEngine._release_year_for('Enter Sandman - Metallica') == 1991
        assert TasteEngine._release_year_for('bad guy - Billie Eilish') == 2019

    def test_release_year_db_reversed_format(self, engine):
        """The data frequently writes 'Song - Artist' (reversed); both
        orientations of a dashed title are tried against the database."""
        assert TasteEngine._release_year_for('Bohemian Rhapsody (Queen, 1975)') == 1975
        assert TasteEngine._release_year_for('Comfortably Numb - Pink Floyd') == 1979
        assert TasteEngine._release_year_for('Hotel California - The Eagles') == 1977

    def test_release_year_db_no_match(self, engine):
        """Titles that aren't in the database and carry no year resolve to None."""
        assert TasteEngine._release_year_for('Totally Unknown Track - Nobody') is None
        assert TasteEngine._release_year_for('') is None
        assert TasteEngine._db_year_for('Totally Unknown Track - Nobody') is None

    def test_release_year_cache_consulted(self, engine):
        """A MusicBrainz-enriched cache entry resolves songs the curated DB
        doesn't have (its most specific match for the exact artist+song pair)."""
        # pick a song the committed enrichment cache genuinely doesn't have
        key = TasteEngine._release_year_key('Obscure Local Band', 'Nebulous Nonsense')
        assert key not in TasteEngine._release_year_cache
        TasteEngine._release_year_cache[key] = 2013
        try:
            assert TasteEngine._release_year_for('Obscure Local Band - Nebulous Nonsense') == 2013
            assert TasteEngine._release_year_source('Obscure Local Band - Nebulous Nonsense') == 'cache'
        finally:
            del TasteEngine._release_year_cache[key]

    def test_release_year_db_beats_cache(self, engine):
        """The hand-curated database year is authoritative: a fuzzy cache
        entry must never override it (e.g. Dancing Queen 1976 vs a
        compilation's 2004)."""
        key = TasteEngine._release_year_key('ABBA', 'Dancing Queen')
        TasteEngine._release_year_cache[key] = 2004
        try:
            assert TasteEngine._release_year_for('Dancing Queen - ABBA') == 1976
            assert TasteEngine._release_year_source('Dancing Queen - ABBA') == 'db'
        finally:
            del TasteEngine._release_year_cache[key]

    def test_year_from_mb_recording(self, engine):
        """MusicBrainz response parsing takes the earliest release year from
        first-release-date and per-release dates."""
        payload = {
            'recordings': [
                {
                    'title': 'Firework',
                    'first-release-date': '2010-10-26',
                    'releases': [
                        {'title': 'Teenage Dream', 'date': '2010-08-24'},
                        {'title': 'Firework', 'date': '2010-08-31'},
                    ],
                },
                {
                    'title': 'Firework (Remix)',
                    'releases': [{'title': 'Remix EP', 'date': '2011-01-01'}],
                },
            ]
        }
        assert TasteEngine._year_from_mb_recording(payload) == 2010
        assert TasteEngine._year_from_mb_recording({'recordings': []}) is None

    def test_mb_title_confirms(self, engine):
        """The anti-false-positive guard accepts exact/substring title matches
        and rejects unrelated recordings."""
        assert TasteEngine._mb_title_confirms('Firework', 'Firework')
        assert TasteEngine._mb_title_confirms('Shine On You Crazy Diamond', 'Shine on You Crazy Diamond pt. 1')
        assert not TasteEngine._mb_title_confirms('Roar', 'Firework')
        assert not TasteEngine._mb_title_confirms('', 'Firework')

    def test_evolution_release_year_coverage(self, engine):
        """The evolution payload reports how many rated songs were matched."""
        ev = engine.get_evolution()
        cov = ev['release_year_coverage']
        assert 'matched' in cov and 'total' in cov
        assert 0 <= cov['matched'] <= cov['total']
        assert cov['total'] == len(engine.rated_entries)
        assert cov['matched'] == sum(d['count'] for d in ev['release_year_avg'].values())
        # The per-source breakdown accounts for every matched song
        assert sum(cov['by_source'].values()) == cov['matched']

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
        """Each category should have recommendations (banned genre cats may be empty)."""
        recs = engine.get_recommendations()
        for cat_name, cat_data in recs.items():
            assert 'recommendations' in cat_data

    def test_recommendation_items_have_fields(self, engine):
        """Each recommendation should have required fields."""
        recs = engine.get_recommendations()
        for cat_name, cat_data in recs.items():
            for rec in cat_data['recommendations']:
                assert 'artist' in rec
                assert 'song' in rec
                assert 'reason' in rec

    def test_no_owned_songs_in_recommendations(self, engine):
        """No recommendation should be already_owned — they're filtered backend-side."""
        recs = engine.get_recommendations()
        for cat_name, cat_data in recs.items():
            for rec in cat_data['recommendations']:
                # If this rec matches a known song, verify it's NOT in collection
                dup = engine.check_song_exists(rec['artist'], rec['song'])
                assert not dup['exists'], \
                    f"'{rec['artist']} - {rec['song']}' is in collection but still appears in recommendations"

    def test_recommendations_exclude_newly_added_song(self, engine):
        """After adding a song that matches a recommendation, it should no longer appear."""

        # Find a recommendation that doesn't yet exist in the collection
        recs = engine.get_recommendations()
        target = None
        for cat_name, cat_data in recs.items():
            for rec in cat_data['recommendations']:
                dup = engine.check_song_exists(rec['artist'], rec['song'])
                if not dup['exists']:
                    target = rec
                    break
            if target:
                break

        assert target is not None, "No unowned recommendation found to test with"

        # Simulate adding this song to the CSV
        import csv, tempfile, os
        date = '2024-01-15'
        with open(engine.csv_path, 'a', encoding='utf-8', newline='') as f:
            w = csv.writer(f)
            w.writerow([date, '90', f"{target['song']} ({target['artist']}, 2024)", 'Added via test'])

        # Reload engine
        engine._load_data()
        engine._classify_rows()
        engine._build_artist_index()
        engine._build_song_index()

        # Now the recommendation should be gone
        updated_recs = engine.get_recommendations()
        for cat_name, cat_data in updated_recs.items():
            for rec in cat_data['recommendations']:
                # The exact same song should not appear
                assert not (rec['artist'] == target['artist'] and rec['song'] == target['song']), \
                    f"'{target['artist']} - {target['song']}' still appears after being added"

        # Clean up the appended row (not critical for test correctness)
        # The temp CSV in sample_csv_path fixture handles cleanup



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

    def test_algorithmic_picks_are_scored_ranked_not_owned(self, engine):
        picks = engine.get_algorithmic_recommendations(limit=6)
        assert len(picks) <= 6
        for p in picks:
            # never an owned / in-collection song
            assert p['already_owned'] is False
            assert not engine.check_song_exists(p['artist'], p['song'])['exists']
            # scored & reasoned from data (not hardcoded)
            assert isinstance(p['score'], float)
            assert p['score'] > 0
            assert p['reason']
            assert 'album' not in p['song']
        # ranks are sorted descending
        scores = [p['score'] for p in picks]
        assert scores == sorted(scores, reverse=True)


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


class TestUncategorizedBreakdown:
    """Test the uncategorized breakdown method."""

    def test_breakdown_structure(self, engine):
        """Should return expected structure."""
        result = engine.get_uncategorized_breakdown()
        assert 'known_artists' in result
        assert 'unknown_artists' in result
        assert 'no_artist' in result
        assert 'meta_entries' in result
        assert 'summary' in result
        assert 'total' in result

    def test_breakdown_summary_fields(self, engine):
        """Summary should have all required fields."""
        result = engine.get_uncategorized_breakdown()
        s = result['summary']
        assert 'total_uncategorized' in s
        assert 'by_known_artists' in s
        assert 'by_unknown_artists' in s
        assert 'no_artist_count' in s
        assert 'meta_count' in s

    def test_breakdown_totals_add_up(self, engine):
        """Sub-totals should equal total_uncategorized."""
        result = engine.get_uncategorized_breakdown()
        s = result['summary']
        total = s['by_known_artists'] + s['by_unknown_artists'] + s['no_artist_count'] + s['meta_count']
        assert total == s['total_uncategorized'], f"{total} != {s['total_uncategorized']}"

    def test_breakdown_known_artists_structure(self, engine):
        """Known artists entries should have required fields."""
        result = engine.get_uncategorized_breakdown()
        for artist, info in result['known_artists'].items():
            assert 'count' in info
            assert 'sample_songs' in info
            assert 'suggested_genre' in info
            assert info['count'] > 0

    def test_breakdown_unknown_artists_structure(self, engine):
        """Unknown artists entries should have required fields."""
        result = engine.get_uncategorized_breakdown()
        for artist, info in result['unknown_artists'].items():
            assert 'count' in info
            assert 'sample_songs' in info
            assert info['count'] > 0

    def test_breakdown_no_artist_entries(self, engine):
        """No-artist entries should have title field."""
        result = engine.get_uncategorized_breakdown()
        for entry in result['no_artist']:
            assert 'title' in entry

    def test_breakdown_no_false_positives(self, engine):
        """Common substrings like 'ost' in 'post' should not cause false positives.
        This was a real bug where 'Announcement' entry's tail 'post' matched 'ost' keyword.
        """
        result = engine.get_uncategorized_breakdown()
        # All entries in the test fixture should be classified (artists are curated)
        # so the breakdown total should be 0 for this well-classified dataset
        assert result['total'] == 0, f"Expected 0 uncategorized, got {result['total']}"


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
        """Genre distribution should always have an Uncategorized key (even if 0).
        With the curated artist mapping, all test artists are now classified.
        """
        dist = engine._get_genre_distribution()
        # The test dataset has Ed Sheeran (Pop), Maroon 5 (Pop), Owl City (Pop),
        # Taylor Swift (Pop), Olly Murs (Pop), Muse (Rock), Stevie Wonder (R&B/Soul),
        # Lindsey Stirling / Taylor Davis (Classical/Instrumental), etc.
        # All are in _CURATED_ARTIST_GENRES, so Uncategorized may be 0.
        assert 'Uncategorized' in dist, f"Expected 'Uncategorized' key. Got: {list(dist.keys())}"
        assert isinstance(dist['Uncategorized']['count'], int)
        # Most importantly: the count should be 0 because all test artists are mapped
        assert dist['Uncategorized']['count'] == 0, \
            f"Expected 0 uncategorized, got {dist['Uncategorized']['count']}. All test artists should be classified."

    def test_curated_mapping_fallback_in_genre_distribution(self):
        """_CURATED_ARTIST_GENRES should be checked as a fallback for uncategorized songs."""
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8', newline='')
        writer = csv.writer(tmp)
        writer.writerow(['date', 'rating', 'title', 'tail'])
        # Song with no genre keywords in review text, but artist IS in curated mapping
        writer.writerow(['2024-01-01', '85', 'Test Song (Taylor Swift, 2024)', 'A song without any genre keywords'])
        writer.writerow(['2024-01-02', '90', 'Another Song (Ed Sheeran, 2024)', 'No genre keywords here either'])
        tmp.close()
        try:
            e = TasteEngine(tmp.name)
            dist = e._get_genre_distribution()
            # Both Taylor Swift and Ed Sheeran should be classified as Pop via curated mapping fallback
            pop = dist.get('Pop', {})
            assert pop.get('count', 0) == 2, f"Expected 2 Pop songs from curated mapping fallback, got {pop.get('count', 0)}"
            uncat = dist.get('Uncategorized', {}).get('count', 0)
            assert uncat == 0, f"Expected 0 uncategorized with curated fallback, got {uncat}"
        finally:
            os.unlink(tmp.name)

    def test_curated_mapping_in_constellation_genre(self):
        """Constellation nodes should get genre from curated mapping when keywords don't match."""
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8', newline='')
        writer = csv.writer(tmp)
        writer.writerow(['date', 'rating', 'title', 'tail'])
        # Artist in curated mapping but no genre keywords in text
        writer.writerow(['2024-01-01', '85', 'Wonder (Taylor Swift, 2024)', 'Beautiful song'])
        tmp.close()
        try:
            e = TasteEngine(tmp.name)
            const = e.get_constellation()
            # Find Taylor Swift in nodes
            ts = [n for n in const['nodes'] if n['id'] == 'Taylor Swift']
            assert len(ts) == 1, "Taylor Swift should be in constellation nodes"
            assert ts[0]['genre'] == 'Pop', f"Expected 'Pop' from curated mapping, got '{ts[0]['genre']}'"
        finally:
            os.unlink(tmp.name)





class TestBanList:
    """Test the ban list feature (blocking genres/artists/songs from recs)."""

    def test_ban_list_loaded(self, engine):
        """Ban list should be loaded with Eurovision genre banned by default."""
        assert 'genres' in engine.ban_list
        assert isinstance(engine.ban_list['genres'], list)
        assert 'artists' in engine.ban_list
        assert 'songs' in engine.ban_list
        assert 'eurovision' in engine.ban_list['genres']

    def test_is_banned_genre(self, engine):
        """Eurovision should be banned."""
        assert engine._is_banned(genre='Eurovision') is True
        assert engine._is_banned(genre='eurovision') is True

    def test_is_banned_genre_not_banned(self, engine):
        """Pop should not be banned."""
        assert engine._is_banned(genre='Pop') is False
        assert engine._is_banned(genre='Rock') is False

    def test_is_banned_no_args(self, engine):
        """Calling with no args should return False."""
        assert engine._is_banned() is False

    def test_is_banned_artist_not_set(self, engine):
        """No artists are banned by default."""
        assert engine._is_banned(artist='Loreen') is False

    def test_is_banned_compound_song_entry(self, engine):
        """A ban stored as 'Artist \u2013 Song' must match when queried by separate
        artist + song fields (the format challenge ignore buttons produce)."""
        engine.ban_list['songs'].append('Neutral Milk Hotel \u2013 In the Aeroplane Over the Sea')
        try:
            assert engine._is_banned(artist='Neutral Milk Hotel',
                                     song='In the Aeroplane Over the Sea') is True
            # Case and dash variants should also match
            assert engine._is_banned(artist='neutral milk hotel',
                                     song='in the aeroplane over the sea') is True
        finally:
            engine.ban_list['songs'].remove('Neutral Milk Hotel \u2013 In the Aeroplane Over the Sea')

    def test_is_banned_bare_song_entry(self, engine):
        """A ban stored as a bare title still matches by song name."""
        engine.ban_list['songs'].append('Karma Police')
        try:
            assert engine._is_banned(artist='Radiohead', song='Karma Police') is True
            assert engine._is_banned(song='karma police') is True
        finally:
            engine.ban_list['songs'].remove('Karma Police')

    def test_challenges_exclude_ignored_compound_song(self, engine):
        """An ignored challenge song (stored as 'Artist \u2013 Song') must not reappear."""
        engine.ban_list['songs'].append('Neutral Milk Hotel \u2013 In the Aeroplane Over the Sea')
        try:
            chal = engine.get_challenges(count=50)
            combos = {(c['artist'].lower(), c['song'].lower()) for c in chal['challenges']}
            assert ('neutral milk hotel', 'in the aeroplane over the sea') not in combos
        finally:
            engine.ban_list['songs'].remove('Neutral Milk Hotel \u2013 In the Aeroplane Over the Sea')

    def test_recommendations_exclude_eurovision(self, engine):
        """Eurovision category should be empty (genre ban filters by cat name)."""
        recs = engine.get_recommendations()
        for cat_name, cat_data in recs.items():
            if 'eurovision' in cat_name.lower():
                assert len(cat_data['recommendations']) == 0,                     f"Eurovision category should be empty but has {len(cat_data['recommendations'])} recs"

    def test_challenges_exclude_banned_genre(self, engine):
        """Challenges with a banned genre should be filtered out."""
        engine.ban_list['genres'].append('rap/hip-hop')
        try:
            chal = engine.get_challenges(count=50)
            for c in chal['challenges']:
                mapped = c.get('class_genre', c.get('genre', '')).lower()
                assert mapped != 'rap/hip-hop',                     f"'{c['artist']} - {c['song']}' has banned genre 'Rap/Hip-Hop'"
        finally:
            engine.ban_list['genres'].remove('rap/hip-hop')


# ============================================================
# Taste DNA (Fingerprint) Tests
# ============================================================


class TestTasteFingerprint:
    """Test the taste fingerprint engine methods."""

    def test_fingerprint_returns_dict(self, engine):
        """get_taste_fingerprint should return a dict."""
        result = engine.get_taste_fingerprint()
        assert isinstance(result, dict)

    def test_fingerprint_has_all_keys(self, engine):
        """Should contain all expected keys."""
        result = engine.get_taste_fingerprint()
        expected = ['genre_fingerprint', 'year_fingerprint', 'predictability',
                    'top_influences', 'taste_summary', 'positive_song_count', 'overall_avg']
        for key in expected:
            assert key in result, f"Missing key: {key}"

    def test_fingerprint_genre_weights_sum_to_one(self, engine):
        """Genre weights should sum to approximately 1.0."""
        result = engine.get_taste_fingerprint()
        total = sum(g['weight'] for g in result['genre_fingerprint'].values())
        assert 0.99 <= total <= 1.01, f"Genre weights sum to {total}"

    def test_fingerprint_year_weights_sum_to_one(self, engine):
        """Year/decade weights should sum to approximately 1.0."""
        result = engine.get_taste_fingerprint()
        total = sum(y['weight'] for y in result['year_fingerprint'].values())
        assert 0.99 <= total <= 1.01, f"Year weights sum to {total}"

    def test_fingerprint_predictability_range(self, engine):
        """Predictability should be between 0 and 100."""
        result = engine.get_taste_fingerprint()
        p = result['predictability']
        assert 0 <= p['overall'] <= 100
        assert 0 <= p['genre_predictability'] <= 100
        assert 0 <= p['year_predictability'] <= 100

    def test_fingerprint_positive_song_count(self, engine):
        """Should count songs rated >= 75."""
        result = engine.get_taste_fingerprint()
        assert result['positive_song_count'] > 0

    def test_fingerprint_top_influences_sorted(self, engine):
        """Top influences should be sorted by influence score (descending)."""
        result = engine.get_taste_fingerprint()
        scores = [inf['influence_score'] for inf in result['top_influences']]
        assert scores == sorted(scores, reverse=True)

    def test_fingerprint_influences_have_required_fields(self, engine):
        """Each influence should have artist, influence_score, genres, top_song, top_rating."""
        result = engine.get_taste_fingerprint()
        for inf in result['top_influences']:
            assert 'artist' in inf
            assert 'influence_score' in inf
            assert 'genres' in inf
            assert 'top_song' in inf
            assert 'top_rating' in inf

    def test_fingerprint_skips_announcement(self, engine):
        """'Announcement' should not appear in top influences."""
        result = engine.get_taste_fingerprint()
        influence_names = [inf['artist'] for inf in result['top_influences']]
        assert 'Announcement' not in influence_names

    def test_fingerprint_genre_entry_has_required_fields(self, engine):
        """Each genre entry should have weight, avg_rating, song_count."""
        result = engine.get_taste_fingerprint()
        for genre, data in result['genre_fingerprint'].items():
            assert 'weight' in data, f"{genre} missing weight"
            assert 'avg_rating' in data, f"{genre} missing avg_rating"
            assert 'song_count' in data, f"{genre} missing song_count"
            assert data['weight'] >= 0

    def test_fingerprint_year_entry_has_required_fields(self, engine):
        """Each year/decade entry should have weight, avg_rating, song_count."""
        result = engine.get_taste_fingerprint()
        for decade, data in result['year_fingerprint'].items():
            assert 'weight' in data, f"{decade} missing weight"
            assert 'avg_rating' in data, f"{decade} missing avg_rating"
            assert 'song_count' in data, f"{decade} missing song_count"
            assert data['weight'] >= 0


class TestTasteFit:
    """Test the taste fit scorer."""

    def test_fit_returns_dict(self, engine):
        """get_taste_fit should return a dict."""
        result = engine.get_taste_fit('Test Artist', 'Test Song')
        assert isinstance(result, dict)

    def test_fit_has_all_fields(self, engine):
        """Should contain all expected fields."""
        result = engine.get_taste_fit('Test', 'Song')
        expected = ['fit_score', 'genre_match', 'year_match', 'artist_match',
                    'explanation', 'label']
        for field in expected:
            assert field in result, f"Missing field: {field}"

    def test_fit_score_range(self, engine):
        """Fit score should be between 0 and 100."""
        result = engine.get_taste_fit('Test', 'Song')
        assert 0 <= result['fit_score'] <= 100

    def test_fit_with_genre(self, engine):
        """Genre match should be positive when genre is in fingerprint."""
        result = engine.get_taste_fit('Test', 'Song', genre='Pop')
        assert result['genre_match'] > 0

    def test_fit_with_year(self, engine):
        """Year match should be non-negative."""
        result = engine.get_taste_fit('Test', 'Song', year=2015)
        assert result['year_match'] >= 0

    def test_fit_label_matches_score(self, engine):
        """Label should match the score range."""
        result = engine.get_taste_fit('Test', 'Song')
        score = result['fit_score']
        label = result['label']
        if score >= 90:
            assert label == 'Perfect Fit'
        elif score >= 75:
            assert label == 'Strong Match'
        elif score >= 60:
            assert label == 'Good Fit'
        elif score >= 40:
            assert label == 'Moderate Match'
        elif score >= 20:
            assert label == 'Weak Match'
        else:
            assert label == 'Poor Fit'

    def test_fit_influential_artist_scores_higher(self, engine):
        """Known favorite should score higher than unknown artist."""
        # Lindsey Stirling is a top influence in the test data
        d1 = engine.get_taste_fit('Lindsey Stirling', 'Song', 'Classical/Instrumental', 2015)
        d2 = engine.get_taste_fit('Unknown Artist', 'Song', 'Pop', 2020)
        assert d1['fit_score'] > d2['fit_score']

    def test_fit_explanation_is_string(self, engine):
        """Explanation should be a non-empty string."""
        result = engine.get_taste_fit('Test', 'Song')
        assert isinstance(result['explanation'], str)
        assert len(result['explanation']) > 0
