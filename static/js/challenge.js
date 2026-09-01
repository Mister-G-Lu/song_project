/**
 * challenge.js - Challenge view
 * Critically acclaimed songs from outside your listening zone,
 * plus an "Opposite Taste" mode that pushes genres you rate lowest.
 */

let currentChallengeMode = 'outside_zone';
let currentPopularityThreshold = 85;

async function loadChallenges() {
    showViewLoading('view-challenge', '🏆 Curating your challenges...');
    try {
        let url = '/api/challenges?count=24&mode=' + currentChallengeMode;
        if (currentChallengeMode === 'obscure') {
            url += '&popularity_threshold=' + currentPopularityThreshold;
        }
        const res = await fetch(url);
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
    const labels = {
        'outside_zone': '🏆 Curating acclaimed songs...',
        'opposite_taste': '⚡ Finding opposite-taste challenges...',
        'obscure': '🔍 Digging up obscure gems...',
        'artist_blind_spots': '🎭 Finding artist blind spots...'
    };
    const label = labels[mode] || labels['outside_zone'];
    showViewLoading('view-challenge', label);
    loadChallengesMode(mode);
}

async function loadChallengesMode(mode) {
    try {
        let url = '/api/challenges?count=24&mode=' + mode;
        if (mode === 'obscure') {
            url += '&popularity_threshold=' + currentPopularityThreshold;
        }
        const res = await fetch(url);
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
        let emptyMsg = '<p>🎉 You\'ve explored all our challenge songs! Come back later for new additions.</p>';
        if (mode === 'obscure' && data.popularity_min !== undefined) {
            emptyMsg = '<p>🔍 No songs found with popularity ≤ ' + currentPopularityThreshold + '/100.</p>' +
                '<p style="margin-top:8px;color:var(--text-muted)">The lowest popularity in our database is <strong>' + data.popularity_min + '/100</strong>. ' +
                'Try raising the slider to at least <strong>' + data.popularity_min + '</strong> to see results.</p>';
        }
        container.innerHTML = '<div class="challenge-empty">' + emptyMsg + '</div>';
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
        '🎯 Critically Acclaimed</button>' +
        '<button class="challenge-mode-btn' + (mode === 'opposite_taste' ? ' active' : '') + '" ' +
        'data-mode="opposite_taste" onclick="switchChallengeMode(\'opposite_taste\')">' +
        '⚡ Opposite Taste</button>' +
        '<button class="challenge-mode-btn' + (mode === 'obscure' ? ' active' : '') + '" ' +
        'data-mode="obscure" onclick="switchChallengeMode(\'obscure\')">' +
        '🔍 Obscure Gems</button>' +
        '<button class="challenge-mode-btn' + (mode === 'artist_blind_spots' ? ' active' : '') + '" ' +
        'data-mode="artist_blind_spots" onclick="switchChallengeMode(\'artist_blind_spots\')">' +
        '🎭 Artist Blind Spots</button>' +
        '</div>';

    // === Zone Info Banner ===
    const isOpposite = mode === 'opposite_taste';
    const isObscure = mode === 'obscure';
    const isArtistBlind = mode === 'artist_blind_spots';

    // === Popularity Threshold Slider (obscure mode only) ===
    if (isObscure) {
        html += '<div class="obscure-threshold-control">' +
            '<label class="threshold-label">Maximum popularity: <strong id="thresholdValue">' + currentPopularityThreshold + '</strong>/100</label>' +
            '<input type="range" id="obscureThreshold" class="threshold-slider" ' +
            'min="30" max="100" step="5" value="' + currentPopularityThreshold + '" ' +
            'oninput="updateThreshold(this.value)">' +
            '<div class="threshold-hints">' +
            '<span>30 · Ultra-obscure</span>' +
            '<span>65 · Hidden gems</span>' +
            '<span>100 · All songs</span>' +
            '</div></div>';
    }
    const lowestGenres = data.your_zones?.lowest_rated_genres || [];
    
    if (isObscure) {
        html += '<div class="challenge-zone-banner obscure-banner">' +
            '<div class="zone-banner-header">' +
            '<span class="zone-banner-icon">🔍</span>' +
            '<span>Obscure Gems · Songs with low popularity scores that most people haven\'t heard · ' +
            '<strong>' + data.total_available + '</strong> hidden gems available</span>' +
            '</div></div>';
    } else if (isArtistBlind) {
        html += '<div class="challenge-zone-banner artist-blind-banner">' +
            '<div class="zone-banner-header">' +
            '<span class="zone-banner-icon">🎭</span>' +
            '<span>Artist Blind Spots · Acclaimed songs from genres where you dislike specific artists · ' +
            '<strong>' + data.total_available + '</strong> blind spots available</span>' +
            '</div></div>';
    } else if (isOpposite) {
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
    if (isObscure) {
        html += '<div class="challenge-intro obscure-intro">' +
            '<p>These are <strong>critically acclaimed hidden gems</strong> — songs with low popularity scores that most people have never heard. ' +
            'Think of this as musical treasure hunting 🗺️ — acclaimed music that flew under the radar. ' +
            'Sorted by obscurity: the most unknown songs first.</p></div>';
    } else if (isArtistBlind) {
        html += '<div class="challenge-intro artist-blind-intro">' +
            '<p>These are <strong>acclaimed songs from artists you haven\'t tried</strong> — but in genres where you\'ve rated other artists low. ' +
            'Think of it as: "I don\'t like LMFAO, but maybe I\'d love Daft Punk" 🎭 — same genre, different artist. ' +
            'These songs are highly rated by critics and the public, even if your past experience in the genre was disappointing.</p></div>';
    } else if (isOpposite) {
        html += '<div class="challenge-intro opposite-intro">' +
            '<p>These are <strong>critically acclaimed masterpieces</strong> from genres you historically rate low. ' +
            'Think of this as musical vegetables 🥦 — universally beloved songs that might change your mind about a whole genre. ' +
            'You rated <strong>' + escapeHtml(lowestGenres.join(', ')) + '</strong> songs low on average. ' +
            'These are the absolute best that those genres have to offer.</p></div>';
    } else {
        html += '<div class="challenge-intro">' +
            '<p>These are songs widely considered masterpieces — but they fall outside your usual listening patterns. ' +
            'Each one is an <strong>acclaimed song challenge</strong>: music that billions of people love, waiting for you to discover.</p></div>';
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

            const extraHtml =
                '<div class="challenge-card-header">' +
                '<span class="challenge-tier-badge">' + outsideStr + ' Level ' + c.outside_score + '</span>' +
                '</div>' +
                '<div class="challenge-genre">' + escapeHtml(c.genre) + '</div>' +
                '<div class="challenge-acclaim">' + escapeHtml(c.acclaim) + '</div>' +
                '<div class="challenge-zone-note">' +
                '<span class="zone-note-icon">' + outsideStr + '</span> ' +
                escapeHtml(c.zone_note) + '</div>';

            html += songCard({
                artist: c.artist,
                song: c.song,
                year: c.year || null,
                genre: c.genre,
                reason: '',
                listened: c.listened,
                source: 'challenge',
                cardClass: 'challenge-card' + (isOppositeCard ? ' opposite-card' : ''),
                extraHtml: extraHtml,
            });
        });

        html += '</div></div>';
    }

    // === Stats Footer ===
    if (isObscure) {
        html += '<div class="challenge-footer obscure-footer">' +
            '<p>🔍 ' + challenges.length + ' obscure gems shown &middot; ' + data.total_available + ' total available &middot; ' +
            'Sorted by popularity score — lowest first. Songs that flew under the radar but are critically acclaimed.</p>' +
            '<button class="btn btn-outline" onclick="loadChallenges()" style="margin-top:12px">\ud83d\udd04 Refresh</button></div>';
    } else if (isArtistBlind) {
        html += '<div class="challenge-footer artist-blind-footer">' +
            '<p>🎭 ' + challenges.length + ' artist blind spots shown &middot; ' + data.total_available + ' total available &middot; ' +
            'Songs from genres where you dislike certain artists, but these are critically acclaimed alternatives.</p>' +
            '<button class="btn btn-outline" onclick="loadChallenges()" style="margin-top:12px">\ud83d\udd04 Refresh</button></div>';
    } else if (isOpposite) {
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

let _thresholdDebounce = null;
function updateThreshold(val) {
    currentPopularityThreshold = parseInt(val, 10);
    document.getElementById('thresholdValue').textContent = currentPopularityThreshold;
    // Debounce: reload after 300ms of no slider movement
    clearTimeout(_thresholdDebounce);
    _thresholdDebounce = setTimeout(function() {
        loadChallenges();
    }, 300);
}
