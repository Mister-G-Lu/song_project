/**
 * hygiene.js - Data Hygiene View
 * Surfaces data-quality problems (placeholder artists, identity variants,
 * genre-cache conflicts, duplicate/artist-level rows) so pollution gets
 * caught automatically instead of by eyeballing the CSV.
 */

let _hygieneData = null;

async function loadHygiene() {
    await withViewLoading('view-hygiene', '🧼 Scanning your data for problems...', async () => {
        _hygieneData = window.ViewControl
            ? await window.ViewControl.fetch('hygiene', '/api/data-hygiene')
            : await (await fetch('/api/data-hygiene')).json();
        renderHygiene(_hygieneData);
    }, { onError: (err) => {
        console.error('Hygiene load error:', err);
        document.getElementById('hygieneGrid').innerHTML =
            '<div class="loading-msg" style="color:var(--danger)">Error loading data hygiene scan. Is the server running?</div>';
    } });
}

function renderHygiene(data) {
    const { summary, ...sections } = data;
    const summaryEl = document.getElementById('hygieneSummary');
    const gridEl = document.getElementById('hygieneGrid');

    const totalIssues = Object.values(summary).reduce((a, b) => a + b, 0);
    summaryEl.innerHTML = `
        <div class="outliers-stats-row">
            <div class="outlier-stat"><span class="outlier-stat-val">${totalIssues}</span><span class="outlier-stat-lbl">Total findings</span></div>
            <div class="outlier-stat"><span class="outlier-stat-val">${summary.case_variant_groups}</span><span class="outlier-stat-lbl">Identity variants</span></div>
            <div class="outlier-stat"><span class="outlier-stat-val">${summary.cache_conflicts}</span><span class="outlier-stat-lbl">Cache conflicts</span></div>
            <div class="outlier-stat"><span class="outlier-stat-val">${summary.artist_self_rows}</span><span class="outlier-stat-lbl">Artist-level rows</span></div>
            <div class="outlier-stat"><span class="outlier-stat-val">${summary.generic_artist_rows}</span><span class="outlier-stat-lbl">Placeholder rows</span></div>
            <div class="outlier-stat"><span class="outlier-stat-val">${summary.no_artist_rows}</span><span class="outlier-stat-lbl">No-artist rows</span></div>
        </div>
    `;

    let html = '';

    if (sections.case_variants && sections.case_variants.length > 0) {
        html += hygieneSection('🔤 Identity Variants',
            'Artist spellings that differ by case or spacing. The engine already merges them at load time — listed here so you know they exist in the raw CSV.',
            sections.case_variants.map(v => `
                <div class="outlier-card">
                    <div class="outlier-card-header">
                        <span class="outlier-name">${esc(v.canonical)}</span>
                        <span class="outlier-badge">${v.rows} rows · auto-merged</span>
                    </div>
                    <div class="outlier-detail">${Object.entries(v.variants).map(([spelling, n]) => `${esc(spelling)} (${n})`).join(' · ')}</div>
                </div>
            `).join(''));
    }

    if (sections.cache_conflicts && sections.cache_conflicts.length > 0) {
        html += hygieneSection('⚔️ Genre Cache Conflicts',
            'Artists whose genre was cached under multiple spellings with different values. Lookups resolve automatically (curated value wins, then the most-rated spelling).',
            sections.cache_conflicts.map(c => `
                <div class="outlier-card">
                    <div class="outlier-card-header">
                        <span class="outlier-name">${esc(c.artist)}</span>
                        <span class="outlier-badge">resolves to: ${esc(c.resolved || '?')}</span>
                    </div>
                    <div class="outlier-detail">${Object.entries(c.values).map(([k, v]) => `${esc(k)} → ${esc(v)}`).join(' · ')}</div>
                </div>
            `).join(''));
    }

    if (sections.artist_self_rows && sections.artist_self_rows.length > 0) {
        html += hygieneSection('🎭 Artist-Level Rows',
            'Rows where title = artist (imported artist ratings). Counted toward artist stats but never shown as songs.',
            sections.artist_self_rows.map(r => `
                <div class="outlier-card">
                    <div class="outlier-card-header">
                        <span class="outlier-name">${esc(r.title)}</span>
                        <span class="outlier-badge">${r.rating ? r.rating + '/100' : 'unrated'}</span>
                    </div>
                    <div class="outlier-detail">${esc(r.date)}</div>
                </div>
            `).join(''));
    }

    if (sections.generic_artists && sections.generic_artists.length > 0) {
        html += hygieneSection('❓ Placeholder Artists',
            'Generic names like "Unknown Artist" or "Various Artists". They are never assigned a genre and may deserve manual cleanup in the CSV.',
            sections.generic_artists.map(g => `
                <div class="outlier-card">
                    <div class="outlier-card-header">
                        <span class="outlier-name">${esc(g.artist)}</span>
                        <span class="outlier-badge">${g.count} rows</span>
                    </div>
                </div>
            `).join(''));
    }

    if (sections.duplicate_songs && sections.duplicate_songs.length > 0) {
        html += hygieneSection('👯 Duplicate Songs',
            'Same artist+song appearing in multiple rows (kept best rating at load).',
            sections.duplicate_songs.map(d => `
                <div class="outlier-card">
                    <div class="outlier-card-header">
                        <span class="outlier-name">${esc(d.rows[0].title)}</span>
                        <span class="outlier-badge">${d.rows.length} rows</span>
                    </div>
                    <div class="outlier-detail">${esc(d.rows[0].artist)} · ratings: ${d.rows.map(r => r.rating ?? '?').join(', ')}</div>
                </div>
            `).join(''));
    }

    if (sections.no_artist && sections.no_artist.length > 0) {
        html += hygieneSection('🕳️ No-Artist Rows',
            'Songs with no artist information at all — they cannot be classified by artist.',
            sections.no_artist.map(r => `
                <div class="outlier-card">
                    <div class="outlier-card-header">
                        <span class="outlier-name">${esc(r.title)}</span>
                        <span class="outlier-badge">${r.rating ? r.rating + '/100' : 'unrated'}</span>
                    </div>
                    <div class="outlier-detail">${esc(r.date)}</div>
                </div>
            `).join(''));
    }

    if (!html) {
        html = '<div class="loading-msg">✨ No data problems found. Your collection is squeaky clean!</div>';
    }

    gridEl.innerHTML = html;
}

function hygieneSection(title, subtitle, content) {
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

function esc(str) {
    if (!str) return '';
    const el = document.createElement('span');
    el.textContent = str;
    return el.innerHTML;
}
