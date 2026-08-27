"""
BBPro Signal Bot - Multi-Timeframe Confluence
تحليل التطابق بين أطر زمنية متعددة (1h + 4h + 1d)
"""
import logging
from typing import Dict, List, Optional
import pandas as pd

from market_data import MarketDataFetcher
from strategies import ALL_STRATEGIES

logger = logging.getLogger(__name__)


class ConfluenceAnalyzer:
    """يحلل التطابق بين 1h, 4h, 1d"""

    TIMEFRAMES = ["1h", "4h", "1d"]

    def __init__(self, fetcher: MarketDataFetcher):
        self.fetcher = fetcher

    def _run_strategies_on_tf(self, timeframe: str, symbol: str = "XAU/USD") -> List[Dict]:
        """يشغل كل الاستراتيجيات على إطار زمني محدد"""
        signals = []
        try:
            df = self.fetcher.fetch_ohlcv(symbol, timeframe, 200)
            if df.empty or len(df) < 50:
                logger.warning(f"Insufficient data for {timeframe}")
                return signals

            for name, config in ALL_STRATEGIES.items():
                try:
                    func = config["func"]
                    trade_type = config["trade_type"]
                    sig = func(df, symbol, trade_type)
                    if sig and sig.get("signal_type") != "NEUTRAL":
                        sig["timeframe"] = timeframe
                        signals.append(sig)
                except Exception as e:
                    logger.debug(f"Strategy {name} on {timeframe}: {e}")

        except Exception as e:
            logger.error(f"Error analyzing {timeframe}: {e}")

        return signals

    def analyze_confluence(self) -> Dict:
        """
        يحلل التطابق بين الأطر الزمنية
        Returns: direction, confidence, timeframes_agreeing, per_timeframe, confluence_level
        """
        per_timeframe: Dict[str, List[Dict]] = {}
        directions: Dict[str, str] = {}

        for tf in self.TIMEFRAMES:
            sigs = self._run_strategies_on_tf(tf)
            per_timeframe[tf] = sigs

            if not sigs:
                directions[tf] = "NEUTRAL"
                continue

            # اتجاه الإطار = أغلبية الإشارات
            buy_count = sum(1 for s in sigs if s["signal_type"] == "BUY")
            sell_count = sum(1 for s in sigs if s["signal_type"] == "SELL")

            if buy_count > sell_count:
                directions[tf] = "BUY"
            elif sell_count > buy_count:
                directions[tf] = "SELL"
            else:
                directions[tf] = "NEUTRAL"

        # حساب التطابق
        non_neutral = {tf: d for tf, d in directions.items() if d != "NEUTRAL"}
        agreeing_timeframes = list(non_neutral.keys())

        # هل كلها متفقة؟
        unique_directions = set(non_neutral.values())

        if len(agreeing_timeframes) == 3 and len(unique_directions) == 1:
            confluence_level = "STRONG"
            direction = unique_directions.pop()
            confidence_boost = 20
        elif len(agreeing_timeframes) == 2 and len(unique_directions) == 1:
            confluence_level = "MEDIUM"
            direction = unique_directions.pop()
            confidence_boost = 10
        elif len(agreeing_timeframes) >= 2 and len(unique_directions) > 1:
            confluence_level = "MIXED"
            direction = "NEUTRAL"
            confidence_boost = 0
        else:
            confluence_level = "WEAK"
            direction = list(unique_directions)[0] if unique_directions else "NEUTRAL"
            confidence_boost = 0

        # متوسط الثقة من كل الأطر
        all_confs = []
        for tf, sigs in per_timeframe.items():
            for s in sigs:
                all_confs.append(s.get("confidence", 0))
        avg_confidence = sum(all_confs) / len(all_confs) if all_confs else 0

        return {
            "direction": direction,
            "confluence_level": confluence_level,
            "confidence_boost": confidence_boost,
            "avg_confidence": avg_confidence,
            "timeframes_agreeing": agreeing_timeframes,
            "directions": directions,
            "per_timeframe": per_timeframe,
        }

    def format_confluence_report(self, data: Dict) -> str:
        """تقرير التطابق بصيغة عربية"""
        level = data["confluence_level"]
        level_emoji = {"STRONG": "🟢 تطابق قوي", "MEDIUM": "🟡 تطابق متوسط",
                        "MIXED": "🔴 تضارب", "WEAK": "⚪ ضعيف"}.get(level, "⚪")

        direction = data["direction"]
        dir_emoji = "🟢 شراء" if direction == "BUY" else "🔴 بيع" if direction == "SELL" else "⚪ محايد"

        msg = "📊 تحليل التطابق متعدد الأطر\n"
        msg += "━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"🎯 الاتجاه: {dir_emoji}\n"
        msg += f"💪 التطابق: {level_emoji}\n"
        msg += f"📈 متوسط الثقة: {data['avg_confidence']:.0f}%\n"
        msg += f"🔢 الأطر المتفقة: {len(data['timeframes_agreeing'])}/3\n\n"

        # تفصيل كل إطار زمني
        tf_names = {"1h": "1 ساعة", "4h": "4 ساعات", "1d": "يومي"}
        for tf in self.TIMEFRAMES:
            dir_tf = data["directions"].get(tf, "NEUTRAL")
            sigs = data["per_timeframe"].get(tf, [])

            if dir_tf == "BUY":
                tf_emoji = "🟢 شراء"
            elif dir_tf == "SELL":
                tf_emoji = "🔴 بيع"
            else:
                tf_emoji = "⚪ محايد"

            sig_count = len(sigs)
            msg += f"📊 {tf_names.get(tf, tf)}: {tf_emoji}"
            if sig_count > 0:
                avg_tf_conf = sum(s.get("confidence", 0) for s in sigs) / sig_count
                msg += f" ({sig_count} إشارة, متوسط {avg_tf_conf:.0f}%)"
            msg += "\n"

        msg += f"\n📅 تحليل لحظي\n"
        msg += "🤖 BBPro Signal"

        return msg

    def enhance_signal_with_confluence(self, signal: Dict, confluence_data: Dict) -> Dict:
        """يعزز ثقة الإشارة بناءً على التطابق"""
        boost = confluence_data.get("confidence_boost", 0)

        if boost > 0:
            original = signal.get("confidence", 50)
            signal["confidence"] = min(95, original + boost)
            signal["confluence_level"] = confluence_data.get("confluence_level", "")
            signal["confluence_boost"] = boost
            logger.info(
                f"Enhanced signal: {original}% → {signal['confidence']}% "
                f"(+{boost}% from {confluence_data.get('confluence_level', '')})"
            )

        return signal
