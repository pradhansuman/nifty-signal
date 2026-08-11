#!/bin/bash
# Start Nifty Signal server + public tunnel
WORKSPACE="/Users/skp/.openclaw-autoclaw/agents/nifty-50/workspace"
cd "$WORKSPACE"

# Start Flask server if not running
if ! pgrep -f nifty_server.py > /dev/null; then
  nohup .openclaw/tmp/venv/bin/python nifty_server.py > /dev/null 2>&1 &
  sleep 3
fi

# Start bore tunnel, save URL
nohup .openclaw/tmp/bore local 5099 --to bore.pub > .openclaw/tmp/bore_url.txt 2>&1 &
sleep 3

URL=$(grep -o 'bore.pub:[0-9]*' .openclaw/tmp/bore_url.txt | tail -1)
echo "http://$URL"
