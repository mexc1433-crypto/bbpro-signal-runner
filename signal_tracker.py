"""
BBPro Signal Bot - Signal Tracker
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
        msg += "🤖 BBPro Signal"

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
