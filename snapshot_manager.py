"""
宏观战情室 V2 - 每日快照管理模块
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os


class SnapshotManager:
    """每日快照管理器"""
    
    def __init__(self, data_dir='data'):
        self.data_dir = data_dir
        self.snapshot_file = os.path.join(data_dir, 'daily_snapshots.csv')
        os.makedirs(data_dir, exist_ok=True)
        
    def _load_snapshots(self):
        """加载历史快照"""
        if os.path.exists(self.snapshot_file):
            try:
                df = pd.read_csv(self.snapshot_file, parse_dates=['date'])
                return df
            except Exception as e:
                print(f"加载快照失败: {e}")
                return pd.DataFrame()
        return pd.DataFrame()
    
    def _save_snapshots(self, df):
        """保存快照到CSV"""
        df.to_csv(self.snapshot_file, index=False)
    
    def get_snapshot_stats(self):
        """获取快照统计信息"""
        df = self._load_snapshots()
        
        if df.empty:
            return {
                'count': 0,
                'earliest_date': None,
                'latest_date': None,
                'today_saved': False,
            }
        
        today = datetime.now().strftime('%Y-%m-%d')
        today_saved = today in df['date'].astype(str).values
        
        return {
            'count': len(df),
            'earliest_date': df['date'].min().strftime('%Y-%m-%d') if len(df) > 0 else None,
            'latest_date': df['date'].max().strftime('%Y-%m-%d') if len(df) > 0 else None,
            'today_saved': today_saved,
        }
    
    def is_today_saved(self):
        """检查今日是否已保存"""
        stats = self.get_snapshot_stats()
        return stats['today_saved']
    
    def generate_snapshot(self, indicators, scores, all_data):
        """从当前数据生成快照"""
        today = datetime.now().strftime('%Y-%m-%d')
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        snapshot = {
            'date': today,
            'timestamp': timestamp,
        }
        
        # ==================== 流动性指标 ====================
        liq = indicators.get('liquidity', {})
        
        net_liq = liq.get('net_liquidity', {})
        snapshot['net_liquidity'] = net_liq.get('latest', None)
        snapshot['net_liquidity_z60'] = net_liq.get('z_60d', None)
        snapshot['net_liquidity_pct252'] = net_liq.get('pct_252d', None)
        
        rrp = liq.get('rrp', {})
        snapshot['rrp'] = rrp.get('latest', None)
        
        tga = liq.get('tga', {})
        snapshot['tga'] = tga.get('latest', None)
        
        hyg_lqd = liq.get('hyg_lqd', {})
        snapshot['hyg_lqd'] = hyg_lqd.get('latest', None)
        snapshot['hyg_lqd_z60'] = hyg_lqd.get('z_60d', None)
        
        # ==================== 货币环境 ====================
        curr = indicators.get('currency', {})
        
        dxy = curr.get('dxy', {})
        snapshot['dxy'] = dxy.get('latest', None)
        snapshot['dxy_z60'] = dxy.get('z_60d', None)
        snapshot['dxy_trend'] = dxy.get('trend', None)
        
        usdjpy = curr.get('usdjpy', {})
        snapshot['usdjpy'] = usdjpy.get('latest', None)
        snapshot['usdjpy_z60'] = usdjpy.get('z_60d', None)
        snapshot['usdjpy_change_20d'] = usdjpy.get('change_20d', None)
        
        real_rate = curr.get('real_rate', {})
        snapshot['real_rate'] = real_rate.get('latest', None)
        
        term_spread = curr.get('term_spread', {})
        snapshot['term_spread_10y3m'] = term_spread.get('latest', None)
        
        vix = curr.get('vix', {})
        snapshot['vix'] = vix.get('latest', None)
        
        fed_policy = curr.get('fed_policy', {})
        snapshot['fed_rate'] = fed_policy.get('current_rate', None)
        snapshot['fed_policy_signal'] = fed_policy.get('signal', None)
        
        # ==================== 经济周期 ====================
        cycle = indicators.get('economic_cycle', {})
        snapshot['economic_cycle'] = cycle.get('cycle', None)
        
        growth_signal = cycle.get('growth_signal', {})
        snapshot['copper_gold_change_20d'] = growth_signal.get('change_20d', None)
        
        inflation_signal = cycle.get('inflation_signal', {})
        snapshot['inflation_change_20d_bp'] = inflation_signal.get('change_20d_bp', None)
        
        # ==================== RS Z-Score (13个资产) ====================
        rs_momentum = indicators.get('rs_momentum', [])
        
        # 创建ticker到数据的映射
        rs_map = {item['ticker']: item for item in rs_momentum}
        
        rs_assets = [
            ('GLD', 'gold'),
            ('SLV', 'silver'),
            ('CPER', 'copper'),
            ('DBC', 'commodity'),
            ('USO', 'oil'),
            ('EEM', 'em'),
            ('EWH', 'hk'),
            ('FXI', 'china'),
            ('IWM', 'smallcap'),
            ('QQQ', 'qqq'),
            ('BTC-USD', 'btc'),
            ('ARKK', 'arkk'),
            ('TLT', 'tlt'),
        ]
        
        for ticker, name in rs_assets:
            if ticker in rs_map:
                snapshot[f'rs_z_{name}'] = rs_map[ticker].get('rs_z', None)
                snapshot[f'rs_mom_{name}'] = rs_map[ticker].get('rs_momentum', None)
                snapshot[f'rs_status_{name}'] = rs_map[ticker].get('status', None)
            else:
                snapshot[f'rs_z_{name}'] = None
                snapshot[f'rs_mom_{name}'] = None
                snapshot[f'rs_status_{name}'] = None
        
        # ==================== 评分 ====================
        snapshot['score_liquidity'] = scores.get('liquidity', {}).get('score', None)
        snapshot['score_currency'] = scores.get('currency', {}).get('score', None)
        snapshot['score_rotation'] = scores.get('rotation', {}).get('score', None)
        snapshot['score_us_structure'] = scores.get('us_structure', {}).get('score', None)
        snapshot['score_total'] = scores.get('total', {}).get('score', None)
        
        # ==================== 领先指标 ====================
        leading = indicators.get('leading_indicators', [])
        leading_map = {item['name']: item for item in leading}
        
        if '铜/金比率' in leading_map:
            snapshot['leading_copper_gold'] = leading_map['铜/金比率'].get('change_20d', None)
        if 'HYG/TLT比率' in leading_map:
            snapshot['leading_hyg_tlt'] = leading_map['HYG/TLT比率'].get('change_20d', None)
        if '半导体/纳指' in leading_map:
            snapshot['leading_smh_qqq'] = leading_map['半导体/纳指'].get('change_20d', None)
        if '2Y国债收益率' in leading_map:
            snapshot['leading_dgs2'] = leading_map['2Y国债收益率'].get('change_20d', None)
        if '美元指数' in leading_map:
            snapshot['leading_dxy'] = leading_map['美元指数'].get('change_20d', None)
        if 'USD/JPY' in leading_map:
            snapshot['leading_usdjpy'] = leading_map['USD/JPY'].get('change_20d', None)
        
        # ==================== 相关性异常 ====================
        corr_monitor = indicators.get('correlation_monitor', [])
        abnormal_count = len([c for c in corr_monitor if '异常' in c.get('status', '')])
        snapshot['correlation_abnormal_count'] = abnormal_count
        
        # ==================== 预警数量 ====================
        # 需要从scorer获取，这里简化处理
        snapshot['alert_count'] = 0  # 后续可以补充
        
        # ==================== 市场收盘价 (用于后续计算收益) ====================
        yahoo = all_data.get('yahoo', pd.DataFrame())
        if not yahoo.empty:
            for ticker, col_name in [('SPY', 'spy_close'), ('QQQ', 'qqq_close'), ('IWM', 'iwm_close')]:
                if ticker in yahoo.columns:
                    valid = yahoo[ticker].dropna()
                    if len(valid) > 0:
                        snapshot[col_name] = valid.iloc[-1]
                    else:
                        snapshot[col_name] = None
                else:
                    snapshot[col_name] = None
        
        # ==================== 后续收益 (初始为空，后续更新) ====================
        snapshot['spy_return_1d'] = None
        snapshot['spy_return_5d'] = None
        snapshot['spy_return_20d'] = None
        snapshot['qqq_return_1d'] = None
        snapshot['qqq_return_5d'] = None
        snapshot['qqq_return_20d'] = None
        
        return snapshot
    
    def save_today_snapshot(self, indicators, scores, all_data):
        """保存今日快照"""
        # 检查是否已保存
        if self.is_today_saved():
            return False, "今日快照已存在，无需重复保存"
        
        # 生成快照
        snapshot = self.generate_snapshot(indicators, scores, all_data)
        
        # 加载现有数据
        df = self._load_snapshots()
        
        # 追加新快照
        new_row = pd.DataFrame([snapshot])
        df = pd.concat([df, new_row], ignore_index=True)
        
        # 保存
        self._save_snapshots(df)
        
        return True, f"快照已保存: {snapshot['date']}"
    
    def update_forward_returns(self, price_data):
        """更新历史快照的后续收益"""
        df = self._load_snapshots()
        
        if df.empty:
            return 0
        
        updated_count = 0
        
        for idx, row in df.iterrows():
            snapshot_date = pd.to_datetime(row['date'])
            
            # 计算SPY收益
            if pd.isna(row.get('spy_return_20d')) and row.get('spy_close'):
                for days, col in [(1, 'spy_return_1d'), (5, 'spy_return_5d'), (20, 'spy_return_20d')]:
                    future_date = snapshot_date + timedelta(days=days)
                    
                    if 'SPY' in price_data.columns:
                        future_prices = price_data['SPY'][price_data.index >= future_date]
                        if len(future_prices) > 0:
                            future_price = future_prices.iloc[0]
                            ret = (future_price / row['spy_close'] - 1) * 100
                            df.loc[idx, col] = ret
                            updated_count += 1
            
            # 计算QQQ收益
            if pd.isna(row.get('qqq_return_20d')) and row.get('qqq_close'):
                for days, col in [(1, 'qqq_return_1d'), (5, 'qqq_return_5d'), (20, 'qqq_return_20d')]:
                    future_date = snapshot_date + timedelta(days=days)
                    
                    if 'QQQ' in price_data.columns:
                        future_prices = price_data['QQQ'][price_data.index >= future_date]
                        if len(future_prices) > 0:
                            future_price = future_prices.iloc[0]
                            ret = (future_price / row['qqq_close'] - 1) * 100
                            df.loc[idx, col] = ret
                            updated_count += 1
        
        if updated_count > 0:
            self._save_snapshots(df)
        
        return updated_count
    
    def get_all_snapshots(self):
        """获取所有快照数据"""
        return self._load_snapshots()
    
    def get_recent_snapshots(self, days=30):
        """获取最近N天的快照"""
        df = self._load_snapshots()
        
        if df.empty:
            return df
        
        cutoff = datetime.now() - timedelta(days=days)
        df['date'] = pd.to_datetime(df['date'])
        return df[df['date'] >= cutoff].sort_values('date', ascending=False)


# ==================== 便捷函数 ====================

def get_snapshot_manager(data_dir='data'):
    """获取快照管理器实例"""
    return SnapshotManager(data_dir)


if __name__ == '__main__':
    # 测试
    manager = SnapshotManager()
    stats = manager.get_snapshot_stats()
    print(f"快照统计: {stats}")
