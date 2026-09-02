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

// ============================================================
// Reverse Me — opposite-taste recommendations
// ============================================================

let reverseMeVisible = false;
let reverseMeData = null;

async function toggleReverseMe() {
    const section = document.getElementById('reverseMeSection');
    reverseMeVisible = !reverseMeVisible;
    section.style.display = reverseMeVisible ? 'block' : 'none';
    document.getElementById('reverseMeBtn').classList.toggle('active', reverseMeVisible);
    
    if (reverseMeVisible && !reverseMeData) {
        await loadReverseMe();
    }
}

async function loadReverseMe() {
    const picksContainer = document.getElementById('reverseMePicks');
    const profileContainer = document.getElementById('reverseMeProfile');
    const descContainer = document.getElementById('reverseMeDescription');
    
    try {
        const res = await fetch('/api/reverse-me');
        if (!res.ok) throw new Error('Failed to load reverse me data');
        reverseMeData = await res.json();
        
        descContainer.textContent = reverseMeData.description || '';
        
        // Render inverted profile
        const profile = reverseMeData.inverted_profile || {};
        let profileHtml = '<div class="reverse-profile-grid">';
        
        if (profile.top_genres && profile.top_genres.length > 0) {
            profileHtml += '<div class="reverse-profile-section"><h4>Inverted Top Genres</h4><div class="reverse-genre-pills">';
            for (const g of profile.top_genres) {
                profileHtml += `<div class="reverse-genre-pill"><span class="reverse-genre-name">${escapeHtml(g.genre)}</span><span class="reverse-genre-avg">${g.inverted_avg}/100 → your ${g.your_avg}/100</span></div>`;
            }
            profileHtml += '</div></div>';
        }
        
        if (profile.favorite_artists && profile.favorite_artists.length > 0) {
            profileHtml += '<div class="reverse-profile-section"><h4>Inverted Favorite Artists</h4><div class="reverse-artist-list">';
            for (const a of profile.favorite_artists) {
                profileHtml += `<div class="reverse-artist-item"><span class="reverse-artist-name">${escapeHtml(a.name)}</span><span class="reverse-artist-rating">${a.inverted_rating}/100 → your ~${a.your_avg}/100</span></div>`;
            }
            profileHtml += '</div></div>';
        }
        
        if (reverseMeData.stats) {
            const s = reverseMeData.stats;
            profileHtml += `<div class="reverse-profile-section reverse-stats"><div class="reverse-stat"><span class="reverse-stat-val">${s.avg_rating}</span><span class="reverse-stat-lbl">Your Avg</span></div><div class="reverse-stat-arrow">→</div><div class="reverse-stat"><span class="reverse-stat-val">${s.reverse_avg}</span><span class="reverse-stat-lbl">Reverse Avg</span></div><div class="reverse-stat"><span class="reverse-stat-val">${s.songs_rated}</span><span class="reverse-stat-lbl">Songs Rated</span></div></div>`;
        }
        
        profileHtml += '</div>';
        profileContainer.innerHTML = profileHtml;
        
        // Render picks
        const picks = reverseMeData.picks || [];
        if (picks.length === 0) {
            picksContainer.innerHTML = '<div class="loading-msg">No reverse picks available</div>';
            return;
        }
        
        let html = '';
        for (const pick of picks) {
            html += songCard({
                artist: pick.artist,
                song: pick.song,
                year: pick.year || null,
                reason: pick.reason,
                source: 'reverse-me',
                cardClass: 'reverse-me-card',
            });
        }
        picksContainer.innerHTML = html;
        
    } catch (err) {
        console.error('Reverse me load error:', err);
        picksContainer.innerHTML = '<div class="loading-msg" style="color:var(--danger)">Failed to load reverse me data</div>';
    }
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
