/**
 * utils.js - Shared utility functions for all views
 * Must be loaded before all other JS files.
 */

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

    // Load view content
    switch (viewName) {
        case 'dashboard':
            if (!document.getElementById('statTotal')?.textContent || document.getElementById('statTotal')?.textContent === '-') {
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
                setTimeout(loadConstellation, 100);
            }
            break;
        case 'evolution':
            if (!window.evolutionData) {
                loadEvolution();
            }
            break;
        case 'weekly':
            if (!document.querySelector('#view-weekly .weekly-pick')) {
                loadWeekly();
            }
            break;
        case 'history':
            loadSongs(true);
            break;
        case 'challenge':
            if (!document.querySelector('#view-challenge .challenge-tier')) {
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
