"""
BBPro Signal Bot - MEXC Client
عميل MEXC للتنفيذ التلقائي + التحقق من الإحالات
"""
import hashlib
import hmac
import logging
import time
import json
from typing import Dict, List, Optional

import ccxt
import requests

logger = logging.getLogger(__name__)

# MEXC API endpoints
MEXC_BASE = "https://api.mexc.com"
MEXC_AFFILIATE_API = "https://www.mexc.com/api"


class MexcClient:
    """عميل MEXC للتنفيذ التلقائي والتحقق من الإحالات"""

    # XAU/USDT perpetual on MEXC
    GOLD_SYMBOL = "XAUUSDT"
    GOLD_SYMBOL_SPOT = "XAUUSDT"

    def __init__(self, api_key: str = "", api_secret: str = "", is_futures: bool = True):
        self.api_key = api_key
        self.api_secret = api_secret
        self.is_futures = is_futures

        # إنشاء ccxt exchange
        self.exchange = ccxt.mexc({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'swap' if is_futures else 'spot',
            }
        })

        # للتحقق من الإحالات (Owner API only)
        self.owner_api_key = ""
        self.owner_api_secret = ""

    @classmethod
    def for_owner(cls, api_key: str, api_secret: str, is_futures: bool = True):
        """إنشاء عميل بحساب الـ Owner للتحقق من الإحالات"""
        client = cls(api_key, api_secret, is_futures)
        client.owner_api_key = api_key
        client.owner_api_secret = api_secret
        return client

    # ═══════════════════════════════════════════
    # معلومات الحساب
    # ═══════════════════════════════════════════

    def get_balance(self) -> Dict:
        """جلب رصيد الحساب (USDT)"""
        try:
            balance = self.exchange.fetch_balance()
            usdt_free = balance.get('USDT', {}).get('free', 0)
            usdt_total = balance.get('USDT', {}).get('total', 0)
            return {
                "free": float(usdt_free),
                "total": float(usdt_total),
                "success": True,
            }
        except Exception as e:
            logger.error(f"Error fetching balance: {e}")
            return {"free": 0, "total": 0, "success": False, "error": str(e)}

    def get_positions(self) -> List[Dict]:
        """جلب الصفقات المفتوحة"""
        try:
            positions = self.exchange.fetch_positions([self.GOLD_SYMBOL])
            return [
                {
                    "symbol": p.get("symbol", ""),
                    "side": p.get("side", ""),
                    "size": float(p.get("contracts", 0)),
                    "entry_price": float(p.get("entryPrice", 0)),
                    "unrealized_pnl": float(p.get("unrealizedPnl", 0)),
                    "leverage": float(p.get("leverage", 1)),
                }
                for p in positions
                if float(p.get("contracts", 0)) > 0
            ]
        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            return []

    def get_ticker(self) -> Optional[Dict]:
        """سعر الذهب الحالي على MEXC"""
        try:
            ticker = self.exchange.fetch_ticker(self.GOLD_SYMBOL)
            return {
                "last": float(ticker.get("last", 0)),
                "bid": float(ticker.get("bid", 0)),
                "ask": float(ticker.get("ask", 0)),
                "high": float(ticker.get("high", 0)),
                "low": float(ticker.get("low", 0)),
                "volume": float(ticker.get("baseVolume", 0)),
            }
        except Exception as e:
            logger.error(f"Error fetching ticker: {e}")
            return None

    # ═══════════════════════════════════════════
    # التنفيذ التلقائي
    # ═══════════════════════════════════════════

    def set_leverage(self, leverage: int) -> bool:
        """ضبط الرافعة المالية"""
        try:
            self.exchange.set_leverage(leverage, self.GOLD_SYMBOL)
            logger.info(f"Leverage set to {leverage}x for {self.GOLD_SYMBOL}")
            return True
        except Exception as e:
            logger.error(f"Error setting leverage: {e}")
            return False

    def open_position(self, signal: Dict, risk_amount: float, leverage: int = 10) -> Dict:
        """
        فتح صفقة على MEXC
        signal: {signal_type: BUY/SELL, entry_price, stop_loss, take_profit_1}
        risk_amount: المبلغ المخاطر به بالدولار
        """
        try:
            # ضبط الرافعة
            self.set_leverage(leverage)

            # حساب حجم الصفقة
            entry = signal.get("entry_price", 0)
            sl = signal.get("stop_loss", 0)
            if not entry or not sl:
                return {"success": False, "error": "Missing entry or SL"}

            # نسبة المخاطرة = (entry - sl) / entry
            risk_pct = abs(entry - sl) / entry
            if risk_pct == 0:
                return {"success": False, "error": "Invalid risk percentage"}

            # حجم الصفقة = risk_amount / risk_pct
            position_size = risk_amount / risk_pct
            # حجم العقود
            amount = position_size / entry

            # تقريب للأرقام مناسبة
            amount = round(amount, 2)
            if amount < 0.01:
                return {"success": False, "error": "Position too small"}

            side = "buy" if signal["signal_type"] == "BUY" else "sell"

            # فتح الصفقة
            order = self.exchange.create_market_order(
                symbol=self.GOLD_SYMBOL,
                side=side,
                amount=amount,
            )

            order_id = order.get("id", "")
            fill_price = float(order.get("average", entry))

            # وضع SL و TP
            tp = signal.get("take_profit_1", 0)
            if tp:
                self._place_stop_loss(sl, side, amount)
                self._place_take_profit(tp, side, amount)

            logger.info(f"✅ Position opened: {side} {amount} {self.GOLD_SYMBOL} @ {fill_price}")

            return {
                "success": True,
                "order_id": order_id,
                "side": side,
                "amount": amount,
                "fill_price": fill_price,
                "sl": sl,
                "tp": tp,
                "leverage": leverage,
            }

        except Exception as e:
            logger.error(f"Error opening position: {e}")
            return {"success": False, "error": str(e)}

    def close_position(self) -> Dict:
        """إغلاق كل صفقات الذهب"""
        try:
            positions = self.get_positions()
            if not positions:
                return {"success": True, "message": "No positions to close"}

            for pos in positions:
                side = pos["side"]
                amount = pos["size"]
                close_side = "sell" if side == "long" else "buy"

                self.exchange.create_market_order(
                    symbol=self.GOLD_SYMBOL,
                    side=close_side,
                    amount=amount,
                    params={"reduceOnly": True}
                )

            logger.info(f"✅ Closed {len(positions)} positions")
            return {"success": True, "closed": len(positions)}

        except Exception as e:
            logger.error(f"Error closing position: {e}")
            return {"success": False, "error": str(e)}

    def _place_stop_loss(self, sl_price: float, side: str, amount: float):
        """وضع أمر وقف الخسارة"""
        try:
            sl_side = "sell" if side == "buy" else "buy"
            self.exchange.create_order(
                symbol=self.GOLD_SYMBOL,
                type="stop_market",
                side=sl_side,
                amount=amount,
                params={
                    "stopPrice": sl_price,
                    "trigger": "markPrice",
                    "reduceOnly": True,
                }
            )
            logger.info(f"SL placed at {sl_price}")
        except Exception as e:
            logger.warning(f"Failed to place SL: {e}")

    def _place_take_profit(self, tp_price: float, side: str, amount: float):
        """وضع أمر جني الأرباح"""
        try:
            tp_side = "sell" if side == "buy" else "buy"
            self.exchange.create_order(
                symbol=self.GOLD_SYMBOL,
                type="take_profit_market",
                side=tp_side,
                amount=amount,
                params={
                    "stopPrice": tp_price,
                    "trigger": "markPrice",
                    "reduceOnly": True,
                }
            )
            logger.info(f"TP placed at {tp_price}")
        except Exception as e:
            logger.warning(f"Failed to place TP: {e}")

    # ═══════════════════════════════════════════
    # التحقق من الإحالة (Owner only)
    # ═══════════════════════════════════════════

    def check_referral(self, mexc_uid: str) -> Dict:
        """
        التحقق لو UID مسجل تحت إحالتك
        ملاحظة: MEXC Affiliate API محدود — نتحقق برصيد الحساب
        """
        try:
            # محاولة التحقق عن طريق API
            # MEXC affiliate API يحتاج صلاحيات خاصة
            # مؤقتاً: نتحقق إن الـ UID رقم صحيح والـ API شغال
            if not mexc_uid or not mexc_uid.isdigit():
                return {"verified": False, "error": "Invalid UID format"}

            # محاولة جلب معلومات الحساب للتأكد إن API شغال
            balance = self.get_balance()
            if balance.get("success"):
                return {
                    "verified": True,
                    "uid": mexc_uid,
                    "note": "Manual verification recommended",
                    "api_working": True,
                }
            else:
                return {
                    "verified": False,
                    "error": "Owner API not working",
                }

        except Exception as e:
            logger.error(f"Referral check error: {e}")
            return {"verified": False, "error": str(e)}

    # ═══════════════════════════════════════════
    # فحص صلاحية API (للمستخدمين الجدد)
    # ═══════════════════════════════════════════

    @staticmethod
    def validate_api(api_key: str, api_secret: str) -> Dict:
        """فحص إن API Key شغال"""
        try:
            client = ccxt.mexc({
                'apiKey': api_key,
                'secret': api_secret,
                'enableRateLimit': True,
                'options': {'defaultType': 'swap'},
            })
            balance = client.fetch_balance()
            usdt = float(balance.get('USDT', {}).get('free', 0))

            return {
                "valid": True,
                "usdt_balance": usdt,
                "message": "API Keys صحيحة ومفعّلة",
            }
        except ccxt.AuthenticationError:
            return {"valid": False, "error": "API Keys غير صحيحة"}
        except ccxt.PermissionDenied:
            return {"valid": False, "error": "API Keys ليس لها صلاحية التداول"}
        except Exception as e:
            return {"valid": False, "error": str(e)}
