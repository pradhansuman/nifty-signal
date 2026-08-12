# 📖 Trading Playbook — Nifty Option Buyer

**Your system:** 200 EMA bounce + BTST + ORB + VWAP/EMA + PCR contrarian
**You:** Pure option BUYER (Buy CE / Buy PE only — never sell)

---

## ⏰ Daily Routine

| Time (IST) | Action |
|---|---|
| **8:55 AM** | Open dashboard. Check pre-market brief (auto-alert arrives 9:00 AM) |
| **9:00 AM** | Read alert: gap, VIX, FII/DII (yesterday), overnight cues |
| **9:15-9:30** | **NO TRADING.** Let opening volatility settle. Watch the 200 EMA |
| **9:30-10:15** | **ORB window** — if Nifty breaks opening range with volume → scalp |
| **10:15-11:00** | Watch for the **200 EMA bounce setup** (the main trade) |
| **11:00-1:00** | VWAP + EMA crossover signals (secondary) |
| **1:00-2:30** | Tug-of-war zone — prefer waiting, tightening stops |
| **2:30-3:00** | Position management — no NEW entries unless setup is perfect |
| **3:00-3:25** | BTST decision (auto-alert at 3:25 PM) |
| **3:30** | Close. Daily P&L summary auto-arrives |

---

## 🎯 The Main Trade: 200 EMA Bounce

### BUY_CALLS (bounce up)
- **Entry condition:** Nifty touches/hits 200 EMA from above + ADX ≥ 18 + RSI < 70 + spot above 200 EMA
- **Action:** Buy the **ATM CE** shown on dashboard (e.g., Buy 24,450 CE)
- **Buy limit:** Premium shown (e.g., ₹240 → ₹15,600/lot)

### BUY_PUTS (breakdown)
- **Entry condition:** Nifty breaks 200 EMA by 0.8% + ADX ≥ 18 + RSI > 30
- **Action:** Buy the **ATM PE** shown

### ⛔ WAIT (no trade)
- Nifty below 200 EMA without breakdown trigger, or ADX < 18 (sideways), or RSI overbought/oversold
- **Doing nothing is a position.** Most money is lost overtrading.

---

## 🛑 Stop Loss Rules (NON-NEGOTIABLE)

1. **Index stop** — dashboard shows it (e.g., "Stop: 24,290"). If Nifty hits it, **EXIT IMMEDIATELY**. No averaging, no hoping.
2. **Premium stop** — hard rule: if your option loses **40%** of premium paid, exit. Example: bought at ₹240 → exit at ₹144.
3. **Time stop** — if trade hasn't moved your way in **2 hours**, exit. Theta eats buyers alive.
4. **Warnings** — dashboard alerts at 0.6% and 0.3% from stop. When you see them, be ready.

---

## 📐 Position Sizing (your system computes this)

- Dashboard shows **max lots** based on delta + VIX + capital
- **VIX < 12** (like today): 2 lots max (cheap premiums, but small moves)
- **VIX 12-22**: 1-2 lots
- **VIX > 22**: 1 lot or skip (options too expensive, market too wild)
- **Rule:** Total risk per trade ≤ 1-2% of capital. If 1 lot at ₹15,600 = >2% of your capital, **use fewer lots or skip**.

---

## ✅ Exit Rules (take the money)

| Situation | Action |
|---|---|
| **+50% profit** | Trail stop to breakeven. Never let a winner become a loser |
| **+100% profit** | Take 50% off, trail the rest |
| Nifty crosses back above 200 EMA (for puts) / below (for calls) | EXIT — thesis broken |
| Signal flips to EXIT on dashboard | EXIT immediately |
| Last 15 min of expiry day | Exit or close — gamma risk explodes |

---

## 🚫 What NOT To Do

1. **Never average down a losing option.** Buyers don't average — sellers do.
2. **Never hold through expiry** hoping for a miracle.
3. **Never trade the first 15 minutes** (9:15-9:30) — fake moves.
4. **Never trade with > 1-2% risk per trade.**
5. **Never trade on a flat VIX day with ADX < 18** — that's coin-flipping.
6. **Never revenge trade** after a loss. Loss limit: **-5% of capital/day = DONE for the day.**

---

## 📊 Reading the Dashboard Like a Pro

- **BUY_CALLS + FII green + DII green + PCR < 0.9** → high-confidence long
- **BUY_CALLS + FII red + DII green** → low-confidence (tug-of-war) → smaller size, faster exits
- **PCR < 0.7** → crowd euphoric → system says BUY PE (contrarian)
- **PCR > 1.4** → crowd panicked → system says BUY CE (contrarian)
- **Max Pain** → where market tends to settle at expiry → take profits before it pulls you back
- **ATM IV low (like 10-11%)** → premiums cheap → buying is fine
- **ATM IV > 20%** → premiums expensive → be extra selective

---

## 🧪 Today's Example (12-Aug)

- Morning: BUY_CALLS at 24,471, stop 24,300 → you bought CE
- Nifty fell to 24,290 → **stop hit** → system would exit, you should too
- FII -₹1,002 Cr / DII +₹5,842 Cr → tug-of-war → confirms choppy day, tight stops right call
- Lesson: the false bounce (~40% of the time) is WHY stops exist. 3 wins of +100% pay for 2 losses of -40%.

---

## 📈 Expected Edge (if you follow rules)

- ~60% of bounce signals work
- Winners avg +60-100%, losers capped at -40%
- **3 winners pay for 2 losers** — that's the math that makes this profitable
- The system's job: keep you disciplined. Your job: follow it exactly.
