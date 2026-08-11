/**
 * NSE Option Chain Fetcher — Google Apps Script Web App
 * Works with both V8 and Rhino runtime (no template literals)
 */

var NSE_BASE = "https://www.nseindia.com";
var USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36";

function fetchNSEOptionChain(symbol, expiryDate) {
  var cookieResponse = UrlFetchApp.fetch(NSE_BASE, {
    muteHttpExceptions: true,
    headers: {
      "User-Agent": USER_AGENT,
      "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
      "Accept-Language": "en-US,en;q=0.9"
    },
    followRedirects: true
  });
  
  var cookies = cookieResponse.getAllHeaders()["Set-Cookie"] || "";
  var apiUrl = NSE_BASE + "/api/option-chain-indices?symbol=" + encodeURIComponent(symbol);
  
  var response = UrlFetchApp.fetch(apiUrl, {
    muteHttpExceptions: true,
    headers: {
      "User-Agent": USER_AGENT,
      "Accept": "application/json, text/plain, */*",
      "Accept-Language": "en-US,en;q=0.9",
      "Referer": NSE_BASE + "/option-chain",
      "X-Requested-With": "XMLHttpRequest",
      "Cookie": cookies
    },
    followRedirects: true
  });
  
  if (response.getResponseCode() !== 200) {
    throw new Error("NSE API returned " + response.getResponseCode());
  }
  
  var data = JSON.parse(response.getContentText());
  var records = data.records || data;
  var allData = (records.data || []);
  
  var filtered = allData.filter(function(entry) {
    var ce = entry.CE || {};
    var pe = entry.PE || {};
    return ce.expiryDate === expiryDate || pe.expiryDate === expiryDate;
  });
  
  return {
    underlying: (data.records || {}).underlyingValue || null,
    totalStrikes: filtered.length,
    expiryDate: expiryDate,
    timestamp: (data.records || {}).timestamp || new Date().toISOString(),
    chain: filtered,
    allExpiries: (data.records || {}).expiryDates || []
  };
}

function flattenToCSV(chainEntries, spot) {
  return chainEntries.map(function(entry) {
    var ce = entry.CE || {};
    var pe = entry.PE || {};
    return {
      strike: entry.strikePrice || 0,
      ce_ltp: ce.lastPrice || 0,
      ce_oi: ce.openInterest || 0,
      ce_oi_chg: ce.changeinOpenInterest || 0,
      ce_vol: ce.totalTradedVolume || 0,
      ce_iv: ce.impliedVolatility || 0,
      pe_ltp: pe.lastPrice || 0,
      pe_oi: pe.openInterest || 0,
      pe_oi_chg: pe.changeinOpenInterest || 0,
      pe_vol: pe.totalTradedVolume || 0,
      pe_iv: pe.impliedVolatility || 0
    };
  });
}

function computeSummary(chainEntries, spot) {
  var tco = 0, tpo = 0, tcoChg = 0, tpoChg = 0, tcv = 0, tpv = 0;
  var maxPainStrike = null, maxPainOI = 0;
  
  chainEntries.forEach(function(entry) {
    var s = entry.strikePrice || 0;
    var ce = entry.CE || {};
    var pe = entry.PE || {};
    var coi = ce.openInterest || 0;
    var poi = pe.openInterest || 0;
    tco += coi;
    tpo += poi;
    tcoChg += (ce.changeinOpenInterest || 0);
    tpoChg += (pe.changeinOpenInterest || 0);
    tcv += (ce.totalTradedVolume || 0);
    tpv += (pe.totalTradedVolume || 0);
    var combined = coi + poi;
    if (combined > maxPainOI) {
      maxPainOI = combined;
      maxPainStrike = s;
    }
  });
  
  return {
    pcr_oi: tco > 0 ? parseFloat((tpo / tco).toFixed(3)) : null,
    pcr_volume: tcv > 0 ? parseFloat((tpv / tcv).toFixed(3)) : null,
    total_call_oi: tco,
    total_put_oi: tpo,
    call_oi_change: tcoChg,
    put_oi_change: tpoChg,
    total_call_vol: tcv,
    total_put_vol: tpv,
    max_pain_strike: maxPainStrike,
    max_pain_oi: maxPainOI,
    spot: spot
  };
}

function doGet(e) {
  var params = (e && e.parameter) ? e.parameter : {};
  var symbol = params.symbol || "NIFTY";
  var expiry = params.expiry || "";
  var format = params.format || "json";
  
  if (!expiry) {
    return ContentService.createTextOutput(JSON.stringify({
      error: "Missing expiry. Use ?expiry=DD-Mon-YYYY",
      example: "?symbol=NIFTY&expiry=18-Aug-2026"
    })).setMimeType(ContentService.MimeType.JSON);
  }
  
  if (format === "expiries") {
    try {
      var data = fetchNSEOptionChain(symbol, expiry);
      return ContentService.createTextOutput(JSON.stringify({
        symbol: symbol,
        expiries: data.allExpiries
      })).setMimeType(ContentService.MimeType.JSON);
    } catch (err) {
      return ContentService.createTextOutput(JSON.stringify({
        error: err.toString()
      })).setMimeType(ContentService.MimeType.JSON);
    }
  }
  
  try {
    var data = fetchNSEOptionChain(symbol, expiry);
    var csvRows = flattenToCSV(data.chain);
    var summary = computeSummary(data.chain, data.underlying);
    
    return ContentService.createTextOutput(JSON.stringify({
      success: true,
      symbol: symbol,
      expiry: expiry,
      timestamp: data.timestamp,
      underlying: data.underlying,
      totalStrikes: data.totalStrikes,
      summary: summary,
      chain: csvRows
    })).setMimeType(ContentService.MimeType.JSON);
    
  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({
      success: false,
      error: err.toString()
    })).setMimeType(ContentService.MimeType.JSON);
  }
}

function test() {
  var result = doGet({ parameter: { symbol: "NIFTY", expiry: "18-Aug-2026" } });
  Logger.log(result.getContentText());
  return result.getContentText();
}
