# Deploy Nifty Signal to your NAS

## What you need
- NAS with Docker support (Synology DSM 7+, QNAP Container Station, TrueNAS SCALE, Unraid, or any Linux NAS)
- 512MB+ RAM available for containers

## Quick deploy (all NAS platforms)

### 1. Copy files to NAS
SSH into your NAS or use File Station. Create a folder and copy these files:

```
nas:/volume1/docker/nifty-signal/
├── Dockerfile
├── docker-compose.yml
├── nifty_monitor.py
├── nifty_pipeline_v2.py
├── nifty_server.py
└── pwa_static/
    ├── index.html
    ├── manifest.json
    ├── sw.js
    ├── icon-192.png
    └── icon-512.png
```

### 2. Start it
```bash
cd /volume1/docker/nifty-signal
docker compose up -d
```

### 3. Access
- **Local:** `http://nas-ip:5099`
- **Public HTTPS:** check cloudflared container logs:
  ```bash
  docker logs nifty-tunnel 2>&1 | grep trycloudflare
  ```

## Platform-specific notes

### Synology DSM 7+
1. Install **Container Manager** from Package Center
2. SSH in (Control Panel → Terminal & SNMP → Enable SSH)
3. Run `docker compose up -d` in your project folder
4. Or use Container Manager UI: Project → Create → point to docker-compose.yml

### QNAP
1. Install **Container Station**
2. Create → Application → paste docker-compose.yml
3. Or SSH in and use the CLI

### TrueNAS SCALE
1. Apps → Launch Docker Image
2. Or use the built-in Docker Compose via SSH

### Unraid
1. Community Applications → search/add Docker Compose
2. Or SSH in: `docker compose up -d`

## HTTPS access (pick one)

**Option A: Cloudflared (included)**
- The `docker-compose.yml` already starts a cloudflared tunnel
- Get your URL: `docker logs nifty-tunnel 2>&1 | grep trycloudflare`
- Free, auto-HTTPS, no account needed
- URL changes on container restart

**Option B: NAS reverse proxy (fixed URL)**
- Synology: Control Panel → Login Portal → Advanced → Reverse Proxy
  - Source: HTTPS, port 443, hostname: nifty.yourdomain.com
  - Destination: HTTP, localhost, port 5099
- QNAP: Control Panel → System → Reverse Proxy
- Then use Let's Encrypt for SSL (built into Synology/QNAP)

**Option C: Tailscale**
- Install Tailscale on NAS and your phone
- Access via `http://nas-tailscale-ip:5099`
- End-to-end encrypted, no public exposure

## Setting up the cron monitor on NAS

Add this to the NAS crontab (`crontab -e`):
```
*/15 9-15 * * 1-5 cd /volume1/docker/nifty-signal && docker exec nifty-signal python nifty_monitor.py >> /tmp/nifty_monitor.log 2>&1
```

Or use the NAS task scheduler (Synology: Control Panel → Task Scheduler).

## Verify
```bash
# Check container is running
docker ps | grep nifty

# Test the API
curl http://localhost:5099/api/signal
```
