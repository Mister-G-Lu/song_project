/**
 * constellation.js - Artist constellation network graph using D3.js
 * Supports Unsorted (default) and Genre-sorted modes.
 */

let constellationData = null;
let simulation = null;
let currentMode = 'unsorted';
let genreColorMap = {}; // module-level: persists across re-renders within same data load

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
    // Update toggle buttons
    document.querySelectorAll('.mode-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.mode === mode);
    });
    // Show loading while re-rendering
    showViewLoading('view-constellation', '♻️ Reorganizing constellation...');
    // Use requestAnimationFrame to let the loading render before the heavy D3 work
    requestAnimationFrame(() => {
        if (constellationData) {
            renderConstellation(constellationData);
        }
        hideViewLoading('view-constellation');
    });
}

function renderConstellation(data) {
    const svgEl = document.getElementById('constellationSvg');
    const tooltip = document.getElementById('constellationTooltip');
    
    // Guard: SVG element must exist
    if (!svgEl) {
        console.warn('Constellation SVG element not found');
        return;
    }
    
    if (!data.nodes || data.nodes.length === 0) {
        svgEl.innerHTML = '<text x="50%" y="50%" fill="#606078" font-size="14" text-anchor="middle">No artist data available</text>';
        return;
    }

    // Build legend + pre-compute genre colour map
    const allGenres = [...new Set(data.nodes.filter(n => n.genre).map(n => n.genre))].sort();
    genreColorMap = {};
    allGenres.forEach((g, i) => {
        genreColorMap[g] = `hsl(${(i * 35 + 10) % 360}, 60%, 55%)`;
    });

    const legend = document.getElementById('constellationLegend');
    if (legend) {
        if (currentMode === 'genre') {
            legend.innerHTML = allGenres.slice(0, 12).map(g => 
                `<div class="legend-item">
                    <span class="legend-dot" style="background:${genreColorMap[g]}"></span> ${g}
                </div>`
            ).join('') + (allGenres.length > 12 ? `<span style="color:var(--text-muted);font-size:11px">+${allGenres.length - 12} more</span>` : '');
        } else {
            legend.innerHTML = `
                <div class="legend-item">
                    <span class="legend-dot" style="background:var(--rating-100)"></span> 95-100
                </div>
                <div class="legend-item">
                    <span class="legend-dot" style="background:var(--rating-90)"></span> 90-94
                </div>
                <div class="legend-item">
                    <span class="legend-dot" style="background:var(--rating-80)"></span> 80-89
                </div>
                <div class="legend-item">
                    <span class="legend-dot" style="background:var(--rating-70)"></span> &lt;80
                </div>
                <div class="legend-item">
                    <span class="legend-dot" style="background:var(--border-color)"></span> No rating
                </div>
            `;
        }
    }

    // Fallback dimension if parentElement is null (view not attached to DOM yet)
    const container = svgEl.parentElement;
    const width = container ? (container.clientWidth || 900) : 900;
    const height = container ? (container.clientHeight || 600) : 600;

    // Clear SVG and set up D3
    svgEl.innerHTML = '';
    const svg = d3.select(svgEl);
    const g = svg.append('g');  // zoom container group

    const zoom = d3.zoom()
        .scaleExtent([0.3, 4])
        .on('zoom', (event) => {
            g.attr('transform', event.transform);
        });

    svg.call(zoom);
    // Reset zoom transform so stale __zoom from previous render doesn't cause jumps
    svg.call(zoom.transform, d3.zoomIdentity);

    // Build links from co-occurrence data
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

    // Add similarity-based links for well-rated artists (helps graph cohere)
    const highRated = data.nodes.filter(n => n.avg_rating >= 80);
    for (let i = 0; i < highRated.length; i++) {
        for (let j = i + 1; j < highRated.length; j++) {
            const key = [highRated[i].id, highRated[j].id].sort().join('||');
            if (!linkSet.has(key) && Math.abs(highRated[i].avg_rating - highRated[j].avg_rating) < 10) {
                linkSet.add(key);
                links.push({ source: highRated[i].id, target: highRated[j].id });
            }
        }
    }

    // Size nodes by song count
    const maxSongs = Math.max(...data.nodes.map(n => n.song_count || 1));
    const nodeRadius = d3.scaleSqrt().domain([1, maxSongs]).range([6, 24]);

    const nodeColor = (d) => {
        if (currentMode === 'genre' && d.genre && d.genre !== 'Uncategorized') {
            return genreColorMap[d.genre] || '#868e96';
        }
        const avg = d.avg_rating || 0;
        if (avg >= 95) return '#ff6b6b';
        if (avg >= 90) return '#ffd43b';
        if (avg >= 80) return '#69db7c';
        if (avg >= 70) return '#74c0fc';
        if (avg > 0) return '#868e96';
        return '#2a2a3e';
    };

    // Simulation with optional genre-based clustering
    const simulationForce = d3.forceSimulation(data.nodes)
        .force('link', d3.forceLink(links).id(d => d.id).distance(80).strength(0.3))
        .force('charge', d3.forceManyBody().strength(-120))
        .force('center', d3.forceCenter(width / 2, height / 2))
        .force('collision', d3.forceCollide().radius(d => nodeRadius(d) + 4));

    // Add genre clustering force when in genre mode
    if (currentMode === 'genre') {
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
        
        simulationForce.force('genre', d3.forceY(d => {
            const center = genreCenters[d.genre || 'Uncategorized'];
            return center ? center[1] : height / 2;
        }).strength(0.6));
        
        simulationForce.force('genreX', d3.forceX(d => {
            const center = genreCenters[d.genre || 'Uncategorized'];
            return center ? center[0] : width / 2;
        }).strength(0.6));
    }
    
    simulation = simulationForce;

    // Draw links
    const link = g.append('g')
        .selectAll('line')
        .data(links)
        .join('line')
        .attr('class', 'link')
        .attr('stroke', '#2a2a3e')
        .attr('stroke-width', 0.5)
        .attr('stroke-opacity', 0.3);

    // Draw nodes
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
            if (avg >= 95) return '#ff6b6b80';
            if (avg >= 90) return '#ffd43b80';
            return 'transparent';
        })
        .attr('stroke-width', d => d.avg_rating >= 90 ? 2 : 0);

    node.append('text')
        .text(d => d.name.length > 15 ? d.name.slice(0, 15) + '…' : d.name)
        .attr('x', d => nodeRadius(d.song_count || 1) + 6)
        .attr('y', 4)
        .attr('font-size', d => Math.min(11, 9 + nodeRadius(d.song_count || 1) / 4) + 'px');

    // Hover effects with a small delay to avoid flicker
    let tooltipHoverTimer = null;
    node.on('mouseover', (event, d) => {
        clearTimeout(tooltipHoverTimer);
        tooltip.classList.remove('visible');
        tooltipHoverTimer = setTimeout(() => {
            tooltip.innerHTML = `
                <strong>${escapeHtml(d.name)}</strong><br>
                Avg rating: ${d.avg_rating || 'N/A'}/100<br>
                Songs rated: ${d.song_count || 0}<br>
                Best: ${d.max_rating || 'N/A'}/100
            `;
            tooltip.style.left = (event.offsetX + 15) + 'px';
            tooltip.style.top = (event.offsetY - 10) + 'px';
            tooltip.classList.add('visible');
        }, 150);

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
        clearTimeout(tooltipHoverTimer);
        tooltipHoverTimer = setTimeout(() => {
            tooltip.classList.remove('visible');
        }, 200);
        d3.select(event.currentTarget).select('circle')
            .attr('stroke-width', d => d.avg_rating >= 90 ? 2 : 0)
            .attr('stroke', d => {
                const avg = d.avg_rating || 0;
                if (avg >= 95) return '#ff6b6b80';
                if (avg >= 90) return '#ffd43b80';
                return 'transparent';
            });
    });

    // Simulation tick
    simulation.on('tick', () => {
        link
            .attr('x1', d => d.source.x)
            .attr('y1', d => d.source.y)
            .attr('x2', d => d.target.x)
            .attr('y2', d => d.target.y);

        node.attr('transform', d => `translate(${d.x}, ${d.y})`);
    });
}
