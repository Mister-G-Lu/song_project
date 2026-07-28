"""
spotify_helper.py - Optional Spotify API integration for audio features and playlist creation.
Works without Spotify credentials too — just skips Spotify-specific features.
"""

import os
import re
from typing import Optional, Dict, List

try:
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials
    SPOTIPY_AVAILABLE = True
except ImportError:
    SPOTIPY_AVAILABLE = False


class SpotifyHelper:
    def __init__(self):
        self.client_id = os.environ.get('SPOTIFY_CLIENT_ID', '')
        self.client_secret = os.environ.get('SPOTIFY_CLIENT_SECRET', '')
        self.sp = None
        self._initialized = False

        if SPOTIPY_AVAILABLE and self.client_id and self.client_secret:
            try:
                auth_manager = SpotifyClientCredentials(
                    client_id=self.client_id,
                    client_secret=self.client_secret
                )
                self.sp = spotipy.Spotify(auth_manager=auth_manager)
                self._initialized = True
            except Exception as e:
                print(f"Spotify init warning: {e}")

    def is_available(self) -> bool:
        """Check if Spotify integration is available."""
        return self._initialized

    def search_track(self, title: str, artist: str = '') -> Optional[Dict]:
        """Search for a track on Spotify."""
        if not self._initialized:
            return None
        
        try:
            query = f"{title} {artist}".strip()
            results = self.sp.search(q=query, type='track', limit=1)
            if results['tracks']['items']:
                track = results['tracks']['items'][0]
                return {
                    'id': track['id'],
                    'name': track['name'],
                    'artist': track['artists'][0]['name'],
                    'album': track['album']['name'],
                    'preview_url': track.get('preview_url'),
                    'external_url': track['external_urls']['spotify'],
                    'album_image': track['album']['images'][0]['url'] if track['album']['images'] else None,
                    'duration_ms': track['duration_ms'],
                    'popularity': track['popularity'],
                }
        except Exception as e:
            print(f"Spotify search error: {e}")
        return None

    def get_audio_features(self, track_id: str) -> Optional[Dict]:
        """Get audio features for a track."""
        if not self._initialized:
            return None
        
        try:
            features = self.sp.audio_features([track_id])
            if features and features[0]:
                f = features[0]
                return {
                    'danceability': f['danceability'],
                    'energy': f['energy'],
                    'key': f['key'],
                    'loudness': f['loudness'],
                    'mode': f['mode'],
                    'speechiness': f['speechiness'],
                    'acousticness': f['acousticness'],
                    'instrumentalness': f['instrumentalness'],
                    'liveness': f['liveness'],
                    'valence': f['valence'],
                    'tempo': f['tempo'],
                }
        except Exception as e:
            print(f"Audio features error: {e}")
        return None

    def get_recommendations_from_seeds(self, seed_tracks: List[str] = None,
                                        seed_artists: List[str] = None,
                                        seed_genres: List[str] = None,
                                        limit: int = 20) -> List[Dict]:
        """Get Spotify recommendations based on seed tracks/artists/genres."""
        if not self._initialized or not (seed_tracks or seed_artists or seed_genres):
            return []

        try:
            kwargs = {'limit': limit}
            if seed_tracks:
                kwargs['seed_tracks'] = seed_tracks[:5]
            if seed_artists:
                kwargs['seed_artists'] = seed_artists[:5]
            if seed_genres:
                kwargs['seed_genres'] = seed_genres[:5]

            results = self.sp.recommendations(**kwargs)
            tracks = []
            for track in results['tracks']:
                tracks.append({
                    'id': track['id'],
                    'name': track['name'],
                    'artist': track['artists'][0]['name'],
                    'album': track['album']['name'],
                    'preview_url': track.get('preview_url'),
                    'external_url': track['external_urls']['spotify'],
                    'album_image': track['album']['images'][0]['url'] if track['album']['images'] else None,
                    'popularity': track['popularity'],
                })
            return tracks
        except Exception as e:
            print(f"Recommendations error: {e}")
        return []

    def create_playlist(self, user_id: str, name: str, description: str = '',
                        track_uris: List[str] = None) -> Optional[Dict]:
        """Create a Spotify playlist (requires user auth — not just client credentials)."""
        # Note: This requires user authorization, not just client credentials
        # For now, returns None as a placeholder
        return None

    def extract_search_terms(self, song_data: Dict) -> Dict:
        """Extract searchable terms from our song data for Spotify lookups."""
        title = song_data.get('title', '')
        
        # Try to extract artist and song name
        m = re.match(r'^(.+?)\s*[–-]\s*(.+?)(?:\s*\(.*?\))?$', title)
        if m:
            return {'song': m.group(2).strip(), 'artist': m.group(1).strip()}
        
        m = re.search(r'^(.+?)\s*\(([^,]+),?\s*\d{4}\)$', title)
        if m:
            return {'song': m.group(1).strip(), 'artist': m.group(2).strip()}
        
        return {'song': title, 'artist': ''}
