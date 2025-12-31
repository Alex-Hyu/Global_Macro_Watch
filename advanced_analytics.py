"""
宏观战情室 V2 - 高级分析模块
包含：RS动量、轮动热力图、领先指标、相关性监控、经济周期定位
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from config import ZSCORE_WINDOWS


class AdvancedAnalytics:
    """高级分析器"""
    
    def __init__(self, all_data):
        self.fred = all_data.get('fred', pd.DataFrame())
        self.yahoo = all_data.get('yahoo', pd.DataFrame())
        self.akshare = all_data.get('akshare', pd.DataFrame())
    
    # ==================== 基础计算 ====================
    
    def calc_zscore(self, series, window=60):
        """计算Z-Score"""
        if series is None or len(series) < window:
            return pd.Series(index=series.index if series is not None else [])
        rolling_mean = series.rolling(window).mean()
        rolling_std = series.rolling(window).std()
        z = (series - rolling_mean) / rolling_std
        return z
    
    def calc_rolling_corr(self, series1, series2, window=60):
        """计算滚动相关性"""
        if series1 is None or series2 is None:
            return None
        # 对齐索引
        common_idx = series1.index.intersection(series2.index)
        if len(common_idx) < window:
            return None
        s1 = series1.loc[common_idx]
        s2 = series2.loc[common_idx]
        return s1.rolling(window).corr(s2)
    
    # ==================== P0-1: RS动量（动量的动量） ====================
    
    def calc_rs_momentum(self, momentum_period=5):
        """
        计算相对强度的动量
        返回各资产的RS水平和RS变化速度
        """
        results = []
        
        if 'SPY' not in self.yahoo.columns:
            return results
        
        spy = self.yahoo['SPY'].dropna()
        
        # 要分析的资产
        assets = {
            'GLD': '黄金',
            'SLV': '白银',
            'CPER': '铜',
            'DBC': '商品',
            'EEM': '新兴市场',
            'EWH': '港股',
            'FXI': '中国大盘',
            'IWM': '小盘股',
            'QQQ': '纳斯达克',
            'XLF': '金融',
            'XLE': '能源',
            'TLT': '长期国债',
            'BTC-USD': '比特币',
            'ARKK': 'ARK创新',
        }
        
        for ticker, name in assets.items():
            if ticker not in self.yahoo.columns:
                continue
                
            asset = self.yahoo[ticker].dropna()
            common_idx = asset.index.intersection(spy.index)
            
            if len(common_idx) < 70:  # 需要足够数据计算Z-Score和动量
                continue
            
            asset = asset.loc[common_idx]
            spy_aligned = spy.loc[common_idx]
            
            # 计算相对强度
            rs = asset / spy_aligned
            rs_z = self.calc_zscore(rs, 60)
            
            if len(rs_z.dropna()) < momentum_period + 1:
                continue
            
            # 当前RS Z-Score
            current_rs_z = rs_z.iloc[-1]
            
            # RS Z-Score的变化（动量）
            rs_z_change = rs_z.iloc[-1] - rs_z.iloc[-momentum_period-1]
            
            # 判断状态
            if current_rs_z > 0 and rs_z_change > 0:
                status = '🚀 加速上涨'
                status_code = 'accelerating_up'
            elif current_rs_z > 0 and rs_z_change < 0:
                status = '⚠️ 上涨减速'
                status_code = 'decelerating_up'
            elif current_rs_z < 0 and rs_z_change > 0:
                status = '🔄 下跌减速'
                status_code = 'decelerating_down'
            else:
                status = '📉 加速下跌'
                status_code = 'accelerating_down'
            
            results.append({
                'ticker': ticker,
                'name': name,
                'rs_z': current_rs_z,
                'rs_momentum': rs_z_change,
                'status': status,
                'status_code': status_code,
            })
        
        # 按RS动量排序
        results = sorted(results, key=lambda x: x['rs_momentum'], reverse=True)
        
        return results
    
    # ==================== P0-2: 轮动热力图 ====================
    
    def calc_rotation_heatmap(self, weeks=12):
        """
        计算过去N周的RS Z-Score热力图
        """
        if 'SPY' not in self.yahoo.columns:
            return None, []
        
        spy = self.yahoo['SPY'].dropna()
        
        # 资产列表
        assets = {
            'GLD': '黄金',
            'SLV': '白银',
            'CPER': '铜',
            'DBC': '商品',
            'EEM': '新兴市场',
            'FXI': '中国',
            'IWM': '小盘股',
            'QQQ': '纳指',
            'TLT': '长债',
            'BTC-USD': 'BTC',
        }
        
        # 计算每周末的RS Z-Score
        heatmap_data = {}
        asset_names = []
        
        for ticker, name in assets.items():
            if ticker not in self.yahoo.columns:
                continue
            
            asset = self.yahoo[ticker].dropna()
            common_idx = asset.index.intersection(spy.index)
            
            if len(common_idx) < 60 + weeks * 5:
                continue
            
            asset = asset.loc[common_idx]
            spy_aligned = spy.loc[common_idx]
            
            # 计算RS Z-Score
            rs = asset / spy_aligned
            rs_z = self.calc_zscore(rs, 60)
            
            # 按周重采样，取每周最后一个值
            weekly_rs_z = rs_z.resample('W').last().dropna()
            
            if len(weekly_rs_z) >= weeks:
                heatmap_data[name] = weekly_rs_z.iloc[-weeks:].values
                if not asset_names:
                    # 获取周标签
                    week_labels = [d.strftime('%m/%d') for d in weekly_rs_z.iloc[-weeks:].index]
        
        if not heatmap_data:
            return None, []
        
        # 转换为DataFrame
        asset_names = list(heatmap_data.keys())
        heatmap_df = pd.DataFrame(heatmap_data).T
        heatmap_df.columns = week_labels if 'week_labels' in dir() else [f'W{i}' for i in range(weeks)]
        
        return heatmap_df, asset_names
    
    # ==================== P1-1: 领先指标仪表盘 ====================
    
    def calc_leading_indicators(self):
        """
        计算领先指标
        """
        results = []
        
        # 1. 铜/金比率 - 领先全球经济/Risk-on
        if all(t in self.yahoo.columns for t in ['CPER', 'GLD']):
            copper = self.yahoo['CPER'].dropna()
            gold = self.yahoo['GLD'].dropna()
            common_idx = copper.index.intersection(gold.index)
            if len(common_idx) > 20:
                ratio = copper.loc[common_idx] / gold.loc[common_idx]
                current = ratio.iloc[-1]
                change_20d = (ratio.iloc[-1] / ratio.iloc[-21] - 1) * 100 if len(ratio) > 21 else 0
                
                if change_20d > 3:
                    signal = '🟢 Risk-on加强'
                elif change_20d < -3:
                    signal = '🔴 Risk-off信号'
                else:
                    signal = '🟡 中性'
                
                results.append({
                    'name': '铜/金比率',
                    'description': '领先全球经济周期',
                    'value': f'{current:.4f}',
                    'change': f'{change_20d:+.1f}%',
                    'signal': signal,
                    'change_val': change_20d,
                })
        
        # 2. 高收益债利差 (HYG vs TLT) - 领先股市风险
        if all(t in self.yahoo.columns for t in ['HYG', 'TLT']):
            hyg = self.yahoo['HYG'].dropna()
            tlt = self.yahoo['TLT'].dropna()
            common_idx = hyg.index.intersection(tlt.index)
            if len(common_idx) > 20:
                # HYG/TLT比率上升 = 信用风险偏好上升
                ratio = hyg.loc[common_idx] / tlt.loc[common_idx]
                current = ratio.iloc[-1]
                change_20d = (ratio.iloc[-1] / ratio.iloc[-21] - 1) * 100 if len(ratio) > 21 else 0
                
                if change_20d > 2:
                    signal = '🟢 信用风险下降'
                elif change_20d < -2:
                    signal = '🔴 信用风险上升'
                else:
                    signal = '🟡 中性'
                
                results.append({
                    'name': 'HYG/TLT比率',
                    'description': '领先股市风险',
                    'value': f'{current:.3f}',
                    'change': f'{change_20d:+.1f}%',
                    'signal': signal,
                    'change_val': change_20d,
                })
        
        # 3. 半导体/纳指 (SMH/QQQ) - 领先科技板块
        if all(t in self.yahoo.columns for t in ['SMH', 'QQQ']):
            smh = self.yahoo['SMH'].dropna()
            qqq = self.yahoo['QQQ'].dropna()
            common_idx = smh.index.intersection(qqq.index)
            if len(common_idx) > 20:
                ratio = smh.loc[common_idx] / qqq.loc[common_idx]
                current = ratio.iloc[-1]
                change_20d = (ratio.iloc[-1] / ratio.iloc[-21] - 1) * 100 if len(ratio) > 21 else 0
                
                if change_20d > 2:
                    signal = '🟢 半导体领涨'
                elif change_20d < -2:
                    signal = '🔴 半导体落后'
                else:
                    signal = '🟡 同步'
                
                results.append({
                    'name': '半导体/纳指',
                    'description': '领先科技板块',
                    'value': f'{current:.3f}',
                    'change': f'{change_20d:+.1f}%',
                    'signal': signal,
                    'change_val': change_20d,
                })
        
        # 4. 2Y国债收益率变化 - 领先Fed政策预期
        if 'DGS2' in self.fred.columns:
            dgs2 = self.fred['DGS2'].dropna()
            if len(dgs2) > 20:
                current = dgs2.iloc[-1]
                change_20d = dgs2.iloc[-1] - dgs2.iloc[-21] if len(dgs2) > 21 else 0
                change_bps = change_20d * 100
                
                if change_bps < -15:
                    signal = '🟢 降息预期升温'
                elif change_bps > 15:
                    signal = '🔴 加息预期升温'
                else:
                    signal = '🟡 预期稳定'
                
                results.append({
                    'name': '2Y国债收益率',
                    'description': '领先Fed政策',
                    'value': f'{current:.2f}%',
                    'change': f'{change_bps:+.0f}bp',
                    'signal': signal,
                    'change_val': change_bps,
                })
        
        # 5. 美元指数变化 - 领先新兴市场/商品
        if 'DX-Y.NYB' in self.yahoo.columns:
            dxy = self.yahoo['DX-Y.NYB'].dropna()
            if len(dxy) > 20:
                current = dxy.iloc[-1]
                change_20d = (dxy.iloc[-1] / dxy.iloc[-21] - 1) * 100 if len(dxy) > 21 else 0
                
                if change_20d < -1.5:
                    signal = '🟢 利好新兴/商品'
                elif change_20d > 1.5:
                    signal = '🔴 压制新兴/商品'
                else:
                    signal = '🟡 中性'
                
                results.append({
                    'name': '美元指数',
                    'description': '领先新兴市场',
                    'value': f'{current:.2f}',
                    'change': f'{change_20d:+.1f}%',
                    'signal': signal,
                    'change_val': change_20d,
                })
        
        # 6. USDJPY变化 - 领先Risk-off事件
        if 'JPY=X' in self.yahoo.columns:
            usdjpy = self.yahoo['JPY=X'].dropna()
            if len(usdjpy) > 20:
                current = usdjpy.iloc[-1]
                change_20d = (usdjpy.iloc[-1] / usdjpy.iloc[-21] - 1) * 100 if len(usdjpy) > 21 else 0
                
                if change_20d < -2:
                    signal = '🔴 日元走强，Carry风险'
                elif change_20d > 2:
                    signal = '🟢 Carry稳定'
                else:
                    signal = '🟡 观察中'
                
                results.append({
                    'name': 'USD/JPY',
                    'description': '领先Carry风险',
                    'value': f'{current:.2f}',
                    'change': f'{change_20d:+.1f}%',
                    'signal': signal,
                    'change_val': change_20d,
                })
        
        return results
    
    # ==================== P1-2: 相关性变化监控 ====================
    
    def calc_correlation_monitor(self, window=60):
        """
        监控关键资产对的相关性变化
        """
        results = []
        
        # 定义要监控的相关性对及其历史正常范围
        correlation_pairs = [
            {
                'asset1': 'BTC-USD', 'asset2': 'QQQ',
                'name': 'BTC vs 纳指',
                'normal_low': 0.4, 'normal_high': 0.7,
                'interpretation_high': 'BTC被当作科技股交易',
                'interpretation_low': 'BTC走独立行情',
            },
            {
                'asset1': 'GLD', 'asset2': 'TLT',
                'name': '黄金 vs 长债',
                'normal_low': 0.2, 'normal_high': 0.5,
                'interpretation_high': '避险资产同步',
                'interpretation_low': '黄金有独立驱动(通胀/央行购金)',
            },
            {
                'asset1': 'EEM', 'asset2': 'DX-Y.NYB',
                'name': '新兴市场 vs 美元',
                'normal_low': -0.7, 'normal_high': -0.4,
                'interpretation_high': '新兴市场与美元脱钩',
                'interpretation_low': '美元主导新兴市场',
            },
            {
                'asset1': 'SPY', 'asset2': 'TLT',
                'name': '美股 vs 美债',
                'normal_low': -0.4, 'normal_high': 0.2,
                'interpretation_high': '股债同涨(Goldilocks)或同跌(流动性危机)',
                'interpretation_low': '正常负相关',
            },
            {
                'asset1': 'XLE', 'asset2': 'SPY',
                'name': '能源 vs 大盘',
                'normal_low': 0.5, 'normal_high': 0.8,
                'interpretation_high': '能源与大盘高度同步',
                'interpretation_low': '能源走独立行情(供给因素)',
            },
        ]
        
        for pair in correlation_pairs:
            asset1_ticker = pair['asset1']
            asset2_ticker = pair['asset2']
            
            # 获取数据
            if asset1_ticker in self.yahoo.columns:
                asset1 = self.yahoo[asset1_ticker].dropna()
            elif asset1_ticker in self.fred.columns:
                asset1 = self.fred[asset1_ticker].dropna()
            else:
                continue
                
            if asset2_ticker in self.yahoo.columns:
                asset2 = self.yahoo[asset2_ticker].dropna()
            elif asset2_ticker in self.fred.columns:
                asset2 = self.fred[asset2_ticker].dropna()
            else:
                continue
            
            # 计算滚动相关性
            corr = self.calc_rolling_corr(asset1, asset2, window)
            if corr is None or len(corr.dropna()) < 10:
                continue
            
            current_corr = corr.iloc[-1]
            
            # 计算历史均值（用于对比）
            hist_mean = corr.dropna().mean()
            
            # 判断是否异常
            normal_low = pair['normal_low']
            normal_high = pair['normal_high']
            
            if current_corr > normal_high:
                status = '🔴 异常高'
                interpretation = pair['interpretation_high']
            elif current_corr < normal_low:
                status = '🔴 异常低'
                interpretation = pair['interpretation_low']
            else:
                status = '🟢 正常'
                interpretation = '在历史正常范围内'
            
            deviation = current_corr - hist_mean
            
            results.append({
                'name': pair['name'],
                'current': current_corr,
                'hist_mean': hist_mean,
                'deviation': deviation,
                'status': status,
                'interpretation': interpretation,
                'normal_range': f'[{normal_low:.1f}, {normal_high:.1f}]',
            })
        
        return results
    
    # ==================== P2-1: 经济周期定位 ====================
    
    def calc_economic_cycle(self):
        """
        判断当前经济周期阶段
        使用铜/金比率作为增长代理，通胀预期和收益率曲线作为通胀/政策代理
        """
        result = {
            'cycle': None,
            'growth_signal': None,
            'inflation_signal': None,
            'indicators': {},
            'favorable_assets': [],
            'unfavorable_assets': [],
        }
        
        # 1. 增长代理：铜/金比率变化
        growth_change = None
        if all(t in self.yahoo.columns for t in ['CPER', 'GLD']):
            copper = self.yahoo['CPER'].dropna()
            gold = self.yahoo['GLD'].dropna()
            common_idx = copper.index.intersection(gold.index)
            if len(common_idx) > 20:
                ratio = copper.loc[common_idx] / gold.loc[common_idx]
                growth_change = (ratio.iloc[-1] / ratio.iloc[-21] - 1) * 100 if len(ratio) > 21 else None
                result['indicators']['copper_gold_change'] = growth_change
        
        # 2. 通胀代理：10Y盈亏平衡通胀变化
        inflation_change = None
        if 'T10YIE' in self.fred.columns:
            t10yie = self.fred['T10YIE'].dropna()
            if len(t10yie) > 20:
                inflation_change = (t10yie.iloc[-1] - t10yie.iloc[-21]) * 100 if len(t10yie) > 21 else None  # bps
                result['indicators']['inflation_expectation_change'] = inflation_change
        
        # 3. 收益率曲线变化
        curve_change = None
        if all(k in self.fred.columns for k in ['DGS10', 'DGS2']):
            dgs10 = self.fred['DGS10'].dropna()
            dgs2 = self.fred['DGS2'].dropna()
            common_idx = dgs10.index.intersection(dgs2.index)
            if len(common_idx) > 20:
                curve = dgs10.loc[common_idx] - dgs2.loc[common_idx]
                curve_change = (curve.iloc[-1] - curve.iloc[-21]) * 100 if len(curve) > 21 else None  # bps
                result['indicators']['curve_change'] = curve_change
                result['indicators']['current_curve'] = curve.iloc[-1]
        
        # 4. 判断周期
        if growth_change is not None and inflation_change is not None:
            # 增长信号
            if growth_change > 2:
                result['growth_signal'] = '加速'
                growth_up = True
            elif growth_change < -2:
                result['growth_signal'] = '减速'
                growth_up = False
            else:
                result['growth_signal'] = '平稳'
                growth_up = None
            
            # 通胀信号
            if inflation_change > 5:
                result['inflation_signal'] = '升温'
                inflation_up = True
            elif inflation_change < -5:
                result['inflation_signal'] = '降温'
                inflation_up = False
            else:
                result['inflation_signal'] = '稳定'
                inflation_up = None
            
            # 周期判断
            if growth_up == True and inflation_up != True:
                result['cycle'] = '复苏'
                result['cycle_description'] = '增长加速，通胀温和'
                result['favorable_assets'] = ['小盘股', '周期股', '铜', '新兴市场', '金融']
                result['unfavorable_assets'] = ['长期国债', '防御板块', '黄金']
            elif growth_up == True and inflation_up == True:
                result['cycle'] = '扩张/过热'
                result['cycle_description'] = '增长强劲，通胀上升'
                result['favorable_assets'] = ['商品', '能源', '价值股', '通胀保值债券']
                result['unfavorable_assets'] = ['长久期债券', '高估值成长股']
            elif growth_up == False and inflation_up == True:
                result['cycle'] = '滞胀'
                result['cycle_description'] = '增长放缓，通胀顽固'
                result['favorable_assets'] = ['黄金', '商品', '现金', '防御板块']
                result['unfavorable_assets'] = ['股票', '债券', '周期股']
            elif growth_up == False and inflation_up != True:
                result['cycle'] = '衰退'
                result['cycle_description'] = '增长放缓，通胀下降'
                result['favorable_assets'] = ['长期国债', '黄金', '防御板块', '公用事业']
                result['unfavorable_assets'] = ['周期股', '小盘股', '新兴市场', '商品']
            else:
                result['cycle'] = '过渡期'
                result['cycle_description'] = '信号混合，方向不明确'
                result['favorable_assets'] = ['均衡配置']
                result['unfavorable_assets'] = ['高杠杆策略']
        
        return result
    
    # ==================== 汇总 ====================
    
    def calc_all_advanced(self):
        """计算所有高级分析指标"""
        return {
            'rs_momentum': self.calc_rs_momentum(momentum_period=5),
            'rotation_heatmap': self.calc_rotation_heatmap(weeks=12),
            'leading_indicators': self.calc_leading_indicators(),
            'correlation_monitor': self.calc_correlation_monitor(window=60),
            'economic_cycle': self.calc_economic_cycle(),
        }


if __name__ == '__main__':
    from data_fetcher import fetch_data
    
    # 获取数据
    all_data = fetch_data()
    
    # 高级分析
    analytics = AdvancedAnalytics(all_data)
    results = analytics.calc_all_advanced()
    
    print("\n" + "=" * 50)
    print("RS动量分析")
    print("=" * 50)
    for item in results['rs_momentum'][:5]:
        print(f"{item['name']}: RS={item['rs_z']:.2f}σ, 动量={item['rs_momentum']:.2f}, {item['status']}")
    
    print("\n" + "=" * 50)
    print("经济周期定位")
    print("=" * 50)
    cycle = results['economic_cycle']
    print(f"当前周期: {cycle['cycle']}")
    print(f"增长信号: {cycle['growth_signal']}")
    print(f"通胀信号: {cycle['inflation_signal']}")
    print(f"有利资产: {', '.join(cycle['favorable_assets'])}")
