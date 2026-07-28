/**
 * challenge.js - Challenge view
 * Critically acclaimed songs from outside your listening zone,
 * plus an "Opposite Taste" mode that pushes genres you rate lowest.
 */

let currentChallengeMode = 'outside_zone';

async function loadChallenges() {
    showViewLoading('view-challenge', '🏆 Curating your challenges...');
    try {
        const res = await fetch('/api/challenges?count=24&mode=' + currentChallengeMode);
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

function switchChallengeMode(mode) {
    currentChallengeMode = mode;
    // Update toggle buttons
    document.querySelectorAll('.challenge-mode-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.mode === mode);
    });
    // Update loading text based on mode
    const label = mode === 'outside_zone' ? '🏆 Curating your blind spots...' : '⚡ Finding opposite-taste challenges...';
    showViewLoading('view-challenge', label);
    loadChallengesMode(mode);
}

async function loadChallengesMode(mode) {
    try {
        const res = await fetch('/api/challenges?count=24&mode=' + mode);
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
    const mode = data.mode || 'outside_zone';

    if (challenges.length === 0) {
        container.innerHTML = '<div class="challenge-empty">' +
            '<p>🎉 You\'ve explored all our challenge songs! Come back later for new additions.</p></div>';
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

    // === Mode Toggle ===
    html += '<div class="challenge-mode-toggle">' +
        '<button class="challenge-mode-btn' + (mode === 'outside_zone' ? ' active' : '') + '" ' +
        'data-mode="outside_zone" onclick="switchChallengeMode(\'outside_zone\')">' +
        '🎯 Blind Spots</button>' +
        '<button class="challenge-mode-btn' + (mode === 'opposite_taste' ? ' active' : '') + '" ' +
        'data-mode="opposite_taste" onclick="switchChallengeMode(\'opposite_taste\')">' +
        '⚡ Opposite Taste</button>' +
        '</div>';

    // === Zone Info Banner ===
    const isOpposite = mode === 'opposite_taste';
    const lowestGenres = data.your_zones?.lowest_rated_genres || [];
    
    if (isOpposite) {
        html += '<div class="challenge-zone-banner opposite-banner">' +
            '<div class="zone-banner-header">' +
            '<span class="zone-banner-icon">⚡</span>' +
            '<span>Opposite-Taste Mode · Targeting your <strong>' + lowestGenres.length + '</strong> lowest-rated genres: ' +
            (lowestGenres.length > 0 ? '<strong>' + escapeHtml(lowestGenres.join(', ')) + '</strong>' : '') +
            ' · <strong>' + data.total_available + '</strong> challenges available</span>' +
            '</div></div>';
    } else {
        html += '<div class="challenge-zone-banner">' +
            '<div class="zone-banner-header">' +
            '<span class="zone-banner-icon">🎯</span>' +
            '<span>You\'re strong in <strong>' + (data.your_zones?.loved_genres?.length || 0) + '</strong> genres · ' +
            '<strong>' + (data.your_zones?.known_artists_count || 0) + '</strong> known artists · ' +
            '<strong>' + data.total_available + '</strong> challenges available</span>' +
            '</div></div>';
    }

    // === Intro Text ===
    if (isOpposite) {
        html += '<div class="challenge-intro opposite-intro">' +
            '<p>These are <strong>critically acclaimed masterpieces</strong> from genres you historically rate low. ' +
            'Think of this as musical vegetables 🥦 — universally beloved songs that might change your mind about a whole genre. ' +
            'You rated <strong>' + escapeHtml(lowestGenres.join(', ')) + '</strong> songs low on average. ' +
            'These are the absolute best that those genres have to offer.</p></div>';
    } else {
        html += '<div class="challenge-intro">' +
            '<p>These are songs widely considered masterpieces — but they fall outside your usual listening patterns. ' +
            'Each one is a <strong>blind spot challenge</strong>: music that billions of people love, waiting for you to discover.</p></div>';
    }

    // === Render by tier ===
    for (const tier of tierOrder) {
        const tierSongs = byTier[tier] || [];
        if (tierSongs.length === 0) continue;
        
        const tl = tierLabels[tier] || { emoji: '🎵', label: tier, desc: '' };
        
        html += '<div class="challenge-tier">' +
            '<div class="tier-header">' +
            '<h3>' + tl.emoji + ' ' + tl.label + '</h3>' +
            '<p class="tier-desc">' + tl.desc + '</p></div>' +
            '<div class="challenge-grid">';

        tierSongs.forEach(function(c) {
            const outsideStr = c.outside_score >= 4 ? '🚀' : c.outside_score >= 3 ? '🌟' : c.outside_score >= 2 ? '🔥' : '📌';
            const isOppositeCard = isOpposite && lowestGenres.indexOf(c.class_genre || c.genre) !== -1;
            
            html += '<div class="challenge-card' + (isOppositeCard ? ' opposite-card' : '') + '" ' +
                'onclick="challengeCardClick(\'' + escapeHtml(c.artist) + '\', \'' + escapeHtml(c.song) + '\')">' +
                '<div class="challenge-card-header">' +
                '<span class="challenge-tier-badge">' + outsideStr + ' Level ' + c.outside_score + '</span>' +
                '<span class="challenge-year">' + c.year + '</span></div>' +
                '<div class="challenge-artist">' + escapeHtml(c.artist) + '</div>' +
                '<div class="challenge-song">\u201c' + escapeHtml(c.song) + '\u201d</div>' +
                '<div class="challenge-genre">' + escapeHtml(c.genre) + '</div>' +
                '<div class="challenge-acclaim">' + escapeHtml(c.acclaim) + '</div>' +
                '<div class="challenge-zone-note">' +
                '<span class="zone-note-icon">' + outsideStr + '</span> ' +
                escapeHtml(c.zone_note) + '</div>' +
                '<div class="challenge-actions">' +
                '<button class="rec-btn rec-btn-listen" ' +
                'onclick="event.stopPropagation(); searchSpotifyTrack(\'' + escapeHtml(c.artist) + '\', \'' + escapeHtml(c.song) + '\')">\u25b6 Listen</button>' +
                '<button class="rec-btn rec-btn-add" ' +
                'onclick="event.stopPropagation(); quickAddFromRecommender(\'' + escapeHtml(c.artist) + '\', \'' + escapeHtml(c.song) + '\')">+ Save</button></div></div>';
        });

        html += '</div></div>';
    }

    // === Stats Footer ===
    if (isOpposite) {
        html += '<div class="challenge-footer opposite-footer">' +
            '<p>\u26a1 ' + challenges.length + ' opposite-taste challenges shown &middot; ' + data.total_available + ' total available &middot; ' +
            'Sourced from Rolling Stone 500, RateYourMusic, Grammy winners &middot; ' +
            'Push your boundaries by exploring your lowest-rated genres with their best offerings.</p>' +
            '<button class="btn btn-outline" onclick="loadChallenges()" style="margin-top:12px">\ud83d\udd04 Refresh</button></div>';
    } else {
        html += '<div class="challenge-footer">' +
            '<p>\ud83c\udfb5 ' + challenges.length + ' challenges shown &middot; ' + data.total_available + ' total available &middot; ' +
            'Songs sourced from Rolling Stone 500, RateYourMusic charts, Grammy winners, and critical consensus.</p>' +
            '<button class="btn btn-outline" onclick="loadChallenges()" style="margin-top:12px">\ud83d\udd04 Refresh</button></div>';
    }

    container.innerHTML = html;
}

function challengeCardClick(artist, song) {
    searchSpotifyTrack(artist, song);
}
