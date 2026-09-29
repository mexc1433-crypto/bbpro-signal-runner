#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""باك تيست الساعات: نجاح كل ساعة من اليوم (UTC — نفس توقيت البوت على Railway)"""
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest
from strategies import ALL_STRATEGIES

df = backtest.fetch_gc("1y", "1h")
print(f"شمعات 1h: {len(df)}")

# سجل كل صفقة: (ساعة الدخول، النتيجة، R) — كل الاستراتيجيات المتوسطة مجمعة
records = []
for name, cfg in ALL_STRATEGIES.items():
    if cfg["trade_type"] != "MEDIUM":
        continue
    i = backtest.MIN_BARS
    last_signal = -999
    while i < len(df) - 1:
        if i - last_signal < backtest.COOLDOWN:
            i += backtest.STEP
            continue
        window = df.iloc[i - backtest.MIN_BARS: i + 1]
        try:
            sig = cfg["func"](window, "XAU/USD", "MEDIUM")
        except Exception:
            sig = None
        if sig and sig.get("signal_type") not in (None, "NEUTRAL"):
            res = backtest.simulate(df, i, sig, "MEDIUM")
            if res:
                hour = df.index[i].hour  # UTC
                records.append((hour, res["outcome"], res["r"]))
                last_signal = i
        i += backtest.STEP

# تجميع لكل ساعة
per_hour = defaultdict(lambda: {"trades": 0, "wins": 0, "losses": 0, "timeouts": 0, "total_r": 0.0})
for hour, outcome, r in records:
    h = per_hour[hour]
    h["trades"] += 1
    h["total_r"] += r
    if outcome == "WIN":
        h["wins"] += 1
    elif outcome == "LOSS":
        h["losses"] += 1
    else:
        h["timeouts"] += 1

print("\nساعة (UTC) | صفقات | نجاح | إجمالي R")
weak_hours = []
for hour in sorted(per_hour):
    h = per_hour[hour]
    decided = h["wins"] + h["losses"]
    wr = (h["wins"] / decided * 100) if decided else 0
    flag = ""
    if decided >= 25 and wr < 45:
        flag = " ⛔"
        weak_hours.append(hour)
    print(f"  {hour:02d}:00      | {h['trades']:5d} | {wr:4.0f}% | {h['total_r']:+7.1f}R{flag}")

print(f"\n⛔ ساعات وحشة (<45% و≥25 صفقة محسومة): {weak_hours}")
with open("/tmp/hour_stats.json", "w") as f:
    json.dump({str(h): v for h, v in per_hour.items()} | {"weak_hours": weak_hours}, f, indent=2)
print("💾 /tmp/hour_stats.json")
