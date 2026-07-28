// ============================================================
// Dashboard Tests — Stats grid, charts, top artists, reviews
// ============================================================

describe('Dashboard: Stats and Charts', () => {
  before(() => {
    cy.visit('/');
    cy.waitForApp();
  });

  it('renders all 8 stat cards with values', () => {
    const statIds = ['statTotal', 'statRated', 'statAvg', 'statMedian', 'statRange', 'statArtists', 'statPeriod', 'statPerfect'];
    statIds.forEach((id) => {
      cy.get(`#${id}`, { timeout: 10000 }).should('be.visible');
      cy.get(`#${id}`).invoke('text').should('match', /[\d\-–]/);
    });
  });

  it('shows total entries as a positive number', () => {
    cy.get('#statTotal').invoke('text').then(parseFloat).should('be.gt', 0);
  });

  it('shows rated songs as a positive number', () => {
    cy.get('#statRated').invoke('text').then(parseFloat).should('be.gt', 0);
  });

  it('shows average rating between 0 and 100', () => {
    cy.get('#statAvg').invoke('text').then((t) => {
      if (t !== '-') {
        const val = parseFloat(t);
        expect(val).to.be.within(0, 100);
      }
    });
  });

  it('shows the rating range (min–max)', () => {
    cy.get('#statRange').invoke('text').should('match', /\d+\s*[–-]\s*\d+/);
  });

  it('shows unique artists as a positive number', () => {
    cy.get('#statArtists').invoke('text').then(parseFloat).should('be.gt', 0);
  });

  it('shows the time span in years', () => {
    cy.get('#statPeriod').invoke('text').should('match', /\d+\s*years?/);
  });

  it('renders the rating distribution chart (canvas)', () => {
    cy.get('#ratingChart').should('exist');
    cy.get('#ratingChart').should('be.visible');
  });

  it('renders the genre breakdown chart (canvas)', () => {
    cy.get('#genreChart').should('exist');
    cy.get('#genreChart').should('be.visible');
  });

  it('renders the top artists table', () => {
    cy.get('#topArtistsTable', { timeout: 10000 }).should('be.visible');
    cy.get('#topArtistsTable').should('not.contain.text', 'Loading');
    cy.get('#topArtistsTable table.data-table').should('exist');
    cy.get('#topArtistsTable tbody tr').should('have.length.at.least', 1);
  });

  it('displays at least 5 top artists', () => {
    cy.get('#topArtistsTable tbody tr').should('have.length.at.least', 5);
  });

  it('shows rank numbers with top-3 highlighting', () => {
    cy.get('#topArtistsTable .artist-rank.top3').should('have.length', 3);
  });

  it('renders recent reviews', () => {
    cy.get('#recentReviews', { timeout: 10000 }).should('be.visible');
    cy.get('#recentReviews').should('not.contain.text', 'Loading');
    cy.get('#recentReviews .review-item').should('have.length.at.least', 1);
  });

  it('shows rating badges in recent reviews', () => {
    cy.get('#recentReviews .rating-badge').should('have.length.at.least', 1);
  });

  it('shows the backfill preview panel', () => {
    cy.get('.backfill-panel').should('be.visible');
    cy.get('#backfillPreviewStats', { timeout: 10000 }).should('be.visible');
    cy.get('#backfillPreviewStats').should('not.contain.text', 'Analyzing');
  });

  it('shows backfill action buttons', () => {
    cy.get('#backfillBtn').should('be.visible');
    cy.get('.backfill-actions .btn-outline').should('be.visible');
  });
});
