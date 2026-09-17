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
    port = int(os.environ.get('PORT', 5000))
    # Loopback-only by default (see app.py for rationale); BIND_ALL=1 opts back
    # into 0.0.0.0 deliberately.
    host = '0.0.0.0' if os.environ.get('BIND_ALL') else '127.0.0.1'
    print(f"Starting Music Taste Analyzer on http://{host}:{port}")
    print(f"Press Ctrl+C to stop the server")
    app.run(debug=False, host=host, port=port, threaded=True, use_reloader=False)
