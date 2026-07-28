/**
 * dashboard.js - Dashboard view with stats, charts, and tables
 */

let ratingChartInstance = null;
let genreChartInstance = null;

async function loadDashboard() {
    try {
        const res = await fetch('/api/stats');
        const data = await res.json();
        renderStats(data);
        renderRatingChart(data.rating_distribution);
        renderGenreChart(data.genre_distribution);
        renderTopArtists(data.top_artists);
        renderRecentReviews(data.recent_reviews);
    } catch (err) {
        console.error('Dashboard load error:', err);
    }
    // Also load backfill preview alongside dashboard stats
    try {
        await loadBackfillPreview();
    } catch (err) {
        // Backfill is secondary — don't block dashboard
    }
}

function renderStats(data) {
    document.getElementById('statTotal').textContent = data.total_entries?.toLocaleString() || '-';
    document.getElementById('statRated').textContent = data.rated_entries?.toLocaleString() || '-';
    document.getElementById('statAvg').textContent = data.avg_rating !== undefined ? data.avg_rating : '-';
    document.getElementById('statMedian').textContent = data.median_rating !== undefined ? data.median_rating : '-';
    document.getElementById('statRange').textContent = data.min_rating !== undefined ? `${data.min_rating} – ${data.max_rating}` : '-';
    document.getElementById('statArtists').textContent = data.unique_artists !== undefined ? data.unique_artists : '-';

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
    const ctx = document.getElementById('ratingChart').getContext('2d');
    
    if (ratingChartInstance) ratingChartInstance.destroy();

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
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: '#1a1a28',
                    titleColor: '#e8e8f0',
                    bodyColor: '#9090a8',
                    borderColor: '#2a2a3e',
                    borderWidth: 1,
                    callbacks: {
                        label: (ctx) => `${ctx.parsed.y} songs`
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: { color: '#2a2a3e30' },
                    ticks: { color: '#606078', font: { size: 11 } }
                },
                x: {
                    grid: { display: false },
                    ticks: { color: '#606078', font: { size: 11 } }
                }
            }
        }
    });
}

function renderGenreChart(genres) {
    const ctx = document.getElementById('genreChart').getContext('2d');
    
    if (genreChartInstance) genreChartInstance.destroy();

    const entries = Object.entries(genres || {}).filter(([,v]) => v.count > 0);
    const sorted = entries.sort((a, b) => b[1].count - a[1].count).slice(0, 12);
    
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
            responsive: true,
            maintainAspectRatio: false,
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
                tooltip: {
                    backgroundColor: '#1a1a28',
                    titleColor: '#e8e8f0',
                    bodyColor: '#9090a8',
                    borderColor: '#2a2a3e',
                    borderWidth: 1,
                    callbacks: {
                        label: (ctx) => {
                            const genre = ctx.label;
                            const info = genres[genre] || {};
                            return [
                                `${ctx.parsed} songs`,
                                `Avg rating: ${info.avg_rating || 'N/A'}`
                            ];
                        }
                    }
                }
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
        const badgeClass = artist.avg_rating >= 90 ? 'perfect' : artist.avg_rating >= 80 ? 'high' : artist.avg_rating >= 70 ? 'good' : 'ok';
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
        const badgeClass = r.rating >= 90 ? 'perfect' : r.rating >= 80 ? 'high' : r.rating >= 70 ? 'good' : 'ok';
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

// ============================================================
// Backfill Missing Ratings — Letter grades & tone inference
// ============================================================

async function loadBackfillPreview() {
    const container = document.getElementById('backfillPreviewStats');
    try {
        const res = await fetch('/api/backfill-preview?method=all');
        const data = await res.json();
        renderBackfillPreview(data);
    } catch (err) {
        container.innerHTML = '<div class="backfill-error">⚠️ Failed to load preview. Is the server running?</div>';
    }
}

function renderBackfillPreview(data) {
    const container = document.getElementById('backfillPreviewStats');
    const btn = document.getElementById('backfillBtn');
    
    if (data.total_changes === 0) {
        container.innerHTML = '<div class="backfill-none">✅ No unrated entries found — all songs already have ratings!</div>';
        btn.disabled = true;
        return;
    }
    
    const src = data.changes_by_source;
    const pct = ((data.after.rated / data.after.total) * 100).toFixed(0);
    
    let detailHtml = '';
    if (data.changes && data.changes.length > 0) {
        detailHtml = '<div class="backfill-sample"><h4>Sample entries to be backfilled:</h4>';
        detailHtml += '<table class="data-table"><thead><tr><th>Title</th><th>Source</th><th>New Rating</th><th>Preview</th></tr></thead><tbody>';
        data.changes.slice(0, 10).forEach(c => {
            const sourceLabel = c.source === 'letter' ? `📝 ${c.grade_str}` : `🎯 ${c.source.replace('tone:', '')}`;
            detailHtml += `<tr>
                <td><strong>${escapeHtml(c.title)}</strong></td>
                <td><span class="backfill-source">${sourceLabel}</span></td>
                <td><span class="rating-badge ${c.new_rating >= 90 ? 'perfect' : c.new_rating >= 80 ? 'high' : c.new_rating >= 70 ? 'good' : 'ok'}">${c.new_rating}</span></td>
                <td style="font-size:12px;color:var(--text-muted);max-width:200px;overflow:hidden;text-overflow:ellipsis">${escapeHtml(c.preview).slice(0,100)}</td>
            </tr>`;
        });
        detailHtml += '</tbody></table></div>';
    }
    
    container.innerHTML = `
        <div class="backfill-grid">
            <div class="backfill-stat">
                <div class="bf-value">+${data.total_changes}</div>
                <div class="bf-label">Ratings to Recover</div>
            </div>
            <div class="backfill-stat">
                <div class="bf-value">${src.letter_grades}</div>
                <div class="bf-label">From Letter Grades</div>
            </div>
            <div class="backfill-stat">
                <div class="bf-value">${src.tone_inference}</div>
                <div class="bf-label">From Tone Inference</div>
            </div>
            <div class="backfill-stat">
                <div class="bf-value">${pct}%</div>
                <div class="bf-label">Coverage After</div>
            </div>
        </div>
        <div class="backfill-compare">
            <span class="bf-before">Before: ${data.before.rated} rated (avg ${data.before.avg_rating})</span>
            <span class="bf-arrow">→</span>
            <span class="bf-after">After: <strong>${data.after.rated}</strong> rated (avg <strong>${data.after.avg_rating}</strong>)</span>
        </div>
    `;
    
    document.getElementById('backfillDetail').innerHTML = detailHtml;
    btn.disabled = false;
}

async function refreshBackfillPreview() {
    const btn = document.getElementById('backfillBtn');
    btn.disabled = true;
    btn.textContent = '⟳ Loading...';
    await loadBackfillPreview();
    btn.textContent = '⚡ Apply Backfill';
    btn.disabled = false;
}

async function applyBackfill() {
    const btn = document.getElementById('backfillBtn');
    if (btn.disabled) return;
    
    if (!confirm('This will write recovered ratings to your CSV file. The original data will be preserved but ratings will be added to unrated entries. Continue?')) {
        return;
    }
    
    btn.disabled = true;
    btn.textContent = '⟳ Applying...';
    
    try {
        const res = await fetch('/api/backfill-ratings', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ method: 'all' })
        });
        const data = await res.json();
        
        if (data.error) {
            showToast(`⚠️ ${data.error}`);
            btn.disabled = false;
            btn.textContent = '⚡ Apply Backfill';
            return;
        }
        
        showToast(`✅ Backfilled ${data.total_changes} ratings! ${data.after.rated} songs now rated (avg ${data.after.avg_rating})`);
        renderBackfillPreview(data);
        
        // Reload dashboard stats
        loadDashboard();
    } catch (err) {
        showToast(`⚠️ Error applying backfill: ${err.message}`);
        btn.disabled = false;
        btn.textContent = '⚡ Apply Backfill';
    }
}


