/**
 * app.js - Main application initialization
 * Handles app startup, data loading, and keyboard shortcuts
 */

// ============================================================
// Keyboard shortcuts
// ============================================================

document.addEventListener('keydown', (e) => {
    if (e.ctrlKey || e.metaKey) return;
    
    const views = ['dashboard', 'recommender', 'blindspots', 'constellation', 'evolution', 'weekly', 'history', 'challenge'];
    const num = parseInt(e.key);
    if (num >= 1 && num <= 8) {
        switchView(views[num - 1]);
        e.preventDefault();
    }
});

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
                if (spotData.available) {
                    statusText.innerHTML = '<span class="status-dot online"></span> Spotify: Connected';
                } else {
                    statusText.innerHTML = '<span class="status-dot offline"></span> Spotify: Not configured';
                }
            } catch (e) { /* ignore parse errors */ }
        }

        // Sidebar info
        if (statsRes && statsRes.ok) {
            const statsData = await statsRes.json();
            document.getElementById('dataInfo').innerHTML = `
                ${statsData.rated_entries} songs · ${statsData.unique_artists} artists<br>
                Avg ${statsData.avg_rating}/100
            `;
        }

        // Load dashboard view
        await loadDashboard();

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
            loading.innerHTML = `
                <div style="text-align:center;color:var(--danger)">
                    <div style="font-size:48px;margin-bottom:12px">⚠️</div>
                    <p>Error loading app. Check that the Flask server is running.</p>
                    <p style="font-size:12px;color:var(--text-muted);margin-top:8px">${err.message}</p>
                </div>
            `;
        }
    }
}

// ============================================================
// Start
// ============================================================

document.addEventListener('DOMContentLoaded', () => {
    // Preload library-independent data immediately
    initApp();
});
