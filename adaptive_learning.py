"""
صياد الشمعات | Candle Hunter - Adaptive Learning
يتعلم من أداء الاستراتيجيات ويعدل الأوزان تلقائياً
"""
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)

DATA_FILE = os.path.join(os.getenv("STATE_DIR", os.path.dirname(os.path.abspath(__file__))), "adaptive_weights.json")
os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)


class AdaptiveLearning:
    """
    يتبع أداء كل استراتيجية في كل جلسة تداول:
    - يحسب win rate لكل استراتيجية
    - يعدل الأوزان: الاستراتيجيات الأفضل تاخد confidence boost
    - الاستراتيجيات اللي win rate < 40% بعد 15 إشارة → تقليل الوزن
    - الاستراتيجيات اللي win rate < 25% بعد 20 إشارة → تعطيل مؤقت
    """

    MIN_SIGNALS_FOR_ADJUST = 10
    MIN_SIGNALS_FOR_DISABLE = 20
    DISABLE_WINRATE = 25.0
    BOOST_WINRATE = 65.0
    DISABLE_RECOVERY_HOURS = 6
    MAX_BOOST = 15  # max +15% confidence
    MAX_PENALTY = -20  # max -20% confidence

    def __init__(self):
        self.data: Dict = {
            "strategies": {},
            "disabled": {},
            "session_stats": {},
        }
        self._load()

    def _load(self):
        try:
            if os.path.exists(DATA_FILE):
                with open(DATA_FILE, 'r') as f:
                    self.data = json.load(f)
        except:
            pass

    def _save(self):
        try:
            with open(DATA_FILE, 'w') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except:
            pass

    def record_signal(self, strategy: str, session: str, signal_type: str, confidence: float):
        """يسجل إشارة جديدة"""
        key = f"{strategy}_{session}"
        if key not in self.data["strategies"]:
            self.data["strategies"][key] = {
                "strategy": strategy,
                "session": session,
                "total": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0.0,
                "recent_results": [],
            }

        s = self.data["strategies"][key]
        s["total"] += 1
        s["recent_results"].append({"type": signal_type, "confidence": confidence, "result": None})
        # Keep only last 30
        s["recent_results"] = s["recent_results"][-30:]
        self._save()

    def record_result(self, strategy: str, session: str, result: str):
        """يسجل نتيجة (WIN/LOSS)"""
        key = f"{strategy}_{session}"
        if key not in self.data["strategies"]:
            return

        s = self.data["strategies"][key]

        if result == "WIN":
            s["wins"] += 1
        else:
            s["losses"] += 1

        s["win_rate"] = round((s["wins"] / s["total"] * 100) if s["total"] > 0 else 0, 1)

        # Update recent results (last entry)
        if s["recent_results"]:
            s["recent_results"][-1]["result"] = result

        # Check if strategy needs to be disabled
        if s["total"] >= self.MIN_SIGNALS_FOR_DISABLE and s["win_rate"] < self.DISABLE_WINRATE:
            disable_key = f"{strategy}_{session}"
            self.data["disabled"][disable_key] = (
                datetime.now() + timedelta(hours=self.DISABLE_RECOVERY_HOURS)
            ).isoformat()
            logger.warning(
                f"🧠 Adaptive: {strategy} in {session} disabled "
                f"(win rate {s['win_rate']}% < {self.DISABLE_WINRATE}%) — recovers in {self.DISABLE_RECOVERY_HOURS}h"
            )

        self._save()

    def is_disabled(self, strategy: str, session: str) -> bool:
        """هل الاستراتيجية معطلة في الجلسة دي؟"""
        key = f"{strategy}_{session}"
        if key not in self.data["disabled"]:
            return False

        try:
            recover_at = datetime.fromisoformat(self.data["disabled"][key])
            if datetime.now() >= recover_at:
                # Recovery — re-enable
                del self.data["disabled"][key]
                self._save()
                logger.info(f"🧠 Adaptive: {strategy} in {session} re-enabled")
                return False
            return True
        except:
            del self.data["disabled"][key]
            return False

    def get_adjustment(self, strategy: str, session: str) -> float:
        """
        يحسب نسبة التعديل للاستراتيجية في الجلسة دي
        Returns: +X% boost or -X% penalty
        """
        key = f"{strategy}_{session}"

        if self.is_disabled(strategy, session):
            return self.MAX_PENALTY  # full penalty

        if key not in self.data["strategies"]:
            return 0.0

        s = self.data["strategies"][key]
        if s["total"] < self.MIN_SIGNALS_FOR_ADJUST:
            return 0.0  # not enough data

        win_rate = s["win_rate"]

        if win_rate >= self.BOOST_WINRATE:
            # Scale: 65% → +5, 80% → +10, 90%+ → +15
            boost = min(
                (win_rate - self.BOOST_WINRATE) / (100 - self.BOOST_WINRATE) * self.MAX_BOOST,
                self.MAX_BOOST
            )
            return round(boost, 1)

        elif win_rate < 40:
            # Scale: 40% → 0, 25% → -15, <15% → -20
            penalty = max(
                (40 - win_rate) / 40 * self.MAX_PENALTY,
                self.MAX_PENALTY
            )
            return round(penalty, 1)

        return 0.0

    def get_all_stats(self) -> List[Dict]:
        """إحصائيات كل الاستراتيجيات"""
        stats = []
        for key, s in self.data["strategies"].items():
            stats.append({
                "strategy": s["strategy"],
                "session": s["session"],
                "total": s["total"],
                "wins": s["wins"],
                "losses": s["losses"],
                "win_rate": s["win_rate"],
                "adjustment": self.get_adjustment(s["strategy"], s["session"]),
                "disabled": self.is_disabled(s["strategy"], s["session"]),
            })
        return sorted(stats, key=lambda x: x["win_rate"], reverse=True)

    def format_report(self) -> str:
        """تقرير الأداء التكيفي"""
        stats = self.get_all_stats()
        if not stats:
            return "🧠 Adaptive Learning: لا توجد بيانات كافية بعد"

        msg = "🧠 Adaptive Learning — أداء الاستراتيجيات\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"

        for s in stats:
            emoji = "🟢" if s["win_rate"] >= 60 else "🟡" if s["win_rate"] >= 40 else "🔴"
            status = "🚫 معطلة" if s["disabled"] else f"{'+' if s['adjustment'] > 0 else ''}{s['adjustment']}%"
            msg += f"{emoji} {s['strategy']} [{s['session']}]: "
            msg += f"{s['wins']}W/{s['losses']}L ({s['win_rate']}%) → {status}\n"

        return msg
