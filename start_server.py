"""Start the Flask server in the background."""

import subprocess
import sys
import os
import time

# Kill any existing Python servers
try:
    subprocess.run(['taskkill', '/F', '/IM', 'python.exe'], 
                   capture_output=True, timeout=5)
except:
    pass

time.sleep(1)

# Start fresh server
log = open('flask_output.log', 'w', encoding='utf-8')
proc = subprocess.Popen(
    [sys.executable, 'run.py'],
    stdout=log,
    stderr=subprocess.STDOUT,
    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    env={**os.environ, 'PORT': '5000'}
)

print(f'Server started on PID {proc.pid}')
print('Waiting for server to start...', flush=True)
time.sleep(3)

# Verify endpoints
import urllib.request
import json

endpoints = [
    '/api/challenges',
    '/api/backfill-preview',
    '/api/stats',
    '/api/constellation',
]

for ep in endpoints:
    try:
        resp = urllib.request.urlopen(f'http://localhost:5000{ep}', timeout=5)
        data = json.loads(resp.read().decode('utf-8'))
        print(f'  ✓ {ep}: {resp.status} OK', flush=True)
    except Exception as e:
        print(f'  ✗ {ep}: {e}', flush=True)

print(f'\n✅ Server running on http://localhost:5000', flush=True)
