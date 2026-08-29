"""
صياد الشمعات | Candle Hunter - Chart Generator
توليد صورة مخطط التحليل للإشارات القوية
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd
import numpy as np
import logging
import os
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# ألوان الهوية
BG_COLOR = '#0a0e1a'
TEXT_COLOR = '#e0e0e0'
GREEN = '#00d4aa'
RED = '#ff4444'
GOLD = '#ffd700'
GRID = '#1a1e2e'

plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['axes.facecolor'] = BG_COLOR
plt.rcParams['figure.facecolor'] = BG_COLOR


def generate_signal_chart(
    df: pd.DataFrame,
    signal: Dict,
    output_path: str = "signal_chart.png"
) -> Optional[str]:
    """
    يولّد صورة مخطط الشموع مع خطوط الدخول والـ TP والـ SL
    """
    try:
        entry = signal.get("entry_price", 0)
        tp1 = signal.get("take_profit_1", 0)
        tp2 = signal.get("take_profit_2", 0)
        tp3 = signal.get("take_profit_3", 0)
        sl = signal.get("stop_loss", 0)
        signal_type = signal.get("signal_type", "BUY")
        confidence = signal.get("confidence", 0)

        if entry <= 0 or len(df) < 20:
            logger.warning("Not enough data for chart")
            return None

        # آخر 60 شمعة
        df = df.tail(60).copy()

        # ضبط المحور
        all_prices = [entry, tp1, tp2, tp3, sl]
        df_min = df['Low'].min()
        df_max = df['High'].max()
        chart_min = min(df_min, min(all_prices)) * 0.998
        chart_max = max(df_max, max(all_prices)) * 1.002

        # إنشاء المخطط
        fig, axes = mpf.plot(
            df,
            type='candle',
            style='charles',
            volume=False,
            figsize=(12, 7),
            returnfig=True,
            scale_padding=1.2,
        )

        ax = axes[0]
        ax.set_facecolor(BG_COLOR)
        fig.set_facecolor(BG_COLOR)

        # خط الدخول
        ax.axhline(y=entry, color=GOLD, linestyle='-', linewidth=1.5, alpha=0.9)
        ax.fill_between(range(len(df)), entry, df['Close'].values, alpha=0.05, color=GOLD)
        ax.text(len(df) + 1, entry, f'  Entry: {entry:,.2f}', color=GOLD, fontsize=9, va='center', fontweight='bold')

        # خطوط TP
        for tp, label in [(tp1, f'TP1: {tp1:,.2f}'), (tp2, f'TP2: {tp2:,.2f}'), (tp3, f'TP3: {tp3:,.2f}')]:
            if tp > 0:
                ax.axhline(y=tp, color=GREEN, linestyle='--', linewidth=1, alpha=0.7)
                ax.text(len(df) + 1, tp, f'  {label}', color=GREEN, fontsize=8, va='center')

        # خط SL
        if sl > 0:
            ax.axhline(y=sl, color=RED, linestyle='--', linewidth=1, alpha=0.7)
            ax.text(len(df) + 1, sl, f'  SL: {sl:,.2f}', color=RED, fontsize=8, va='center')

        # مناطق الربح والخسارة
        if tp1 > 0:
            ax.fill_between(range(len(df)), entry, tp1, alpha=0.06, color=GREEN)
        if sl > 0:
            ax.fill_between(range(len(df)), entry, sl, alpha=0.06, color=RED)

        # العنوان
        direction_emoji = "BUY" if signal_type == "BUY" else "SELL"
        title = f'  {direction_emoji} | XAU/USD'
        if confidence > 0:
            title += f'  |  Confidence: {confidence}%'
        ax.set_title(title, color=TEXT_COLOR, fontsize=14, fontweight='bold', pad=15, loc='left')

        # تنسيق المحاور
        ax.tick_params(axis='x', colors=TEXT_COLOR, labelsize=8)
        ax.tick_params(axis='y', colors=TEXT_COLOR, labelsize=9)
        ax.spines['bottom'].set_color(GRID)
        ax.spines['top'].set_color(GRID)
        ax.spines['left'].set_color(GRID)
        ax.spines['right'].set_color(GRID)
        ax.grid(True, alpha=0.15, color=GRID)
        ax.set_ylim(chart_min, chart_max)

        # تذييل
        timeframe = signal.get("timeframe", "")
        footer = f'{timeframe}  |  {signal.get("timestamp", "")}'
        fig.text(0.02, 0.01, 'Candle Hunter', color=TEXT_COLOR, fontsize=8, alpha=0.6)
        fig.text(0.98, 0.01, footer, color=TEXT_COLOR, fontsize=8, alpha=0.6, ha='right')

        plt.tight_layout()
        plt.subplots_adjust(right=0.88)

        fig.savefig(output_path, dpi=150, facecolor=BG_COLOR, bbox_inches='tight')
        plt.close(fig)

        logger.info(f"Chart generated: {output_path}")
        return output_path

    except Exception as e:
        logger.error(f"Chart generation failed: {e}")
        return None
