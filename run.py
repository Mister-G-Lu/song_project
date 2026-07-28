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
    print(f"Starting Music Taste Analyzer on http://localhost:{port}")
    print(f"Press Ctrl+C to stop the server")
    app.run(debug=False, host='0.0.0.0', port=port, threaded=True, use_reloader=False)
