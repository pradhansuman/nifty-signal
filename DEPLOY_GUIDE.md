# NSE Option Chain — Google Apps Script Bridge

## Why this exists
NSE's API (`nseindia.com/api/option-chain-indices`) is geo-blocked — requests from non-Indian IPs return 403/404. Google's servers run from Indian IPs and are NOT blocked. This bridge runs on Google's infrastructure and returns clean JSON.

## Deployment (takes ~3 minutes, one-time)

### Step 1: Open Google Apps Script
1. Go to https://script.google.com
2. Click **"New project"**
3. Delete any default code in the editor

### Step 2: Paste the script
1. Open [nse_fetcher.gs](/nse_fetcher.gs) from this workspace
2. Copy the entire contents
3. Paste into the Apps Script editor
4. Click the save icon (or Ctrl+S)

### Step 3: Deploy as Web App
1. Click **"Deploy"** (top-right blue button) → **"New deployment"**
2. Click the gear ⚙️ icon → Select **"Web app"**
3. Configure:
   - **Description:** `NSE Option Chain Fetcher`
   - **Execute as:** `Me` (your Google account)
   - **Who has access:** `Anyone` (the data is public NSE data)
4. Click **"Deploy"**
5. **Authorize** when prompted (this allows the script to make HTTP requests)
6. **Copy the Web App URL** — it looks like:
   `https://script.google.com/macros/s/AKfycb.../exec`

### Step 4: Test it
Visit the URL in your browser with query params:
```
https://script.google.com/macros/s/.../exec?symbol=NIFTY&expiry=27-Aug-2026
```
You should see a JSON response with `"success": true` and chain data.

### Step 5: Wire it to the pipeline
```
python nifty_pipeline_v2.py --nse-proxy "https://script.google.com/macros/s/YOUR_ID/exec"
```

That's it. Every run will now auto-fetch live NSE option chain data.

## Optional: List available expiries
```
https://script.google.com/macros/s/.../exec?symbol=NIFTY&format=expiries
```

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "Script not deployed" / 404 | Re-deploy: Deploy → Manage deployments → Edit → New version |
| "Authorization required" | You skipped the OAuth screen — re-deploy and authorize |
| Empty chain / 0 strikes | Check the expiry date format: `DD-Mon-YYYY` (e.g. `27-Aug-2026`) |
| Timeout | First run is slow (cold start). Subsequent runs are faster. Increase Python timeout if needed. |
