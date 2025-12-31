"""
宏观战情室 V2 - 指标计算模块
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from config import (
    ZSCORE_WINDOWS, TREND_MA_PERIODS, RS_PERIOD,
    SECTOR_PAIRS, CURRENT_FED_RATE, CURRENT_BOJ_RATE,
    ALERT_THRESHOLDS, get_zscore_signal
)


class IndicatorCalculator:
    """指标计算器"""
    
    def __init__(self, all_data):
        self.fred = all_data.get('fred', pd.DataFrame())
        self.yahoo = all_data.get('yahoo', pd.DataFrame())
        self.akshare = all_data.get('akshare', pd.DataFrame())
        
    # ==================== 基础计算函数 ====================
    
    def calc_zscore(self, series, window=60):
        """计算Z-Score"""
        if series is None or len(series) < window:
            return pd.Series(index=series.index if series is not None else [])
        rolling_mean = series.rolling(window).mean()
        rolling_std = series.rolling(window).std()
        return (series - rolling_mean) / rolling_std
    
    def calc_percentile(self, series, window=252):
        """计算历史百分位"""
        if series is None or len(series) < window:
            return pd.Series(index=series.index if series is not None else [])
        return series.rolling(window).apply(
            lambda x: pd.Series(x).rank(pct=True).iloc[-1] * 100, 
            raw=False
        )
    
    def calc_trend(self, series, fast=20, slow=50):
        """计算趋势状态"""
        if series is None or len(series) < slow:
            return None
            
        ma_fast = series.rolling(fast).mean()
        ma_slow = series.rolling(slow).mean()
        
        latest = series.iloc[-1]
        ma_fast_latest = ma_fast.iloc[-1]
        ma_slow_latest = ma_slow.iloc[-1]
        
        if latest > ma_fast_latest > ma_slow_latest:
            return '上行', '🟢'
        elif latest < ma_fast_latest < ma_slow_latest:
            return '下行', '🔴'
        else:
            return '震荡', '🟡'
    
    def calc_relative_strength(self, asset, benchmark, period=20):
        """计算相对强度"""
        if asset is None or benchmark is None:
            return None
        
        # 对齐索引
        common_idx = asset.index.intersection(benchmark.index)
        if len(common_idx) < period:
            return None
            
        asset = asset.loc[common_idx]
        benchmark = benchmark.loc[common_idx]
        
        # 相对强度 = 资产/基准 的变化率
        ratio = asset / benchmark
        rs = ratio.pct_change(period) * 100  # 百分比
        return rs
    
    def calc_momentum(self, series, period=20):
        """计算动量"""
        if series is None or len(series) < period:
            return None
        return series.pct_change(period) * 100
    
    # ==================== 流动性指标 ====================
    
    def calc_liquidity_indicators(self):
        """计算流动性指标"""
        results = {}
        
        # 净流动性 = Fed资产负债表 - RRP - TGA
        if all(col in self.fred.columns for col in ['WALCL', 'RRPONTSYD', 'WTREGEN']):
            walcl = self.fred['WALCL'] / 1000  # 转换为万亿
            rrp = self.fred['RRPONTSYD'] / 1000
            tga = self.fred['WTREGEN'] / 1000000  # TGA单位是百万
            
            net_liq = walcl - rrp - tga
            net_liq = net_liq.dropna()
            
            if len(net_liq) > 0:
                results['net_liquidity'] = {
                    'series': net_liq,
                    'latest': net_liq.iloc[-1],
                    'z_60d': self.calc_zscore(net_liq, 60).iloc[-1] if len(net_liq) > 60 else np.nan,
                    'z_252d': self.calc_zscore(net_liq, 252).iloc[-1] if len(net_liq) > 252 else np.nan,
                    'pct_252d': self.calc_percentile(net_liq, 252).iloc[-1] if len(net_liq) > 252 else np.nan,
                    'change_20d': self.calc_momentum(net_liq, 20).iloc[-1] if len(net_liq) > 20 else np.nan,
                }
        
        # RRP
        if 'RRPONTSYD' in self.fred.columns:
            rrp = self.fred['RRPONTSYD']
            rrp = rrp.dropna()
            if len(rrp) > 1:
                results['rrp'] = {
                    'latest': rrp.iloc[-1],
                    'change_1d': rrp.iloc[-1] - rrp.iloc[-2] if len(rrp) > 1 else 0,
                    'z_60d': self.calc_zscore(rrp, 60).iloc[-1] if len(rrp) > 60 else np.nan,
                }
        
        # TGA
        if 'WTREGEN' in self.fred.columns:
            tga = self.fred['WTREGEN'] / 1000  # 转换为十亿
            tga = tga.dropna()
            if len(tga) > 1:
                results['tga'] = {
                    'latest': tga.iloc[-1],
                    'change_1d': tga.iloc[-1] - tga.iloc[-2] if len(tga) > 1 else 0,
                    'z_60d': self.calc_zscore(tga, 60).iloc[-1] if len(tga) > 60 else np.nan,
                }
        
        # SOFR (利率数据可能不在FRED中)
        if 'SOFR' in self.fred.columns:
            sofr = self.fred['SOFR'].dropna()
            if len(sofr) > 0:
                results['sofr'] = {
                    'latest': sofr.iloc[-1],
                }
        
        # HYG/LQD 信用风险偏好
        if all(col in self.yahoo.columns for col in ['HYG', 'LQD']):
            hyg = self.yahoo['HYG']
            lqd = self.yahoo['LQD']
            hyg_lqd = (hyg / lqd).dropna()
            
            if len(hyg_lqd) > 0:
                results['hyg_lqd'] = {
                    'series': hyg_lqd,
                    'latest': hyg_lqd.iloc[-1],
                    'z_60d': self.calc_zscore(hyg_lqd, 60).iloc[-1] if len(hyg_lqd) > 60 else np.nan,
                    'change_1d': hyg_lqd.pct_change().iloc[-1] * 100 if len(hyg_lqd) > 1 else np.nan,
                }
        
        return results
    
    # ==================== 货币/利率指标 ====================
    
    def calc_currency_indicators(self):
        """计算货币和利率指标"""
        results = {}
        
        # DXY
        dxy_col = 'DX-Y.NYB'
        if dxy_col in self.yahoo.columns:
            dxy = self.yahoo[dxy_col].dropna()
            if len(dxy) > 0:
                trend_state, trend_emoji = self.calc_trend(dxy) or ('N/A', '⚪')
                results['dxy'] = {
                    'series': dxy,
                    'latest': dxy.iloc[-1],
                    'trend': trend_state,
                    'trend_emoji': trend_emoji,
                    'z_60d': self.calc_zscore(dxy, 60).iloc[-1] if len(dxy) > 60 else np.nan,
                    'change_20d': self.calc_momentum(dxy, 20).iloc[-1] if len(dxy) > 20 else np.nan,
                }
        
        # USDJPY
        usdjpy_col = 'JPY=X'
        if usdjpy_col in self.yahoo.columns:
            usdjpy = self.yahoo[usdjpy_col].dropna()
            if len(usdjpy) > 0:
                trend_state, trend_emoji = self.calc_trend(usdjpy) or ('N/A', '⚪')
                momentum = self.calc_momentum(usdjpy, 20)
                
                # Carry Trade风险评估
                # USDJPY下降（日元走强）= Carry平仓风险上升
                carry_risk = '低'
                if momentum is not None and len(momentum) > 0:
                    mom_val = momentum.iloc[-1]
                    if mom_val < -3:
                        carry_risk = '高'
                    elif mom_val < -1:
                        carry_risk = '中'
                
                results['usdjpy'] = {
                    'series': usdjpy,
                    'latest': usdjpy.iloc[-1],
                    'trend': trend_state,
                    'trend_emoji': trend_emoji,
                    'z_60d': self.calc_zscore(usdjpy, 60).iloc[-1] if len(usdjpy) > 60 else np.nan,
                    'change_20d': momentum.iloc[-1] if momentum is not None and len(momentum) > 0 else np.nan,
                    'carry_risk': carry_risk,
                }
        
        # 10Y收益率
        if 'DGS10' in self.fred.columns:
            dgs10 = self.fred['DGS10'].dropna()
            if len(dgs10) > 0:
                results['dgs10'] = {
                    'latest': dgs10.iloc[-1],
                    'z_60d': self.calc_zscore(dgs10, 60).iloc[-1] if len(dgs10) > 60 else np.nan,
                }
        
        # 3M收益率
        if 'DGS3MO' in self.fred.columns:
            dgs3mo = self.fred['DGS3MO'].dropna()
            if len(dgs3mo) > 0:
                results['dgs3mo'] = {
                    'latest': dgs3mo.iloc[-1],
                }
        
        # 期限利差 10Y-3M
        if 'DGS10' in self.fred.columns and 'DGS3MO' in self.fred.columns:
            spread = (self.fred['DGS10'] - self.fred['DGS3MO']).dropna()
            if len(spread) > 0:
                # 曲线形态判断
                latest_spread = spread.iloc[-1]
                if latest_spread < -0.5:
                    curve_shape = '深度倒挂'
                elif latest_spread < 0:
                    curve_shape = '倒挂'
                elif latest_spread < 0.5:
                    curve_shape = '平坦'
                else:
                    curve_shape = '陡峭'
                    
                results['term_spread'] = {
                    'series': spread,
                    'latest': latest_spread,
                    'curve_shape': curve_shape,
                    'z_60d': self.calc_zscore(spread, 60).iloc[-1] if len(spread) > 60 else np.nan,
                }
        
        # 实际利率 = 10Y - 10Y BEI
        if 'DGS10' in self.fred.columns and 'T10YIE' in self.fred.columns:
            real_rate = (self.fred['DGS10'] - self.fred['T10YIE']).dropna()
            if len(real_rate) > 0:
                trend_state, trend_emoji = self.calc_trend(real_rate) or ('N/A', '⚪')
                results['real_rate'] = {
                    'series': real_rate,
                    'latest': real_rate.iloc[-1],
                    'trend': trend_state,
                    'trend_emoji': trend_emoji,
                    'z_60d': self.calc_zscore(real_rate, 60).iloc[-1] if len(real_rate) > 60 else np.nan,
                }
        
        # VIX
        if '^VIX' in self.yahoo.columns:
            vix = self.yahoo['^VIX'].dropna()
            if len(vix) > 0:
                results['vix'] = {
                    'latest': vix.iloc[-1],
                    'z_60d': self.calc_zscore(vix, 60).iloc[-1] if len(vix) > 60 else np.nan,
                }
        
        # ==================== 央行政策代理指标 ====================
        
        # 获取当前Fed利率 (优先使用FRED DFF数据)
        current_fed_rate = CURRENT_FED_RATE  # 默认值
        if 'DFF' in self.fred.columns:
            dff = self.fred['DFF'].dropna()
            if len(dff) > 0:
                current_fed_rate = dff.iloc[-1]
                print(f"✓ 使用FRED实时Fed利率: {current_fed_rate:.2f}%")
        
        # Fed政策预期: 2Y国债 vs 当前Fed利率
        if 'DGS2' in self.fred.columns:
            dgs2 = self.fred['DGS2'].dropna()
            if len(dgs2) > 0:
                fed_policy_signal = dgs2.iloc[-1] - current_fed_rate
                # 负值越大 = 市场定价越多降息
                if fed_policy_signal < -0.75:
                    fed_outlook = '鸽派 (市场预期多次降息)'
                elif fed_policy_signal < -0.25:
                    fed_outlook = '偏鸽 (市场预期降息)'
                elif fed_policy_signal > 0.25:
                    fed_outlook = '偏鹰 (市场预期加息)'
                else:
                    fed_outlook = '中性'
                    
                results['fed_policy'] = {
                    'dgs2': dgs2.iloc[-1],
                    'signal': fed_policy_signal,
                    'outlook': fed_outlook,
                    'current_rate': current_fed_rate,
                }
        
        # BOJ政策预期: 用USDJPY动量作为代理
        if 'usdjpy' in results:
            usdjpy_mom = results['usdjpy'].get('change_20d', 0)
            if usdjpy_mom is not None and not np.isnan(usdjpy_mom):
                # 日元走强（USDJPY下降）= 市场预期BOJ更鹰/Fed更鸽
                if usdjpy_mom < -3:
                    boj_outlook = '鹰派信号 (日元走强)'
                elif usdjpy_mom < -1:
                    boj_outlook = '偏鹰 (日元小幅走强)'
                elif usdjpy_mom > 3:
                    boj_outlook = '鸽派信号 (日元走弱)'
                else:
                    boj_outlook = '中性'
            else:
                boj_outlook = 'N/A'
                
            results['boj_policy'] = {
                'usdjpy_momentum': usdjpy_mom,
                'outlook': boj_outlook,
                'current_rate': CURRENT_BOJ_RATE,
            }
        
        return results
    
    # ==================== 全球轮动指标 ====================
    
    def calc_rotation_indicators(self):
        """计算全球资产轮动指标"""
        results = {
            'rankings': [],
            'extreme_sentiment': {},
        }
        
        # 基准: SPY
        if 'SPY' not in self.yahoo.columns:
            return results
            
        spy = self.yahoo['SPY'].dropna()
        
        # 计算各资产对SPY的相对强度
        assets = {
            'GLD': '黄金',
            'SLV': '白银', 
            'CPER': '铜',
            'DBC': '商品',
            'USO': '原油',
            'EEM': '新兴市场',
            'EWH': '港股',
            'FXI': '中国大盘',
            'IWM': '小盘股',
        }
        
        for ticker, name in assets.items():
            if ticker in self.yahoo.columns:
                asset = self.yahoo[ticker].dropna()
                rs = self.calc_relative_strength(asset, spy, RS_PERIOD)
                
                if rs is not None and len(rs) > 0:
                    rs_z = self.calc_zscore(rs, 60)
                    if len(rs_z) > 0 and not np.isnan(rs_z.iloc[-1]):
                        z_val = rs_z.iloc[-1]
                        emoji, signal = get_zscore_signal(z_val)
                        
                        results['rankings'].append({
                            'ticker': ticker,
                            'name': name,
                            'rs': rs.iloc[-1],
                            'z': z_val,
                            'emoji': emoji,
                            'signal': signal,
                        })
        
        # 添加A股/港股指数
        if not self.akshare.empty:
            for col in self.akshare.columns:
                if col in ['sh000300', 'HSI']:
                    name = '沪深300' if col == 'sh000300' else '恒生指数'
                    asset = self.akshare[col].dropna()
                    
                    # 对齐到SPY的交易日
                    common_idx = asset.index.intersection(spy.index)
                    if len(common_idx) > RS_PERIOD:
                        asset_aligned = asset.loc[common_idx]
                        spy_aligned = spy.loc[common_idx]
                        rs = self.calc_relative_strength(asset_aligned, spy_aligned, RS_PERIOD)
                        
                        if rs is not None and len(rs) > 0:
                            rs_z = self.calc_zscore(rs, 60)
                            if len(rs_z) > 0 and not np.isnan(rs_z.iloc[-1]):
                                z_val = rs_z.iloc[-1]
                                emoji, signal = get_zscore_signal(z_val)
                                
                                results['rankings'].append({
                                    'ticker': col,
                                    'name': name,
                                    'rs': rs.iloc[-1],
                                    'z': z_val,
                                    'emoji': emoji,
                                    'signal': signal,
                                })
        
        # 按Z-Score排序
        results['rankings'] = sorted(results['rankings'], key=lambda x: x['z'], reverse=True)
        
        # 极端情绪指标
        extreme_tickers = {
            'BTC-USD': '比特币',
            'ARKK': 'ARK创新',
        }
        
        for ticker, name in extreme_tickers.items():
            if ticker in self.yahoo.columns:
                asset = self.yahoo[ticker].dropna()
                rs = self.calc_relative_strength(asset, spy, RS_PERIOD)
                
                if rs is not None and len(rs) > 0:
                    rs_z = self.calc_zscore(rs, 60)
                    if len(rs_z) > 0 and not np.isnan(rs_z.iloc[-1]):
                        z_val = rs_z.iloc[-1]
                        
                        # 情绪解读
                        if z_val > 1.5:
                            sentiment = '投机狂热'
                        elif z_val > 0.5:
                            sentiment = '风险偏好上升'
                        elif z_val < -1.5:
                            sentiment = '投机冰点'
                        elif z_val < -0.5:
                            sentiment = '风险偏好下降'
                        else:
                            sentiment = '中性'
                        
                        results['extreme_sentiment'][ticker] = {
                            'name': name,
                            'z': z_val,
                            'sentiment': sentiment,
                        }
        
        return results
    
    # ==================== 美股结构指标 ====================
    
    def calc_us_structure_indicators(self):
        """计算美股内部结构指标"""
        results = {
            'risk_appetite': [],
            'sector_rotation': [],
            'breadth': [],
        }
        
        for category, pairs in SECTOR_PAIRS.items():
            for pair_key, (ticker1, ticker2, name) in pairs.items():
                if ticker1 in self.yahoo.columns and ticker2 in self.yahoo.columns:
                    asset1 = self.yahoo[ticker1].dropna()
                    asset2 = self.yahoo[ticker2].dropna()
                    
                    # 计算比率
                    common_idx = asset1.index.intersection(asset2.index)
                    if len(common_idx) > 60:
                        ratio = asset1.loc[common_idx] / asset2.loc[common_idx]
                        ratio_z = self.calc_zscore(ratio, 60)
                        
                        if len(ratio_z) > 0 and not np.isnan(ratio_z.iloc[-1]):
                            z_val = ratio_z.iloc[-1]
                            emoji, signal = get_zscore_signal(z_val)
                            
                            results[category].append({
                                'pair': pair_key,
                                'name': name,
                                'z': z_val,
                                'emoji': emoji,
                                'signal': signal,
                            })
        
        return results
    
    # ==================== 汇总计算 ====================
    
    def calc_all_indicators(self):
        """计算所有指标"""
        return {
            'liquidity': self.calc_liquidity_indicators(),
            'currency': self.calc_currency_indicators(),
            'rotation': self.calc_rotation_indicators(),
            'us_structure': self.calc_us_structure_indicators(),
        }


if __name__ == '__main__':
    from data_fetcher import fetch_data
    
    # 获取数据
    all_data = fetch_data()
    
    # 计算指标
    calc = IndicatorCalculator(all_data)
    indicators = calc.calc_all_indicators()
    
    print("\n指标计算完成:")
    for category, data in indicators.items():
        print(f"\n{category}:")
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, dict) and 'latest' in value:
                    print(f"  {key}: {value['latest']:.2f}")
                elif isinstance(value, list):
                    print(f"  {key}: {len(value)} items")
