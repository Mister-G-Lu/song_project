/**
 * Tests for utils.js view lifecycle: switchView (nav/aria/legacy redirects/
 * lazy loading), refreshActiveViews, and searchSpotifyTrack.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { setupDom } from './setup.js';

/** Minimal app shell: nav + one view section per name. */
function appShell(...views) {
    document.body.innerHTML = `
        <div id="toast"></div>
        <nav>
            ${views.map(v => `
                <a href="#" class="nav-item" data-view="${v}">
                    <span class="nav-label">${v}</span>
                </a>`).join('')}
        </nav>
        ${views.map(v => `<section class="view" id="view-${v}"></section>`).join('')}
    `;
}

describe('switchView (utils.js)', () => {
    beforeEach(() => setupDom());

    it('activates the target view, nav state, and aria-current', () => {
        appShell('dashboard', 'history');
        window.loadSongs = vi.fn(); // switchView('history') lazy-loads
        document.getElementById('view-dashboard').classList.add('active');

        window.switchView('history');

        expect(document.getElementById('view-history').classList.contains('active')).toBe(true);
        expect(document.getElementById('view-dashboard').classList.contains('active')).toBe(false);
        const activeNav = document.querySelector('.nav-item[data-view="history"]');
        expect(activeNav.classList.contains('active')).toBe(true);
        expect(activeNav.getAttribute('aria-current')).toBe('page');
        const inactiveNav = document.querySelector('.nav-item[data-view="dashboard"]');
        expect(inactiveNav.hasAttribute('aria-current')).toBe(false);
    });

    it('ignores unknown view names', () => {
        const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
        appShell('dashboard');
        window.switchView('nope');
        expect(document.querySelectorAll('.view.active')).toHaveLength(0);
        expect(warn).toHaveBeenCalled();
        warn.mockRestore();
    });

    it('redirects legacy weekly → discover', () => {
        appShell('dashboard', 'discover');
        window.loadDiscover = vi.fn(); // discover tab lazy-load on first show
        window.switchView('weekly');
        expect(document.getElementById('view-discover').classList.contains('active')).toBe(true);
    });

    it('redirects legacy challenge → discover and opens the challenge tab', () => {
        appShell('dashboard', 'discover');
        window.loadDiscover = vi.fn();
        window.loadChallenges = vi.fn();
        window.setDiscoverTab = vi.fn();
        window.switchView('challenge');
        expect(document.getElementById('view-discover').classList.contains('active')).toBe(true);
        expect(window.setDiscoverTab).toHaveBeenCalledWith('challenge');
    });

    it('lazy-loads history every time it becomes active', () => {
        appShell('history');
        window.loadSongs = vi.fn();
        window.switchView('history');
        expect(window.loadSongs).toHaveBeenCalledWith(true);
    });

    it('lazy-loads evolution only until data exists', () => {
        appShell('evolution');
        window.loadEvolution = vi.fn();
        window.switchView('evolution');
        expect(window.loadEvolution).toHaveBeenCalledTimes(1);
        window.evolutionData = { some: 'data' };
        window.switchView('evolution');
        expect(window.loadEvolution).toHaveBeenCalledTimes(1); // cached, no refetch
        delete window.evolutionData;
    });

    it('lazy-loads dashboard when stats are still placeholders', () => {
        appShell('dashboard');
        document.body.innerHTML += '<div id="statTotal">-</div>';
        window.loadDashboard = vi.fn();
        window.switchView('dashboard');
        expect(window.loadDashboard).toHaveBeenCalledTimes(1);
        // Already populated → no refetch on revisit
        document.getElementById('statTotal').textContent = '5558';
        window.switchView('dashboard');
        expect(window.loadDashboard).toHaveBeenCalledTimes(1);
    });

    it('outliers delegates to the dashboard view', () => {
        appShell('dashboard', 'outliers');
        window.loadDashboard = vi.fn();
        window.switchView('outliers');
        expect(window.loadDashboard).toHaveBeenCalled();
    });
});

describe('refreshActiveViews (utils.js)', () => {
    beforeEach(() => {
        setupDom();
        // refreshActiveViews builds its view map eagerly, referencing every
        // view's loader — all must exist in the test environment.
        window.loadDashboard = vi.fn();
        window.loadDiscover = vi.fn();
        window.loadChallenges = vi.fn();
        window.loadRecommender = vi.fn();
        window.loadBlindSpots = vi.fn();
        window.loadOutliers = vi.fn();
        window.loadConstellation = vi.fn();
        window.loadEvolution = vi.fn();
    });

    it('refreshes only active views that already have content', () => {
        vi.useFakeTimers();
        appShell('recommender', 'evolution');
        document.getElementById('view-recommender').classList.add('active');
        document.getElementById('view-evolution').classList.add('active');
        // recommender has loaded content; evolution is active but never loaded
        document.getElementById('view-recommender').innerHTML = '<div class="rec-category">x</div>';

        window.loadRecommender = vi.fn();
        window.loadEvolution = vi.fn();
        window.refreshActiveViews();
        vi.advanceTimersByTime(400);

        expect(window.loadRecommender).toHaveBeenCalledTimes(1);
        expect(window.loadEvolution).not.toHaveBeenCalled();
        vi.useRealTimers();
    });

    it('refreshes data-var-backed views when the data exists', () => {
        vi.useFakeTimers();
        appShell('evolution');
        document.getElementById('view-evolution').classList.add('active');
        window.evolutionData = { ok: 1 };
        window.loadEvolution = vi.fn();
        window.refreshActiveViews();
        vi.advanceTimersByTime(400);
        expect(window.loadEvolution).toHaveBeenCalledTimes(1);
        delete window.evolutionData;
        vi.useRealTimers();
    });

    it('skips inactive views entirely', () => {
        vi.useFakeTimers();
        appShell('recommender');
        document.getElementById('view-recommender').innerHTML = '<div class="rec-category">x</div>';
        window.loadRecommender = vi.fn();
        window.refreshActiveViews();
        vi.advanceTimersByTime(400);
        expect(window.loadRecommender).not.toHaveBeenCalled();
        vi.useRealTimers();
    });
});

describe('searchSpotifyTrack (utils.js)', () => {
    beforeEach(() => {
        setupDom();
        document.body.innerHTML = '<div id="toast"></div>';
    });

    it('opens the API external_url when available', async () => {
        const open = vi.fn();
        vi.stubGlobal('open', open);
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
            json: async () => ({ external_url: 'https://open.spotify.com/track/x' }),
        }));
        await window.searchSpotifyTrack('A', 'S');
        expect(open).toHaveBeenCalledWith('https://open.spotify.com/track/x', '_blank', 'noopener,noreferrer');
        vi.unstubAllGlobals();
    });

    it('falls back to a combined title+artist query when the first misses', async () => {
        const open = vi.fn();
        vi.stubGlobal('open', open);
        vi.stubGlobal('fetch', vi.fn()
            .mockResolvedValueOnce({ json: async () => ({}) })
            .mockResolvedValueOnce({ json: async () => ({ external_url: 'https://x/2' }) }));
        await window.searchSpotifyTrack('A', 'S');
        expect(open).toHaveBeenCalledWith('https://x/2', '_blank', 'noopener,noreferrer');
        vi.unstubAllGlobals();
    });

    it('shows a friendly toast when nothing is found', async () => {
        vi.stubGlobal('open', vi.fn());
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ json: async () => ({}) }));
        await window.searchSpotifyTrack('A', 'S');
        expect(document.getElementById('toast').textContent)
            .toContain("Couldn't find on Spotify");
        vi.unstubAllGlobals();
    });

    it('never throws on network errors', async () => {
        vi.stubGlobal('open', vi.fn());
        vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));
        await expect(window.searchSpotifyTrack('A', 'S')).resolves.toBeUndefined();
        expect(document.getElementById('toast').textContent).toContain('unavailable');
        vi.unstubAllGlobals();
    });
});
