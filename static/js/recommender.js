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
            const artist_esc = escapeHtml(rec.artist);
            const song_esc = escapeHtml(rec.song);
            // escapeJsAttr: safe for single-quoted JS strings inside onclick.
            // escapeHtml would turn ' into &#039;, which the HTML parser decodes
            // back to ' inside the attribute — breaking songs like "He's a Pirate".
            const artist_js = escapeJsAttr(rec.artist);
            const song_js = escapeJsAttr(rec.song);
            // All recommendations returned by the API are unowned
            // (the backend filters owned songs out server-side)
            html += `<div class="rec-card">
                <div class="rec-artist">${artist_esc}</div>
                <div class="rec-song">“${song_esc}”</div>
                <div class="rec-reason">${escapeHtml(rec.reason)}</div>
                <div class="rec-actions">
                    <button class="rec-btn rec-btn-listen" onclick="searchSpotifyTrack('${artist_js}', '${song_js}')" title="Open on Spotify">&#9654; Listen</button>
                    ${listenedButtonHtml(rec.artist, rec.song, rec.listened)}
                    ${ignoreButtonHtml(rec.artist, rec.song)}
                    <button class="rec-btn rec-btn-add" onclick="quickAddFromRecommender('${artist_js}', '${song_js}', 'recommender')">+ Save</button>
                </div>
            </div>`;
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
