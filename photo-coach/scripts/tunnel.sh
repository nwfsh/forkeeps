#!/bin/bash
# Runs the app for a phone that isn't on this computer's network:  npm run tunnel
# Opens a public address for the analysis server (which must already be running on port 8000),
# then starts Expo in tunnel mode pointed at it. Ctrl+C stops both.
cd "$(dirname "$0")/.."

if ! curl -s -m 5 -o /dev/null http://localhost:8000/health; then
  echo "The analysis server isn't running on port 8000. Start it from server/ first." >&2
  exit 1
fi

log=$(mktemp)
cloudflared tunnel --url http://localhost:8000 >"$log" 2>&1 &
tunnel=$!
trap 'kill $tunnel 2>/dev/null; rm -f "$log"' EXIT

echo "Opening a public address for the server..."
for _ in $(seq 60); do
  url=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$log" | head -1)
  [ -n "$url" ] && break
  sleep 0.5
done
if [ -z "$url" ]; then
  echo "cloudflared didn't give an address:" >&2
  cat "$log" >&2
  exit 1
fi

# Wait for cloudflared to say it's connected. Asking the address itself from this computer
# too early makes macOS remember it as not existing, so the log is the safer thing to watch.
for _ in $(seq 60); do
  grep -q 'Registered tunnel connection' "$log" && connected=1 && break
  sleep 0.5
done
if [ -z "$connected" ]; then
  echo "cloudflared couldn't connect:" >&2
  cat "$log" >&2
  exit 1
fi
echo "Server address: $url"

EXPO_PUBLIC_SERVER_URL="$url" npx expo start --tunnel
