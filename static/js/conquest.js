/**
 * conquest.js - Year Conquest panel on dashboard
 * Groups years into collapsible decades, showing top unreviewed songs per year.
 */

async function loadYearConquest() {
    const container = document.getElementById('conquestContent');
    if (!container) return;

    const startDecade = document.getElementById('conquestStartDecade')?.value || '2010';

    try {
        const res = await fetch(`/api/year-conquest?start_year=${startDecade}9&count=5`);
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

    // Group years into decades
    const decades = {};
    for (const yearData of years) {
        const decade = Math.floor(yearData.year / 10) * 10;
        if (!decades[decade]) decades[decade] = [];
        decades[decade].push(yearData);
    }

    // Sort decades descending
    const sortedDecades = Object.keys(decades).map(Number).sort((a, b) => b - a);

    let html = '';

    for (const decade of sortedDecades) {
        const yearList = decades[decade];
        let totalSongs = 0;
        let totalConquered = 0;

        for (const y of yearList) {
            totalSongs += y.songs.length;
            // Count years where all songs are reviewed (empty songs array AND total_in_db > 0)
            if (y.songs.length === 0 && y.total_in_db > 0) {
                totalConquered++;
            }
        }

        const totalInDb = yearList.reduce((sum, y) => sum + (y.total_in_db || 0), 0);
        const allConquered = totalInDb > 0 && totalSongs === 0;
        const decadeLabel = `${decade}s`;
        const isExpanded = decade >= 2010; // Expand current decade by default

        html += `
            <div class="conquest-decade ${allConquered ? 'conquest-decade-complete' : ''}">
                <div class="conquest-decade-header" onclick="this.parentElement.classList.toggle('expanded')">
                    <div class="conquest-decade-left">
                        <span class="conquest-decade-chevron">${isExpanded ? '▼' : '▶'}</span>
                        <span class="conquest-decade-label">${decadeLabel}</span>
                        ${allConquered ? '<span class="conquest-decade-badge conquest-badge-done">✅ Conquered!</span>' : ''}
                    </div>
                    <div class="conquest-decade-right">
                        ${totalSongs > 0
                            ? `<span class="conquest-decade-count">${totalSongs} songs to go</span>`
                            : totalConquered > 0
                                ? `<span class="conquest-decade-count conquest-count-done">${yearList.length} years done</span>`
                                : `<span class="conquest-decade-count">No data</span>`
                        }
                    </div>
                </div>
                <div class="conquest-decade-body">
        `;

        for (const yearData of yearList) {
            const { year, songs, total_in_db } = yearData;

            if (songs.length === 0) {
                if (total_in_db > 0) {
                    html += `
                        <div class="conquest-year conquest-year-complete">
                            <div class="conquest-year-header">
                                <span class="conquest-year-label">${year}</span>
                                <span class="conquest-year-badge conquest-badge-done">✅ Done!</span>
                            </div>
                        </div>
                    `;
                }
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
