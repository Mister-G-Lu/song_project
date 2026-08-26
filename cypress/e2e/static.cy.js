/**
 * static.cy.js — End-to-end verification of the GitHub Pages static snapshot.
 *
 * The snapshot is built (scripts/export_static.py) and served (python -m
 * http.server) by the `test:e2e:static` npm script, which passes the port to
 * Cypress via `--config baseUrl`. That keeps this spec free of any in-process
 * server or before-hook shell calls — the same pattern as test:e2e:ci.
 *
 * It confirms the app renders and behaves correctly with NO Python backend:
 * all views load from pre-computed JSON, history search/pagination work
 * client-side, both challenge modes work, and write actions are read-only.
 */
describe('Static GitHub Pages snapshot', () => {
    beforeEach(() => {
        cy.visit('/');
        cy.get('#loadingScreen', { timeout: 20000 }).should('have.class', 'hidden');
    });

    it('detects static mode, shows read-only banner, hides FAB', () => {
        cy.get('.static-banner', { timeout: 15000 }).should('be.visible');
        cy.window().then((win) => {
            expect(win.STATIC_MODE).to.equal(true);
            expect(win.staticApiFile('/api/stats', new URLSearchParams())).to.equal('data/api/stats.json');
            expect(win.staticApiFile('/api/challenges', new URLSearchParams('mode=opposite_taste')))
                .to.equal('data/api/challenges-opposite.json');
        });
        cy.get('#statTotal').should('not.have.text', '-');
        cy.get('#fabButton').should('not.be.visible');
    });

    it('renders dashboard, recommender, blind spots, weekly from static JSON', () => {
        cy.get('#statTotal').should('not.have.text', '-');

        cy.navigateToView('recommender');
        cy.get('#view-recommender .rec-category', { timeout: 15000 }).should('exist');

        cy.navigateToView('blindspots');
        cy.get('#view-blindspots .spot-card', { timeout: 15000 }).should('exist');

        cy.navigateToView('weekly');
        cy.get('#view-weekly .weekly-pick', { timeout: 15000 }).should('exist');
    });

    it('renders constellation and evolution charts', () => {
        cy.navigateToView('constellation');
        cy.get('#constellationSvg circle', { timeout: 20000 }).should('exist');

        cy.navigateToView('evolution');
        cy.get('#evolutionSummary').should('not.be.empty');
        cy.get('#evolutionChart').should('exist');
    });

    it('switches challenge modes via separate snapshot files', () => {
        cy.navigateToView('challenge');
        cy.get('#view-challenge .challenge-tier', { timeout: 15000 }).should('exist');

        cy.get('[data-mode="opposite_taste"]').click();
        cy.get('#view-challenge .opposite-banner', { timeout: 15000 }).should('exist');
        cy.get('#view-challenge .challenge-tier', { timeout: 15000 }).should('exist');
    });

    it('browses history with client-side search', () => {
        cy.navigateToView('history');
        cy.get('#view-history .history-item', { timeout: 15000 }).should('exist');
        cy.get('#historyCount').should('not.have.text', '');

        cy.get('#historySearch').type('queen');
        cy.get('#view-history .history-item', { timeout: 15000 }).should('exist');
        cy.get('#historyCount').should('contain.text', 'results');
    });

    it('blocks quick-add in read-only mode', () => {
        cy.get('body').type('a');
        cy.get('#quickAddOverlay').should('not.have.class', 'active');
        cy.get('.toast').should('contain.text', 'Read-only');
    });
});
