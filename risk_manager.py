"""
صياد الشمعات | Candle Hunter - Risk Manager
إدارة المخاطر وتقسيم رأس المال
"""
import numpy as np
from typing import Dict, List, Optional, Tuple
from config import CAPITAL_TIERS, CAPITAL_TIER_CONFIG, RISK_LEVELS


class RiskManager:
    """إدارة المخاطر وحساب أحجام الصفقات"""

    def __init__(self):
        self.capital_tiers = CAPITAL_TIERS
        self.tier_config = CAPITAL_TIER_CONFIG

    def calculate_position_size(self, capital: float, entry_price: float,
                                 stop_loss: float, risk_percent: float) -> Dict:
        """
        يحسب حجم الصفقة بناءً على رأس المال ونسبة المخاطرة
        """
        risk_amount = capital * (risk_percent / 100)
        sl_distance = abs(entry_price - stop_loss)
        sl_pct = (sl_distance / entry_price) * 100

        if sl_pct == 0:
            return {"position_size_usd": 0, "position_qty": 0, "margin": 0}

        # Without leverage
        position_size_base = risk_amount / (sl_pct / 100)

        # Apply recommended leverage
        tier_config = self._get_tier_config(capital)
        leverage = tier_config["leverage"]

        position_size_with_lev = position_size_base
        max_position = capital * leverage

        if position_size_with_lev > max_position:
            position_size_with_lev = max_position

        margin = position_size_with_lev / leverage
        position_qty = position_size_with_lev / entry_price

        return {
            "position_size_usd": round(position_size_with_lev, 2),
            "position_qty": round(position_qty, 6),
            "margin_required": round(margin, 2),
            "leverage": leverage,
            "risk_amount": round(risk_amount, 2),
            "sl_pct": round(sl_pct, 2),
        }

    def calculate_risk_reward_ratio(self, entry: float, stop_loss: float,
                                      take_profit: float) -> float:
        """نسبة المخاطرة إلى الربح"""
        risk = abs(entry - stop_loss)
        reward = abs(take_profit - entry)
        if risk == 0:
            return 0
        return round(reward / risk, 2)

    def assess_risk_level(self, signal: Dict, atr_pct: float = 0) -> str:
        """
        يقيّم مستوى المخاطرة بناءً على الثقة والتقلب ونسبة R:R
        """
        confidence = signal.get("confidence", 50)
        rr = self.calculate_risk_reward_ratio(
            signal["entry_price"],
            signal["stop_loss"],
            signal["take_profit_2"]
        )

        if confidence >= 70 and rr >= 2.0 and atr_pct < 3:
            return "LOW"
        elif confidence >= 55 and rr >= 1.5 and atr_pct < 5:
            return "MEDIUM"
        else:
            return "HIGH"

    def get_capital_recommendations(self, capital: float) -> Dict:
        """يرجع توصيات رأس المال للنطاق المعطى"""
        tier_config = self._get_tier_config(capital)
        return {
            "tier_label": tier_config["label"],
            "risk_per_trade": tier_config["risk_pct"],
            "max_concurrent_trades": tier_config["max_trades"],
            "recommended_leverage": tier_config["leverage"],
        }

    def calculate_max_loss(self, capital: float, position_size: float,
                           sl_distance_pct: float) -> float:
        """أقصى خسارة محتملة"""
        return round(position_size * (sl_distance_pct / 100), 2)

    def calculate_expected_value(self, confidence: float, risk_reward: float,
                                  risk_amount: float) -> float:
        """
        القيمة المتوقعة = (نسبة النجاح × الربح) - (نسبة الخسارة × المخاطرة)
        """
        win_prob = confidence / 100
        lose_prob = 1 - win_prob
        potential_profit = risk_amount * risk_reward
        ev = (win_prob * potential_profit) - (lose_prob * risk_amount)
        return round(ev, 2)

    def get_trade_allocation_by_capital(self, signal: Dict, capital: float) -> Dict:
        """
        يحسب خطة الصفقة الكاملة لرأس مال معين
        """
        tier_config = self._get_tier_config(capital)
        risk_pct = tier_config["risk_pct"]
        leverage = tier_config["leverage"]

        entry = signal["entry_price"]
        sl = signal["stop_loss"]
        tp1 = signal["take_profit_1"]
        tp2 = signal["take_profit_2"]
        tp3 = signal["take_profit_3"]

        sl_distance_pct = abs(entry - sl) / entry * 100

        # Position sizing
        risk_amount = capital * (risk_pct / 100)
        position_size = risk_amount / (sl_distance_pct / 100)
        max_position = capital * leverage

        if position_size > max_position:
            position_size = max_position

        margin = position_size / leverage
        position_qty = position_size / entry

        # P&L calculations
        tp1_profit = position_size * (abs(tp1 - entry) / entry)
        tp2_profit = position_size * (abs(tp2 - entry) / entry)
        tp3_profit = position_size * (abs(tp3 - entry) / entry)
        max_loss = position_size * (sl_distance_pct / 100)

        # R:R
        rr = self.calculate_risk_reward_ratio(entry, sl, tp2)

        # Expected Value
        ev = self.calculate_expected_value(signal["confidence"], rr, max_loss)

        return {
            "capital": capital,
            "tier": tier_config["label"],
            "position_size_usd": round(position_size, 2),
            "position_size_pct": round((position_size / capital) * 100, 1),
            "leverage": f"{leverage}x",
            "margin_required": round(margin, 2),
            "position_qty": round(position_qty, 6),
            "potential_profit_tp1": round(tp1_profit, 2),
            "potential_profit_tp2": round(tp2_profit, 2),
            "potential_profit_tp3": round(tp3_profit, 2),
            "potential_loss": round(max_loss, 2),
            "risk_reward_ratio": rr,
            "success_probability": signal["confidence"],
            "max_concurrent_trades": tier_config["max_trades"],
            "expected_value": ev,
        }

    def get_all_capital_plans(self, signal: Dict) -> List[Dict]:
        """يرجع خطط كل مستويات رأس المال"""
        plans = []
        for capital in self.capital_tiers:
            plans.append(self.get_trade_allocation_by_capital(signal, capital))
        return plans

    def _get_tier_config(self, capital: float) -> Dict:
        """يرجع إعدادات النطاق المناسب لرأس المال"""
        for i, tier in enumerate(self.capital_tiers):
            if capital <= tier:
                return self.tier_config[tier]
        return self.tier_config[self.capital_tiers[-1]]
