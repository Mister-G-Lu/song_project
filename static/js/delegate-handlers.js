/**
 * delegate-handlers.js - Central ActionBus registration.
 *
 * Every UI control declares `data-action="name"` (+ data-* args) in markup;
 * this file maps those names to the functions that do the work. Nothing here
 * is inline-JS, so the whole app is CSP-compatible and the handlers are
 * unit-testable (register the bus in jsdom, dispatch synthetic clicks).
 *
 * Load order: last, after all view scripts (functions must exist).
 */
(function () {
    'use strict';

    /**
     * Register every delegated handler on the ActionBus. Exposed for tests;
     * runs automatically at load time.
     */
    function setupDelegatedHandlers() {
        const bus = window.ActionBus;
        if (!bus) {
            console.error('[delegate-handlers] ActionBus missing — check script load order');
            return;
        }

    const g = (name) => {
        const fn = window[name];
        if (typeof fn !== 'function') {
            console.warn(`[delegate-handlers] global "${name}" not found at registration time`);
            return () => console.warn(`[ActionBus] "${name}" global missing`);
        }
        return fn;
    };

    // --- Navigation -----------------------------------------------------
    bus.register('switchView', (ctx) => g('switchView')(ctx.dataset.view));

    // --- Generic UI helpers ---------------------------------------------
    bus.register('toggleCollapsed', (ctx) => {
        const scope = ctx.el.closest(ctx.dataset.toggleSelector || '.chart-card');
        if (scope) scope.classList.toggle('collapsed');
    });
    bus.register('toggleNextSibling', (ctx) => {
        if (ctx.el.nextElementSibling) ctx.el.nextElementSibling.classList.toggle('collapsed');
    });
    bus.register('quickAddOverlayClick', (ctx) => {
        if (ctx.event.target === ctx.el) g('closeQuickAdd')();
    });

    // --- Dashboard / backfill / conquest ---------------------------------
    bus.register('loadYearConquest', () => g('loadYearConquest')());
    bus.register('applyBackfill', () => g('applyBackfill')());
    bus.register('refreshBackfillPreview', () => g('refreshBackfillPreview')());
    bus.register('toggleDecadeExpand', (ctx) => {
        const decade = ctx.el.closest('.conquest-decade');
        if (decade) decade.classList.toggle('expanded');
    });
    bus.register('quickAddFromConquest', (ctx) =>
        g('quickAddFromConquest')(ctx.dataset.artist, ctx.dataset.song));
    bus.register('selectGenreLegend', (ctx) => g('selectGenreLegend')(ctx.dataset.genreJsKey));
    bus.register('addBanItem', () => g('addBanItem')());
    bus.register('banValueEnter', (ctx) => {
        if (ctx.event.key === 'Enter') g('addBanItem')();
    });
    bus.register('removeBanItem', (ctx) =>
        g('removeBanItem')(ctx.dataset.banType, ctx.dataset.banValue));
    bus.register('lockAutoSuppression', (ctx) =>
        g('lockAutoSuppression')(ctx.dataset.banType, ctx.dataset.banValue));

    // --- Recommender ------------------------------------------------------
    bus.register('refreshRecommendations', () => g('refreshRecommendations')());
    bus.register('toggleReverseMe', () => g('toggleReverseMe')());
    bus.register('loadRecommender', () => g('loadRecommender')());
    bus.register('toggleListened', (ctx) =>
        g('toggleListenedButton')(ctx.el, ctx.dataset.artist, ctx.dataset.song,
            ctx.dataset.listened === 'true'));
    bus.register('ignoreSong', (ctx) =>
        g('ignoreSong')(ctx.el, ctx.dataset.artist, ctx.dataset.song));
    bus.register('searchSpotifyTrack', (ctx) =>
        g('searchSpotifyTrack')(ctx.dataset.artist, ctx.dataset.song));
    bus.register('quickAddFromRecommender', (ctx) =>
        g('quickAddFromRecommender')(ctx.dataset.artist, ctx.dataset.song, ctx.dataset.source));

    // --- Challenges ---------------------------------------------------------
    bus.register('loadChallenges', () => g('loadChallenges')());

    // --- Data hygiene -----------------------------------------------------
    bus.register('loadHygiene', () => g('loadHygiene')());
    bus.register('switchChallengeMode', (ctx) =>
        g('switchChallengeMode')(ctx.dataset.mode));
    bus.register('updateThreshold', (ctx) => {
        const value = ctx.dataset.valueAttr
            ? ctx.el.getAttribute(ctx.dataset.valueAttr)
            : ctx.el.value;
        g('updateThreshold')(value);
    });

    // --- Discover ------------------------------------------------------------
    bus.register('setDiscoverTab', (ctx) => g('setDiscoverTab')(ctx.dataset.tab));
    bus.register('setDiscoverTabChallenge', () => g('setDiscoverTab')('challenge'));
    bus.register('setDiscoverMode', (ctx) => g('setDiscoverMode')(ctx.dataset.mode));
    bus.register('refreshDiscover', () => g('refreshDiscover')());
    bus.register('loadDiscoverForce', () => g('loadDiscover')(true));
    bus.register('exploreFromArtist', (ctx) => g('exploreFromArtist')(ctx.dataset.artist));
    bus.register('clearDiscoverSeed', () => g('clearDiscoverSeed')());
    bus.register('onDiscoverSeedKey', (ctx) => g('onDiscoverSeedKey')(ctx.event));
    bus.register('discoverSeedGo', () => {
        const input = document.getElementById('discoverSeedInput');
        g('exploreFromArtist')(input ? input.value : '');
    });
    bus.register('toggleFreshReleases', (ctx) => g('toggleFreshReleases')(ctx.el));
    bus.register('gotoChallenges', () => g('switchView')('challenge'));

    // --- History ----------------------------------------------------------------
    bus.register('loadSongs', () => g('loadSongs')());
    bus.register('retryLoadSongs', () => g('loadSongs')(true));
    bus.register('loadMoreSongs', () => g('loadMoreSongs')());
    bus.register('searchHistory', () => g('searchHistory')());
    bus.register('debounceSearch', () => g('debounceSearch')());

    // --- Evolution -----------------------------------------------------------------
    bus.register('loadEvolution', () => g('loadEvolution')());
    bus.register('toggleReleaseYearShowAll', () => g('toggleReleaseYearShowAll')());
    bus.register('sortReleaseYearBy', (ctx) => g('sortReleaseYearBy')(ctx.dataset.sortKey));
    bus.register('setReleaseYearChartMode', (ctx) =>
        g('setReleaseYearChartMode')(ctx.dataset.ryMode));
    bus.register('updateGenreEvolutionChart', () => g('updateGenreEvolutionChart')());

    // --- Constellation / blind spots / fingerprint -------------------------------------
    bus.register('loadConstellation', () => g('loadConstellation')());
    bus.register('setConstellationMode', (ctx) =>
        g('setConstellationMode')(ctx.dataset.mode));
    bus.register('closeUncategorizedBreakdown', () => g('closeUncategorizedBreakdown')());

    // --- Quick-add modal ------------------------------------------------------------
    bus.register('openQuickAdd', () => g('openQuickAdd')());
    bus.register('closeQuickAdd', () => g('closeQuickAdd')());
    bus.register('resetQuickAddForm', () => g('resetQuickAddForm')());
    bus.register('submitQuickAdd', (ctx) => g('submitQuickAdd')(ctx.event));
    bus.register('_selectArtist', (ctx) => g('_selectArtist')(ctx.dataset.artistName));
    bus.register('filterInfluences', () => g('filterInfluences')());
    bus.register('scoreFit', () => g('scoreFit')());

    // --- Error-view retry buttons -----------------------------------------------
    // renderErrorView(container, msg, 'loadX') emits a retry button with
    // data-action="loadX" directly, so no extra indirection is needed — the
    // plain action registrations above cover retry buttons too.
    }

    // Run automatically at load time; re-runnable for tests.
    window.setupDelegatedHandlers = setupDelegatedHandlers;
    setupDelegatedHandlers();
})();
