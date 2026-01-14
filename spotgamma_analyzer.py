"""
SpotGamma 期权数据分析模块
用于解析SpotGamma CSV导出数据，提供Gamma环境、方向性指标、波动率分析

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
        uploaded_file: Streamlit上传的文件对象
        
    Returns:
        解析后的DataFrame，失败返回None
    """
    try:
        # SpotGamma CSV有多层表头
        df = pd.read_csv(uploaded_file, header=[0, 1])
        
        # 展平列名
        flat_cols = []
        for col in df.columns:
            if 'Unnamed' in str(col[0]):
                flat_cols.append(col[1])
            else:
                # 简化列名
                flat_cols.append(col[1])
        
        df.columns = flat_cols
        
        # 标准化列名映射
        col_mapping = {
            'Symbol': 'symbol',
            'Current Price': 'price',
            'Stock Volume': 'volume',
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
        
        # 清理数字列（移除引号）
        numeric_cols = ['price', 'zero_gamma', 'key_delta', 'hedge_wall', 'call_wall', 'put_wall',
                       'options_impact', 'call_gamma', 'put_gamma', 'next_exp_gamma', 'next_exp_delta',
                       'pc_oi_ratio', 'volume_ratio', 'gamma_ratio', 'delta_ratio',
                       'ne_skew', 'skew', 'rv_1m', 'iv_1m', 'iv_rank', 'garch_rank', 'implied_move']
        
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(
                    df[col].astype(str).str.replace("'", "").str.replace(",", ""), 
                    errors='coerce'
                )
        
        return df
        
    except Exception as e:
        print(f"SpotGamma CSV解析失败: {e}")
        return None


def analyze_gamma_environment(row: pd.Series) -> Dict:
    """
    分析单个标的的Gamma环境
    
    Returns:
        包含gamma环境分析的字典
    """
    result = {
        'symbol': row.get('symbol', 'N/A'),
        'price': row.get('price', 0),
        'zero_gamma': row.get('zero_gamma', 0),
        'call_wall': row.get('call_wall', 0),
        'put_wall': row.get('put_wall', 0),
        'hedge_wall': row.get('hedge_wall', 0),
        'gamma_env': 'N/A',
        'gamma_env_emoji': '⚪',
        'position_desc': '',
        'dist_to_call_wall': 0,
        'dist_to_put_wall': 0,
        'dist_to_zero_gamma': 0,
    }
    
    price = row.get('price', 0)
    zero_gamma = row.get('zero_gamma', 0)
    call_wall = row.get('call_wall', 0)
    put_wall = row.get('put_wall', 0)
    
    if pd.isna(price) or price == 0:
        return result
    
    # Gamma环境判断
    if pd.notna(zero_gamma) and zero_gamma > 0:
        if price > zero_gamma:
            result['gamma_env'] = '正Gamma'
            result['gamma_env_emoji'] = '✅'
            result['position_desc'] = 'MM买涨卖跌，波动抑制'
        else:
            result['gamma_env'] = '负Gamma'
            result['gamma_env_emoji'] = '⚠️'
            result['position_desc'] = 'MM追涨杀跌，波动放大'
        
        result['dist_to_zero_gamma'] = ((price - zero_gamma) / zero_gamma) * 100
    
    # 距离关键位
    if pd.notna(call_wall) and call_wall > 0:
        result['dist_to_call_wall'] = ((call_wall - price) / price) * 100
    
    if pd.notna(put_wall) and put_wall > 0:
        result['dist_to_put_wall'] = ((price - put_wall) / price) * 100
    
    return result


def analyze_directional_indicators(row: pd.Series) -> Dict:
    """
    分析方向性指标
    
    Delta Ratio: Put Delta ÷ Call Delta (负值)
        - > -1: 偏多
        - -1 到 -3: 中性到偏空
        - < -3: 强烈偏空
    
    Gamma Ratio: Put Gamma ÷ Call Gamma
        - < 1: Call Gamma主导，上涨加速
        - 1-2: 均衡
        - > 2: Put Gamma主导，下跌加速
    
    P/C OI Ratio:
        - < 0.7: 偏多
        - 0.7-1.5: 中性
        - > 1.5: 偏空
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
        'composite_score': 0,
        'composite_signal': '⚪',
        'composite_desc': '中性',
    }
    
    # Delta Ratio 分析
    delta_ratio = row.get('delta_ratio', 0)
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
    gamma_ratio = row.get('gamma_ratio', 0)
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
    pc_ratio = row.get('pc_oi_ratio', 0)
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
    
    # 综合评分 (-100 到 +100)
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
    
    return result


def analyze_volatility(row: pd.Series) -> Dict:
    """
    分析波动率指标
    """
    result = {
        'iv_1m': row.get('iv_1m', 0),
        'rv_1m': row.get('rv_1m', 0),
        'iv_rank': row.get('iv_rank', 0),
        'skew': row.get('skew', 0),
        'implied_move': row.get('implied_move', 0),
        'iv_rv_ratio': 0,
        'iv_rv_signal': '⚪',
        'iv_rv_desc': 'IV合理',
        'skew_signal': '⚪',
        'skew_desc': '正常',
        'iv_rank_signal': '⚪',
        'iv_rank_desc': '中等',
    }
    
    iv = row.get('iv_1m', 0)
    rv = row.get('rv_1m', 0)
    
    # IV vs RV 分析
    if pd.notna(iv) and pd.notna(rv) and rv > 0:
        ratio = iv / rv
        result['iv_rv_ratio'] = ratio
        
        if ratio > 1.3:
            result['iv_rv_signal'] = '🔴'
            result['iv_rv_desc'] = 'IV偏高 (可卖权)'
        elif ratio > 1.1:
            result['iv_rv_signal'] = '🟠'
            result['iv_rv_desc'] = 'IV略高'
        elif ratio < 0.8:
            result['iv_rv_signal'] = '🟢'
            result['iv_rv_desc'] = 'IV偏低 (可买权)'
        elif ratio < 0.9:
            result['iv_rv_signal'] = '🟢'
            result['iv_rv_desc'] = 'IV略低'
        else:
            result['iv_rv_signal'] = '⚪'
            result['iv_rv_desc'] = 'IV合理'
    
    # Skew 分析
    skew = row.get('skew', 0)
    if pd.notna(skew):
        if skew < -0.2:
            result['skew_signal'] = '🔴'
            result['skew_desc'] = 'Put溢价 (看跌偏斜)'
        elif skew > 0.2:
            result['skew_signal'] = '🟢'
            result['skew_desc'] = 'Call溢价 (看涨偏斜)'
        else:
            result['skew_signal'] = '⚪'
            result['skew_desc'] = '正常'
    
    # IV Rank 分析
    iv_rank = row.get('iv_rank', 0)
    if pd.notna(iv_rank):
        if iv_rank > 0.8:
            result['iv_rank_signal'] = '🔴'
            result['iv_rank_desc'] = '极高 (卖权优势)'
        elif iv_rank > 0.5:
            result['iv_rank_signal'] = '🟠'
            result['iv_rank_desc'] = '偏高'
        elif iv_rank < 0.2:
            result['iv_rank_signal'] = '🟢'
            result['iv_rank_desc'] = '极低 (买权优势)'
        elif iv_rank < 0.35:
            result['iv_rank_signal'] = '🟢'
            result['iv_rank_desc'] = '偏低'
        else:
            result['iv_rank_signal'] = '⚪'
            result['iv_rank_desc'] = '中等'
    
    return result


def generate_full_analysis(df: pd.DataFrame) -> Dict:
    """
    生成完整的SpotGamma分析报告
    
    Returns:
        包含所有分析结果的字典
    """
    result = {
        'symbols': [],
        'gamma_summary': {
            'positive_gamma': [],
            'negative_gamma': [],
        },
        'directional_summary': {
            'bullish': [],
            'bearish': [],
            'neutral': [],
        },
        'volatility_summary': {
            'iv_high': [],
            'iv_low': [],
            'skew_put': [],
            'skew_call': [],
        },
        'alerts': [],
        'analysis_by_symbol': {},
    }
    
    for _, row in df.iterrows():
        symbol = row.get('symbol', 'N/A')
        if pd.isna(symbol) or symbol == 'N/A':
            continue
        
        result['symbols'].append(symbol)
        
        # 分析各维度
        gamma_analysis = analyze_gamma_environment(row)
        directional_analysis = analyze_directional_indicators(row)
        vol_analysis = analyze_volatility(row)
        
        # 存储完整分析
        result['analysis_by_symbol'][symbol] = {
            'gamma': gamma_analysis,
            'directional': directional_analysis,
            'volatility': vol_analysis,
        }
        
        # 汇总分类
        if gamma_analysis['gamma_env'] == '正Gamma':
            result['gamma_summary']['positive_gamma'].append(symbol)
        elif gamma_analysis['gamma_env'] == '负Gamma':
            result['gamma_summary']['negative_gamma'].append(symbol)
        
        if directional_analysis['composite_score'] > 20:
            result['directional_summary']['bullish'].append(symbol)
        elif directional_analysis['composite_score'] < -30:
            result['directional_summary']['bearish'].append(symbol)
        else:
            result['directional_summary']['neutral'].append(symbol)
        
        if vol_analysis['iv_rv_desc'] == 'IV偏高 (可卖权)':
            result['volatility_summary']['iv_high'].append(symbol)
        elif vol_analysis['iv_rv_desc'] == 'IV偏低 (可买权)':
            result['volatility_summary']['iv_low'].append(symbol)
        
        if vol_analysis['skew_desc'] == 'Put溢价 (看跌偏斜)':
            result['volatility_summary']['skew_put'].append(symbol)
        elif vol_analysis['skew_desc'] == 'Call溢价 (看涨偏斜)':
            result['volatility_summary']['skew_call'].append(symbol)
        
        # 生成预警
        # 1. 负Gamma + 偏空 = 高风险
        if gamma_analysis['gamma_env'] == '负Gamma' and directional_analysis['composite_score'] < -30:
            result['alerts'].append({
                'symbol': symbol,
                'level': 'high',
                'message': f'{symbol}: 负Gamma + 方向偏空，下跌可能加速'
            })
        
        # 2. Gamma Ratio > 2.5 = 下跌加速风险
        gamma_ratio = row.get('gamma_ratio', 0)
        if pd.notna(gamma_ratio) and gamma_ratio > 2.5:
            result['alerts'].append({
                'symbol': symbol,
                'level': 'medium',
                'message': f'{symbol}: Gamma Ratio={gamma_ratio:.1f}，Put Gamma主导'
            })
        
        # 3. Delta Ratio 极端
        delta_ratio = row.get('delta_ratio', 0)
        if pd.notna(delta_ratio) and delta_ratio < -5:
            result['alerts'].append({
                'symbol': symbol,
                'level': 'medium',
                'message': f'{symbol}: Delta Ratio={delta_ratio:.1f}，强烈偏空持仓'
            })
    
    return result


def get_key_levels_for_symbol(df: pd.DataFrame, symbol: str) -> Optional[Dict]:
    """
    获取特定标的的关键位
    """
    row = df[df['symbol'] == symbol]
    if row.empty:
        return None
    
    row = row.iloc[0]
    
    return {
        'symbol': symbol,
        'price': row.get('price', 0),
        'zero_gamma': row.get('zero_gamma', 0),
        'call_wall': row.get('call_wall', 0),
        'put_wall': row.get('put_wall', 0),
        'hedge_wall': row.get('hedge_wall', 0),
    }


def create_levels_visualization_data(analysis: Dict, symbols: List[str] = None) -> List[Dict]:
    """
    创建关键位可视化数据
    """
    if symbols is None:
        symbols = analysis.get('symbols', [])
    
    viz_data = []
    
    for sym in symbols:
        sym_analysis = analysis['analysis_by_symbol'].get(sym)
        if not sym_analysis:
            continue
        
        gamma = sym_analysis['gamma']
        
        viz_data.append({
            'symbol': sym,
            'price': gamma['price'],
            'put_wall': gamma['put_wall'],
            'zero_gamma': gamma['zero_gamma'],
            'call_wall': gamma['call_wall'],
            'gamma_env': gamma['gamma_env'],
            'gamma_env_emoji': gamma['gamma_env_emoji'],
        })
    
    return viz_data


# ==================== Streamlit 显示函数 ====================

def render_spotgamma_section(df: pd.DataFrame, st_module):
    """
    在Streamlit中渲染SpotGamma分析章节
    
    Args:
        df: 解析后的SpotGamma DataFrame
        st_module: streamlit模块引用
    """
    st = st_module
    
    # 生成完整分析
    analysis = generate_full_analysis(df)
    
    # ===== 1. Gamma环境总览 =====
    st.markdown("### 🎯 Gamma环境总览")
    
    pos_gamma = analysis['gamma_summary']['positive_gamma']
    neg_gamma = analysis['gamma_summary']['negative_gamma']
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("正Gamma", len(pos_gamma), help="价格在Zero Gamma之上，波动抑制")
        if pos_gamma:
            st.success(", ".join(pos_gamma[:8]))
    
    with col2:
        st.metric("负Gamma", len(neg_gamma), help="价格在Zero Gamma之下，波动放大")
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
    
    # ===== 2. 关键位地图 =====
    st.markdown("### 📍 关键位地图")
    
    # 选择要显示的标的
    key_symbols = ['NDX', 'QQQ', 'SPY', 'IWM', 'SPX']
    display_symbols = [s for s in key_symbols if s in analysis['symbols']]
    if not display_symbols:
        display_symbols = analysis['symbols'][:6]
    
    # 创建关键位表格
    levels_data = []
    for sym in display_symbols:
        sym_data = analysis['analysis_by_symbol'].get(sym)
        if sym_data:
            g = sym_data['gamma']
            levels_data.append({
                '标的': sym,
                '价格': f"${g['price']:.2f}" if g['price'] else 'N/A',
                'Put Wall': f"${g['put_wall']:.0f}" if g['put_wall'] else 'N/A',
                'Zero Gamma': f"${g['zero_gamma']:.0f}" if g['zero_gamma'] else 'N/A',
                'Call Wall': f"${g['call_wall']:.0f}" if g['call_wall'] else 'N/A',
                'Gamma环境': f"{g['gamma_env_emoji']} {g['gamma_env']}",
                '距Call Wall': f"{g['dist_to_call_wall']:+.1f}%" if g['dist_to_call_wall'] else 'N/A',
                '距Put Wall': f"-{g['dist_to_put_wall']:.1f}%" if g['dist_to_put_wall'] else 'N/A',
            })
    
    if levels_data:
        st.dataframe(pd.DataFrame(levels_data), use_container_width=True, hide_index=True)
    
    # ===== 3. 方向性指标 =====
    st.markdown("### 📊 方向性指标分析")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        bullish = analysis['directional_summary']['bullish']
        st.markdown("**🟢 看多信号**")
        if bullish:
            for sym in bullish[:5]:
                score = analysis['analysis_by_symbol'][sym]['directional']['composite_score']
                st.markdown(f"- {sym}: +{score}")
        else:
            st.caption("无")
    
    with col2:
        neutral = analysis['directional_summary']['neutral']
        st.markdown("**⚪ 中性**")
        if neutral:
            st.caption(", ".join(neutral[:8]))
        else:
            st.caption("无")
    
    with col3:
        bearish = analysis['directional_summary']['bearish']
        st.markdown("**🔴 看空信号**")
        if bearish:
            for sym in bearish[:5]:
                score = analysis['analysis_by_symbol'][sym]['directional']['composite_score']
                st.markdown(f"- {sym}: {score}")
        else:
            st.caption("无")
    
    # 方向性详细表格
    with st.expander("📋 方向性指标详情", expanded=False):
        dir_data = []
        for sym in analysis['symbols']:
            sym_data = analysis['analysis_by_symbol'].get(sym)
            if sym_data:
                d = sym_data['directional']
                dir_data.append({
                    '标的': sym,
                    'Delta Ratio': f"{d['delta_ratio']:.2f}" if d['delta_ratio'] else 'N/A',
                    'Delta信号': f"{d['delta_signal']} {d['delta_desc']}",
                    'Gamma Ratio': f"{d['gamma_ratio']:.2f}" if d['gamma_ratio'] else 'N/A',
                    'Gamma信号': f"{d['gamma_signal']} {d['gamma_desc']}",
                    'P/C OI': f"{d['pc_oi_ratio']:.2f}" if d['pc_oi_ratio'] else 'N/A',
                    'P/C信号': f"{d['pc_signal']} {d['pc_desc']}",
                    '综合': f"{d['composite_signal']} {d['composite_score']:+.0f}",
                })
        
        if dir_data:
            st.dataframe(pd.DataFrame(dir_data), use_container_width=True, hide_index=True)
    
    # ===== 4. 波动率洞察 =====
    st.markdown("### 📈 波动率洞察")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**IV vs RV**")
        iv_high = analysis['volatility_summary']['iv_high']
        iv_low = analysis['volatility_summary']['iv_low']
        
        if iv_high:
            st.error(f"🔴 IV偏高 (可卖权): {', '.join(iv_high[:6])}")
        if iv_low:
            st.success(f"🟢 IV偏低 (可买权): {', '.join(iv_low[:6])}")
        if not iv_high and not iv_low:
            st.info("⚪ IV普遍合理")
    
    with col2:
        st.markdown("**Skew 偏斜**")
        skew_put = analysis['volatility_summary']['skew_put']
        skew_call = analysis['volatility_summary']['skew_call']
        
        if skew_put:
            st.warning(f"🔴 Put溢价 (看跌偏斜): {', '.join(skew_put[:6])}")
        if skew_call:
            st.success(f"🟢 Call溢价 (看涨偏斜): {', '.join(skew_call[:6])}")
        if not skew_put and not skew_call:
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
                    'IV/RV': f"{v['iv_rv_signal']} {v['iv_rv_desc']}",
                    'IV Rank': f"{v['iv_rank']*100:.0f}%" if v['iv_rank'] else 'N/A',
                    'IV Rank信号': f"{v['iv_rank_signal']} {v['iv_rank_desc']}",
                    'Skew': f"{v['skew']:.3f}" if v['skew'] else 'N/A',
                    'Skew信号': f"{v['skew_signal']} {v['skew_desc']}",
                    '隐含波动': f"±${v['implied_move']:.2f}" if v['implied_move'] else 'N/A',
                })
        
        if vol_data:
            st.dataframe(pd.DataFrame(vol_data), use_container_width=True, hide_index=True)
    
    # ===== 5. 风险预警 =====
    if analysis['alerts']:
        st.markdown("### ⚠️ 风险预警")
        
        for alert in analysis['alerts']:
            if alert['level'] == 'high':
                st.error(f"🚨 {alert['message']}")
            else:
                st.warning(f"⚠️ {alert['message']}")
    
    # ===== 6. 交易提示 =====
    st.markdown("### 💡 交易提示")
    
    tips = []
    
    # 正Gamma环境提示
    if len(pos_gamma) > len(neg_gamma):
        tips.append("✅ **正Gamma主导**: 适合均值回归策略，Call Wall附近可考虑卖Call")
    else:
        tips.append("⚠️ **负Gamma主导**: 趋势可能延续，避免逆势操作")
    
    # IV提示
    if iv_high:
        tips.append(f"📉 **卖权机会**: {', '.join(iv_high[:3])} IV偏高，可考虑卖出策略")
    if iv_low:
        tips.append(f"📈 **买权机会**: {', '.join(iv_low[:3])} IV偏低，可考虑买入策略")
    
    # 方向性提示
    if bullish:
        tips.append(f"🟢 **看多标的**: {', '.join(bullish[:3])} 期权持仓偏多")
    if bearish:
        tips.append(f"🔴 **看空标的**: {', '.join(bearish[:3])} 期权持仓偏空")
    
    for tip in tips:
        st.markdown(tip)
    
    return analysis
