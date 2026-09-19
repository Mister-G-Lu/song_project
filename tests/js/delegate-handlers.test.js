/**
 * Contract test: EVERY action registered in delegate-handlers.js must be
 * dispatchable. Each row stubs the view-layer globals the handler delegates
 * to, fires the real DOM event through the delegated listeners, and asserts
 * the underlying function was called with the expected arguments.
 *
 * This doubles as full-registry coverage and as a safety net: adding a
 * data-action in markup without registering it fails the static-markup list
 * in hardening.test.js; registering one without a dispatch row fails here.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { setupDom, click, button } from './setup.js';

/** Fire the event type matching the data attribute under test. */
function fireEvent(el, attr) {
    switch (attr) {
        case 'data-change-action':
            el.dispatchEvent(new Event('change', { bubbles: true }));
            break;
        case 'data-input-action':
            el.dispatchEvent(new Event('input', { bubbles: true }));
            break;
        case 'data-keydown-action':
            el.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true, key: 'Enter' }));
            break;
        case 'data-submit-action':
            el.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
            break;
        default:
            click(el);
    }
}

/**
 * Create an element with the given data attrs and dispatch the event.
 * @returns {{el: Element, spy: function}} the element and the stubbed global
 */
function dispatchAction(attr, attrs) {
    const all = { [attr]: attrs[attr] };
    for (const [k, v] of Object.entries(attrs)) {
        if (k !== attr) all[k] = v;
    }
    const el = button(all);
    fireEvent(el, attr);
    return el;
}

describe('full registry dispatch contract (delegate-handlers.js)', () => {
    let spies;

    beforeEach(() => {
        setupDom();
        // Stub every view-layer global the handlers delegate to. One shared
        // table so a missing global fails loudly at its dispatch row.
        spies = {
            switchView: vi.fn(),
            loadYearConquest: vi.fn(),
            applyBackfill: vi.fn(),
            refreshBackfillPreview: vi.fn(),
            quickAddFromConquest: vi.fn(),
            selectGenreLegend: vi.fn(),
            addBanItem: vi.fn(),
            removeBanItem: vi.fn(),
            lockAutoSuppression: vi.fn(),
            refreshRecommendations: vi.fn(),
            toggleReverseMe: vi.fn(),
            loadRecommender: vi.fn(),
            toggleListenedButton: vi.fn(),
            ignoreSong: vi.fn(),
            searchSpotifyTrack: vi.fn(),
            quickAddFromRecommender: vi.fn(),
            loadChallenges: vi.fn(),
            switchChallengeMode: vi.fn(),
            updateThreshold: vi.fn(),
            setDiscoverTab: vi.fn(),
            setDiscoverMode: vi.fn(),
            refreshDiscover: vi.fn(),
            loadDiscover: vi.fn(),
            exploreFromArtist: vi.fn(),
            clearDiscoverSeed: vi.fn(),
            onDiscoverSeedKey: vi.fn(),
            toggleFreshReleases: vi.fn(),
            loadSongs: vi.fn(),
            loadMoreSongs: vi.fn(),
            searchHistory: vi.fn(),
            debounceSearch: vi.fn(),
            loadEvolution: vi.fn(),
            toggleReleaseYearShowAll: vi.fn(),
            sortReleaseYearBy: vi.fn(),
            setReleaseYearChartMode: vi.fn(),
            updateGenreEvolutionChart: vi.fn(),
            loadConstellation: vi.fn(),
            setConstellationMode: vi.fn(),
            closeUncategorizedBreakdown: vi.fn(),
            openQuickAdd: vi.fn(),
            closeQuickAdd: vi.fn(),
            resetQuickAddForm: vi.fn(),
            submitQuickAdd: vi.fn(),
            _selectArtist: vi.fn(),
            filterInfluences: vi.fn(),
            scoreFit: vi.fn(),
        };
        for (const [name, spy] of Object.entries(spies)) {
            window[name] = spy;
        }
    });

    // [attr, attrs, expectedGlobalCall]
    const CASES = [
        // --- Navigation ------------------------------------------------
        ['data-action', { 'data-action': 'switchView', 'data-view': 'evolution' },
            ['switchView', ['evolution']]],
        // --- Generic UI ------------------------------------------------
        ['data-action', { 'data-action': 'toggleCollapsed', 'data-toggle-selector': '.card' },
            null], // custom assertion below
        ['data-action', { 'data-action': 'toggleNextSibling' }, null],
        ['data-action', { 'data-action': 'quickAddOverlayClick' }, null],
        // --- Dashboard / backfill / conquest ------------------------------
        ['data-action', { 'data-action': 'loadYearConquest' }, ['loadYearConquest', []]],
        ['data-action', { 'data-action': 'applyBackfill' }, ['applyBackfill', []]],
        ['data-action', { 'data-action': 'refreshBackfillPreview' }, ['refreshBackfillPreview', []]],
        ['data-action', { 'data-action': 'toggleDecadeExpand' }, null],
        ['data-action', { 'data-action': 'quickAddFromConquest', 'data-artist': 'A', 'data-song': 'S' },
            ['quickAddFromConquest', ['A', 'S']]],
        ['data-action', { 'data-action': 'selectGenreLegend', 'data-genre-js-key': 'k' },
            ['selectGenreLegend', ['k']]],
        ['data-action', { 'data-action': 'addBanItem' }, ['addBanItem', []]],
        ['data-keydown-action', { 'data-keydown-action': 'banValueEnter' }, null],
        ['data-action', { 'data-action': 'removeBanItem', 'data-ban-type': 'genres', 'data-ban-value': 'v' },
            ['removeBanItem', ['genres', 'v']]],
        ['data-action', { 'data-action': 'lockAutoSuppression', 'data-ban-type': 'artists', 'data-ban-value': 'a' },
            ['lockAutoSuppression', ['artists', 'a']]],
        // --- Recommender --------------------------------------------------
        ['data-action', { 'data-action': 'refreshRecommendations' }, ['refreshRecommendations', []]],
        ['data-action', { 'data-action': 'toggleReverseMe' }, ['toggleReverseMe', []]],
        ['data-action', { 'data-action': 'loadRecommender' }, ['loadRecommender', []]],
        ['data-action', { 'data-action': 'toggleListened', 'data-artist': 'A', 'data-song': 'S', 'data-listened': 'true' },
            ['toggleListenedButton', [expect.anything(), 'A', 'S', true]]],
        ['data-action', { 'data-action': 'ignoreSong', 'data-artist': 'A', 'data-song': 'S' },
            ['ignoreSong', [expect.anything(), 'A', 'S']]],
        ['data-action', { 'data-action': 'searchSpotifyTrack', 'data-artist': 'A', 'data-song': 'S' },
            ['searchSpotifyTrack', ['A', 'S']]],
        ['data-action', { 'data-action': 'quickAddFromRecommender', 'data-artist': 'A', 'data-song': 'S', 'data-source': 'recommender' },
            ['quickAddFromRecommender', ['A', 'S', 'recommender']]],
        // --- Challenges ----------------------------------------------------
        ['data-action', { 'data-action': 'loadChallenges' }, ['loadChallenges', []]],
        ['data-action', { 'data-action': 'switchChallengeMode', 'data-mode': 'obscure' },
            ['switchChallengeMode', ['obscure']]],
        ['data-input-action', { 'data-input-action': 'updateThreshold', 'data-value-attr': 'value', 'value': '65' },
            ['updateThreshold', ['65']]],
        // --- Discover --------------------------------------------------------
        ['data-action', { 'data-action': 'setDiscoverTab', 'data-tab': 'challenge' },
            ['setDiscoverTab', ['challenge']]],
        ['data-action', { 'data-action': 'setDiscoverTabChallenge' }, ['setDiscoverTab', ['challenge']]],
        ['data-action', { 'data-action': 'setDiscoverMode', 'data-mode': 'hard' },
            ['setDiscoverMode', ['hard']]],
        ['data-action', { 'data-action': 'refreshDiscover' }, ['refreshDiscover', []]],
        ['data-action', { 'data-action': 'loadDiscoverForce' }, ['loadDiscover', [true]]],
        ['data-action', { 'data-action': 'exploreFromArtist', 'data-artist': 'Caravan Palace' },
            ['exploreFromArtist', ['Caravan Palace']]],
        ['data-action', { 'data-action': 'clearDiscoverSeed' }, ['clearDiscoverSeed', []]],
        ['data-keydown-action', { 'data-keydown-action': 'onDiscoverSeedKey' }, null],
        ['data-action', { 'data-action': 'discoverSeedGo' }, null],
        ['data-action', { 'data-action': 'toggleFreshReleases' }, null],
        ['data-action', { 'data-action': 'gotoChallenges' }, ['switchView', ['challenge']]],
        // --- History -------------------------------------------------------------
        ['data-action', { 'data-action': 'loadSongs' }, ['loadSongs', []]],
        ['data-action', { 'data-action': 'retryLoadSongs' }, ['loadSongs', [true]]],
        ['data-action', { 'data-action': 'loadMoreSongs' }, ['loadMoreSongs', []]],
        ['data-action', { 'data-action': 'searchHistory' }, ['searchHistory', []]],
        ['data-input-action', { 'data-input-action': 'debounceSearch' }, ['debounceSearch', []]],
        // --- Evolution ---------------------------------------------------------------
        ['data-action', { 'data-action': 'loadEvolution' }, ['loadEvolution', []]],
        ['data-action', { 'data-action': 'toggleReleaseYearShowAll' }, ['toggleReleaseYearShowAll', []]],
        ['data-action', { 'data-action': 'sortReleaseYearBy', 'data-sort-key': 'count' },
            ['sortReleaseYearBy', ['count']]],
        ['data-action', { 'data-action': 'setReleaseYearChartMode', 'data-ry-mode': 'avg' },
            ['setReleaseYearChartMode', ['avg']]],
        ['data-change-action', { 'data-change-action': 'updateGenreEvolutionChart' },
            ['updateGenreEvolutionChart', []]],
        // --- Constellation ---------------------------------------------------------------
        ['data-action', { 'data-action': 'loadConstellation' }, ['loadConstellation', []]],
        ['data-action', { 'data-action': 'setConstellationMode', 'data-mode': 'followers' },
            ['setConstellationMode', ['followers']]],
        ['data-action', { 'data-action': 'closeUncategorizedBreakdown' },
            ['closeUncategorizedBreakdown', []]],
        // --- Quick-add modal ----------------------------------------------------------------
        ['data-action', { 'data-action': 'openQuickAdd' }, ['openQuickAdd', []]],
        ['data-action', { 'data-action': 'closeQuickAdd' }, ['closeQuickAdd', []]],
        ['data-action', { 'data-action': 'resetQuickAddForm' }, ['resetQuickAddForm', []]],
        ['data-submit-action', { 'data-submit-action': 'submitQuickAdd' }, null],
        ['data-action', { 'data-action': '_selectArtist', 'data-artist-name': 'Tuyu' },
            ['_selectArtist', ['Tuyu']]],
        ['data-input-action', { 'data-input-action': 'filterInfluences' }, ['filterInfluences', []]],
        ['data-action', { 'data-action': 'scoreFit' }, ['scoreFit', []]],
    ];

    it.each(CASES)('dispatches %j', (attr, attrs, expected) => {
        dispatchAction(attr, attrs);
        if (!expected) return; // custom assertions below
        const [fnName, args] = expected;
        expect(spies[fnName]).toHaveBeenCalledTimes(1);
        expect(spies[fnName]).toHaveBeenCalledWith(...args);
    });

    // --- Handlers with structural assertions -------------------------------

    it('toggleCollapsed toggles the closest matching scope', () => {
        const card = document.createElement('div');
        card.className = 'card collapsed';
        const header = document.createElement('h3');
        header.setAttribute('data-action', 'toggleCollapsed');
        header.setAttribute('data-toggle-selector', '.card');
        card.appendChild(header);
        document.body.appendChild(card);
        click(header);
        expect(card.classList.contains('collapsed')).toBe(false);
    });

    it('toggleNextSibling toggles the element after the header', () => {
        const h = button({ 'data-action': 'toggleNextSibling' });
        const body = document.createElement('div');
        body.className = 'collapsed';
        h.after(body);
        click(h);
        expect(body.classList.contains('collapsed')).toBe(false);
    });

    it('quickAddOverlayClick closes only when the overlay itself is the target', () => {
        const overlay = button({ 'data-action': 'quickAddOverlayClick' });
        const inner = document.createElement('span');
        overlay.appendChild(inner);
        click(inner);
        expect(spies.closeQuickAdd).not.toHaveBeenCalled();
        click(overlay);
        expect(spies.closeQuickAdd).toHaveBeenCalledTimes(1);
    });

    it('toggleDecadeExpand toggles the enclosing .conquest-decade', () => {
        const decade = document.createElement('div');
        decade.className = 'conquest-decade';
        const header = document.createElement('div');
        header.setAttribute('data-action', 'toggleDecadeExpand');
        decade.appendChild(header);
        document.body.appendChild(decade);
        click(header);
        expect(decade.classList.contains('expanded')).toBe(true);
    });

    it('banValueEnter triggers addBanItem only for Enter', () => {
        const input = document.createElement('input');
        input.setAttribute('data-keydown-action', 'banValueEnter');
        document.body.appendChild(input);
        input.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true, key: 'a' }));
        expect(spies.addBanItem).not.toHaveBeenCalled();
        input.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true, key: 'Enter' }));
        expect(spies.addBanItem).toHaveBeenCalledTimes(1);
    });

    it('onDiscoverSeedKey forwards the event', () => {
        const input = document.createElement('input');
        input.setAttribute('data-keydown-action', 'onDiscoverSeedKey');
        document.body.appendChild(input);
        const evt = new KeyboardEvent('keydown', { bubbles: true, key: 'Enter' });
        input.dispatchEvent(evt);
        expect(spies.onDiscoverSeedKey).toHaveBeenCalledWith(evt);
    });

    it('discoverSeedGo reads the seed input value', () => {
        const input = document.createElement('input');
        input.id = 'discoverSeedInput';
        input.value = 'Yuki Kajiura';
        document.body.appendChild(input);
        click(button({ 'data-action': 'discoverSeedGo' }));
        expect(spies.exploreFromArtist).toHaveBeenCalledWith('Yuki Kajiura');
    });

    it('toggleFreshReleases passes the header element', () => {
        const header = button({ 'data-action': 'toggleFreshReleases' });
        click(header);
        expect(spies.toggleFreshReleases).toHaveBeenCalledWith(header);
    });

    it('updateThreshold reads the configured attribute', () => {
        const slider = button({
            'data-input-action': 'updateThreshold',
            'data-value-attr': 'value',
            'value': '65',
        });
        slider.dispatchEvent(new Event('input', { bubbles: true }));
        expect(spies.updateThreshold).toHaveBeenCalledWith('65');
    });

    it('updateThreshold reads live .value not initial attribute for range inputs', () => {
        // Regression: getAttribute('value') returns the initial HTML value,
        // not the current slider position. The handler must use .value.
        const slider = document.createElement('input');
        slider.type = 'range';
        slider.min = '30';
        slider.max = '100';
        slider.step = '5';
        slider.value = '85';  // initial HTML value
        slider.setAttribute('data-input-action', 'updateThreshold');
        slider.setAttribute('data-value-attr', 'value');
        document.body.appendChild(slider);

        // Simulate user moving slider to 45
        slider.value = '45';
        slider.dispatchEvent(new Event('input', { bubbles: true }));

        // Must receive 45 (live value), not 85 (initial attribute)
        expect(spies.updateThreshold).toHaveBeenCalledWith('45');
    });

    it('submitQuickAdd forwards the event and prevents page POST', () => {
        const form = document.createElement('form');
        form.setAttribute('data-submit-action', 'submitQuickAdd');
        document.body.appendChild(form);
        const evt = new Event('submit', { bubbles: true, cancelable: true });
        form.dispatchEvent(evt);
        expect(spies.submitQuickAdd).toHaveBeenCalledWith(evt);
        expect(evt.defaultPrevented).toBe(true);
    });

    it('renderErrorView retry buttons dispatch their action directly', () => {
        const grid = document.createElement('div');
        document.body.appendChild(grid);
        window.renderErrorView(grid, 'broken', 'loadDiscover');
        const retryBtn = grid.querySelector('[data-action="loadDiscover"]');
        expect(retryBtn).not.toBeNull();
        click(retryBtn);
        expect(spies.loadDiscover).toHaveBeenCalledTimes(1);
    });
});
