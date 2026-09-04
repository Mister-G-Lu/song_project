/**
 * utils.js - Shared utility functions for all views
 * Must be loaded before all other JS files.
 *
 * Standardized helpers to reduce duplication and improve testability.
 * Every view should use these instead of redefining tooltip configs,
 * badge classes, error HTML, or spotify search logic.
 */

// ============================================================
// HTML & Display Helpers
// ============================================================

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Escape a string for safe embedding inside a SINGLE-QUOTED JS string
 * literal that lives in an inline onclick attribute:
 *   onclick="quickAddFromRecommender('${escapeJsAttr(x)}', ...)"
 *
 * Why not escapeHtml()? escapeHtml turns ' into &#039;, but the HTML parser
 * decodes &#039; back to ' INSIDE the attribute before the JS engine runs,
 * so a title like "He's a Pirate" produces a broken JS string literal and
 * the click handler dies with a silent SyntaxError.
 *
 * This escapes for the JS layer (backslash, apostrophe, newlines) and then
 * for the HTML attribute layer (&, ", <, >) — order matters: & first so the
 * entities we introduce ("&quot;") aren't re-escaped.
 */
function escapeJsAttr(text) {
    if (text === null || text === undefined) return '';
    return String(text)
        .replace(/&/g, '&amp;')
        .replace(/"/g, '&quot;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/\\/g, '\\\\')
        .replace(/'/g, "\\'")
        .replace(/\r\n/g, '\\n')
        .replace(/\n/g, '\\n')
        .replace(/\r/g, '\\r')
        .replace(/\u2028/g, '\\u2028')
        .replace(/\u2029/g, '\\u2029');
}

function showToast(message) {
    const toast = document.getElementById('toast');
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add('show');
    
    clearTimeout(toast._hideTimeout);
    toast._hideTimeout = setTimeout(() => {
        toast.classList.remove('show');
    }, 3000);
}

/**
 * Return the rating badge CSS class for a numeric rating.
 * Standardizes 'perfect' | 'high' | 'good' | 'ok' | 'low' across all views.
 */
function getRatingClass(rating) {
    if (rating === null || rating === undefined) return '';
    if (rating >= 90) return 'perfect';
    if (rating >= 80) return 'high';
    if (rating >= 70) return 'good';
    if (rating >= 60) return 'ok';
    return 'low';
}

/**
 * Return the CSS variable string for a numeric rating (for inline `color:`).
 * Companion to getRatingClass() — use this when you need the color value
 * directly (e.g. inline styles in dynamically built HTML) rather than a
 * class name.
 */
function getRatingColor(rating) {
    if (rating === null || rating === undefined) return 'var(--text-muted)';
    if (rating >= 95) return 'var(--rating-100)';
    if (rating >= 90) return 'var(--rating-90)';
    if (rating >= 80) return 'var(--rating-80)';
    if (rating >= 70) return 'var(--rating-70)';
    return 'var(--text-muted)';
}

/**
 * Render a standardized error view with retry button.
 * @param {HTMLElement} container - DOM element to fill
 * @param {string} message - Error message to display
 * @param {function} retryFn - Function to call on retry click
 */
function renderErrorView(container, message, retryFn) {
    const retryAttr = retryFn ? ` onclick="(${retryFn.name})()"` : '';
    container.innerHTML = `
        <div class="view-error">
            <span class="view-error-icon">⚠️</span>
            <p>${escapeHtml(message || 'Failed to load')}</p>
            ${retryFn ? '<button class="btn btn-outline"' + retryAttr + '>Retry</button>' : ''}
        </div>`;
}

// ============================================================
// CSS Variable Reader
// ============================================================

/**
 * Read a CSS custom property value from :root.
 * Returns the raw string (e.g. '#7c5cfc'), or the fallback if not found.
 */
function cssVar(name, fallback) {
    try {
        const val = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
        return val || fallback || '';
    } catch (e) {
        return fallback || '';
    }
}

/**
 * Convenience: wrap an rgba() call with CSS variable RGB components.
 * cssVarRgb('--accent-rgb', 0.15) → 'rgba(124, 92, 252, 0.15)'
 */
function cssVarRgb(name, alpha) {
    const rgb = cssVar(name, '0, 0, 0');
    return `rgba(${rgb}, ${alpha})`;
}

/**
 * Pre-resolved palette — read once on initial pageload.
 * Other JS files use PALETTE.xxx instead of hardcoded hex.
 */
const PALETTE = (function() {
    // Wait until DOM is ready, then snapshot all CSS vars
    const r = getComputedStyle(document.documentElement);
    function g(n) { return (r.getPropertyValue(n) || '').trim(); }
    return {
        bgCard:        g('--bg-card')        || '#1a1a28',
        textPrimary:   g('--text-primary')   || '#e8e8f0',
        textSecondary: g('--text-secondary') || '#9090a8',
        textMuted:     g('--text-muted')     || '#606078',
        borderColor:   g('--border-color')   || '#2a2a3e',
        accent:        g('--accent')         || '#7c5cfc',
        accentLight:   g('--accent-light')   || '#9b7fff',
        success:       g('--success')        || '#34d399',
        warning:       g('--warning')        || '#fbbf24',
        danger:        g('--danger')         || '#f87171',
        rating100:     g('--rating-100')     || '#ff6b6b',
        rating90:      g('--rating-90')      || '#ffd43b',
        rating80:      g('--rating-80')      || '#69db7c',
        rating70:      g('--rating-70')      || '#74c0fc',
        ratingLow:     g('--rating-low')     || '#868e96',
        white:         g('--white')          || '#ffffff',
        bgPrimary:     g('--bg-primary')     || '#0a0a0f',
        // For Chart.js — visually distinct data-vis colors (not theme colors).
        // These are intentionally static because they need to be distinguishable
        // from each other, not synced to CSS theme variables.
        chartColors: [
            '#f87171', '#fb923c', '#fbbf24', '#a3e635', '#34d399', '#22d3ee'
        ]
    };
})();

// ============================================================
// Chart.js Helpers
// ============================================================

/**
 * Shared Chart.js tooltip / scale theme config.
 * Reads CSS variables from PALETTE so charts stay in sync with variables.css.
 * Use spread: options: { ...CHART_THEME, ... }
 */
const CHART_THEME = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
        legend: { display: false },
        tooltip: {
            backgroundColor: PALETTE.bgCard,
            titleColor: PALETTE.textPrimary,
            bodyColor: PALETTE.textSecondary,
            borderColor: PALETTE.borderColor,
            borderWidth: 1,
        }
    },
    scales: {
        y: {
            grid: { color: PALETTE.borderColor + '30' },
            ticks: { color: PALETTE.textMuted, font: { size: 11 } }
        },
        x: {
            grid: { display: false },
            ticks: { color: PALETTE.textMuted, font: { size: 11 } }
        }
    }
};

// ============================================================
// Spotify Search
// ============================================================

async function searchSpotifyTrack(artist, song) {
    // Static snapshot: no Spotify API backend — jump straight to a Spotify
    // search URL (no API key needed) instead of the /api/search-spotify route.
    if (await staticModePromise) {
        const q = encodeURIComponent(`${artist} ${song}`);
        window.open(`https://open.spotify.com/search/${q}`, '_blank');
        showToast(`Opening Spotify search for "${song}" by ${artist}`);
        return;
    }
    try {
        const res = await fetch(`/api/search-spotify?title=${encodeURIComponent(song)}&artist=${encodeURIComponent(artist)}`);
        const data = await res.json();
        
        if (data && data.external_url) {
            window.open(data.external_url, '_blank');
            showToast(`Opening "${song}" by ${artist} on Spotify`);
        } else if (data && data.error) {
            showToast(`Spotify not configured. Try searching manually.`);
        } else {
            // Try searching just the song name
            const res2 = await fetch(`/api/search-spotify?title=${encodeURIComponent(song + ' ' + artist)}`);
            const data2 = await res2.json();
            if (data2 && data2.external_url) {
                window.open(data2.external_url, '_blank');
                showToast(`Opening "${song}" on Spotify`);
            } else {
                showToast(`Couldn't find on Spotify. Try a direct search.`);
            }
        }
    } catch (err) {
        showToast('Spotify search unavailable');
    }
}

/**
 * Show a loading overlay inside a specific view.
 * @param {string} viewId - e.g. 'view-constellation'
 * @param {string} message - optional loading message
 */
function showViewLoading(viewId, message) {
    const view = document.getElementById(viewId);
    if (!view) return;
    // Remove existing overlay
    const existing = view.querySelector('.view-loading-overlay');
    if (existing) existing.remove();
    
    const overlay = document.createElement('div');
    overlay.className = 'view-loading-overlay';
    overlay.innerHTML = `
        <div class="view-loading-spinner"></div>
        <p class="view-loading-text">${message || 'Loading...'}</p>
    `;
    view.appendChild(overlay);
}

/**
 * Hide the loading overlay for a view.
 */
function hideViewLoading(viewId) {
    const view = document.getElementById(viewId);
    if (!view) return;
    const overlay = view.querySelector('.view-loading-overlay');
    if (overlay) overlay.remove();
}

/**
 * All valid view names. Shared with app.js for keyboard shortcuts.
 */
const VALID_VIEWS = ['dashboard', 'discover', 'recommender', 'blindspots', 'outliers', 'constellation', 'evolution', 'weekly', 'history', 'challenge'];
// 'outliers', 'weekly' and 'challenge' are legacy ids kept so old links/bookmarks still resolve.

function switchView(viewName) {
    if (!VALID_VIEWS.includes(viewName)) {
        console.warn(`switchView: unknown view "${viewName}"`);
        return;
    }

    // Update nav
    document.querySelectorAll('.nav-item').forEach(el => {
        el.classList.toggle('active', el.dataset.view === viewName);
    });

    // Update view
    document.querySelectorAll('.view').forEach(el => {
        el.classList.remove('active');
    });
    const targetView = document.getElementById(`view-${viewName}`);
    if (targetView) {
        targetView.classList.add('active');
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    // Load view content — show loading overlay BEFORE async fetch
    switch (viewName) {
        case 'dashboard':
            if (!document.getElementById('statTotal')?.textContent || document.getElementById('statTotal')?.textContent === '-') {
                showViewLoading('view-dashboard', 'Loading dashboard...');
                loadDashboard();
            }
            break;
        case 'discover':
            if (discoverTab === 'challenge') {
                if (!document.querySelector('#challengeContent .challenge-tier')) loadChallenges();
            } else if (!document.querySelector('#view-discover .discover-card')) {
                loadDiscover();
            }
            break;
        case 'recommender':
            if (!document.querySelector('#view-recommender .rec-category')) {
                loadRecommender();
            }
            break;
        case 'blindspots':
            if (!document.querySelector('#view-blindspots .spot-card')) {
                loadBlindSpots();
            }
            break;
        case 'outliers':
            // Outliers now live at the bottom of dashboard — switch to dashboard and scroll
            switchView('dashboard');
            setTimeout(() => {
                const panel = document.getElementById('outliersPanel');
                if (panel) panel.scrollIntoView({ behavior: 'smooth' });
            }, 200);
            return;
        case 'constellation':
            if (!document.querySelector('#constellationSvg circle')) {
                showViewLoading('view-constellation', 'Loading constellation...');
                setTimeout(loadConstellation, 100);
            }
            break;
        case 'evolution':
            if (!window.evolutionData) {
                showViewLoading('view-evolution', 'Loading evolution...');
                loadEvolution();
            }
            break;
        case 'weekly':
            // Legacy: the Weekly view was folded into Discover.
            switchView('discover');
            return;
        case 'challenge':
            // Legacy: Challenges are now the "Out of your zone" tab on Discover.
            switchView('discover');
            setDiscoverTab('challenge');
            return;
        case 'history':
            showViewLoading('view-history', 'Loading history...');
            loadSongs(true);
            break;
    }
}

/**
 * After adding a song, refresh ALL recommendation views that are currently visible
 * so the newly saved song disappears from recs/challenges/weekly/blindspots/etc.
 * Called from submitQuickAdd() in quickadd.js after any successful add.
 */
function refreshActiveViews() {
    const viewMap = [
        { id: 'dashboard', check: '#topArtistsTable', loadFn: () => loadDashboard() },
        { id: 'discover', check: '.discover-card', loadFn: () => loadDiscover() },
        { id: 'discover', check: '#challengeContent .challenge-tier', loadFn: loadChallenges },
        { id: 'recommender', check: '.rec-category', loadFn: loadRecommender },
        { id: 'blindspots', check: '.spot-card', loadFn: loadBlindSpots },
        { id: 'dashboard', check: '#outliersPanel .outlier-card', loadFn: loadOutliers },
        { id: 'constellation', check: null, dataVar: 'constellationData', loadFn: loadConstellation },
        { id: 'evolution', check: null, dataVar: 'evolutionData', loadFn: loadEvolution },
    ];

    for (const view of viewMap) {
        const viewEl = document.getElementById('view-' + view.id);
        if (!viewEl || !viewEl.classList.contains('active')) continue;

        // Only refresh views that have previously loaded content
        let hasContent = false;
        if (view.check) {
            hasContent = !!viewEl.querySelector(view.check);
        } else if (view.dataVar) {
            hasContent = !!window[view.dataVar];
        }

        if (hasContent) {
            // Brief delay so the add/save finishes before re-fetching
            setTimeout(() => view.loadFn(), 300);
        }
    }
}

/**
 * Fetch JSON from an API endpoint with error handling.
 */
async function apiFetch(url) {
    try {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return await res.json();
    } catch (err) {
        console.error(`API fetch error (${url}):`, err);
        throw err;
    }
}

// ============================================================
// Listened tracking (live app only)
// ============================================================

/**
 * Set a listened-toggle button's visual state.
 * @param {HTMLButtonElement} btn
 * @param {boolean} listened
 */
function setListenedButton(btn, listened) {
    btn.classList.toggle('is-listened', listened);
    btn.textContent = listened ? '✓ Listened' : 'Mark Listened';
    btn.title = listened ? 'Mark as not listened' : 'Mark as listened';
}

/**
 * Toggle the listened state of a recommended song from a card button.
 * Optimistically flips the button, then reverts on failure.
 * @param {HTMLButtonElement} btn - the clicked button
 * @param {string} artist - artist name
 * @param {string} song - song title
 * @param {boolean} wasListened - state before this click
 */
async function toggleListenedButton(btn, artist, song, wasListened) {
    if (window.STATIC_MODE) {
        showToast('📄 Read-only snapshot — listened tracking needs the live app');
        return;
    }
    const now = !wasListened;
    btn.classList.add('is-busy');
    try {
        const res = await fetch('/api/mark-listened', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ artist, song, listened: now })
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        setListenedButton(btn, now);
        showToast(now ? `✓ Marked “${song}” as listened` : `“${song}” marked as not listened`);
    } catch (err) {
        console.error('mark-listened error:', err);
        // Keep the button reflecting reality (wasListened) on failure.
        setListenedButton(btn, wasListened);
        showToast('Failed to update listened state');
    } finally {
        btn.classList.remove('is-busy');
    }
}

/**
 * Build the HTML for a listened-toggle button on a rec/weekly/challenge card.
 * @param {string} artist
 * @param {string} song
 * @param {boolean} listened
 */
function listenedButtonHtml(artist, song, listened) {
    const artist_js = escapeJsAttr(artist);
    const song_js = escapeJsAttr(song);
    const label = listened ? '✓ Listened' : 'Mark Listened';
    const cls = listened ? 'rec-btn rec-btn-listened is-listened' : 'rec-btn rec-btn-listened';
    return `<button class="${cls}" onclick="toggleListenedButton(this, '${artist_js}', '${song_js}', ${!!listened})" title="${listened ? 'Mark as not listened' : 'Mark as listened'}">${label}</button>`;
}

/**
 * Ignore a suggested song: adds it to the ban list so it never appears in
 * recommendations, weekly picks, or challenges again, then removes its card.
 * This is the app's "hide this song" (Spotify) / "ban" (Last.fm) equivalent —
 * the ban list is persisted in data/ban_list.json and respected by every
 * suggestion source (see TasteEngine._is_banned).
 */
async function ignoreSong(btn, artist, song) {
    if (window.STATIC_MODE) {
        showToast('📄 Read-only snapshot — ignoring songs needs the live app');
        return;
    }
    btn.classList.add('is-busy');
    try {
        const res = await fetch('/api/ban-list/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ type: 'songs', value: `${artist} – ${song}` })
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        // Remove the card from the current view.
        const card = btn.closest('.song-card');
        if (card) card.remove();
        showToast(`🚫 “${song}” ignored — won't be suggested again`);
    } catch (err) {
        console.error('ignore-song error:', err);
        btn.classList.remove('is-busy');
        showToast('Failed to ignore song');
    }
}

/**
 * Build the HTML for the red Ignore button on a rec/weekly/challenge card.
 * @param {string} artist
 * @param {string} song
 */
function ignoreButtonHtml(artist, song) {
    const artist_js = escapeJsAttr(artist);
    const song_js = escapeJsAttr(song);
    return `<button class="rec-btn rec-btn-ignore" onclick="ignoreSong(this, '${artist_js}', '${song_js}')" title="Never suggest this song again">&#10005; Ignore</button>`;
}

// ============================================================
// Shared Song Card Component
// ============================================================
/**
 * Render a standardized song suggestion card.
 * Used by Recommender, Weekly, Challenges, and Conquest views.
 *
 * @param {Object} opts
 * @param {string} opts.artist - Artist name
 * @param {string} opts.song  - Song title
 * @param {number|null} opts.year - Release year (shown as badge)
 * @param {string}  [opts.genre]    - Genre badge
 * @param {string}  [opts.reason]   - Why-this-song blurb
 * @param {boolean} [opts.listened] - Whether already marked listened
 * @param {string}  [opts.source]   - 'recommender'|'weekly'|'challenge'|'conquest'
 * @param {string}  [opts.cardClass] - Extra CSS class(es) on the card wrapper
 * @param {string}  [opts.extraHtml] - Arbitrary HTML appended inside the card
 * @param {string}  [opts.cover]    - Album art URL (rendered as a thumbnail)
 * @param {number}  [opts.deezerId] - Deezer track id → enables the 30s Preview button
 * @param {boolean} [opts.showActions=true] - Render action buttons
 * @returns {string} HTML string
 */
function songCard(opts) {
    const {
        artist = '',
        song = '',
        year = null,
        genre = '',
        reason = '',
        listened = false,
        source = 'recommender',
        cardClass = '',
        extraHtml = '',
        showActions = true,
        cover = '',
        deezerId = null,
    } = opts || {};

    const artist_esc  = escapeHtml(artist);
    const song_esc    = escapeHtml(song);
    const artist_js   = escapeJsAttr(artist);
    const song_js     = escapeJsAttr(song);
    const genre_esc   = escapeHtml(genre);
    const reason_esc  = escapeHtml(reason);

    const yearBadge = year
        ? `<span class="song-year-badge">${escapeHtml(String(year))}</span>`
        : '';
    const genreBadge = genre
        ? `<span class="song-genre-badge">${genre_esc}</span>`
        : '';

    const previewBtn = deezerId
        ? `<button class="rec-btn rec-btn-preview" onclick="togglePreview(this, ${parseInt(deezerId, 10)})" title="Play a 30-second preview">&#9654; Preview</button>`
        : '';
    const coverHtml = cover
        ? `<img class="song-cover" src="${escapeHtml(cover)}" alt="" loading="lazy">`
        : '';

    const actionsHtml = showActions ? `
        <div class="song-actions">
            ${previewBtn}
            <button class="rec-btn rec-btn-listen"
                onclick="searchSpotifyTrack('${artist_js}', '${song_js}')"
                title="Open on Spotify">${deezerId ? 'Spotify' : '&#9654; Listen'}</button>
            ${listenedButtonHtml(artist, song, listened)}
            ${ignoreButtonHtml(artist, song)}
            <button class="rec-btn rec-btn-add"
                onclick="quickAddFromRecommender('${artist_js}', '${song_js}', '${escapeJsAttr(source)}')">+ Save</button>
        </div>
    ` : '';

    return `
        <div class="song-card ${cardClass}${cover ? ' has-cover' : ''}">
            ${coverHtml}
            <div class="song-card-meta">
                ${yearBadge}${genreBadge}
            </div>
            <div class="song-artist">${artist_esc}</div>
            <div class="song-title">“${song_esc}”</div>
            ${reason ? `<div class="song-reason">${reason_esc}</div>` : ''}
            ${extraHtml}
            ${actionsHtml}
        </div>
    `;
}

// ============================================================
// Static snapshot mode (GitHub Pages)
// ============================================================
// scripts/export_static.py pre-computes every read-only API endpoint into
// data/api/*.json. When the page is served from that snapshot (detected by the
// presence of data/config.json), a thin fetch wrapper maps the same `/api/...`
// URLs to those files so all views work with zero per-view changes.
// History pagination/search is served client-side from the full songs dump.

/**
 * Map a static API path + query to its snapshot JSON file (relative to page).
 * Pure function — kept separate for testability.
 * @param {string} path - e.g. '/api/stats'
 * @param {URLSearchParams} params - query params from the original URL
 * @returns {string} relative file path, e.g. 'data/api/stats.json'
 */
function staticApiFile(path, params) {
    if (path === '/api/challenges') {
        // Both challenge modes are snapshotted separately.
        return params.get('mode') === 'opposite_taste'
            ? 'data/api/challenges-opposite.json'
            : 'data/api/challenges.json';
    }
    if (path === '/api/discover') {
        // One snapshot per mode; a seeded explore falls back to that mode's file.
        const mode = ['easy', 'medium', 'hard'].includes(params.get('mode')) ? params.get('mode') : 'easy';
        return `data/api/discover-${mode}.json`;
    }
    if (path === '/api/songs' || path === '/api/search-history') {
        // Served client-side from the full dump (see staticSongsResponse).
        return 'data/api/songs.json';
    }
    return 'data/api/' + path.replace('/api/', '') + '.json';
}

/** Promise that resolves true when this page is a static snapshot. */
const staticModePromise = (async () => {
    try {
        const res = await window.fetch('data/config.json');
        if (!res.ok) return false;
        const cfg = await res.json();
        return !!(cfg && cfg.mode === 'static');
    } catch (e) {
        return false;
    }
})();

// Cache of the full songs dump (data/api/songs.json), loaded lazily.
let staticSongsCache = null;
async function staticSongsData() {
    if (!staticSongsCache) {
        const res = await window.fetch('data/api/songs.json');
        staticSongsCache = res.ok ? await res.json() : { songs: [] };
    }
    return staticSongsCache;
}

function _staticJsonResponse(data, status) {
    return new Response(JSON.stringify(data), {
        status: status || 200,
        headers: { 'Content-Type': 'application/json' },
    });
}

/**
 * Serve /api/songs entirely client-side: filter, sort, paginate the dump
 * exactly like the Flask endpoint does.
 */
async function staticSongsResponse(params) {
    const all = await staticSongsData();
    // Match the Flask /api/songs endpoint, which only lists rated entries.
    let list = all.songs.filter(s => s.rating != null);

    const search = (params.get('search') || '').toLowerCase();
    if (search) {
        list = list.filter(s => (s.title || '').toLowerCase().includes(search));
    }
    const minRating = params.get('min_rating');
    if (minRating) {
        const min = parseInt(minRating, 10) || 0;
        list = list.filter(s => (s.rating || 0) >= min);
    }

    const sortBy = params.get('sort') || 'rating';
    const order = params.get('order') || 'desc';
    const reverse = order === 'desc';
    // Flask sorts ratings as ints (0 for unrated); mirror by coercing nulls to 0.
    const num = v => (typeof v === 'number' ? v : (v == null ? 0 : v));
    list.sort((a, b) => {
        const av = num(a[sortBy]);
        const bv = num(b[sortBy]);
        if (typeof av === 'number' && typeof bv === 'number') {
            return reverse ? bv - av : av - bv;
        }
        const as = String(a[sortBy] == null ? '' : a[sortBy]);
        const bs = String(b[sortBy] == null ? '' : b[sortBy]);
        return reverse ? bs.localeCompare(as) : as.localeCompare(bs);
    });

    const offset = parseInt(params.get('offset') || '0', 10) || 0;
    const limit = parseInt(params.get('limit') || '50', 10) || 50;
    const page = list.slice(offset, offset + limit).map(s => ({
        ...s,
        rating: s.rating || 0, // live endpoint reports 0 for unrated
    }));
    return _staticJsonResponse({ songs: page, total: list.length });
}

/** Serve /api/search-history client-side, mirroring the Flask handler. */
async function staticSearchResponse(params) {
    const all = await staticSongsData();
    const q = (params.get('q') || '').toLowerCase();
    const matched = all.songs.filter(s =>
        (s.title || '').toLowerCase().includes(q) ||
        (s.preview || '').toLowerCase().includes(q)
    );
    const results = matched.slice(0, 30).map(s => ({
        title: (s.title || '').slice(0, 80),
        rating: s.rating,
        date: s.date || '',
        preview: (s.preview || '').slice(0, 300),
    }));
    return _staticJsonResponse({ results, total: matched.length });
}

/**
 * Install the fetch shim synchronously at parse time (utils.js loads first),
 * so even the very first /api/ fetch from app.js is routed correctly once
 * static mode is confirmed.
 */
const _realFetch = window.fetch.bind(window);
window.fetch = function (input, init) {
    if (typeof input === 'string' && input.startsWith('/api/')) {
        return staticModePromise.then(staticMode => {
            if (!staticMode) return _realFetch(input, init);

            const method = (init && init.method) || 'GET';
            if (method !== 'GET') {
                // Read-only snapshot — write actions are guarded in the UI too.
                return _staticJsonResponse(
                    { error: 'Read-only snapshot — this action requires the local app.' },
                    501
                );
            }

            const [path, query] = input.split('?');
            const params = new URLSearchParams(query || '');
            if (path === '/api/songs') return staticSongsResponse(params);
            if (path === '/api/search-history') return staticSearchResponse(params);
            return _realFetch(staticApiFile(path, params));
        });
    }
    return _realFetch(input, init);
};

/** Apply read-only UI once static mode is confirmed (runs at load time). */
staticModePromise.then(staticMode => {
    if (!staticMode) return;
    window.STATIC_MODE = true;

    const fab = document.getElementById('fabButton');
    if (fab) fab.style.display = 'none';
    const hint = document.getElementById('shortcutHint');
    if (hint) hint.style.display = 'none';

    const banner = document.createElement('div');
    banner.className = 'static-banner';
    banner.innerHTML = '📄 <strong>Read-only snapshot</strong> — data is frozen at build time. ' +
        'Add or rate songs in your local app, then re-push to update this site.';
    // Insert inside #mainContent (not body): body is a flex container and the
    // sidebar is position:fixed, so a body.firstChild banner would overlap the
    // sidebar. mainContent starts past the 240px sidebar, keeping nav clickable.
    const mainContent = document.getElementById('mainContent');
    if (mainContent) {
        mainContent.insertBefore(banner, mainContent.firstChild);
    } else {
        document.body.insertBefore(banner, document.body.firstChild);
    }
});
