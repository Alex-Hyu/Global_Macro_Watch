"""
SpotGamma 分析模块 - 宏观战情室 V2
整合官方指标定义和增强分析功能

官方指标定义:
- Key Gamma Strike: 最大Gamma头寸行权价（磁吸效应）
- Hedge Wall: 做市商风险暴露变化位（上方均值回归，下方高波动）
- Volume Ratio: ATM Put Delta与Call Delta成交量比（非传统P/C Vol）
- Options Implied Move: 美元值（非百分比）
- Next Exp Gamma >25%: 短期头寸集中，到期前后易剧烈波动
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, List, Tuple, Dict, Any
from enum import Enum
from datetime import datetime, date
import re
import io


# ============================================================
# 数据结构定义
# ============================================================

class GammaEnvironment(Enum):
    """Gamma环境类型"""
    POSITIVE = "正Gamma"
    NEGATIVE = "负Gamma"
    NEUTRAL = "中性"


class MarketBias(Enum):
    """市场偏向"""
    BULLISH = "偏多"
    BEARISH = "偏空"
    NEUTRAL = "中性"


class RiskLevel(Enum):
    """风险等级"""
    LOW = "低"
    MEDIUM = "中"
    HIGH = "高"
    EXTREME = "极端"


@dataclass
class GammaLevels:
    """Gamma关键位置数据"""
    zero_gamma: float = 0
    call_wall: float = 0
    put_wall: float = 0
    volatility_trigger: float = 0
    hedge_wall: float = 0
    key_gamma_strike: float = 0
    key_delta_strike: float = 0
    large_gamma_1: float = 0
    large_gamma_2: float = 0
    large_gamma_3: float = 0
    large_gamma_4: float = 0


@dataclass
class SpotGammaIndicators:
    """SpotGamma方向性和波动性指标"""
    # 方向性指标
    delta_ratio: float = -1.0       # Put Delta ÷ Call Delta（负值）
    gamma_ratio: float = 1.0        # Put Gamma ÷ Call Gamma
    put_call_oi_ratio: float = 1.0  # Put OI ÷ Call OI
    volume_ratio: float = 1.0       # ATM Put Delta vs Call Delta成交量比
    
    # 波动性指标
    options_implied_move: float = 0  # 美元值！非百分比
    iv_rank: float = 50              # IV百分位 (0-100)
    one_month_iv: float = 0          # 1个月隐含波动率
    one_month_rv: float = 0          # 1个月实际波动率
    skew: float = 0                  # 偏度
    ne_skew: float = 0               # 近期偏度
    
    # 期权影响
    options_impact: float = 0        # 期权驱动股价程度 (0-1)
    
    # 到期集中度
    next_exp_gamma_pct: float = 0    # 下次到期Gamma占比
    next_exp_delta_pct: float = 0    # 下次到期Delta占比
    top_gamma_exp: str = ""          # 最大Gamma到期日
    top_delta_exp: str = ""          # 最大Delta到期日


# ============================================================
# CSV 解析函数
# ============================================================

def parse_spotgamma_csv(file) -> pd.DataFrame:
    """解析SpotGamma CSV文件"""
    try:
        # 支持文件对象或路径
        if hasattr(file, 'read'):
            file.seek(0)
            df = pd.read_csv(file)
        else:
            df = pd.read_csv(file)
        
        # 清理列名（去除空格和特殊字符）
        df.columns = df.columns.str.strip()
        
        return df
    except Exception as e:
        print(f"CSV解析错误: {e}")
        return pd.DataFrame()


def extract_stock_data(df: pd.DataFrame, ticker: str) -> Tuple[Optional[Dict], Optional[SpotGammaIndicators]]:
    """从DataFrame中提取特定股票的数据"""
    if df.empty:
        return None, None
    
    # 查找ticker列
    ticker_col = None
    for col in df.columns:
        if col.lower() in ['ticker', 'symbol', 'stock']:
            ticker_col = col
            break
    
    if ticker_col is None:
        # 假设第一列是ticker
        ticker_col = df.columns[0]
    
    # 筛选股票
    row = df[df[ticker_col].str.upper() == ticker.upper()]
    
    if row.empty:
        return None, None
    
    row = row.iloc[0].to_dict()
    
    # 解析关键位置
    levels = {}
    indicators = SpotGammaIndicators()
    
    # 提取价格信息
    for col, key in [
        ('Key Gamma Strike', 'key_gamma_strike'),
        ('Key Delta Strike', 'key_delta_strike'),
        ('Hedge Wall', 'hedge_wall'),
        ('Call Wall', 'call_wall'),
        ('Put Wall', 'put_wall'),
    ]:
        if col in row:
            try:
                levels[key] = float(row[col]) if row[col] else 0
            except:
                levels[key] = 0
    
    # 辅助函数：解析百分比
    def parse_pct(val):
        if pd.isna(val) or val == '':
            return 0
        if isinstance(val, str):
            return float(val.replace('%', '').replace(',', ''))
        return float(val)
    
    # 辅助函数：解析数字
    def parse_num(val):
        if pd.isna(val) or val == '':
            return 0
        if isinstance(val, str):
            val = val.replace(',', '').replace('$', '')
        try:
            return float(val)
        except:
            return 0
    
    # 提取指标
    indicators.delta_ratio = parse_num(row.get('Delta Ratio', -1))
    indicators.gamma_ratio = parse_num(row.get('Gamma Ratio', 1))
    indicators.put_call_oi_ratio = parse_num(row.get('Put/Call OI Ratio', row.get('Put/Call OI\xa0Ratio', 1)))
    indicators.volume_ratio = parse_num(row.get('Volume Ratio', 1))
    
    indicators.options_implied_move = parse_num(row.get('Options Implied Move', 0))
    indicators.iv_rank = parse_pct(row.get('IV Rank', 50))
    indicators.one_month_iv = parse_pct(row.get('1 M IV', row.get('1M IV', 0)))
    indicators.one_month_rv = parse_pct(row.get('1 M RV', row.get('1M RV', 0)))
    indicators.skew = parse_pct(row.get('Skew', 0))
    indicators.ne_skew = parse_pct(row.get('NE Skew', 0))
    
    indicators.options_impact = parse_num(row.get('Options Impact', 0))
    indicators.next_exp_gamma_pct = parse_pct(row.get('Next Exp Gamma', 0))
    indicators.next_exp_delta_pct = parse_pct(row.get('Next Exp Delta', 0))
    indicators.top_gamma_exp = str(row.get('Top Gamma Exp', ''))
    indicators.top_delta_exp = str(row.get('Top Delta Exp', ''))
    
    return levels, indicators


# ============================================================
# 分析引擎
# ============================================================

class SpotGammaAnalyzer:
    """SpotGamma 分析器"""
    
    def __init__(self, ticker: str = "QQQ"):
        self.ticker = ticker
        self.current_price: float = 0
        self.previous_close: float = 0
        self.levels: Dict = {}
        self.indicators: SpotGammaIndicators = SpotGammaIndicators()
        self.is_friday: bool = date.today().weekday() == 4
        self.is_data_day: bool = False
        self.data_event: str = ""
    
    def load_from_csv(self, df: pd.DataFrame, current_price: float, previous_close: float = 0):
        """从CSV DataFrame加载数据"""
        levels, indicators = extract_stock_data(df, self.ticker)
        
        if levels:
            self.levels = levels
        if indicators:
            self.indicators = indicators
        
        self.current_price = current_price
        self.previous_close = previous_close or current_price
    
    def set_manual_levels(self, 
                          zero_gamma: float = 0,
                          call_wall: float = 0, 
                          put_wall: float = 0,
                          volatility_trigger: float = 0):
        """手动设置关键位置"""
        if zero_gamma:
            self.levels['zero_gamma'] = zero_gamma
        if call_wall:
            self.levels['call_wall'] = call_wall
        if put_wall:
            self.levels['put_wall'] = put_wall
        if volatility_trigger:
            self.levels['volatility_trigger'] = volatility_trigger
    
    def determine_gamma_environment(self) -> Tuple[GammaEnvironment, float, float]:
        """判断Gamma环境"""
        zg = self.levels.get('zero_gamma', 0) or self.levels.get('hedge_wall', 0)
        
        if not zg or not self.current_price:
            return GammaEnvironment.NEUTRAL, 0, 0
        
        distance = self.current_price - zg
        distance_pct = (distance / self.current_price) * 100
        
        if distance > 0:
            return GammaEnvironment.POSITIVE, distance, distance_pct
        elif distance < 0:
            return GammaEnvironment.NEGATIVE, distance, distance_pct
        else:
            return GammaEnvironment.NEUTRAL, 0, 0
    
    def analyze_delta_ratio(self) -> Tuple[MarketBias, str]:
        """
        分析Delta Ratio
        官方定义: Put Delta ÷ Call Delta（负值）
        > -1.0 = 偏多 | -1 to -2 = 中性 | < -2.0 = 偏空 | < -3.0 = 强烈偏空
        """
        dr = self.indicators.delta_ratio
        
        if dr > -1.0:
            return MarketBias.BULLISH, f"Delta Ratio {dr:.2f} > -1: Call Delta主导，偏多"
        elif -2.0 <= dr <= -1.0:
            return MarketBias.NEUTRAL, f"Delta Ratio {dr:.2f}: 中性区间"
        elif -3.0 <= dr < -2.0:
            return MarketBias.BEARISH, f"Delta Ratio {dr:.2f} < -2: 偏空"
        else:
            return MarketBias.BEARISH, f"Delta Ratio {dr:.2f} < -3: 强烈偏空！"
    
    def analyze_gamma_ratio(self) -> Tuple[MarketBias, str]:
        """
        分析Gamma Ratio
        官方定义: Put Gamma ÷ Call Gamma
        < 1.0 = Call Gamma主导(上涨加速) | = 1.0 均衡 | > 2.0 = Put Gamma主导(下跌加速)
        """
        gr = self.indicators.gamma_ratio
        
        if gr < 1.0:
            return MarketBias.BULLISH, f"Gamma Ratio {gr:.2f} < 1: Call Gamma主导，上涨加速"
        elif 1.0 <= gr <= 2.0:
            return MarketBias.NEUTRAL, f"Gamma Ratio {gr:.2f}: 均衡区间"
        else:
            return MarketBias.BEARISH, f"Gamma Ratio {gr:.2f} > 2: Put Gamma主导，下跌加速"
    
    def analyze_volume_ratio(self) -> Tuple[str, str]:
        """
        分析Volume Ratio
        官方定义: ATM Put Delta与Call Delta成交量比（非传统P/C Vol）
        高比率 = 大量ATM Put头寸，到期后MM平空头对冲可能推动反弹
        """
        vr = self.indicators.volume_ratio
        
        if vr > 1.5:
            return "高", f"Volume Ratio {vr:.2f}: 大量ATM Put头寸，到期后可能推动反弹"
        elif vr > 1.0:
            return "略高", f"Volume Ratio {vr:.2f}: ATM Put偏多"
        elif vr < 0.7:
            return "低", f"Volume Ratio {vr:.2f}: ATM Call主导"
        else:
            return "均衡", f"Volume Ratio {vr:.2f}: 均衡"
    
    def analyze_hedge_wall(self) -> str:
        """分析Hedge Wall位置"""
        hw = self.levels.get('hedge_wall', 0)
        if not hw:
            return "Hedge Wall 数据缺失"
        
        if self.current_price > hw:
            return f"价格 > Hedge Wall ({hw:.0f}): 均值回归模式"
        else:
            return f"价格 < Hedge Wall ({hw:.0f}): ⚠️ 高波动/趋势模式"
    
    def analyze_next_exp_concentration(self) -> Tuple[bool, str]:
        """
        分析下次到期集中度
        官方: Next Exp Gamma > 25% = 短期头寸集中，到期前后易剧烈波动
        """
        neg = self.indicators.next_exp_gamma_pct
        is_concentrated = neg > 25
        
        if is_concentrated:
            return True, f"⚠️ Next Exp Gamma {neg:.1f}% > 25%: 到期前后易剧烈波动！"
        else:
            return False, f"Next Exp Gamma {neg:.1f}%: 正常分布"
    
    def calculate_implied_range(self) -> Tuple[float, float]:
        """计算隐含波动范围 (Options Implied Move 是美元值！)"""
        im = self.indicators.options_implied_move
        price = self.current_price
        
        if not im or not price:
            return price - 5, price + 5
        
        return price - im, price + im
    
    def get_risk_level(self) -> RiskLevel:
        """获取风险等级"""
        gamma_env, dist, dist_pct = self.determine_gamma_environment()
        
        if abs(dist_pct) < 0.5:
            risk = RiskLevel.EXTREME
        elif abs(dist_pct) < 1.0:
            risk = RiskLevel.HIGH
        elif abs(dist_pct) < 2.0:
            risk = RiskLevel.MEDIUM
        else:
            risk = RiskLevel.LOW
        
        if gamma_env == GammaEnvironment.NEGATIVE:
            if risk == RiskLevel.LOW:
                risk = RiskLevel.MEDIUM
            elif risk == RiskLevel.MEDIUM:
                risk = RiskLevel.HIGH
        
        return risk
    
    def generate_scenarios(self) -> List[Dict]:
        """生成情景分析"""
        gamma_env, _, _ = self.determine_gamma_environment()
        
        zg = self.levels.get('zero_gamma', 0) or self.levels.get('hedge_wall', self.current_price)
        cw = self.levels.get('call_wall', self.current_price + 10)
        pw = self.levels.get('put_wall', self.current_price - 15)
        price = self.current_price
        
        if gamma_env == GammaEnvironment.POSITIVE:
            return [
                {
                    "name": "区间震荡",
                    "probability": 55,
                    "description": f"在 {zg:.0f}-{cw:.0f} 区间震荡",
                    "strategy": "支撑做多，阻力获利"
                },
                {
                    "name": "冲高回落",
                    "probability": 30,
                    "description": f"冲击 {cw:.0f} Call Wall 后回落",
                    "strategy": "不追Call Wall突破"
                },
                {
                    "name": "下探反弹",
                    "probability": 15,
                    "description": f"下探 {zg:.0f} Zero Gamma 后反弹",
                    "strategy": "Zero Gamma是做多机会"
                }
            ]
        else:
            return [
                {
                    "name": "继续下跌",
                    "probability": 50,
                    "description": f"测试 {pw:.0f} Put Wall",
                    "strategy": "不抄底，等Put Wall"
                },
                {
                    "name": "反弹受阻",
                    "probability": 35,
                    "description": f"反弹至 {zg:.0f} Zero Gamma 受阻",
                    "strategy": "反弹不追，观察能否站稳ZG"
                },
                {
                    "name": "站回正Gamma",
                    "probability": 15,
                    "description": f"强势站稳 {zg:.0f} 上方",
                    "strategy": "需利好催化，确认后可做多"
                }
            ]
    
    def get_trading_signals(self) -> Dict:
        """获取交易信号"""
        gamma_env, _, _ = self.determine_gamma_environment()
        
        zg = self.levels.get('zero_gamma', 0) or self.levels.get('hedge_wall', 0)
        cw = self.levels.get('call_wall', 0)
        pw = self.levels.get('put_wall', 0)
        
        if gamma_env == GammaEnvironment.POSITIVE:
            return {
                "long_entry": zg if zg else None,
                "long_desc": "Zero Gamma支撑",
                "short_entry": cw if cw else None,
                "short_desc": "Call Wall阻力",
                "stop_loss": (zg - 3) if zg else None,
                "target": cw
            }
        else:
            return {
                "long_entry": pw if pw else None,
                "long_desc": "Put Wall强支撑",
                "short_entry": zg if zg else None,
                "short_desc": "Zero Gamma(变阻力)",
                "stop_loss": (zg + 2) if zg else None,
                "target": pw
            }
    
    def get_full_analysis(self) -> Dict:
        """获取完整分析结果"""
        gamma_env, dist, dist_pct = self.determine_gamma_environment()
        delta_bias, delta_msg = self.analyze_delta_ratio()
        gamma_bias, gamma_msg = self.analyze_gamma_ratio()
        vol_level, vol_msg = self.analyze_volume_ratio()
        hedge_msg = self.analyze_hedge_wall()
        exp_concentrated, exp_msg = self.analyze_next_exp_concentration()
        implied_low, implied_high = self.calculate_implied_range()
        risk = self.get_risk_level()
        scenarios = self.generate_scenarios()
        signals = self.get_trading_signals()
        
        return {
            "ticker": self.ticker,
            "current_price": self.current_price,
            "previous_close": self.previous_close,
            "levels": self.levels,
            "indicators": self.indicators,
            
            # Gamma环境
            "gamma_environment": gamma_env,
            "distance_to_zg": dist,
            "distance_to_zg_pct": dist_pct,
            
            # 方向分析
            "delta_bias": delta_bias,
            "delta_msg": delta_msg,
            "gamma_bias": gamma_bias,
            "gamma_msg": gamma_msg,
            "volume_level": vol_level,
            "volume_msg": vol_msg,
            "hedge_wall_msg": hedge_msg,
            "exp_concentrated": exp_concentrated,
            "exp_msg": exp_msg,
            
            # 波动预测
            "implied_low": implied_low,
            "implied_high": implied_high,
            
            # 风险和信号
            "risk_level": risk,
            "scenarios": scenarios,
            "signals": signals,
        }


# ============================================================
# 高级分析函数
# ============================================================

def generate_full_analysis(df: pd.DataFrame, tickers: List[str] = None, prices: Dict[str, float] = None) -> Dict:
    """
    生成完整的SpotGamma分析
    
    Args:
        df: SpotGamma CSV DataFrame
        tickers: 要分析的股票列表，默认 ['QQQ', 'SPY']
        prices: 当前价格字典，如 {'QQQ': 520.5, 'SPY': 580.2}
    
    Returns:
        包含所有分析结果的字典
    """
    if tickers is None:
        tickers = ['QQQ', 'SPY']
    
    if prices is None:
        prices = {}
    
    results = {}
    
    for ticker in tickers:
        analyzer = SpotGammaAnalyzer(ticker)
        price = prices.get(ticker, 0)
        
        if price:
            analyzer.load_from_csv(df, price)
            results[ticker] = analyzer.get_full_analysis()
        else:
            # 尝试从CSV获取价格
            levels, _ = extract_stock_data(df, ticker)
            if levels:
                # 使用hedge_wall作为近似价格
                approx_price = levels.get('hedge_wall', 0) or levels.get('key_gamma_strike', 0)
                if approx_price:
                    analyzer.load_from_csv(df, approx_price)
                    results[ticker] = analyzer.get_full_analysis()
    
    return results


# ============================================================
# Streamlit 渲染函数
# ============================================================

def render_spotgamma_section(df: pd.DataFrame, st_module, prices: Dict[str, float] = None) -> Dict:
    """
    渲染SpotGamma分析部分
    
    Args:
        df: SpotGamma CSV DataFrame
        st_module: streamlit模块
        prices: 当前价格字典
    
    Returns:
        分析结果字典
    """
    st = st_module
    
    # 获取价格输入
    if prices is None:
        prices = {}
    
    col_p1, col_p2, col_p3 = st.columns(3)
    with col_p1:
        qqq_price = st.number_input("QQQ 当前价格", value=prices.get('QQQ', 520.0), step=0.01, key="sg_qqq_price")
        prices['QQQ'] = qqq_price
    with col_p2:
        spy_price = st.number_input("SPY 当前价格", value=prices.get('SPY', 580.0), step=0.01, key="sg_spy_price")
        prices['SPY'] = spy_price
    with col_p3:
        # 日历效应
        is_data_day = st.checkbox("今日有重要数据?", key="sg_data_day")
        data_event = st.text_input("数据事件", placeholder="CPI/PPI/FOMC", key="sg_event")
    
    # 手动输入Zero Gamma（CSV可能没有）
    with st.expander("📝 手动输入关键位置 (可选)", expanded=False):
        st.caption("如果CSV中没有Zero Gamma等位置，可在此手动输入")
        mcol1, mcol2, mcol3, mcol4 = st.columns(4)
        with mcol1:
            manual_zg_qqq = st.number_input("QQQ Zero Gamma", value=0.0, step=0.5, key="manual_zg_qqq")
        with mcol2:
            manual_cw_qqq = st.number_input("QQQ Call Wall", value=0.0, step=0.5, key="manual_cw_qqq")
        with mcol3:
            manual_pw_qqq = st.number_input("QQQ Put Wall", value=0.0, step=0.5, key="manual_pw_qqq")
        with mcol4:
            manual_vt_qqq = st.number_input("QQQ Vol Trigger", value=0.0, step=0.5, key="manual_vt_qqq")
    
    # 分析主要标的
    analysis_results = {}
    
    for ticker in ['QQQ', 'SPY']:
        analyzer = SpotGammaAnalyzer(ticker)
        price = prices.get(ticker, 0)
        
        if price:
            analyzer.load_from_csv(df, price)
            analyzer.is_data_day = is_data_day
            analyzer.data_event = data_event
            
            # 应用手动输入的位置
            if ticker == 'QQQ':
                analyzer.set_manual_levels(
                    zero_gamma=manual_zg_qqq if manual_zg_qqq > 0 else 0,
                    call_wall=manual_cw_qqq if manual_cw_qqq > 0 else 0,
                    put_wall=manual_pw_qqq if manual_pw_qqq > 0 else 0,
                    volatility_trigger=manual_vt_qqq if manual_vt_qqq > 0 else 0
                )
            
            result = analyzer.get_full_analysis()
            analysis_results[ticker] = result
    
    # 渲染QQQ分析
    if 'QQQ' in analysis_results:
        render_single_stock_analysis(st, analysis_results['QQQ'], expanded=True)
    
    # 渲染SPY分析（折叠）
    if 'SPY' in analysis_results:
        with st.expander("📊 SPY Gamma分析", expanded=False):
            render_single_stock_analysis(st, analysis_results['SPY'], expanded=False, show_header=False)
    
    # 显示完整数据表
    with st.expander("📋 完整数据表", expanded=False):
        st.dataframe(df, use_container_width=True, height=400)
    
    return analysis_results


def render_single_stock_analysis(st, result: Dict, expanded: bool = True, show_header: bool = True):
    """渲染单只股票的分析"""
    
    ticker = result['ticker']
    gamma_env = result['gamma_environment']
    
    if show_header:
        # Gamma环境大标题
        if gamma_env == GammaEnvironment.POSITIVE:
            st.success(f"🟢 **{ticker} 正 Gamma 环境** | 距 Zero Gamma: ${result['distance_to_zg']:.2f} ({result['distance_to_zg_pct']:.2f}%)")
        elif gamma_env == GammaEnvironment.NEGATIVE:
            st.error(f"🔴 **{ticker} 负 Gamma 环境** | 距 Zero Gamma: ${result['distance_to_zg']:.2f} ({result['distance_to_zg_pct']:.2f}%)")
        else:
            st.info(f"⚪ **{ticker} Gamma环境**: 数据不足")
    
    # 核心指标卡片
    col1, col2, col3, col4 = st.columns(4)
    
    indicators = result['indicators']
    
    with col1:
        delta_color = "normal" if result['delta_bias'] == MarketBias.BULLISH else "inverse" if result['delta_bias'] == MarketBias.BEARISH else "off"
        st.metric("Delta Ratio", f"{indicators.delta_ratio:.2f}", delta=result['delta_bias'].value, delta_color=delta_color)
    
    with col2:
        gamma_color = "normal" if result['gamma_bias'] == MarketBias.BULLISH else "inverse" if result['gamma_bias'] == MarketBias.BEARISH else "off"
        st.metric("Gamma Ratio", f"{indicators.gamma_ratio:.2f}", delta=result['gamma_bias'].value, delta_color=gamma_color)
    
    with col3:
        st.metric("Implied Move", f"${indicators.options_implied_move:.2f}")
    
    with col4:
        risk = result['risk_level']
        risk_delta = "⚠️" if risk in [RiskLevel.HIGH, RiskLevel.EXTREME] else ""
        st.metric("风险等级", risk.value, delta=risk_delta)
    
    # 关键位置
    st.markdown("#### 📍 关键位置")
    levels = result['levels']
    
    level_cols = st.columns(5)
    level_items = [
        ('Zero Gamma / Hedge Wall', levels.get('zero_gamma', 0) or levels.get('hedge_wall', 0)),
        ('Call Wall', levels.get('call_wall', 0)),
        ('Put Wall', levels.get('put_wall', 0)),
        ('Key Gamma Strike', levels.get('key_gamma_strike', 0)),
        ('Key Delta Strike', levels.get('key_delta_strike', 0)),
    ]
    
    for i, (name, value) in enumerate(level_items):
        with level_cols[i]:
            if value:
                # 计算与当前价格的距离
                dist = value - result['current_price']
                dist_str = f"+{dist:.1f}" if dist > 0 else f"{dist:.1f}"
                st.metric(name, f"${value:.0f}", delta=dist_str)
            else:
                st.metric(name, "N/A")
    
    # 方向性分析
    st.markdown("#### 📈 方向性分析")
    
    analysis_cols = st.columns(2)
    
    with analysis_cols[0]:
        st.markdown(f"- {result['delta_msg']}")
        st.markdown(f"- {result['gamma_msg']}")
        st.markdown(f"- {result['volume_msg']}")
    
    with analysis_cols[1]:
        st.markdown(f"- {result['hedge_wall_msg']}")
        st.markdown(f"- {result['exp_msg']}")
        
        # IV vs RV
        iv = indicators.one_month_iv
        rv = indicators.one_month_rv
        if iv and rv:
            iv_rv_diff = iv - rv
            if iv_rv_diff > 5:
                st.markdown(f"- IV {iv:.1f}% > RV {rv:.1f}%: 期权偏贵")
            elif iv_rv_diff < -5:
                st.markdown(f"- IV {iv:.1f}% < RV {rv:.1f}%: 期权便宜")
            else:
                st.markdown(f"- IV {iv:.1f}% ≈ RV {rv:.1f}%: 定价合理")
    
    # 情景分析
    st.markdown("#### 🔮 情景分析")
    
    scenario_cols = st.columns(len(result['scenarios']))
    for i, scenario in enumerate(result['scenarios']):
        with scenario_cols[i]:
            st.markdown(f"**{scenario['name']}** ({scenario['probability']}%)")
            st.caption(scenario['description'])
            st.markdown(f"*策略: {scenario['strategy']}*")
    
    # 操作建议
    st.markdown("#### 💡 操作建议")
    
    if gamma_env == GammaEnvironment.POSITIVE:
        st.info("**正 Gamma 铁律:** ❌不追Call Wall突破 | ✅Zero Gamma是支撑 | ✅预期均值回归")
    elif gamma_env == GammaEnvironment.NEGATIVE:
        st.warning("**负 Gamma 铁律:** ❌不在ZG下方抄底 | ❌ZG现在是阻力 | ✅等Put Wall或站回ZG")
    
    signals = result['signals']
    sig_cols = st.columns(3)
    
    with sig_cols[0]:
        if signals.get('long_entry'):
            st.success(f"做多观察: ${signals['long_entry']:.0f}\n({signals['long_desc']})")
    
    with sig_cols[1]:
        if signals.get('short_entry'):
            st.error(f"做空观察: ${signals['short_entry']:.0f}\n({signals['short_desc']})")
    
    with sig_cols[2]:
        if signals.get('stop_loss'):
            st.warning(f"止损参考: ${signals['stop_loss']:.0f}")


# ============================================================
# 工具函数
# ============================================================

def get_gamma_summary(analysis: Dict) -> str:
    """生成Gamma分析摘要文本"""
    if not analysis:
        return "无分析数据"
    
    lines = []
    
    for ticker, result in analysis.items():
        gamma_env = result['gamma_environment']
        env_str = "正Gamma" if gamma_env == GammaEnvironment.POSITIVE else "负Gamma" if gamma_env == GammaEnvironment.NEGATIVE else "中性"
        
        lines.append(f"## {ticker} Gamma分析")
        lines.append(f"- 环境: {env_str}")
        lines.append(f"- 距Zero Gamma: ${result['distance_to_zg']:.2f} ({result['distance_to_zg_pct']:.2f}%)")
        lines.append(f"- Delta Ratio: {result['indicators'].delta_ratio:.2f} ({result['delta_bias'].value})")
        lines.append(f"- Gamma Ratio: {result['indicators'].gamma_ratio:.2f} ({result['gamma_bias'].value})")
        lines.append(f"- Implied Move: ${result['indicators'].options_implied_move:.2f}")
        lines.append(f"- 风险等级: {result['risk_level'].value}")
        
        levels = result['levels']
        lines.append(f"- Call Wall: ${levels.get('call_wall', 0):.0f}")
        lines.append(f"- Put Wall: ${levels.get('put_wall', 0):.0f}")
        lines.append(f"- Zero Gamma: ${levels.get('zero_gamma', 0) or levels.get('hedge_wall', 0):.0f}")
        
        lines.append("")
    
    return "\n".join(lines)
