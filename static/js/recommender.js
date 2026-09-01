/**
 * recommender.js - Smart recommender view
 * Shows personalized song suggestions based on taste profile
 */

async function loadRecommender() {
    showViewLoading('view-recommender', '🎯 Generating recommendations...');
    try {
        const res = await fetch('/api/recommendations');
        const data = await res.json();
        hideViewLoading('view-recommender');
        renderRecommendations(data);
    } catch (err) {
        hideViewLoading('view-recommender');
        console.error('Recommender load error:', err);
        document.getElementById('recommendationsContainer').innerHTML = 
            '<div class="view-error"><span class="view-error-icon">⚠️</span><p>Failed to load recommendations</p><button class="btn btn-outline" onclick="loadRecommender()">Retry</button></div>';
    }
}

/**
 * Re-fetch the recommendation pool so freshly saved / ignored / listened songs
 * drop out and newly available ones surface. The pool includes more songs than
 * the first screenful, so refreshing genuinely turns up new picks.
 */
async function refreshRecommendations() {
    if (window.STATIC_MODE) {
        showToast('📄 Read-only snapshot — recommendations update when you re-push');
        return;
    }
    await loadRecommender();
    showToast('✨ Recommendations refreshed');
}

function renderRecommendations(data) {
    const container = document.getElementById('recommendationsContainer');
    if (!data || Object.keys(data).length === 0) {
        container.innerHTML = '<div class="loading-msg">No recommendations available yet. Keep rating songs!</div>';
        return;
    }

    let html = '';
    let totalShown = 0;
    for (const [category, catData] of Object.entries(data)) {
        const recs = catData.recommendations || [];
        totalShown += recs.length;
        html += `<div class="rec-category">
            <h3>${escapeHtml(category)}</h3>
            <div class="rec-grid">`;

        for (const rec of recs) {
            html += songCard({
                artist: rec.artist,
                song: rec.song,
                year: rec.year || null,
                reason: rec.reason,
                listened: rec.listened,
                source: 'recommender',
                cardClass: 'rec-card',
            });
        }

        // Let the user know when a category has nothing left to show.
        if (recs.length === 0) {
            html += '<div class="rec-empty">You\'ve covered everything here — hit 🔄 Fresh to pull in new picks.</div>';
        }

        html += `</div></div>`;
    }

    container.innerHTML = html;

    const note = document.getElementById('recPoolNote');
    if (note) note.textContent = `${totalShown} suggestions ready`;
}
