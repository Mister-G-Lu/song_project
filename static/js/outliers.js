/**
 * outliers.js - Statistical Outliers View
 * Shows songs/artists that break your own rating patterns.
 */

let _outliersData = null;

async function loadOutliers() {
    try {
        const res = await fetch('/api/outliers');
        if (!res.ok) throw new Error('Failed to load outliers');
        _outliersData = await res.json();
        renderOutliers(_outliersData);
    } catch (err) {
        console.error('Outliers load error:', err);
        document.getElementById('outliersGrid').innerHTML =
            '<div class="loading-msg" style="color:var(--danger)">Error loading outliers. Is the server running?</div>';
    }
}

function renderOutliers(data) {
    const { categories: cats, summary } = data;
    const summaryEl = document.getElementById('outliersSummary');
    const gridEl = document.getElementById('outliersGrid');

    // Summary bar
    summaryEl.innerHTML = `
        <div class="outliers-stats-row">
            <div class="outlier-stat"><span class="outlier-stat-val">${summary.volatile_artists}</span><span class="outlier-stat-lbl">Volatile Artists</span></div>
            <div class="outlier-stat"><span class="outlier-stat-val">${summary.genre_rebels_count}</span><span class="outlier-stat-lbl">Genre Rebels</span></div>
            <div class="outlier-stat"><span class="outlier-stat-val">${summary.guilty_pleasures_count}</span><span class="outlier-stat-lbl">Guilty Pleasures</span></div>
            <div class="outlier-stat"><span class="outlier-stat-val">${summary.disappointments_count}</span><span class="outlier-stat-lbl">Disappointments</span></div>
            <div class="outlier-stat"><span class="outlier-stat-val">${summary.one_hit_wonders_count}</span><span class="outlier-stat-lbl">One-Hit Wonders</span></div>
            <div class="outlier-stat"><span class="outlier-stat-val">${summary.surprises_count}</span><span class="outlier-stat-lbl">Rating Surprises</span></div>
        </div>
    `;

    // Build cards
    let html = '';

    // 1. Artist Volatility
    if (cats.artist_volatility && cats.artist_volatility.length > 0) {
        html += outlierSection('🌋 Artist Volatility', 'Artists where your ratings swing wildly',
            cats.artist_volatility.map(a => `
                <div class="outlier-card">
                    <div class="outlier-card-header">
                        <span class="outlier-name">${esc(a.artist)}</span>
                        <span class="outlier-badge">${a.genre}</span>
                    </div>
                    <div class="outlier-bar-container">
                        <div class="outlier-bar-range">
                            <div class="outlier-bar-fill" style="left:${a.min_rating}%;width:${a.max_rating - a.min_rating}%"></div>
                            <div class="outlier-bar-avg" style="left:${a.avg_rating}%"></div>
                        </div>
                        <div class="outlier-bar-labels">
                            <span>${a.min_rating}</span>
                            <span class="outlier-avg-label">avg ${a.avg_rating}</span>
                            <span>${a.max_rating}</span>
                        </div>
                    </div>
                    <div class="outlier-detail">${a.song_count} songs · spread of <strong>${a.spread} pts</strong></div>
                </div>
            `).join('')
        );
    }

    // 2. Guilty Pleasures
    if (cats.guilty_pleasures && cats.guilty_pleasures.length > 0) {
        html += outlierSection('😏 Guilty Pleasures', 'High-rated songs in genres you usually score low',
            cats.guilty_pleasures.map(s => songCard(s, `You avg ${s.genre_avg} in ${s.genre} but rated this ${s.rating}`)).join('')
        );
    }

    // 3. Disappointments
    if (cats.disappointments && cats.disappointments.length > 0) {
        html += outlierSection('😬 Disappointments', 'Low-rated songs in genres you usually love',
            cats.disappointments.map(s => songCard(s, `You avg ${s.genre_avg} in ${s.genre} but rated this only ${s.rating}`)).join('')
        );
    }

    // 4. One-Hit Wonders
    if (cats.one_hit_wonders && cats.one_hit_wonders.length > 0) {
        html += outlierSection('⭐ One-Hit Wonders', 'One standout song far above an artist\'s average',
            cats.one_hit_wonders.map(s => `
                <div class="outlier-card">
                    <div class="outlier-card-header">
                        <span class="outlier-name">${esc(s.title)}</span>
                        <span class="outlier-badge outlier-badge-up">+${s.diff} above avg</span>
                    </div>
                    <div class="outlier-detail">${esc(s.artist)} · ${s.genre}</div>
                    <div class="outlier-rating-row">
                        <span class="outlier-rating">${s.rating}/100</span>
                        <span class="outlier-vs">vs artist avg ${s.artist_avg}</span>
                    </div>
                </div>
            `).join('')
        );
    }

    // 5. Genre Rebels
    if (cats.genre_rebels && cats.genre_rebels.length > 0) {
        html += outlierSection('🔥 Genre Rebels', 'Songs rated 20+ pts away from their genre average',
            cats.genre_rebels.slice(0, 12).map(s => `
                <div class="outlier-card">
                    <div class="outlier-card-header">
                        <span class="outlier-name">${esc(s.title)}</span>
                        <span class="outlier-badge ${s.direction === 'above' ? 'outlier-badge-up' : 'outlier-badge-down'}">${s.diff > 0 ? '+' : ''}${s.diff} vs ${s.genre}</span>
                    </div>
                    <div class="outlier-detail">${esc(s.artist)} · ${s.genre}</div>
                    <div class="outlier-rating-row">
                        <span class="outlier-rating">${s.rating}/100</span>
                        <span class="outlier-vs">genre avg ${s.genre_avg}</span>
                    </div>
                </div>
            `).join('')
        );
    }

    // 6. Rating Surprises
    if (cats.rating_surprises && cats.rating_surprises.length > 0) {
        const above = cats.rating_surprises.filter(s => s.direction === 'above').slice(0, 8);
        const below = cats.rating_surprises.filter(s => s.direction === 'below').slice(0, 8);
        let surpriseHtml = '';
        if (above.length > 0) {
            surpriseHtml += '<h4 class="outlier-subhead">📈 Far Above Your Average</h4>';
            surpriseHtml += above.map(s => `
                <div class="outlier-card outlier-card-up">
                    <div class="outlier-card-header">
                        <span class="outlier-name">${esc(s.title)}</span>
                        <span class="outlier-badge outlier-badge-up">+${s.diff}</span>
                    </div>
                    <div class="outlier-detail">${esc(s.artist)} · ${s.genre}</div>
                    <div class="outlier-rating-row">
                        <span class="outlier-rating">${s.rating}/100</span>
                        <span class="outlier-vs">your avg ${s.overall_avg}</span>
                    </div>
                </div>
            `).join('');
        }
        if (below.length > 0) {
            surpriseHtml += '<h4 class="outlier-subhead">📉 Far Below Your Average</h4>';
            surpriseHtml += below.map(s => `
                <div class="outlier-card outlier-card-down">
                    <div class="outlier-card-header">
                        <span class="outlier-name">${esc(s.title)}</span>
                        <span class="outlier-badge outlier-badge-down">${s.diff}</span>
                    </div>
                    <div class="outlier-detail">${esc(s.artist)} · ${s.genre}</div>
                    <div class="outlier-rating-row">
                        <span class="outlier-rating">${s.rating}/100</span>
                        <span class="outlier-vs">your avg ${s.overall_avg}</span>
                    </div>
                </div>
            `).join('');
        }
        html += outlierSection('🎲 Rating Surprises', 'Songs 25+ pts from your overall average', surpriseHtml);
    }

    if (!html) {
        html = '<div class="loading-msg">Not enough data to detect outliers yet. Rate more songs!</div>';
    }

    gridEl.innerHTML = html;
}

// ---- Helpers ----

function outlierSection(title, subtitle, content) {
    return `
        <div class="outlier-section">
            <div class="outlier-section-header">
                <h3>${title}</h3>
                <p class="outlier-section-sub">${subtitle}</p>
            </div>
            <div class="outlier-cards">${content}</div>
        </div>
    `;
}

function songCard(s, reason) {
    return `
        <div class="outlier-card">
            <div class="outlier-card-header">
                <span class="outlier-name">${esc(s.title)}</span>
                <span class="outlier-badge">${s.genre}</span>
            </div>
            <div class="outlier-detail">${esc(s.artist)} · ${reason}</div>
            <div class="outlier-rating-row">
                <span class="outlier-rating">${s.rating}/100</span>
                <span class="outlier-vs">genre avg ${s.genre_avg}</span>
            </div>
        </div>
    `;
}

function esc(str) {
    if (!str) return '';
    const el = document.createElement('span');
    el.textContent = str;
    return el.innerHTML;
}
