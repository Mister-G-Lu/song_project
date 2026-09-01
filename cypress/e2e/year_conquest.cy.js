// ============================================================
// Year Conquest — Decade accordion and song interaction tests
// ============================================================

describe('Year Conquest: Decade Accordion', () => {
  beforeEach(() => {
    cy.visit('/');
    cy.waitForApp();
  });

  it('renders the Year Conquest panel on the dashboard', () => {
    cy.get('#conquestContent', { timeout: 10000 }).should('be.visible');
    cy.get('.conquest-decade').should('have.length.at.least', 1);
  });

  it('renders at least 3 decade sections', () => {
    cy.get('.conquest-decade').should('have.length.at.least', 3);
  });

  it('shows decade labels (e.g. "2010s", "2000s")', () => {
    cy.get('.conquest-decade-label').first().invoke('text').should('match', /\d{4}s/);
  });

  it('the current decade (2010s) is expanded by default', () => {
    cy.get('.conquest-decade').first().should('have.class', 'expanded');
  });

  it('shows a song count on each decade header', () => {
    cy.get('.conquest-decade-count').first().invoke('text').should('match', /\d+ songs to go/);
  });

  it('collapse an expanded decade on click', () => {
    // 2010s starts expanded — click to collapse
    cy.get('.conquest-decade').first().within(() => {
      cy.get('.conquest-decade-header').click();
    });
    cy.get('.conquest-decade').first().should('not.have.class', 'expanded');
  });

  it('expand a collapsed decade on click', () => {
    // 2000s starts collapsed — click to expand
    cy.get('.conquest-decade').eq(1).within(() => {
      cy.get('.conquest-decade-header').click();
    });
    cy.get('.conquest-decade').eq(1).should('have.class', 'expanded');
  });

  it('toggle a decade from expanded back to collapsed', () => {
    // Expand
    cy.get('.conquest-decade').eq(1).within(() => {
      cy.get('.conquest-decade-header').click();
    });
    cy.get('.conquest-decade').eq(1).should('have.class', 'expanded');

    // Collapse
    cy.get('.conquest-decade').eq(1).within(() => {
      cy.get('.conquest-decade-header').click();
    });
    cy.get('.conquest-decade').eq(1).should('not.have.class', 'expanded');
  });

  it('shows year headers inside an expanded decade', () => {
    cy.get('.conquest-decade').first().should('have.class', 'expanded');
    cy.get('.conquest-decade').first().within(() => {
      cy.get('.conquest-year').should('have.length.at.least', 1);
    });
  });

  it('shows song entries inside a year', () => {
    cy.get('.conquest-decade').first().should('have.class', 'expanded');
    cy.get('.conquest-decade').first().within(() => {
      cy.get('.conquest-song').should('have.length.at.least', 1);
    });
  });

  it('shows artist and title on each conquest song', () => {
    cy.get('.conquest-song').first().within(() => {
      cy.get('.conquest-song-artist').should('exist').and('not.be.empty');
      cy.get('.conquest-song-title').should('exist').and('not.be.empty');
    });
  });

  it('shows star ratings (acclaim) on each conquest song', () => {
    cy.get('.conquest-song').first().within(() => {
      cy.get('.conquest-stars').invoke('text').should('match', /[★☆]+/);
    });
  });

  it('shows a + button on each conquest song', () => {
    cy.get('.conquest-song').first().within(() => {
      cy.get('.btn-conquest-add').should('exist').and('be.visible');
    });
  });

  it('+ button has correct data attributes', () => {
    cy.get('.conquest-song').first().within(() => {
      cy.get('.btn-conquest-add')
        .should('have.attr', 'data-artist')
        .and('not.be.empty');
      cy.get('.btn-conquest-add')
        .should('have.attr', 'data-song')
        .and('not.be.empty');
    });
  });

  it('+ button opens the quick-add modal pre-filled', () => {
    cy.get('.conquest-song').first().within(() => {
      cy.get('.btn-conquest-add').click();
    });
    // Quick-add modal should open
    cy.get('#quickAddOverlay').should('be.visible');
    // Artist and song fields should be pre-filled
    cy.get('#qaArtist').invoke('val').should('not.be.empty');
    cy.get('#qaSong').invoke('val').should('not.be.empty');
    // Close modal
    cy.get('.modal-close').click();
    cy.get('#quickAddOverlay').should('not.be.visible');
  });

  it('decade dropdown exists and can be changed', () => {
    cy.get('#conquestStartDecade', { timeout: 10000 }).should('exist');
    cy.get('#conquestStartDecade').select('2000');
    // Panel should reload with 2000s content
    cy.get('.conquest-decade').should('have.length.at.least', 1);
  });

  it('refreshes conquest data after closing the quick-add modal', () => {
    // Open quick-add from a conquest song
    cy.get('.conquest-song').first().within(() => {
      cy.get('.btn-conquest-add').click();
    });
    cy.get('#quickAddOverlay').should('be.visible');
    // Close without adding
    cy.get('.modal-close').click();
    cy.get('#quickAddOverlay').should('not.be.visible');
    // Conquest content should still be present
    cy.get('.conquest-decade').should('have.length.at.least', 1);
  });

  it('no JS errors during conquest interaction', () => {
    // Expand all decades
    cy.get('.conquest-decade-header').each(($header) => {
      cy.wrap($header).click();
      cy.wait(200);
    });
    // Collapse all
    cy.get('.conquest-decade-header').each(($header) => {
      cy.wrap($header).click();
      cy.wait(200);
    });
  });
});
