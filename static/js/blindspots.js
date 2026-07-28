/**
 * blindspots.js - Genre blind spots explorer
 */

async function loadBlindSpots() {
    showViewLoading('view-blindspots', '🔍 Exploring your blind spots...');
    try {
        const res = await fetch('/api/blind-spots');
        const data = await res.json();
        hideViewLoading('view-blindspots');
        renderTopGenres(data.top_loved_genres);
        renderBlindSpots(data.blind_spots);
    } catch (err) {
        hideViewLoading('view-blindspots');
        console.error('Blind spots load error:', err);
        renderErrorView(document.getElementById('blindspotsGrid'), 'Failed to load blind spots', loadBlindSpots);
    }
}

function renderTopGenres(genres) {
    const container = document.getElementById('topGenrePills');
    if (!genres || genres.length === 0) {
        container.innerHTML = '<span class="table-placeholder">No genre data available</span>';
        return;
    }

    let html = '';
    genres.forEach(([genre, avg, count]) => {
        html += `<span class="genre-pill">
            ${escapeHtml(genre)}
            <span class="pill-rating">${avg}</span>
            <span style="font-size:11px;color:var(--text-muted)">(${count} songs)</span>
        </span>`;
    });
    container.innerHTML = html;
}

function renderBlindSpots(spots) {
    const container = document.getElementById('blindspotsGrid');
    if (!spots || Object.keys(spots).length === 0) {
        container.innerHTML = '<div class="loading-msg">No blind spots identified yet.</div>';
        return;
    }

    let html = '';
    for (const [genre, info] of Object.entries(spots)) {
        html += `<div class="spot-card">
            <h4>${escapeHtml(genre)}</h4>
            <div class="spot-why">${escapeHtml(info.why || info.why_you || '')}</div>
            <div class="spot-expect">Expected enjoyment: ${info.expected_rating || '?'}</div>
            <div class="spot-artists">🎯 ${escapeHtml(info.suggestion || '')}</div>
        </div>`;
    }
    container.innerHTML = html;
}
