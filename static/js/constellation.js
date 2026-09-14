/**
 * constellation.js - Artist constellation network graph using D3.js
 * Three modes:
 *   Genre & Taste (default) — genre clusters in a grid, favorites float to
 *     the top and disliked sink to the bottom within each genre band.
 *   Artist Connections — edge-driven layout: collaborations, genre similarity,
 *     and rating-pattern edges pull related artists together. Louvain community
 *     detection clusters appear naturally from the physics, no genre grid.
 *   Followers — a scatter CHART, not physics: X axis is follower count on a
 *     LOG scale (1 → 100M) with labeled ticks, Y is one row per genre. Nodes
 *     are pinned to their exact audience size; the log scale spreads the
 *     collection far better than Spotify's 0-100 popularity (74% of artists
 *     sit in 80-89 there).
 */

let constellationData = null;
let simulation = null;
let currentMode = 'genre';

// --- Pre-computed colour palettes ---

/**
 * 32 visually distinct categorical colours for D3.js community clusters.
 * Used by the Artist Connections mode to colour Louvain communities.
 */
const COMMUNITY_COLORS = [
    '#e6194b', '#3cb44b', '#ffe119', '#4363d8', '#f58231', '#911eb4',
    '#42d4f4', '#f032e6', '#bfef45', '#fabed4', '#469990', '#dcbeff',
    '#9a6324', '#fffac8', '#800000', '#aaffc3', '#808000', '#ffd8b1',
    '#000075', '#a9a9a9', '#e6beff', '#ff6f00', '#008080', '#bcf60c',
    '#cd853f', '#7f6cf0', '#ff1493', '#00ced1', '#8b4513', '#6a5acd',
    '#20b2aa', '#dc1436'
];

// ---- Sentiment (Liked/Disliked) — semantic colours, separate from the
// heat-scale rating palette. Higher value = greener (more loved). ----
// Deterministic per-name jitter: keeps thousands of nodes with near-identical
// popularity from crowding one x-strip (real-world popularity is concentrated
// around 70-90), without changing an artist's relative position between renders.
function _nameJitter(name, spread) {
    let h = 0;
    const s = String(name || '');
    for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
    return ((h >>> 0) % (spread * 2)) - spread;
}

const LOVED_COLOR   = '#2ec27e';
const LIKED_COLOR   = '#94d82d';
const MEH_COLOR     = '#a8adbe';
const DISLIKED_COLOR = '#e8590c';

// Returns a per-node sentiment bucket: loved/liked/meh/disliked.
function _sentiment(avg) {
    // dir is the vertical offset multiplier (negative = toward the top of
    // the genre band). Must be MONOTONIC with rating: higher-rated artists
    // always sit above lower-rated ones, across the full 0-100 range.
    if (avg >= 90) return { key: 'loved',    label: 'Loved (90+)',   color: LOVED_COLOR,    dir: -1.0 };
    if (avg >= 80) return { key: 'liked',    label: 'Liked (80–89)', color: LIKED_COLOR,    dir: -0.66 };
    if (avg >= 70) return { key: 'meh',      label: 'Meh (70–79)',   color: MEH_COLOR,      dir: -0.33 };
    return            { key: 'disliked', label: 'Disliked (<70)', color: DISLIKED_COLOR, dir: 1.0 };
}

function _communityColor(communityId) {
    if (communityId < 0 || communityId === undefined || communityId === null) return PALETTE.borderColor;
    return COMMUNITY_COLORS[communityId % COMMUNITY_COLORS.length];
}

// ===================================================================
// Mode switching
// ===================================================================

const MODE_DESCRIPTIONS = {
    genre: 'Genre spectrum — <span style="color:var(--text-secondary)">similar genres share horizontal spans</span> (Rap → R&B → Pop → Rock → Metal → Electronic → Folk) · <span style="color:var(--text-secondary)">↑ highest-rated at top, ↓ lowest at bottom</span> across full height',
    connections: 'Artists linked by <span style="color:var(--text-secondary)">collaborations, genre & rating similarity</span> — clusters detected automatically',
    followers: 'Scatter chart — X: <span style="color:var(--text-secondary)">follower count, log scale</span> (bedroom artist → global superstar) · Y: one row per genre, artists pinned to their exact audience size'
};

function setConstellationMode(mode) {
    currentMode = mode;
    // Update both the in-view segmented control and the optional global bar
    // (the global bar is a persistent sub-nav promoted outside the constellation view).
    document.querySelectorAll('.mode-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.mode === mode);
    });
    const globalTabsEl = document.getElementById('constellationGlobalTabs');
    if (globalTabsEl) {
        globalTabsEl.classList.toggle('visible', !!constellationData);
        const globalBtns = globalTabsEl.querySelectorAll('.mode-btn');
        globalBtns.forEach(btn => {
            btn.classList.toggle('active', btn.dataset.mode === mode);
        });
    }
    const descEl = document.getElementById('constellationModeDesc');
    const popDescEl = document.getElementById('constellationFollowersDesc');
    if (descEl) descEl.style.display = (mode === 'followers') ? 'none' : '';
    if (popDescEl) popDescEl.style.display = (mode === 'followers') ? '' : 'none';
    if (descEl && MODE_DESCRIPTIONS[mode]) descEl.innerHTML = MODE_DESCRIPTIONS[mode];
    showViewLoading('view-constellation', '♻️ Reorganizing constellation...');
    requestAnimationFrame(() => {
        if (constellationData) {
            renderConstellation(constellationData);
        }
        hideViewLoading('view-constellation');
    });
}

// ===================================================================

async function loadConstellation() {
    showViewLoading('view-constellation', '🌌 Mapping artist constellation...');
    try {
        const res = await fetch('/api/constellation');
        const data = await res.json();
        constellationData = data;
        hideViewLoading('view-constellation');
        renderConstellation(data);
    } catch (err) {
        hideViewLoading('view-constellation');
        // Hide the global sub-nav on load failure so the stale tabs don't linger.
        const globalTabsEl = document.getElementById('constellationGlobalTabs');
        if (globalTabsEl) globalTabsEl.classList.remove('visible');
        console.error('Constellation load error:', err);
        document.querySelector('#view-constellation .constellation-container').innerHTML =
            '<div class="view-error"><span class="view-error-icon">⚠️</span><p>Failed to load constellation</p><button class="btn btn-outline" onclick="loadConstellation()">Retry</button></div>';
    }
}

// ===================================================================
// Legend rendering
// ===================================================================

function _renderLegend(legendEl, data) {
    if (!legendEl) return;

    if (currentMode === 'connections') {
        // Community clusters — show dominant genre per cluster
        const communities = data.communities || {};
        const entries = Object.entries(communities);
        if (entries.length === 0) {
            legendEl.innerHTML = '<span style="color:var(--text-muted);font-size:12px">No communities found</span>';
            return;
        }
        legendEl.innerHTML = entries.slice(0, 14).map(([cid, meta]) => {
            const color = _communityColor(Number(cid));
            const label = meta.dominant_genre && meta.dominant_genre !== 'Uncategorized'
                ? meta.dominant_genre
                : `Cluster ${cid}`;
            return `<div class="legend-item" title="${meta.top_artists.map(a => a.name).join(', ')}">
                <span class="legend-dot" style="background:${color}"></span>
                ${label}
                <span class="legend-count">${meta.size}</span>
            </div>`;
        }).join('') + (entries.length > 14
            ? `<span style="color:var(--text-muted);font-size:11px;margin-left:8px">+${entries.length - 14} more</span>`
            : '');
        return;
    }

    // Genre & Taste AND Followers share the sentiment palette
    // (Followers adds an axis hint instead of the per-genre list).

    // Genre & Taste mode — sentiment tiers + genre info
    const sentimentItems = [
        [LOVED_COLOR, 'Loved (90+)'], [LIKED_COLOR, 'Liked (80–89)'],
        [MEH_COLOR, 'Meh (70–79)'], [DISLIKED_COLOR, 'Disliked (<70)']
    ];
    const sentimentHtml = sentimentItems.map(([c, l]) =>
        `<div class="legend-item"><span class="legend-dot" style="background:${c}"></span> ${l}</div>`
    ).join('');

    const communities = data.communities || {};
    const genreEntries = Object.entries(communities)
        .filter(([, meta]) => meta.dominant_genre && meta.dominant_genre !== 'Uncategorized')
        .slice(0, 6);
    const genreHtml = (genreEntries.length > 0 && currentMode !== 'followers')
        ? `<span style="color:var(--text-muted);font-size:11px;margin-left:12px">← ${genreEntries.map(([, meta]) => meta.dominant_genre).join(' → ')} →</span>`
        : (currentMode === 'followers'
            ? `<span style="color:var(--text-muted);font-size:11px;margin-left:12px">← niche · follower count (log scale) · arena-filling →</span>`
            : '');

    legendEl.innerHTML = sentimentHtml + genreHtml;
}

// Deterministic per-name jitter helper (kept for potential reuse in dense
// force layouts; the followers chart pins nodes exactly instead).
function _nameJitter(name, spread) {
    let h = 0;
    const s = String(name || '');
    for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
    return ((h >>> 0) % (spread * 2)) - spread;
}

// ===================================================================
// Followers mode: deterministic scatter chart (no force simulation).
// X = follower count on a LOG scale with real axis ticks (1, 100, 1K,
// 10K, 100K, 1M, 10M); Y = one row per genre, so each genre reads
// left→right as bedroom artist → global superstar.
// ===================================================================

function _formatFollowers(v) {
    if (v >= 1e6) return (v / 1e6).toFixed(v >= 1e7 ? 0 : 1).replace(/\.0$/, '') + 'M';
    if (v >= 1e3) return (v / 1e3).toFixed(v >= 1e4 ? 0 : 1).replace(/\.0$/, '') + 'K';
    return String(v);
}

function _renderFollowersChart({ g, data, width, height, nodeRadius, nodeColor }) {
    const tooltip = document.getElementById('constellationTooltip');
    const padLeft = 40, padRight = 18, padTop = 12, padBottom = 40;
    const plotW = Math.max(60, width - padLeft - padRight);
    const chartH = Math.max(60, height - padTop - padBottom);

    // ---- Scales: log makes 7 decades of audience size readable ----
    const followersOf = (d) => {
        const f = Number(d.followers);
        return (Number.isFinite(f) && f > 0) ? f : 1000; // neutral 1K fallback
    };
    const fMin = Math.max(1, d3.min(data.nodes, followersOf) || 1);
    const fMax = Math.max(fMin * 10, d3.max(data.nodes, followersOf) || 1e6);
    const x = d3.scaleLog().domain([fMin, fMax]).range([padLeft, padLeft + plotW]).clamp(true);

    const genres = [...new Set(data.nodes.filter(n => n.genre).map(n => n.genre))].sort();
    // Followers chart is a scatter chart, not a pure log plot: within each
    // genre row, high-rated artists sit toward the top and low-rated ones
    // toward the bottom, so the same "rating on top" intent that Genre &
    // Taste mode carries is preserved in the chart too.
    const ratingBands = [
        { key: 'loved',     min: 90, max: 100, dir: -1.0 },
        { key: 'liked',     min: 80, max: 90,  dir: -0.66 },
        { key: 'meh',       min: 70, max: 80,  dir: -0.33 },
        { key: 'disliked',  min: 0,  max: 70,  dir: 1.0 },
    ];
    const bandFor = (avg) => {
        const a = Math.max(0, Math.min(100, Number(avg) || 0));
        return ratingBands.find(b => a >= b.min && a < b.max) || ratingBands[3];
    };

    const nRows = Math.max(1, genres.length);
    const rowH = chartH / nRows;
    const genreRow = {};
    genres.forEach((gn, i) => { genreRow[gn] = i; });
    const rowCenter = (gn) => {
        const r = genreRow[gn || 'Uncategorized'];
        return r === undefined ? padTop + chartH / 2 : padTop + rowH * (r + 0.5);
    };

    // ---- X axis with ticks + title ----
    // d3 log-scale .ticks(count) ignores `count` and emits ~10 per decade;
    // compute a clean 1/2/5-multiple decade set ourselves instead.
    const tickVals = [];
    for (let e = Math.floor(Math.log10(fMin)); Math.pow(10, e) <= fMax * 10; e++) {
        for (const m of [1, 2, 5]) {
            const v = m * Math.pow(10, e);
            if (v >= fMin * 0.999 && v <= fMax * 1.001) tickVals.push(v);
        }
    }
    g.append('g')
        .attr('class', 'pop-axis')
        .attr('transform', `translate(0,${height - padBottom + 8})`)
        .call(d3.axisBottom(x)
            .tickValues(tickVals)
            .tickSize(4)
            // Thin labels on narrow screens (every other tick) to avoid overlap.
            .tickFormat((v, i) => (plotW / tickVals.length < 34 && i % 2) ? '' : _formatFollowers(v)));
    g.append('text')
        .attr('class', 'pop-axis-title')
        .attr('x', padLeft + plotW / 2)
        .attr('y', height - 6)
        .attr('text-anchor', 'middle')
        .attr('font-family', "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif")
        .attr('font-size', 11)
        .attr('fill', PALETTE.textMuted)
        .text('Follower count — log scale (Deezer nb_fan, Spotify followers proxy)');

    // ---- Genre row separators + labels ----
    const labelEvery = Math.max(1, Math.ceil(nRows / 30));
    genres.forEach((gn, i) => {
        const yTop = padTop + rowH * i;
        if (i > 0) {
            g.append('line')
                .attr('x1', padLeft).attr('x2', padLeft + plotW)
                .attr('y1', yTop).attr('y2', yTop)
                .attr('stroke', PALETTE.borderColor)
                .attr('stroke-opacity', 0.35)
                .attr('stroke-dasharray', '3,4');
        }
        if (i % labelEvery === 0) {
            g.append('text')
                .attr('x', padLeft - 6)
                .attr('y', yTop + rowH / 2 + 3)
                .attr('text-anchor', 'end')
                .attr('font-family', "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif")
                .attr('font-size', 9)
                .attr('fill', PALETTE.textMuted)
                .text(gn.length > 18 ? gn.slice(0, 17) + '…' : gn);
        }
    });

    // ---- Points (pinned to exact follower count + rating band) ----
    const communitiesMeta = data.communities || {};
    const nodes = [...data.nodes].sort((a, b) => (a.followers || 0) - (b.followers || 0));

    const point = g.append('g')
        .attr('class', 'pop-points')
        .selectAll('g')
        .data(nodes)
        .join('g')
        .attr('class', 'node')
        .attr('transform', d => {
            const px = x(followersOf(d));
            // Within each genre row, the vertical position is a function of
            // the rating BAND (loved/liked/meh/disliked). Within a band the
            // points are spread a little by exact avg_rating so a 99-sitter
            // still sits slightly higher than a 90-sitter in the same band.
            const avg = Math.max(0, Math.min(100, d.avg_rating || 0));
            // Same linear rating->y contract as Genre & Taste mode: higher avg_rating
            // always maps to a smaller y (higher on screen) within the row's band.
            const bandH = rowH * 0.85;
            const py = rowCenter(d.genre) + (0.5 - avg / 100) * bandH;
            d.x = px; d.y = py;  // store pinned coords (tooltip/debug consistency)
            return `translate(${px},${py})`;
        });

    point.append('circle')
        .attr('r', d => nodeRadius(d.song_count || 1) * 1.2)
        .attr('fill', d => nodeColor(d))
        .attr('fill-opacity', 0.85)
        // Expose pinned coordinates for tooltip logic and debugging.
        .attr('stroke', d => {
            const avg = d.avg_rating || 0;
            if (avg >= 95) return PALETTE.rating100 + '80';
            if (avg >= 90) return PALETTE.rating90 + '80';
            return 'transparent';
        })
        .attr('stroke-width', d => d.avg_rating >= 90 ? 2 : 0);

    // Labels only for well-rated artists — anything denser is unreadable.
    point.filter(d => (d.song_count || 1) >= 10)
        .append('text')
        .text(d => d.name.length > 14 ? d.name.slice(0, 13) + '\u2026' : d.name)
        .attr('x', d => nodeRadius(d.song_count || 1) * 0.8 + 4)
        .attr('y', 3)
        .attr('font-size', 9)
        .attr('fill', PALETTE.textSecondary);

    // ---- Hover tooltip (same content as the force modes) ----
    point.on('mouseover', (event, d) => {
        let extra = '';
        const cid = d.community_id;
        if (cid !== undefined && cid !== null && cid >= 0) {
            const meta = communitiesMeta[String(cid)];
            if (meta) extra = `<br>Cluster: ${meta.dominant_genre || 'Group ' + cid} (${meta.size} artists)`;
        } else if (d.genre) {
            extra = `<br>Genre: ${d.genre}`;
        }
        const popLine = (d.followers !== undefined && d.followers !== null)
            ? `<br>Followers: ${_formatFollowers(Number(d.followers) > 0 ? Number(d.followers) : 1000)} (${d.followers_source || '?'})`
            : '';
        const songs = Array.isArray(d.top_songs) ? d.top_songs : [];
        // Song entries repeat the artist ("Toto – Africa") — strip the
        // "Artist - " prefix since the tooltip already names the artist.
        const artistPrefix = (d.name || '').toLowerCase() + ' ';
        const stripPrefix = (t) => {
            const s = String(t || '');
            const low = s.toLowerCase();
            const idx = low.indexOf(artistPrefix);
            return idx === 0
                ? s.slice(artistPrefix.length).replace(/^[–—-]\s*/, '')
                : s;
        };
        const songsLine = songs.length
            ? `<br><span class="tooltip-muted">Top songs:</span> ${songs.map(s => escapeHtml(stripPrefix(s.title))).join(' · ')}`
            : '';
        tooltip.innerHTML = `
            <span class="tooltip-muted">Artist:</span> <strong>${escapeHtml(d.name)}</strong><br>
            Avg rating: ${d.avg_rating || 'N/A'}/100<br>
            Songs rated: ${d.song_count || 0}<br>
            Best: ${d.max_rating || 'N/A'}/100${popLine}${extra}${songsLine}
        `;
        tooltip.style.left = (event.offsetX + 15) + 'px';
        tooltip.style.top = (event.offsetY - 10) + 'px';
        tooltip.classList.add('visible');
        d3.select(event.currentTarget).select('circle')
            .attr('stroke-width', 3)
            .attr('stroke', 'white');
    })
    .on('mousemove', (event) => {
        if (tooltip.classList.contains('visible')) {
            tooltip.style.left = (event.offsetX + 15) + 'px';
            tooltip.style.top = (event.offsetY - 10) + 'px';
        }
    })
    .on('mouseout', (event, d) => {
        tooltip.classList.remove('visible');
        d3.select(event.currentTarget).select('circle')
            .attr('stroke-width', d.avg_rating >= 90 ? 2 : 0)
            .attr('stroke', () => {
                const avg = d.avg_rating || 0;
                if (avg >= 95) return PALETTE.rating100 + '80';
                if (avg >= 90) return PALETTE.rating90 + '80';
                return 'transparent';
            });
    });
}

// ===================================================================
// Main render
// ===================================================================

function renderConstellation(data) {
    if (window.__d3Failed || typeof d3 === 'undefined') {
        console.warn('D3.js not available — constellation disabled');
        return;
    }
    // The three mode tabs live in the persistent global sub-nav (#constellationGlobalTabs)
    // above the views, so they stay reachable without re-navigating to the Constellation
    // page. Make sure it's visible now that constellation data is loaded.
    const globalTabsEl = document.getElementById('constellationGlobalTabs');
    if (globalTabsEl) globalTabsEl.classList.add('visible');
    const svgEl = document.getElementById('constellationSvg');
    const tooltip = document.getElementById('constellationTooltip');
    if (!svgEl) {
        console.warn('Constellation SVG element not found');
        return;
    }
    if (!data.nodes || data.nodes.length === 0) {
        svgEl.innerHTML = '<text x="50%" y="50%" fill="' + PALETTE.textMuted + '" font-size="14" text-anchor="middle">No artist data available</text>';
        return;
    }

    // Stop any previous simulation before re-rendering
    if (simulation) {
        simulation.stop();
        simulation = null;
    }

    // Legend
    _renderLegend(document.getElementById('constellationLegend'), data);

    // Dimensions
    const container = svgEl.parentElement;
    const width = container ? (container.clientWidth || 900) : 900;
    const height = container ? (container.clientHeight || 600) : 600;

    // Clear cached positions so the simulation recomputes from the centre —
    // needed when switching views but the JS objects are reused across renders.
    data.nodes.forEach(d => { d.x = width / 2; d.y = height / 2; });

    // Clear + set up D3
    svgEl.innerHTML = '';
    const svg = d3.select(svgEl)
        .attr('width', width)
        .attr('height', height);
    const g = svg.append('g');

    // Zoom range: 0.2× (see whole constellation) up to 10× (see individual nodes).
    // The Genre & Taste layout is scaled 5× wider (X) and 10× taller (Y) than the
    // raw 0..1 genre_x / 0..100 rating range, so zooming in reveals artist-level detail.
    const zoom = d3.zoom()
        .scaleExtent([0.2, 10])
        .on('zoom', (event) => { g.attr('transform', event.transform); });
    svg.call(zoom);
    svg.call(zoom.transform, d3.zoomIdentity);

    // Edges from API data
    const nodeMap = new Map(data.nodes.map(n => [n.id, n]));
    const linkSet = new Set();
    const links = [];
    for (const edge of (data.edges || [])) {
        const key = [edge.source, edge.target].sort().join('||');
        if (!linkSet.has(key) && nodeMap.has(edge.source) && nodeMap.has(edge.target)) {
            linkSet.add(key);
            links.push({ source: edge.source, target: edge.target });
        }
    }

    // Node radius
    const maxSongs = Math.max(...data.nodes.map(n => n.song_count || 1));
    const nodeRadius = d3.scaleSqrt().domain([1, maxSongs]).range([6, 24]);

    // Node colour — sentiment in genre/connections, community colour in
    // connections mode (handled inside nodeColor below).
    const nodeColor = (d) => {
        if (currentMode === 'connections') {
            // In connections mode, color by community for visual clustering
            const cid = d.community_id;
            if (cid !== undefined && cid !== null && cid >= 0) {
                return _communityColor(cid);
            }
        }
        // Genre & Taste mode: sentiment colors
        return _sentiment(d.avg_rating || 0).color;
    };

    // ---- Simulation forces ----
    // Created for all force modes (genre, connections). The followers chart
    // mode doesn't use it — its branch below stops the auto-started timer.
    const simulationForce = d3.forceSimulation(data.nodes)
        .force('link', d3.forceLink(links).id(d => d.id).distance(80).strength(0.3))
        .force('charge', d3.forceManyBody().strength(-120))
        .force('center', d3.forceCenter(width / 2, height / 2))
        .force('collision', d3.forceCollide().radius(d => nodeRadius(d) + 4));

    // Followers mode is a chart: deterministic positions, labeled axis,
    // no force simulation. Render it and skip the physics entirely.
    if (currentMode === 'followers') {
        // forceSimulation auto-starts its timer on creation — stop it, and kill
        // any animation loop left over from a previous force-mode render so it
        // can't overwrite the chart's pinned positions.
        simulationForce.stop();
        simulation = null;
        if (window.__constellationRaf) cancelAnimationFrame(window.__constellationRaf);
        window.__constellationRaf = null;
        _renderFollowersChart({ g, data, width, height, nodeRadius, nodeColor });
        return;
    }

    if (currentMode === 'connections') {
        // Artist Connections: pure edge-driven layout.
        // Only add a gentle vertical pull toward the community's center of mass
        // so clusters don't collapse into one blob.
        // Pre-compute community center-of-mass from initial positions.
        const communityCOM = {};
        data.nodes.forEach(d => {
            const cid = d.community_id;
            if (cid === undefined || cid === null || cid < 0) return;
            if (!communityCOM[cid]) communityCOM[cid] = { x: 0, y: 0, n: 0 };
            communityCOM[cid].x += d.x || width / 2;
            communityCOM[cid].y += d.y || height / 2;
            communityCOM[cid].n += 1;
        });
        Object.values(communityCOM).forEach(c => { c.x /= c.n; c.y /= c.n; });

        // Gentle pull toward community center (strength 0.15 — enough to
        // separate clusters but not fight the edge forces).
        simulationForce.force('communityX', d3.forceX(d => {
            const com = communityCOM[d.community_id];
            return com ? com.x : width / 2;
        }).strength(0.15));
        simulationForce.force('communityY', d3.forceY(d => {
            const com = communityCOM[d.community_id];
            return com ? com.y : height / 2;
        }).strength(0.15));

    }
    // NOTE: the 'followers' mode does NOT use the force simulation at all —
    // it renders a deterministic scatter chart in _renderFollowersChart().
    else {
        // Genre & Taste: genre SPECTRUM on X (similar genres share horizontal
        // spans left→right: Rap/Hip-Hop → R&B/Soul → Pop → K-Pop → J-Pop →
        // Jazz → Rock → Indie/Alternative → Punk → Metal → Electronic →
        // Folk/Acoustic → Country → Blues → Classical), and RATING on Y (highest
        // rated at top, lowest at bottom) across the full chart height.
        // Each genre gets a vertical column at its spectrum x-position; columns
        // have a fixed width so neighbouring genres can overlap slightly without
        // merging (the per-node name jitter keeps individual artists separable).
        // Deterministic layout (no physics) — the rating-on-top invariant is
        // guaranteed by construction, not by simulation convergence.
        simulationForce.stop();
        simulation = null;
        if (window.__constellationRaf) cancelAnimationFrame(window.__constellationRaf);
        window.__constellationRaf = null;
        const link = g.append('g')
            .selectAll('line')
            .data(links)
            .join('line')
            .attr('class', 'link')
            .attr('stroke', PALETTE.borderColor)
            .attr('stroke-width', 0.5)
            .attr('stroke-opacity', 0.15);
        // Genre columns live at their spectrum x-position; column width is a
        // fraction of the chart width / number of distinct genres, capped so
        // dense genres (Pop, Rock) still get readable columns.
        const genres = [...new Set(data.nodes.filter(n => n.genre).map(n => n.genre))].sort();
        const padL = width * 0.06, padR = width * 0.06;
        const plotW = width - padL - padR;
        const colW = Math.min(plotW / Math.max(1, genres.length), plotW * 0.18);
        const genreXMap = {};
        genres.forEach((gn) => {
            // genre_x comes from the API (taste_engine genres_spectrum_x); each node
            // carries its own genre_x so multi-genre artists could theoretically span
            // columns — but the current engine assigns one primary genre per artist.
            const sample = data.nodes.find(n => (n.genre || 'Uncategorized') === gn);
            genreXMap[gn] = (sample && sample.genre_x != null)
                ? sample.genre_x
                : 0.5;
        });
        const colX = (gn) => padL + genreXMap[gn] * plotW * 5;
        // Y axis: rating 0-100 mapped 10× across an extended height so zooming in
        // reveals individual artist separation. avg 100→top, avg 0→bottom of the
        // extended range. padT is the visual top anchor; everything above padT is
        // the "highest rated" region you zoom into.
        const padT = height * 0.10, padB = height * 0.06;
        const chartH = height - padT - padB;
        const yForRating = (avg) => {
            const a = Math.max(0, Math.min(100, Number(avg) || 0));
            return padT + chartH * (1 - a / 100) * 10;
        };
        _renderGenreTasteBands({
            g, data, width, height, genres, genreXMap, colW, colX, yForRating,
            padT, padB, chartH, nodeRadius, nodeColor, link,
            palette: PALETTE, sentiment: _sentiment, communityColor: _communityColor
        });
        return;
    }

    simulation = simulationForce;
    // Stop D3's built-in timer — we drive the loop manually via rAF.
    simulation.stop();

    // ---- Draw links ----
    const link = g.append('g')
        .selectAll('line')
        .data(links)
        .join('line')
        .attr('class', 'link')
        .attr('stroke', PALETTE.borderColor)
        .attr('stroke-width', 0.5)
        .attr('stroke-opacity', 0.15);

    // ---- Draw nodes ----
    const node = g.append('g')
        .selectAll('g')
        .data(data.nodes)
        .join('g')
        .attr('class', 'node')
        .call(d3.drag()
            .on('start', (event, d) => {
                if (!event.active) simulation.alphaTarget(0.3).restart();
                d.fx = d.x;
                d.fy = d.y;
            })
            .on('drag', (event, d) => {
                d.fx = event.x;
                d.fy = event.y;
            })
            .on('end', (event, d) => {
                if (!event.active) simulation.alphaTarget(0);
                d.fx = null;
                d.fy = null;
            })
        );

    node.append('circle')
        .attr('r', d => nodeRadius(d.song_count || 1))
        .attr('fill', d => nodeColor(d))
        .attr('stroke', d => {
            const avg = d.avg_rating || 0;
            if (avg >= 95) return PALETTE.rating100 + '80';
            if (avg >= 90) return PALETTE.rating90 + '80';
            return 'transparent';
        })
        .attr('stroke-width', d => d.avg_rating >= 90 ? 2 : 0);

    // Show name + rating labels for artists with 3+ songs;
    // all nodes have tooltip on hover for full details.
    node.filter(d => (d.song_count || 1) >= 3)
        .append('text')
        .text(d => {
            const name = d.name.length > 15 ? d.name.slice(0, 15) + '\u2026' : d.name;
            const avg = d.avg_rating ? Math.round(d.avg_rating) : '';
            return `${name} ${avg}`;
        })
        .attr('x', d => nodeRadius(d.song_count || 1) + 6)
        .attr('y', 4)
        .attr('font-family', "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif")
        .attr('font-size', d => Math.min(11, 9 + nodeRadius(d.song_count || 1) / 4) + 'px')
        .attr('fill', PALETTE.textSecondary);

    // ---- Hover / tooltip ----
    const communitiesMeta = data.communities || {};

    node.on('mouseover', (event, d) => {
        let extra = '';
        const cid = d.community_id;
        if (cid !== undefined && cid !== null && cid >= 0) {
            const meta = communitiesMeta[String(cid)];
            if (meta) {
                extra = `<br>Cluster: ${meta.dominant_genre || 'Group ' + cid} (${meta.size} artists)`;
            }
        } else if (d.genre) {
            extra = `<br>Genre: ${d.genre}`;
        }
        const popLine = (d.followers !== undefined && d.followers !== null)
            ? `<br>Followers: ${_formatFollowers(Number(d.followers) > 0 ? Number(d.followers) : 1000)} (${d.followers_source || '?'})`
            : '';
        const songs = Array.isArray(d.top_songs) ? d.top_songs : [];
        // Song entries repeat the artist ("Toto – Africa") — strip the
        // "Artist - " prefix since the tooltip already names the artist.
        const artistPrefix = (d.name || '').toLowerCase() + ' ';
        const stripPrefix = (t) => {
            const s = String(t || '');
            const low = s.toLowerCase();
            const idx = low.indexOf(artistPrefix);
            return idx === 0
                ? s.slice(artistPrefix.length).replace(/^[–—-]\s*/, '')
                : s;
        };
        const songsLine = songs.length
            ? `<br><span class="tooltip-muted">Top songs:</span> ${songs.map(s => escapeHtml(stripPrefix(s.title))).join(' · ')}`
            : '';
        tooltip.innerHTML = `
            <span class="tooltip-muted">Artist:</span> <strong>${escapeHtml(d.name)}</strong><br>
            Avg rating: ${d.avg_rating || 'N/A'}/100<br>
            Songs rated: ${d.song_count || 0}<br>
            Best: ${d.max_rating || 'N/A'}/100${popLine}${extra}${songsLine}
        `;
        tooltip.style.left = (event.offsetX + 15) + 'px';
        tooltip.style.top = (event.offsetY - 10) + 'px';
        tooltip.classList.add('visible');

        d3.select(event.currentTarget).select('circle')
            .attr('stroke-width', 3)
            .attr('stroke', 'white');
    })
    .on('mousemove', (event) => {
        if (tooltip.classList.contains('visible')) {
            tooltip.style.left = (event.offsetX + 15) + 'px';
            tooltip.style.top = (event.offsetY - 10) + 'px';
        }
    })
    .on('mouseout', (event) => {
        tooltip.classList.remove('visible');
        d3.select(event.currentTarget).select('circle')
            .attr('stroke-width', d => d.avg_rating >= 90 ? 2 : 0)
            .attr('stroke', d => {
                const avg = d.avg_rating || 0;
                if (avg >= 95) return PALETTE.rating100 + '80';
                if (avg >= 90) return PALETTE.rating90 + '80';
                return 'transparent';
            });
    });

    // ---- Animation loop ----
    let _tickRaf = null;
    function _tick() {
        if (!simulation || simulation.alpha < 0.001) return;
        simulation.tick();
        link
            .attr('x1', d => d.source.x)
            .attr('y1', d => d.source.y)
            .attr('x2', d => d.target.x)
            .attr('y2', d => d.target.y);
        const gNode = svgEl.querySelector('g');
        if (gNode) {
            gNode.querySelectorAll('g.node').forEach(el => {
                const d = el.__data__;
                if (d) el.setAttribute('transform', 'translate(' + d.x + ',' + d.y + ')');
            });
        }
        _tickRaf = requestAnimationFrame(_tick);
    }
    // Stop any previous animation loop from an earlier render.
    if (window.__constellationRaf) cancelAnimationFrame(window.__constellationRaf);
    window.__constellationRaf = _tickRaf = requestAnimationFrame(_tick);
    if (simulation) simulation.alpha(1).restart();
}

// ===================================================================
// Genre & Taste deterministic banded layout
// ===================================================================
// Each genre is a column; within the column, nodes are sorted into rating bands
// (loved/liked/meh/disliked) and placed at fixed y-offsets from the column's
// vertical center. Higher-rated bands sit above lower-rated bands by construction,
// so the "favorites on top, disliked on bottom" invariant always holds — no force
// simulation needed, no convergence race, no density-dependent inversion.
// ===================================================================

function _renderGenreTasteBands({ g, data, width, height, genres, genreXMap, colW, colX, yForRating, padT, padB, chartH, nodeRadius, nodeColor, link, palette, sentiment, communityColor }) {
    const communitiesMeta = data.communities || {};
    // Per-genre lists, each sorted by rating so the band placement is stable.
    const byGenre = {};
    data.nodes.forEach(n => {
        const g = n.genre || 'Uncategorized';
        (byGenre[g] = byGenre[g] || []).push(n);
    });

    // Draw genre column background rectangles (subtle, under the nodes).
    // Each genre column is centered at its spectrum x-position with fixed width.
    genres.forEach((gn) => {
        const cx = colX(gn);
        if (cx == null || isNaN(cx)) return;
        const nodesHere = byGenre[gn] || [];
        const hasLoved = nodesHere.some(n => (n.avg_rating || 0) >= 90);
        const hasLiked = nodesHere.some(n => (n.avg_rating || 0) >= 80 && (n.avg_rating || 0) < 90);
        const hasMeh = nodesHere.some(n => (n.avg_rating || 0) >= 70 && (n.avg_rating || 0) < 80);
        const hasDisliked = nodesHere.some(n => (n.avg_rating || 0) < 70);
        const bandKeys = [];
        if (hasLoved) bandKeys.push('loved');
        if (hasLiked) bandKeys.push('liked');
        if (hasMeh) bandKeys.push('meh');
        if (hasDisliked) bandKeys.push('disliked');

        // Stack band background rects from top to bottom across the extended height.
        // Each band gets a fraction of the extended chart height proportional to its
        // rating range (scaled 10× by yForRating).
        const bandRanges = [
            { key: 'loved',     min: 90, max: 100 },
            { key: 'liked',     min: 80, max: 90 },
            { key: 'meh',       min: 70, max: 80 },
            { key: 'disliked',  min: 0,  max: 70 },
        ];
        bandRanges.forEach(br => {
            if (!bandKeys.includes(br.key)) return;
            const yTop = yForRating(br.max);
            const yBot = yForRating(br.min);
            g.append('rect')
                .attr('x', cx - colW * 2.5)
                .attr('y', yTop)
                .attr('width', colW * 5)
                .attr('height', Math.max(0, yBot - yTop))
                .attr('fill', palette.bgSubtle || 'transparent')
                .attr('fill-opacity', 0.2)
                .attr('stroke', palette.borderColor)
                .attr('stroke-opacity', 0.1)
                .attr('stroke-width', 1);
        });

        // Genre column header label at the top of each column.
        // Positioned just above the chart area so users can see which genre each
        // vertical span belongs to. Font size scales with column width so narrow
        // columns (rare genres) don't overflow.
        const headerY = padT - 8;
        const headerFontSize = Math.max(9, Math.min(12, colW * 0.35));
        const headerLabel = gn.length > 20 ? gn.slice(0, 19) + '…' : gn;
        g.append('text')
            .attr('x', cx)
            .attr('y', headerY)
            .attr('text-anchor', 'middle')
            .attr('font-family', "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif")
            .attr('font-size', headerFontSize)
            .attr('font-weight', 600)
            .attr('fill', palette.textSecondary)
            .attr('stroke', palette.bgSubtle || 'white')
            .attr('stroke-width', 2)
            .attr('paint-order', 'stroke')
            .text(headerLabel);
    });

    // Sort all nodes by rating (descending) so higher-rated artists are drawn on top
    // and placed higher within their genre column.
    const sortedNodes = [...data.nodes].sort((a, b) => {
        const ra = Number(a.avg_rating) || 0;
        const rb = Number(b.avg_rating) || 0;
        return rb - ra;
    });

    const nodeG = g.append('g').selectAll('g')
        .data(sortedNodes)
        .join('g')
        .attr('class', 'node')
        .attr('transform', d => {
            const gn = d.genre || 'Uncategorized';
            const cx = colX(gn);
            const baseX = (cx != null && !isNaN(cx)) ? cx : (width / 2);
            // Horizontal jitter keeps artists in the same genre column from stacking
            // in a single pixel column; spread scales with the 5× wider columns.
            const px = baseX + _nameJitter(d.name, Math.max(4, colW * 0.2 * 5));
            // Vertical position: rating 0-100 mapped 10× across the extended height.
            // Higher-rated artists are ALWAYS above lower-rated ones.
            // Vertical jitter also scales so same-rating artists stay separable when
            // zoomed in.
            const py = yForRating(d.avg_rating) + _nameJitter(d.name + '|' + d.id, 10);
            d.x = px; d.y = py;
            return `translate(${px},${py})`;
        });

    // Draw links (edges) — same as before.
    link
        .attr('x1', d => d.source.x)
        .attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x)
        .attr('y2', d => d.target.y);

    // Node circles — slightly larger so they're more visible when zoomed in.
    nodeG.append('circle')
        .attr('r', d => nodeRadius(d.song_count || 1) * 1.2)
        .attr('fill', d => nodeColor(d))
        .attr('fill-opacity', 0.85)
        .attr('stroke', d => {
            const avg = d.avg_rating || 0;
            if (avg >= 95) return palette.rating100 + '80';
            if (avg >= 90) return palette.rating90 + '80';
            return 'transparent';
        })
        .attr('stroke-width', d => d.avg_rating >= 90 ? 2 : 0);

    // Labels for artists with 3+ songs.
    nodeG.filter(d => (d.song_count || 1) >= 3)
        .append('text')
        .text(d => {
            const name = d.name.length > 15 ? d.name.slice(0, 15) + '\u2026' : d.name;
            const avg = d.avg_rating ? Math.round(d.avg_rating) : '';
            return `${name} ${avg}`;
        })
        .attr('x', d => nodeRadius(d.song_count || 1) * 1.2 + 6)
        .attr('y', 4)
        .attr('font-family', "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif")
        .attr('font-size', d => Math.min(13, 10 + nodeRadius(d.song_count || 1) / 4) + 'px')
        .attr('fill', palette.textSecondary);

    // Hover / tooltip (same as before).
    nodeG.on('mouseover', (event, d) => {
        let extra = '';
        const cid = d.community_id;
        if (cid !== undefined && cid !== null && cid >= 0) {
            const meta = communitiesMeta[String(cid)];
            if (meta) extra = `<br>Cluster: ${meta.dominant_genre || 'Group ' + cid} (${meta.size} artists)`;
        } else if (d.genre) {
            extra = `<br>Genre: ${d.genre}`;
        }
        const popLine = (d.followers !== undefined && d.followers !== null)
            ? `<br>Followers: ${_formatFollowers(Number(d.followers) > 0 ? Number(d.followers) : 1000)} (${d.followers_source || '?'})`
            : '';
        const songs = Array.isArray(d.top_songs) ? d.top_songs : [];
        const artistPrefix = (d.name || '').toLowerCase() + ' ';
        const stripPrefix = (t) => {
            const s = String(t || '');
            const low = s.toLowerCase();
            const idx = low.indexOf(artistPrefix);
            return idx === 0
                ? s.slice(artistPrefix.length).replace(/^[–—-]\s*/, '')
                : s;
        };
        const songsLine = songs.length
            ? `<br><span class="tooltip-muted">Top songs:</span> ${songs.map(s => escapeHtml(stripPrefix(s.title))).join(' · ')}`
            : '';
        const tooltip = document.getElementById('constellationTooltip');
        tooltip.innerHTML = `
            <span class="tooltip-muted">Artist:</span> <strong>${escapeHtml(d.name)}</strong><br>
            Avg rating: ${d.avg_rating || 'N/A'}/100<br>
            Songs rated: ${d.song_count || 0}<br>
            Best: ${d.max_rating || 'N/A'}/100${popLine}${extra}${songsLine}
        `;
        tooltip.style.left = (event.offsetX + 15) + 'px';
        tooltip.style.top = (event.offsetY - 10) + 'px';
        tooltip.classList.add('visible');
        d3.select(event.currentTarget).select('circle')
            .attr('stroke-width', 3)
            .attr('stroke', 'white');
    })
    .on('mousemove', (event) => {
        const tooltip = document.getElementById('constellationTooltip');
        if (tooltip.classList.contains('visible')) {
            tooltip.style.left = (event.offsetX + 15) + 'px';
            tooltip.style.top = (event.offsetY - 10) + 'px';
        }
    })
    .on('mouseout', (event, d) => {
        const tooltip = document.getElementById('constellationTooltip');
        tooltip.classList.remove('visible');
        d3.select(event.currentTarget).select('circle')
            .attr('stroke-width', d.avg_rating >= 90 ? 2 : 0)
            .attr('stroke', d => {
                const avg = d.avg_rating || 0;
                if (avg >= 95) return palette.rating100 + '80';
                if (avg >= 90) return palette.rating90 + '80';
                return 'transparent';
            });
    });

    // Edges update (called from the animation loop, but since we're deterministic,
    // the positions don't change — still update once so links match node positions).
    link
        .attr('x1', d => d.source.x)
        .attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x)
        .attr('y2', d => d.target.y);
}
