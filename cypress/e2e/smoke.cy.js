// ============================================================
// Smoke Tests — Every view loads without crashing
// ============================================================

describe('Smoke Tests: All Views Load', () => {
  before(() => {
    cy.visit('/');
    cy.waitForApp();
  });

  it('shows the initial loading state', () => {
    cy.visit('/');
    // Loading screen should appear briefly then hide
    cy.get('#loadingScreen').should('exist');
    cy.get('#loadingScreen', { timeout: 15000 }).should('have.class', 'hidden');
  });

  it('has a visible sidebar with all nav items', () => {
    const views = ['dashboard', 'recommender', 'blindspots', 'constellation', 'evolution', 'weekly', 'history', 'challenge'];
    cy.get('.sidebar').should('be.visible');
    cy.get('.nav-item').should('have.length', views.length);
    views.forEach((view) => {
      cy.get(`[data-view="${view}"]`).should('be.visible');
    });
  });

  it('shows the dashboard as the default active view', () => {
    cy.get('#view-dashboard').should('have.class', 'active');
    cy.get('#view-dashboard .view-header h2').should('contain.text', 'Dashboard');
    cy.get('#loadingScreen').should('have.class', 'hidden');
  });

  it('shows data in the sidebar footer', () => {
    cy.get('#dataInfo', { timeout: 10000 }).should('not.contain.text', 'Loading');
    cy.get('#dataInfo').should('contain.text', 'songs');
  });

  it('shows the FAB (quick-add button)', () => {
    cy.get('#fabButton').should('be.visible').and('contain.text', '+');
  });

  it('shows the keyboard shortcut hint', () => {
    cy.get('#shortcutHint').should('be.visible').and('contain.text', 'A');
  });

  it('does not have any 404 errors in the HTML response', () => {
    cy.request('/').its('status').should('eq', 200);
  });

  it('all static JS files are reachable', () => {
    const scripts = [
      '/js/utils.js', '/js/quickadd.js', '/js/dashboard.js',
      '/js/recommender.js', '/js/blindspots.js', '/js/constellation.js',
      '/js/evolution.js', '/js/weekly.js', '/js/history.js', '/js/challenge.js',
      '/js/app.js'
    ];
    scripts.forEach((script) => {
      cy.request(script).its('status').should('eq', 200);
    });
  });

  it('the CSS file is reachable', () => {
    cy.request('/css/style.css').its('status').should('eq', 200);
  });
});
