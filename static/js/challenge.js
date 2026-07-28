/**
 * challenge.js - Challenge view
 * Critically acclaimed songs from outside your listening zone.
 * Think of it as a "music education" section — songs the world loves
 * that you haven't encountered yet.
 */

async function loadChallenges() {
    showViewLoading('view-challenge', '🏆 Curating your challenges...');
    try {
        const res = await fetch('/api/challenges?count=24');
        const data = await res.json();
        hideViewLoading('view-challenge');
        renderChallenges(data);
    } catch (err) {
        hideViewLoading('view-challenge');
        console.error('Challenge load error:', err);
        document.getElementById('challengeContent').innerHTML =
            '<div class="view-error"><span class="view-error-icon">⚠️</span><p>Failed to load challenges</p><button class="btn btn-outline" onclick="loadChallenges()">Retry</button></div>';
    }
}

function renderChallenges(data) {
    const container = document.getElementById('challengeContent');
    const challenges = data.challenges || [];
    const byTier = data.by_tier || {};

    if (challenges.length === 0) {
        container.innerHTML = '<div class="challenge-empty"><p>🎉 You\'ve explored all our challenge songs! Come back later for new additions.</p></div>';
        return;
    }

    const tierOrder = ['legendary', 'modern_classic', 'classic', 'cult'];
    const tierLabels = {
        'legendary': { emoji: '🏆', label: 'Legendary', desc: 'The undisputed greats — songs that changed music forever' },
        'modern_classic': { emoji: '⭐', label: 'Modern Classics', desc: 'Critically acclaimed songs from the last 25 years' },
        'classic': { emoji: '💎', label: 'Timeless Classics', desc: 'Beloved songs that have stood the test of time' },
        'cult': { emoji: '🔥', label: 'Cult Favorites', desc: 'Deep cuts adored by critics and connoisseurs' },
    };

    let html = '';

    // Zone info banner
    html += `<div class="challenge-zone-banner">
        <div class="zone-banner-header">
            <span class="zone-banner-icon">🎯</span>
            <span>You're strong in <strong>${data.your_zones?.loved_genres?.length || 0}</strong> genres · 
            <strong>${data.your_zones?.known_artists_count || 0}</strong> known artists · 
            <strong>${data.total_available}</strong> challenges available</span>
        </div>
    </div>`;

    // Intro text
    html += `<div class="challenge-intro">
        <p>These are songs widely considered masterpieces — but they fall outside your usual listening patterns.
        Each one is a <strong>blind spot challenge</strong>: music that billions of people love, waiting for you to discover.</p>
    </div>`;

    // Render by tier
    for (const tier of tierOrder) {
        const tierSongs = byTier[tier] || [];
        if (tierSongs.length === 0) continue;
        
        const tl = tierLabels[tier] || { emoji: '🎵', label: tier, desc: '' };
        
        html += `<div class="challenge-tier">
            <div class="tier-header">
                <h3>${tl.emoji} ${tl.label}</h3>
                <p class="tier-desc">${tl.desc}</p>
            </div>
            <div class="challenge-grid">`;

        tierSongs.forEach(c => {
            const outsideStr = c.outside_score >= 3 ? '🚀' : c.outside_score >= 2 ? '🌟' : '📌';
            html += `<div class="challenge-card" onclick="challengeCardClick('${escapeHtml(c.artist)}', '${escapeHtml(c.song)}')">
                <div class="challenge-card-header">
                    <span class="challenge-tier-badge">${outsideStr} Level ${c.outside_score}</span>
                    <span class="challenge-year">${c.year}</span>
                </div>
                <div class="challenge-artist">${escapeHtml(c.artist)}</div>
                <div class="challenge-song">“${escapeHtml(c.song)}”</div>
                <div class="challenge-genre">${escapeHtml(c.genre)}</div>
                <div class="challenge-acclaim">${escapeHtml(c.acclaim)}</div>
                <div class="challenge-zone-note">
                    <span class="zone-note-icon">${outsideStr}</span>
                    ${escapeHtml(c.zone_note)}
                </div>
                <div class="challenge-actions">
                    <button class="rec-btn rec-btn-listen" onclick="event.stopPropagation(); searchSpotifyTrack('${escapeHtml(c.artist)}', '${escapeHtml(c.song)}')">▶ Listen</button>
                    <button class="rec-btn rec-btn-add" onclick="event.stopPropagation(); quickAddFromRecommender('${escapeHtml(c.artist)}', '${escapeHtml(c.song)}')">+ Save</button>
                </div>
            </div>`;
        });

        html += `</div></div>`;
    }

    // Stats footer
    html += `<div class="challenge-footer">
        <p>🎵 ${challenges.length} challenges shown · ${data.total_available} total available · 
        Songs sourced from Rolling Stone 500, RateYourMusic charts, Grammy winners, and critical consensus.</p>
        <button class="btn btn-outline" onclick="loadChallenges()" style="margin-top:12px">🔄 Refresh Challenges</button>
    </div>`;

    container.innerHTML = html;
}

function challengeCardClick(artist, song) {
    // Open on Spotify on click
    searchSpotifyTrack(artist, song);
}
