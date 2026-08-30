"""
وحدة التكامل المتقدم — APIs متعددة
Finnhub (أخبار) + Groq AI (تحليل) + GoldAPI (سعر) + FMP (ذهب) + Alpha Vantage (مؤشرات)
"""
import os
import json
import logging
import requests
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger("enhanced_apis")

# ===== API KEYS =====
FINNHUB_KEY = os.getenv("FINNHUB_API_KEY", "")
ALPHAVANTAGE_KEY = os.getenv("ALPHAVANTAGE_API_KEY", "")
FMP_KEY = os.getenv("FINANCIAL_API_KEY", "")
GROQ_KEY = os.getenv("GROQ_API_KEY", "")
GOLDAPI_KEY = os.getenv("GOLDAPI_TOKEN", "")

# ===== FINNHUB: أخبار لحظية =====
FINNHUB_BASE = "https://finnhub.io/api/v1"

def finnhub_news(limit=50, category="general") -> List[Dict]:
    """جلب أخبار مالية لحظية من Finnhub"""
    try:
        url = f"{FINNHUB_BASE}/news?category={category}&token={FINNHUB_KEY}"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        news = resp.json()[:limit]
        
        formatted = []
        for item in news:
            formatted.append({
                "id": item.get("id"),
                "headline": item.get("headline", ""),
                "summary": item.get("summary", ""),
                "source": item.get("source", ""),
                "url": item.get("url", ""),
                "datetime": datetime.fromtimestamp(item.get("datetime", 0)),
                "category": item.get("category", ""),
            })
        logger.info(f"📊 Finnhub: {len(formatted)} news fetched")
        return formatted
    except Exception as e:
        logger.warning(f"Finnhub news error: {e}")
        return []


# ===== GROQ AI: تحليل ذكي للأخبار =====
GROQ_BASE = "https://api.groq.com/openai/v1"
GROQ_MODEL = "openai/gpt-oss-120b"  # أقوى موديل متاح مجاناً

def groq_analyze_news(headlines: List[str], summaries: List[str] = None) -> Dict:
    """
    تحليل ذكي للأخبار الذهبية باستخدام Groq AI (gpt-oss-120b)
    يرجع: sentiment, confidence, impact, recommendation, summary_ar
    """
    try:
        news_text = ""
        for i, h in enumerate(headlines[:10]):
            news_text += f"{i+1}. {h}\n"
            if summaries and i < len(summaries):
                summary = summaries[i][:200] if summaries[i] else ""
                if summary:
                    news_text += f"   ملخص: {summary}\n"
        
        prompt = f"""أنت محلل مالي خبير في الذهب (XAU/USD). حلل الأخبار التالية وحدد تأثيرها على سعر الذهب.

الأخبار:
{news_text}

أجب بصيغة JSON فقط بدون أي نص إضافي:
{{"gold_sentiment":"bullish أو bearish أو neutral","confidence":0-100,"impact_level":"high أو medium أو low","summary_ar":"ملخص بالعربي في سطرين","recommendation":"buy أو sell أو wait","key_factors":["عامل1","عامل2"]}}"""

        url = f"{GROQ_BASE}/chat/completions"
        headers = {
            "Authorization": f"Bearer {GROQ_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": GROQ_MODEL,
            "messages": [
                {"role": "system", "content": "أنت محلل مالي متخصص في الذهب. أجب بـ JSON فقط بدون نص إضافي."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 800
        }
        
        resp = requests.post(url, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        
        msg = data["choices"][0]["message"]
        content = msg.get("content", "").strip()
        
        # لو content فاضي، نستخدم reasoning
        if not content:
            content = msg.get("reasoning", "").strip()
        
        if not content:
            raise ValueError("Empty response from Groq")
        
        # تنظيف الـ JSON
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            parts = content.split("```")
            if len(parts) >= 2:
                content = parts[1].strip()
        
        # استخراج JSON من النص لو فيه نص زائد
        if "{" in content and "}" in content:
            start = content.index("{")
            end = content.rindex("}") + 1
            content = content[start:end]
        elif "{" in content:
            # JSON ناقص — نضيف القوس
            start = content.index("{")
            content = content[start:] + "}"
        
        try:
            result = json.loads(content.strip())
        except json.JSONDecodeError:
            # JSON مقطوع — نحمل الـ summary والـ sentiment يدوياً
            import re
            sentiment_match = re.search(r'"gold_sentiment"\s*:\s*"([^"]+)"', content)
            confidence_match = re.search(r'"confidence"\s*:\s*(\d+)', content)
            summary_match = re.search(r'"summary_ar"\s*:\s*"([^"]*)"', content)
            rec_match = re.search(r'"recommendation"\s*:\s*"([^"]+)"', content)
            result = {
                "gold_sentiment": sentiment_match.group(1) if sentiment_match else "neutral",
                "confidence": int(confidence_match.group(1)) if confidence_match else 50,
                "impact_level": "medium",
                "summary_ar": summary_match.group(1) if summary_match else "",
                "recommendation": rec_match.group(1) if rec_match else "wait",
                "key_factors": []
            }
        
        result["analyzed_at"] = datetime.now().isoformat()
        
        logger.info(f"🤖 Groq AI: sentiment={result.get('gold_sentiment')}, confidence={result.get('confidence')}%")
        return result
        
    except Exception as e:
        logger.warning(f"Groq AI error: {e}")
        return {
            "gold_sentiment": "neutral",
            "confidence": 50,
            "impact_level": "low",
            "summary_ar": "تعذر تحليل الأخبار",
            "recommendation": "wait",
            "key_factors": []
        }

def groq_daily_gold_brief(news_list: List[Dict]) -> str:
    """توليد ملخص يومي ذكي بالعربي"""
    try:
        headlines = [n.get("headline", "") for n in news_list[:15]]
        
        prompt = f"""اكتب ملخص يومي احترافي بالعربي لتحليل سوق الذهب بناء على الأخبار التالية:
{chr(10).join(headlines)}

اكتب:
1. ملخص في 2-3 أسطر
2. أهم 3 نقاط مؤثرة على الذهب
3. التوقعات للجلسة القادمة
بأسلوب احترافي ومباشر بدون إيموجي."""

        url = f"{GROQ_BASE}/chat/completions"
        headers = {
            "Authorization": f"Bearer {GROQ_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": GROQ_MODEL,
            "messages": [
                {"role": "system", "content": "أنت محلل ذهب محترف. اكتب بالعربي الفصيح بدون إيموجي."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.4,
            "max_tokens": 800
        }
        
        resp = requests.post(url, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        brief = data["choices"][0]["message"]["content"]
        
        logger.info("🤖 Groq daily brief generated")
        return brief
    except Exception as e:
        logger.warning(f"Groq brief error: {e}")
        return "تعذر توليد الملخص اليومي"


# ===== GOLDAPI: سعر الذهب العالمي (LBMA) =====
def goldapi_spot() -> Dict:
    """سعر الذهب اللحظي من GoldAPI (LBMA reference)"""
    try:
        url = "https://www.goldapi.io/api/price/XAU/USD"
        headers = {"x-access-token": GOLDAPI_KEY, "Content-Type": "application/json"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        
        result = {
            "price": float(data.get("price", 0)),
            "bid": float(data.get("bid", 0)),
            "ask": float(data.get("ask", 0)),
            "spread": float(data.get("ask", 0)) - float(data.get("bid", 0)),
            "high": float(data.get("high_price", 0)),
            "low": float(data.get("low_price", 0)),
            "prev_close": float(data.get("prev_close_price", 0)),
            "exchange": data.get("exchange", ""),
        }
        logger.info(f"🥇 GoldAPI spot: ${result['price']:.2f} (spread=${result['spread']:.2f})")
        return result
    except Exception as e:
        logger.warning(f"GoldAPI error: {e}")
        return {}


# ===== FMP: سعر الذهب من البيانات المالية =====
FMP_BASE = "https://financialmodelingprep.com/stable"

def fmp_gold_price() -> Dict:
    """سعر الذهب من FMP (Gold Futures GCUSD)"""
    try:
        url = f"{FMP_BASE}/quote?symbol=GCUSD&apikey={FMP_KEY}"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list) and data:
            item = data[0]
            result = {
                "price": float(item.get("price", 0)),
                "change": float(item.get("change", 0)),
                "change_pct": float(item.get("changesPercentage", 0)),
                "high": float(item.get("dayHigh", 0)),
                "low": float(item.get("dayLow", 0)),
                "volume": int(item.get("volume", 0)),
                "name": item.get("name", "Gold Futures"),
            }
            logger.info(f"💰 FMP Gold: ${result['price']:.2f} ({result['change_pct']:+.2f}%)")
            return result
    except Exception as e:
        logger.warning(f"FMP gold price error: {e}")
        return {}


# ===== ALPHA VANTAGE: مؤشرات فنية (محدود 25/يوم) =====
AV_BASE = "https://www.alphavantage.co/query"
_av_last_call = 0

def _av_rate_limit():
    """ضمان 1 طلب كل 2 ثانية لتجنب الحظر"""
    global _av_last_call
    elapsed = time.time() - _av_last_call
    if elapsed < 2:
        time.sleep(2 - elapsed)
    _av_last_call = time.time()

def av_technical_indicator(indicator="RSI", symbol="GC=F", interval="60min", **params) -> Dict:
    """
    جلب مؤشر فني من Alpha Vantage
    المؤشرات: RSI, MACD, BBANDS, EMA, SMA, STOCH, ADX, ATR, OBV
    محدود: 25 طلب/يوم على الـ free tier
    """
    try:
        _av_rate_limit()
        params_str = "&".join([f"{k}={v}" for k, v in params.items()])
        url = f"{AV_BASE}?function={indicator}&symbol={symbol}&interval={interval}&{params_str}&apikey={ALPHAVANTAGE_KEY}"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        
        # فحص رسائل الخطأ/الحد
        if "Information" in data or "Error Message" in data or "Note" in data:
            logger.warning(f"AV {indicator} rate limited or error")
            return {}
        
        # استخراج المؤشر
        for key in data.keys():
            if key.startswith("Technical Analysis"):
                indicators = data[key]
                latest_date = list(indicators.keys())[0]
                latest = indicators[latest_date]
                result = {"indicator": indicator, "date": latest_date, "values": latest}
                logger.info(f"📈 AV {indicator}: {latest}")
                return result
        
        return data
    except Exception as e:
        logger.warning(f"Alpha Vantage {indicator} error: {e}")
        return {}


# ===== دالة التكامل الموحدة =====
def get_enhanced_market_context() -> Dict:
    """
    يجمع كل البيانات من كل الـ APIs
    يرجع context كامل للبوت يستخدمه في قرارات التداول
    """
    context = {
        "timestamp": datetime.now().isoformat(),
        "news": [],
        "ai_sentiment": {},
        "gold_spot": {},
        "fmp_gold": {},
        "economic_events": [],
    }
    
    # 1. أخبار Finnhub
    context["news"] = finnhub_news(limit=15)
    
    # 2. تحليل Groq AI للأخبار
    if context["news"]:
        headlines = [n["headline"] for n in context["news"][:8]]
        summaries = [n.get("summary", "") for n in context["news"][:8]]
        context["ai_sentiment"] = groq_analyze_news(headlines, summaries)
    
    # 3. سعر الذهب من GoldAPI (LBMA reference)
    context["gold_spot"] = goldapi_spot()
    
    # 4. سعر الذهب من FMP (Gold Futures)
    context["fmp_gold"] = fmp_gold_price()
    
    return context


def get_confidence_adjustment(ai_sentiment: Dict, signal_direction: str = "buy") -> float:
    """
    يحول تحليل AI إلى تعديل ثقة الإشارة
    لو الإشارة شراء وأخبار إيجابية = +ثقة
    لو الإشارة شراء وأخبار سلبية = -ثقة
    """
    sentiment = ai_sentiment.get("gold_sentiment", "neutral")
    confidence = ai_sentiment.get("confidence", 50)
    
    if sentiment == "neutral":
        return 0
    
    is_bullish = sentiment == "bullish"
    is_buy_signal = signal_direction.lower() in ("buy", "long")
    
    # تطابق: إشارة شراء + أخبار إيجابية OR إشارة بيع + أخبار سلبية
    if (is_bullish and is_buy_signal) or (not is_bullish and not is_buy_signal):
        return min(confidence / 10, 10)  # +0 إلى +10
    else:
        # تعارض: إشارة شراء + أخبار سلبية OR إشارة بيع + أخبار إيجابية
        return -min(confidence / 10, 10)  # -0 إلى -10


def format_gold_report(context: Dict) -> str:
    """تنسيق تقرير شامل للذهب من كل الـ APIs"""
    lines = ["📊 تقرير شامل للذهب | صياد الشمعات\n"]
    
    # سعر الذهب
    spot = context.get("gold_spot", {})
    if spot:
        lines.append(f"🥇 سعر LBMA: ${spot['price']:.2f}")
        lines.append(f"   Bid: ${spot['bid']:.2f} | Ask: ${spot['ask']:.2f}")
    
    fmp = context.get("fmp_gold", {})
    if fmp:
        lines.append(f"💰 عقود الذهب: ${fmp['price']:.2f} ({fmp['change_pct']:+.2f}%)")
    
    # تحليل AI
    ai = context.get("ai_sentiment", {})
    if ai:
        lines.append(f"\n🤖 تحليل AI ({GROQ_MODEL}):")
        lines.append(f"   الاتجاه: {ai.get('gold_sentiment', 'neutral')}")
        lines.append(f"   الثقة: {ai.get('confidence', 50)}%")
        lines.append(f"   التوصية: {ai.get('recommendation', 'wait')}")
        lines.append(f"   الملخص: {ai.get('summary_ar', '')}")
    
    return "\n".join(lines)
