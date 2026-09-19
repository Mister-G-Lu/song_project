/**
 * Unit tests for dashboard.js pure functions.
 *
 * Tests the genre filter toggle logic, chart model building, and
 * other pure functions that don't depend on DOM or Chart.js.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { setupDom, loadScript } from './setup.js';

beforeEach(() => {
    setupDom();
    window.loadLib = vi.fn().mockResolvedValue(true);
    window.PALETTE = {
        success: '#22c55e', warning: '#f59e0b', danger: '#ef4444',
        textMuted: '#94a3b8', bgPrimary: '#0f172a', rating100: '#fbbf24',
        rating90: '#34d399', rating80: '#60a5fa', rating70: '#c084fc'
    };
    window.CHART_THEME = {
        scales: { x: { ticks: {} }, y: { ticks: {} } },
        plugins: { tooltip: {} }
    };
    if (typeof window._filterGenreDistribution !== 'function') {
        loadScript('static/js/dashboard.js');
    }
});

/**
 * Trigger the genre filter toggle by clicking the button with the given
 * data-filter attribute.  This sets the module-level _genreFilterMode
 * variable that _filterGenreDistribution reads.
 */
function setFilterMode(mode) {
    // Create the toggle DOM if missing
    let toggle = document.getElementById('genreFilterToggle');
    if (!toggle) {
        toggle = document.createElement('div');
        toggle.id = 'genreFilterToggle';
        document.body.appendChild(toggle);
    }
    toggle.innerHTML = `
        <button class="genre-toggle-btn" data-filter="all">All</button>
        <button class="genre-toggle-btn" data-filter="liked90">90+</button>
    `;
    // Bind the real click handler (idempotent)
    if (!toggle.dataset.bound) {
        window._initGenreFilterToggle();
    }
    // Click the target button
    const btn = toggle.querySelector(`[data-filter="${mode}"]`);
    if (btn) btn.click();
}

describe('_filterGenreDistribution', () => {
    const genres = {
        'Pop': { count: 100, liked_70: 80, liked_90: 30, avg_rating: 75 },
        'Rock': { count: 50, liked_70: 40, liked_90: 10, avg_rating: 72 },
        'Rap': { count: 30, liked_70: 5, liked_90: 1, avg_rating: 45 },
        'Uncategorized': { count: 10, liked_70: 2, liked_90: 0, avg_rating: 60 }
    };

    it('returns all genres when filter is "all"', () => {
        setFilterMode('all');
        const result = window._filterGenreDistribution(genres);
        expect(Object.keys(result)).toHaveLength(4);
        expect(result['Pop'].count).toBe(100);
    });

    it('filters to liked_90 when filter is "liked90"', () => {
        setFilterMode('liked90');
        const result = window._filterGenreDistribution(genres);
        expect(result['Pop'].count).toBe(30);
        expect(result['Rock'].count).toBe(10);
        expect(result['Rap'].count).toBe(1);
    });

    it('excludes genres with zero count in filtered mode', () => {
        setFilterMode('liked90');
        const result = window._filterGenreDistribution(genres);
        expect(result['Uncategorized']).toBeUndefined();
    });

    it('handles empty genres object', () => {
        setFilterMode('liked90');
        const result = window._filterGenreDistribution({});
        expect(Object.keys(result)).toHaveLength(0);
    });

    it('handles missing liked fields gracefully', () => {
        setFilterMode('liked90');
        const sparse = { 'Pop': { count: 100 } };
        const result = window._filterGenreDistribution(sparse);
        // liked_90 is undefined, falls back to count
        expect(result['Pop'].count).toBe(100);
    });
});

describe('genreBreakdownModel', () => {
    it('returns labels, counts, colors, and labelToKey', () => {
        const genres = {
            'Pop': { count: 100, avg_rating: 75 },
            'Rock': { count: 50, avg_rating: 72 }
        };
        const model = window.genreBreakdownModel(genres);
        expect(model.labels).toBeDefined();
        expect(model.counts).toBeDefined();
        expect(model.colors).toBeDefined();
        expect(model.labelToKey).toBeDefined();
        expect(model.labels.length).toBe(2);
    });

    it('sorts genres by count descending', () => {
        const genres = {
            'Pop': { count: 100, avg_rating: 75 },
            'Rock': { count: 50, avg_rating: 72 },
            'Jazz': { count: 200, avg_rating: 80 }
        };
        const model = window.genreBreakdownModel(genres);
        expect(model.labels[0]).toBe('Jazz');
        expect(model.labels[1]).toBe('Pop');
        expect(model.labels[2]).toBe('Rock');
    });

    it('handles empty genres', () => {
        const model = window.genreBreakdownModel({});
        expect(model.labels).toHaveLength(0);
    });
});
