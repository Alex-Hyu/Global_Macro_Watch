"""
黄金宏观预警模块 - Gold Macro Alert System
用于监控US10Y、DXY与黄金期货的相关性和预警信号

整合到宏观战情室V2:
1. 将此文件放到宏观战情室项目目录
2. 在app.py中: from gold_alert import render_gold_alert_section, GoldMacroAnalyzer
3. 在主函数中调用: render_gold_alert_section(all_data, indicators)
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple
import warnings
warnings.filterwarnings('ignore')

# ==================== 数据类和枚举 ====================

class GoldSignal(Enum):
    STRONG_BUY = "强做多"
    BUY = "偏多"
    NEUTRAL = "中性"
    SELL = "偏空"
    STRONG_SELL = "强做空"

class AlertLevel(Enum):
    CRITICAL = "critical"  # 立即行动
    WARNING = "warning"    # 密切关注
    INFO = "info"          # 信息参考

@dataclass
class GoldAlert:
    """黄金预警信号"""
    level: AlertLevel
    title: str
    message: str
    factors: List[str]
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

@dataclass 
class CorrelationStatus:
    """相关性状态"""
    gold_dxy_corr: float          # 黄金vs DXY相关性
    gold_us10y_corr: float        # 黄金vs US10Y相关性
    dxy_us10y_corr: float         # DXY vs US10Y相关性
    correlation_regime: str       # 相关性体制
    regime_note: str              # 体制说明

# ==================== 核心分析器 ====================

class GoldMacroAnalyzer:
    """黄金宏观分析器"""
    
    # 历史相关性参考值 (基于研究报告)
    HISTORICAL_CORRELATIONS = {
        'gold_real_yield': -0.82,  # 最强负相关
        'gold_dxy': -0.55,         # 经典负相关
        'gold_us10y': -0.45,       # 名义收益率
    }
    
    # 实际利率阈值
    REAL_YIELD_THRESHOLDS = {
        'very_bullish': 0,      # 负实际利率 = 极度利好黄金
        'bullish': 1.0,         # < 1% = 利好
        'neutral': 2.0,         # 1-2% = 中性
        'bearish': 2.0,         # > 2% = 利空
    }
    
    def __init__(self, lookback_days: int = 60):
        self.lookback_days = lookback_days
        self.data = {}
        self.indicators = {}
        
    def load_data(self, yahoo_data: pd.DataFrame, fred_data: pd.DataFrame = None):
        """加载数据"""
        self.data['yahoo'] = yahoo_data
        self.data['fred'] = fred_data
        self._extract_series()
        
    def _extract_series(self):
        """提取关键时间序列"""
        yahoo = self.data.get('yahoo', pd.DataFrame())
        fred = self.data.get('fred', pd.DataFrame())
        
        # 从Yahoo获取
        self.gold = self._safe_extract(yahoo, ['GC=F', 'GLD'])  # 黄金期货或GLD
        self.dxy = self._safe_extract(yahoo, ['DX-Y.NYB', 'UUP'])  # 美元指数
        self.us10y = self._safe_extract(yahoo, ['^TNX'])  # 10年期收益率
        self.vix = self._safe_extract(yahoo, ['^VIX'])  # VIX
        self.tips = self._safe_extract(yahoo, ['TIP'])  # TIPS ETF代理实际利率
        
        # 从FRED获取 (如果可用)
        if fred is not None and not fred.empty:
            if 'DGS10' in fred.columns:
                self.us10y = fred['DGS10'].dropna()
            if 'DFII10' in fred.columns:  # 10年实际利率
                self.real_yield_fred = fred['DFII10'].dropna()
            if 'T10YIE' in fred.columns:  # 10年盈亏平衡通胀
                self.breakeven = fred['T10YIE'].dropna()
                
    def _safe_extract(self, df: pd.DataFrame, possible_cols: List[str]) -> pd.Series:
        """安全提取列"""
        if df is None or df.empty:
            return pd.Series(dtype=float)
        for col in possible_cols:
            if col in df.columns:
                return df[col].dropna()
        return pd.Series(dtype=float)
    
    def calculate_real_yield(self) -> Dict:
        """计算实际利率"""
        result = {
            'latest': None,
            'change_5d': None,
            'change_20d': None,
            'z_score': None,
            'percentile': None,
            'source': None
        }
        
        # 优先使用FRED的DFII10
        if hasattr(self, 'real_yield_fred') and len(self.real_yield_fred) > 0:
            series = self.real_yield_fred
            result['source'] = 'FRED DFII10'
        # 其次计算: US10Y - Breakeven
        elif hasattr(self, 'breakeven') and len(self.us10y) > 0 and len(self.breakeven) > 0:
            common_idx = self.us10y.index.intersection(self.breakeven.index)
            if len(common_idx) > 0:
                series = self.us10y.loc[common_idx] - self.breakeven.loc[common_idx]
                result['source'] = 'US10Y - Breakeven'
            else:
                return result
        # 最后用TIPS ETF代理
        elif len(self.tips) > 0:
            # TIP价格反向代理实际利率 (TIP涨 = 实际利率跌)
            # 简化处理：用TIP的变化率估算
            series = -self.tips.pct_change(20) * 100  # 转换为大致的利率变化
            result['source'] = 'TIP ETF (代理)'
        else:
            return result
        
        if len(series) > 0:
            result['latest'] = series.iloc[-1]
            if len(series) >= 5:
                result['change_5d'] = series.iloc[-1] - series.iloc[-5]
            if len(series) >= 20:
                result['change_20d'] = series.iloc[-1] - series.iloc[-20]
            if len(series) >= self.lookback_days:
                mean = series.iloc[-self.lookback_days:].mean()
                std = series.iloc[-self.lookback_days:].std()
                if std > 0:
                    result['z_score'] = (series.iloc[-1] - mean) / std
                result['percentile'] = (series.iloc[-self.lookback_days:] <= series.iloc[-1]).mean() * 100
                
        return result
    
    def calculate_correlations(self, window: int = 30) -> CorrelationStatus:
        """计算滚动相关性"""
        # 默认值
        default = CorrelationStatus(
            gold_dxy_corr=np.nan,
            gold_us10y_corr=np.nan,
            dxy_us10y_corr=np.nan,
            correlation_regime="未知",
            regime_note="数据不足"
        )
        
        if len(self.gold) < window or len(self.dxy) < window:
            return default
            
        # 对齐数据
        common_idx = self.gold.index.intersection(self.dxy.index)
        if len(self.us10y) > 0:
            common_idx = common_idx.intersection(self.us10y.index)
        
        if len(common_idx) < window:
            return default
            
        gold_aligned = self.gold.loc[common_idx].iloc[-window:]
        dxy_aligned = self.dxy.loc[common_idx].iloc[-window:]
        
        # 计算收益率
        gold_ret = gold_aligned.pct_change().dropna()
        dxy_ret = dxy_aligned.pct_change().dropna()
        
        # Gold vs DXY
        gold_dxy_corr = gold_ret.corr(dxy_ret)
        
        # Gold vs US10Y
        gold_us10y_corr = np.nan
        dxy_us10y_corr = np.nan
        
        if len(self.us10y) >= window:
            us10y_aligned = self.us10y.loc[common_idx].iloc[-window:]
            us10y_ret = us10y_aligned.pct_change().dropna()
            
            # 重新对齐
            common_ret_idx = gold_ret.index.intersection(us10y_ret.index)
            if len(common_ret_idx) > 10:
                gold_us10y_corr = gold_ret.loc[common_ret_idx].corr(us10y_ret.loc[common_ret_idx])
                dxy_us10y_corr = dxy_ret.loc[common_ret_idx].corr(us10y_ret.loc[common_ret_idx])
        
        # 判断相关性体制
        regime, note = self._determine_correlation_regime(gold_dxy_corr, gold_us10y_corr)
        
        return CorrelationStatus(
            gold_dxy_corr=gold_dxy_corr,
            gold_us10y_corr=gold_us10y_corr,
            dxy_us10y_corr=dxy_us10y_corr,
            correlation_regime=regime,
            regime_note=note
        )
    
    def _determine_correlation_regime(self, gold_dxy: float, gold_us10y: float) -> Tuple[str, str]:
        """判断相关性体制"""
        if np.isnan(gold_dxy):
            return "未知", "数据不足"
            
        # 正常体制: 黄金与美元负相关
        if gold_dxy < -0.3:
            return "正常", "传统负相关有效，可用DXY反向交易黄金"
        # 弱相关
        elif -0.3 <= gold_dxy <= 0.3:
            return "弱化", "相关性减弱，其他因素(地缘/央行购金)主导"
        # 异常体制: 同涨同跌
        else:
            return "异常", "⚠️ 黄金与美元同向移动，可能是避险需求或央行购金"
    
    def calculate_indicators(self) -> Dict:
        """计算所有指标"""
        indicators = {}
        
        # 1. 黄金价格指标
        if len(self.gold) > 0:
            indicators['gold'] = {
                'latest': self.gold.iloc[-1],
                'change_1d': self.gold.pct_change().iloc[-1] * 100 if len(self.gold) > 1 else 0,
                'change_5d': (self.gold.iloc[-1] / self.gold.iloc[-5] - 1) * 100 if len(self.gold) >= 5 else 0,
                'change_20d': (self.gold.iloc[-1] / self.gold.iloc[-20] - 1) * 100 if len(self.gold) >= 20 else 0,
                'ma20': self.gold.rolling(20).mean().iloc[-1] if len(self.gold) >= 20 else self.gold.iloc[-1],
                'ma50': self.gold.rolling(50).mean().iloc[-1] if len(self.gold) >= 50 else self.gold.iloc[-1],
            }
            # 判断趋势
            if indicators['gold']['latest'] > indicators['gold']['ma20'] > indicators['gold']['ma50']:
                indicators['gold']['trend'] = "上升趋势"
                indicators['gold']['trend_emoji'] = "📈"
            elif indicators['gold']['latest'] < indicators['gold']['ma20'] < indicators['gold']['ma50']:
                indicators['gold']['trend'] = "下降趋势"
                indicators['gold']['trend_emoji'] = "📉"
            else:
                indicators['gold']['trend'] = "震荡"
                indicators['gold']['trend_emoji'] = "↔️"
        
        # 2. DXY指标
        if len(self.dxy) > 0:
            dxy_series = self.dxy
            indicators['dxy'] = {
                'latest': dxy_series.iloc[-1],
                'change_5d': (dxy_series.iloc[-1] / dxy_series.iloc[-5] - 1) * 100 if len(dxy_series) >= 5 else 0,
                'rsi_14': self._calculate_rsi(dxy_series, 14),
            }
            # RSI判断
            rsi = indicators['dxy']['rsi_14']
            if rsi > 70:
                indicators['dxy']['rsi_status'] = "超买"
                indicators['dxy']['rsi_emoji'] = "🔴"
            elif rsi < 30:
                indicators['dxy']['rsi_status'] = "超卖"
                indicators['dxy']['rsi_emoji'] = "🟢"
            else:
                indicators['dxy']['rsi_status'] = "中性"
                indicators['dxy']['rsi_emoji'] = "⚪"
        
        # 3. US10Y指标
        if len(self.us10y) > 0:
            us10y_series = self.us10y
            indicators['us10y'] = {
                'latest': us10y_series.iloc[-1],
                'change_5d': us10y_series.iloc[-1] - us10y_series.iloc[-5] if len(us10y_series) >= 5 else 0,
                'change_20d': us10y_series.iloc[-1] - us10y_series.iloc[-20] if len(us10y_series) >= 20 else 0,
            }
            # 方向判断
            if indicators['us10y']['change_5d'] > 0.05:
                indicators['us10y']['direction'] = "上升"
                indicators['us10y']['direction_emoji'] = "⬆️"
            elif indicators['us10y']['change_5d'] < -0.05:
                indicators['us10y']['direction'] = "下降"
                indicators['us10y']['direction_emoji'] = "⬇️"
            else:
                indicators['us10y']['direction'] = "持平"
                indicators['us10y']['direction_emoji'] = "➡️"
        
        # 4. 实际利率
        indicators['real_yield'] = self.calculate_real_yield()
        
        # 5. 相关性
        indicators['correlations'] = self.calculate_correlations(30)
        
        # 6. VIX
        if len(self.vix) > 0:
            indicators['vix'] = {
                'latest': self.vix.iloc[-1],
                'level': 'high' if self.vix.iloc[-1] > 25 else 'low' if self.vix.iloc[-1] < 15 else 'normal'
            }
        
        self.indicators = indicators
        return indicators
    
    def _calculate_rsi(self, series: pd.Series, period: int = 14) -> float:
        """计算RSI"""
        if len(series) < period + 1:
            return 50.0
        
        delta = series.diff()
        gain = delta.where(delta > 0, 0).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi.iloc[-1] if not np.isnan(rsi.iloc[-1]) else 50.0
    
    def calculate_composite_score(self) -> Dict:
        """计算黄金综合评分 (0-100, 50为中性)"""
        if not self.indicators:
            self.calculate_indicators()
        
        score = 50  # 起始中性
        factors = []
        
        # 1. 实际利率因子 (权重 40%)
        real_yield = self.indicators.get('real_yield', {})
        ry_latest = real_yield.get('latest')
        
        if ry_latest is not None and not np.isnan(ry_latest):
            if ry_latest < 0:
                score += 20
                factors.append(f"✅ 负实际利率 ({ry_latest:.2f}%) → 极度利好黄金 (+20)")
            elif ry_latest < 1.0:
                score += 10
                factors.append(f"✅ 低实际利率 ({ry_latest:.2f}%) → 利好黄金 (+10)")
            elif ry_latest > 2.0:
                score -= 15
                factors.append(f"❌ 高实际利率 ({ry_latest:.2f}%) → 利空黄金 (-15)")
            
            # 变化方向
            ry_change = real_yield.get('change_5d', 0)
            if ry_change is not None and not np.isnan(ry_change):
                if ry_change < -0.1:
                    score += 8
                    factors.append(f"✅ 实际利率5日下降 ({ry_change:.2f}%) → 利好 (+8)")
                elif ry_change > 0.15:
                    score -= 8
                    factors.append(f"❌ 实际利率5日上升 ({ry_change:.2f}%) → 利空 (-8)")
        
        # 2. DXY因子 (权重 25%)
        dxy = self.indicators.get('dxy', {})
        dxy_rsi = dxy.get('rsi_14', 50)
        
        if dxy_rsi > 70:
            score += 12
            factors.append(f"✅ DXY超买 (RSI={dxy_rsi:.1f}) → 利好黄金 (+12)")
        elif dxy_rsi < 30:
            score -= 10
            factors.append(f"❌ DXY超卖 (RSI={dxy_rsi:.1f}) → 利空黄金 (-10)")
        
        dxy_change = dxy.get('change_5d', 0)
        if dxy_change < -1:
            score += 5
            factors.append(f"✅ DXY走弱 ({dxy_change:.1f}%) → 利好 (+5)")
        elif dxy_change > 1:
            score -= 5
            factors.append(f"❌ DXY走强 ({dxy_change:.1f}%) → 利空 (-5)")
        
        # 3. VIX因子 (权重 20%)
        vix = self.indicators.get('vix', {})
        vix_level = vix.get('level', 'normal')
        vix_latest = vix.get('latest', 20)
        
        if vix_level == 'high':
            score += 10
            factors.append(f"✅ VIX高位 ({vix_latest:.1f}) → Risk-off利好黄金 (+10)")
        elif vix_level == 'low':
            score -= 5
            factors.append(f"⚪ VIX低位 ({vix_latest:.1f}) → 风险偏好高 (-5)")
        
        # 4. 相关性状态因子 (权重 15%)
        corr = self.indicators.get('correlations')
        if corr and not np.isnan(corr.gold_dxy_corr):
            if corr.correlation_regime == "正常":
                score += 5
                factors.append(f"✅ 相关性正常 (Gold/DXY={corr.gold_dxy_corr:.2f}) → 框架有效 (+5)")
            elif corr.correlation_regime == "异常":
                factors.append(f"⚠️ 相关性异常 (Gold/DXY={corr.gold_dxy_corr:.2f}) → 需谨慎 (不加分)")
        
        # 限制范围
        score = max(0, min(100, score))
        
        # 生成信号
        if score >= 75:
            signal = GoldSignal.STRONG_BUY
        elif score >= 60:
            signal = GoldSignal.BUY
        elif score >= 40:
            signal = GoldSignal.NEUTRAL
        elif score >= 25:
            signal = GoldSignal.SELL
        else:
            signal = GoldSignal.STRONG_SELL
        
        return {
            'score': score,
            'signal': signal,
            'factors': factors,
            'interpretation': self._get_score_interpretation(score)
        }
    
    def _get_score_interpretation(self, score: float) -> str:
        """获取评分解读"""
        if score >= 75:
            return "极度利好黄金 - 多因子共振做多信号"
        elif score >= 60:
            return "偏多 - 逢低做多黄金"
        elif score >= 40:
            return "中性 - 观望等待明确信号"
        elif score >= 25:
            return "偏空 - 谨慎做空或减持"
        else:
            return "极度利空 - 多因子共振做空信号"
    
    def generate_alerts(self) -> List[GoldAlert]:
        """生成预警信号"""
        if not self.indicators:
            self.calculate_indicators()
        
        alerts = []
        
        # 1. 实际利率预警
        real_yield = self.indicators.get('real_yield', {})
        ry_latest = real_yield.get('latest')
        ry_change = real_yield.get('change_5d', 0)
        
        if ry_latest is not None and not np.isnan(ry_latest):
            if ry_latest < 0:
                alerts.append(GoldAlert(
                    level=AlertLevel.CRITICAL,
                    title="负实际利率",
                    message=f"实际利率为 {ry_latest:.2f}%，历史上这是黄金大涨的前提条件",
                    factors=["实际利率 < 0", "黄金持有成本为负"]
                ))
            
            if ry_change is not None and not np.isnan(ry_change):
                if ry_change < -0.15:
                    alerts.append(GoldAlert(
                        level=AlertLevel.WARNING,
                        title="实际利率快速下行",
                        message=f"实际利率5日下降 {abs(ry_change):.2f}%，利好黄金",
                        factors=[f"5日变化: {ry_change:.2f}%"]
                    ))
                elif ry_change > 0.2:
                    alerts.append(GoldAlert(
                        level=AlertLevel.WARNING,
                        title="实际利率快速上行",
                        message=f"实际利率5日上升 {ry_change:.2f}%，警惕黄金回调",
                        factors=[f"5日变化: +{ry_change:.2f}%"]
                    ))
        
        # 2. DXY预警
        dxy = self.indicators.get('dxy', {})
        dxy_rsi = dxy.get('rsi_14', 50)
        
        if dxy_rsi > 75:
            alerts.append(GoldAlert(
                level=AlertLevel.WARNING,
                title="DXY极度超买",
                message=f"DXY RSI={dxy_rsi:.1f}，美元可能见顶回落，利好黄金",
                factors=[f"RSI: {dxy_rsi:.1f}", "历史上DXY超买后常回调"]
            ))
        elif dxy_rsi < 25:
            alerts.append(GoldAlert(
                level=AlertLevel.WARNING,
                title="DXY极度超卖",
                message=f"DXY RSI={dxy_rsi:.1f}，美元可能反弹，警惕黄金回调",
                factors=[f"RSI: {dxy_rsi:.1f}"]
            ))
        
        # 3. 相关性异常预警
        corr = self.indicators.get('correlations')
        if corr and corr.correlation_regime == "异常":
            alerts.append(GoldAlert(
                level=AlertLevel.WARNING,
                title="相关性异常",
                message=f"黄金与DXY相关性为 {corr.gold_dxy_corr:.2f}（正相关），传统框架失效",
                factors=["可能是避险需求", "可能是央行购金", "需结合其他因素判断"]
            ))
        
        # 4. US10Y与DXY背离预警
        us10y = self.indicators.get('us10y', {})
        us10y_change = us10y.get('change_5d', 0)
        dxy_change = dxy.get('change_5d', 0)
        
        if us10y_change is not None and dxy_change is not None:
            if us10y_change < -0.1 and dxy_change > 0.5:
                alerts.append(GoldAlert(
                    level=AlertLevel.INFO,
                    title="US10Y与DXY背离",
                    message=f"收益率下跌({us10y_change:.2f}%)但美元上涨({dxy_change:.1f}%)，关注后续修正",
                    factors=["收益率下跌", "美元上涨", "可能有一方会修正"]
                ))
            elif us10y_change > 0.1 and dxy_change < -0.5:
                alerts.append(GoldAlert(
                    level=AlertLevel.INFO,
                    title="US10Y与DXY背离",
                    message=f"收益率上涨({us10y_change:.2f}%)但美元下跌({dxy_change:.1f}%)，关注后续修正",
                    factors=["收益率上涨", "美元下跌", "可能有一方会修正"]
                ))
        
        # 5. VIX预警
        vix = self.indicators.get('vix', {})
        vix_latest = vix.get('latest', 20)
        
        if vix_latest > 30:
            alerts.append(GoldAlert(
                level=AlertLevel.WARNING,
                title="VIX高位",
                message=f"VIX={vix_latest:.1f}，市场恐慌，黄金避险需求上升",
                factors=[f"VIX: {vix_latest:.1f}", "Risk-off环境"]
            ))
        
        return alerts
    
    def get_trading_suggestions(self) -> Dict:
        """获取交易建议"""
        if not self.indicators:
            self.calculate_indicators()
        
        score_data = self.calculate_composite_score()
        score = score_data['score']
        signal = score_data['signal']
        
        suggestions = {
            'signal': signal.value,
            'score': score,
            'actions': [],
            'key_levels': {},
            'risk_factors': []
        }
        
        # 获取黄金价格
        gold = self.indicators.get('gold', {})
        gold_price = gold.get('latest', 0)
        gold_ma20 = gold.get('ma20', 0)
        gold_ma50 = gold.get('ma50', 0)
        
        if gold_price > 0:
            suggestions['key_levels'] = {
                'current': gold_price,
                'ma20_support': gold_ma20,
                'ma50_support': gold_ma50,
            }
        
        # 根据信号给出建议
        if signal == GoldSignal.STRONG_BUY:
            suggestions['actions'] = [
                "✅ 可考虑建立黄金多头头寸",
                f"✅ 支撑位参考: MA20 ${gold_ma20:.0f}",
                "✅ 可逐步加仓，控制总仓位"
            ]
        elif signal == GoldSignal.BUY:
            suggestions['actions'] = [
                "📈 偏多观点，等待回调做多",
                f"📈 理想入场区间: ${gold_ma20:.0f} - ${gold_price:.0f}",
                "📈 建议分批建仓"
            ]
        elif signal == GoldSignal.NEUTRAL:
            suggestions['actions'] = [
                "⚪ 观望为主，等待明确信号",
                "⚪ 可轻仓参与区间交易",
                "⚪ 关注实际利率和DXY变化"
            ]
        elif signal == GoldSignal.SELL:
            suggestions['actions'] = [
                "📉 偏空观点，谨慎做多",
                "📉 已有多头可考虑减仓",
                "📉 等待更好的做多时机"
            ]
        else:  # STRONG_SELL
            suggestions['actions'] = [
                "❌ 不建议做多黄金",
                "❌ 可考虑轻仓做空或完全离场",
                f"❌ 若跌破MA50 ${gold_ma50:.0f} 可能加速下跌"
            ]
        
        # 风险因素
        corr = self.indicators.get('correlations')
        if corr and corr.correlation_regime == "异常":
            suggestions['risk_factors'].append("⚠️ 相关性异常，传统框架可能失效")
        
        real_yield = self.indicators.get('real_yield', {})
        if real_yield.get('latest', 0) > 2:
            suggestions['risk_factors'].append("⚠️ 高实际利率环境不利于黄金")
        
        return suggestions


# ==================== Streamlit 渲染函数 ====================

def render_gold_alert_section(all_data: Dict, indicators: Dict = None):
    """渲染黄金预警章节 - 用于集成到宏观战情室V2"""
    import streamlit as st
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    
    st.markdown('<div class="chapter-header">🥇 黄金宏观预警</div>', unsafe_allow_html=True)
    st.markdown('*"实际利率+美元+避险三因子监控"*')
    
    # 初始化分析器
    analyzer = GoldMacroAnalyzer()
    
    yahoo_data = all_data.get('yahoo', pd.DataFrame())
    fred_data = all_data.get('fred', pd.DataFrame())
    
    if yahoo_data.empty:
        st.warning("Yahoo数据不可用，黄金分析功能受限")
        return
    
    analyzer.load_data(yahoo_data, fred_data)
    gold_indicators = analyzer.calculate_indicators()
    score_data = analyzer.calculate_composite_score()
    alerts = analyzer.generate_alerts()
    suggestions = analyzer.get_trading_suggestions()
    
    # ========== 评分和信号 ==========
    col1, col2, col3 = st.columns([1, 1, 2])
    
    with col1:
        # 评分仪表盘
        score = score_data['score']
        signal = score_data['signal']
        
        # 颜色
        if score >= 60:
            color = '#FFD700'  # 金色
        elif score >= 40:
            color = '#808080'  # 灰色
        else:
            color = '#FF6347'  # 红色
        
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=score,
            domain={'x': [0, 1], 'y': [0, 1]},
            title={'text': "黄金宏观评分", 'font': {'size': 16, 'color': 'white'}},
            number={'font': {'size': 36, 'color': 'white'}},
            gauge={
                'axis': {'range': [0, 100], 'tickcolor': "white"},
                'bar': {'color': color},
                'bgcolor': "rgba(0,0,0,0)",
                'borderwidth': 2,
                'bordercolor': "gray",
                'steps': [
                    {'range': [0, 25], 'color': 'rgba(255,99,71,0.3)'},
                    {'range': [25, 40], 'color': 'rgba(255,165,0,0.3)'},
                    {'range': [40, 60], 'color': 'rgba(128,128,128,0.3)'},
                    {'range': [60, 75], 'color': 'rgba(144,238,144,0.3)'},
                    {'range': [75, 100], 'color': 'rgba(255,215,0,0.3)'},
                ],
            }
        ))
        
        fig_gauge.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font={'color': 'white'},
            height=200,
            margin=dict(l=20, r=20, t=40, b=20)
        )
        
        st.plotly_chart(fig_gauge, use_container_width=True)
        
        # 信号显示
        signal_colors = {
            GoldSignal.STRONG_BUY: ('🟢', '#00C853'),
            GoldSignal.BUY: ('🟢', '#90EE90'),
            GoldSignal.NEUTRAL: ('⚪', '#808080'),
            GoldSignal.SELL: ('🔴', '#FF9800'),
            GoldSignal.STRONG_SELL: ('🔴', '#FF1744'),
        }
        emoji, _ = signal_colors.get(signal, ('⚪', '#808080'))
        st.markdown(f"**信号: {emoji} {signal.value}**")
    
    with col2:
        # 关键指标
        gold = gold_indicators.get('gold', {})
        real_yield = gold_indicators.get('real_yield', {})
        dxy = gold_indicators.get('dxy', {})
        
        st.metric(
            "黄金 (GC/GLD)",
            f"${gold.get('latest', 0):.0f}",
            f"{gold.get('change_5d', 0):.1f}% (5d)"
        )
        
        ry_val = real_yield.get('latest', 0)
        ry_str = f"{ry_val:.2f}%" if ry_val is not None and not np.isnan(ry_val) else "N/A"
        st.metric(
            "实际利率",
            ry_str,
            f"5d: {real_yield.get('change_5d', 0):.2f}%" if real_yield.get('change_5d') else None,
            delta_color="inverse"
        )
        
        st.metric(
            "DXY",
            f"{dxy.get('latest', 0):.1f}",
            f"RSI: {dxy.get('rsi_14', 50):.0f} {dxy.get('rsi_emoji', '')}"
        )
    
    with col3:
        # 相关性状态
        corr = gold_indicators.get('correlations')
        if corr:
            st.markdown("**📊 相关性状态 (30日滚动)**")
            
            col3a, col3b, col3c = st.columns(3)
            with col3a:
                corr_val = corr.gold_dxy_corr
                corr_str = f"{corr_val:.2f}" if not np.isnan(corr_val) else "N/A"
                corr_emoji = "✅" if corr_val < -0.3 else "⚠️" if corr_val > 0.3 else "⚪"
                st.metric("Gold/DXY", corr_str, corr_emoji)
            
            with col3b:
                corr_val2 = corr.gold_us10y_corr
                corr_str2 = f"{corr_val2:.2f}" if not np.isnan(corr_val2) else "N/A"
                st.metric("Gold/US10Y", corr_str2)
            
            with col3c:
                st.metric("体制", corr.correlation_regime)
            
            st.caption(f"💡 {corr.regime_note}")
    
    # ========== 预警信号 ==========
    if alerts:
        st.markdown("**🚨 预警信号**")
        for alert in alerts[:4]:
            level_class = {
                AlertLevel.CRITICAL: ('alert-extreme', '🔴'),
                AlertLevel.WARNING: ('alert-warning', '🟡'),
                AlertLevel.INFO: ('', 'ℹ️'),
            }
            css_class, emoji = level_class.get(alert.level, ('', 'ℹ️'))
            
            st.markdown(f"""
            <div class="alert-box {css_class}" style="padding: 8px; border-radius: 5px; margin: 5px 0; 
                 background: {'rgba(255,23,68,0.15)' if alert.level == AlertLevel.CRITICAL else 'rgba(255,214,0,0.15)' if alert.level == AlertLevel.WARNING else 'rgba(100,100,100,0.1)'};
                 border-left: 3px solid {'#FF1744' if alert.level == AlertLevel.CRITICAL else '#FFD600' if alert.level == AlertLevel.WARNING else '#666'};">
                {emoji} <strong>{alert.title}</strong>: {alert.message}
            </div>
            """, unsafe_allow_html=True)
    
    # ========== 评分因子 ==========
    with st.expander("📋 评分因子明细", expanded=False):
        for factor in score_data['factors']:
            st.markdown(f"- {factor}")
        st.markdown(f"\n**解读:** {score_data['interpretation']}")
    
    # ========== 交易建议 ==========
    with st.expander("💡 交易建议", expanded=False):
        st.markdown(f"**信号: {suggestions['signal']}** (评分: {suggestions['score']}/100)")
        
        st.markdown("**操作建议:**")
        for action in suggestions['actions']:
            st.markdown(f"- {action}")
        
        if suggestions['key_levels']:
            st.markdown("**关键价位:**")
            levels = suggestions['key_levels']
            st.markdown(f"- 当前: ${levels.get('current', 0):.0f}")
            st.markdown(f"- MA20支撑: ${levels.get('ma20_support', 0):.0f}")
            st.markdown(f"- MA50支撑: ${levels.get('ma50_support', 0):.0f}")
        
        if suggestions['risk_factors']:
            st.markdown("**风险因素:**")
            for risk in suggestions['risk_factors']:
                st.markdown(f"- {risk}")
    
    # ========== 指标说明 ==========
    with st.expander("📖 黄金宏观指标说明", expanded=False):
        st.markdown("""
        ### 核心驱动因子
        
        **实际利率 (权重40%)**
        - 定义: 名义利率 - 通胀预期
        - 与黄金相关性: **-0.82** (最强负相关)
        - 逻辑: 实际利率下降 → 持有黄金机会成本降低 → 利好黄金
        - 阈值: <0%极度利好, <1%利好, >2%利空
        
        **DXY美元指数 (权重25%)**
        - 与黄金相关性: **-0.55** (经典负相关)
        - 逻辑: 黄金以美元计价，美元走弱 → 黄金相对便宜 → 利好
        - 监控: RSI超买(>70)可能预示美元回调，利好黄金
        
        **VIX恐慌指数 (权重20%)**
        - 与黄金: 正相关 (避险需求)
        - 逻辑: VIX上升 → Risk-off → 资金流入黄金避险
        - 阈值: >25高位利好黄金, <15低位中性
        
        **相关性状态 (权重15%)**
        - 正常: Gold/DXY负相关 → 传统框架有效
        - 异常: Gold/DXY正相关 → 央行购金或极端避险主导
        
        ### 2023-2024年特殊情况
        - 黄金与美元同涨 (历史异常)
        - 原因: 央行购金 + 地缘避险
        - 启示: 不能单纯依赖DXY反向交易黄金
        """)
    
    return {
        'score': score_data['score'],
        'signal': score_data['signal'].value,
        'indicators': gold_indicators,
        'alerts': alerts,
        'suggestions': suggestions
    }


def get_gold_summary_for_prompt(all_data: Dict) -> str:
    """生成黄金分析摘要 - 用于Claude导出"""
    analyzer = GoldMacroAnalyzer()
    
    yahoo_data = all_data.get('yahoo', pd.DataFrame())
    fred_data = all_data.get('fred', pd.DataFrame())
    
    if yahoo_data.empty:
        return "黄金数据不可用"
    
    analyzer.load_data(yahoo_data, fred_data)
    indicators = analyzer.calculate_indicators()
    score_data = analyzer.calculate_composite_score()
    alerts = analyzer.generate_alerts()
    
    summary_lines = [
        "## 🥇 黄金宏观分析",
        f"- 评分: {score_data['score']}/100 ({score_data['signal'].value})",
    ]
    
    gold = indicators.get('gold', {})
    if gold:
        summary_lines.append(f"- 黄金价格: ${gold.get('latest', 0):.0f} ({gold.get('trend', 'N/A')})")
    
    real_yield = indicators.get('real_yield', {})
    ry_val = real_yield.get('latest')
    if ry_val is not None and not np.isnan(ry_val):
        summary_lines.append(f"- 实际利率: {ry_val:.2f}%")
    
    dxy = indicators.get('dxy', {})
    if dxy:
        summary_lines.append(f"- DXY: {dxy.get('latest', 0):.1f} (RSI: {dxy.get('rsi_14', 50):.0f})")
    
    corr = indicators.get('correlations')
    if corr:
        summary_lines.append(f"- 相关性体制: {corr.correlation_regime}")
    
    if alerts:
        summary_lines.append("- 预警:")
        for alert in alerts[:3]:
            summary_lines.append(f"  - {alert.title}: {alert.message}")
    
    return "\n".join(summary_lines)


# ==================== 测试 ====================

if __name__ == "__main__":
    print("黄金宏观预警模块已加载")
    print("使用方法:")
    print("1. from gold_alert import GoldMacroAnalyzer, render_gold_alert_section")
    print("2. 在Streamlit中调用 render_gold_alert_section(all_data, indicators)")
