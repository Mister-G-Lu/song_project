"""Start Flask server, wait for readiness, then run Cypress E2E tests.

Usage:
    python run_e2e_tests.py                    # Run all E2E tests
    python run_e2e_tests.py cypress/e2e/smoke.cy.js  # Run a single spec

The Flask server is started as a subprocess and killed on exit.
"""
import subprocess, sys, time, urllib.request, os, atexit

SERVER_URL = 'http://localhost:5000'
server = None  # Keep reference for cleanup


def start_server():
    global server
    server = subprocess.Popen(
        [sys.executable, 'run.py'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=os.path.dirname(os.path.abspath(__file__))
    )

    print('Waiting for Flask server...', flush=True)
    for i in range(30):
        time.sleep(1)
        try:
            urllib.request.urlopen(SERVER_URL, timeout=3)
            print(f'Server ready after {i+1}s (PID {server.pid})', flush=True)
            return True
        except Exception:
            if i == 0:
                pass  # Expected on first attempt
    return False


def cleanup():
    global server
    if server and server.poll() is None:
        print('Shutting down Flask server...', flush=True)
        server.kill()
        server.wait(timeout=5)
        print('Server stopped.', flush=True)


atexit.register(cleanup)

if __name__ == '__main__':
    if not start_server():
        print('ERROR: Flask server failed to start within 30s', flush=True)
        sys.exit(1)

    # Build Cypress command
    cypress_cmd = ['npx', 'cypress', 'run', '--headless', '--browser', 'chrome']
    if len(sys.argv) > 1:
        cypress_cmd += ['--spec', sys.argv[1]]

    print(f'Running: {" ".join(cypress_cmd)}', flush=True)
    result = subprocess.run(cypress_cmd, shell=False)

    cleanup()
    print(f'Cypress exited with code {result.returncode}', flush=True)
    sys.exit(result.returncode)
