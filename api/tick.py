"""
api/tick.py — Vercel Serverless Entry Point
=============================================
Single-tick execution for Vercel serverless.
Called by Vercel Cron every 1-5 minutes.

Each tick:
  1. Fetch latest bars from Yahoo Finance
  2. Run full analysis (8 strategies + SMC + VWAP + Divergence)
  3. Send signal to Telegram if conditions met
  4. Check active signals for TP/SL hit
  5. Return status
"""

import asyncio
import sys
import os
import json
import time
import traceback
from datetime import datetime, timezone

# Add bot directory to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bot"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bot"))

# Force signal-only mode
os.environ["SIGNAL_ONLY_MODE"] = "true"


async def _run_tick():
    """Run a single bot tick and return results."""
    from config import load_config, TradeDirection, BreakoutMode
    from indicators import compute_all_indicators
    from filters import multi_layer_filter
    from risk_manager import calculate_sl_tp
    from ctrader_client import CTraderClient, SymbolInfo, Bar
    from notifications.telegram import create_notifier
    from candlestick import detect_all_patterns
    from strategies import StrategyManager
    from multi_tf import MultiTFAnalyzer
    from sr_levels import SRLevels
    from signal_tracker import SignalTracker
    from smc import SmartMoneyConcepts
    from vwap import VWAPStrategy
    from risk_manager_pro import RiskManagerPro
    from market_regime import MarketRegimeDetector
    from divergence import DivergenceDetector
    import numpy as np
    import uuid

    cfg = load_config()
    cfg.signal_only_mode = True
    cfg.web_monitor_enabled = False

    client = CTraderClient(cfg)
    notifier = create_notifier(
        cfg.telegram_bot_token, cfg.telegram_chat_id, cfg.telegram_enabled
    )

    smc = SmartMoneyConcepts()
    vwap = VWAPStrategy()
    risk_pro = RiskManagerPro()
    regime_detector = MarketRegimeDetector()
    divergence = DivergenceDetector()
    strategy_mgr = StrategyManager()
    mtf_analyzer = MultiTFAnalyzer()
    sr_calc = SRLevels(lookback=cfg.sr_lookback)

    results = []
    symbols = cfg.symbols if cfg.multi_symbol_mode else [cfg.symbol]

    for symbol in symbols:
        try:
            cfg.symbol = symbol
            from symbol_profiles import apply_profile
            apply_profile(cfg, symbol)

            # Fetch bars
            warmup = max(cfg.bb_period, cfg.slow_ema_period, cfg.atr_period) + 50
            bars = await client.get_recent_bars(symbol, cfg.timeframe, count=warmup)

            if not bars or len(bars) < 50:
                results.append({"symbol": symbol, "status": "no_data"})
                continue

            # Symbol info
            sym_info = await client.get_symbol_info(symbol)

            # Compute indicators
            closes = np.array([b.close for b in bars])
            highs = np.array([b.high for b in bars])
            lows = np.array([b.low for b in bars])
            ind = compute_all_indicators(highs, lows, closes, cfg)

            idx = -1
            close_now = float(closes[idx])
            close_prev = float(closes[idx - 1])
            bb_upper = float(ind["bb_upper"][idx])
            bb_lower = float(ind["bb_lower"][idx])
            bb_upper_p = float(ind["bb_upper"][idx - 1])
            bb_lower_p = float(ind["bb_lower"][idx - 1])
            rsi_now = float(ind["rsi"][idx])
            ema_f = float(ind["ema_fast"][idx])
            ema_s = float(ind["ema_slow"][idx])
            atr_now = float(ind["atr"][idx])
            adx_now = float(ind["adx"][idx]) if "adx" in ind else 0.0
            if np.isnan(adx_now):
                adx_now = 0.0

            if any(np.isnan([bb_upper, bb_lower, rsi_now, ema_f, ema_s, atr_now])):
                results.append({"symbol": symbol, "status": "nan_indicators"})
                continue

            # Market Regime
            regime = regime_detector.detect(bars)
            if regime.regime == "choppy":
                results.append({"symbol": symbol, "status": "choppy_skip"})
                continue

            # Multi-strategy
            best_signal = None
            best_strategy = ""
            strategy_results = strategy_mgr.run_all(bars, cfg)
            if strategy_results:
                best = strategy_mgr.get_best_signal(strategy_results)
                if best:
                    best_signal = best.signal
                    best_strategy = best.strategy

                # Filter by regime
                regime_strats = set(regime.recommended_strategies)
                if regime_strats:
                    filtered = [r for r in strategy_results if r.strategy in regime_strats]
                    if filtered:
                        best = strategy_mgr.get_best_signal(filtered)
                        if best:
                            best_signal = best.signal
                            best_strategy = best.strategy

            # MTF confluence
            mtf_result = None
            if cfg.enable_multi_tf:
                try:
                    mtf_result = await mtf_analyzer.analyze(client, symbol, cfg)
                    if mtf_result["confluence"] < cfg.min_tf_confluence:
                        results.append({"symbol": symbol, "status": "low_mtf"})
                        continue
                except Exception:
                    pass

            # Candlestick patterns
            patterns = []
            if cfg.enable_candlestick_confirm:
                try:
                    patterns = detect_all_patterns(bars[-10:])
                except Exception:
                    pass

            # SMC
            smc_result = smc.analyze(bars)
            # VWAP
            vwap_result = vwap.analyze(bars)
            # Divergence
            div_result = None
            try:
                rsi_arr = ind.get("rsi", np.array([]))
                div_result = divergence.detect_all(closes, rsi_arr)
            except Exception:
                pass

            # Determine direction
            if best_signal:
                directions = [best_signal]
            else:
                directions = [TradeDirection.BUY, TradeDirection.SELL]

            # Spread
            spread_pips = 1.0
            bid, ask = await client.get_quote(symbol)
            if bid and ask:
                spread_pips = (ask - bid) / sym_info.pip_size

            if cfg.max_spread_pips > 0 and spread_pips > cfg.max_spread_pips:
                results.append({"symbol": symbol, "status": "high_spread"})
                continue

            signal_sent = False

            for direction in directions:
                # BB Breakout check
                breakout = False
                if direction == TradeDirection.BUY:
                    if cfg.bb_mode == BreakoutMode.TOUCH_BAND:
                        breakout = close_now >= bb_upper and close_prev < bb_upper_p
                    elif cfg.bb_mode == BreakoutMode.PENETRATION_PIPS:
                        breakout = close_now >= bb_upper + sym_info.pip_size
                    else:
                        breakout = close_now > bb_upper and close_prev <= bb_upper_p
                else:
                    if cfg.bb_mode == BreakoutMode.TOUCH_BAND:
                        breakout = close_now <= bb_lower and close_prev > bb_lower_p
                    elif cfg.bb_mode == BreakoutMode.PENETRATION_PIPS:
                        breakout = close_now <= bb_lower - sym_info.pip_size
                    else:
                        breakout = close_now < bb_lower and close_prev >= bb_lower_p

                if not breakout and not best_signal:
                    continue
                if best_signal and not breakout and best_strategy != "consensus":
                    continue

                # Multi-layer filter
                side = "buy" if direction == TradeDirection.BUY else "sell"
                indicators_dict = {
                    "rsi": rsi_now, "adx": adx_now, "close": close_now,
                    "ema50": ema_f, "ema200": ema_s,
                    "spread_pips": spread_pips, "max_spread": cfg.max_spread_pips,
                    "bars": bars, "bars_h4": [], "time": datetime.now(timezone.utc),
                }
                result = multi_layer_filter(side, indicators_dict)
                score = result.get("score", 0)
                if not result.get("pass", False):
                    continue

                # SL/TP
                sl_tp = calculate_sl_tp(cfg, direction=direction, entry_price=close_now,
                                       atr_value=atr_now, pip_size=sym_info.pip_size)
                if sl_tp is None:
                    continue

                if sl_tp.sl_pips < cfg.min_sl_pips:
                    if direction == TradeDirection.BUY:
                        new_sl = close_now - cfg.min_sl_pips * sym_info.pip_size
                    else:
                        new_sl = close_now + cfg.min_sl_pips * sym_info.pip_size
                    sl_tp = type(sl_tp)(
                        sl_pips=cfg.min_sl_pips, tp_pips=sl_tp.tp_pips,
                        sl_price=new_sl, tp_price=sl_tp.tp_price,
                    )

                # R:R
                sl_dist = abs(close_now - sl_tp.sl_price)
                tp_dist = abs(sl_tp.tp_price - close_now)
                rr_ratio = tp_dist / sl_dist if sl_dist > 0 else 0

                if cfg.min_rr_ratio > 0 and rr_ratio < cfg.min_rr_ratio:
                    if direction == TradeDirection.BUY:
                        sl_tp = type(sl_tp)(
                            sl_pips=sl_tp.sl_pips,
                            tp_pips=sl_tp.sl_pips * cfg.min_rr_ratio,
                            sl_price=sl_tp.sl_price,
                            tp_price=close_now + sl_dist * cfg.min_rr_ratio,
                        )
                    else:
                        sl_tp = type(sl_tp)(
                            sl_pips=sl_tp.sl_pips,
                            tp_pips=sl_tp.sl_pips * cfg.min_rr_ratio,
                            sl_price=sl_tp.sl_price,
                            tp_price=close_now - sl_dist * cfg.min_rr_ratio,
                        )
                    rr_ratio = cfg.min_rr_ratio

                # S/R levels
                sr_text = ""
                if cfg.enable_sr_levels:
                    try:
                        sr_levels = sr_calc.calculate(bars)
                        sr_text = sr_calc.format_for_signal(sr_levels, close_now, symbol)
                    except Exception:
                        pass

                # SMC bonus
                smc_text = ""
                if smc_result and smc_result.signal:
                    if (smc_result.signal == "buy" and direction == TradeDirection.BUY) or \
                       (smc_result.signal == "sell" and direction == TradeDirection.SELL):
                        score += 10
                        smc_text = smc.format_for_signal(smc_result, symbol)

                # VWAP bonus
                vwap_text = ""
                if vwap_result and vwap_result.signal:
                    if (vwap_result.signal == "buy" and direction == TradeDirection.BUY) or \
                       (vwap_result.signal == "sell" and direction == TradeDirection.SELL):
                        score += 5
                    vwap_text = vwap.format_for_signal(vwap_result, symbol)

                # Divergence bonus
                div_text = ""
                if div_result:
                    if div_result.get("any_bullish") and direction == TradeDirection.BUY:
                        score += 8
                        div_text = "⚡ Bullish Divergence"
                    elif div_result.get("any_bearish") and direction == TradeDirection.SELL:
                        score += 8
                        div_text = "⚡ Bearish Divergence"

                # Signal Quality
                quality = None
                quality_text = ""
                try:
                    quality = risk_pro.score_signal(
                        indicators={"rsi": rsi_now, "ema_fast": ema_f, "ema_slow": ema_s,
                                    "close": close_now, "side": side},
                        mtf_confluence=mtf_result["confluence"] if mtf_result else 50,
                        ai_confidence=0, pattern_count=len(patterns),
                        rr_ratio=rr_ratio, adx=adx_now,
                    )
                    quality_text = f"Quality: {quality.grade} ({quality.score:.0f}/100) — {quality.recommendation}"
                    if quality.score < 40:
                        continue
                except Exception:
                    pass

                # Multi-TP
                multi_tp_text = ""
                try:
                    mtp = risk_pro.calculate_multi_tp(
                        entry=close_now, sl_price=sl_tp.sl_price,
                        side=side, pip_size=sym_info.pip_size,
                    )
                    multi_tp_text = risk_pro.format_multi_tp(mtp, symbol)
                    be = risk_pro.calculate_break_even(
                        entry=close_now, sl_price=sl_tp.sl_price,
                        side=side, pip_size=sym_info.pip_size,
                    )
                    multi_tp_text += f"\n💡 BE at {be['trigger_price']:.5f}"
                except Exception:
                    pass

                # Signal ID
                signal_id = str(uuid.uuid4())[:8]

                # Strategy name
                strategy_name = best_strategy if best_strategy else "BB Breakout"
                if patterns:
                    strongest = max(patterns, key=lambda p: p["strength"])
                    strategy_name += f" + {strongest['pattern']}"

                # Extra info
                extra_parts = []
                if smc_text:
                    extra_parts.append(f"🏛️ SMC:\n{smc_text}")
                if vwap_text:
                    extra_parts.append(vwap_text)
                if div_text:
                    extra_parts.append(div_text)
                if quality_text:
                    extra_parts.append(f"⭐ {quality_text}")
                if multi_tp_text:
                    extra_parts.append(f"🎯 Multi-TP:\n{multi_tp_text}")
                if regime:
                    extra_parts.append(f"📊 Regime: {regime.regime} (ADX={regime.adx:.0f})")

                # SEND SIGNAL
                notifier.send_signal(
                    symbol=symbol, side=side, entry_price=close_now,
                    sl_price=sl_tp.sl_price, tp_price=sl_tp.tp_price,
                    score=score, ai_confidence=0, rr_ratio=rr_ratio,
                    strategy=strategy_name, sr_text=sr_text,
                    signal_id=signal_id if cfg.enable_inline_buttons else "",
                )

                # Send extra analysis
                extra_text = "\n\n".join(extra_parts) if extra_parts else ""
                if extra_text:
                    notifier.send(f"📊 Analysis | {symbol}\n\n{extra_text}")

                results.append({
                    "symbol": symbol, "status": "SIGNAL_SENT",
                    "side": side, "entry": close_now,
                    "sl": sl_tp.sl_price, "tp": sl_tp.tp_price,
                    "score": score, "rr": rr_ratio,
                    "strategy": strategy_name,
                    "quality": quality.grade if quality else "N/A",
                    "regime": regime.regime if regime else "unknown",
                })
                signal_sent = True
                break

            if not signal_sent:
                results.append({
                    "symbol": symbol, "status": "no_signal",
                    "regime": regime.regime if regime else "unknown",
                    "adx": round(adx_now, 1) if adx_now else 0,
                })

        except Exception as e:
            results.append({"symbol": symbol, "status": "error", "error": str(e)[:200]})

    return results


def handler(request):
    """Vercel serverless handler."""
    try:
        results = asyncio.run(_run_tick())
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "status": "ok",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "results": results,
            }, default=str),
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "status": "error",
                "error": str(e),
                "traceback": traceback.format_exc()[:500],
            }),
        }
