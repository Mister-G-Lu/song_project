// ============================================================
// API Integration Tests — Verify endpoint contracts
// These catch frontend-backend contract drift
// ============================================================

describe('API Integration: Endpoint Contracts', () => {
  before(() => {
    cy.visit('/');
    cy.waitForApp();
  });

  it('/api/stats returns all required fields', () => {
    cy.request('/api/stats').then((resp) => {
      expect(resp.status).to.eq(200);
      const data = resp.body;
      expect(data).to.have.property('total_entries').that.is.a('number');
      expect(data).to.have.property('rated_entries').that.is.a('number');
      expect(data).to.have.property('avg_rating').that.is.a('number');
      expect(data).to.have.property('median_rating').that.is.a('number');
      expect(data).to.have.property('unique_artists').that.is.a('number');
      expect(data).to.have.property('genre_distribution').that.is.an('object');
      expect(data).to.have.property('rating_distribution').that.is.an('object');
      expect(data).to.have.property('top_artists').that.is.an('array');
      expect(data).to.have.property('recent_reviews').that.is.an('array');
    });
  });

  it('/api/stats total_entries matches the count', () => {
    cy.request('/api/stats').then((resp) => {
      expect(resp.body.total_entries).to.be.gt(2000);
    });
  });

  it('/api/constellation returns nodes and edges', () => {
    cy.request('/api/constellation').then((resp) => {
      expect(resp.status).to.eq(200);
      const data = resp.body;
      expect(data).to.have.property('nodes').that.is.an('array');
      expect(data).to.have.property('edges').that.is.an('array');
      expect(data.nodes.length).to.be.gt(0);
      // Each node should have an id and name
      data.nodes.slice(0, 5).forEach((node) => {
        expect(node).to.have.property('id');
        expect(node).to.have.property('name');
      });
    });
  });

  it('/api/evolution returns all chart data', () => {
    cy.request('/api/evolution').then((resp) => {
      expect(resp.status).to.eq(200);
      const data = resp.body;
      expect(data).to.have.property('yearly').that.is.an('object');
      expect(data).to.have.property('monthly_avg').that.is.an('object');
      expect(data).to.have.property('cumulative').that.is.an('array');
      expect(data).to.have.property('genre_evolution').that.is.an('object');
      // Each year in yearly should have year-specific stats
      const years = Object.keys(data.yearly);
      expect(years.length).to.be.gt(0);
      const firstYear = data.yearly[years[0]];
      expect(firstYear).to.have.property('count');
      expect(firstYear).to.have.property('avg');
    });
  });

  it('/api/blind-spots returns top_loved_genres and blind_spots', () => {
    cy.request('/api/blind-spots').then((resp) => {
      expect(resp.status).to.eq(200);
      const data = resp.body;
      expect(data).to.have.property('top_loved_genres').that.is.an('array');
      expect(data).to.have.property('blind_spots').that.is.an('array');
      expect(data.top_loved_genres.length).to.be.gt(0);
      expect(data.blind_spots.length).to.be.gt(0);
    });
  });

  it('/api/weekly-discovery returns picks and message', () => {
    cy.request('/api/weekly-discovery').then((resp) => {
      expect(resp.status).to.eq(200);
      const data = resp.body;
      expect(data).to.have.property('picks').that.is.an('array');
      expect(data).to.have.property('message').that.is.a('string');
      expect(data).to.have.property('stats').that.is.an('object');
    });
  });

  it('/api/challenges returns challenges with tiers', () => {
    cy.request('/api/challenges?count=5').then((resp) => {
      expect(resp.status).to.eq(200);
      const data = resp.body;
      expect(data).to.have.property('challenges').that.is.an('array');
      expect(data).to.have.property('by_tier').that.is.an('object');
      expect(data).to.have.property('your_zones').that.is.an('object');
      expect(data).to.have.property('total_available').that.is.a('number');
    });
  });

  it('/api/recommendations returns recs by category', () => {
    cy.request('/api/recommendations').then((resp) => {
      expect(resp.status).to.eq(200);
      const data = resp.body;
      // Response is an object keyed by recommendation category names
      expect(data).to.be.an('object');
      const categories = Object.keys(data);
      expect(categories.length).to.be.gt(0);
      // Each category should contain an array of recs
      categories.forEach((cat) => {
        expect(data[cat]).to.be.an('array');
      });
    });
  });

  it('/api/songs returns paginated results', () => {
    cy.request('/api/songs?limit=5&sort=date&order=desc').then((resp) => {
      expect(resp.status).to.eq(200);
      const data = resp.body;
      expect(data).to.have.property('songs').that.is.an('array');
      expect(data).to.have.property('total').that.is.a('number');
      expect(data.songs.length).to.be.at.most(5);
      expect(data.total).to.be.gt(0);
    });
  });

  it('/api/backfill-preview returns before/after stats', () => {
    cy.request('/api/backfill-preview?method=all').then((resp) => {
      expect(resp.status).to.eq(200);
      const data = resp.body;
      expect(data).to.have.property('total_changes').that.is.a('number');
      expect(data).to.have.property('before').that.is.an('object');
      expect(data).to.have.property('after').that.is.an('object');
      expect(data.before).to.have.property('rated');
      expect(data.before).to.have.property('total');
      expect(data.before).to.have.property('avg_rating');
    });
  });

  it('/api/songs handles search parameter', () => {
    cy.request('/api/songs?search=love&limit=3').then((resp) => {
      expect(resp.status).to.eq(200);
      expect(resp.body.songs).to.be.an('array');
    });
  });

  it('/api/songs handles min_rating filter', () => {
    cy.request('/api/songs?min_rating=90&limit=3').then((resp) => {
      expect(resp.status).to.eq(200);
      resp.body.songs.forEach((song) => {
        expect(song.rating).to.be.at.least(90);
      });
    });
  });

  it('/api/search-history returns results for valid query', () => {
    cy.request('/api/search-history?q=the').then((resp) => {
      expect(resp.status).to.eq(200);
      expect(resp.body).to.have.property('results').that.is.an('array');
      expect(resp.body).to.have.property('total').that.is.a('number');
    });
  });

  it('/api/search-history returns empty for nonsense query', () => {
    cy.request('/api/search-history?q=xyznonexistent98765').then((resp) => {
      expect(resp.status).to.eq(200);
      expect(resp.body.results).to.be.an('array').that.is.empty;
      expect(resp.body.total).to.eq(0);
    });
  });

  it('/api/check-song returns existence check', () => {
    cy.request({
      method: 'POST',
      url: '/api/check-song',
      body: { artist: 'Beyoncé', song: 'Halo' },
      headers: { 'Content-Type': 'application/json' },
    }).then((resp) => {
      expect(resp.status).to.eq(200);
      expect(resp.body).to.have.property('exists');
      expect(resp.body).to.have.property('title');
    });
  });

  it('/api/export returns comprehensive JSON', () => {
    cy.request('/api/export').then((resp) => {
      expect(resp.status).to.eq(200);
      expect(resp.body).to.have.property('stats');
      expect(resp.body).to.have.property('blind_spots');
      expect(resp.body).to.have.property('evolution');
      expect(resp.body).to.have.property('recommendations');
    });
  });

  it('/api/spotify-status returns availability', () => {
    cy.request('/api/spotify-status').then((resp) => {
      expect(resp.status).to.eq(200);
      expect(resp.body).to.have.property('available');
      expect(resp.body).to.have.property('message');
    });
  });

  it('/api/known-songs returns signatures', () => {
    cy.request('/api/known-songs').then((resp) => {
      expect(resp.status).to.eq(200);
      expect(resp.body).to.have.property('count').that.is.a('number');
      expect(resp.body).to.have.property('sigs').that.is.an('array');
      expect(resp.body).to.have.property('titles').that.is.an('array');
      expect(resp.body.count).to.be.gt(0);
    });
  });
});
