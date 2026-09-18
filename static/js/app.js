/**
 * app.js - Main application initialization
 * Handles app startup, data loading, and keyboard shortcuts
 */

// ============================================================
// Keyboard shortcuts
// ============================================================
// NOTE: The number-key quick navigation (1-8 to jump to views) was REMOVED.
// It had no input guard, so typing digits into the quick-add modal (e.g. a
// rating like 85, or a song title containing numbers) hijacked view switching.
// The sidebar is easy enough to click. See DECISIONS.md for the full rationale.

// ============================================================
// CDN library failure flags
// ============================================================
// Chart.js and D3 are lazy-loaded on first view need (loadLib in utils.js,
// SRI-verified). A failed/timeout CDN load sets window.__chartjsFailed /
// window.__d3Failed via the loadLib().catch() handlers in each consumer,
// which permanently disable the affected charts for the session. Do NOT
// probe typeof Chart/d3 on a timer — with lazy loading "not loaded yet" is
// the normal state, not a failure.

// ============================================================
// Initialization
// ============================================================

async function initApp() {
    try {
        // Check Spotify status (non-blocking — failure is fine)
        const [spotRes, statsRes] = await Promise.all([
            fetch('/api/spotify-status').catch(() => null),
            fetch('/api/stats').catch(() => null)
        ]);

        // Spotify status badge
        if (spotRes && spotRes.ok) {
            try {
                const spotData = await spotRes.json();
                const statusText = document.querySelector('.spotify-status');
                if (statusText) {
                    statusText.innerHTML = spotData.available
                        ? '<span class="status-dot online"></span> Spotify: Connected'
                        : '<span class="status-dot offline"></span> Spotify: Not configured';
                }
            } catch (e) { /* ignore parse errors */ }
        }

        // Sidebar info
        let statsData = null;
        if (statsRes && statsRes.ok) {
            statsData = await statsRes.json();
            const dataInfo = document.getElementById('dataInfo');
            if (dataInfo) {
                dataInfo.innerHTML = `
                    ${statsData.rated_entries} songs · ${statsData.unique_artists} artists<br>
                    Avg ${statsData.avg_rating}/100
                `;
            }
        }

        // Load dashboard view — pass pre-fetched stats to avoid duplicate fetch
        await loadDashboard(statsData);

        // Hide loading screen
        document.getElementById('loadingScreen').classList.add('hidden');

        // Show welcome toast
        setTimeout(() => {
            showToast(`🎵 Welcome! Your taste profile is ready. Try the Recommender or Blind Spots!`);
        }, 500);

    } catch (err) {
        console.error('Init error:', err);
        const loading = document.getElementById('loadingScreen');
        if (loading) {
            // Use textContent to avoid XSS via error message (adversarial review finding)
            loading.innerHTML = '<div style="text-align:center;color:var(--danger)">' +
                '<div style="font-size:48px;margin-bottom:12px">⚠️</div>' +
                '<p>Error loading app. Check that the Flask server is running.</p>' +
                '<p style="font-size:12px;color:var(--text-muted);margin-top:8px"></p>' +
                '</div>';
            loading.querySelector('p:last-child').textContent = err.message;
        }
    }
}

// ============================================================
// Start
// ============================================================

document.addEventListener('DOMContentLoaded', () => {
    // Preload library-independent data immediately
    initApp();
    // Deep links / bookmarks: honor #view-name in the URL once the shell is up
    if (typeof applyHashView === 'function') applyHashView();
});
