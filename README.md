# BBPro Signal Bot

Bot توصيات تداول — يرسل إشارات BUY/SELL على Telegram بدون تنفيذ صفقات حقيقية.

## المميزات

- 📡 يجيب بيانات السوق من Yahoo Finance
- 📊 يحلل المؤشرات الفنية (Bollinger Bands, RSI, EMA, ATR, ADX)
- 🤖 تحليل اختياري بالذكاء الاصطناعي (Groq) لتأكيد الإشارات
- 📱 يرسل التوصيات على Telegram بالشكل:
  ```
  XAUUSD BUY NOW 4422🌟
  SL : 4413
  TP : 4430
  ```
- 🌐 لوحة مراقبة ويب (Dashboard)
- 💾 حفظ التوصيات في قاعدة بيانات SQLite

## الإعداد

1. انسخ `.env.example` إلى `.env` واملأه بال مفاتيح
2. ثبّت المتطلبات: `pip install -r requirements.txt`
3. شغّل: `python bot/main.py`

## المتغيرات المطلوبة

| المتغير | الوصف |
|---------|-------|
| `TELEGRAM_BOT_TOKEN` | توكن بوت Telegram |
| `TELEGRAM_CHAT_ID` | معرف الشات |
| `SIGNAL_ONLY_MODE` | `true` = توصيات فقط بدون تداول حقيقي |
| `GROQ_API_KEY` | (اختياري) مفتاح Groq AI |

## النشر

المنصات المدعومة: Docker, Render, Koyeb, Railway, Back4App, Termux
