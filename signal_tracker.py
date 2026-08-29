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

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "signals_data.json")


class SignalTracker:
    """يتتبع كل إشارة ويسجل النتيجة (نجاح/فشل)"""

    def __init__(self):
        self.signals: List[Dict] = []
        self._load()

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

    def check_pending_signals(self, current_price: float) -> List[Dict]:
        """فحص الإشارات المعلقة وتحديث النتيجة"""
        updated = []
        for sig in self.signals:
            if sig["status"] != "PENDING":
                continue

            entry = sig["entry_price"]
            tp1 = sig["take_profit_1"]
            sl = sig["stop_loss"]
            is_buy = sig["signal_type"] == "BUY"

            hit_tp = current_price >= tp1 if is_buy else current_price <= tp1
            hit_sl = current_price <= sl if is_buy else current_price >= sl

            if hit_tp:
                sig["status"] = "CLOSED"
                sig["result"] = "WIN"
                sig["exit_price"] = current_price
                sig["exit_time"] = datetime.now().strftime('%Y-%m-%d %H:%M')
                updated.append(sig)
                logger.info(f"✅ WIN: {sig['id']} {sig['strategy_name']} exited at {current_price}")
            elif hit_sl:
                sig["status"] = "CLOSED"
                sig["result"] = "LOSS"
                sig["exit_price"] = current_price
                sig["exit_time"] = datetime.now().strftime('%Y-%m-%d %H:%M')
                updated.append(sig)
                logger.info(f"❌ LOSS: {sig['id']} {sig['strategy_name']} exited at {current_price}")

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
        pending = [s for s in recent if s["status"] == "PENDING"]

        win_rate = (len(wins) / len(closed) * 100) if closed else 0

        # Stats per strategy
        strategy_stats = {}
        for s in closed:
            name = s["strategy_name"]
            if name not in strategy_stats:
                strategy_stats[name] = {"wins": 0, "losses": 0, "total": 0}
            strategy_stats[name]["total"] += 1
            if s["result"] == "WIN":
                strategy_stats[name]["wins"] += 1
            else:
                strategy_stats[name]["losses"] += 1

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
            "pending": len(pending),
            "win_rate": win_rate,
            "strategy_stats": strategy_stats,
            "best_strategy": best_strategy,
            "best_rate": best_rate,
            "worst_strategy": worst_strategy,
            "worst_rate": worst_rate,
        }

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
