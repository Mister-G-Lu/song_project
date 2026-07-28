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

function renderRecommendations(data) {
    const container = document.getElementById('recommendationsContainer');
    if (!data || Object.keys(data).length === 0) {
        container.innerHTML = '<div class="loading-msg">No recommendations available yet. Keep rating songs!</div>';
        return;
    }

    let html = '';
    for (const [category, catData] of Object.entries(data)) {
        html += `<div class="rec-category">
            <h3>${escapeHtml(category)}</h3>
            <div class="rec-grid">`;

        for (const rec of (catData.recommendations || [])) {
            const artist_esc = escapeHtml(rec.artist);
            const song_esc = escapeHtml(rec.song);
            const owned = rec.already_owned;
            const ownedBadge = owned ? '<span class="owned-badge">Already in collection</span>' : '';
            const addDisabled = owned ? ' disabled' : '';
            const addTitle = owned ? 'You already have this song in your collection' : 'Add to your collection';
            html += `<div class="rec-card${owned ? ' rec-card-owned' : ''}">
                ${ownedBadge}
                <div class="rec-artist">${artist_esc}</div>
                <div class="rec-song">“${song_esc}”</div>
                <div class="rec-reason">${escapeHtml(rec.reason)}</div>
                <div class="rec-actions">
                    <button class="rec-btn rec-btn-listen" onclick="searchSpotifyTrack('${artist_esc}', '${song_esc}')" title="Open on Spotify">&#9654; Listen</button>
                    <button class="rec-btn rec-btn-add" onclick="quickAddFromRecommender('${artist_esc}', '${song_esc}')" title="${addTitle}"${addDisabled}>+ Save</button>
                </div>
            </div>`;
        }

        html += `</div></div>`;
    }

    container.innerHTML = html;
}

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
