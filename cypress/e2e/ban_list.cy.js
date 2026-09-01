// ============================================================
// Ban List — Add / Remove flow from the dashboard UI
// ============================================================

describe('Ban List: UI Flow', () => {
  const TEST_GENRE = '__cypresstestgenre__';
  const TEST_ARTIST = '__cypresstestartist__';
  const TEST_SONG = '__cypresstestsong__';

  beforeEach(() => {
    cy.visit('/');
    cy.waitForApp();
    // Clean up any leftover test ban items
    cy.request({
      method: 'POST',
      url: '/api/ban-list/remove',
      body: { type: 'genres', value: TEST_GENRE },
      headers: { 'Content-Type': 'application/json' },
      failOnStatusCode: false,
    });
    cy.request({
      method: 'POST',
      url: '/api/ban-list/remove',
      body: { type: 'artists', value: TEST_ARTIST },
      headers: { 'Content-Type': 'application/json' },
      failOnStatusCode: false,
    });
    cy.request({
      method: 'POST',
      url: '/api/ban-list/remove',
      body: { type: 'songs', value: TEST_SONG },
      headers: { 'Content-Type': 'application/json' },
      failOnStatusCode: false,
    });
  });

  afterEach(() => {
    // Clean up test ban items after each test
    cy.request({
      method: 'POST',
      url: '/api/ban-list/remove',
      body: { type: 'genres', value: TEST_GENRE },
      headers: { 'Content-Type': 'application/json' },
      failOnStatusCode: false,
    });
    cy.request({
      method: 'POST',
      url: '/api/ban-list/remove',
      body: { type: 'artists', value: TEST_ARTIST },
      headers: { 'Content-Type': 'application/json' },
      failOnStatusCode: false,
    });
    cy.request({
      method: 'POST',
      url: '/api/ban-list/remove',
      body: { type: 'songs', value: TEST_SONG },
      headers: { 'Content-Type': 'application/json' },
      failOnStatusCode: false,
    });
  });

  it('ban list panel exists on the dashboard', () => {
    cy.get('#banListPanel', { timeout: 10000 }).should('exist');
  });

  it('ban list panel is collapsed by default', () => {
    cy.get('#banListPanel').should('have.class', 'collapsed');
  });

  it('expand the ban list panel', () => {
    cy.get('#banListPanel .collapsible-header').click();
    cy.get('#banListPanel').should('not.have.class', 'collapsed');
  });

  it('shows the add form with type selector and input', () => {
    cy.get('#banListPanel .collapsible-header').click();
    cy.get('#banTypeSelect').should('be.visible');
    cy.get('#banValueInput').should('be.visible');
    cy.get('.ban-list-add .btn-primary').should('contain.text', 'Block');
  });

  it('type selector has Genre, Artist, and Song options', () => {
    cy.get('#banListPanel .collapsible-header').click();
    cy.get('#banTypeSelect option').should('have.length', 3);
    cy.get('#banTypeSelect option').eq(0).should('have.value', 'genres');
    cy.get('#banTypeSelect option').eq(1).should('have.value', 'artists');
    cy.get('#banTypeSelect option').eq(2).should('have.value', 'songs');
  });

  it('shows existing ban list items', () => {
    cy.get('#banListPanel .collapsible-header').click();
    cy.get('#banListContent .ban-list-stats').should('exist');
    cy.get('#banListContent .ban-list-stats').invoke('text').should('match', /\d+ items? blocked/);
  });

  it('add a genre to the ban list', () => {
    cy.get('#banListPanel .collapsible-header').click();
    cy.get('#banTypeSelect').select('genres');
    cy.get('#banValueInput').type(TEST_GENRE);
    cy.get('.ban-list-add .btn-primary').click();
    cy.get('#banValueInput', { timeout: 5000 }).should('have.value', '');
    cy.contains('#banListContent .ban-tag', TEST_GENRE).should('exist');
  });

  it('add an artist to the ban list', () => {
    cy.get('#banListPanel .collapsible-header').click();
    cy.get('#banTypeSelect').select('artists');
    cy.get('#banValueInput').type(TEST_ARTIST);
    cy.get('.ban-list-add .btn-primary').click();
    cy.get('#banValueInput', { timeout: 5000 }).should('have.value', '');
    cy.contains('#banListContent .ban-tag', TEST_ARTIST).should('exist');
  });

  it('add a song to the ban list', () => {
    cy.get('#banListPanel .collapsible-header').click();
    cy.get('#banTypeSelect').select('songs');
    cy.get('#banValueInput').type(TEST_SONG);
    cy.get('.ban-list-add .btn-primary').click();
    cy.get('#banValueInput', { timeout: 5000 }).should('have.value', '');
    cy.contains('#banListContent .ban-tag', TEST_SONG).should('exist');
  });

  it('clears the input after adding', () => {
    cy.get('#banListPanel .collapsible-header').click();
    cy.get('#banTypeSelect').select('songs');
    cy.get('#banValueInput').type(TEST_SONG);
    cy.get('.ban-list-add .btn-primary').click();
    cy.get('#banValueInput').should('have.value', '');
  });

  it('remove a banned item by clicking the × button', () => {
    // First add
    cy.get('#banListPanel .collapsible-header').click();
    cy.get('#banTypeSelect').select('genres');
    cy.get('#banValueInput').type(TEST_GENRE);
    cy.get('.ban-list-add .btn-primary').click();
    cy.get('#banValueInput', { timeout: 5000 }).should('have.value', '');
    cy.contains('#banListContent .ban-tag', TEST_GENRE).should('exist');

    // Then remove via the × button
    cy.contains('#banListContent .ban-tag', TEST_GENRE).within(() => {
      cy.get('.ban-remove').click();
    });
    // The specific tag should disappear
    cy.contains('#banListContent .ban-tag', TEST_GENRE).should('not.exist');
  });

  it('ban list count updates after adding', () => {
    // Get initial count
    cy.get('#banListPanel .collapsible-header').click();
    cy.get('#banListContent .ban-list-stats').invoke('text').then((text) => {
      const initialCount = parseInt(text.match(/(\d+)/)[1], 10);

      // Add an item
      cy.get('#banTypeSelect').select('songs');
      cy.get('#banValueInput').type(TEST_SONG);
      cy.get('.ban-list-add .btn-primary').click();

      // Count should increase by 1
      cy.get('#banListContent .ban-list-stats', { timeout: 5000 })
        .invoke('text')
        .should('match', new RegExp(`${initialCount + 1} items? blocked`));

      // Clean up
      cy.request({
        method: 'POST',
        url: '/api/ban-list/remove',
        body: { type: 'songs', value: TEST_SONG },
        headers: { 'Content-Type': 'application/json' },
        failOnStatusCode: false,
      });
    });
  });

  it('ban list persists after page reload', () => {
    cy.get('#banListPanel .collapsible-header').click();
    cy.get('#banTypeSelect').select('songs');
    cy.get('#banValueInput').type(TEST_SONG);
    cy.get('.ban-list-add .btn-primary').click();
    cy.get('#banValueInput', { timeout: 5000 }).should('have.value', '');
    cy.contains('#banListContent .ban-tag', TEST_SONG).should('exist');

    // Reload
    cy.reload();
    cy.waitForApp();

    // Expand and verify it's still there
    cy.get('#banListPanel .collapsible-header').click();
    cy.contains('#banListContent .ban-tag', TEST_SONG, { timeout: 10000 }).should('exist');
  });

  it('empty input shows toast and does not add', () => {
    cy.get('#banListPanel .collapsible-header').click();
    cy.get('.ban-list-add .btn-primary').click();
    // Toast should show error message
    cy.get('#toast.show').should('contain.text', 'Enter a value');
  });

  it('add button submit via Enter key', () => {
    cy.get('#banListPanel .collapsible-header').click();
    cy.get('#banTypeSelect').select('songs');
    cy.get('#banValueInput').type(`${TEST_SONG}{enter}`);
    cy.get('#banValueInput', { timeout: 5000 }).should('have.value', '');
    cy.contains('#banListContent .ban-tag', TEST_SONG).should('exist');
  });

  it('no JS errors during ban list interactions', () => {
    cy.get('#banListPanel .collapsible-header').click();
    cy.get('#banTypeSelect').select('genres');
    cy.get('#banValueInput').type(TEST_GENRE);
    cy.get('.ban-list-add .btn-primary').click();
    cy.get('#banValueInput', { timeout: 5000 }).should('have.value', '');
    cy.contains('#banListContent .ban-tag', TEST_GENRE).should('exist');
    // Remove it
    cy.contains('#banListContent .ban-tag', TEST_GENRE).within(() => {
      cy.get('.ban-remove').click();
    });
  });
});
