/**
 * conquest.js - Year Conquest panel on dashboard
 * Shows top unreviewed songs per year, starting from 2011 going down.
 */

async function loadYearConquest() {
    const container = document.getElementById('conquestContent');
    if (!container) return;

    const startYear = document.getElementById('conquestStartYear')?.value || 2011;

    try {
        const res = await fetch(`/api/year-conquest?start_year=${startYear}&count=5`);
        if (!res.ok) throw new Error('Failed to load conquest data');
        const data = await res.json();
        renderYearConquest(data);
    } catch (err) {
        console.error('Year conquest error:', err);
        container.innerHTML = '<div class="loading-msg" style="color:var(--danger)">Error loading conquest data</div>';
    }
}

function renderYearConquest(data) {
    const container = document.getElementById('conquestContent');
    if (!container) return;

    const years = data.years || [];
    if (years.length === 0) {
        container.innerHTML = '<div class="loading-msg">No conquest data available</div>';
        return;
    }

    let html = '';

    for (const yearData of years) {
        const { year, songs, unreviewed_count, total_in_db } = yearData;

        if (songs.length === 0) {
            // All songs reviewed for this year!
            html += `
                <div class="conquest-year conquest-year-complete">
                    <div class="conquest-year-header">
                        <span class="conquest-year-label">${year}</span>
                        <span class="conquest-year-badge conquest-badge-done">✅ Conquered!</span>
                    </div>
                </div>
            `;
            continue;
        }

        html += `
            <div class="conquest-year">
                <div class="conquest-year-header">
                    <span class="conquest-year-label">${year}</span>
                    <span class="conquest-year-count">${songs.length} to go</span>
                </div>
                <div class="conquest-songs">
        `;

        for (const song of songs) {
            const stars = '★'.repeat(song.acclaim) + '☆'.repeat(5 - song.acclaim);
            html += `
                <div class="conquest-song">
                    <div class="conquest-song-info">
                        <span class="conquest-song-artist">${escapeHtml(song.artist)}</span>
                        <span class="conquest-song-title">${escapeHtml(song.song)}</span>
                    </div>
                    <div class="conquest-song-actions">
                        <span class="conquest-stars" title="Acclaim: ${song.acclaim}/5">${stars}</span>
                        <button class="btn btn-conquest-add" data-artist="${escapeHtml(song.artist)}" data-song="${escapeHtml(song.song)}" onclick="quickAddFromConquest(this.dataset.artist, this.dataset.song)" title="Add this song">+</button>
                    </div>
                </div>
            `;
        }

        html += '</div></div>';
    }

    container.innerHTML = html;
}

function quickAddFromConquest(artist, song) {
    // Open the quick-add modal pre-filled
    if (typeof openQuickAdd === 'function') {
        openQuickAdd();
        const artistInput = document.getElementById('qaArtist');
        const songInput = document.getElementById('qaSong');
        if (artistInput) artistInput.value = artist;
        if (songInput) songInput.value = song;
        // Auto-focus rating
        const ratingInput = document.getElementById('qaRating');
        if (ratingInput) ratingInput.focus();
    }
}
