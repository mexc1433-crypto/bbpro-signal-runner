#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
باك تيست تاريخي لاستراتيجيات صياد الشموع
يجيب بيانات GC=F (الذهب) من Yahoo Finance ويشغل كل استراتيجية على التاريخ
ويحسب: عدد الصفقات، نسبة النجاح (TP1 قبل SL)، المهلة، متوسط R، إجمالي R
"""
import json
import os
import sys
import time
from datetime import datetime

import pandas as pd
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from strategies import ALL_STRATEGIES

STATE = os.getenv("STATE_DIR", "/tmp")
OUT_FILE = os.path.join(STATE, "backtest_results.json")
UA = {"User-Agent": "Mozilla/5.0"}

# إعدادات المحاكاة حسب نوع التداول
HOLD_BARS = {  # أقصى عدد شمعات قبل اعتبارها مهلة
    "SCALPING": 8,    # 2h على 15m
    "MEDIUM": 24,     # 24h على 1h
    "SWING": 18,      # 72h على 4h
}
COOLDOWN = 6  # شمعات راحة بعد كل إشارة
MIN_BARS = 200
STEP = 2      # نتحرك شمعتين شمعتين للسرعة


def fetch_gc(range_, interval):
    r = requests.get(
        "https://query1.finance.yahoo.com/v8/finance/chart/GC=F",
        params={"range": range_, "interval": interval},
        headers=UA, timeout=20,
    )
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    df = pd.DataFrame(
        {"open": q["open"], "high": q["high"], "low": q["low"],
         "close": q["close"], "volume": q["volume"]},
        index=pd.to_datetime(res["timestamp"], unit="s"),
    )
    return df.dropna()


def simulate(df, i, signal, trade_type):
    """يمشي قدام من الشمعة i+1 ويراقب SL و TP1 و TP2"""
    entry = signal.get("entry_price", 0) or float(df["close"].iloc[i])
    sl = signal.get("stop_loss", 0)
    tp1 = signal.get("take_profit_1", 0)
    tp2 = signal.get("take_profit_2", 0)
    if not entry or not sl or not tp1:
        return None
    risk = abs(entry - sl)
    if risk <= 0:
        return None
    is_buy = signal.get("signal_type") == "BUY"

    max_bars = HOLD_BARS.get(trade_type, 24)
    end = min(len(df), i + 1 + max_bars)
    for j in range(i + 1, end):
        hi = float(df["high"].iloc[j]); lo = float(df["low"].iloc[j])
        if is_buy:
            sl_hit = lo <= sl
            tp1_hit = hi >= tp1
            tp2_hit = hi >= tp2 if tp2 else False
        else:
            sl_hit = hi >= sl
            tp1_hit = lo <= tp1
            tp2_hit = lo <= tp2 if tp2 else False
        # نحسب SL الأول (كونسرفاتيف — الشمعة ممكن تضرب الاتنين)
        if sl_hit and not tp1_hit:
            return {"outcome": "LOSS", "r": -1.0}
        if tp1_hit and not sl_hit:
            if tp2_hit:
                return {"outcome": "WIN", "r": abs(tp2 - entry) / risk}
            return {"outcome": "WIN", "r": abs(tp1 - entry) / risk}
        if sl_hit and tp1_hit:
            # شمعة واحدة ضربت الاتنين — نعتبرها خسارة (أسوأ احتمال)
            return {"outcome": "LOSS", "r": -1.0}
    return {"outcome": "TIMEOUT", "r": 0.0}


def run_timeframe(tf, yahoo_range, yahoo_interval):
    print(f"\n{'='*60}\n📡 بيانات {tf} (range={yahoo_range})")
    df = fetch_gc(yahoo_range, yahoo_interval)
    print(f"   {len(df)} شمعة: {df.index[0]} → {df.index[-1]}")
    results = {}

    relevant = {n: c for n, c in ALL_STRATEGIES.items() if c["trade_type"] in tf_map[tf]}
    for name, cfg in relevant.items():
        t0 = time.time()
        stats = {"trades": 0, "wins": 0, "losses": 0, "timeouts": 0,
                 "total_r": 0.0, "conf_sum": 0.0}
        i = MIN_BARS
        last_signal = -999
        while i < len(df) - 1:
            if i - last_signal < COOLDOWN:
                i += STEP
                continue
            window = df.iloc[i - MIN_BARS: i + 1]
            try:
                sig = cfg["func"](window, "XAU/USD", cfg["trade_type"])
            except Exception:
                sig = None
            if sig and sig.get("signal_type") not in (None, "NEUTRAL"):
                res = simulate(df, i, sig, cfg["trade_type"])
                if res:
                    stats["trades"] += 1
                    _okey = {"WIN": "wins", "LOSS": "losses", "TIMEOUT": "timeouts"}[res["outcome"]]
                    stats[_okey] += 1
                    stats["total_r"] += res["r"]
                    stats["conf_sum"] += sig.get("confidence", 0)
                    last_signal = i
            i += STEP

        decided = stats["wins"] + stats["losses"]
        stats["win_rate"] = round(stats["wins"] / decided * 100, 1) if decided else None
        stats["avg_r"] = round(stats["total_r"] / stats["trades"], 2) if stats["trades"] else None
        stats["avg_conf"] = round(stats["conf_sum"] / stats["trades"], 0) if stats["trades"] else None
        stats["secs"] = round(time.time() - t0, 0)
        results[name] = stats
        wr = f"{stats['win_rate']}%" if stats["win_rate"] is not None else "—"
        print(f"   {name:18s}: {stats['trades']:4d} صفقة | نجاح {wr:7s} | إجمالي {stats['total_r']:+.1f}R | متوسط {stats['avg_r'] if stats['avg_r'] is not None else '—'}R | {stats['secs']:.0f}s")

    return results


if __name__ == "__main__":
    tf_map = {
        "15m": ["SCALPING"],
        "1h": ["MEDIUM"],
        "4h": ["SWING"],
    }
    all_results = {}
    # 15m: Yahoo بيدي 60 يوم بس — كفاية للسكالبينج
    all_results["15m"] = run_timeframe("15m", "60d", "15m")
    # 1h: سنة كاملة
    all_results["1h"] = run_timeframe("1h", "1y", "1h")
    # 4h: سنتين (بيانات أكتر للسوينج)
    all_results["4h"] = run_timeframe("4h", "2y", "4h")

    with open(OUT_FILE, "w") as f:
        json.dump({"generated_at": datetime.now().isoformat(),
                   "results": all_results}, f, ensure_ascii=False, indent=2)
    print(f"\n💾 النتائج اتحفظت: {OUT_FILE}")
    print("\n✅ الباك تيست خلص")
