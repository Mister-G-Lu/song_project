const { defineConfig } = require('cypress');

// The static-snapshot spec (cypress/e2e/static.cy.js) is served externally by
// the `test:e2e:static` npm script (python -m http.server via
// start-server-and-test), matching the test:e2e:ci pattern — no in-process
// server tasks needed here.
module.exports = defineConfig({
  e2e: {
    baseUrl: 'http://localhost:5000',
    supportFile: 'cypress/support/e2e.js',
    specPattern: 'cypress/e2e/**/*.cy.js',
    viewportWidth: 1280,
    viewportHeight: 800,
    defaultCommandTimeout: 10000,
    requestTimeout: 10000,
    responseTimeout: 15000,
    video: false,
    screenshotOnRunFailure: true,
    retries: {
      runMode: 1,
      openMode: 0,
    },
    setupNodeEvents(on, config) {
      // Register a task to check if the server is responding
      on('task', {
        log(message) {
          console.log(message);
          return null;
        },
      });
    },
  },
});
