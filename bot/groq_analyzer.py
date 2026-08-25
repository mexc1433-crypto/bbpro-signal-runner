"""
Groq AI Market Analyzer — Intelligent signal analysis for BBPro Signal Bot

Uses Groq's fast inference (Llama 3.3 70B) to:
- Analyze confluence signals from multiple indicators
- Score trade setups with AI confidence
- Provide natural-language market commentary

NOTE: This module uses synchronous Groq calls. The caller (main.py) wraps
calls in asyncio.to_thread() to avoid blocking the event loop.
"""

from __future__ import annotations
import os, logging, json
from typing import Dict, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class AIAnalysis:
    confidence: int
    verdict: str
    reasoning: str
    risk_note: str
    suggestion: str


class GroqAnalyzer:
    def __init__(self, api_key: str = ""):
        self.api_key = api_key or os.environ.get("GROQ_API_KEY", "")
        self.client = None
        if self.api_key:
            try:
                from groq import Groq
                self.client = Groq(api_key=self.api_key)
                logger.info("🤖 Groq AI analyzer initialized (Llama 3.3 70B)")
            except Exception as e:
                logger.warning("Groq init failed: %s", e)
        else:
            logger.info("Groq AI: no API key set — analysis disabled")

    @property
    def enabled(self) -> bool:
        return self.client is not None

    def analyze_signal(
        self,
        symbol: str,
        direction: str,
        confluence_score: int,
        indicators: Dict,
        atr: float = 0.0,
        adx: float = 0.0,
        spread_pips: float = 0.0,
    ) -> Optional[AIAnalysis]:
        if not self.enabled:
            return None

        prompt = f"""You are an expert forex/gold trading analyst. Analyze this trade setup:

Symbol: {symbol}
Direction: {direction.upper()}
Confluence Score: {confluence_score}/100
Indicators: {json.dumps(indicators, indent=2)}
ATR: {atr}
ADX: {adx} (trend strength)
Spread: {spread_pips} pips

Provide a concise analysis in this EXACT JSON format:
{{
  "confidence": <0-100 integer>,
  "verdict": "<BUY|SELL|WAIT>",
  "reasoning": "<2-3 sentences explaining the analysis>",
  "risk_note": "<1 sentence about key risk>",
  "suggestion": "<1 actionable sentence>"
}}

Rules:
- If confluence < 60, recommend WAIT
- If ADX < 20, note weak trend
- If spread > 3 pips, note high spread risk
- Be conservative — better to WAIT than force a bad trade
- Keep it SHORT and DIRECT"""

        try:
            response = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": "You are a professional trading analyst. Respond ONLY with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=300,
            )
            text = response.choices[0].message.content.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text
                text = text.rsplit("```", 1)[0] if "```" in text else text
            data = json.loads(text)
            return AIAnalysis(
                confidence=int(data.get("confidence", 50)),
                verdict=data.get("verdict", "WAIT"),
                reasoning=data.get("reasoning", ""),
                risk_note=data.get("risk_note", ""),
                suggestion=data.get("suggestion", ""),
            )
        except json.JSONDecodeError:
            logger.warning("Groq returned non-JSON response")
            return None
        except Exception as e:
            logger.warning("Groq analysis failed: %s", e)
            return None

    def daily_summary(
        self,
        total_trades: int,
        wins: int,
        losses: int,
        total_pnl: float,
        win_rate: float,
        best_trade: str,
        worst_trade: str,
        market_session: str = "London/NY",
    ) -> str:
        if not self.enabled:
            return ""

        prompt = f"""Write a concise daily trading summary in Arabic:

Stats:
- Total Signals: {total_trades}
- Win Rate: {win_rate:.1f}%
- Total PnL: {total_pnl:+.2f}
- Best: {best_trade}
- Worst: {worst_trade}
- Session: {market_session}

Format: 3-4 short paragraphs in Arabic. Be honest. End with one suggestion for tomorrow."""

        try:
            response = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": "You are a professional trading analyst. Be concise and honest. Write in Arabic."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5,
                max_tokens=400,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.warning("Groq daily summary failed: %s", e)
            return ""
