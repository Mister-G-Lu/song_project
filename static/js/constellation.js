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

function setConstellationMode(mode) {
    currentMode = mode;
    document.querySelectorAll('.mode-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.mode === mode);
    });
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

    // Legend
    _renderLegend(document.getElementById('constellationLegend'), data);

    // Dimensions
    const container = svgEl.parentElement;
    const width = container ? (container.clientWidth || 900) : 900;
    const height = container ? (container.clientHeight || 600) : 600;

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

    // Node colour function
    const nodeColor = (d) => {
        if (currentMode === 'genre' && d.genre && d.genre !== 'Uncategorized') {
            return genreColorMap[d.genre] || '#868e96';
        }
        // Unsorted mode → community colour
        const cid = d.community_id;
        if (cid !== undefined && cid !== null && cid >= 0) {
            return _communityColor(cid);
        }
        // Fallback: rating-based (isolated nodes)
        const avg = d.avg_rating || 0;
        if (avg >= 95) return PALETTE.rating100;
        if (avg >= 90) return PALETTE.rating90;
        if (avg >= 80) return PALETTE.rating80;
        if (avg >= 70) return PALETTE.rating70;
        if (avg > 0) return PALETTE.ratingLow;
        return PALETTE.borderColor;
    };

    // ---- Simulation forces ----
    const simulationForce = d3.forceSimulation(data.nodes)
        .force('link', d3.forceLink(links).id(d => d.id).distance(80).strength(0.3))
        .force('charge', d3.forceManyBody().strength(-120))
        .force('center', d3.forceCenter(width / 2, height / 2))
        .force('collision', d3.forceCollide().radius(d => nodeRadius(d) + 4));

    // ---- Clustering forces ----
    if (currentMode === 'genre') {
        // Genre-based (existing behaviour)
        const genres = [...new Set(data.nodes.filter(n => n.genre).map(n => n.genre))].sort();
        const genreCenters = {};
        const cols = Math.min(genres.length, 6);
        genres.forEach((g, i) => {
            const row = Math.floor(i / cols);
            const col = i % cols;
            genreCenters[g] = [
                width * 0.15 + (width * 0.7 / cols) * col,
                height * 0.15 + (height * 0.7 / Math.ceil(genres.length / cols)) * row
            ];
        });
        simulationForce.force('genreY', d3.forceY(d => {
            const center = genreCenters[d.genre || 'Uncategorized'];
            return center ? center[1] : height / 2;
        }).strength(0.6));
        simulationForce.force('genreX', d3.forceX(d => {
            const center = genreCenters[d.genre || 'Uncategorized'];
            return center ? center[0] : width / 2;
        }).strength(0.6));
    } else {
        // Community-based clustering (unsorted mode)
        const communities = data.communities || {};
        const cids = Object.keys(communities).map(Number).filter(cid => cid >= 0);
        if (cids.length > 1) {
            const commCenters = {};
            const cols = Math.min(cids.length, 7);
            cids.forEach((cid, i) => {
                const row = Math.floor(i / cols);
                const col = i % cols;
                commCenters[cid] = [
                    width * 0.12 + (width * 0.76 / cols) * col,
                    height * 0.12 + (height * 0.76 / Math.ceil(cids.length / cols)) * row
                ];
            });
            simulationForce.force('commY', d3.forceY(d => {
                const cid = d.community_id;
                const center = (cid !== undefined && cid !== null) ? commCenters[cid] : null;
                return center ? center[1] : height / 2;
            }).strength(0.5));
            simulationForce.force('commX', d3.forceX(d => {
                const cid = d.community_id;
                const center = (cid !== undefined && cid !== null) ? commCenters[cid] : null;
                return center ? center[0] : width / 2;
            }).strength(0.5));
        }
    }

    simulation = simulationForce;

    // ---- Draw links ----
    const link = g.append('g')
        .selectAll('line')
        .data(links)
        .join('line')
        .attr('class', 'link')
        .attr('stroke', PALETTE.borderColor)
        .attr('stroke-width', 0.5)
        .attr('stroke-opacity', 0.3);

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

    node.append('text')
        .text(d => d.name.length > 15 ? d.name.slice(0, 15) + '…' : d.name)
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

    // ---- Tick ----
    simulation.on('tick', () => {
        link
            .attr('x1', d => d.source.x)
            .attr('y1', d => d.source.y)
            .attr('x2', d => d.target.x)
            .attr('y2', d => d.target.y);
        node.attr('transform', d => `translate(${d.x}, ${d.y})`);
    });
}
