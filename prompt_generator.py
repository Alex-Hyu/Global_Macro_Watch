"""
宏观战情室 V2 - Claude Prompt 生成模块
"""
import numpy as np
from datetime import datetime


def generate_claude_prompt(indicators, scores, scorer, advanced=None):
    """生成Claude分析入口的prompt"""
    
    date_str = datetime.now().strftime('%Y-%m-%d')
    
    # 流动性部分
    liq = indicators.get('liquidity', {})
    liq_score = scores.get('liquidity', {})
    
    net_liq = liq.get('net_liquidity', {})
    rrp = liq.get('rrp', {})
    tga = liq.get('tga', {})
    hyg_lqd = liq.get('hyg_lqd', {})
    
    # 货币部分
    curr = indicators.get('currency', {})
    curr_score = scores.get('currency', {})
    
    dxy = curr.get('dxy', {})
    usdjpy = curr.get('usdjpy', {})
    real_rate = curr.get('real_rate', {})
    term_spread = curr.get('term_spread', {})
    fed_policy = curr.get('fed_policy', {})
    boj_policy = curr.get('boj_policy', {})
    vix = curr.get('vix', {})
    
    # 轮动部分
    rot = indicators.get('rotation', {})
    rot_score = scores.get('rotation', {})
    rankings = rot.get('rankings', [])
    extreme = rot.get('extreme_sentiment', {})
    
    # 美股结构
    us = indicators.get('us_structure', {})
    us_score = scores.get('us_structure', {})
    
    # 综合评分
    total = scores.get('total', {})
    
    # 预警
    alerts = scorer.get_alerts()
    
    # 有利/不利资产
    favorable = scorer.get_favorable_assets()
    unfavorable = scorer.get_unfavorable_assets()
    
    # 生成排行榜
    ranking_str = ""
    for i, r in enumerate(rankings[:10], 1):
        ranking_str += f"  {i}. {r['emoji']} {r['name']}: Z={r['z']:.2f} ({r['signal']})\n"
    
    # 生成美股结构因子
    def format_factors(factor_list):
        if not factor_list:
            return "  数据不可用\n"
        return '\n'.join([f"  - {f['name']}: Z={f['z']:.2f} {f['emoji']}" for f in factor_list])
    
    risk_factors = format_factors(us.get('risk_appetite', []))
    sector_factors = format_factors(us.get('sector_rotation', []))
    breadth_factors = format_factors(us.get('breadth', []))
    
    # 生成预警
    alerts_str = ""
    if alerts:
        for a in alerts[:10]:
            level_emoji = '🔴' if a['level'] == 'extreme' else '🟡'
            alerts_str += f"- {level_emoji} [{a['category']}] {a['indicator']}: Z={a['z']:.2f}\n  → {a['message']}\n"
    else:
        alerts_str = "- 无重大预警信号\n"
    
    # 组装prompt
    prompt = f"""## 宏观战情室数据摘要 ({date_str})

### 一、流动性环境
- 净流动性: {net_liq.get('latest', 'N/A'):.2f}万亿美元
  - 60日变化: {net_liq.get('change_20d', 0):.1f}%
  - 60日Z-Score: {net_liq.get('z_60d', 0):.2f}σ
  - 252日百分位: {net_liq.get('pct_252d', 0):.0f}%
- RRP逆回购: ${rrp.get('latest', 0):.0f}B (日变化: {rrp.get('change_1d', 0):.0f}B)
- TGA财政账户: ${tga.get('latest', 0):.0f}B (日变化: {tga.get('change_1d', 0):.0f}B)
- HYG/LQD信用偏好: {hyg_lqd.get('latest', 0):.3f} (Z: {hyg_lqd.get('z_60d', 0):.2f}σ)
- **流动性评分: {liq_score.get('score', 0):.1f}/100** ({liq_score.get('interpretation', '')})

### 二、货币与利率环境
- DXY美元指数: {dxy.get('latest', 0):.2f}
  - 趋势: {dxy.get('trend', 'N/A')} {dxy.get('trend_emoji', '')}
  - Z-Score: {dxy.get('z_60d', 0):.2f}σ
- USD/JPY: {usdjpy.get('latest', 0):.2f}
  - 趋势: {usdjpy.get('trend', 'N/A')} {usdjpy.get('trend_emoji', '')}
  - 20日动量: {usdjpy.get('change_20d', 0):.1f}%
  - Carry Trade风险: {usdjpy.get('carry_risk', 'N/A')}
- 实际利率: {real_rate.get('latest', 0):.2f}%
  - 趋势: {real_rate.get('trend', 'N/A')} {real_rate.get('trend_emoji', '')}
- 10Y-3M利差: {term_spread.get('latest', 0):.2f}% (曲线形态: {term_spread.get('curve_shape', 'N/A')})
- VIX: {vix.get('latest', 0):.1f}
- **货币环境评分: {curr_score.get('score', 0):.1f}/100** ({curr_score.get('interpretation', '')})

### 三、央行政策预期 (代理指标)
**Fed政策信号:**
- 2Y国债收益率: {fed_policy.get('dgs2', 0):.2f}%
- 2Y vs Fed利率({fed_policy.get('current_rate', 0):.2f}%)差值: {fed_policy.get('signal', 0):.2f}%
- 市场预期: {fed_policy.get('outlook', 'N/A')}

**BOJ政策信号:**
- USD/JPY 20日动量: {boj_policy.get('usdjpy_momentum', 0):.1f}%
- 市场预期: {boj_policy.get('outlook', 'N/A')}
- 当前BOJ利率: {boj_policy.get('current_rate', 0):.2f}%

### 四、全球资产轮动
**相对强度排行 (vs SPY, 20日RS, Z-Score):**
{ranking_str}
**极端情绪指标:**
"""
    
    for ticker, data in extreme.items():
        prompt += f"- {data['name']}: Z={data['z']:.2f}σ ({data['sentiment']})\n"
    
    prompt += f"""
- **轮动评分: {rot_score.get('score', 0):.1f}/100** ({rot_score.get('interpretation', '')})

### 五、美股内部结构
**风险偏好因子:**
{risk_factors}

**板块轮动因子:**
{sector_factors}

**市场广度因子:**
{breadth_factors}

- **美股结构评分: {us_score.get('score', 0):.1f}/100** ({us_score.get('interpretation', '')})

### 六、综合评估
- **宏观综合评分: {total.get('score', 0):.1f}/100**
- **解读: {total.get('interpretation', '')}**

**当前环境有利资产:** {', '.join(favorable[:5]) if favorable else '无明显有利资产'}
**当前环境不利资产:** {', '.join(unfavorable[:5]) if unfavorable else '无明显不利资产'}

### 七、预警信号
{alerts_str}
"""

    # 添加高级分析数据
    if advanced:
        # 经济周期
        cycle = advanced.get('economic_cycle', {})
        if cycle.get('cycle'):
            prompt += f"""
### 八、经济周期定位
- **当前周期: {cycle.get('cycle', 'N/A')}**
- 描述: {cycle.get('cycle_description', '')}
- 增长信号: {cycle.get('growth_signal', 'N/A')}
- 通胀信号: {cycle.get('inflation_signal', 'N/A')}
- 周期有利资产: {', '.join(cycle.get('favorable_assets', []))}
- 周期不利资产: {', '.join(cycle.get('unfavorable_assets', []))}
"""

        # RS动量
        rs_momentum = advanced.get('rs_momentum', [])
        if rs_momentum:
            prompt += """
### 九、RS动量分析 (资金流动方向)
"""
            acc_up = [x for x in rs_momentum if x['status_code'] == 'accelerating_up']
            dec_up = [x for x in rs_momentum if x['status_code'] == 'decelerating_up']
            dec_down = [x for x in rs_momentum if x['status_code'] == 'decelerating_down']
            acc_down = [x for x in rs_momentum if x['status_code'] == 'accelerating_down']
            
            if acc_up:
                prompt += f"**加速流入:** {', '.join([x['name'] for x in acc_up[:4]])}\n"
            if dec_up:
                prompt += f"**流入放缓(可能见顶):** {', '.join([x['name'] for x in dec_up[:4]])}\n"
            if dec_down:
                prompt += f"**流出放缓(可能见底):** {', '.join([x['name'] for x in dec_down[:4]])}\n"
            if acc_down:
                prompt += f"**加速流出:** {', '.join([x['name'] for x in acc_down[:4]])}\n"

        # 领先指标
        leading = advanced.get('leading_indicators', [])
        if leading:
            prompt += """
### 十、领先指标信号
"""
            for ind in leading:
                prompt += f"- {ind['name']}: {ind['value']} ({ind['change']}) {ind['signal']}\n"

        # 相关性异常
        corr = advanced.get('correlation_monitor', [])
        abnormal = [c for c in corr if '异常' in c['status']]
        if abnormal:
            prompt += """
### 十一、相关性异常
"""
            for c in abnormal:
                prompt += f"- {c['name']}: 当前{c['current']:.2f} vs 历史{c['hist_mean']:.2f} - {c['interpretation']}\n"

    prompt += """
---

**请基于以上数据进行分析：**

1. **流动性评估**: 当前Fed净流动性水位对风险资产的支撑/压制程度如何?

2. **经济周期判断**: 根据铜/金比率和通胀预期变化，当前处于什么周期阶段?这对资产配置有何指导意义?

3. **资金轮动方向**: 哪些资产正在加速获得资金流入?哪些可能见顶或见底?

4. **领先指标信号**: 各领先指标发出的信号是否一致?是否有潜在的转折信号?

5. **相关性异常**: 如有相关性异常，这意味着什么?是否暗示市场regime变化?

6. **风险提示**: 当前需要关注的主要风险点是什么?

7. **资产配置建议**: 综合以上分析，给出当前环境下的资产配置倾向性建议。

请用中文回答，语言简洁专业，重点突出。
"""
    
    return prompt


def generate_short_summary(indicators, scores, scorer):
    """生成简短的摘要版本"""
    
    date_str = datetime.now().strftime('%Y-%m-%d')
    total = scores.get('total', {})
    
    liq_score = scores.get('liquidity', {}).get('score', 0)
    curr_score = scores.get('currency', {}).get('score', 0)
    rot_score = scores.get('rotation', {}).get('score', 0)
    us_score = scores.get('us_structure', {}).get('score', 0)
    
    favorable = scorer.get_favorable_assets()[:3]
    unfavorable = scorer.get_unfavorable_assets()[:3]
    
    alerts = scorer.get_alerts()
    alert_count = len([a for a in alerts if a['level'] == 'extreme'])
    
    summary = f"""📊 宏观战情室 ({date_str})

综合评分: {total.get('score', 0):.1f}/100 | {total.get('interpretation', '')}

子评分:
• 流动性: {liq_score:.0f} | 货币: {curr_score:.0f} | 轮动: {rot_score:.0f} | 美股: {us_score:.0f}

资金流向:
• 有利: {', '.join(favorable) if favorable else '无'}
• 不利: {', '.join(unfavorable) if unfavorable else '无'}

预警: {alert_count}个极端信号 {'⚠️' if alert_count > 0 else '✅'}
"""
    
    return summary


if __name__ == '__main__':
    from data_fetcher import fetch_data
    from indicators import IndicatorCalculator
    from scoring import ScoringSystem
    
    # 获取数据
    all_data = fetch_data()
    
    # 计算指标
    calc = IndicatorCalculator(all_data)
    indicators = calc.calc_all_indicators()
    
    # 计算评分
    scorer = ScoringSystem(indicators)
    scores = scorer.calc_total_score()
    
    # 生成prompt
    prompt = generate_claude_prompt(indicators, scores, scorer)
    
    print(prompt)
