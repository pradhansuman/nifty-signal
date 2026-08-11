#!/usr/bin/env python3
"""Quick expiry calendar test"""
from datetime import datetime, timedelta

def get_nifty_expiries(from_date=None):
    """Nifty expiries: Weekly = Tuesday, Monthly = last Thursday."""
    if from_date is None:
        from_date = datetime.now()
    
    today = from_date.date()
    expiries = []
    
    # Collect for 45 days
    for i in range(45):
        d = today + timedelta(days=i)
        dt = datetime(d.year, d.month, d.day)
        
        # Weekly: every Tuesday (weekday=1)
        if d.weekday() == 1:
            expiries.append({
                "date": d.strftime("%Y-%m-%d"),
                "display": d.strftime("%d-%b-%Y"),
                "day": d.strftime("%A"),
                "type": "weekly",
                "dte": (d - today).days,
            })
        
        # Monthly: last Thursday of each month
        # Find the last Thursday: go to the 28th, then find next Thursday
        last_day = datetime(d.year, d.month, 28)
        # Find next Thursday from the 28th
        days_to_thu = (3 - last_day.weekday()) % 7
        last_thu = last_day + timedelta(days=days_to_thu)
        
        if d == last_thu.date() and d.weekday() == 3:  # is Thursday
            # Check if this monthly is already listed
            date_str = d.strftime("%Y-%m-%d")
            if not any(e["date"] == date_str for e in expiries):
                expiries.append({
                    "date": date_str,
                    "display": d.strftime("%d-%b-%Y"),
                    "day": d.strftime("%A"),
                    "type": "monthly",
                    "dte": (d - today).days,
                })
    
    expiries.sort(key=lambda x: x["dte"])
    return expiries

exps = get_nifty_expiries()
print("Nifty Expiry Calendar (weekly=Tue, monthly=last Thu):")
for e in exps[:10]:
    flag = " ← TODAY (expiry day!)" if e["dte"] == 0 else ""
    print(f"  {e['display']} ({e['day']}) | {e['type']:7s} | {e['dte']:3d} DTE{flag}")
