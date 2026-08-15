# BBPro Signal Bot — Ultimate Edition

بوت توصيات تداول متقدم يرسل إشارات على Telegram بدون تنفيذ صفقات حقيقية.

## المميزات الكاملة

### استراتيجيات التداول (8 استراتيجيات)
1. **BB Breakout** — اختراق بولينجر باند
2. **RSI Reversal** — انعكاس RSI من التشبع
3. **EMA Crossover** — تقاطع EMA 50/200 (Golden/Death Cross)
4. **Support/Resistance** — ارتداد من مستويات الدعم/المقاومة
5. **BB Mean Reversion** — عودة للوسط بعد لمس الباند
6. **MACD Crossover** — تقاطع MACD
7. **Stochastic Reversal** — انعكاس ستوكاستيك
8. **Trend ADX** — تبعية التند القوي

### تحليل متقدم
- 🧠 **Smart Money Concepts (SMC)** — Order Blocks, FVG, BOS/CHoCH, Liquidity Sweeps
- 📊 **Multi-Timeframe Confluence** — تحليل M15 + M30 + H1 + H4
- 🕯️ **Candlestick Patterns** — 8 أنماط شموع يابانية
- 📈 **RSI & MACD Divergence** — كشف الانعكاسات
- 🎯 **Market Regime Detection** — trending/ranging/volatile/choppy
- 📊 **VWAP** — Volume Weighted Average Price

### إدارة المخاطر
- 📏 **Kelly Criterion** — حساب حجم الصفقة الأمثل
- 🎯 **Multi-Level TP** — 3 مستويات جني أرباح (TP1, TP2, TP3)
- 🛡️ **Break-Even** — نقطة التعادل التلقائية
- ⚖️ **R:R Ratio** — إدارة المخاطرة:العائد
- 📊 **Signal Quality Score** — تقييم جودة الإشارة (A+/A/B/C/D)

### تتبع وإدارة
- 📊 **Signal Tracking** — WIN/LOSS/EXPIRED
- 📅 **Daily/Weekly Reports** — تقارير الأداء
- 📋 **Economic Calendar** — إيقاف وقت الأخبار
- 🏷️ **Symbol Profiles** — إعدادات لكل رمز (6 رموز)
- ⏱️ **Cooldown** — منع الإشارات المتكررة
- ⚡ **Pre-Signal Alerts** — تنبيه مسبق

### أوامر Telegram
- `/status` — حالة البوت والإشارات النشطة
- `/stats` — إحصائيات الأداء
- `/backtest [symbol] [days]` — اختبار استراتيجية
- `/report [daily|weekly]` — تقرير الأداء
- `/symbols` — الرموز النشطة
- `/news [symbol]` — الأخبار القادمة
- `/help` — المساعدة
- `/stop` — إيقاف البوت

## الإعداد

1. انسخ `.env.example` إلى `.env` واملأ المفاتيح
2. `pip install -r requirements.txt`
3. `python bot/main.py`

## النشر
GitHub: https://github.com/mexc1433-crypto/bbpro-signal-bot

المنصات المدعومة: Docker, Render, Koyeb, Railway, Back4App, Termux
