/**
 * dashboard.js - Dashboard view with stats, charts, and tables
 */

let ratingChartInstance = null;
let genreChartInstance = null;

async function loadDashboard(prefetchedStats, skipBackfill) {
    try {
        const data = prefetchedStats || await (await fetch('/api/stats')).json();
        hideViewLoading('view-dashboard');
        renderStats(data);
        renderRatingChart(data.rating_distribution);
        renderGenreChart(data.genre_distribution);
        renderTopArtists(data.top_artists);
        renderRecentReviews(data.recent_reviews);
    } catch (err) {
        hideViewLoading('view-dashboard');
        console.error('Dashboard load error:', err);
    }
    // Also load backfill preview alongside dashboard stats (unless caller opts out)
    if (!skipBackfill) {
        try {
            await loadBackfillPreview();
        } catch (err) {
            // Backfill is secondary — don't block dashboard
        }
    }
}

function renderStats(data) {
    document.getElementById('statTotal').textContent = data.total_entries?.toLocaleString() || '-';
    document.getElementById('statRated').textContent = data.rated_entries?.toLocaleString() || '-';
    document.getElementById('statAvg').textContent = data.avg_rating !== undefined ? data.avg_rating : '-';
    document.getElementById('statMedian').textContent = data.median_rating !== undefined ? data.median_rating : '-';
    document.getElementById('statRange').textContent = data.min_rating !== undefined ? `${data.min_rating} – ${data.max_rating}` : '-';
    document.getElementById('statArtists').textContent = data.unique_artists !== undefined ? data.unique_artists : '-';

    // Genre coverage: compute from genre_distribution
    const genres = data.genre_distribution || {};
    const uncategorized = genres['Uncategorized']?.count || 0;
    const total = data.total_entries || 0;
    const coveragePct = total > 0 ? ((1 - uncategorized / total) * 100).toFixed(1) : '-';
    const coverageEl = document.getElementById('statCoverage');
    if (coverageEl) {
        coverageEl.textContent = coveragePct !== '-' ? `${coveragePct}%` : '-';
        const pct = parseFloat(coveragePct);
        coverageEl.style.color = pct >= 85 ? 'var(--accent-success, #34d399)' : pct >= 70 ? 'var(--accent-warning, #fbbf24)' : 'var(--accent-danger, #f87171)';
    }

    if (data.date_range) {
        const start = data.date_range.start || '';
        const end = data.date_range.end || '';
        const startYear = start.slice(0, 4);
        const endYear = end.slice(0, 4);
        const years = parseInt(endYear) - parseInt(startYear);
        document.getElementById('statPeriod').textContent = `${years} years`;
    }

    const perfectCount = Object.entries(data.rating_distribution || {})
        .filter(([k]) => k === '96-100')
        .reduce((sum, [,v]) => sum + v, 0);
    document.getElementById('statPerfect').textContent = perfectCount;
}

function renderRatingChart(distribution) {
    const canvas = document.getElementById('ratingChart');
    if (!canvas || window.__chartjsFailed) return;
    const ctx = canvas.getContext('2d');
    
    if (ratingChartInstance) { ratingChartInstance.destroy(); ratingChartInstance = null; }

    const labels = Object.keys(distribution);
    const values = Object.values(distribution);
    const colors = ['#f87171', '#fb923c', '#fbbf24', '#a3e635', '#34d399', '#22d3ee'];

    ratingChartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                data: values,
                backgroundColor: colors.map(c => c + 'CC'),
                borderColor: colors,
                borderWidth: 1,
                borderRadius: 4,
            }]
        },
        options: {
            ...CHART_THEME,
            scales: {
                y: { beginAtZero: true, ...CHART_THEME.scales.y },
                x: { ...CHART_THEME.scales.x }
            },
            plugins: {
                legend: { display: false },
                tooltip: { ...CHART_THEME.plugins.tooltip, callbacks: {
                    label: (ctx) => `${ctx.parsed.y} songs`
                }}
            }
        }
    });
}

function renderGenreChart(genres) {
    const canvas = document.getElementById('genreChart');
    if (!canvas || window.__chartjsFailed) return;
    const ctx = canvas.getContext('2d');
    
    if (genreChartInstance) { genreChartInstance.destroy(); genreChartInstance = null; }

    const entries = Object.entries(genres || {}).filter(([,v]) => v.count > 0);
    // Rename 'Uncategorized' to 'Other' for better UX
    const renamed = entries.map(([k, v]) => [k === 'Uncategorized' ? 'Other' : k, v]);
    const sorted = renamed.sort((a, b) => b[1].count - a[1].count).slice(0, 12);
    // Map renamed labels back to original keys for tooltip lookup
    const labelToKey = { 'Other': 'Uncategorized' };
    
    const labels = sorted.map(([k]) => k);
    const counts = sorted.map(([,v]) => v.count);
    const avgRatings = sorted.map(([,v]) => v.avg_rating);
    
    const colors = labels.map((_, i) => {
        const hue = (i * 27) % 360;
        return `hsla(${hue}, 70%, 55%, 0.8)`;
    });

    genreChartInstance = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels,
            datasets: [{
                data: counts,
                backgroundColor: colors,
                borderColor: '#12121a',
                borderWidth: 2,
            }]
        },
        options: {
            ...CHART_THEME,
            plugins: {
                legend: {
                    position: 'right',
                    labels: {
                        color: '#9090a8',
                        font: { size: 11 },
                        padding: 8,
                        usePointStyle: true,
                    }
                },
                tooltip: { ...CHART_THEME.plugins.tooltip, callbacks: {
                    label: (ctx) => {
                        const genre = ctx.label;
                        const lookupKey = labelToKey[genre] || genre;
                        const info = genres[lookupKey] || {};
                        return [
                            `${ctx.parsed} songs`,
                            `Avg rating: ${info.avg_rating || 'N/A'}`
                        ];
                    }
                }}
            }
        }
    });
}

function renderTopArtists(artists) {
    const container = document.getElementById('topArtistsTable');
    if (!artists || artists.length === 0) {
        container.innerHTML = '<div class="table-placeholder">No artist data available</div>';
        return;
    }

    let html = '<table class="data-table"><thead><tr><th>#</th><th>Artist</th><th>Avg Rating</th><th>Songs</th><th>Top Songs</th></tr></thead><tbody>';
    
    artists.forEach((artist, i) => {
        const rankClass = i < 3 ? 'top3' : '';
        const badgeClass = getRatingClass(artist.avg_rating);
        const topSongs = (artist.top_songs || []).map(s => s.title.split('(')[0].trim()).join(', ').slice(0, 60);
        
        html += `<tr>
            <td><span class="artist-rank ${rankClass}">${i + 1}</span></td>
            <td><strong>${artist.name}</strong></td>
            <td><span class="rating-badge ${badgeClass}">${artist.avg_rating}</span></td>
            <td>${artist.song_count}</td>
            <td style="font-size:12px;color:var(--text-muted)">${topSongs || '—'}</td>
        </tr>`;
    });
    
    html += '</tbody></table>';
    container.innerHTML = html;
}

function renderRecentReviews(reviews) {
    const container = document.getElementById('recentReviews');
    if (!reviews || reviews.length === 0) {
        container.innerHTML = '<div class="table-placeholder">No reviews yet</div>';
        return;
    }

    let html = '';
    reviews.forEach(r => {
        const badgeClass = getRatingClass(r.rating);
        html += `<div class="review-item">
            <div class="review-header">
                <span class="review-title">${escapeHtml(r.title)}</span>
                <span><span class="rating-badge ${badgeClass}">${r.rating || '?'}</span> <span class="review-date">${r.date}</span></span>
            </div>
            <div class="review-preview">${escapeHtml(r.preview || '')}</div>
        </div>`;
    });
    
    container.innerHTML = html;
}

