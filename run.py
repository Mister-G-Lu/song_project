"""
run.py - Start the Music Taste Analyzer Flask server
"""

import sys
import os

# Fix Windows console encoding
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from app import app

if __name__ == '__main__':
    # PORT=0 (or unset-and-empty) means "use the default" — a literal 0 would
    # bind an OS-assigned ephemeral port, which breaks tooling that expects
    # the known URL.
    try:
        port = int(os.environ.get('PORT', 5000))
    except (TypeError, ValueError):
        port = 5000
    if port == 0:
        port = 5000
    # Loopback-only by default (see app.py for rationale); BIND_ALL=1 opts back
    # into 0.0.0.0 deliberately.
    host = '0.0.0.0' if os.environ.get('BIND_ALL') else '127.0.0.1'

    # Production WSGI server: waitress (waitress==3.0.2) is the recommended
    # Windows-native server — Werkzeug's dev server warns it is not for
    # production use. Use USE_DEV_SERVER=1 to force the Werkzeug path (e.g.
    # for tooling that expects it). Falls back automatically if waitress
    # isn't installed.
    use_dev = os.environ.get('USE_DEV_SERVER') == '1'
    if not use_dev:
        try:
            from waitress import serve
            print(f"Starting Music Taste Analyzer on http://{host}:{port} (waitress)")
            print(f"Press Ctrl+C to stop the server")
            serve(app, host=host, port=port, threads=8)
            sys.exit(0)
        except ImportError:
            print("waitress not installed — falling back to Werkzeug dev server")

    print(f"Starting Music Taste Analyzer on http://{host}:{port} (Werkzeug dev)")
    print(f"Press Ctrl+C to stop the server")
    app.run(debug=False, host=host, port=port, threaded=True, use_reloader=False)
