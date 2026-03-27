"""
新闻情绪预警 - 后台监控脚本
News Sentiment Alert - Background Monitor

功能：
- 每15分钟获取最新新闻
- 分析情绪和关键词
- 推送重要新闻headlines (Fed/地缘/MAG7/宏观数据)
- 有HIGH/EXTREME预警时特别提醒

部署方式：
1. GitHub Actions: 每15分钟自动运行

作者: Alex's Trading System
"""

import requests
import time
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass
import json
import os

# ============================================================================
# 配置 - 从环境变量读取（GitHub Secrets）
# ============================================================================

FINNHUB_API_KEY = os.environ.get('FINNHUB_API_KEY', '')
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')

# 刷新间隔（秒）
REFRESH_INTERVAL = 300  # 5分钟

# 是否推送每日摘要
SEND_DAILY_SUMMARY = True
DAILY_SUMMARY_HOUR = 8  # 早上8点发送

# ============================================================================
# 关键词配置
# ============================================================================

MACRO_KEYWORDS = {
    'fed_policy': {
        'keywords': ['fed', 'fomc', 'powell', 'rate cut', 'rate hike', 'hawkish', 'dovish', 
                     'federal reserve', 'monetary policy', 'quantitative', 'tightening', 'easing'],
        'weight': 1.5,
        'emoji': '🏦',
        'always_push': True
    },
    'economic_data': {
        'keywords': ['cpi', 'ppi', 'nfp', 'jobs report', 'unemployment', 'gdp', 'retail sales',
                     'pce', 'inflation', 'jobless claims', 'payroll', 'consumer confidence', 
                     'ism', 'manufacturing pmi', 'services pmi'],
        'weight': 1.3,
        'emoji': '📊',
        'always_push': True
    },
    'geopolitical': {
        'keywords': ['iran', 'china trade', 'russia', 'ukraine', 'taiwan', 'tariff', 'sanctions',
                     'war', 'military', 'missile', 'attack', 'tension', 'israel', 'gaza', 
                     'north korea', 'strike', 'retaliation', 'conflict'],
        'weight': 1.8,
        'emoji': '🌍',
        'always_push': True
    },
    'market_structure': {
        'keywords': ['vix', 'volatility', 'squeeze', 'margin call', 'liquidation', 
                     'options', 'gamma', 'expiration', '0dte'],
        'weight': 1.4,
        'emoji': '📈',
        'always_push': False
    },
    'mag7': {
        'keywords': ['nvidia', 'nvda', 'apple', 'aapl', 'microsoft', 'msft', 'google', 'googl', 
                     'alphabet', 'amazon', 'amzn', 'meta', 'facebook', 'tesla', 'tsla'],
        'weight': 1.3,
        'emoji': '🏢',
        'always_push': True
    },
    'major_market': {
        'keywords': ['s&p 500', 'sp500', 'nasdaq', 'dow jones', 'russell', 'qqq', 'spy',
                     'treasury', 'bond yield', '10-year', 'yield curve', 'inversion',
                     'bull market', 'bear market', 'correction', 'crash', 'rally'],
        'weight': 1.2,
        'emoji': '📉',
        'always_push': True
    },
}

SENTIMENT_KEYWORDS = {
    'bullish': ['surge', 'soar', 'rally', 'jump', 'gain', 'bullish', 'beat', 'upgrade',
                'recovery', 'rebound', 'strong', 'growth'],
    'bearish': ['crash', 'plunge', 'tumble', 'drop', 'fall', 'bearish', 'miss', 'downgrade',
                'recession', 'crisis', 'collapse', 'panic', 'fear', 'weak', 'decline']
}

# ============================================================================
# 数据结构
# ============================================================================

@dataclass
class NewsItem:
    id: str
    headline: str
    source: str
    datetime: datetime
    sentiment_score: float
    categories: List[str]
    importance: float

@dataclass
class Alert:
    level: str  # HIGH, EXTREME
    message: str
    reason: str
    news: List[str]

# ============================================================================
# 核心功能
# ============================================================================

class NewsAlertBot:
    def __init__(self):
        self.sent_alerts = set()
        self.last_summary_date = None
        
    def fetch_news(self) -> List[dict]:
        """获取Finnhub新闻"""
        url = "https://finnhub.io/api/v1/news"
        params = {'category': 'general', 'token': FINNHUB_API_KEY}
        
        for attempt in range(3):
            try:
                response = requests.get(url, params=params, timeout=30)
                response.raise_for_status()
                return response.json()[:30]
            except Exception as e:
                print(f"[WARN] 获取新闻失败 (尝试 {attempt+1}/3): {e}")
                if attempt < 2:
                    time.sleep(5)
        
        return []
    
    def analyze_sentiment(self, text: str) -> float:
        """简单情绪分析"""
        text_lower = text.lower()
        
        bullish = sum(1 for kw in SENTIMENT_KEYWORDS['bullish'] if kw in text_lower)
        bearish = sum(1 for kw in SENTIMENT_KEYWORDS['bearish'] if kw in text_lower)
        
        total = bullish + bearish
        if total == 0:
            return 0.0
        
        return (bullish - bearish) / total
    
    def detect_categories(self, text: str) -> List[str]:
        """检测宏观类别"""
        text_lower = text.lower()
        detected = []
        
        for cat, config in MACRO_KEYWORDS.items():
            if any(kw in text_lower for kw in config['keywords']):
                detected.append(cat)
        
        return detected
    
    def process_news(self, raw_news: List[dict]) -> List[NewsItem]:
        """处理新闻列表"""
        items = []
        
        for news in raw_news:
            headline = news.get('headline', '')
            if not headline:
                continue
            
            sentiment = self.analyze_sentiment(headline)
            categories = self.detect_categories(headline)
            
            importance = 5.0 + abs(sentiment) * 2
            for cat in categories:
                importance += MACRO_KEYWORDS.get(cat, {}).get('weight', 0)
            
            items.append(NewsItem(
                id=str(news.get('id', hash(headline))),
                headline=headline,
                source=news.get('source', 'Unknown'),
                datetime=datetime.fromtimestamp(news.get('datetime', 0)),
                sentiment_score=sentiment,
                categories=categories,
                importance=min(10, importance)
            ))
        
        return items
    
    def generate_alerts(self, news_items: List[NewsItem]) -> List[Alert]:
        """生成预警"""
        alerts = []
        
        if not news_items:
            return alerts
        
        recent = [n for n in news_items 
                  if n.datetime > datetime.now() - timedelta(hours=4)]
        
        if not recent:
            return alerts
        
        avg_sentiment = sum(n.sentiment_score for n in recent) / len(recent)
        
        # 地缘政治预警
        geo_news = [n for n in recent if 'geopolitical' in n.categories and n.sentiment_score < -0.2]
        if len(geo_news) >= 2:
            alerts.append(Alert(
                level='HIGH',
                message='🌍 地缘政治风险升温',
                reason=f'{len(geo_news)}条负面地缘新闻',
                news=[n.headline[:50] for n in geo_news[:3]]
            ))
        
        # 整体情绪预警
        if avg_sentiment < -0.5:
            alerts.append(Alert(
                level='EXTREME',
                message='🔴🔴 市场情绪极度悲观',
                reason=f'4小时平均情绪: {avg_sentiment:.2f}',
                news=[n.headline[:50] for n in recent if n.sentiment_score < -0.3][:3]
            ))
        elif avg_sentiment < -0.3:
            alerts.append(Alert(
                level='HIGH',
                message='🔴 市场情绪悲观',
                reason=f'4小时平均情绪: {avg_sentiment:.2f}',
                news=[]
            ))
        
        # Fed鹰派预警
        fed_news = [n for n in recent if 'fed_policy' in n.categories]
        if fed_news:
            fed_sentiment = sum(n.sentiment_score for n in fed_news) / len(fed_news)
            if fed_sentiment < -0.3:
                alerts.append(Alert(
                    level='HIGH',
                    message='🏦 Fed政策偏鹰信号',
                    reason=f'Fed相关新闻情绪: {fed_sentiment:.2f}',
                    news=[n.headline[:50] for n in fed_news[:2]]
                ))
        
        return alerts
    
    def send_telegram(self, message: str) -> bool:
        """发送Telegram消息"""
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        
        try:
            response = requests.post(url, json={
                'chat_id': TELEGRAM_CHAT_ID,
                'text': message,
                'parse_mode': 'Markdown'
            }, timeout=10)
            return response.status_code == 200
        except Exception as e:
            print(f"[ERROR] Telegram发送失败: {e}")
            return False
    
    def get_alert_hash(self, alert: Alert) -> str:
        """生成预警hash用于去重"""
        content = f"{alert.level}_{alert.message}_{datetime.now().strftime('%Y%m%d%H')}"
        return hashlib.md5(content.encode()).hexdigest()[:16]

    def run_once(self):
        """执行一次检查"""
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 检查新闻...")
        
        # 获取新闻
        raw_news = self.fetch_news()
        if not raw_news:
            print("[WARN] 未获取到新闻")
            return
        
        # 处理新闻
        news_items = self.process_news(raw_news)
        print(f"[INFO] 处理了 {len(news_items)} 条新闻")
        
        # 生成预警
        alerts = self.generate_alerts(news_items)
        
        # 计算情绪
        recent = [n for n in news_items if n.datetime > datetime.now() - timedelta(hours=4)]
        avg_sent = sum(n.sentiment_score for n in recent) / len(recent) if recent else 0
        
        # 筛选重要新闻（Fed/地缘/MAG7/宏观数据）
        important_news = []
        for n in recent:
            for cat in n.categories:
                if MACRO_KEYWORDS.get(cat, {}).get('always_push', False):
                    important_news.append(n)
                    break
        
        # 去重
        seen_headlines = set()
        unique_important = []
        for n in important_news:
            if n.headline not in seen_headlines:
                seen_headlines.add(n.headline)
                unique_important.append(n)
        
        # 构建情绪描述
        if avg_sent > 0.2:
            emoji = "📈"
            mood = "偏多"
        elif avg_sent < -0.2:
            emoji = "📉"
            mood = "偏空"
        else:
            emoji = "➡️"
            mood = "中性"
        
        # 构建重要新闻部分
        important_section = ""
        if unique_important:
            important_section = "\n*📌 重要新闻:*\n"
            for n in unique_important[:8]:
                cat_emojis = [MACRO_KEYWORDS.get(c, {}).get('emoji', '') for c in n.categories if MACRO_KEYWORDS.get(c, {}).get('always_push', False)]
                cat_str = ''.join(cat_emojis[:2])
                sent_emoji = "🟢" if n.sentiment_score > 0.2 else "🔴" if n.sentiment_score < -0.2 else "🟡"
                important_section += f"{cat_str}{sent_emoji} {n.headline[:55]}...\n"
        
        # 检查是否有HIGH/EXTREME预警
        high_alerts = [a for a in alerts if a.level in ['HIGH', 'EXTREME']]
        
        if high_alerts:
            # 有预警：发送预警+重要新闻
            alert = high_alerts[0]  # 取最重要的一个
            message = f"""🚨 *新闻情绪预警*

*级别:* {alert.level}
*信号:* {alert.message}
*原因:* {alert.reason}

{emoji} 情绪: {mood} ({avg_sent:.2f})
📊 新闻: {len(recent)}条 | 重要: {len(unique_important)}条
⏰ {datetime.now().strftime('%H:%M')} UTC
{important_section if important_section else ''}"""
            
            self.send_telegram(message)
            print(f"[ALERT] 已发送预警+新闻")
        else:
            # 无预警：发送摘要+重要新闻
            message = f"""📰 *新闻情绪快报*

{emoji} 情绪: {mood} ({avg_sent:.2f})
📊 新闻: {len(recent)}条 | 重要: {len(unique_important)}条
⏰ {datetime.now().strftime('%H:%M')} UTC
{important_section if important_section else '_无重要宏观新闻_'}"""
            
            self.send_telegram(message)
            print(f"[INFO] 已发送摘要，包含 {len(unique_important)} 条重要新闻")

    def run_forever(self):
        """持续运行"""
        print("=" * 50)
        print("📰 新闻情绪预警机器人启动")
        print(f"⏰ 刷新间隔: {REFRESH_INTERVAL}秒")
        print(f"📱 Telegram: {TELEGRAM_CHAT_ID}")
        print("=" * 50)
        
        self.send_telegram("🤖 *新闻预警机器人已启动*\n\n每15分钟检查一次，有重要新闻会推送。")
        
        while True:
            try:
                self.run_once()
            except Exception as e:
                print(f"[ERROR] {e}")
            
            time.sleep(REFRESH_INTERVAL)


# ============================================================================
# 入口
# ============================================================================

if __name__ == "__main__":
    bot = NewsAlertBot()
    
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '--once':
        bot.run_once()
    else:
        bot.run_forever()
