// ============================================================
// Quick-Add Tests — Modal, form, validation, submission
// NOTE: The add-song test writes a test entry to the real CSV.
// This is intentional for an E2E test of the personal tool.
// ============================================================

describe('Quick-Add: Add a Song', () => {
  before(() => {
    cy.visit('/');
    cy.waitForApp();
  });

  beforeEach(() => {
    // Ensure modal is closed before each test
    cy.get('#quickAddOverlay').should('not.be.visible');
  });

  it('opens the quick-add modal via FAB button', () => {
    cy.get('#fabButton').click();
    cy.get('#quickAddOverlay').should('be.visible');
    cy.get('#quickAddForm').should('be.visible');
    cy.get('.modal-header h3').should('contain.text', 'Add a Song');
    cy.get('.modal-close').click();
    cy.get('#quickAddOverlay').should('not.be.visible');
  });

  it('opens via keyboard shortcut (A key)', () => {
    cy.get('body').type('a');
    cy.get('#quickAddOverlay').should('be.visible');
    cy.get('.modal-close').click();
    cy.get('#quickAddOverlay').should('not.be.visible');
  });

  it('closes on overlay click', () => {
    cy.get('#fabButton').click();
    cy.get('#quickAddOverlay').should('be.visible');
    cy.get('#quickAddOverlay').click('left');
    cy.get('#quickAddOverlay').should('not.be.visible');
  });

  it('closes on Escape key', () => {
    cy.get('#fabButton').click();
    cy.get('#quickAddOverlay').should('be.visible');
    cy.get('body').type('{esc}');
    cy.get('#quickAddOverlay').should('not.be.visible');
  });

  it('shows validation error when submitting with empty title', () => {
    cy.get('#fabButton').click();
    cy.get('#quickAddForm').within(() => {
      cy.get('#qaTitle').clear();
      cy.get('button[type="submit"]').click();
    });
    // HTML5 required validation should fire — form stays visible
    cy.get('#quickAddForm').should('be.visible');
    cy.get('.modal-close').click();
  });

  it('successfully adds a song with just a title', () => {
    cy.get('#fabButton').click();
    cy.get('#qaTitle').type('Test E2E Song (Cypress Artist, 2025)');
    cy.get('button[type="submit"]').click();

    // Success state should appear
    cy.get('#qaSuccess', { timeout: 5000 }).should('be.visible');
    cy.get('#qaSuccess').should('contain.text', 'added');
    cy.get('#qaSuccess .btn-primary').click(); // "Add Another"
    cy.get('#quickAddForm').should('be.visible');
    cy.get('#qaTitle').should('have.value', '');
    cy.get('.modal-close').click();
  });

  it('successfully adds a song with title, rating, and notes', () => {
    cy.get('#fabButton').click();
    cy.get('#qaTitle').type('Another E2E Song (Cypress Artist, 2025)');
    cy.get('#qaRating').type('85');
    cy.get('#qaNotes').type('E2E test song.');
    cy.get('button[type="submit"]').click();

    cy.get('#qaSuccess', { timeout: 5000 }).should('be.visible');
    cy.get('#qaSuccess .btn-outline').click(); // "Done"
    cy.get('#quickAddOverlay').should('not.be.visible');
  });

  it('rejects ratings over 100 via backend validation', () => {
    cy.get('#fabButton').click();
    cy.get('#qaTitle').type('Over100 Song (Artist, 2025)');
    // Submit directly via cy.request to bypass HTML5 input validation
    cy.request({
      method: 'POST',
      url: '/api/add-song',
      body: { title: 'Over100 Song (Artist, 2025)', rating: 150 },
      headers: { 'Content-Type': 'application/json' },
      failOnStatusCode: false
    }).then((resp) => {
      expect(resp.status).to.eq(400);
      expect(resp.body).to.have.property('error');
    });
    cy.get('.modal-close').click();
  });

  it('rejects negative ratings via backend validation', () => {
    cy.request({
      method: 'POST',
      url: '/api/add-song',
      body: { title: 'Negative Rating Song (Artist, 2025)', rating: -5 },
      headers: { 'Content-Type': 'application/json' },
      failOnStatusCode: false
    }).then((resp) => {
      expect(resp.status).to.eq(400);
      expect(resp.body).to.have.property('error');
    });
  });

  it('includes a source dropdown with multiple options', () => {
    cy.get('#fabButton').click();
    cy.get('#qaSource').should('be.visible');
    cy.get('#qaSource option').should('have.length.at.least', 5);
    cy.get('#qaSource').select('recommender');
    cy.get('#qaSource').should('have.value', 'recommender');
    cy.get('.modal-close').click();
  });
});
