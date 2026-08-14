"""Shared test helpers: synthetic market data + mocks (no network)."""
import numpy as np
import pandas as pd

IST = "Asia/Kolkata"


def make_bars(n=400, up=True, start_price=24000.0, seed=42, vol=1.5, today_bars=80):
    """Synthetic 5m OHLCV: prior session + today's session (last `today_bars`)."""
    rng = np.random.default_rng(seed)
    total = n
    # drift 2.2/bar → EMA200 steady-state lag ≈ 100×drift ≈ 220 pts ≈ 0.92% —
    # clears the 0.8% trend gate so gate tests hit the gate under test
    step = 2.2 if up else -2.2
    drift = np.cumsum(rng.normal(step, vol, total))
    close = start_price + drift
    prior = total - today_bars
    idx = list(pd.date_range("2026-08-13 09:15", periods=prior, freq="5min", tz=IST)) + \
          list(pd.date_range("2026-08-14 09:15", periods=today_bars, freq="5min", tz=IST))
    idx = pd.DatetimeIndex(idx)
    open_ = close + rng.normal(0, vol * 0.3, total)
    high = np.maximum(open_, close) + rng.uniform(0, vol, total)
    low = np.minimum(open_, close) - rng.uniform(0, vol, total)
    df = pd.DataFrame({
        "Open": open_, "High": high, "Low": low, "Close": close,
        "Volume": rng.integers(1000, 9000, total).astype(float),
    }, index=idx)
    return df


def make_flat_bars(n=400, start_price=24000.0, seed=7):
    """Choppy data around a fixed level — weak trend, low ADX."""
    rng = np.random.default_rng(seed)
    close = start_price + rng.normal(0, 2.5, n).cumsum() * 0.35
    idx = list(pd.date_range("2026-08-13 09:15", periods=n - 80, freq="5min", tz=IST)) + \
          list(pd.date_range("2026-08-14 09:15", periods=80, freq="5min", tz=IST))
    idx = pd.DatetimeIndex(idx)
    open_ = close + rng.normal(0, 0.4, n)
    high = np.maximum(open_, close) + rng.uniform(0, 1.0, n)
    low = np.minimum(open_, close) - rng.uniform(0, 1.0, n)
    return pd.DataFrame({
        "Open": open_, "High": high, "Low": low, "Close": close,
        "Volume": rng.integers(1000, 9000, n).astype(float),
    }, index=idx)


def chain_row(strike, ltp, bid=None, ask=None, delta=0.5, theta=-0.5, otype="CE"):
    """One option row dict in chain_table format."""
    bid = bid if bid is not None else ltp - 0.5
    ask = ask if ask is not None else ltp + 0.5
    return {
        "strike": strike, "ce_ltp": ltp, "ce_bid": bid, "ce_ask": ask,
        "ce_delta": delta, "ce_theta": theta,
        "pe_ltp": ltp * 0.8, "pe_bid": bid * 0.8, "pe_ask": ask * 0.8,
        "pe_delta": -delta, "pe_theta": theta,
        "ce_key": "NSE_FO|{}".format(10000 + int(strike)),
        "pe_key": "NSE_FO|{}".format(20000 + int(strike)),
        "ce_iv": 14.0, "pe_iv": 14.5, "ce_oi": 100, "pe_oi": 90, "ce_vol": 10, "pe_vol": 8,
    }


def mock_chain(rows, expiry="2026-08-18"):
    return {"rows": rows, "expiry": expiry}
