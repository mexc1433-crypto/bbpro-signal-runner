"""
صياد الشمعات | Candle Hunter - Signal Tracker
تتبع إشارات التداول وتسجيل النجاح/الفشل
"""
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

DATA_FILE = os.path.join(os.getenv("STATE_DIR", os.path.dirname(os.path.abspath(__file__))), "signals_data.json")
os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)


class SignalTracker:
    """يتتبع كل إشارة ويسجل النتيجة (نجاح/فشل)"""

    def __init__(self):
        self.signals: List[Dict] = []
        self._load()

    # ===== FEATURE 6: Daily Drawdown Limit =====
    MAX_DAILY_LOSSES = 3         # إيقاف بعد 3 خسائر في يوم واحد
    MAX_DAILY_DRAWDOWN_PCT = 5.0  # إيقاف بعد خسارة 5% من رأس المال

    # ===== TTL for PENDING signals =====
    PENDING_TTL_HOURS = {
        "SCALPING": 2,    # ساعتين للـ scalping
        "MEDIUM": 24,     # 24 ساعة للـ medium (الأهداف بتاخد وقت أطول من 6 ساعات)
        "SWING": 72,      # 72 ساعة للـ swing
    }
    DEFAULT_TTL_HOURS = 4  # افتراضي

    def get_daily_stats(self, date_str: str = None) -> Dict:
        """إحصائيات يوم واحد — للـ drawdown limit"""
        if date_str is None:
            date_str = datetime.now().strftime('%Y-%m-%d')

        today_signals = []
        for s in self.signals:
            try:
                created = datetime.fromisoformat(s.get("created_at", ""))
                if created.strftime('%Y-%m-%d') == date_str:
                    today_signals.append(s)
            except:
                continue

        closed = [s for s in today_signals if s["status"] == "CLOSED"]
        losses = [s for s in closed if s["result"] == "LOSS"]
        wins = [s for s in closed if s["result"] == "WIN"]

        # حساب الخسارة كنسبة
        total_pnl = 0
        for s in closed:
            entry = s.get("entry_price", 0)
            exit_p = s.get("exit_price", 0)
            if entry > 0 and exit_p > 0:
                if s["signal_type"] == "BUY":
                    pnl = (exit_p - entry) / entry * 100
                else:
                    pnl = (entry - exit_p) / entry * 100
                total_pnl += pnl

        return {
            "date": date_str,
            "total": len(today_signals),
            "wins": len(wins),
            "losses": len(losses),
            "pnl_pct": total_pnl,
            "should_stop": len(losses) >= self.MAX_DAILY_LOSSES or total_pnl <= -self.MAX_DAILY_DRAWDOWN_PCT,
            "stop_reason": (
                f"خسائر {len(losses)}/{self.MAX_DAILY_LOSSES}" if len(losses) >= self.MAX_DAILY_LOSSES
                else f"drawdown {total_pnl:.1f}% حد {self.MAX_DAILY_DRAWDOWN_PCT}%"
                if total_pnl <= -self.MAX_DAILY_DRAWDOWN_PCT
                else None
            )
        }

    def should_pause_trading(self) -> tuple:
        """هل نوقف التداول اليوم؟ Returns: (bool, reason)"""
        stats = self.get_daily_stats()
        if stats["should_stop"]:
            return True, f"🛑 إيقاف يومي: {stats['stop_reason']}"
        return False, None

    def _load(self):
        """تحميل الإشارات من ملف JSON"""
        try:
            if os.path.exists(DATA_FILE):
                with open(DATA_FILE, 'r', encoding='utf-8') as f:
                    self.signals = json.load(f)
                logger.info(f"Loaded {len(self.signals)} tracked signals")
        except Exception as e:
            logger.error(f"Error loading signals data: {e}")
            self.signals = []

    def _save(self):
        """حفظ الإشارات في ملف JSON"""
        try:
            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.signals, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving signals data: {e}")

    def track_signal(self, signal: Dict):
        """تسجيل إشارة جديدة للتتبع"""
        entry = {
            "id": f"sig_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "symbol": signal.get("symbol", "XAU/USD"),
            "signal_type": signal.get("signal_type", "BUY"),
            "entry_price": signal.get("entry_price", 0),
            "take_profit_1": signal.get("take_profit_1", 0),
            "take_profit_2": signal.get("take_profit_2", 0),
            "take_profit_3": signal.get("take_profit_3", 0),
            "stop_loss": signal.get("stop_loss", 0),
            "strategy_name": signal.get("strategy_name", "Unknown"),
            "trade_type": signal.get("trade_type", "MEDIUM"),
            "confidence": signal.get("confidence", 0),
            "timestamp": signal.get("timestamp", datetime.now().strftime('%Y-%m-%d %H:%M')),
            "created_at": datetime.now().isoformat(),
            "status": "PENDING",
            "result": None,
            "exit_price": None,
            "exit_time": None,
        }
        self.signals.append(entry)
        self._save()
        logger.info(f"Tracking signal: {entry['id']} {entry['signal_type']} {entry['symbol']}")

    def check_pending_signals(self, current_price: float, candles: List[Dict] = None) -> List[Dict]:
        """فحص الإشارات المعلقة — مع Partial TP و Trailing Stop + TTL expiry"""
        updated = []
        now = datetime.now()
        for sig in self.signals:
            if sig["status"] != "PENDING":
                continue

            # فحص TTL — لو الإشارة قديمة، اقفلها كـ EXPIRED
            try:
                created = datetime.fromisoformat(sig.get("created_at", now.isoformat()))
                age_hours = (now - created).total_seconds() / 3600
                trade_type = sig.get("trade_type", "MEDIUM")
                ttl = self.PENDING_TTL_HOURS.get(trade_type, self.DEFAULT_TTL_HOURS)
                if age_hours >= ttl:
                    sig["status"] = "CLOSED"
                    if sig.get("tp1_hit"):
                        sig["result"] = "PROTECTED"
                        sig["close_type"] = "SECURED_TTL"
                    else:
                        sig["result"] = "EXPIRED"
                    sig["exit_price"] = current_price
                    sig["exit_time"] = now.strftime('%Y-%m-%d %H:%M')
                    sig["close_type"] = "TTL_EXPIRED"
                    updated.append(sig)
                    logger.info(f"⏰ EXPIRED (TTL {ttl}h): {sig['id']} {sig['signal_type']} — age {age_hours:.1f}h")
                    continue
            except Exception as e:
                logger.warning(f"TTL check failed for {sig.get('id')}: {e}")

            entry = sig["entry_price"]
            tp1 = sig.get("take_profit_1", 0)
            tp2 = sig.get("take_profit_2", 0)
            sl = sig.get("stop_loss", 0)
            is_buy = sig["signal_type"] == "BUY"
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M')

            # قمة/قاع الفترة من شموع 15 دقيقة — الحركات السريعة ما بتفلتش
            period_high = current_price
            period_low = current_price
            if candles:
                try:
                    created_dt = datetime.fromisoformat(sig.get("created_at", now.isoformat()))
                    sig_candles = [c for c in candles if c["ts"] >= created_dt]
                    if sig_candles:
                        period_high = max(max(c["high"] for c in sig_candles), current_price)
                        period_low = min(min(c["low"] for c in sig_candles), current_price)
                except Exception:
                    pass

            hit_tp1 = tp1 > 0 and (period_high >= tp1 if is_buy else period_low <= tp1)
            hit_tp2 = tp2 > 0 and (period_high >= tp2 if is_buy else period_low <= tp2)
            hit_sl = period_low <= sl if is_buy else period_high >= sl

            # ===== 🛡️ TP1 = تأمين الصفقة مش إغلاقها =====
            # اتفاق المالك: ضرب TP1 → أغلق نص الحجم + حرّك الستوب للدخول
            # الصفقة تفضل متتبعة: TP2 = WIN كامل، الستوب بعد التأمين = PROTECTED (بريك إيفن)
            if hit_tp1 and not sig.get("tp1_hit", False):
                sig["tp1_hit"] = True
                sig["tp1_price"] = tp1
                sig["secured"] = True
                # حرّك الستوب لنقطة الدخول — الباقي بلا خسارة
                sig["stop_loss"] = entry
                sig["trailing_stop"] = entry
                sig["_event"] = "TP1_SECURED"
                updated.append(sig)
                logger.info(f"🔒 TP1 SECURED: {sig['id']} {sig['strategy_name']} — SL moved to entry {entry}")

            # TP2 بعد التأمين → WIN كامل
            elif sig.get("tp1_hit") and hit_tp2:
                sig["tp2_hit"] = True
                sig["tp2_price"] = tp2
                sig["exit_price"] = tp2
                sig["exit_time"] = now_str
                sig["result"] = "WIN"
                sig["status"] = "CLOSED"
                sig["close_type"] = "FULL_TP2"
                updated.append(sig)
                logger.info(f"✅ WIN (TP2 after secure): {sig['id']} {sig['strategy_name']} exited at {tp2}")

            # الستوب بعد التأمين → PROTECTED: النص الأول ربح، والباقي على الدخول
            elif sig.get("tp1_hit") and hit_sl:
                sig["status"] = "CLOSED"
                sig["result"] = "PROTECTED"
                sig["exit_price"] = entry
                sig["exit_time"] = now_str
                sig["close_type"] = "BREAKEVEN"
                updated.append(sig)
                logger.info(f"🔒 PROTECTED (breakeven): {sig['id']} {sig['strategy_name']} — half won at TP1, rest at entry")

            # TP2 مباشرة (قفزة سريعة فوق TP1) → WIN كامل
            elif hit_tp2 and not sig.get("tp2_hit", False) and not sig.get("tp1_hit", False):
                sig["tp2_hit"] = True
                sig["tp2_price"] = tp2
                sig["exit_price"] = tp2
                sig["exit_time"] = now_str
                sig["result"] = "WIN"
                sig["status"] = "CLOSED"
                sig["close_type"] = "FULL_TP2"
                updated.append(sig)
                logger.info(f"✅ WIN (TP2): {sig['id']} {sig['strategy_name']} exited at {current_price}")

            # ===== Stop Loss قبل أي تأمين → LOSS =====
            elif hit_sl:
                sig["status"] = "CLOSED"
                sig["result"] = "LOSS"
                sig["exit_price"] = sl
                sig["exit_time"] = now_str
                sig["close_type"] = "STOP_LOSS"
                updated.append(sig)
                logger.info(f"❌ LOSS (SL): {sig['id']} {sig['strategy_name']} exited at {current_price}")

        if updated:
            self._save()

        return updated

    def get_performance_stats(self, days: int = 7) -> Dict:
        """حساب إحصائيات الأداء"""
        cutoff = datetime.now() - timedelta(days=days)
        recent = []
        for s in self.signals:
            try:
                created = datetime.fromisoformat(s["created_at"])
                if created >= cutoff:
                    recent.append(s)
            except:
                continue

        total = len(recent)
        closed = [s for s in recent if s["status"] == "CLOSED"]
        wins = [s for s in closed if s["result"] == "WIN"]
        losses = [s for s in closed if s["result"] == "LOSS"]
        protected = [s for s in closed if s["result"] == "PROTECTED"]
        expired = [s for s in closed if s["result"] == "EXPIRED"]
        pending = [s for s in recent if s["status"] == "PENDING"]
        secured_open = [s for s in pending if s.get("tp1_hit")]

        # نسبة النجاح على الصفقات المحسومة (الإشارات المؤمنة بريك إيفن ما تدخلش)
        decided = len(wins) + len(losses)
        win_rate = (len(wins) / decided * 100) if decided else 0

        # Stats per strategy
        strategy_stats = {}
        for s in closed:
            name = s["strategy_name"]
            if name not in strategy_stats:
                strategy_stats[name] = {"wins": 0, "losses": 0, "protected": 0, "total": 0}
            strategy_stats[name]["total"] += 1
            if s["result"] == "WIN":
                strategy_stats[name]["wins"] += 1
            elif s["result"] == "LOSS":
                strategy_stats[name]["losses"] += 1
            elif s["result"] == "PROTECTED":
                strategy_stats[name]["protected"] += 1

        # Best and worst strategy
        best_strategy = None
        worst_strategy = None
        best_rate = 0
        worst_rate = 100

        for name, stats in strategy_stats.items():
            rate = (stats["wins"] / stats["total"] * 100) if stats["total"] > 0 else 0
            if rate >= best_rate:
                best_rate = rate
                best_strategy = name
            if rate <= worst_rate:
                worst_rate = rate
                worst_strategy = name

        return {
            "total": total,
            "closed": len(closed),
            "wins": len(wins),
            "losses": len(losses),
            "protected": len(protected),
            "expired": len(expired),
            "pending": len(pending),
            "secured_open": len(secured_open),
            "win_rate": win_rate,
            "strategy_stats": strategy_stats,
            "best_strategy": best_strategy,
            "best_rate": best_rate,
            "worst_strategy": worst_strategy,
            "worst_rate": worst_rate,
        }

    def get_strategy_stats(self, days: int = 30) -> Dict:
        """أداء كل استراتيجية على مدى معين + قائمة الضعاف (نجاح < 45% و10 صفقات محسومة)"""
        cutoff = datetime.now() - timedelta(days=days)
        per = {}
        for s in self.signals:
            if s.get("status") != "CLOSED":
                continue
            try:
                if datetime.fromisoformat(s["created_at"]) < cutoff:
                    continue
            except Exception:
                continue
            name = s["strategy_name"]
            d = per.setdefault(name, {"trades": 0, "wins": 0, "losses": 0,
                                       "protected": 0, "timeouts": 0})
            d["trades"] += 1
            res = s.get("result", "")
            if res == "WIN":
                d["wins"] += 1
            elif res == "LOSS":
                d["losses"] += 1
            elif res == "PROTECTED":
                d["protected"] += 1
            else:
                d["timeouts"] += 1
        for name, d in per.items():
            decided = d["wins"] + d["losses"]
            d["decided"] = decided
            d["win_rate"] = round(d["wins"] / decided * 100, 1) if decided else None
        weak = [n for n, d in per.items()
                if d["decided"] >= 10 and d["win_rate"] is not None and d["win_rate"] < 45]
        return {"strategies": per, "weak": weak}

    def get_performance_report(self, days: int = 7) -> str:
        """تقرير الأداء بصيغة عربية"""
        stats = self.get_performance_stats(days)

        msg = f"📊 تقرير الأداء ({days} أيام)\n"
        msg += "━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"📈 إجمالي الإشارات: {stats['total']}\n"
        msg += f"✅ نجاح: {stats['wins']} | ❌ فشل: {stats['losses']}\n"
        msg += f"⏳ معلقة: {stats['pending']}\n"

        if stats["closed"] > 0:
            msg += f"🎯 نسبة النجاح: {stats['win_rate']:.1f}%\n\n"
        else:
            msg += "🎯 لا توجد صفقات مغلقة بعد\n\n"

        if stats["best_strategy"]:
            msg += "🏆 أفضل استراتيجية:\n"
            msg += f"  {stats['best_strategy']} ({stats['best_rate']:.0f}%)\n"

        if stats["worst_strategy"] and stats["worst_strategy"] != stats["best_strategy"]:
            msg += f"📉 أضعف استراتيجية:\n"
            msg += f"  {stats['worst_strategy']} ({stats['worst_rate']:.0f}%)\n"

        # Per strategy breakdown
        if stats["strategy_stats"]:
            msg += "\n📋 تفصيل الاستراتيجيات:\n"
            msg += "━━━━━━━━━━━━━━━━━━━━\n"
            for name, s in sorted(stats["strategy_stats"].items(),
                                   key=lambda x: x[1]["total"], reverse=True):
                rate = (s["wins"] / s["total"] * 100) if s["total"] > 0 else 0
                emoji = "🟢" if rate >= 60 else "🟡" if rate >= 40 else "🔴"
                msg += f"{emoji} {name}: {s['wins']}W/{s['losses']}L ({rate:.0f}%)\n"

        msg += f"\n📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        msg += "🤖 صياد الشمعات | Candle Hunter"

        return msg


    def get_detailed_stats(self, days: int = 30) -> Dict:
        """إحصائيات تفصيلية شاملة"""
        cutoff = datetime.now() - timedelta(days=days)
        recent = []
        for s in self.signals:
            try:
                created = datetime.fromisoformat(s["created_at"])
                if created >= cutoff:
                    recent.append(s)
            except:
                continue

        total = len(recent)
        closed = [s for s in recent if s["status"] == "CLOSED"]
        wins = [s for s in closed if s["result"] == "WIN"]
        losses = [s for s in closed if s["result"] == "LOSS"]
        pending = [s for s in recent if s["status"] == "PENDING"]

        win_rate = (len(wins) / len(closed) * 100) if closed else 0

        # Calculate P&L
        total_pnl = 0
        for s in closed:
            entry = s.get("entry_price", 0)
            exit_p = s.get("exit_price", 0)
            if entry > 0 and exit_p > 0:
                if s["signal_type"] == "BUY":
                    pnl = (exit_p - entry) / entry * 100
                else:
                    pnl = (entry - exit_p) / entry * 100
                total_pnl += pnl

        # Best/worst trades
        trade_results = []
        for s in closed:
            entry = s.get("entry_price", 0)
            exit_p = s.get("exit_price", 0)
            if entry > 0 and exit_p > 0:
                if s["signal_type"] == "BUY":
                    pnl = (exit_p - entry) / entry * 100
                else:
                    pnl = (entry - exit_p) / entry * 100
                trade_results.append((s, pnl))

        best_trade = max(trade_results, key=lambda x: x[1]) if trade_results else None
        worst_trade = min(trade_results, key=lambda x: x[1]) if trade_results else None

        # Per direction
        buy_signals = [s for s in closed if s["signal_type"] == "BUY"]
        sell_signals = [s for s in closed if s["signal_type"] == "SELL"]
        buy_wins = [s for s in buy_signals if s["result"] == "WIN"]
        sell_wins = [s for s in sell_signals if s["result"] == "WIN"]

        # Per timeframe
        tf_stats = {}
        for s in closed:
            tf = s.get("timeframe", "unknown")
            if tf not in tf_stats:
                tf_stats[tf] = {"wins": 0, "losses": 0, "total": 0}
            tf_stats[tf]["total"] += 1
            if s["result"] == "WIN":
                tf_stats[tf]["wins"] += 1
            else:
                tf_stats[tf]["losses"] += 1

        # Streak (current win/loss streak)
        streak_type = None
        streak_count = 0
        for s in sorted(closed, key=lambda x: x.get("exit_time", ""), reverse=True):
            if streak_type is None:
                streak_type = s["result"]
                streak_count = 1
            elif s["result"] == streak_type:
                streak_count += 1
            else:
                break

        return {
            "period_days": days,
            "total_signals": total,
            "closed": len(closed),
            "wins": len(wins),
            "losses": len(losses),
            "pending": len(pending),
            "win_rate": win_rate,
            "total_pnl_pct": total_pnl,
            "avg_pnl_per_trade": (total_pnl / len(closed)) if closed else 0,
            "best_trade": best_trade,
            "worst_trade": worst_trade,
            "buy_signals": len(buy_signals),
            "buy_wins": len(buy_wins),
            "buy_win_rate": (len(buy_wins) / len(buy_signals) * 100) if buy_signals else 0,
            "sell_signals": len(sell_signals),
            "sell_wins": len(sell_wins),
            "sell_win_rate": (len(sell_wins) / len(sell_signals) * 100) if sell_signals else 0,
            "tf_stats": tf_stats,
            "streak_type": streak_type,
            "streak_count": streak_count,
        }

    def format_detailed_report(self, days: int = 30) -> str:
        """تقرير إحصائي تفصيلي"""
        stats = self.get_detailed_stats(days)

        period_label = f"{days} يوم" if days < 365 else "كل الفترة"

        msg = f"📊 لوحة إحصائيات الأداء ({period_label})\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"📈 إجمالي الإشارات: {stats['total_signals']}\n"
        msg += f"✅ صفقات ناجحة: {stats['wins']}\n"
        msg += f"❌ صفقات خاسرة: {stats['losses']}\n"
        msg += f"⏳ معلقة: {stats['pending']}\n"

        if stats["closed"] > 0:
            wr_emoji = "🟢" if stats["win_rate"] >= 60 else "🟡" if stats["win_rate"] >= 40 else "🔴"
            msg += f"{wr_emoji} نسبة النجاح: {stats['win_rate']:.1f}%\n"
            msg += f"💰 إجمالي الربح: {stats['total_pnl_pct']:+.2f}%\n"
            msg += f"📐 متوسط الصفقة: {stats['avg_pnl_per_trade']:+.2f}%\n"
        else:
            msg += "🎯 لا توجد صفقات مغلقة بعد\n"

        # Streak
        if stats["streak_type"] == "WIN":
            msg += f"🔥 سلسلة نجاح: {stats['streak_count']}\n"
        elif stats["streak_type"] == "LOSS":
            msg += f"💀 سلسلة خسارة: {stats['streak_count']}\n"

        # Direction breakdown
        if stats["buy_signals"] > 0 or stats["sell_signals"] > 0:
            msg += "\n📋 حسب الاتجاه:\n"
            msg += "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            if stats["buy_signals"] > 0:
                msg += f"🟢 شراء: {stats['buy_wins']}/{stats['buy_signals']} ({stats['buy_win_rate']:.0f}%)\n"
            if stats["sell_signals"] > 0:
                msg += f"🔴 بيع: {stats['sell_wins']}/{stats['sell_signals']} ({stats['sell_win_rate']:.0f}%)\n"

        # Best/worst
        if stats["best_trade"]:
            bt = stats["best_trade"]
            msg += f"\n🏆 أفضل صفقة: {bt[1]:+.2f}% ({bt[0]['signal_type']})\n"
        if stats["worst_trade"]:
            wt = stats["worst_trade"]
            msg += f"💀 أسوأ صفقة: {wt[1]:+.2f}% ({wt[0]['signal_type']})\n"

        # Per timeframe
        if stats["tf_stats"]:
            tf_names = {"5m": "5د", "15m": "15د", "1h": "1س", "4h": "4س", "1d": "يومي"}
            msg += "\n⏱️ حسب الإطار الزمني:\n"
            msg += "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            for tf, s in sorted(stats["tf_stats"].items(),
                                key=lambda x: x[1]["total"], reverse=True):
                rate = (s["wins"] / s["total"] * 100) if s["total"] > 0 else 0
                name = tf_names.get(tf, tf)
                emoji = "🟢" if rate >= 60 else "🟡" if rate >= 40 else "🔴"
                msg += f"{emoji} {name}: {s['wins']}W/{s['losses']}L ({rate:.0f}%)\n"

        msg += f"\n📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        msg += "🤖 صياد الشمعات | Candle Hunter"

        return msg

    def get_calibration(self, days: int = 30) -> Dict:
        """🎯 معايرة الثقة: هل الـ 85% بتحقق 85% فعلًا؟
        بنقسم الإشارات المقفولة على شرائح الثقة المتوقعة ونشوف نسبة النجاح الفعلية."""
        cutoff = datetime.now() - timedelta(days=days)
        buckets = {
            "85-89": {"wins": 0, "losses": 0, "timeouts": 0},
            "90-94": {"wins": 0, "losses": 0, "timeouts": 0},
            "95-100": {"wins": 0, "losses": 0, "timeouts": 0},
        }
        for s in self.signals:
            if s.get("status") != "CLOSED":
                continue
            try:
                if datetime.fromisoformat(s.get("created_at", "")) < cutoff:
                    continue
            except Exception:
                continue
            conf = s.get("confidence", 0)
            if conf < 85:
                continue
            key = "85-89" if conf < 90 else ("90-94" if conf < 95 else "95-100")
            res = s.get("result", "")
            if res == "WIN":
                buckets[key]["wins"] += 1
            elif res == "LOSS":
                buckets[key]["losses"] += 1
            elif res == "PROTECTED":
                buckets[key]["protected"] = buckets[key].get("protected", 0) + 1
            else:
                buckets[key]["timeouts"] += 1

        out = {}
        for key, b in buckets.items():
            total = b["wins"] + b["losses"] + b["timeouts"]
            decided = b["wins"] + b["losses"]
            # PROTECTED = نص الصفقة ربح → تحسب نص ربح في النجاح الفعلي
            eff_wins = b["wins"] + (b.get("protected", 0) * 0.5)
            out[key] = {
                "signals": total,
                "wins": b["wins"], "losses": b["losses"],
                "protected": b.get("protected", 0),
                "timeouts": b["timeouts"],
                "win_rate": round(eff_wins / decided * 100, 1) if decided else None,
            }
        return out

    def get_pending_signals(self) -> List[Dict]:
        """جلب كل الإشارات المعلقة — للـ pre-close alerts"""
        return [s for s in self.signals if s.get("status") == "PENDING"]

    def cleanup_old_signals(self, days: int = 30):
        """حذف الإشارات الأقدم من N يوم"""
        cutoff = datetime.now() - timedelta(days=days)
        before = len(self.signals)
        self.signals = [
            s for s in self.signals
            if datetime.fromisoformat(s.get("created_at", datetime.now().isoformat())) >= cutoff
        ]
        removed = before - len(self.signals)
        if removed > 0:
            self._save()
            logger.info(f"Cleaned up {removed} old signals")
