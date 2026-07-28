// ============================================================
// Navigation Tests — Sidebar, keyboard, and back/forth
// ============================================================

describe('Navigation: Switching Between Views', () => {
  before(() => {
    cy.visit('/');
    cy.waitForApp();
  });

  beforeEach(() => {
    // Reset to dashboard before each navigation test
    cy.navigateToView('dashboard');
  });

  it('navigates to Recommender via sidebar click', () => {
    cy.navigateToView('recommender');
    cy.get('#view-recommender .view-header h2').should('contain.text', 'Recommender');
  });

  it('navigates to Blind Spots via sidebar click', () => {
    cy.navigateToView('blindspots');
    cy.get('#view-blindspots').should('have.class', 'active');
    cy.get('#view-blindspots .view-header h2').should('contain.text', 'Blind');
  });

  it('navigates to Constellation via sidebar click', () => {
    cy.navigateToView('constellation');
    cy.get('#view-constellation').should('have.class', 'active');
    cy.get('#view-constellation .view-header h2').should('contain.text', 'Constellation');
  });

  it('navigates to Evolution via sidebar click', () => {
    cy.navigateToView('evolution');
    cy.get('#view-evolution').should('have.class', 'active');
    cy.get('#view-evolution .view-header h2').should('contain.text', 'Evolution');
  });

  it('navigates to Weekly via sidebar click', () => {
    cy.navigateToView('weekly');
    cy.get('#view-weekly').should('have.class', 'active');
    cy.get('#view-weekly .view-header h2').should('contain.text', 'Weekly');
  });

  it('navigates to History via sidebar click', () => {
    cy.navigateToView('history');
    cy.get('#view-history').should('have.class', 'active');
    cy.get('#view-history .view-header h2').should('contain.text', 'History');
  });

  it('navigates to Challenges via sidebar click', () => {
    cy.navigateToView('challenge');
    cy.get('#view-challenge').should('have.class', 'active');
    cy.get('#view-challenge .view-header h2').should('contain.text', 'Challenge');
  });

  it('highlights the active nav item', () => {
    cy.get('[data-view="dashboard"]').should('have.class', 'active');
    cy.navigateToView('weekly');
    cy.get('[data-view="weekly"]').should('have.class', 'active');
    cy.get('[data-view="dashboard"]').should('not.have.class', 'active');
  });

  it('navigates back and forth between views without errors', () => {
    cy.navigateToView('constellation');
    cy.get('#view-constellation').should('have.class', 'active');

    cy.navigateToView('challenge');
    cy.get('#view-challenge').should('have.class', 'active');

    cy.navigateToView('dashboard');
    cy.get('#view-dashboard').should('have.class', 'active');
    cy.get('#view-constellation').should('not.have.class', 'active');
  });

  it('supports keyboard shortcuts (1-8)', () => {
    cy.get('body').type('{2}');
    cy.get('#view-recommender').should('have.class', 'active');
    cy.get('[data-view="recommender"]').should('have.class', 'active');

    cy.get('body').type('{4}');
    cy.get('#view-constellation').should('have.class', 'active');
    cy.get('[data-view="constellation"]').should('have.class', 'active');

    cy.get('body').type('{1}');
    cy.get('#view-dashboard').should('have.class', 'active');
    cy.get('[data-view="dashboard"]').should('have.class', 'active');
  });

  it('does not trigger keyboard shortcuts with modifier keys', () => {
    cy.get('body').type('{ctrl}3');
    cy.get('#view-blindspots').should('not.have.class', 'active');
    cy.get('#view-dashboard').should('have.class', 'active');
  });

  it('shows toast notification on load', () => {
    cy.get('#toast', { timeout: 3000 }).should('be.visible');
    cy.get('#toast').should('contain.text', 'Welcome');
  });
});
