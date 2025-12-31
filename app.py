"""
宏观战情室 V2 - Streamlit 主程序
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import os

# 设置页面配置
st.set_page_config(
    page_title="宏观战情室 V2",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 导入自定义模块
from data_fetcher import DataFetcher
from indicators import IndicatorCalculator
from scoring import ScoringSystem
from prompt_generator import generate_claude_prompt, generate_short_summary
from config import COLORS, get_score_color, ALERT_THRESHOLDS

# ==================== 样式 ====================

st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        text-align: center;
        padding: 1rem;
        background: linear-gradient(90deg, #1a1a2e 0%, #16213e 100%);
        border-radius: 10px;
        margin-bottom: 2rem;
    }
    .chapter-header {
        font-size: 1.5rem;
        font-weight: bold;
        color: #00d4ff;
        border-bottom: 2px solid #00d4ff;
        padding-bottom: 0.5rem;
        margin: 1.5rem 0 1rem 0;
    }
    .metric-card {
        background: #1e1e2e;
        border-radius: 10px;
        padding: 1rem;
        text-align: center;
    }
    .score-display {
        font-size: 3rem;
        font-weight: bold;
    }
    .alert-box {
        padding: 1rem;
        border-radius: 8px;
        margin: 0.5rem 0;
    }
    .alert-extreme {
        background: rgba(255, 23, 68, 0.2);
        border-left: 4px solid #FF1744;
    }
    .alert-warning {
        background: rgba(255, 214, 0, 0.2);
        border-left: 4px solid #FFD600;
    }
</style>
""", unsafe_allow_html=True)

# ==================== 缓存数据加载 ====================

@st.cache_data(ttl=3600)
def load_data(force_refresh=False):
    """加载数据"""
    fetcher = DataFetcher()
    return fetcher.fetch_all_data(force_refresh=force_refresh)

@st.cache_data(ttl=3600)
def compute_indicators(_all_data):
    """计算指标"""
    calc = IndicatorCalculator(_all_data)
    return calc.calc_all_indicators()

# ==================== 图表函数 ====================

def create_gauge_chart(score, title="综合评分"):
    """创建仪表盘图表"""
    color = get_score_color(score)
    
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        domain={'x': [0, 1], 'y': [0, 1]},
        title={'text': title, 'font': {'size': 20, 'color': 'white'}},
        number={'font': {'size': 40, 'color': 'white'}},
        gauge={
            'axis': {'range': [-100, 100], 'tickwidth': 1, 'tickcolor': "white"},
            'bar': {'color': color},
            'bgcolor': "rgba(0,0,0,0)",
            'borderwidth': 2,
            'bordercolor': "gray",
            'steps': [
                {'range': [-100, -50], 'color': 'rgba(255,23,68,0.3)'},
                {'range': [-50, -20], 'color': 'rgba(255,152,0,0.3)'},
                {'range': [-20, 20], 'color': 'rgba(255,214,0,0.3)'},
                {'range': [20, 50], 'color': 'rgba(76,175,80,0.3)'},
                {'range': [50, 100], 'color': 'rgba(0,200,83,0.3)'},
            ],
            'threshold': {
                'line': {'color': "white", 'width': 4},
                'thickness': 0.75,
                'value': score
            }
        }
    ))
    
    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font={'color': 'white'},
        height=300,
        margin=dict(l=20, r=20, t=50, b=20)
    )
    
    return fig

def create_score_bar(scores):
    """创建子评分条形图"""
    categories = ['流动性', '货币环境', '全球轮动', '美股结构']
    values = [
        scores['liquidity']['score'],
        scores['currency']['score'],
        scores['rotation']['score'],
        scores['us_structure']['score'],
    ]
    colors = [get_score_color(v) for v in values]
    
    fig = go.Figure(go.Bar(
        x=values,
        y=categories,
        orientation='h',
        marker_color=colors,
        text=[f'{v:.0f}' for v in values],
        textposition='inside',
    ))
    
    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font={'color': 'white'},
        height=200,
        margin=dict(l=100, r=20, t=20, b=20),
        xaxis=dict(range=[-100, 100], showgrid=True, gridcolor='rgba(255,255,255,0.1)'),
        yaxis=dict(showgrid=False),
    )
    
    return fig

def create_rotation_chart(rankings):
    """创建轮动排行图"""
    if not rankings:
        return None
        
    names = [r['name'] for r in rankings[:10]]
    z_values = [r['z'] for r in rankings[:10]]
    colors = ['#00C853' if z > 0 else '#FF1744' for z in z_values]
    
    fig = go.Figure(go.Bar(
        x=z_values,
        y=names,
        orientation='h',
        marker_color=colors,
        text=[f'{z:.2f}σ' for z in z_values],
        textposition='outside',
    ))
    
    fig.add_vline(x=0, line_color='white', line_dash='dash')
    fig.add_vline(x=2, line_color='#00C853', line_dash='dot', opacity=0.5)
    fig.add_vline(x=-2, line_color='#FF1744', line_dash='dot', opacity=0.5)
    
    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font={'color': 'white'},
        height=400,
        margin=dict(l=100, r=50, t=20, b=20),
        xaxis=dict(title='Z-Score (vs SPY)', showgrid=True, gridcolor='rgba(255,255,255,0.1)'),
        yaxis=dict(showgrid=False),
    )
    
    return fig

def create_liquidity_chart(liq_data, yahoo_data):
    """创建流动性图表"""
    if 'net_liquidity' not in liq_data or 'series' not in liq_data['net_liquidity']:
        return None
        
    net_liq = liq_data['net_liquidity']['series']
    
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    fig.add_trace(
        go.Scatter(
            x=net_liq.index,
            y=net_liq.values,
            name='净流动性 (万亿)',
            line=dict(color='#00d4ff', width=2),
            fill='tozeroy',
            fillcolor='rgba(0,212,255,0.1)',
        ),
        secondary_y=False,
    )
    
    if yahoo_data is not None and 'SPY' in yahoo_data.columns:
        spy = yahoo_data['SPY'].dropna()
        common_idx = net_liq.index.intersection(spy.index)
        if len(common_idx) > 0:
            fig.add_trace(
                go.Scatter(
                    x=spy.loc[common_idx].index,
                    y=spy.loc[common_idx].values,
                    name='SPY',
                    line=dict(color='#FFD600', width=1),
                    opacity=0.7,
                ),
                secondary_y=True,
            )
    
    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font={'color': 'white'},
        height=350,
        margin=dict(l=50, r=50, t=30, b=30),
        legend=dict(orientation='h', yanchor='bottom', y=1.02),
        hovermode='x unified',
    )
    
    fig.update_xaxes(showgrid=True, gridcolor='rgba(255,255,255,0.1)')
    fig.update_yaxes(title_text='净流动性 (万亿美元)', secondary_y=False, showgrid=True, gridcolor='rgba(255,255,255,0.1)')
    fig.update_yaxes(title_text='SPY', secondary_y=True, showgrid=False)
    
    return fig

def create_currency_chart(yahoo_data):
    """创建货币图表"""
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1,
                       subplot_titles=('DXY 美元指数', 'USD/JPY'))
    
    if yahoo_data is not None and 'DX-Y.NYB' in yahoo_data.columns:
        dxy = yahoo_data['DX-Y.NYB'].dropna()
        fig.add_trace(
            go.Scatter(x=dxy.index, y=dxy.values, name='DXY', line=dict(color='#00d4ff')),
            row=1, col=1
        )
        ma20 = dxy.rolling(20).mean()
        ma50 = dxy.rolling(50).mean()
        fig.add_trace(
            go.Scatter(x=ma20.index, y=ma20.values, name='MA20', line=dict(color='#FFD600', width=1, dash='dot')),
            row=1, col=1
        )
        fig.add_trace(
            go.Scatter(x=ma50.index, y=ma50.values, name='MA50', line=dict(color='#FF9800', width=1, dash='dash')),
            row=1, col=1
        )
    
    if yahoo_data is not None and 'JPY=X' in yahoo_data.columns:
        usdjpy = yahoo_data['JPY=X'].dropna()
        fig.add_trace(
            go.Scatter(x=usdjpy.index, y=usdjpy.values, name='USD/JPY', line=dict(color='#E91E63')),
            row=2, col=1
        )
        fig.add_hline(y=150, line_dash='dash', line_color='#00C853', opacity=0.5, row=2, col=1)
        fig.add_hline(y=160, line_dash='dash', line_color='#FF1744', opacity=0.5, row=2, col=1)
    
    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font={'color': 'white'},
        height=450,
        margin=dict(l=50, r=30, t=50, b=30),
        showlegend=True,
        legend=dict(orientation='h', yanchor='bottom', y=1.02),
    )
    
    fig.update_xaxes(showgrid=True, gridcolor='rgba(255,255,255,0.1)')
    fig.update_yaxes(showgrid=True, gridcolor='rgba(255,255,255,0.1)')
    
    return fig

# ==================== 主程序 ====================

def main():
    st.markdown('<div class="main-header">🌍 宏观战情室 V2</div>', unsafe_allow_html=True)
    
    with st.sidebar:
        st.header("⚙️ 控制面板")
        
        if st.button("🔄 刷新数据", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        
        st.divider()
        
        show_charts = st.checkbox("显示图表", value=True)
        show_details = st.checkbox("显示详细数据", value=False)
    
    with st.spinner("正在加载数据..."):
        all_data = load_data()
        
    if all_data['yahoo'].empty and all_data['fred'].empty:
        st.error("数据加载失败，请检查网络连接后刷新页面")
        return
    
    with st.spinner("正在计算指标..."):
        indicators = compute_indicators(all_data)
    
    scorer = ScoringSystem(indicators)
    scores = scorer.calc_total_score()
    
    st.markdown(f"**数据更新时间:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    # ==================== 综合评估 ====================
    
    st.markdown('<div class="chapter-header">📊 综合评估</div>', unsafe_allow_html=True)
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        total_score = scores['total']['score']
        fig_gauge = create_gauge_chart(total_score, "宏观综合评分")
        st.plotly_chart(fig_gauge, use_container_width=True)
        st.markdown(f"**解读:** {scores['total']['interpretation']}")
    
    with col2:
        fig_bar = create_score_bar(scores)
        st.plotly_chart(fig_bar, use_container_width=True)
        
        col2a, col2b = st.columns(2)
        with col2a:
            favorable = scorer.get_favorable_assets()
            st.markdown("**🟢 有利资产:**")
            st.markdown(", ".join(favorable[:5]) if favorable else "无明显有利资产")
        with col2b:
            unfavorable = scorer.get_unfavorable_assets()
            st.markdown("**🔴 不利资产:**")
            st.markdown(", ".join(unfavorable[:5]) if unfavorable else "无明显不利资产")
    
    # ==================== 预警信号 ====================
    
    alerts = scorer.get_alerts()
    if alerts:
        st.markdown('<div class="chapter-header">🚨 预警信号</div>', unsafe_allow_html=True)
        
        for alert in alerts[:8]:
            level_class = 'alert-extreme' if alert['level'] == 'extreme' else 'alert-warning'
            level_emoji = '🔴' if alert['level'] == 'extreme' else '🟡'
            
            st.markdown(f"""
            <div class="alert-box {level_class}">
                {level_emoji} <strong>[{alert['category']}] {alert['indicator']}</strong>: Z={alert['z']:.2f}σ<br>
                → {alert['message']}
            </div>
            """, unsafe_allow_html=True)
    
    # ==================== 第一章：流动性 ====================
    
    st.markdown('<div class="chapter-header">🌊 第一章：流动性水位</div>', unsafe_allow_html=True)
    st.markdown('*"钱从哪里来?有多少?"*')
    
    liq = indicators.get('liquidity', {})
    
    cols = st.columns(5)
    
    with cols[0]:
        net_liq = liq.get('net_liquidity', {})
        st.metric(
            "净流动性 (万亿)",
            f"${net_liq.get('latest', 0):.2f}T",
            f"{net_liq.get('change_20d', 0):.1f}% (20d)",
            delta_color="normal"
        )
    
    with cols[1]:
        rrp = liq.get('rrp', {})
        st.metric(
            "RRP逆回购",
            f"${rrp.get('latest', 0):.0f}B",
            f"{rrp.get('change_1d', 0):.0f}B",
            delta_color="inverse"
        )
    
    with cols[2]:
        tga = liq.get('tga', {})
        st.metric(
            "TGA财政账户",
            f"${tga.get('latest', 0):.0f}B",
            f"{tga.get('change_1d', 0):.0f}B",
            delta_color="inverse"
        )
    
    with cols[3]:
        hyg_lqd = liq.get('hyg_lqd', {})
        st.metric(
            "HYG/LQD",
            f"{hyg_lqd.get('latest', 0):.3f}",
            f"Z: {hyg_lqd.get('z_60d', 0):.2f}σ"
        )
    
    with cols[4]:
        liq_score_val = scores['liquidity']['score']
        st.metric("💧 流动性评分", f"{liq_score_val:.0f}/100")
    
    if show_charts:
        fig_liq = create_liquidity_chart(liq, all_data.get('yahoo'))
        if fig_liq:
            st.plotly_chart(fig_liq, use_container_width=True)
    
    # ==================== 第二章：货币/利率 ====================
    
    st.markdown('<div class="chapter-header">💱 第二章：货币与利率风向</div>', unsafe_allow_html=True)
    st.markdown('*"钱更愿意待在哪种货币/资产里?"*')
    
    curr = indicators.get('currency', {})
    
    cols = st.columns(6)
    
    with cols[0]:
        dxy = curr.get('dxy', {})
        st.metric("DXY美元指数", f"{dxy.get('latest', 0):.2f}", f"{dxy.get('trend', 'N/A')} {dxy.get('trend_emoji', '')}")
    
    with cols[1]:
        usdjpy = curr.get('usdjpy', {})
        st.metric("USD/JPY", f"{usdjpy.get('latest', 0):.2f}", f"Carry风险: {usdjpy.get('carry_risk', 'N/A')}")
    
    with cols[2]:
        real_rate = curr.get('real_rate', {})
        st.metric("实际利率", f"{real_rate.get('latest', 0):.2f}%", f"{real_rate.get('trend', 'N/A')} {real_rate.get('trend_emoji', '')}")
    
    with cols[3]:
        term_spread = curr.get('term_spread', {})
        st.metric("10Y-3M利差", f"{term_spread.get('latest', 0):.2f}%", f"{term_spread.get('curve_shape', 'N/A')}")
    
    with cols[4]:
        vix = curr.get('vix', {})
        st.metric("VIX", f"{vix.get('latest', 0):.1f}")
    
    with cols[5]:
        curr_score_val = scores['currency']['score']
        st.metric("🧭 货币环境评分", f"{curr_score_val:.0f}/100")
    
    st.markdown("**📅 央行政策预期 (代理指标)**")
    
    col1, col2 = st.columns(2)
    
    with col1:
        fed = curr.get('fed_policy', {})
        st.markdown(f"""
        **🇺🇸 Fed政策信号:**
        - 2Y国债: {fed.get('dgs2', 0):.2f}% | 当前Fed利率: {fed.get('current_rate', 0):.2f}%
        - 利差信号: {fed.get('signal', 0):.2f}%
        - **市场预期: {fed.get('outlook', 'N/A')}**
        """)
    
    with col2:
        boj = curr.get('boj_policy', {})
        st.markdown(f"""
        **🇯🇵 BOJ政策信号:**
        - USD/JPY 20日动量: {boj.get('usdjpy_momentum', 0):.1f}%
        - 当前BOJ利率: {boj.get('current_rate', 0):.2f}%
        - **市场预期: {boj.get('outlook', 'N/A')}**
        """)
    
    if show_charts:
        fig_curr = create_currency_chart(all_data.get('yahoo'))
        if fig_curr:
            st.plotly_chart(fig_curr, use_container_width=True)
    
    # ==================== 第三章：全球轮动 ====================
    
    st.markdown('<div class="chapter-header">🌍 第三章：全球资产轮动雷达</div>', unsafe_allow_html=True)
    st.markdown('*"资金在全球怎么流动?"*')
    
    rot = indicators.get('rotation', {})
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("**相对强度排行 (vs SPY, 20日RS, Z-Score)**")
        rankings = rot.get('rankings', [])
        if rankings and show_charts:
            fig_rot = create_rotation_chart(rankings)
            if fig_rot:
                st.plotly_chart(fig_rot, use_container_width=True)
    
    with col2:
        st.markdown("**极端情绪指标**")
        extreme = rot.get('extreme_sentiment', {})
        for ticker, data in extreme.items():
            z = data.get('z', 0)
            emoji = '🟢' if z > 1 else '🔴' if z < -1 else '⚪'
            st.markdown(f"""
            **{data.get('name', ticker)}**
            - Z-Score: {z:.2f}σ {emoji}
            - 信号: {data.get('sentiment', 'N/A')}
            """)
        
        st.markdown("---")
        rot_score_val = scores['rotation']['score']
        st.metric("🌐 轮动评分", f"{rot_score_val:.0f}/100")
    
    # ==================== 第四章：美股结构 ====================
    
    st.markdown('<div class="chapter-header">🇺🇸 第四章：美股内部结构</div>', unsafe_allow_html=True)
    st.markdown('*"美股内部,钱在怎么转?"*')
    
    us = indicators.get('us_structure', {})
    
    cols = st.columns(3)
    
    with cols[0]:
        st.markdown("**风险偏好因子**")
        risk_factors = us.get('risk_appetite', [])
        if risk_factors:
            for f in risk_factors:
                emoji = f.get('emoji', '⚪')
                st.markdown(f"{emoji} {f['name']}: **{f['z']:.2f}σ**")
    
    with cols[1]:
        st.markdown("**板块轮动因子**")
        sector_factors = us.get('sector_rotation', [])
        if sector_factors:
            for f in sector_factors:
                emoji = f.get('emoji', '⚪')
                st.markdown(f"{emoji} {f['name']}: **{f['z']:.2f}σ**")
    
    with cols[2]:
        st.markdown("**市场广度因子**")
        breadth_factors = us.get('breadth', [])
        if breadth_factors:
            for f in breadth_factors:
                emoji = f.get('emoji', '⚪')
                st.markdown(f"{emoji} {f['name']}: **{f['z']:.2f}σ**")
    
    us_score_val = scores['us_structure']['score']
    st.metric("🏛️ 美股结构评分", f"{us_score_val:.0f}/100")
    
    # ==================== 附录 ====================
    
    with st.expander("📖 附录：指标解读手册"):
        st.markdown("""
        ### 流动性指标
        
        **净流动性 (Net Liquidity)**
        - 公式: Fed资产负债表 - 逆回购(RRP) - 财政部账户(TGA)
        - 解读: 衡量实际流入金融市场的美元数量。上升=利好风险资产
        
        **RRP (逆回购)**
        - 作用: 流动性蓄水池，Fed回收市场上多余的美元
        - 解读: RRP下降=流动性释放到市场=利好
        
        **TGA (财政部账户)**
        - 作用: 财政部在Fed的现金账户
        - 解读: TGA下降=财政部花钱=流动性注入市场=利好
        
        **HYG/LQD**
        - 高收益债ETF / 投资级债ETF的比值
        - 解读: 比值上升=市场风险偏好上升
        
        ### 货币/利率指标
        
        **DXY美元指数**
        - 衡量美元对一篮子货币的强弱
        - 解读: 弱美元利好商品、新兴市场、加密货币
        
        **USD/JPY**
        - 美元/日元汇率，Carry Trade风向标
        - 解读: 日元快速走强=Carry平仓风险=全球Risk-off
        
        **实际利率**
        - 10Y国债收益率 - 10Y盈亏平衡通胀
        - 解读: 实际利率下降利好黄金和成长股
        
        **10Y-3M利差**
        - 收益率曲线斜率
        - 解读: 倒挂=衰退预警；陡峭化=经济预期改善
        
        ### 评分系统
        
        - **Z-Score**: 衡量当前值偏离过去60天均值的标准差数量
        - **|Z| > 2**: 极端水平，触发预警
        - **评分范围**: -100到+100，正分利好风险资产
        """)
    
    # ==================== Claude入口 ====================
    
    st.markdown('<div class="chapter-header">🤖 Claude分析入口</div>', unsafe_allow_html=True)
    
    prompt = generate_claude_prompt(indicators, scores, scorer)
    
    st.markdown("点击下方按钮复制数据摘要，粘贴给Claude进行深度分析：")
    
    with st.expander("📋 查看完整Prompt", expanded=False):
        st.code(prompt, language="markdown")
    
    st.markdown("**📊 快速摘要:**")
    short_summary = generate_short_summary(indicators, scores, scorer)
    st.code(short_summary, language="text")
    
    st.markdown("---")
    st.markdown(f"*宏观战情室 V2 | 数据来源: FRED, Yahoo Finance, AKShare | 更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}*")


if __name__ == '__main__':
    main()
