# 🎯 ML Advanced Recommendation Engine — Design Document

## Overview

This document outlines the architecture for a machine learning-powered recommendation engine that goes beyond the current rule-based system. The new engine will leverage audio features, listening patterns, and external platform data (YouTube/Spotify) to provide more accurate and personalized recommendations.

## Current System Limitations

The existing recommendation engine uses:
- **Keyword-based genre matching** — Limited to text analysis
- **Artist similarity** — Based on co-occurrence in reviews
- **Random sampling** — Within genre categories
- **No audio features** — Ignores musical characteristics
- **No external validation** — No real-time data from platforms

## Proposed ML Engine Architecture

### 1. Feature Engineering Layer

#### Audio Features (from Spotify/YouTube)
```python
# Spotify Audio Features
audio_features = {
    "acousticness": float,    # 0.0-1.0 confidence track is acoustic
    "danceability": float,    # 0.0-1.0 how suitable for dancing
    "energy": float,          # 0.0-1.0 perceptual measure of intensity
    "instrumentalness": float,# 0.0-1.0 predicts absence of vocals
    "liveness": float,        # 0.0-1.0 presence of audience
    "loudness": float,        # dB overall loudness
    "speechiness": float,     # 0.0-1.0 presence of spoken words
    "tempo": float,           # BPM estimated tempo
    "valence": float,         # 0.0-1.0 musical positiveness
    "key": int,               # 0-11 pitch class
    "time_signature": int,    # estimated time signature
}

# YouTube Features (via YouTube Data API)
youtube_features = {
    "view_count": int,        # Total views
    "like_count": int,        # Total likes
    "comment_count": int,     # Total comments
    "duration": int,          # Video length in seconds
    "publish_date": str,      # When published
    "channel_subscribers": int,# Channel size
    "genre_tags": list,       # Video category tags
}
```

#### User Taste Profile
```python
user_profile = {
    "genre_distribution": dict,    # Genre preferences
    "rating_patterns": dict,       # Rating behavior over time
    "artist_affinity": dict,       # Artist preference scores
    "temporal_patterns": dict,     # Listening time patterns
    "audio_feature_preferences": dict,  # Preferred audio features
    "mood_preferences": dict,      # Mood/emotion patterns
}
```

### 2. ML Models

#### Model 1: Collaborative Filtering
- **Purpose**: Find users with similar taste patterns
- **Algorithm**: Matrix Factorization (SVD) or Neural Collaborative Filtering
- **Input**: User-item interaction matrix (ratings)
- **Output**: Predicted ratings for unrated songs

#### Model 2: Content-Based Filtering
- **Purpose**: Recommend songs with similar audio features
- **Algorithm**: K-Nearest Neighbors (KNN) or Neural Networks
- **Input**: Audio features of liked songs
- **Output**: Similar songs ranked by feature similarity

#### Model 3: Hybrid Model
- **Purpose**: Combine collaborative and content-based approaches
- **Algorithm**: Weighted ensemble or neural network
- **Input**: Both user interactions and audio features
- **Output**: Final recommendation scores

### 3. External Platform Integration

#### Spotify Integration
```python
class SpotifyMLIntegration:
    def __init__(self, client_id, client_secret):
        self.sp = spotipy.Spotify(auth_manager=SpotifyOAuth(...))
    
    def get_audio_features(self, track_id):
        """Get audio features for a track"""
        return self.sp.audio_features([track_id])[0]
    
    def get_recommendations_by_features(self, seed_tracks, target_features):
        """Get recommendations based on audio features"""
        return self.sp.recommendations(
            seed_tracks=seed_tracks,
            target_acousticness=target_features.get('acousticness'),
            target_danceability=target_features.get('danceability'),
            target_energy=target_features.get('energy'),
            target_valence=target_features.get('valence'),
            limit=20
        )
    
    def search_with_filters(self, query, genre=None, year_range=None):
        """Search with genre and year filters"""
        q = query
        if genre:
            q += f" genre:{genre}"
        if year_range:
            q += f" year:{year_range[0]}-{year_range[1]}"
        return self.sp.search(q, type='track', limit=50)
```

#### YouTube Integration
```python
class YouTubeMLIntegration:
    def __init__(self, api_key):
        self.youtube = googleapiclient.discovery.build(
            'youtube', 'v3', developerKey=api_key
        )
    
    def get_video_stats(self, video_id):
        """Get video statistics"""
        request = self.youtube.videos().list(
            part="statistics,snippet",
            id=video_id
        )
        response = request.execute()
        return response['items'][0]['statistics']
    
    def search_with_genre_filter(self, query, genre=None):
        """Search with genre/category filter"""
        request = self.youtube.search().list(
            q=query,
            part="snippet",
            videoCategoryId=genre if genre else None,
            type="video",
            maxResults=50
        )
        return request.execute()
    
    def get_trending_by_genre(self, genre_id):
        """Get trending videos in a genre"""
        request = self.youtube.videos().list(
            part="statistics,snippet",
            chart="mostPopular",
            videoCategoryId=genre_id,
            regionCode="US",
            maxResults=50
        )
        return request.execute()
```

### 4. Recommendation Pipeline

```python
class MLRecommendationEngine:
    def __init__(self):
        self.collaborative_model = None
        self.content_model = None
        self.hybrid_model = None
        self.feature_scaler = StandardScaler()
    
    def train(self, user_data, audio_features):
        """Train all models"""
        # Prepare data
        X, y = self._prepare_training_data(user_data, audio_features)
        
        # Train collaborative filtering
        self.collaborative_model = self._train_collaborative(X, y)
        
        # Train content-based
        self.content_model = self._train_content_based(audio_features)
        
        # Train hybrid
        self.hybrid_model = self._train_hybrid(X, y, audio_features)
    
    def recommend(self, user_id, n_recommendations=10):
        """Generate recommendations for a user"""
        # Get user profile
        user_profile = self._get_user_profile(user_id)
        
        # Get candidate songs
        candidates = self._get_candidate_songs(user_profile)
        
        # Score with each model
        collaborative_scores = self.collaborative_model.predict(
            user_id, candidates
        )
        content_scores = self.content_model.predict(
            user_profile['audio_preferences'], candidates
        )
        hybrid_scores = self.hybrid_model.predict(
            user_id, candidates
        )
        
        # Combine scores (weighted average)
        final_scores = (
            0.3 * collaborative_scores +
            0.3 * content_scores +
            0.4 * hybrid_scores
        )
        
        # Apply filters
        filtered = self._apply_filters(candidates, final_scores, user_profile)
        
        # Return top N
        return sorted(
            zip(filtered, final_scores),
            key=lambda x: x[1],
            reverse=True
        )[:n_recommendations]
    
    def _apply_filters(self, candidates, scores, user_profile):
        """Apply platform-specific filters"""
        filtered = []
        for song, score in zip(candidates, scores):
            # Check genre restrictions
            if not self._check_genre_restrictions(song, user_profile):
                continue
            
            # Check view count thresholds
            if not self._check_view_counts(song, user_profile):
                continue
            
            # Check availability
            if not self._check_availability(song):
                continue
            
            filtered.append(song)
        return filtered
```

### 5. Genre Restriction & View Count Logic

#### Genre Restrictions
```python
def check_genre_restrictions(song, user_profile):
    """
    Check if song's genre is allowed based on user preferences
    
    Returns:
        bool: True if genre is allowed
    """
    song_genre = song.get('genre', 'Unknown')
    
    # Check if genre is in ban list
    if song_genre in user_profile.get('banned_genres', []):
        return False
    
    # Check genre confidence threshold
    if song.get('genre_confidence', 0) < 0.3:
        # Low confidence classification - be more conservative
        return song_genre in user_profile.get('preferred_genres', [])
    
    # Check if genre matches user's taste profile
    genre_pref = user_profile.get('genre_distribution', {})
    if song_genre in genre_pref:
        return genre_pref[song_genre] > 0.1  # At least 10% preference
    
    # Unknown genre - allow if user is exploratory
    return user_profile.get('exploration_score', 0) > 0.5
```

#### View Count Thresholds
```python
def check_view_counts(song, user_profile):
    """
    Check if song meets view count requirements
    
    Thresholds:
    - Mainstream: > 1M views
    - Popular: 100K-1M views
    - Niche: 10K-100K views
    - Underground: < 10K views
    
    Returns:
        bool: True if view count is acceptable
    """
    view_count = song.get('view_count', 0)
    user_pref = user_profile.get('popularity_preference', 'popular')
    
    thresholds = {
        'mainstream': 1_000_000,
        'popular': 100_000,
        'niche': 10_000,
        'underground': 0
    }
    
    min_views = thresholds.get(user_pref, 10_000)
    max_views = thresholds.get(
        list(thresholds.keys())[
            list(thresholds.keys()).index(user_pref) + 1
        ],
        float('inf')
    )
    
    return min_views <= view_count < max_views
```

### 6. API Endpoints

```python
# New ML-powered endpoints
@app.route('/api/ml/recommendations')
def ml_recommendations():
    """Get ML-powered recommendations"""
    user_id = request.args.get('user_id', 'default')
    count = request.args.get('count', 10, type=int)
    
    engine = MLRecommendationEngine()
    recommendations = engine.recommend(user_id, count)
    
    return jsonify({
        'recommendations': recommendations,
        'model_version': '1.0.0',
        'confidence_scores': [r['confidence'] for r in recommendations]
    })

@app.route('/api/ml/similar-songs')
def ml_similar_songs():
    """Find songs similar to a given song"""
    song_id = request.args.get('song_id')
    count = request.args.get('count', 10, type=int)
    
    engine = MLRecommendationEngine()
    similar = engine.find_similar(song_id, count)
    
    return jsonify({'similar_songs': similar})

@app.route('/api/ml/taste-profile')
def ml_taste_profile():
    """Get detailed taste profile with audio features"""
    user_id = request.args.get('user_id', 'default')
    
    engine = MLRecommendationEngine()
    profile = engine.get_taste_profile(user_id)
    
    return jsonify(profile)
```

### 7. Data Storage

#### New Tables
```sql
-- Audio features cache
CREATE TABLE audio_features (
    song_id VARCHAR(255) PRIMARY KEY,
    spotify_id VARCHAR(255),
    youtube_id VARCHAR(255),
    features JSON,
    last_updated TIMESTAMP,
    source VARCHAR(50)  -- 'spotify', 'youtube', 'computed'
);

-- User taste profiles
CREATE TABLE user_taste_profiles (
    user_id VARCHAR(255) PRIMARY KEY,
    profile JSON,
    model_version VARCHAR(50),
    last_trained TIMESTAMP,
    sample_size INTEGER
);

-- Recommendation history
CREATE TABLE recommendation_history (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255),
    song_id VARCHAR(255),
    model_used VARCHAR(50),
    score FLOAT,
    was_listened BOOLEAN,
    created_at TIMESTAMP
);

-- Platform restrictions
CREATE TABLE platform_restrictions (
    platform VARCHAR(50),
    genre VARCHAR(100),
    min_views INTEGER,
    max_views INTEGER,
    allowed BOOLEAN,
    PRIMARY KEY (platform, genre)
);
```

### 8. Implementation Phases

#### Phase 1: Data Collection (Week 1-2)
- [ ] Set up Spotify API integration for audio features
- [ ] Set up YouTube Data API for view counts
- [ ] Create database tables for audio features
- [ ] Build data collection pipeline
- [ ] Collect features for existing songs

#### Phase 2: Model Development (Week 3-4)
- [ ] Implement collaborative filtering model
- [ ] Implement content-based model
- [ ] Train initial models on existing data
- [ ] Validate model performance
- [ ] Set up model versioning

#### Phase 3: Integration (Week 5-6)
- [ ] Integrate models into Flask backend
- [ ] Create new ML-powered API endpoints
- [ ] Update frontend to use ML recommendations
- [ ] Add A/B testing framework
- [ ] Implement caching for performance

#### Phase 4: Refinement (Week 7-8)
- [ ] Collect user feedback on recommendations
- [ ] Retrain models with new data
- [ ] Optimize for real-time performance
- [ ] Add explainability features
- [ ] Document model decisions

### 9. Performance Considerations

- **Caching**: Cache audio features and recommendations (TTL: 24 hours)
- **Batch Processing**: Pre-compute recommendations nightly
- **Lazy Loading**: Load features on-demand for new songs
- **Model Updates**: Retrain weekly with new data
- **Fallback**: Graceful degradation to rule-based system if ML fails

### 10. Monitoring & Evaluation

#### Metrics
- **Precision@K**: How many of top K recommendations are relevant
- **Recall@K**: How many relevant songs are in top K
- **NDCG**: Normalized Discounted Cumulative Gain
- **Click-Through Rate**: User engagement with recommendations
- **Listening Time**: How long users listen to recommended songs

#### Monitoring
```python
class RecommendationMonitor:
    def track_impression(self, user_id, song_id, position):
        """Track when a recommendation is shown"""
        pass
    
    def track_click(self, user_id, song_id):
        """Track when a user clicks a recommendation"""
        pass
    
    def track_listen(self, user_id, song_id, duration):
        """Track listening behavior"""
        pass
    
    def calculate_metrics(self, date_range):
        """Calculate performance metrics"""
        pass
```

## Success Criteria

1. **Accuracy**: ML recommendations should outperform rule-based by 20%+ in user testing
2. **Engagement**: Increase in recommendation click-through rate by 15%
3. **Diversity**: Maintain genre diversity in recommendations
4. **Performance**: Response time < 200ms for recommendation requests
5. **Scalability**: Support 1000+ users with daily retraining

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| API rate limits | Data collection delays | Implement exponential backoff, batch requests |
| Model overfitting | Poor generalization | Cross-validation, regularization |
| Cold start problem | Poor recommendations for new users | Use popularity-based fallback |
| Platform changes | Broken integrations | Abstract API layer, version pinning |
| Privacy concerns | User trust issues | Anonymize data, transparent policies |

## Conclusion

The ML recommendation engine will significantly improve recommendation quality by leveraging audio features and platform data. The hybrid approach combines the strengths of collaborative and content-based filtering while maintaining the existing system as a fallback. The modular design allows for incremental implementation and easy maintenance.
