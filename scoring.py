"""
宏观战情室 V2 - 评分系统模块
"""
import pandas as pd
import numpy as np
from datetime import datetime

from config import (
    SCORE_WEIGHTS, LIQUIDITY_WEIGHTS, CURRENCY_WEIGHTS,
    ROTATION_WEIGHTS, US_STRUCTURE_WEIGHTS,
    ALERT_THRESHOLDS, get_score_color
)


class ScoringSystem:
    """评分系统"""
    
    def __init__(self, indicators):
        self.indicators = indicators
        self.scores = {}
        self.alerts = []
        
    def z_to_score(self, z, max_z=3):
        """
        将Z-Score映射到[-100, +100]
        返回: (score, is_extreme)
        """
        if z is None or np.isnan(z):
            return 0, False
            
        is_extreme = abs(z) > ALERT_THRESHOLDS['extreme']
        
        # 限制在[-max_z, +max_z]范围内
        z_clamped = np.clip(z, -max_z, max_z)
        score = (z_clamped / max_z) * 100
        
        return score, is_extreme
    
    def calc_weighted_score(self, z_scores, weights):
        """计算加权评分"""
        total_score = 0
        total_weight = 0
        
        for key, weight in weights.items():
            if key in z_scores and z_scores[key] is not None:
                z = z_scores[key]
                if not np.isnan(z):
                    score, is_extreme = self.z_to_score(z)
                    total_score += score * weight
                    total_weight += weight
        
        if total_weight > 0:
            return total_score / total_weight
        return 0
    
    # ==================== 流动性评分 ====================
    
    def calc_liquidity_score(self):
        """计算流动性评分"""
        liq = self.indicators.get('liquidity', {})
        
        z_scores = {}
        
        # 净流动性Z-Score (正分 = 流动性充裕)
        if 'net_liquidity' in liq:
            z = liq['net_liquidity'].get('z_60d')
            if z is not None and not np.isnan(z):
                z_scores['net_liquidity_trend'] = z
                
                # 添加预警
                if abs(z) > ALERT_THRESHOLDS['extreme']:
                    self.alerts.append({
                        'level': 'extreme',
                        'category': '流动性',
                        'indicator': '净流动性',
                        'z': z,
                        'message': '流动性极端充裕' if z > 0 else '流动性极端紧张',
                    })
        
        # RRP变化 (RRP下降 = 释放流动性 = 正分)
        if 'rrp' in liq:
            z = liq['rrp'].get('z_60d')
            if z is not None and not np.isnan(z):
                z_scores['rrp_change'] = -z  # 反向：RRP低=正分
        
        # TGA变化 (TGA下降 = 释放流动性 = 正分)
        if 'tga' in liq:
            z = liq['tga'].get('z_60d')
            if z is not None and not np.isnan(z):
                z_scores['tga_change'] = -z  # 反向：TGA低=正分
        
        # HYG/LQD (高 = 风险偏好高 = 正分)
        if 'hyg_lqd' in liq:
            z = liq['hyg_lqd'].get('z_60d')
            if z is not None and not np.isnan(z):
                z_scores['hyg_lqd'] = z
                
                if abs(z) > ALERT_THRESHOLDS['extreme']:
                    self.alerts.append({
                        'level': 'extreme',
                        'category': '流动性',
                        'indicator': 'HYG/LQD',
                        'z': z,
                        'message': '信用风险偏好极高' if z > 0 else '信用风险规避极端',
                    })
        
        score = self.calc_weighted_score(z_scores, LIQUIDITY_WEIGHTS)
        
        return {
            'score': score,
            'z_scores': z_scores,
            'interpretation': self.interpret_score(score, '流动性'),
        }
    
    # ==================== 货币环境评分 ====================
    
    def calc_currency_score(self):
        """计算货币环境评分"""
        curr = self.indicators.get('currency', {})
        
        z_scores = {}
        
        # DXY趋势 (弱美元 = 利好风险资产 = 正分)
        if 'dxy' in curr:
            z = curr['dxy'].get('z_60d')
            if z is not None and not np.isnan(z):
                z_scores['dxy_trend'] = -z  # 反向：DXY低=正分
                
                if abs(z) > ALERT_THRESHOLDS['extreme']:
                    self.alerts.append({
                        'level': 'extreme',
                        'category': '货币',
                        'indicator': 'DXY',
                        'z': z,
                        'message': '美元极端强势' if z > 0 else '美元极端弱势',
                    })
        
        # USDJPY趋势 (日元走弱 = Carry正常 = 正分)
        if 'usdjpy' in curr:
            z = curr['usdjpy'].get('z_60d')
            if z is not None and not np.isnan(z):
                z_scores['usdjpy_trend'] = z  # USDJPY高=正分(Carry稳定)
                
                carry_risk = curr['usdjpy'].get('carry_risk', '低')
                if carry_risk == '高':
                    self.alerts.append({
                        'level': 'warning',
                        'category': '货币',
                        'indicator': 'USDJPY',
                        'z': z,
                        'message': 'Carry Trade平仓风险上升',
                    })
        
        # 实际利率 (实际利率下降 = 利好黄金和风险资产 = 正分)
        if 'real_rate' in curr:
            z = curr['real_rate'].get('z_60d')
            if z is not None and not np.isnan(z):
                z_scores['real_rate_trend'] = -z  # 反向：实际利率低=正分
        
        # 期限利差 (陡峭化 = 经济预期改善 = 正分)
        if 'term_spread' in curr:
            z = curr['term_spread'].get('z_60d')
            if z is not None and not np.isnan(z):
                z_scores['term_spread'] = z
                
                curve_shape = curr['term_spread'].get('curve_shape', '')
                if '倒挂' in curve_shape:
                    self.alerts.append({
                        'level': 'warning',
                        'category': '利率',
                        'indicator': '收益率曲线',
                        'z': z,
                        'message': f'收益率曲线{curve_shape}',
                    })
        
        score = self.calc_weighted_score(z_scores, CURRENCY_WEIGHTS)
        
        return {
            'score': score,
            'z_scores': z_scores,
            'interpretation': self.interpret_score(score, '货币环境'),
        }
    
    # ==================== 全球轮动评分 ====================
    
    def calc_rotation_score(self):
        """计算全球轮动评分"""
        rot = self.indicators.get('rotation', {})
        
        z_scores = {}
        
        rankings = rot.get('rankings', [])
        
        # 风险资产平均RS
        risk_assets = ['GLD', 'DBC', 'CPER', 'EEM']
        risk_z = [r['z'] for r in rankings if r['ticker'] in risk_assets]
        if risk_z:
            z_scores['risk_assets_rs'] = np.mean(risk_z)
        
        # 避险资产RS (黄金)
        safe_z = [r['z'] for r in rankings if r['ticker'] == 'GLD']
        if safe_z:
            # 黄金走强可能是避险，也可能是通胀对冲，这里作为中性处理
            z_scores['safe_assets_rs'] = safe_z[0] * 0.5  # 降低权重
        
        # 新兴vs发达
        em_z = [r['z'] for r in rankings if r['ticker'] in ['EEM', 'FXI', 'sh000300', 'HSI']]
        if em_z:
            z_scores['em_vs_dm'] = np.mean(em_z)
            
            # 新兴市场极端强势
            if np.mean(em_z) > ALERT_THRESHOLDS['extreme']:
                self.alerts.append({
                    'level': 'extreme',
                    'category': '轮动',
                    'indicator': '新兴市场',
                    'z': np.mean(em_z),
                    'message': '新兴市场相对美股极端强势',
                })
        
        # 极端情绪指标
        extreme = rot.get('extreme_sentiment', {})
        for ticker, data in extreme.items():
            z = data.get('z', 0)
            if abs(z) > ALERT_THRESHOLDS['extreme']:
                self.alerts.append({
                    'level': 'extreme',
                    'category': '情绪',
                    'indicator': data.get('name', ticker),
                    'z': z,
                    'message': data.get('sentiment', ''),
                })
        
        score = self.calc_weighted_score(z_scores, ROTATION_WEIGHTS)
        
        return {
            'score': score,
            'z_scores': z_scores,
            'interpretation': self.interpret_score(score, '全球轮动'),
        }
    
    # ==================== 美股结构评分 ====================
    
    def calc_us_structure_score(self):
        """计算美股结构评分"""
        us = self.indicators.get('us_structure', {})
        
        category_scores = {}
        
        for category in ['risk_appetite', 'sector_rotation', 'breadth']:
            pairs = us.get(category, [])
            if pairs:
                z_values = [p['z'] for p in pairs if not np.isnan(p['z'])]
                if z_values:
                    category_scores[category] = np.mean(z_values)
                    
                    # 检查极端值
                    for p in pairs:
                        if abs(p['z']) > ALERT_THRESHOLDS['extreme']:
                            self.alerts.append({
                                'level': 'extreme',
                                'category': '美股结构',
                                'indicator': p['name'],
                                'z': p['z'],
                                'message': f"{p['name']} 处于极端水平",
                            })
        
        score = self.calc_weighted_score(category_scores, US_STRUCTURE_WEIGHTS)
        
        return {
            'score': score,
            'category_scores': category_scores,
            'interpretation': self.interpret_score(score, '美股结构'),
        }
    
    # ==================== 综合评分 ====================
    
    def calc_total_score(self):
        """计算综合评分"""
        self.alerts = []  # 重置预警
        
        # 计算各子评分
        liquidity = self.calc_liquidity_score()
        currency = self.calc_currency_score()
        rotation = self.calc_rotation_score()
        us_structure = self.calc_us_structure_score()
        
        self.scores = {
            'liquidity': liquidity,
            'currency': currency,
            'rotation': rotation,
            'us_structure': us_structure,
        }
        
        # 综合评分
        total = (
            liquidity['score'] * SCORE_WEIGHTS['liquidity'] +
            currency['score'] * SCORE_WEIGHTS['currency'] +
            rotation['score'] * SCORE_WEIGHTS['rotation'] +
            us_structure['score'] * SCORE_WEIGHTS['us_structure']
        )
        
        self.scores['total'] = {
            'score': total,
            'interpretation': self.interpret_total_score(total),
            'color': get_score_color(total),
        }
        
        # 按严重程度排序预警
        self.alerts = sorted(self.alerts, 
                           key=lambda x: 0 if x['level'] == 'extreme' else 1)
        
        return self.scores
    
    def interpret_score(self, score, category):
        """解读单项评分"""
        if score >= 50:
            return f'{category}环境非常有利'
        elif score >= 20:
            return f'{category}环境偏有利'
        elif score >= -20:
            return f'{category}环境中性'
        elif score >= -50:
            return f'{category}环境偏不利'
        else:
            return f'{category}环境非常不利'
    
    def interpret_total_score(self, score):
        """解读综合评分"""
        if score >= 50:
            return '宏观环境极度有利，Risk-On'
        elif score >= 30:
            return '宏观环境较好，偏Risk-On'
        elif score >= 10:
            return '宏观环境中性偏积极'
        elif score >= -10:
            return '宏观环境中性'
        elif score >= -30:
            return '宏观环境中性偏谨慎'
        elif score >= -50:
            return '宏观环境较差，偏Risk-Off'
        else:
            return '宏观环境极度不利，Risk-Off'
    
    def get_favorable_assets(self):
        """获取当前环境有利的资产"""
        rot = self.indicators.get('rotation', {})
        rankings = rot.get('rankings', [])
        
        favorable = [r for r in rankings if r['z'] > 0.5]
        return [r['name'] for r in sorted(favorable, key=lambda x: x['z'], reverse=True)]
    
    def get_unfavorable_assets(self):
        """获取当前环境不利的资产"""
        rot = self.indicators.get('rotation', {})
        rankings = rot.get('rankings', [])
        
        unfavorable = [r for r in rankings if r['z'] < -0.5]
        return [r['name'] for r in sorted(unfavorable, key=lambda x: x['z'])]
    
    def get_alerts(self):
        """获取预警列表"""
        return self.alerts
    
    def format_alert(self, alert):
        """格式化预警消息"""
        level_emoji = '🔴' if alert['level'] == 'extreme' else '🟡'
        return f"{level_emoji} [{alert['category']}] {alert['indicator']}: Z={alert['z']:.2f} - {alert['message']}"


if __name__ == '__main__':
    from data_fetcher import fetch_data
    from indicators import IndicatorCalculator
    
    # 获取数据
    all_data = fetch_data()
    
    # 计算指标
    calc = IndicatorCalculator(all_data)
    indicators = calc.calc_all_indicators()
    
    # 计算评分
    scorer = ScoringSystem(indicators)
    scores = scorer.calc_total_score()
    
    print("\n" + "=" * 50)
    print("评分结果")
    print("=" * 50)
    
    for category, data in scores.items():
        if isinstance(data, dict) and 'score' in data:
            print(f"\n{category}: {data['score']:.1f}")
            print(f"  解读: {data.get('interpretation', '')}")
    
    print("\n" + "=" * 50)
    print("预警信号")
    print("=" * 50)
    
    for alert in scorer.get_alerts():
        print(scorer.format_alert(alert))
    
    print("\n有利资产:", ', '.join(scorer.get_favorable_assets()[:5]))
    print("不利资产:", ', '.join(scorer.get_unfavorable_assets()[:5]))
