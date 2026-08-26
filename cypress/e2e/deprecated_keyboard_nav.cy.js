/**
 * deprecated_keyboard_nav.cy.js — Regression coverage for ADR-001.
 *
 * Number-key view navigation (1–8) was deprecated because the global handler
 * had no input guard: typing digits into the quick-add modal (a rating like 85,
 * or a song title containing numbers) silently switched views. See
 * DECISIONS.md ADR-001.
 *
 * Kept as its own spec so these checks run independently of the sidebar
 * navigation spec, which has a separate pre-existing environment flake.
 */
describe('Deprecated number-key navigation (ADR-001)', () => {
    beforeEach(() => {
        cy.visit('/');
        cy.get('#loadingScreen', { timeout: 20000 }).should('have.class', 'hidden');
        cy.get('#view-dashboard').should('have.class', 'active');
    });

    it('does not navigate via number keys', () => {
        cy.get('body').type('{2}');
        cy.get('#view-dashboard').should('have.class', 'active');
        cy.get('#view-recommender').should('not.have.class', 'active');

        cy.get('body').type('{4}');
        cy.get('#view-dashboard').should('have.class', 'active');
        cy.get('#view-constellation').should('not.have.class', 'active');

        // Modifier-key combos do nothing either
        cy.get('body').type('{ctrl}3');
        cy.get('#view-blindspots').should('not.have.class', 'active');
        cy.get('#view-dashboard').should('have.class', 'active');
    });

    it('typing numbers inside an input does not trigger navigation', () => {
        // Regression for the exact bug that motivated ADR-001: typing digits
        // in the quick-add modal must not hijack view switching.
        cy.get('body').type('a'); // open quick-add via the retained 'A' shortcut
        cy.get('#quickAddOverlay').should('have.class', 'active');

        cy.get('#qaRating').type('85');
        cy.get('#view-dashboard').should('have.class', 'active');
        cy.get('#view-recommender').should('not.have.class', 'active');
        cy.get('#qaRating').should('have.value', '85');

        // And typing digits into the song-title field is safe too
        cy.get('#qaTitle').type('123');

        cy.get('body').type('{esc}');
        cy.get('#quickAddOverlay').should('not.have.class', 'active');
    });

    it('the A quick-add shortcut still works (not removed)', () => {
        cy.get('body').type('a');
        cy.get('#quickAddOverlay').should('have.class', 'active');
        cy.get('#qaTitle').should('be.focused');
        cy.get('body').type('{esc}');
        cy.get('#quickAddOverlay').should('not.have.class', 'active');
    });
});
