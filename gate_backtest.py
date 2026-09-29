#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🎯 باك تيست البوابات نفسها: إيه اللي هيطفّل لو مررنا التاريخ كله
على نفس فلاتر النشر الحية؟ (مقارنة: قبل البوابات vs بعدها)
ملاحظة تقريب: SMC/شمعة التأكيد على فريم 1h (اللأيف بيستخدم 15m) —
والمكوّنات اللحظية (AI/DXY/US10Y) مستثناة لأنها مش قابلة للاستنساخ تاريخياً.
"""
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("STATE_DIR", "/tmp")

import backtest
from strategies import ALL_STRATEGIES
from smc_analyzer import SMCAnalyzer

BAD_HOURS = {3, 9, 17, 21}
MIN_CONF = 85
DEAD_CONF = 90
SMC_MIN = 3
MIN_RR = 1.5
HOLD_BARS = backtest.HOLD_BARS.get("MEDIUM", 24)
COOLDOWN = backtest.COOLDOWN
MIN_BARS = backtest.MIN_BARS
STEP = backtest.STEP

smc = SMCAnalyzer()
df = backtest.fetch_gc("1y", "1h")
print(f"شمعات 1h: {len(df)}")

MEDIUM = {k: v for k, v in ALL_STRATEGIES.items() if v["trade_type"] == "MEDIUM"}


def session_of(hour):
    if 0 <= hour < 5:
        return "ASIAN"
    if 7 <= hour < 15:
        return "LONDON"
    if 12 <= hour < 20:
        return "NEW_YORK"
    return "DEAD"


def atr_of(window, n=14):
    hl = window["high"] - window["low"]
    hc = (window["high"] - window["close"].shift()).abs()
    lc = (window["low"] - window["close"].shift()).abs()
    tr = __import__("pandas").concat([hl, hc, lc], axis=1).max(axis=1)
    return float(tr.iloc[-n:].mean())


funnel = {"raw": 0, "multi": 0, "premium": 0, "bad_hour": 0,
          "quality": 0, "smc": 0, "candle": 0, "rr": 0, "published": 0}
results_gated = []     # (outcome, r, hour)
results_base = []      # بدون بوابات
last_pub = -999
last_pub_base = -999

i = MIN_BARS
while i < len(df) - 1:
    window = df.iloc[i - MIN_BARS: i + 1]
    hour = int(df.index[i].hour)

    # ── توليد خام
    sigs = []
    for name, cfg in MEDIUM.items():
        try:
            s = cfg["func"](window, "XAU/USD", "MEDIUM")
        except Exception:
            s = None
        if s and s.get("signal_type") in ("BUY", "SELL"):
            s["strategy_name"] = name
            sigs.append(s)
    funnel["raw"] += len(sigs)

    # ── بوابة التأكيد المتعدد (زي اللأيف بالظبط)
    dcount = {}
    for s in sigs:
        dcount[s["signal_type"]] = dcount.get(s["signal_type"], 0) + 1
    confirmed = []
    for s in sigs:
        c = dcount[s["signal_type"]]
        if c >= 2 and s["confidence"] >= 75:
            confirmed.append(s)
        elif c == 1 and s["confidence"] >= 80:
            confirmed.append(s)
    # بوابة R:R على الأهداف الأصلية — قبل أي تعديل (زي ترتيب اللأيف)
    ok_rr = []
    for s in confirmed:
        e, t2, sl = s.get("entry_price", 0), s.get("take_profit_2", 0), s.get("stop_loss", 0)
        if e > 0 and sl > 0 and t2 > 0:
            rr = abs(t2 - e) / abs(e - sl)
            if rr < MIN_RR:
                funnel["rr"] += 1
                continue
        ok_rr.append(s)
    confirmed = ok_rr
    funnel["multi"] += len(confirmed)

    # أعلى ثقة لكل اتجاه (منع تكرار الاتجاه في نفس المسح)
    best = {}
    for s in confirmed:
        d = s["signal_type"]
        if d not in best or s["confidence"] > best[d]["confidence"]:
            best[d] = s

    # ── البازلاين (بدون بوابات): نحاكي أعلى إشارة لكل اتجاه
    if i - last_pub_base >= COOLDOWN and best:
        pick = max(best.values(), key=lambda s: s["confidence"])
        res = backtest.simulate(df, i, pick, "MEDIUM")
        if res:
            results_base.append((res["outcome"], res["r"], hour))
            last_pub_base = i

    # ── البايبلاين الكامل
    if i - last_pub < COOLDOWN or not best:
        i += STEP
        continue

    gate = DEAD_CONF if session_of(hour) in ("ASIAN", "DEAD") else MIN_CONF

    published = False
    for s in best.values():
        STRUCT_ONLY = os.getenv("STRUCT_ONLY", "0") == "1"
        # 1) Premium/Discount على آخر 150 شمعة
        try:
            smc.apply_premium_discount(s, df.iloc[max(0, i - 149): i + 1])
        except Exception:
            pass
        funnel["premium"] += 1

        # 2) ساعات وحشة
        if hour in BAD_HOURS:
            funnel["bad_hour"] += 1
            continue

        # 3) بوابة الثقة (تتخطى في وضع البوابات الهيكلية)
        if not STRUCT_ONLY and s["confidence"] < gate:
            funnel["quality"] += 1
            continue

        # 4) بوابة SMC (1h بدل 15m)
        try:
            g = smc.directional_gate(df.iloc[max(0, i - 119): i + 1],
                                     s["signal_type"], SMC_MIN)
            if not g["passed"]:
                funnel["smc"] += 1
                continue
        except Exception:
            pass

        # 5) شمعة التأكيد — آخر شمعة مقفولة توافق الاتجاه
        last_closed = window.iloc[-2]
        bullish = last_closed["close"] > last_closed["open"]
        if (s["signal_type"] == "BUY" and not bullish) or \
           (s["signal_type"] == "SELL" and bullish):
            funnel["candle"] += 1
            continue

        # 6) SL/TP ديناميكي (ATR) + أهداف سيولة + بوابة R:R
        entry = float(df["close"].iloc[i])
        atr = atr_of(window)
        is_buy = s["signal_type"] == "BUY"
        sl = entry - (atr * 1.5) if is_buy else entry + (atr * 1.5)
        tp1 = entry + atr if is_buy else entry - atr
        tp2 = entry + (atr * 2) if is_buy else entry - (atr * 2)
        try:
            lt = smc.liquidity_targets(df.iloc[max(0, i - 249): i + 1],
                                       entry, sl, s["signal_type"], atr)
            if lt and lt.get("tp1"):
                if (is_buy and entry < lt["tp1"] < tp2) or \
                   ((not is_buy) and tp2 < lt["tp1"] < entry):
                    tp1 = lt["tp1"]
        except Exception:
            pass
        # ✅ نشر — نحاكي النتيجة الفعلية
        sim_sig = dict(s, entry_price=entry, stop_loss=sl,
                       take_profit_1=tp1, take_profit_2=tp2)
        res = backtest.simulate(df, i, sim_sig, "MEDIUM")
        funnel["published"] += 1
        if res:
            results_gated.append((res["outcome"], res["r"], hour))
        published = True

    if published:
        last_pub = i
    i += STEP


def summarize(res):
    n = len(res)
    wins = sum(1 for o, _, _ in res if o == "WIN")
    losses = sum(1 for o, _, _ in res if o == "LOSS")
    to = sum(1 for o, _, _ in res if o == "TIMEOUT")
    total_r = sum(r for _, r, _ in res)
    wr = wins / (wins + losses) * 100 if (wins + losses) else 0
    return n, wins, losses, to, wr, total_r


print("\n" + "=" * 60)
print("🎯 نتيجة مقارنة: قبل البوابات vs بعد البوابات (سنة، 1h)")
print("=" * 60)
for label, res in [("بدون بوابات (زي أول الإشارات)", results_base),
                   ("بعد البوابات كاملة", results_gated)]:
    n, w, l, t, wr, tr = summarize(res)
    avg = tr / n if n else 0
    print(f"\n{label}:")
    print(f"  إشارات: {n} | ربح: {w} | خسارة: {l} | انتهت مدة: {t}")
    print(f"  نسبة النجاح (محسومة): {wr:.1f}% | إجمالي: {tr:+.1f}R | متوسط: {avg:+.2f}R")

print("\n🔎 القمع (Funnel) — إيه اللي طفّل إيه:")
print(f"  خام: {funnel['raw']} | بعد التأكيد المتعدد: {funnel['multi']}")
print(f"  طفّلتهم الساعات الوحشة: {funnel['bad_hour']} | بوابة الثقة: {funnel['quality']}")
print(f"  بوابة SMC: {funnel['smc']} | شمعة التأكيد: {funnel['candle']} | R:R: {funnel['rr']}")
print(f"  المنشورة: {funnel['published']}")

out = {
    "baseline": dict(zip(["n", "wins", "losses", "timeouts", "win_rate", "total_r"], summarize(results_base))),
    "gated": dict(zip(["n", "wins", "losses", "timeouts", "win_rate", "total_r"], summarize(results_gated))),
    "funnel": funnel,
    "generated_at": datetime.utcnow().isoformat(),
}
with open("/tmp/gate_backtest.json", "w") as f:
    json.dump(out, f, indent=2, ensure_ascii=False)
print("\n💾 /tmp/gate_backtest.json")
