"""
新闻情绪监控模块 V2 - News Sentiment Monitor
用于宏观战情室 (Macro War Room) 整合

功能:
1. 实时市场新闻流 (Finnhub API)
2. 情绪评分量化 (Bullish/Bearish/Neutral)
3. 宏观关键词触发预警 (Fed/CPI/Tariff/Geopolitical)
4. 情绪趋势可视化
5. 与Gamma环境联动预警
6. Telegram实时推送

数据源: Finnhub (免费tier - 60次/分钟)
"""

import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
import time
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, asdict
from enum import Enum
import re
import urllib.parse
import hashlib

# ============================================================================
# 配置常量
# ============================================================================

# Finnhub API Key (从环境变量读取，带默认值)
import os
FINNHUB_API_KEY = os.environ.get('FINNHUB_API_KEY') or "d732oopr01qn7f07d8lgd732oopr01qn7f07d8m0"

# Telegram配置 (从环境变量读取)
TELEGRAM_CONFIG = {
    'enabled': bool(os.environ.get('TELEGRAM_BOT_TOKEN')),
    'webhook_url': None,
    'bot_token': os.environ.get('TELEGRAM_BOT_TOKEN', ''),
    'chat_id': os.environ.get('TELEGRAM_CHAT_ID', ''),
}

class SentimentLevel(Enum):
    VERY_BEARISH = -2
    BEARISH = -1
    NEUTRAL = 0
    BULLISH = 1
    VERY_BULLISH = 2

class AlertLevel(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    EXTREME = "EXTREME"

# 监控标的列表
WATCHLIST_TICKERS = ['QQQ', 'SPY', 'NVDA', 'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'TSLA']

# 宏观关键词分类
MACRO_KEYWORDS = {
    'fed_policy': {
        'keywords': ['fed', 'fomc', 'powell', 'rate cut', 'rate hike', 'hawkish', 'dovish', 
                     'quantitative', 'tightening', 'easing', 'inflation target', 'federal reserve',
                     'fed fund', 'monetary policy', 'balance sheet'],
        'weight': 1.5,
        'category_cn': 'Fed政策',
        'emoji': '🏦'
    },
    'economic_data': {
        'keywords': ['cpi', 'ppi', 'nfp', 'jobs report', 'unemployment', 'gdp', 'retail sales',
                     'pce', 'core inflation', 'jobless claims', 'payroll', 'consumer confidence',
                     'ism', 'manufacturing', 'services pmi'],
        'weight': 1.3,
        'category_cn': '经济数据',
        'emoji': '📊'
    },
    'geopolitical': {
        'keywords': ['iran', 'china', 'russia', 'ukraine', 'taiwan', 'tariff', 'sanctions',
                     'war', 'military', 'missile', 'attack', 'tension', 'conflict', 'middle east',
                     'north korea', 'israel', 'gaza', 'strike', 'retaliation'],
        'weight': 1.8,
        'category_cn': '地缘政治',
        'emoji': '🌍'
    },
    'market_structure': {
        'keywords': ['options', 'gamma', 'vix', 'volatility', 'opex', 'expiration', 'squeeze',
                     'short squeeze', 'margin call', 'liquidation', 'hedge fund', 'dealer',
                     'zero gamma', 'call wall', 'put wall', '0dte'],
        'weight': 1.4,
        'category_cn': '市场结构',
        'emoji': '📈'
    },
    'earnings': {
        'keywords': ['earnings', 'revenue', 'guidance', 'beat', 'miss', 'outlook', 'forecast',
                     'quarterly', 'profit', 'eps', 'revenue miss', 'earnings beat'],
        'weight': 1.0,
        'category_cn': '财报',
        'emoji': '💰'
    },
    'crypto': {
        'keywords': ['bitcoin', 'btc', 'ethereum', 'crypto', 'cryptocurrency', 'coinbase',
                     'binance', 'sec crypto', 'spot etf', 'bitcoin etf'],
        'weight': 1.1,
        'category_cn': '加密货币',
        'emoji': '₿'
    }
}

# 情绪关键词（用于增强情绪判断）
SENTIMENT_KEYWORDS = {
    'bullish': ['surge', 'soar', 'rally', 'jump', 'gain', 'bullish', 'optimism', 'upbeat',
                'breakout', 'record high', 'beat', 'upgrade', 'buy', 'outperform', 'boom',
                'recovery', 'rebound', 'strong', 'positive', 'growth', 'expand'],
    'bearish': ['crash', 'plunge', 'tumble', 'drop', 'fall', 'bearish', 'pessimism', 'fear',
                'breakdown', 'record low', 'miss', 'downgrade', 'sell', 'underperform', 'bust',
                'recession', 'crisis', 'collapse', 'panic', 'risk-off', 'warning', 'concern',
                'weak', 'decline', 'slump', 'tank', 'dive']
}

# ============================================================================
# 数据类定义
# ============================================================================

@dataclass
class NewsItem:
    """新闻条目数据结构"""
    id: str
    headline: str
    summary: str
    source: str
    url: str
    datetime: datetime
    related_tickers: List[str]
    sentiment_score: float  # -1 to 1
    sentiment_label: str
    macro_categories: List[str]
    importance_score: float  # 0 to 10

@dataclass
class SentimentAlert:
    """情绪预警数据结构"""
    level: str  # 'HIGH', 'MEDIUM', 'LOW', 'EXTREME'
    message: str
    message_en: str
    trigger_reason: str
    timestamp: datetime
    related_news: List[str]
    sent_to_telegram: bool = False

# ============================================================================
# Telegram 推送模块
# ============================================================================

class TelegramNotifier:
    """Telegram通知推送"""
    
    def __init__(self, bot_token: str = None, chat_id: str = None, webhook_url: str = None):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.webhook_url = webhook_url
        self.sent_alerts = set()  # 用于去重
    
    def _get_alert_hash(self, alert: SentimentAlert) -> str:
        """生成预警的唯一hash用于去重"""
        content = f"{alert.level}_{alert.message}_{alert.timestamp.strftime('%Y%m%d%H')}"
        return hashlib.md5(content.encode()).hexdigest()[:16]
    
    def send_alert(self, alert: SentimentAlert) -> bool:
        """发送预警到Telegram"""
        
        # 检查是否已发送
        alert_hash = self._get_alert_hash(alert)
        if alert_hash in self.sent_alerts:
            return False
        
        # 构建消息
        level_emoji = {
            'EXTREME': '🔴🔴🔴',
            'HIGH': '🔴',
            'MEDIUM': '🟡',
            'LOW': '🟢'
        }
        
        message = f"""
{level_emoji.get(alert.level, '⚪')} *新闻情绪预警*

*级别:* {alert.level}
*信号:* {alert.message}
*原因:* {alert.trigger_reason}
*时间:* {alert.timestamp.strftime('%Y-%m-%d %H:%M')}
"""
        
        if alert.related_news:
            message += "\n*相关新闻:*\n"
            for news in alert.related_news[:3]:
                message += f"• {news[:60]}...\n"
        
        # 发送
        success = self._send_message(message)
        
        if success:
            self.sent_alerts.add(alert_hash)
            alert.sent_to_telegram = True
            
            # 限制缓存大小
            if len(self.sent_alerts) > 1000:
                self.sent_alerts = set(list(self.sent_alerts)[-500:])
        
        return success
    
    def _send_message(self, text: str) -> bool:
        """发送消息到Telegram"""
        
        # 方式1: 使用Cloudflare Worker webhook
        if self.webhook_url:
            try:
                response = requests.post(
                    self.webhook_url,
                    json={'message': text, 'parse_mode': 'Markdown'},
                    timeout=10
                )
                return response.status_code == 200
            except Exception as e:
                print(f"Webhook发送失败: {e}")
                return False
        
        # 方式2: 直接使用Telegram Bot API
        if self.bot_token and self.chat_id:
            try:
                url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
                response = requests.post(url, json={
                    'chat_id': self.chat_id,
                    'text': text,
                    'parse_mode': 'Markdown'
                }, timeout=10)
                return response.status_code == 200
            except Exception as e:
                print(f"Telegram API发送失败: {e}")
                return False
        
        return False
    
    def send_summary(self, summary: dict) -> bool:
        """发送每日情绪摘要"""
        if not summary:
            return False
        
        avg_sent = summary.get('avg_sentiment', 0)
        
        if avg_sent > 0.3:
            sentiment_emoji = "📈"
            sentiment_text = "偏多"
        elif avg_sent < -0.3:
            sentiment_emoji = "📉"
            sentiment_text = "偏空"
        else:
            sentiment_emoji = "➡️"
            sentiment_text = "中性"
        
        message = f"""
📰 *新闻情绪日报*

{sentiment_emoji} *整体情绪:* {sentiment_text} ({avg_sent:.2f})

📊 *24小时统计:*
• 新闻总数: {summary.get('total_news', 0)}
• 看涨: {summary.get('bullish_count', 0)}
• 看跌: {summary.get('bearish_count', 0)}
• 中性: {summary.get('neutral_count', 0)}

*时间:* {datetime.now().strftime('%Y-%m-%d %H:%M')}
"""
        return self._send_message(message)

# ============================================================================
# Finnhub API 客户端
# ============================================================================

class FinnhubClient:
    """Finnhub API 客户端封装"""
    
    BASE_URL = "https://finnhub.io/api/v1"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
        self.request_count = 0
        self.last_request_time = None
    
    def _make_request(self, endpoint: str, params: dict = None) -> dict:
        """发送API请求"""
        if params is None:
            params = {}
        params['token'] = self.api_key
        
        url = f"{self.BASE_URL}/{endpoint}"
        
        try:
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            self.request_count += 1
            self.last_request_time = datetime.now()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"API请求失败: {e}")
            return {}
    
    def get_market_news(self, category: str = 'general') -> List[dict]:
        """获取市场新闻
        category: 'general', 'forex', 'crypto', 'merger'
        """
        return self._make_request('news', {'category': category})
    
    def get_company_news(self, symbol: str, from_date: str, to_date: str) -> List[dict]:
        """获取公司新闻"""
        return self._make_request('company-news', {
            'symbol': symbol,
            'from': from_date,
            'to': to_date
        })
    
    def get_news_sentiment(self, symbol: str) -> dict:
        """获取新闻情绪评分（需要Premium，免费版可能受限）"""
        return self._make_request('news-sentiment', {'symbol': symbol})

# ============================================================================
# 情绪分析引擎
# ============================================================================

class SentimentAnalyzer:
    """新闻情绪分析引擎"""
    
    def __init__(self):
        self.bullish_keywords = set(SENTIMENT_KEYWORDS['bullish'])
        self.bearish_keywords = set(SENTIMENT_KEYWORDS['bearish'])
    
    def analyze_text(self, text: str) -> Tuple[float, str]:
        """
        分析文本情绪
        返回: (score, label)
        score: -1 (极度看跌) 到 1 (极度看涨)
        """
        text_lower = text.lower()
        
        bullish_count = sum(1 for kw in self.bullish_keywords if kw in text_lower)
        bearish_count = sum(1 for kw in self.bearish_keywords if kw in text_lower)
        
        total = bullish_count + bearish_count
        if total == 0:
            return 0.0, 'Neutral'
        
        score = (bullish_count - bearish_count) / total
        
        # 归一化到 -1 到 1
        score = max(-1, min(1, score))
        
        if score > 0.3:
            label = 'Bullish' if score <= 0.6 else 'Very Bullish'
        elif score < -0.3:
            label = 'Bearish' if score >= -0.6 else 'Very Bearish'
        else:
            label = 'Neutral'
        
        return score, label
    
    def detect_macro_categories(self, text: str) -> List[Tuple[str, str, str]]:
        """检测文本中的宏观关键词类别"""
        text_lower = text.lower()
        detected = []
        
        for category, config in MACRO_KEYWORDS.items():
            for keyword in config['keywords']:
                if keyword in text_lower:
                    detected.append((category, config['category_cn'], config['emoji']))
                    break
        
        return detected
    
    def calculate_importance(self, news_item: dict, sentiment_score: float, 
                           macro_categories: List[str]) -> float:
        """计算新闻重要性评分 (0-10)"""
        base_score = 5.0
        
        # 情绪极端性加分
        sentiment_factor = abs(sentiment_score) * 2
        
        # 宏观类别加分
        category_factor = 0
        for cat in macro_categories:
            if cat in MACRO_KEYWORDS:
                category_factor += MACRO_KEYWORDS[cat]['weight']
        
        # 来源权重
        premium_sources = ['reuters', 'bloomberg', 'wsj', 'cnbc', 'financial times', 'dow jones']
        source = news_item.get('source', '').lower()
        source_factor = 1.5 if any(s in source for s in premium_sources) else 1.0
        
        importance = min(10, base_score + sentiment_factor + category_factor) * source_factor
        return round(importance, 1)

# ============================================================================
# 新闻情绪模块主类
# ============================================================================

class NewsSentimentModule:
    """新闻情绪监控模块主类"""
    
    def __init__(self, api_key: str = FINNHUB_API_KEY, telegram_config: dict = None):
        self.client = FinnhubClient(api_key)
        self.analyzer = SentimentAnalyzer()
        self.news_cache: List[NewsItem] = []
        self.alerts: List[SentimentAlert] = []
        self.last_update = None
        
        # 初始化Telegram推送
        tg_config = telegram_config or TELEGRAM_CONFIG
        if tg_config.get('enabled'):
            self.telegram = TelegramNotifier(
                bot_token=tg_config.get('bot_token'),
                chat_id=tg_config.get('chat_id'),
                webhook_url=tg_config.get('webhook_url')
            )
        else:
            self.telegram = None
    
    def fetch_and_analyze_news(self, include_tickers: bool = True, 
                               send_alerts: bool = True) -> List[NewsItem]:
        """获取并分析新闻"""
        all_news = []
        
        # 1. 获取市场综合新闻
        market_news = self.client.get_market_news('general')
        if market_news:
            for item in market_news[:30]:
                news_item = self._process_news_item(item)
                if news_item:
                    all_news.append(news_item)
        
        # 2. 获取关注标的的公司新闻
        if include_tickers:
            today = datetime.now().strftime('%Y-%m-%d')
            week_ago = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')
            
            for ticker in WATCHLIST_TICKERS[:5]:
                company_news = self.client.get_company_news(ticker, week_ago, today)
                if company_news:
                    for item in company_news[:5]:
                        news_item = self._process_news_item(item, related_ticker=ticker)
                        if news_item:
                            all_news.append(news_item)
                time.sleep(0.1)
        
        # 去重并按时间排序
        seen_ids = set()
        unique_news = []
        for item in all_news:
            if item.id not in seen_ids:
                seen_ids.add(item.id)
                unique_news.append(item)
        
        unique_news.sort(key=lambda x: x.datetime, reverse=True)
        self.news_cache = unique_news
        self.last_update = datetime.now()
        
        # 生成预警
        self._generate_alerts()
        
        # 发送Telegram预警
        if send_alerts and self.telegram:
            for alert in self.alerts:
                if alert.level in ['HIGH', 'EXTREME'] and not alert.sent_to_telegram:
                    self.telegram.send_alert(alert)
        
        return unique_news
    
    def _process_news_item(self, raw_item: dict, related_ticker: str = None) -> Optional[NewsItem]:
        """处理单条新闻"""
        try:
            headline = raw_item.get('headline', '')
            summary = raw_item.get('summary', '')
            full_text = f"{headline} {summary}"
            
            if not headline:
                return None
            
            # 情绪分析
            score, label = self.analyzer.analyze_text(full_text)
            
            # 宏观类别检测
            categories = self.analyzer.detect_macro_categories(full_text)
            category_names = [c[0] for c in categories]
            
            # 重要性评分
            importance = self.analyzer.calculate_importance(raw_item, score, category_names)
            
            # 相关标的
            related = raw_item.get('related', '').split(',') if raw_item.get('related') else []
            if related_ticker and related_ticker not in related:
                related.append(related_ticker)
            
            # 时间处理
            timestamp = raw_item.get('datetime', 0)
            news_time = datetime.fromtimestamp(timestamp) if timestamp else datetime.now()
            
            return NewsItem(
                id=str(raw_item.get('id', hash(headline))),
                headline=headline,
                summary=summary[:500] if summary else '',
                source=raw_item.get('source', 'Unknown'),
                url=raw_item.get('url', ''),
                datetime=news_time,
                related_tickers=related,
                sentiment_score=score,
                sentiment_label=label,
                macro_categories=category_names,
                importance_score=importance
            )
        except Exception as e:
            return None
    
    def _generate_alerts(self):
        """基于新闻生成预警"""
        self.alerts = []
        
        if not self.news_cache:
            return
        
        # 计算近期新闻的聚合情绪
        recent_news = [n for n in self.news_cache 
                      if n.datetime > datetime.now() - timedelta(hours=4)]
        
        if not recent_news:
            return
        
        avg_sentiment = np.mean([n.sentiment_score for n in recent_news])
        
        # 检查地缘政治新闻
        geo_news = [n for n in recent_news if 'geopolitical' in n.macro_categories]
        if geo_news and any(n.sentiment_score < -0.3 for n in geo_news):
            self.alerts.append(SentimentAlert(
                level='HIGH',
                message='🌍 地缘政治风险升温',
                message_en='Geopolitical Risk Escalation',
                trigger_reason=f'检测到{len(geo_news)}条地缘政治相关负面新闻',
                timestamp=datetime.now(),
                related_news=[n.headline[:50] for n in geo_news[:3]]
            ))
        
        # 检查Fed相关新闻
        fed_news = [n for n in recent_news if 'fed_policy' in n.macro_categories]
        if fed_news:
            fed_sentiment = np.mean([n.sentiment_score for n in fed_news])
            if fed_sentiment < -0.2:
                self.alerts.append(SentimentAlert(
                    level='MEDIUM',
                    message='🏦 Fed政策偏鹰派信号',
                    message_en='Hawkish Fed Signal',
                    trigger_reason=f'Fed相关新闻情绪偏负面 (Score: {fed_sentiment:.2f})',
                    timestamp=datetime.now(),
                    related_news=[n.headline[:50] for n in fed_news[:3]]
                ))
            elif fed_sentiment > 0.3:
                self.alerts.append(SentimentAlert(
                    level='LOW',
                    message='🏦 Fed政策偏鸽派信号',
                    message_en='Dovish Fed Signal',
                    trigger_reason=f'Fed相关新闻情绪偏正面 (Score: {fed_sentiment:.2f})',
                    timestamp=datetime.now(),
                    related_news=[n.headline[:50] for n in fed_news[:3]]
                ))
        
        # 整体市场情绪预警
        if avg_sentiment < -0.5:
            self.alerts.append(SentimentAlert(
                level='EXTREME',
                message='🔴 市场情绪极度悲观',
                message_en='Extreme Bearish Sentiment',
                trigger_reason=f'4小时内平均情绪得分: {avg_sentiment:.2f}',
                timestamp=datetime.now(),
                related_news=[n.headline[:50] for n in recent_news if n.sentiment_score < -0.3][:3]
            ))
        elif avg_sentiment < -0.3:
            self.alerts.append(SentimentAlert(
                level='HIGH',
                message='📉 市场情绪悲观',
                message_en='Bearish Sentiment',
                trigger_reason=f'4小时内平均情绪得分: {avg_sentiment:.2f}',
                timestamp=datetime.now(),
                related_news=[]
            ))
        elif avg_sentiment < -0.15:
            self.alerts.append(SentimentAlert(
                level='MEDIUM',
                message='🟡 市场情绪偏负面',
                message_en='Slightly Bearish Sentiment',
                trigger_reason=f'4小时内平均情绪得分: {avg_sentiment:.2f}',
                timestamp=datetime.now(),
                related_news=[]
            ))
    
    def get_sentiment_summary(self) -> dict:
        """获取情绪摘要统计"""
        if not self.news_cache:
            return {}
        
        recent = [n for n in self.news_cache 
                 if n.datetime > datetime.now() - timedelta(hours=24)]
        
        if not recent:
            return {}
        
        scores = [n.sentiment_score for n in recent]
        
        return {
            'total_news': len(recent),
            'avg_sentiment': np.mean(scores),
            'sentiment_std': np.std(scores),
            'bullish_count': sum(1 for s in scores if s > 0.2),
            'bearish_count': sum(1 for s in scores if s < -0.2),
            'neutral_count': sum(1 for s in scores if -0.2 <= s <= 0.2),
            'most_bullish': max(recent, key=lambda x: x.sentiment_score) if recent else None,
            'most_bearish': min(recent, key=lambda x: x.sentiment_score) if recent else None,
            'high_importance': [n for n in recent if n.importance_score >= 7]
        }
    
    def get_category_breakdown(self) -> pd.DataFrame:
        """获取各类别新闻统计"""
        if not self.news_cache:
            return pd.DataFrame()
        
        category_stats = {}
        for category, config in MACRO_KEYWORDS.items():
            cat_news = [n for n in self.news_cache if category in n.macro_categories]
            if cat_news:
                category_stats[config['category_cn']] = {
                    'count': len(cat_news),
                    'avg_sentiment': np.mean([n.sentiment_score for n in cat_news]),
                    'emoji': config['emoji'],
                    'latest': cat_news[0].headline[:40] if cat_news else ''
                }
        
        return pd.DataFrame(category_stats).T
    
    def get_gamma_fusion_signal(self, gamma_environment: str = None) -> dict:
        """
        与Gamma环境融合生成风险信号
        
        gamma_environment: 'positive' 或 'negative'
        """
        summary = self.get_sentiment_summary()
        
        if not summary:
            return {
                'level': 'UNKNOWN',
                'message': '无情绪数据',
                'action': '请刷新数据'
            }
        
        sentiment = summary['avg_sentiment']
        has_high_alert = any(a.level in ['HIGH', 'EXTREME'] for a in self.alerts)
        has_geo_risk = any('geopolitical' in n.macro_categories 
                           for n in self.news_cache[:10] if n.sentiment_score < -0.3)
        
        if gamma_environment == 'negative':
            if sentiment < -0.3 or has_high_alert:
                return {
                    'level': 'EXTREME',
                    'message': '负Gamma + 负面情绪 = 极端风险',
                    'action': '建议清仓/重度对冲',
                    'color': '#FF1744'
                }
            elif sentiment < 0:
                return {
                    'level': 'HIGH',
                    'message': '负Gamma环境下情绪偏负',
                    'action': '减仓至50%以下',
                    'color': '#FF9800'
                }
            else:
                return {
                    'level': 'MEDIUM',
                    'message': '负Gamma但情绪尚可',
                    'action': '控制仓位,设好止损',
                    'color': '#FFD600'
                }
        else:  # positive gamma
            if sentiment < -0.4 and has_geo_risk:
                return {
                    'level': 'HIGH',
                    'message': '正Gamma但地缘风险突发',
                    'action': '观望,等待情绪消化',
                    'color': '#FF9800'
                }
            elif sentiment < -0.2:
                return {
                    'level': 'MEDIUM',
                    'message': '正Gamma但情绪偏负',
                    'action': 'Zero Gamma是好的支撑位',
                    'color': '#FFD600'
                }
            else:
                return {
                    'level': 'LOW',
                    'message': '正Gamma + 中性/正面情绪',
                    'action': '正常交易,关注Call Wall阻力',
                    'color': '#00C853'
                }

# ============================================================================
# Streamlit UI 组件
# ============================================================================

def render_sentiment_gauge(score: float, title: str = "市场情绪"):
    """渲染情绪仪表盘"""
    gauge_value = (score + 1) * 50  # -1到1 映射到 0到100
    
    if score < -0.3:
        color = "#FF1744"
        status = "看跌"
    elif score > 0.3:
        color = "#00C853"
        status = "看涨"
    else:
        color = "#FFD600"
        status = "中性"
    
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=gauge_value,
        domain={'x': [0, 1], 'y': [0, 1]},
        title={'text': f"{title}<br><span style='font-size:0.8em;color:{color}'>{status}</span>",
               'font': {'color': 'white'}},
        delta={'reference': 50, 'increasing': {'color': "#00C853"}, 'decreasing': {'color': "#FF1744"}},
        number={'font': {'color': 'white'}},
        gauge={
            'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': 'white'},
            'bar': {'color': color},
            'bgcolor': "rgba(0,0,0,0)",
            'borderwidth': 2,
            'bordercolor': "gray",
            'steps': [
                {'range': [0, 30], 'color': 'rgba(255,23,68,0.3)'},
                {'range': [30, 70], 'color': 'rgba(255,214,0,0.3)'},
                {'range': [70, 100], 'color': 'rgba(0,200,83,0.3)'}
            ],
            'threshold': {
                'line': {'color': "white", 'width': 4},
                'thickness': 0.75,
                'value': gauge_value
            }
        }
    ))
    
    fig.update_layout(
        height=250,
        margin=dict(l=20, r=20, t=50, b=20),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font={'color': 'white'}
    )
    
    return fig

def render_sentiment_timeline(news_items: List[NewsItem]) -> go.Figure:
    """渲染情绪时间线"""
    if not news_items:
        return go.Figure()
    
    df = pd.DataFrame([{
        'datetime': n.datetime,
        'sentiment': n.sentiment_score,
        'headline': n.headline[:50],
        'importance': n.importance_score
    } for n in news_items])
    
    df = df.sort_values('datetime')
    df['sentiment_ma'] = df['sentiment'].rolling(window=5, min_periods=1).mean()
    
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                       vertical_spacing=0.1,
                       row_heights=[0.7, 0.3])
    
    colors = ['#FF1744' if s < -0.2 else '#00C853' if s > 0.2 else '#FFD600' 
              for s in df['sentiment']]
    
    fig.add_trace(
        go.Scatter(
            x=df['datetime'],
            y=df['sentiment'],
            mode='markers',
            marker=dict(size=df['importance']*2, color=colors, opacity=0.6),
            text=df['headline'],
            hovertemplate='%{text}<br>情绪: %{y:.2f}<extra></extra>',
            name='新闻情绪'
        ),
        row=1, col=1
    )
    
    fig.add_trace(
        go.Scatter(
            x=df['datetime'],
            y=df['sentiment_ma'],
            mode='lines',
            line=dict(color='#00d4ff', width=2),
            name='情绪MA5'
        ),
        row=1, col=1
    )
    
    fig.add_hline(y=0, line_dash="dash", line_color="gray", row=1, col=1)
    
    df['hour'] = df['datetime'].dt.floor('H')
    hourly_counts = df.groupby('hour').size().reset_index(name='count')
    
    fig.add_trace(
        go.Bar(
            x=hourly_counts['hour'],
            y=hourly_counts['count'],
            marker_color='#4fc3f7',
            opacity=0.7,
            name='新闻数量/小时'
        ),
        row=2, col=1
    )
    
    fig.update_layout(
        height=400,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=50, r=20, t=30, b=30),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font={'color': 'white'}
    )
    
    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='rgba(255,255,255,0.1)')
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='rgba(255,255,255,0.1)')
    fig.update_yaxes(title_text="情绪得分", row=1, col=1)
    fig.update_yaxes(title_text="新闻数", row=2, col=1)
    
    return fig

def render_category_chart(category_df: pd.DataFrame) -> go.Figure:
    """渲染类别情绪柱状图"""
    if category_df.empty:
        return go.Figure()
    
    colors = ['#FF1744' if s < -0.1 else '#00C853' if s > 0.1 else '#FFD600' 
              for s in category_df['avg_sentiment']]
    
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        x=category_df.index,
        y=category_df['avg_sentiment'],
        marker_color=colors,
        text=[f"n={int(c)}" for c in category_df['count']],
        textposition='outside',
        hovertemplate='%{x}<br>情绪: %{y:.2f}<br>数量: %{text}<extra></extra>'
    ))
    
    fig.add_hline(y=0, line_dash="dash", line_color="gray")
    
    fig.update_layout(
        height=300,
        title="各类别新闻情绪",
        xaxis_title="类别",
        yaxis_title="平均情绪",
        margin=dict(l=50, r=20, t=50, b=50),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font={'color': 'white'}
    )
    
    return fig

def render_alerts_panel(alerts: List[SentimentAlert]) -> None:
    """渲染预警面板"""
    if not alerts:
        st.success("✅ 当前无预警信号")
        return
    
    for alert in alerts:
        if alert.level == 'EXTREME':
            st.error(f"**{alert.message}**\n\n{alert.trigger_reason}")
        elif alert.level == 'HIGH':
            st.warning(f"**{alert.message}**\n\n{alert.trigger_reason}")
        elif alert.level == 'MEDIUM':
            st.info(f"**{alert.message}**\n\n{alert.trigger_reason}")
        else:
            st.success(f"**{alert.message}**\n\n{alert.trigger_reason}")
        
        if alert.related_news:
            with st.expander("相关新闻"):
                for headline in alert.related_news:
                    st.markdown(f"• {headline}...")

def render_news_table(news_items: List[NewsItem], max_items: int = 20) -> None:
    """渲染新闻列表"""
    for i, news in enumerate(news_items[:max_items]):
        if news.sentiment_score > 0.2:
            sentiment_color = "🟢"
            bg_color = "rgba(0, 200, 81, 0.1)"
        elif news.sentiment_score < -0.2:
            sentiment_color = "🔴"
            bg_color = "rgba(255, 68, 68, 0.1)"
        else:
            sentiment_color = "🟡"
            bg_color = "rgba(255, 187, 51, 0.1)"
        
        importance_stars = "⭐" * min(int(news.importance_score / 2), 5)
        
        category_tags = " ".join([
            f"`{MACRO_KEYWORDS.get(c, {}).get('emoji', '')} {MACRO_KEYWORDS.get(c, {}).get('category_cn', c)}`" 
            for c in news.macro_categories[:2]
        ])
        
        with st.container():
            st.markdown(f"""
            <div style="background-color: {bg_color}; padding: 10px; border-radius: 5px; margin-bottom: 10px;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="font-size: 0.8em; color: #888;">{news.datetime.strftime('%m-%d %H:%M')} | {news.source}</span>
                    <span>{sentiment_color} {news.sentiment_score:.2f} | {importance_stars}</span>
                </div>
                <div style="font-weight: bold; margin: 5px 0;">
                    <a href="{news.url}" target="_blank" style="color: #00d4ff; text-decoration: none;">{news.headline}</a>
                </div>
                <div style="font-size: 0.9em; color: #ccc;">{news.summary[:150]}...</div>
                <div style="margin-top: 5px;">{category_tags}</div>
            </div>
            """, unsafe_allow_html=True)

# ============================================================================
# 主渲染函数 - 用于嵌入宏观战情室
# ============================================================================

def render_news_sentiment_section(gamma_environment: str = None):
    """
    新闻情绪监控板块 - 嵌入宏观战情室的主入口
    
    参数:
    - gamma_environment: 'positive' 或 'negative'，用于与Gamma环境联动
    """
    
    st.markdown('<div class="chapter-header">📰 新闻情绪监控</div>', unsafe_allow_html=True)
    st.markdown('*"市场在讨论什么? 情绪如何?"*')
    
    # 初始化模块
    if 'news_sentiment_module' not in st.session_state:
        st.session_state.news_sentiment_module = NewsSentimentModule()
    
    module = st.session_state.news_sentiment_module
    
    # 控制面板
    col1, col2, col3 = st.columns([2, 2, 1])
    
    with col1:
        auto_refresh = st.checkbox("自动刷新 (5分钟)", value=False, key="news_auto_refresh")
    
    with col2:
        include_tickers = st.checkbox("包含关注标的", value=True, key="news_include_tickers")
    
    with col3:
        if st.button("🔄 刷新", key="news_refresh_btn"):
            with st.spinner("正在获取新闻数据..."):
                module.fetch_and_analyze_news(include_tickers=include_tickers)
                st.success(f"已更新 {len(module.news_cache)} 条新闻")
    
    # 自动刷新逻辑
    if auto_refresh:
        if module.last_update is None or \
           (datetime.now() - module.last_update).seconds > 300:
            module.fetch_and_analyze_news(include_tickers=include_tickers)
    
    # 如果没有数据，提示用户刷新
    if not module.news_cache:
        st.info("👆 点击刷新按钮获取最新新闻数据")
        return
    
    # ===== 预警面板 =====
    if module.alerts:
        st.markdown("### 🚨 实时预警")
        render_alerts_panel(module.alerts)
        st.markdown("---")
    
    # ===== 核心指标 =====
    summary = module.get_sentiment_summary()
    
    if summary:
        cols = st.columns(5)
        
        with cols[0]:
            avg_sent = summary['avg_sentiment']
            delta_display = "📈 偏多" if avg_sent > 0.1 else "📉 偏空" if avg_sent < -0.1 else "➡️ 中性"
            st.metric("24h情绪", f"{avg_sent:.2f}", delta_display)
        
        with cols[1]:
            st.metric("新闻总数", summary['total_news'])
        
        with cols[2]:
            st.metric("🟢 看涨", summary['bullish_count'])
        
        with cols[3]:
            st.metric("🔴 看跌", summary['bearish_count'])
        
        with cols[4]:
            # Gamma融合信号
            if gamma_environment:
                fusion = module.get_gamma_fusion_signal(gamma_environment)
                st.metric("综合风险", fusion['level'], 
                         help=f"{fusion['message']}\n建议: {fusion['action']}")
            else:
                st.metric("⚪ 中性", summary['neutral_count'])
    
    # ===== 可视化 =====
    col_left, col_right = st.columns(2)
    
    with col_left:
        if summary:
            gauge_fig = render_sentiment_gauge(summary['avg_sentiment'], "24小时市场情绪")
            st.plotly_chart(gauge_fig, use_container_width=True)
    
    with col_right:
        category_df = module.get_category_breakdown()
        if not category_df.empty:
            cat_fig = render_category_chart(category_df)
            st.plotly_chart(cat_fig, use_container_width=True)
    
    # ===== 时间线图 =====
    with st.expander("📈 情绪时间线", expanded=False):
        timeline_fig = render_sentiment_timeline(module.news_cache)
        st.plotly_chart(timeline_fig, use_container_width=True)
    
    # ===== 新闻列表 =====
    with st.expander("📋 最新新闻", expanded=False):
        col1, col2 = st.columns(2)
        
        with col1:
            sentiment_filter = st.selectbox(
                "情绪筛选",
                ["全部", "看涨 (>0.2)", "看跌 (<-0.2)", "中性"],
                key="news_sentiment_filter"
            )
        
        with col2:
            category_filter = st.selectbox(
                "类别筛选", 
                ["全部"] + [v['category_cn'] for v in MACRO_KEYWORDS.values()],
                key="news_category_filter"
            )
        
        filtered_news = module.news_cache.copy()
        
        if sentiment_filter == "看涨 (>0.2)":
            filtered_news = [n for n in filtered_news if n.sentiment_score > 0.2]
        elif sentiment_filter == "看跌 (<-0.2)":
            filtered_news = [n for n in filtered_news if n.sentiment_score < -0.2]
        elif sentiment_filter == "中性":
            filtered_news = [n for n in filtered_news if -0.2 <= n.sentiment_score <= 0.2]
        
        if category_filter != "全部":
            cat_key = [k for k, v in MACRO_KEYWORDS.items() if v['category_cn'] == category_filter]
            if cat_key:
                filtered_news = [n for n in filtered_news if cat_key[0] in n.macro_categories]
        
        st.markdown(f"*显示 {len(filtered_news)} 条新闻*")
        render_news_table(filtered_news)
    
    # 底部信息
    st.caption(f"最后更新: {module.last_update.strftime('%Y-%m-%d %H:%M:%S') if module.last_update else 'N/A'} | "
               f"API调用: {module.client.request_count} | Finnhub")


def get_news_sentiment_for_prompt(module: NewsSentimentModule = None) -> str:
    """
    生成新闻情绪摘要供Claude Prompt使用（简要版）
    """
    if module is None:
        if 'news_sentiment_module' not in st.session_state:
            return ""
        module = st.session_state.news_sentiment_module
    
    if not module.news_cache:
        return ""
    
    summary = module.get_sentiment_summary()
    if not summary:
        return ""
    
    avg_sent = summary['avg_sentiment']
    
    if avg_sent > 0.3:
        sentiment_desc = "偏多 (Bullish)"
    elif avg_sent < -0.3:
        sentiment_desc = "偏空 (Bearish)"
    else:
        sentiment_desc = "中性 (Neutral)"
    
    # 高重要性新闻
    important_news = summary.get('high_importance', [])[:3]
    news_lines = ""
    for n in important_news:
        news_lines += f"  - [{n.sentiment_label}] {n.headline[:60]}...\n"
    
    # 预警
    alerts_text = ""
    if module.alerts:
        for alert in module.alerts[:2]:
            alerts_text += f"  - [{alert.level}] {alert.message}\n"
    
    prompt_section = f"""
## 📰 新闻情绪分析

**整体情绪:** {sentiment_desc} (Score: {avg_sent:.2f})
**24h新闻数:** {summary['total_news']} (看涨: {summary['bullish_count']}, 看跌: {summary['bearish_count']})

**重要新闻:**
{news_lines if news_lines else "  - 无高重要性新闻"}

**预警信号:**
{alerts_text if alerts_text else "  - 无预警"}
"""
    return prompt_section


def generate_claude_news_analysis_prompt(module: NewsSentimentModule = None, 
                                         gamma_environment: str = None,
                                         include_full_headlines: bool = True,
                                         max_headlines: int = 30) -> str:
    """
    生成完整的Claude新闻分析Prompt
    包含所有headlines，让Claude进行深度情绪分析
    
    参数:
    - module: NewsSentimentModule实例
    - gamma_environment: 'positive' 或 'negative'
    - include_full_headlines: 是否包含完整headline列表
    - max_headlines: 最多包含多少条headlines
    
    返回:
    - 完整的Claude分析Prompt字符串
    """
    if module is None:
        if 'news_sentiment_module' not in st.session_state:
            return "请先刷新新闻数据"
        module = st.session_state.news_sentiment_module
    
    if not module.news_cache:
        return "请先刷新新闻数据"
    
    # 获取统计数据
    summary = module.get_sentiment_summary()
    category_df = module.get_category_breakdown()
    
    # 当前时间
    now = datetime.now()
    
    # ===== 构建Prompt =====
    
    prompt = f"""# 📰 新闻情绪深度分析请求

**分析时间:** {now.strftime('%Y-%m-%d %H:%M')} EST
**数据来源:** Finnhub API
**新闻数量:** {len(module.news_cache)} 条

---

## 📊 基础统计 (机器预处理)

| 指标 | 数值 |
|------|------|
| 24h新闻总数 | {summary.get('total_news', 0)} |
| 机器判定看涨 | {summary.get('bullish_count', 0)} |
| 机器判定看跌 | {summary.get('bearish_count', 0)} |
| 机器判定中性 | {summary.get('neutral_count', 0)} |
| 机器平均得分 | {summary.get('avg_sentiment', 0):.3f} (-1到1) |

**注意:** 以上机器得分基于简单关键词匹配，准确度有限，请以你的分析为准。

---

## 🏷️ 类别分布

"""
    
    # 添加类别统计
    if not category_df.empty:
        for cat_name, row in category_df.iterrows():
            emoji = row.get('emoji', '📌')
            count = int(row.get('count', 0))
            avg_sent = row.get('avg_sentiment', 0)
            prompt += f"- **{emoji} {cat_name}**: {count}条, 机器情绪={avg_sent:.2f}\n"
    else:
        prompt += "- 无明显类别集中\n"
    
    # 添加Gamma环境上下文
    if gamma_environment:
        prompt += f"""
---

## 🎯 当前市场环境

**Gamma环境:** {'正Gamma (Positive)' if gamma_environment == 'positive' else '负Gamma (Negative)'}

{'- 正Gamma = 做市商倾向于均值回归对冲，波动受抑制' if gamma_environment == 'positive' else '- 负Gamma = 做市商顺势对冲，波动放大'}
{'- Zero Gamma和Put Wall是关键支撑位' if gamma_environment == 'positive' else '- 突破关键位后可能加速运动'}
"""
    
    # 添加预警
    if module.alerts:
        prompt += """
---

## 🚨 机器预警 (仅供参考)

"""
        for alert in module.alerts:
            level_emoji = {'EXTREME': '🔴🔴', 'HIGH': '🔴', 'MEDIUM': '🟡', 'LOW': '🟢'}.get(alert.level, '⚪')
            prompt += f"- {level_emoji} **{alert.message}**: {alert.trigger_reason}\n"
    
    # 添加完整headlines
    if include_full_headlines:
        prompt += f"""
---

## 📋 完整新闻Headlines (请分析)

以下是最近{min(max_headlines, len(module.news_cache))}条新闻的完整headline，请你：

1. **重新判断每条新闻的真实情绪** (看涨/看跌/中性)
2. **识别市场主要关注点** (Fed? 地缘? 财报? 其他?)
3. **评估整体市场情绪** 
4. **给出对QQQ/SPY短期走势的影响判断**
5. **结合Gamma环境给出交易建议**

---

"""
        # 按时间排序，最新的在前
        sorted_news = sorted(module.news_cache, key=lambda x: x.datetime, reverse=True)
        
        for i, news in enumerate(sorted_news[:max_headlines], 1):
            time_str = news.datetime.strftime('%m-%d %H:%M')
            categories = ', '.join([MACRO_KEYWORDS.get(c, {}).get('category_cn', c) for c in news.macro_categories[:2]])
            cat_display = f" [{categories}]" if categories else ""
            
            prompt += f"{i}. **[{time_str}]** {news.headline}{cat_display}\n"
            
            # 如果有摘要且不太长，也包含
            if news.summary and len(news.summary) > 20:
                summary_short = news.summary[:150] + "..." if len(news.summary) > 150 else news.summary
                prompt += f"   _{summary_short}_\n"
            prompt += "\n"
    
    # 添加分析指引
    prompt += """
---

## 🤖 请你分析

请基于以上新闻headlines进行深度分析，回答以下问题：

### 1. 情绪判断
- 整体市场情绪是什么？(强烈看涨/看涨/中性/看跌/强烈看跌)
- 与机器判断有何差异？为什么？

### 2. 主题识别
- 市场当前最关注什么话题？
- 有哪些潜在风险被新闻提及？
- 有哪些利好信号？

### 3. 关键新闻
- 哪3-5条新闻最重要？为什么？
- 有没有新闻被误判情绪的？

### 4. 交易影响
- 这些新闻对今日QQQ/SPY走势有何影响？
- 结合当前Gamma环境，有什么交易建议？

### 5. 风险提示
- 需要特别关注哪些风险？
- 有没有"灰犀牛"或"黑天鹅"信号？

---
*请用中文回答，保持简洁但有洞察力*
"""
    
    return prompt


def render_claude_analysis_button(module: NewsSentimentModule = None, 
                                  gamma_environment: str = None):
    """
    渲染"复制到Claude分析"按钮
    """
    if module is None:
        if 'news_sentiment_module' not in st.session_state:
            return
        module = st.session_state.news_sentiment_module
    
    if not module.news_cache:
        return
    
    st.markdown("### 🤖 Claude深度分析")
    st.markdown("点击下方按钮生成完整分析Prompt，复制后发送给Claude进行深度情绪分析：")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        max_news = st.slider("包含新闻数量", min_value=10, max_value=50, value=25, key="claude_news_count")
    
    with col2:
        include_summary = st.checkbox("包含新闻摘要", value=True, key="claude_include_summary")
    
    # 生成Prompt
    prompt = generate_claude_news_analysis_prompt(
        module=module,
        gamma_environment=gamma_environment,
        include_full_headlines=True,
        max_headlines=max_news
    )
    
    with st.expander("📋 查看/复制完整Prompt", expanded=False):
        st.code(prompt, language="markdown")
        st.caption(f"Prompt长度: {len(prompt)} 字符 | 约 {len(prompt)//4} tokens")
    
    # 快速摘要版本
    st.markdown("**📊 快速摘要 (精简版):**")
    
    summary = module.get_sentiment_summary()
    if summary:
        top_headlines = sorted(module.news_cache, key=lambda x: x.importance_score, reverse=True)[:5]
        quick_summary = f"""📰 新闻情绪快报 | {datetime.now().strftime('%m-%d %H:%M')}
情绪: {summary['avg_sentiment']:.2f} | 看涨{summary['bullish_count']} 看跌{summary['bearish_count']}
{'Gamma: ' + gamma_environment if gamma_environment else ''}

重要新闻:
"""
        for i, news in enumerate(top_headlines, 1):
            quick_summary += f"{i}. {news.headline[:60]}...\n"
        
        st.code(quick_summary, language="text")


# ============================================================================
# 模块可独立运行测试
# ============================================================================

if __name__ == "__main__":
    st.set_page_config(
        page_title="新闻情绪监控",
        page_icon="📰",
        layout="wide"
    )
    
    st.markdown("""
    <style>
    .stApp { background-color: #1a1a2e; }
    .chapter-header {
        font-size: 1.5rem;
        font-weight: bold;
        color: #00d4ff;
        border-bottom: 2px solid #00d4ff;
        padding-bottom: 0.5rem;
        margin: 1.5rem 0 1rem 0;
    }
    </style>
    """, unsafe_allow_html=True)
    
    st.title("📰 新闻情绪监控模块测试")
    
    # Telegram配置
    with st.sidebar:
        st.markdown("### ⚙️ 配置")
        st.text_input("Finnhub API Key", value=FINNHUB_API_KEY[:20]+"...", disabled=True)
        
        st.markdown("---")
        st.markdown("### 📱 Telegram推送")
        tg_enabled = st.checkbox("启用Telegram推送", value=False)
        
        if tg_enabled:
            tg_token = st.text_input("Bot Token", type="password")
            tg_chat = st.text_input("Chat ID")
            
            if tg_token and tg_chat:
                TELEGRAM_CONFIG['bot_token'] = tg_token
                TELEGRAM_CONFIG['chat_id'] = tg_chat
                TELEGRAM_CONFIG['enabled'] = True
    
    render_news_sentiment_section(gamma_environment='positive')
