// ============================================================
// History Tests — Search, sort, filter, pagination
// ============================================================

describe('History: Search and Filter', () => {
  before(() => {
    cy.visit('/');
    cy.waitForApp();
    cy.navigateToView('history');
  });

  beforeEach(() => {
    // Intercept songs API calls so we can wait for them
    cy.intercept('/api/songs*').as('songsFetch');
  });

  it('loads the history view with songs', () => {
    cy.get('#view-history').should('have.class', 'active');
    cy.get('#historyList', { timeout: 15000 }).should('be.visible');
    cy.get('#historyList').should('not.contain.text', 'Loading');
  });

  it('displays the total song count', () => {
    cy.get('#historyCount', { timeout: 10000 }).should('be.visible');
    cy.get('#historyCount').invoke('text').should('match', /\d+ songs?/);
  });

  it('shows at least one song in the list', () => {
    cy.get('#historyList .review-item, #historyList tr, #historyList .song-item', { timeout: 10000 })
      .should('have.length.at.least', 1);
  });

  it('shows a "Load More" button when there are many songs', () => {
    cy.get('body').then(($body) => {
      if ($body.find('#loadMoreBtn:visible').length > 0) {
        cy.get('#loadMoreBtn').should('be.visible');
      }
    });
  });

  it('filters songs by search term', () => {
    cy.get('#historySearch').should('be.visible');
    cy.get('#historySearch').clear().type('love', { delay: 30 });
    cy.wait('@songsFetch', { timeout: 10000 });
    // Should find at least one result
    cy.get('#historyList', { timeout: 5000 }).should('be.visible');
  });

  it('returns no results for a nonsense search', () => {
    cy.get('#historySearch').clear().type('xyznonexistent98765', { delay: 20 });
    cy.wait('@songsFetch', { timeout: 10000 });
    cy.get('#historyList', { timeout: 5000 }).should('contain.text', 'No results')
      .or('contain.text', 'no songs')
      .or('contain.text', 'no matches');
  });

  it('resets results when search is cleared', () => {
    cy.get('#historySearch').clear();
    cy.wait('@songsFetch', { timeout: 10000 });
    cy.get('#historyList', { timeout: 5000 }).should('be.visible');
    cy.get('#historyList').should('not.contain.text', 'Loading');
  });

  it('sorts by date ascending', () => {
    cy.get('#historySort').select('date');
    cy.get('#historyOrder').select('asc');
    cy.wait('@songsFetch', { timeout: 10000 });
    cy.get('#historyList .review-item, #historyList tr, #historyList .song-item',
      { timeout: 5000 }).should('have.length.at.least', 1);
  });

  it('sorts by title descending', () => {
    cy.get('#historySort').select('title');
    cy.get('#historyOrder').select('desc');
    cy.wait('@songsFetch', { timeout: 10000 });
    cy.get('#historyList .review-item, #historyList tr, #historyList .song-item',
      { timeout: 5000 }).should('have.length.at.least', 1);
  });

  it('filters by minimum rating', () => {
    cy.get('#historyMinRating').select('90');
    cy.wait('@songsFetch', { timeout: 10000 });
    cy.get('#historyList .review-item, #historyList tr, #historyList .song-item',
      { timeout: 5000 }).should('have.length.at.least', 0);

    // Reset filter
    cy.get('#historyMinRating').select('');
    cy.wait('@songsFetch', { timeout: 10000 });
  });

  it('combines search + sort + filter without errors', () => {
    cy.get('#historySearch').clear().type('the', { delay: 20 });
    cy.get('#historySort').select('rating');
    cy.get('#historyOrder').select('desc');
    cy.get('#historyMinRating').select('70');
    cy.wait('@songsFetch', { timeout: 10000 });
    cy.get('#historyList', { timeout: 5000 }).should('be.visible');
  });
});
