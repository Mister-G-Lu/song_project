/**
 * constellation.js - Artist constellation network graph using D3.js
 * Supports two modes:
 *   Unsorted (default) — community-based clustering forces. Artists are
 *     grouped by Louvain community detection on the backend (edges =
 *     collaborations + genre similarity + rating-pattern overlap). Each
 *     community gets a distinct color and clusters to its own area.
 *   Genre-sorted — genre-based clustering forces, colored by genre.
 */

let constellationData = null;
let simulation = null;
let currentMode = 'unsorted';

// --- Pre-computed colour palettes ---

/** 
 * 32 visually distinct categorical colours for D3.js community clusters.
 * These are intentionally hardcoded because D3 SVG fill attributes cannot
 * reference CSS var(). Each is chosen to be maximally distinguishable from
 * its neighbours — they are NOT theme colours and should NOT be moved to
 * variables.css. If you need to add more, use a colour-blind-safe palette.
 */
const COMMUNITY_COLORS = [
    '#e6194b', '#3cb44b', '#ffe119', '#4363d8', '#f58231', '#911eb4',
    '#42d4f4', '#f032e6', '#bfef45', '#fabed4', '#469990', '#dcbeff',
    '#9a6324', '#fffac8', '#800000', '#aaffc3', '#808000', '#ffd8b1',
    '#000075', '#a9a9a9', '#e6beff', '#ff6f00', '#008080', '#bcf60c',
    '#cd853f', '#7f6cf0', '#ff1493', '#00ced1', '#8b4513', '#6a5acd',
    '#20b2aa', '#dc1436'
];

let genreColorMap = {};

// ---- Sentiment (Liked/Disliked) — semantic colours, separate from the
// heat-scale rating palette. Higher value = greener (more loved); the intent
// is completely opposite to the red=hot heat convention. ----
const LOVED_COLOR   = '#2ec27e';
const LIKED_COLOR   = '#94d82d';
const MEH_COLOR     = '#a8adbe';
const DISLIKED_COLOR = '#e8590c';

// Returns a per-node sentiment bucket used by the "By Taste" mode.
function _sentiment(avg) {
    if (avg >= 90) return { key: 'loved',    label: 'Loved (90+)',   color: LOVED_COLOR,    dir: -0.5 };
    if (avg >= 80) return { key: 'liked',    label: 'Liked (80–89)', color: LIKED_COLOR,    dir: -1.0  };
    if (avg >= 70) return { key: 'meh',      label: 'Meh (70–79)',   color: MEH_COLOR,      dir: 0     };
    return            { key: 'disliked', label: 'Disliked (<70)', color: DISLIKED_COLOR, dir: 1     };
}

// ---- Distinct palette helpers ----

function _communityColor(communityId) {
    if (communityId < 0 || communityId === undefined || communityId === null) return PALETTE.borderColor;
    return COMMUNITY_COLORS[communityId % COMMUNITY_COLORS.length];
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
        console.error('Constellation load error:', err);
        document.querySelector('#view-constellation .constellation-container').innerHTML =
            '<div class="view-error"><span class="view-error-icon">⚠️</span><p>Failed to load constellation</p><button class="btn btn-outline" onclick="loadConstellation()">Retry</button></div>';
    }
}

const MODE_DESCRIPTIONS = {
    unsorted: 'Artists positioned by rating — <span style="color:var(--text-secondary)">↑ favorites</span> at top, <span style="color:var(--text-secondary)">↓ least favorites</span> at bottom',
    genre: 'Artists grouped into <span style="color:var(--text-secondary)">genre clusters</span> — see which genres dominate your collection',
    taste: 'Genre clusters split by taste — <span style="color:var(--text-secondary)">liked artists float up</span>, <span style="color:var(--text-secondary)">disliked sink down</span> within each genre'
};

function setConstellationMode(mode) {
    currentMode = mode;
    document.querySelectorAll('.mode-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.mode === mode);
    });
    const descEl = document.getElementById('constellationModeDesc');
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
// Legend rendering
// ===================================================================

function _renderLegend(legendEl, data) {
    if (!legendEl) return;

    if (currentMode === 'taste') {
        const items = [
            [LOVED_COLOR, 'Loved (90+)'], [LIKED_COLOR, 'Liked (80–89)'],
            [MEH_COLOR, 'Meh (70–79)'], [DISLIKED_COLOR, 'Disliked (<70)']
        ];
        legendEl.innerHTML = items.map(([c, l]) =>
            `<div class="legend-item"><span class="legend-dot" style="background:${c}"></span> ${l}</div>`
        ).join('') + `<span style="color:var(--text-muted);font-size:11px;margin-left:8px">groups split liked\u2197 / disliked\u2198 per genre</span>`;
        return;
    }

    if (currentMode === 'unsorted') {
        const items = [
            [LOVED_COLOR, 'Loved (90+)'], [LIKED_COLOR, 'Liked (80\u201389)'],
            [MEH_COLOR, 'Meh (70\u201379)'], [DISLIKED_COLOR, 'Disliked (<70)']
        ];
        legendEl.innerHTML = items.map(([c, l]) =>
            `<div class="legend-item"><span class="legend-dot" style="background:${c}"></span> ${l}</div>`
        ).join('') + `<span style="color:var(--text-muted);font-size:11px;margin-left:8px">\u2191 highest rated at top \u2193 lowest at bottom</span>`;
        return;
    }

    if (currentMode === 'genre') {
        const allGenres = [...new Set(data.nodes.filter(n => n.genre).map(n => n.genre))].sort();
        genreColorMap = {};
        allGenres.forEach((g, i) => {
            genreColorMap[g] = `hsl(${(i * 35 + 10) % 360}, 60%, 55%)`;
        });
        legendEl.innerHTML = allGenres.slice(0, 12).map(g =>
            `<div class="legend-item">
                <span class="legend-dot" style="background:${genreColorMap[g]}"></span> ${g}
            </div>`
        ).join('') + (allGenres.length > 12 ? `<span style="color:var(--text-muted);font-size:11px">+${allGenres.length - 12} more</span>` : '');
        return;
    }

    // --- Unsorted (community) legend ---
    const communities = data.communities || {};
    const entries = Object.entries(communities);
    if (entries.length === 0) {
        legendEl.innerHTML = '<span style="color:var(--text-muted);font-size:12px">No communities found</span>';
        return;
    }

    legendEl.innerHTML = entries.slice(0, 14).map(([cid, meta]) => {
        const color = _communityColor(Number(cid));
        const label = meta.dominant_genre !== 'Uncategorized' ? meta.dominant_genre
            : `Cluster ${cid}`;
        return `<div class="legend-item" title="${meta.top_artists.map(a => a.name).join(', ')}">
            <span class="legend-dot" style="background:${color}"></span>
            ${label}
            <span class="legend-count">${meta.size}</span>
        </div>`;
    }).join('') + (entries.length > 14
        ? `<span style="color:var(--text-muted);font-size:11px;margin-left:8px">+${entries.length - 14} more clusters</span>`
        : '');
}

// ===================================================================
// Main render
// ===================================================================

function renderConstellation(data) {
    if (window.__d3Failed || typeof d3 === 'undefined') {
        console.warn('D3.js not available — constellation disabled');
        return;
    }
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

    // Clear stale positions so new forces start from centre, not leftover
    // x/y from the previous mode's simulation.
    data.nodes.forEach(d => { d.x = width / 2; d.y = height / 2; });

    // Clear + set up D3
    svgEl.innerHTML = '';
    const svg = d3.select(svgEl)
        .attr('width', width)
        .attr('height', height);
    const g = svg.append('g');

    const zoom = d3.zoom()
        .scaleExtent([0.3, 4])
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

    // Node colour function — By Rating and By Taste both use sentiment colours;
    // By Genre uses genre colours; unsorted (community) uses community colours.
    const nodeColor = (d) => {
        if (currentMode === 'taste' || currentMode === 'unsorted') {
            const s = _sentiment(d.avg_rating || 0);
            return s.color;
        }
        if (currentMode === 'genre' && d.genre && d.genre !== 'Uncategorized') {
            return genreColorMap[d.genre] || PALETTE.ratingLow;
        }
        return PALETTE.borderColor;
    };

    // ---- Simulation forces ----
    const simulationForce = d3.forceSimulation(data.nodes)
        .force('link', d3.forceLink(links).id(d => d.id).distance(80).strength(0.3))
        .force('charge', d3.forceManyBody().strength(-120))
        .force('center', d3.forceCenter(width / 2, height / 2))
        .force('collision', d3.forceCollide().radius(d => nodeRadius(d) + 4));

    // ---- Clustering forces ----
    const genreCeil = (nodes) => [...new Set(nodes.filter(n => n.genre).map(n => n.genre))].sort();
    const buildGenreGrid = (genresIn) => {
        const centers = {};
        const cols = Math.min(genresIn.length, 6);
        genresIn.forEach((g, i) => {
            const row = Math.floor(i / cols);
            const col = i % cols;
            centers[g] = {
                x: width * 0.15 + (width * 0.7 / cols) * col,
                y: height * 0.15 + (height * 0.7 / Math.ceil(genresIn.length / cols)) * row
            };
        });
        return centers;
    };

    if (currentMode === 'taste') {
        // Like/unlike within each genre: liked↗ (!) disliked↘, meh stays put.
        const genres = genreCeil(data.nodes);
        const centers = buildGenreGrid(genres);
        const split = Math.max(22, Math.min(70, height / 9));
        simulationForce.force('tasteY', d3.forceY(d => {
            const c = centers[d.genre || 'Uncategorized'];
            if (!c) return height / 2;
            return c.y + _sentiment(d.avg_rating || 0).dir * split;
        }).strength(0.85));
        simulationForce.force('tasteX', d3.forceX(d => {
            const c = centers[d.genre || 'Uncategorized'];
            return c ? c.x : width / 2;
        }).strength(0.55));
    } else if (currentMode === 'genre') {
        // Genre-based (existing behaviour)
        const genres = genreCeil(data.nodes);
        const genreCenters = buildGenreGrid(genres);
        simulationForce.force('genreY', d3.forceY(d => {
            const center = genreCenters[d.genre || 'Uncategorized'];
            return center ? center.y : height / 2;
        }).strength(0.6));
        simulationForce.force('genreX', d3.forceX(d => {
            const center = genreCenters[d.genre || 'Uncategorized'];
            return center ? center.x : width / 2;
        }).strength(0.6));
    } else {
        // By Rating: vertical rating axis — highest rated at top, lowest at bottom.
        // Horizontal spread uses genre clusters so nodes don't pile up.
        const avgMin = Math.min(...data.nodes.map(n => n.avg_rating || 0));
        const avgMax = Math.max(...data.nodes.map(n => n.avg_rating || 0));
        const ratingRange = avgMax - avgMin || 1;
        // Seed initial x positions with jitter from genre so the vertical
        // bands spread horizontally by cluster rather than collapsing to centre.
        const _genreXMap = {};
        const _genres = [...new Set(data.nodes.filter(n => n.genre).map(n => n.genre))].sort();
        _genres.forEach((g, i) => { _genreXMap[g] = (i / Math.max(1, _genres.length - 1)); });
        data.nodes.forEach(d => {
            if (d.x === undefined || d.x === null || isNaN(d.x)) {
                d.x = (_genreXMap[d.genre || 'Uncategorized'] ?? 0.5) * width;
            }
            if (d.y === undefined || d.y === null || isNaN(d.y)) {
                const norm = 1 - ((d.avg_rating || 0) - avgMin) / ratingRange;
                d.y = height * 0.08 + norm * height * 0.84;
            }
        });
        simulationForce.force('ratingY', d3.forceY(d => {
            // invert: high rating → low y (top)
            const norm = 1 - ((d.avg_rating || 0) - avgMin) / ratingRange;
            return height * 0.08 + norm * height * 0.84;
        }).strength(0.9));
        simulationForce.force('ratingX', d3.forceX(d => {
            // Spread horizontally by genre so vertical rating bands don't collapse.
            const gx = _genreXMap[d.genre || 'Uncategorized'];
            return gx !== undefined ? width * 0.1 + gx * width * 0.8 : width / 2;
        }).strength(0.25));
    }

    simulation = simulationForce;
    // Stop D3's built-in timer — we drive the loop manually via rAF.
    simulation.stop();

    // ---- Draw links (hidden in By Rating mode — vertical position is the organising axis) ----
    const link = g.append('g')
        .selectAll('line')
        .data(links)
        .join('line')
        .attr('class', 'link')
        .attr('stroke', PALETTE.borderColor)
        .attr('stroke-width', 0.5)
        .attr('stroke-opacity', currentMode === 'unsorted' ? 0 : 0.15);

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

    // Only show name labels for artists with 3+ songs to reduce clutter;
    // all nodes have tooltip on hover for full details.
    node.filter(d => (d.song_count || 1) >= 3)
        .append('text')
        .text(d => {
            const name = d.name.length > 15 ? d.name.slice(0, 15) + '\u2026' : d.name;
            if (currentMode === 'unsorted') {
                const avg = d.avg_rating ? Math.round(d.avg_rating) : '';
                return `${name} ${avg}`;
            }
            return name;
        })
        .attr('x', d => nodeRadius(d.song_count || 1) + 6)
        .attr('y', 4)
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
        } else if (d.genre && currentMode === 'genre') {
            extra = `<br>Genre: ${d.genre}`;
        }
        tooltip.innerHTML = `
            <strong>${escapeHtml(d.name)}</strong><br>
            Avg rating: ${d.avg_rating || 'N/A'}/100<br>
            Songs rated: ${d.song_count || 0}<br>
            Best: ${d.max_rating || 'N/A'}/100${extra}
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
    // D3's built-in simulation timer (requestAnimationFrame) doesn't always
    // fire reliably after re-rendering (e.g. on mode switch).  Use an explicit
    // rAF loop that manually ticks the simulation and pushes node positions
    // into the DOM.
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
    simulation.alpha(1).restart();
}
