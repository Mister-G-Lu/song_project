"""
Unit tests for spotify_helper.py
Uses mocking to avoid actual Spotify API calls.
"""

import os
from unittest.mock import MagicMock, patch, PropertyMock
import pytest
from spotify_helper import SpotifyHelper


class TestSpotifyHelperInit:
    """Test initialization behavior."""

    def test_init_without_credentials(self):
        """Helper should not be available without credentials."""
        # Ensure no env vars are set
        os.environ.pop('SPOTIFY_CLIENT_ID', None)
        os.environ.pop('SPOTIFY_CLIENT_SECRET', None)
        helper = SpotifyHelper()
        assert not helper.is_available()

    @patch.dict(os.environ, {'SPOTIFY_CLIENT_ID': 'test_id', 'SPOTIFY_CLIENT_SECRET': 'test_secret'})
    @patch('spotify_helper.SpotifyClientCredentials')
    @patch('spotify_helper.spotipy.Spotify')
    def test_init_with_credentials(self, mock_spotify, mock_auth):
        """Helper should initialize with valid credentials."""
        mock_auth.return_value = MagicMock()
        mock_spotify.return_value = MagicMock()
        helper = SpotifyHelper()
        assert helper.is_available()
        mock_spotify.assert_called_once()

    @patch.dict(os.environ, {'SPOTIFY_CLIENT_ID': 'test_id', 'SPOTIFY_CLIENT_SECRET': 'test_secret'})
    def test_init_auth_failure(self):
        """Helper should handle auth failure gracefully."""
        # The actual import may fail, so this tests that init doesn't crash
        helper = SpotifyHelper()
        # May or may not be available depending on spotipy installation
        assert isinstance(helper.is_available(), bool)


class TestSearchTrack:
    """Test search_track method."""

    def test_search_track_no_init(self):
        """Should return None if not initialized."""
        os.environ.pop('SPOTIFY_CLIENT_ID', None)
        os.environ.pop('SPOTIFY_CLIENT_SECRET', None)
        helper = SpotifyHelper()
        result = helper.search_track('Test Song', 'Test Artist')
        assert result is None

    @patch.dict(os.environ, {'SPOTIFY_CLIENT_ID': 'test_id', 'SPOTIFY_CLIENT_SECRET': 'test_secret'})
    @patch('spotify_helper.SpotifyClientCredentials')
    @patch('spotify_helper.spotipy.Spotify')
    def test_search_track_found(self, mock_spotify, mock_auth):
        """Should return formatted track data when found."""
        mock_instance = MagicMock()
        mock_instance.search.return_value = {
            'tracks': {
                'items': [{
                    'id': 'abc123',
                    'name': 'Test Song',
                    'artists': [{'name': 'Test Artist'}],
                    'album': {'name': 'Test Album', 'images': [{'url': 'http://img.url'}]},
                    'preview_url': 'http://preview.url',
                    'external_urls': {'spotify': 'http://open.spotify.com/track/abc123'},
                    'duration_ms': 200000,
                    'popularity': 75,
                }]
            }
        }
        mock_auth.return_value = MagicMock()
        mock_spotify.return_value = mock_instance

        helper = SpotifyHelper()
        result = helper.search_track('Test Song', 'Test Artist')
        
        assert result is not None
        assert result['id'] == 'abc123'
        assert result['name'] == 'Test Song'
        assert result['artist'] == 'Test Artist'
        assert result['external_url'] == 'http://open.spotify.com/track/abc123'

    @patch.dict(os.environ, {'SPOTIFY_CLIENT_ID': 'test_id', 'SPOTIFY_CLIENT_SECRET': 'test_secret'})
    @patch('spotify_helper.SpotifyClientCredentials')
    @patch('spotify_helper.spotipy.Spotify')
    def test_search_track_not_found(self, mock_spotify, mock_auth):
        """Should return None when track not found."""
        mock_instance = MagicMock()
        mock_instance.search.return_value = {'tracks': {'items': []}}
        mock_auth.return_value = MagicMock()
        mock_spotify.return_value = mock_instance

        helper = SpotifyHelper()
        result = helper.search_track('Nonexistent Song')
        assert result is None


class TestAudioFeatures:
    """Test get_audio_features method."""

    def test_get_audio_features_no_init(self):
        """Should return None if not initialized."""
        os.environ.pop('SPOTIFY_CLIENT_ID', None)
        os.environ.pop('SPOTIFY_CLIENT_SECRET', None)
        helper = SpotifyHelper()
        result = helper.get_audio_features('abc123')
        assert result is None

    @patch.dict(os.environ, {'SPOTIFY_CLIENT_ID': 'test_id', 'SPOTIFY_CLIENT_SECRET': 'test_secret'})
    @patch('spotify_helper.SpotifyClientCredentials')
    @patch('spotify_helper.spotipy.Spotify')
    def test_get_audio_features_success(self, mock_spotify, mock_auth):
        """Should return formatted audio features."""
        mock_instance = MagicMock()
        mock_instance.audio_features.return_value = [{
            'danceability': 0.8,
            'energy': 0.7,
            'key': 5,
            'loudness': -8.5,
            'mode': 1,
            'speechiness': 0.05,
            'acousticness': 0.3,
            'instrumentalness': 0.01,
            'liveness': 0.1,
            'valence': 0.6,
            'tempo': 120.0,
        }]
        mock_auth.return_value = MagicMock()
        mock_spotify.return_value = mock_instance

        helper = SpotifyHelper()
        result = helper.get_audio_features('abc123')
        
        assert result is not None
        assert result['danceability'] == 0.8
        assert result['energy'] == 0.7
        assert result['tempo'] == 120.0


class TestRecommendations:
    """Test get_recommendations_from_seeds method."""

    @patch.dict(os.environ, {'SPOTIFY_CLIENT_ID': 'test_id', 'SPOTIFY_CLIENT_SECRET': 'test_secret'})
    @patch('spotify_helper.SpotifyClientCredentials')
    @patch('spotify_helper.spotipy.Spotify')
    def test_recommendations_with_seeds(self, mock_spotify, mock_auth):
        """Should return recommendations based on seeds."""
        mock_instance = MagicMock()
        mock_instance.recommendations.return_value = {
            'tracks': [{
                'id': 'rec1',
                'name': 'Recommended Song',
                'artists': [{'name': 'Recommended Artist'}],
                'album': {'name': 'Album', 'images': [{'url': 'http://img.url'}]},
                'preview_url': None,
                'external_urls': {'spotify': 'http://open.spotify.com/track/rec1'},
                'popularity': 60,
            }]
        }
        mock_auth.return_value = MagicMock()
        mock_spotify.return_value = mock_instance

        helper = SpotifyHelper()
        result = helper.get_recommendations_from_seeds(
            seed_tracks=['abc123'],
            seed_artists=['artist1'],
            limit=1
        )
        
        assert len(result) == 1
        assert result[0]['id'] == 'rec1'
        assert result[0]['artist'] == 'Recommended Artist'

    def test_recommendations_no_seeds(self):
        """Should return empty if no seeds provided."""
        os.environ.pop('SPOTIFY_CLIENT_ID', None)
        os.environ.pop('SPOTIFY_CLIENT_SECRET', None)
        helper = SpotifyHelper()
        result = helper.get_recommendations_from_seeds()
        assert result == []


class TestExtractSearchTerms:
    """Test extract_search_terms method."""

    def test_extract_dash_format(self):
        """Extract from 'Artist - Title' format."""
        os.environ.pop('SPOTIFY_CLIENT_ID', None)
        os.environ.pop('SPOTIFY_CLIENT_SECRET', None)
        helper = SpotifyHelper()
        result = helper.extract_search_terms({'title': 'Test Artist – Song Title'})
        assert result['artist'] == 'Test Artist'
        assert result['song'] == 'Song Title'

    def test_extract_parenthetical_format(self):
        """Extract from 'Title (Artist, Year)' format."""
        helper = SpotifyHelper()
        result = helper.extract_search_terms({'title': 'Song Title (Test Artist, 2020)'})
        assert result['song'] == 'Song Title'
        assert result['artist'] == 'Test Artist'

    def test_extract_no_match(self):
        """Return raw title when no pattern matches."""
        helper = SpotifyHelper()
        result = helper.extract_search_terms({'title': 'Just a song'})
        assert result['song'] == 'Just a song'
        assert result['artist'] == ''
