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
// Chart.js Helpers
// ============================================================

/**
 * Shared Chart.js tooltip / scale theme config.
 * Use spread: options: { ...CHART_THEME, ... }
 */
const CHART_THEME = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
        legend: { display: false },
        tooltip: {
            backgroundColor: '#1a1a28',
            titleColor: '#e8e8f0',
            bodyColor: '#9090a8',
            borderColor: '#2a2a3e',
            borderWidth: 1,
        }
    },
    scales: {
        y: {
            grid: { color: '#2a2a3e30' },
            ticks: { color: '#606078', font: { size: 11 } }
        },
        x: {
            grid: { display: false },
            ticks: { color: '#606078', font: { size: 11 } }
        }
    }
};

// ============================================================
// Spotify Search
// ============================================================

async function searchSpotifyTrack(artist, song) {
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

function switchView(viewName) {
    const validViews = ['dashboard', 'recommender', 'blindspots', 'constellation', 'evolution', 'weekly', 'history', 'challenge'];
    if (!validViews.includes(viewName)) {
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
            if (!document.querySelector('#view-weekly .weekly-pick')) {
                loadWeekly();
            }
            break;
        case 'history':
            showViewLoading('view-history', 'Loading history...');
            loadSongs(true);
            break;
        case 'challenge':
            if (!document.querySelector('#view-challenge .challenge-tier')) {
                showViewLoading('view-challenge', 'Loading challenges...');
                loadChallenges();
            }
            break;
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
