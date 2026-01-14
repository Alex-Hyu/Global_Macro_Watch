"""
SpotGamma 期权数据分析模块 V2
整合了地形分析、动力学分析、情绪分析、波动率分析

使用方法:
1. 从SpotGamma导出CSV (Data Table)
2. 在Streamlit侧边栏上传CSV
3. 自动解析并显示分析结果
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple


def parse_spotgamma_csv(uploaded_file) -> Optional[pd.DataFrame]:
    """
    解析SpotGamma CSV文件
    
    Args:
        uploaded_file: Streamlit上传的文件对象或文件路径
        
    Returns:
        解析后的DataFrame，失败返回None
    """
    try:
        # 使用skiprows=1跳过合并的表头行
        df = pd.read_csv(uploaded_file, skiprows=1)
        
        # 清理列名中的特殊字符和空格
        df.columns = [c.strip().replace('\xa0', ' ') for c in df.columns]
        
        # 标准化列名映射
        col_mapping = {
            'Symbol': 'symbol',
            'Current Price': 'price',
            'Stock Volume': 'volume',
            'Earnings Date': 'earnings_date',
            'Key Gamma Strike': 'zero_gamma',
            'Key Delta Strike': 'key_delta',
            'Hedge Wall': 'hedge_wall',
            'Call Wall': 'call_wall',
            'Put Wall': 'put_wall',
            'Options Impact': 'options_impact',
            'Call Gamma': 'call_gamma',
            'Put Gamma': 'put_gamma',
            'Next Exp Gamma': 'next_exp_gamma',
            'Next Exp Delta': 'next_exp_delta',
            'Top Gamma Exp': 'top_gamma_exp',
            'Top Delta Exp': 'top_delta_exp',
            'Next Exp Call Vol': 'next_exp_call_vol',
            'Next Exp Put Vol': 'next_exp_put_vol',
            'Put/Call OI Ratio': 'pc_oi_ratio',
            'Volume Ratio': 'volume_ratio',
            'Gamma Ratio': 'gamma_ratio',
            'Delta Ratio': 'delta_ratio',
            'NE Skew': 'ne_skew',
            'Skew': 'skew',
            '1 M RV': 'rv_1m',
            '1 M IV': 'iv_1m',
            'IV Rank': 'iv_rank',
            'Garch Rank': 'garch_rank',
            'Options Implied Move': 'implied_move',
        }
        
        # 重命名列
        df = df.rename(columns=col_mapping)
        
        # 过滤有效行
        df = df[df['symbol'].notna()].copy()
        
        # 处理带有引号的数值字符串 (如 '-2.4685)
        quote_cols = ['delta_ratio', 'gamma_ratio', 'skew', 'ne_skew', 'call_gamma', 'put_gamma']
        for col in quote_cols:
            if col in df.columns:
                df[col] = df[col].astype(str).str.replace("'", "").astype(float)
        
        # 转换其他数值列
        numeric_cols = ['price', 'zero_gamma', 'key_delta', 'hedge_wall', 'call_wall', 'put_wall',
                       'options_impact', 'next_exp_gamma', 'next_exp_delta',
                       'next_exp_call_vol', 'next_exp_put_vol',
                       'pc_oi_ratio', 'volume_ratio',
                       'rv_1m', 'iv_1m', 'iv_rank', 'garch_rank', 'implied_move']
        
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        return df
        
    except Exception as e:
        print(f"SpotGamma CSV解析失败: {e}")
        return None


def analyze_geography(row: pd.Series) -> Dict:
    """
    地形分析 (Geography)
    分析价格相对于关键位的位置
    
    使用Hedge Wall判定Gamma环境（比Key Gamma Strike更准确）
    """
    result = {
        'symbol': row.get('symbol', 'N/A'),
        'price': row.get('price', 0),
        'zero_gamma': row.get('zero_gamma', 0),
        'hedge_wall': row.get('hedge_wall', 0),
        'call_wall': row.get('call_wall', 0),
        'put_wall': row.get('put_wall', 0),
        'gamma_env': 'N/A',
        'gamma_env_emoji': '⚪',
        'gamma_env_desc': '',
        'dist_to_call_wall': 0,
        'dist_to_put_wall': 0,
        'dist_to_hedge_wall': 0,
        'dist_to_zero_gamma': 0,
        'position_zone': '中性区',
    }
    
    price = row.get('price', 0)
    hedge_wall = row.get('hedge_wall', 0)
    call_wall = row.get('call_wall', 0)
    put_wall = row.get('put_wall', 0)
    zero_gamma = row.get('zero_gamma', 0)
    
    if pd.isna(price) or price == 0:
        return result
    
    # 使用Hedge Wall判定Gamma环境（更准确）
    if pd.notna(hedge_wall) and hedge_wall > 0:
        if price > hedge_wall:
            result['gamma_env'] = '正Gamma'
            result['gamma_env_emoji'] = '✅'
            result['gamma_env_desc'] = '稳定/买入回调'
        else:
            result['gamma_env'] = '负Gamma'
            result['gamma_env_emoji'] = '⚠️'
            result['gamma_env_desc'] = '剧烈/易踩踏'
        
        result['dist_to_hedge_wall'] = ((price - hedge_wall) / price) * 100
    
    # 距离关键位计算
    if pd.notna(call_wall) and call_wall > 0:
        result['dist_to_call_wall'] = ((call_wall - price) / price) * 100
    
    if pd.notna(put_wall) and put_wall > 0:
        result['dist_to_put_wall'] = ((price - put_wall) / price) * 100
    
    if pd.notna(zero_gamma) and zero_gamma > 0:
        result['dist_to_zero_gamma'] = ((price - zero_gamma) / price) * 100
    
    # 判定位置区域
    dist_cw = result['dist_to_call_wall']
    dist_pw = result['dist_to_put_wall']
    
    if dist_cw < 0:
        result['position_zone'] = '真空突破区'  # 已突破Call Wall
    elif dist_cw < 1.5:
        result['position_zone'] = 'Call Wall阻力区'
    elif dist_pw < 1.5:
        result['position_zone'] = 'Put Wall支撑区'
    elif dist_pw < 0:
        result['position_zone'] = '下行陷阱区'  # 已跌破Put Wall
    else:
        result['position_zone'] = '安全区间'
    
    return result


def analyze_dynamics(row: pd.Series, geography: Dict) -> Dict:
    """
    动力学分析 (Dynamics)
    分析磁吸效应和悬崖风险
    """
    result = {
        'pinning_strength': '弱',
        'pinning_emoji': '⚪',
        'pinning_target': 0,
        'cliff_risk': '低',
        'cliff_emoji': '🟢',
        'next_exp_gamma': 0,
        'top_gamma_exp': row.get('top_gamma_exp', ''),
    }
    
    price = row.get('price', 0)
    zero_gamma = row.get('zero_gamma', 0)
    next_exp_gamma = row.get('next_exp_gamma', 0)
    
    if pd.isna(price) or price == 0:
        return result
    
    # 磁吸效应 (Pinning) - 距离Key Gamma Strike
    if pd.notna(zero_gamma) and zero_gamma > 0:
        dist_to_ks = abs(price - zero_gamma) / price * 100
        result['pinning_target'] = zero_gamma
        
        if dist_to_ks < 0.5:
            result['pinning_strength'] = '极强'
            result['pinning_emoji'] = '🧲'
        elif dist_to_ks < 1.0:
            result['pinning_strength'] = '强'
            result['pinning_emoji'] = '🔴'
        elif dist_to_ks < 1.5:
            result['pinning_strength'] = '中等'
            result['pinning_emoji'] = '🟠'
        else:
            result['pinning_strength'] = '弱'
            result['pinning_emoji'] = '⚪'
    
    # 悬崖风险 (Cliff Risk) - Next Exp Gamma
    if pd.notna(next_exp_gamma):
        result['next_exp_gamma'] = next_exp_gamma
        
        if next_exp_gamma > 0.4:
            result['cliff_risk'] = '极高'
            result['cliff_emoji'] = '🚨'
        elif next_exp_gamma > 0.3:
            result['cliff_risk'] = '高'
            result['cliff_emoji'] = '🔴'
        elif next_exp_gamma > 0.2:
            result['cliff_risk'] = '中等'
            result['cliff_emoji'] = '🟠'
        else:
            result['cliff_risk'] = '低'
            result['cliff_emoji'] = '🟢'
    
    return result


def analyze_sentiment(row: pd.Series, geography: Dict) -> Dict:
    """
    情绪与压力分析 (Sentiment)
    分析方向性指标和交易信号
    """
    result = {
        'delta_ratio': row.get('delta_ratio', 0),
        'delta_signal': '⚪',
        'delta_desc': '中性',
        'gamma_ratio': row.get('gamma_ratio', 0),
        'gamma_signal': '⚪',
        'gamma_desc': '均衡',
        'pc_oi_ratio': row.get('pc_oi_ratio', 0),
        'pc_signal': '⚪',
        'pc_desc': '中性',
        'volume_ratio': row.get('volume_ratio', 0),
        'composite_score': 0,
        'composite_signal': '⚪',
        'composite_desc': '中性',
        'active_signals': [],
    }
    
    delta_ratio = row.get('delta_ratio', 0)
    gamma_ratio = row.get('gamma_ratio', 0)
    pc_ratio = row.get('pc_oi_ratio', 0)
    volume_ratio = row.get('volume_ratio', 0)
    
    dist_cw = geography.get('dist_to_call_wall', 0)
    dist_pw = geography.get('dist_to_put_wall', 0)
    gamma_env = geography.get('gamma_env', '')
    
    # Delta Ratio 分析
    if pd.notna(delta_ratio):
        if delta_ratio > -0.8:
            result['delta_signal'] = '🟢'
            result['delta_desc'] = '偏多'
            delta_score = 30
        elif delta_ratio > -1.5:
            result['delta_signal'] = '⚪'
            result['delta_desc'] = '中性'
            delta_score = 0
        elif delta_ratio > -3:
            result['delta_signal'] = '🟠'
            result['delta_desc'] = '偏空'
            delta_score = -30
        else:
            result['delta_signal'] = '🔴'
            result['delta_desc'] = '强烈偏空'
            delta_score = -60
    else:
        delta_score = 0
    
    # Gamma Ratio 分析
    if pd.notna(gamma_ratio):
        if gamma_ratio < 1:
            result['gamma_signal'] = '🟢'
            result['gamma_desc'] = '上涨加速'
            gamma_score = 20
        elif gamma_ratio <= 2:
            result['gamma_signal'] = '⚪'
            result['gamma_desc'] = '均衡'
            gamma_score = 0
        else:
            result['gamma_signal'] = '🔴'
            result['gamma_desc'] = '下跌加速'
            gamma_score = -30
    else:
        gamma_score = 0
    
    # P/C OI Ratio 分析
    if pd.notna(pc_ratio):
        if pc_ratio < 0.7:
            result['pc_signal'] = '🟢'
            result['pc_desc'] = '偏多'
            pc_score = 20
        elif pc_ratio <= 1.5:
            result['pc_signal'] = '⚪'
            result['pc_desc'] = '中性'
            pc_score = 0
        else:
            result['pc_signal'] = '🔴'
            result['pc_desc'] = '偏空'
            pc_score = -20
    else:
        pc_score = 0
    
    # 综合评分
    composite = delta_score + gamma_score + pc_score
    result['composite_score'] = composite
    
    if composite > 30:
        result['composite_signal'] = '🟢'
        result['composite_desc'] = '看多'
    elif composite > 0:
        result['composite_signal'] = '🟢'
        result['composite_desc'] = '轻度看多'
    elif composite > -30:
        result['composite_signal'] = '⚪'
        result['composite_desc'] = '中性'
    elif composite > -60:
        result['composite_signal'] = '🟠'
        result['composite_desc'] = '轻度看空'
    else:
        result['composite_signal'] = '🔴'
        result['composite_desc'] = '强烈看空'
    
    # ===== 交易信号检测 =====
    signals = []
    
    # 1. 做市商Short Put回补反弹信号
    if pd.notna(volume_ratio) and pd.notna(delta_ratio):
        if volume_ratio > 1.2 and delta_ratio < -2 and dist_pw > 1:
            signals.append({
                'type': 'rebound',
                'emoji': '📈',
                'title': '潜在反弹',
                'desc': '做市商Short Put压力，到期后有回补买盘'
            })
    
    # 2. Call Wall突破信号
    if dist_cw < 0 and gamma_env == '正Gamma':
        signals.append({
            'type': 'breakout',
            'emoji': '🚀',
            'title': '真空区突破',
            'desc': '已冲破Call Wall，做市商从阻力变推力'
        })
    
    # 3. 下行陷阱警告
    if dist_pw < 1 or dist_pw < 0:
        signals.append({
            'type': 'trap',
            'emoji': '⚠️',
            'title': '下行危险',
            'desc': '逼近/跌破Put Wall，警惕Gamma Trap加速下跌'
        })
    
    # 4. Call Wall强阻力
    if 0 < dist_cw < 1.5:
        signals.append({
            'type': 'resistance',
            'emoji': '🛑',
            'title': 'Call Wall阻力',
            'desc': f'距Call Wall仅{dist_cw:.1f}%，减仓或做空机会'
        })
    
    # 5. Put Wall支撑
    if 0 < dist_pw < 2:
        signals.append({
            'type': 'support',
            'emoji': '🛡️',
            'title': 'Put Wall支撑',
            'desc': f'距Put Wall仅{dist_pw:.1f}%，观察反弹机会'
        })
    
    result['active_signals'] = signals
    
    return result


def analyze_volatility(row: pd.Series) -> Dict:
    """
    波动率分析 (Volatility)
    
    SpotGamma定义：
    - Skew = 25 Delta Put IV - 25 Delta Call IV
      - 负值 = Put相对便宜，市场偏乐观
      - 正值 = Put溢价，市场避险
    - IV > RV 且 Garch Rank低 = 期权定价偏高，适合卖方
    """
    result = {
        'iv_1m': row.get('iv_1m', 0),
        'rv_1m': row.get('rv_1m', 0),
        'iv_rank': row.get('iv_rank', 0),
        'garch_rank': row.get('garch_rank', 0),
        'skew': row.get('skew', 0),
        'ne_skew': row.get('ne_skew', 0),
        'implied_move': row.get('implied_move', 0),
        'iv_rv_spread': 0,
        'vol_edge': '',
        'vol_edge_emoji': '⚪',
        'skew_signal': '⚪',
        'skew_desc': '正常',
        'ne_skew_signal': '⚪',
        'ne_skew_desc': '正常',
        'garch_warning': False,
    }
    
    iv = row.get('iv_1m', 0)
    rv = row.get('rv_1m', 0)
    garch_rank = row.get('garch_rank', 0)
    
    # IV vs RV 分析 (结合Garch Rank)
    if pd.notna(iv) and pd.notna(rv):
        spread = iv - rv
        result['iv_rv_spread'] = spread
        
        if spread > 0.02:
            result['vol_edge'] = '期权高估 (适合卖)'
            result['vol_edge_emoji'] = '📉'
        elif spread < -0.02:
            result['vol_edge'] = '期权低估 (适合买)'
            result['vol_edge_emoji'] = '📈'
        else:
            result['vol_edge'] = '定价合理'
            result['vol_edge_emoji'] = '⚪'
        
        # Garch Rank极低警告
        if pd.notna(garch_rank) and garch_rank < 0.1:
            result['garch_warning'] = True
            result['vol_edge'] += ' | ⚠️统计波动极低，警惕爆发'
    
    # 30天 Skew 分析
    skew = row.get('skew', 0)
    if pd.notna(skew):
        if skew > 0.15:
            result['skew_signal'] = '🔴'
            result['skew_desc'] = 'Put溢价 (避险)'
        elif skew < -0.15:
            result['skew_signal'] = '🟢'
            result['skew_desc'] = 'Put便宜 (乐观)'
        else:
            result['skew_signal'] = '⚪'
            result['skew_desc'] = '正常'
    
    # NE Skew 分析
    ne_skew = row.get('ne_skew', 0)
    if pd.notna(ne_skew):
        if ne_skew > 0.15:
            result['ne_skew_signal'] = '🔴'
            result['ne_skew_desc'] = '短期对冲需求高'
        elif ne_skew < -0.15:
            result['ne_skew_signal'] = '🟢'
            result['ne_skew_desc'] = '短期乐观'
        else:
            result['ne_skew_signal'] = '⚪'
            result['ne_skew_desc'] = '正常'
    
    return result


def derive_conclusion(geography: Dict, dynamics: Dict, sentiment: Dict, volatility: Dict) -> Dict:
    """
    综合结论与操作建议
    """
    result = {
        'action': '观望',
        'action_emoji': '⏸️',
        'reason': '',
        'confidence': '中',
    }
    
    dist_cw = geography.get('dist_to_call_wall', 0)
    dist_pw = geography.get('dist_to_put_wall', 0)
    gamma_env = geography.get('gamma_env', '')
    next_exp_gamma = dynamics.get('next_exp_gamma', 0)
    cliff_risk = dynamics.get('cliff_risk', '')
    composite_score = sentiment.get('composite_score', 0)
    
    # 优先级判断
    
    # 1. Call Wall强阻力
    if -1 < dist_cw < 1:
        result['action'] = '减仓/做空'
        result['action_emoji'] = '📉'
        result['reason'] = '触及Call Wall强阻力'
        result['confidence'] = '高'
        return result
    
    # 2. Put Wall支撑
    if -1 < dist_pw < 1:
        result['action'] = '博反弹'
        result['action_emoji'] = '📈'
        result['reason'] = '触及Put Wall支撑'
        result['confidence'] = '中'
        return result
    
    # 3. 大量Gamma即将释放
    if next_exp_gamma and next_exp_gamma > 0.4:
        result['action'] = '观望/等待'
        result['action_emoji'] = '⏸️'
        result['reason'] = '大量Gamma即将释放，周后有方向选择'
        result['confidence'] = '中'
        return result
    
    # 4. 负Gamma环境
    if gamma_env == '负Gamma':
        result['action'] = '防御/轻仓'
        result['action_emoji'] = '🛡️'
        result['reason'] = '负Gamma环境，波动将放大'
        result['confidence'] = '高'
        return result
    
    # 5. 正Gamma + 方向偏空
    if gamma_env == '正Gamma' and composite_score < -30:
        result['action'] = '谨慎做多'
        result['action_emoji'] = '⚠️'
        result['reason'] = '正Gamma但方向偏空，等待确认'
        result['confidence'] = '低'
        return result
    
    # 6. 安全区间
    if gamma_env == '正Gamma' and dist_cw > 2 and dist_pw > 2:
        result['action'] = '持有/做多'
        result['action_emoji'] = '✅'
        result['reason'] = '地形安全，阻力尚远'
        result['confidence'] = '中'
        return result
    
    return result


def generate_full_analysis(df: pd.DataFrame) -> Dict:
    """
    生成完整的SpotGamma分析报告
    """
    result = {
        'symbols': [],
        'gamma_summary': {
            'positive_gamma': [],
            'negative_gamma': [],
        },
        'sentiment_summary': {
            'bullish': [],
            'bearish': [],
            'neutral': [],
        },
        'volatility_summary': {
            'sell_vol': [],
            'buy_vol': [],
            'skew_fear': [],
            'skew_greed': [],
        },
        'alerts': [],
        'analysis_by_symbol': {},
    }
    
    for _, row in df.iterrows():
        symbol = row.get('symbol', 'N/A')
        if pd.isna(symbol) or symbol == 'N/A':
            continue
        
        result['symbols'].append(symbol)
        
        # 四维分析
        geography = analyze_geography(row)
        dynamics = analyze_dynamics(row, geography)
        sentiment = analyze_sentiment(row, geography)
        volatility = analyze_volatility(row)
        conclusion = derive_conclusion(geography, dynamics, sentiment, volatility)
        
        # 存储完整分析
        result['analysis_by_symbol'][symbol] = {
            'geography': geography,
            'dynamics': dynamics,
            'sentiment': sentiment,
            'volatility': volatility,
            'conclusion': conclusion,
        }
        
        # 汇总分类
        if geography['gamma_env'] == '正Gamma':
            result['gamma_summary']['positive_gamma'].append(symbol)
        elif geography['gamma_env'] == '负Gamma':
            result['gamma_summary']['negative_gamma'].append(symbol)
        
        if sentiment['composite_score'] > 20:
            result['sentiment_summary']['bullish'].append(symbol)
        elif sentiment['composite_score'] < -30:
            result['sentiment_summary']['bearish'].append(symbol)
        else:
            result['sentiment_summary']['neutral'].append(symbol)
        
        if '卖' in volatility['vol_edge']:
            result['volatility_summary']['sell_vol'].append(symbol)
        elif '买' in volatility['vol_edge']:
            result['volatility_summary']['buy_vol'].append(symbol)
        
        if volatility['skew_desc'] == 'Put溢价 (避险)':
            result['volatility_summary']['skew_fear'].append(symbol)
        elif volatility['skew_desc'] == 'Put便宜 (乐观)':
            result['volatility_summary']['skew_greed'].append(symbol)
        
        # 生成预警
        # 1. 负Gamma + 偏空 = 高风险
        if geography['gamma_env'] == '负Gamma' and sentiment['composite_score'] < -30:
            result['alerts'].append({
                'symbol': symbol,
                'level': 'high',
                'emoji': '🚨',
                'message': f'{symbol}: 负Gamma + 方向偏空，下跌可能加速'
            })
        
        # 2. Cliff Risk高
        if dynamics['cliff_risk'] in ['高', '极高']:
            result['alerts'].append({
                'symbol': symbol,
                'level': 'medium',
                'emoji': '⚠️',
                'message': f'{symbol}: 悬崖风险{dynamics["cliff_risk"]}，大量Gamma将在{row.get("top_gamma_exp", "近期")}释放'
            })
        
        # 3. Garch极低警告
        if volatility['garch_warning']:
            result['alerts'].append({
                'symbol': symbol,
                'level': 'medium',
                'emoji': '💥',
                'message': f'{symbol}: Garch Rank极低，统计波动收缩，警惕爆发'
            })
        
        # 4. 交易信号
        for sig in sentiment['active_signals']:
            if sig['type'] in ['trap', 'breakout']:
                result['alerts'].append({
                    'symbol': symbol,
                    'level': 'high' if sig['type'] == 'trap' else 'medium',
                    'emoji': sig['emoji'],
                    'message': f'{symbol}: {sig["title"]} - {sig["desc"]}'
                })
    
    return result


# ==================== Streamlit 显示函数 ====================

def render_spotgamma_section(df: pd.DataFrame, st_module):
    """
    在Streamlit中渲染SpotGamma分析章节
    """
    st = st_module
    
    # 生成完整分析
    analysis = generate_full_analysis(df)
    
    # ===== 1. 综合结论面板 =====
    st.markdown("### 🎯 综合结论")
    
    # 显示每个标的的结论
    conclusions_data = []
    for sym in analysis['symbols'][:10]:  # 最多显示10个
        sym_data = analysis['analysis_by_symbol'].get(sym)
        if sym_data:
            g = sym_data['geography']
            d = sym_data['dynamics']
            c = sym_data['conclusion']
            conclusions_data.append({
                '标的': sym,
                '价格': f"${g['price']:.2f}" if g['price'] else 'N/A',
                'Gamma环境': f"{g['gamma_env_emoji']} {g['gamma_env']}",
                '位置': g['position_zone'],
                '磁吸': f"{d['pinning_emoji']} {d['pinning_strength']}",
                '悬崖风险': f"{d['cliff_emoji']} {d['cliff_risk']}",
                '操作建议': f"{c['action_emoji']} {c['action']}",
                '理由': c['reason'],
            })
    
    if conclusions_data:
        st.dataframe(pd.DataFrame(conclusions_data), use_container_width=True, hide_index=True)
    
    # ===== 2. 风险预警 =====
    if analysis['alerts']:
        st.markdown("### ⚠️ 风险预警")
        
        high_alerts = [a for a in analysis['alerts'] if a['level'] == 'high']
        med_alerts = [a for a in analysis['alerts'] if a['level'] == 'medium']
        
        if high_alerts:
            for alert in high_alerts[:5]:
                st.error(f"{alert['emoji']} {alert['message']}")
        
        if med_alerts:
            with st.expander(f"⚠️ 中等风险预警 ({len(med_alerts)}条)", expanded=False):
                for alert in med_alerts[:10]:
                    st.warning(f"{alert['emoji']} {alert['message']}")
    
    # ===== 3. Gamma环境总览 =====
    st.markdown("### 🌍 Gamma环境总览")
    
    pos_gamma = analysis['gamma_summary']['positive_gamma']
    neg_gamma = analysis['gamma_summary']['negative_gamma']
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("正Gamma", len(pos_gamma), help="价格在Hedge Wall之上，波动抑制")
        if pos_gamma:
            st.success(", ".join(pos_gamma[:8]))
    
    with col2:
        st.metric("负Gamma", len(neg_gamma), help="价格在Hedge Wall之下，波动放大")
        if neg_gamma:
            st.warning(", ".join(neg_gamma[:8]))
    
    with col3:
        total = len(pos_gamma) + len(neg_gamma)
        if total > 0:
            pos_pct = len(pos_gamma) / total * 100
            st.metric("正Gamma占比", f"{pos_pct:.0f}%")
            if pos_pct > 60:
                st.caption("✅ 整体波动抑制环境")
            elif pos_pct < 40:
                st.caption("⚠️ 整体波动放大环境")
            else:
                st.caption("⚪ 混合环境")
    
    # ===== 4. 关键位地图 =====
    st.markdown("### 📍 关键位地图")
    
    key_symbols = ['NDX', 'QQQ', 'SPY', 'IWM', 'SPX']
    display_symbols = [s for s in key_symbols if s in analysis['symbols']]
    if not display_symbols:
        display_symbols = analysis['symbols'][:6]
    
    levels_data = []
    for sym in display_symbols:
        sym_data = analysis['analysis_by_symbol'].get(sym)
        if sym_data:
            g = sym_data['geography']
            levels_data.append({
                '标的': sym,
                '价格': f"${g['price']:.2f}" if g['price'] else 'N/A',
                'Put Wall': f"${g['put_wall']:.0f}" if g['put_wall'] else 'N/A',
                'Hedge Wall': f"${g['hedge_wall']:.0f}" if g['hedge_wall'] else 'N/A',
                'Call Wall': f"${g['call_wall']:.0f}" if g['call_wall'] else 'N/A',
                '距CW': f"{g['dist_to_call_wall']:+.1f}%",
                '距PW': f"{g['dist_to_put_wall']:+.1f}%",
                '位置': g['position_zone'],
            })
    
    if levels_data:
        st.dataframe(pd.DataFrame(levels_data), use_container_width=True, hide_index=True)
    
    # ===== 5. 方向性指标 =====
    st.markdown("### 📊 方向性指标")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        bullish = analysis['sentiment_summary']['bullish']
        st.markdown("**🟢 看多信号**")
        if bullish:
            for sym in bullish[:5]:
                score = analysis['analysis_by_symbol'][sym]['sentiment']['composite_score']
                st.markdown(f"- {sym}: +{score}")
        else:
            st.caption("无")
    
    with col2:
        neutral = analysis['sentiment_summary']['neutral']
        st.markdown("**⚪ 中性**")
        if neutral:
            st.caption(", ".join(neutral[:8]))
        else:
            st.caption("无")
    
    with col3:
        bearish = analysis['sentiment_summary']['bearish']
        st.markdown("**🔴 看空信号**")
        if bearish:
            for sym in bearish[:5]:
                score = analysis['analysis_by_symbol'][sym]['sentiment']['composite_score']
                st.markdown(f"- {sym}: {score}")
        else:
            st.caption("无")
    
    # 方向性详细表格
    with st.expander("📋 方向性指标详情", expanded=False):
        dir_data = []
        for sym in analysis['symbols']:
            sym_data = analysis['analysis_by_symbol'].get(sym)
            if sym_data:
                s = sym_data['sentiment']
                dir_data.append({
                    '标的': sym,
                    'Delta Ratio': f"{s['delta_ratio']:.2f}" if s['delta_ratio'] else 'N/A',
                    'Delta': f"{s['delta_signal']} {s['delta_desc']}",
                    'Gamma Ratio': f"{s['gamma_ratio']:.2f}" if s['gamma_ratio'] else 'N/A',
                    'Gamma': f"{s['gamma_signal']} {s['gamma_desc']}",
                    'P/C OI': f"{s['pc_oi_ratio']:.2f}" if s['pc_oi_ratio'] else 'N/A',
                    'P/C': f"{s['pc_signal']} {s['pc_desc']}",
                    'Vol Ratio': f"{s['volume_ratio']:.2f}" if s['volume_ratio'] else 'N/A',
                    '综合': f"{s['composite_signal']} {s['composite_score']:+.0f}",
                })
        
        if dir_data:
            st.dataframe(pd.DataFrame(dir_data), use_container_width=True, hide_index=True)
    
    # ===== 6. 波动率洞察 =====
    st.markdown("### 📈 波动率性价比")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**IV vs RV 定价**")
        sell_vol = analysis['volatility_summary']['sell_vol']
        buy_vol = analysis['volatility_summary']['buy_vol']
        
        if sell_vol:
            st.error(f"📉 期权高估 (卖方机会): {', '.join(sell_vol[:6])}")
        if buy_vol:
            st.success(f"📈 期权低估 (买方机会): {', '.join(buy_vol[:6])}")
        if not sell_vol and not buy_vol:
            st.info("⚪ 定价普遍合理")
    
    with col2:
        st.markdown("**Skew 市场情绪**")
        skew_fear = analysis['volatility_summary']['skew_fear']
        skew_greed = analysis['volatility_summary']['skew_greed']
        
        if skew_fear:
            st.warning(f"🔴 避险情绪 (Put溢价): {', '.join(skew_fear[:6])}")
        if skew_greed:
            st.success(f"🟢 乐观情绪 (Put便宜): {', '.join(skew_greed[:6])}")
        if not skew_fear and not skew_greed:
            st.info("⚪ Skew正常")
    
    # 波动率详细表格
    with st.expander("📋 波动率详情", expanded=False):
        vol_data = []
        for sym in analysis['symbols']:
            sym_data = analysis['analysis_by_symbol'].get(sym)
            if sym_data:
                v = sym_data['volatility']
                vol_data.append({
                    '标的': sym,
                    '1M IV': f"{v['iv_1m']*100:.1f}%" if v['iv_1m'] else 'N/A',
                    '1M RV': f"{v['rv_1m']*100:.1f}%" if v['rv_1m'] else 'N/A',
                    'IV-RV': f"{v['iv_rv_spread']*100:+.1f}%" if v['iv_rv_spread'] else 'N/A',
                    '定价': f"{v['vol_edge_emoji']} {v['vol_edge'][:10]}..." if len(v['vol_edge']) > 10 else f"{v['vol_edge_emoji']} {v['vol_edge']}",
                    'Garch': f"{v.get('garch_rank', 0)*100:.0f}%" if v.get('garch_rank') else 'N/A',
                    '30D Skew': f"{v['skew']:.3f}" if v['skew'] else 'N/A',
                    'Skew情绪': f"{v['skew_signal']} {v['skew_desc']}",
                    'NE Skew': f"{v['ne_skew']:.3f}" if v['ne_skew'] else 'N/A',
                    '隐含波动': f"±${v['implied_move']:.2f}" if v['implied_move'] else 'N/A',
                })
        
        if vol_data:
            st.dataframe(pd.DataFrame(vol_data), use_container_width=True, hide_index=True)
        
        st.caption("""
        **SpotGamma波动率逻辑:**
        - IV > RV → 期权定价偏高，适合卖方策略
        - IV < RV → 期权定价偏低，适合买方策略
        - Garch Rank < 10% → 统计波动极低，警惕突然爆发
        - Skew正值 = Put溢价(避险)，负值 = Put便宜(乐观)
        """)
    
    # ===== 7. 交易信号汇总 =====
    st.markdown("### 💡 交易信号")
    
    all_signals = []
    for sym in analysis['symbols']:
        sym_data = analysis['analysis_by_symbol'].get(sym)
        if sym_data:
            for sig in sym_data['sentiment']['active_signals']:
                all_signals.append({
                    'symbol': sym,
                    **sig
                })
    
    if all_signals:
        for sig in all_signals[:8]:
            if sig['type'] == 'trap':
                st.error(f"{sig['emoji']} **{sig['symbol']}** {sig['title']}: {sig['desc']}")
            elif sig['type'] == 'breakout':
                st.success(f"{sig['emoji']} **{sig['symbol']}** {sig['title']}: {sig['desc']}")
            elif sig['type'] == 'rebound':
                st.info(f"{sig['emoji']} **{sig['symbol']}** {sig['title']}: {sig['desc']}")
            else:
                st.warning(f"{sig['emoji']} **{sig['symbol']}** {sig['title']}: {sig['desc']}")
    else:
        st.info("⚪ 当前无明显交易信号，市场处于区间震荡")
    
    return analysis
