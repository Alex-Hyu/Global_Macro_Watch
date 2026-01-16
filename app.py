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

# 导入新模块
try:
    from rotation_scanner import (
        get_sofr_repo_history, 
        get_rrp_tga_history,
        scan_etf_flows,
        get_etf_flow_summary,
        calculate_breadth_radar,
        calculate_rotation_score,
        SECTOR_ETFS,
    )
    ROTATION_SCANNER_AVAILABLE = True
except ImportError:
    ROTATION_SCANNER_AVAILABLE = False

# 导入SpotGamma模块 (增强版)
try:
    from spotgamma_analyzer import (
        parse_spotgamma_csv,
        generate_full_analysis,
        render_spotgamma_section,
        get_gamma_summary,
        SpotGammaAnalyzer,
        GammaEnvironment,
        MarketBias,
        RiskLevel,
    )
    SPOTGAMMA_AVAILABLE = True
except ImportError:
    SPOTGAMMA_AVAILABLE = False

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


# ==================== 新增图表函数 ====================

def create_sofr_repo_chart(sofr_data):
    """创建SOFR/Repo利差图表"""
    if not sofr_data.get('dates'):
        return None
    
    fig = make_subplots(
        rows=2, cols=1, 
        shared_xaxes=True, 
        vertical_spacing=0.12,
        row_heights=[0.6, 0.4],
        subplot_titles=('SOFR vs Repo (TGCR) 利率', 'SOFR-Repo 利差')
    )
    
    # 上图：SOFR和TGCR利率
    fig.add_trace(
        go.Scatter(
            x=sofr_data['dates'], 
            y=sofr_data['sofr'],
            name='SOFR', 
            line=dict(color='#0d6efd', width=2)
        ),
        row=1, col=1
    )
    
    fig.add_trace(
        go.Scatter(
            x=sofr_data['dates'], 
            y=sofr_data['tgcr'],
            name='Repo (TGCR)', 
            line=dict(color='#198754', width=2)
        ),
        row=1, col=1
    )
    
    # 下图：利差柱状图
    spread_colors = ['#dc3545' if s > 0.05 else '#ffc107' if s > 0.02 else '#198754' 
                     for s in sofr_data['spread']]
    
    fig.add_trace(
        go.Bar(
            x=sofr_data['dates'], 
            y=sofr_data['spread'],
            name='利差', 
            marker_color=spread_colors
        ),
        row=2, col=1
    )
    
    # 添加警戒线
    fig.add_hline(y=0.05, line_dash="dash", line_color="red", 
                  annotation_text="警戒线 0.05%", row=2, col=1)
    
    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font={'color': 'white'},
        height=350,
        margin=dict(l=50, r=30, t=50, b=30),
        showlegend=True,
        legend=dict(orientation='h', yanchor='bottom', y=1.02),
    )
    
    fig.update_xaxes(showgrid=True, gridcolor='rgba(255,255,255,0.1)')
    fig.update_yaxes(showgrid=True, gridcolor='rgba(255,255,255,0.1)')
    
    return fig


def create_radar_chart(radar_data):
    """创建市场广度雷达图"""
    categories = radar_data['categories']
    values = radar_data['normalized']
    
    # 闭合雷达图
    categories_closed = categories + [categories[0]]
    values_closed = values + [values[0]]
    
    fig = go.Figure()
    
    # 当前值
    fig.add_trace(go.Scatterpolar(
        r=values_closed,
        theta=categories_closed,
        fill='toself',
        fillcolor='rgba(0,212,255,0.2)',
        line=dict(color='#00d4ff', width=2),
        name='当前'
    ))
    
    # 中性线 (50)
    fig.add_trace(go.Scatterpolar(
        r=[50] * len(categories_closed),
        theta=categories_closed,
        mode='lines',
        line=dict(color='gray', dash='dash', width=1),
        name='中性线'
    ))
    
    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 100],
                tickfont=dict(size=10, color='white'),
                gridcolor='rgba(255,255,255,0.2)',
            ),
            angularaxis=dict(
                tickfont=dict(size=12, color='white'),
                gridcolor='rgba(255,255,255,0.2)',
            ),
            bgcolor='rgba(0,0,0,0)',
        ),
        paper_bgcolor='rgba(0,0,0,0)',
        font={'color': 'white'},
        showlegend=False,
        height=350,
        margin=dict(l=60, r=60, t=30, b=30),
    )
    
    return fig


def create_rotation_gauge(score, title="资金轮动评分"):
    """创建资金轮动仪表盘"""
    # 确定颜色
    if score > 60:
        bar_color = '#00C853'
    elif score > 20:
        bar_color = '#90EE90'
    elif score > -20:
        bar_color = '#FFD600'
    elif score > -60:
        bar_color = '#FF9800'
    else:
        bar_color = '#FF1744'
    
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=score,
        domain={'x': [0, 1], 'y': [0, 1]},
        title={'text': title, 'font': {'size': 18, 'color': 'white'}},
        delta={'reference': 0, 'increasing': {'color': "green"}, 'decreasing': {'color': "red"}},
        number={'font': {'size': 36, 'color': 'white'}},
        gauge={
            'axis': {'range': [-100, 100], 'tickwidth': 1, 'tickcolor': "white", 'tickfont': {'color': 'white'}},
            'bar': {'color': bar_color},
            'bgcolor': "rgba(0,0,0,0)",
            'borderwidth': 2,
            'bordercolor': "gray",
            'steps': [
                {'range': [-100, -60], 'color': 'rgba(255,23,68,0.3)'},
                {'range': [-60, -20], 'color': 'rgba(255,152,0,0.3)'},
                {'range': [-20, 20], 'color': 'rgba(255,214,0,0.3)'},
                {'range': [20, 60], 'color': 'rgba(144,238,144,0.3)'},
                {'range': [60, 100], 'color': 'rgba(0,200,83,0.3)'},
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
        height=280,
        margin=dict(l=20, r=20, t=50, b=20)
    )
    
    return fig

# ==================== 主程序 ====================

def main():
    st.markdown('<div class="main-header">🌍 宏观战情室 V2</div>', unsafe_allow_html=True)
    
    # 初始化快照管理器
    from snapshot_manager import SnapshotManager
    snapshot_mgr = SnapshotManager()
    
    with st.sidebar:
        st.header("⚙️ 控制面板")
        
        if st.button("🔄 刷新数据", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        
        st.divider()
        
        show_charts = st.checkbox("显示图表", value=True)
        show_details = st.checkbox("显示详细数据", value=False)
        
        # ==================== 快照管理 ====================
        st.divider()
        st.subheader("📸 数据快照")
        
        # 获取快照统计
        snapshot_stats = snapshot_mgr.get_snapshot_stats()
        
        # 显示状态
        if snapshot_stats['today_saved']:
            st.success("✅ 今日快照已保存")
        else:
            st.warning("❌ 今日快照未保存")
        
        # 显示历史统计
        if snapshot_stats['count'] > 0:
            st.caption(f"历史记录: {snapshot_stats['count']} 天")
            st.caption(f"最早: {snapshot_stats['earliest_date']}")
            st.caption(f"最新: {snapshot_stats['latest_date']}")
        else:
            st.caption("暂无历史记录")
        
        # ==================== SpotGamma 数据上传 ====================
        if SPOTGAMMA_AVAILABLE:
            st.divider()
            st.subheader("📊 SpotGamma数据")
            
            spotgamma_file = st.file_uploader(
                "上传SpotGamma CSV",
                type=['csv'],
                help="从SpotGamma Data Table导出CSV文件（支持多日期累积数据）",
                key="spotgamma_upload"
            )
            
            if spotgamma_file is not None:
                # 预读取CSV检查是否有日期列
                spotgamma_file.seek(0)
                try:
                    preview_df = pd.read_csv(spotgamma_file)
                    spotgamma_file.seek(0)
                    
                    # 检查是否有日期列
                    date_col = None
                    for col in ['DA', 'Date', 'date', 'DATE', '日期']:
                        if col in preview_df.columns:
                            date_col = col
                            break
                    
                    if date_col:
                        # 解析日期列
                        preview_df[date_col] = pd.to_datetime(preview_df[date_col], format='mixed', errors='coerce')
                        available_dates = preview_df[date_col].dropna().unique()
                        available_dates = sorted(available_dates, reverse=True)
                        
                        if len(available_dates) > 0:
                            date_options = [d.strftime('%Y-%m-%d') for d in pd.to_datetime(available_dates)]
                            selected_sg_date = st.selectbox(
                                "📅 选择SpotGamma数据日期",
                                date_options,
                                index=0,
                                key="spotgamma_date_select"
                            )
                            st.session_state['spotgamma_selected_date'] = selected_sg_date
                            st.session_state['spotgamma_date_col'] = date_col
                            st.info(f"已选择 {selected_sg_date} 的数据")
                        else:
                            st.session_state['spotgamma_selected_date'] = None
                            st.session_state['spotgamma_date_col'] = None
                    else:
                        st.session_state['spotgamma_selected_date'] = None
                        st.session_state['spotgamma_date_col'] = None
                except Exception as e:
                    st.warning(f"预览CSV时出错: {e}")
                    st.session_state['spotgamma_selected_date'] = None
                    st.session_state['spotgamma_date_col'] = None
                
                st.session_state['spotgamma_file'] = spotgamma_file
                st.success("✅ CSV已上传")
            elif 'spotgamma_file' in st.session_state:
                st.info("📄 已有数据")
                if st.button("🗑️ 清除数据", key="clear_spotgamma"):
                    del st.session_state['spotgamma_file']
                    if 'spotgamma_selected_date' in st.session_state:
                        del st.session_state['spotgamma_selected_date']
                    if 'spotgamma_date_col' in st.session_state:
                        del st.session_state['spotgamma_date_col']
                    st.rerun()
        
        # ==================== SpotGamma Equity Hub 个股数据上传 ====================
        if SPOTGAMMA_AVAILABLE:
            st.divider()
            st.subheader("📊 SpotGamma个股数据")
            st.caption("用于第八章：个股多空信号分析")
            
            equity_hub_file = st.file_uploader(
                "上传Equity Hub CSV",
                type=['csv'],
                help="从SpotGamma Equity Hub导出的多标的CSV文件",
                key="equity_hub_upload"
            )
            
            if equity_hub_file is not None:
                st.session_state['equity_hub_file'] = equity_hub_file
                st.success("✅ Equity Hub CSV已上传")
            elif 'equity_hub_file' in st.session_state:
                st.info("📄 已有Equity Hub数据")
                if st.button("🗑️ 清除Equity Hub数据", key="clear_equity_hub"):
                    del st.session_state['equity_hub_file']
                    st.rerun()
    
    with st.spinner("正在加载数据..."):
        all_data = load_data()
    
    # 检查是否有任何数据
    has_data = False
    data_status = []
    
    if all_data['fred'] is not None and not all_data['fred'].empty:
        has_data = True
        data_status.append(f"FRED: {len(all_data['fred'].columns)}个指标")
    else:
        data_status.append("FRED: 无数据")
        
    if all_data['yahoo'] is not None and not all_data['yahoo'].empty:
        has_data = True
        data_status.append(f"Yahoo: {len(all_data['yahoo'].columns)}个标的")
    else:
        data_status.append("Yahoo: 无数据")
        
    if all_data['akshare'] is not None and not all_data['akshare'].empty:
        has_data = True
        data_status.append(f"AKShare: {len(all_data['akshare'].columns)}个指数")
    else:
        data_status.append("AKShare: 无数据")
    
    # 显示数据状态
    with st.expander("📡 数据源状态", expanded=not has_data):
        for status in data_status:
            if "无数据" in status:
                st.warning(status)
            else:
                st.success(status)
        
        if not has_data:
            st.error("""
            **所有数据源都无法连接，请检查:**
            1. 网络连接是否正常
            2. 是否需要设置代理
            3. 尝试点击"刷新数据"按钮
            
            **如果在Streamlit Cloud部署:**
            - 添加 `FRED_API_KEY` 到 Secrets
            - 确保 requirements.txt 包含所有依赖
            """)
            st.stop()
        elif "无数据" in str(data_status):
            st.info("部分数据源不可用，显示的指标可能不完整")
    
    with st.spinner("正在计算指标..."):
        indicators = compute_indicators(all_data)
    
    scorer = ScoringSystem(indicators)
    scores = scorer.calc_total_score()
    
    # ==================== 快照保存按钮（在侧边栏，但需要数据） ====================
    with st.sidebar:
        # 保存按钮
        if not snapshot_stats['today_saved']:
            if st.button("💾 保存今日快照", use_container_width=True):
                success, message = snapshot_mgr.save_today_snapshot(indicators, scores, all_data)
                if success:
                    st.success(message)
                    st.rerun()  # 刷新页面更新状态
                else:
                    st.warning(message)
        else:
            st.button("💾 今日已保存", use_container_width=True, disabled=True)
        
        # 更新历史收益按钮
        if snapshot_stats['count'] > 0:
            if st.button("📈 更新历史收益", use_container_width=True):
                yahoo_data = all_data.get('yahoo', pd.DataFrame())
                if not yahoo_data.empty:
                    updated = snapshot_mgr.update_forward_returns(yahoo_data)
                    st.info(f"更新了 {updated} 条收益数据")
    
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
        # 显示趋势和百分位
        z_val = net_liq.get('z_60d')
        pct_val = net_liq.get('pct_252d')
        if z_val is not None and pct_val is not None:
            try:
                if not np.isnan(z_val) and not np.isnan(pct_val):
                    st.caption(f"Z: {z_val:.2f}σ | 252日分位: {pct_val:.0f}%")
            except:
                pass
    
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
    
    # ==================== SOFR/Repo 利差监控 ====================
    
    if ROTATION_SCANNER_AVAILABLE:
        with st.expander("📊 SOFR/Repo 流动性监控 (30天)", expanded=False):
            sofr_data = get_sofr_repo_history(days=30)
            
            if sofr_data.get('success'):
                # 显示关键指标
                col_s1, col_s2, col_s3, col_s4 = st.columns(4)
                
                with col_s1:
                    st.metric("SOFR", f"{sofr_data['current_sofr']:.2f}%")
                
                with col_s2:
                    st.metric("Repo (TGCR)", f"{sofr_data['current_tgcr']:.2f}%")
                
                with col_s3:
                    spread = sofr_data['current_spread']
                    delta_color = "inverse" if spread > 0.05 else "normal"
                    st.metric("利差", f"{spread:.3f}%", 
                             "⚠️" if spread > 0.05 else "✅",
                             delta_color=delta_color)
                
                with col_s4:
                    st.markdown(f"**状态:** {sofr_data['spread_alert_msg']}")
                
                # 图表
                fig_sofr = create_sofr_repo_chart(sofr_data)
                if fig_sofr:
                    st.plotly_chart(fig_sofr, use_container_width=True)
                
                st.caption("""
                **解读:** SOFR-Repo利差是银行间流动性的关键指标。
                - 利差 < 0.02%: 流动性充裕 ✅
                - 利差 0.02-0.05%: 正常范围 ⚪
                - 利差 > 0.05%: 流动性偏紧 ⚠️
                - 利差 > 0.10%: 流动性紧缺 🚨
                """)
            else:
                st.info("SOFR/Repo数据暂时不可用，请稍后刷新")
    
    # ==================== 第二章：货币/利率 ====================
    
    st.markdown('<div class="chapter-header">💱 第二章：货币与利率风向</div>', unsafe_allow_html=True)
    st.markdown('*"钱更愿意待在哪种货币/资产里?"*')
    
    curr = indicators.get('currency', {})
    
    cols = st.columns(7)
    
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
        st.metric("VIX股市波动", f"{vix.get('latest', 0):.1f}", f"Z: {vix.get('z_60d', 0):.2f}σ")
    
    with cols[5]:
        move = curr.get('move', {})
        if move:
            st.metric("MOVE债市波动", f"{move.get('latest', 0):.1f}", f"Z: {move.get('z_60d', 0):.2f}σ")
        else:
            st.metric("MOVE债市波动", "N/A")
    
    with cols[6]:
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
    
    # ==================== 第三章续：RS动量与热力图 ====================
    
    # 新增指标已在indicators中计算
    rs_momentum = indicators.get('rs_momentum', [])
    
    st.markdown("### 📈 RS动量分析 (动量的动量)")
    st.markdown('*区分资产是"正在变强"还是"已强但在转弱"*')
    
    if rs_momentum:
        # 四象限分类显示
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**🚀 加速上涨** (RS>0, 动量>0)")
            acc_up = [x for x in rs_momentum if x['status'] == '加速上涨']
            if acc_up:
                for item in acc_up[:4]:
                    st.markdown(f"- {item['name']}: RS={item['rs_z']:.2f}σ, 动量=+{item['rs_momentum']:.2f}")
            else:
                st.markdown("*无*")
            
            st.markdown("**🔄 下跌减速** (RS<0, 动量>0)")
            dec_down = [x for x in rs_momentum if x['status'] == '下跌减速']
            if dec_down:
                for item in dec_down[:4]:
                    st.markdown(f"- {item['name']}: RS={item['rs_z']:.2f}σ, 动量=+{item['rs_momentum']:.2f}")
            else:
                st.markdown("*无*")
        
        with col2:
            st.markdown("**⚠️ 上涨减速** (RS>0, 动量<0)")
            dec_up = [x for x in rs_momentum if x['status'] == '上涨减速']
            if dec_up:
                for item in dec_up[:4]:
                    st.markdown(f"- {item['name']}: RS={item['rs_z']:.2f}σ, 动量={item['rs_momentum']:.2f}")
            else:
                st.markdown("*无*")
            
            st.markdown("**📉 加速下跌** (RS<0, 动量<0)")
            acc_down = [x for x in rs_momentum if x['status'] == '加速下跌']
            if acc_down:
                for item in acc_down[:4]:
                    st.markdown(f"- {item['name']}: RS={item['rs_z']:.2f}σ, 动量={item['rs_momentum']:.2f}")
            else:
                st.markdown("*无*")
    else:
        st.info("RS动量数据不足")
    
    # 轮动热力图
    st.markdown("### 🗓️ 轮动热力图 (过去12周)")
    
    heatmap_data = indicators.get('rotation_heatmap', {})
    if heatmap_data.get('data') and heatmap_data.get('assets'):
        import numpy as np
        
        # 构建DataFrame
        heatmap_df = pd.DataFrame(
            heatmap_data['data'],
            index=heatmap_data['assets'],
            columns=heatmap_data['dates']
        )
        
        fig_heatmap = go.Figure(data=go.Heatmap(
            z=heatmap_df.values,
            x=heatmap_df.columns.tolist(),
            y=heatmap_df.index.tolist(),
            colorscale=[
                [0, '#FF1744'],      # 红色 (弱)
                [0.25, '#FF8A80'],   # 浅红
                [0.5, '#FFEB3B'],    # 黄色 (中性)
                [0.75, '#69F0AE'],   # 浅绿
                [1, '#00C853']       # 绿色 (强)
            ],
            zmid=0,
            zmin=-3,
            zmax=3,
            text=np.round(heatmap_df.values, 1),
            texttemplate='%{text}',
            textfont={"size": 10},
            hovertemplate='%{y}<br>%{x}<br>Z-Score: %{z:.2f}<extra></extra>',
        ))
        
        fig_heatmap.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font={'color': 'white'},
            height=350,
            margin=dict(l=100, r=20, t=30, b=50),
            xaxis_title='周',
            yaxis_title='',
        )
        
        st.plotly_chart(fig_heatmap, use_container_width=True)
    else:
        st.info("热力图数据不足")
    
    # ==================== 第四章：经济周期与领先指标 ====================
    
    st.markdown('<div class="chapter-header">📊 第四章：经济周期与领先指标</div>', unsafe_allow_html=True)
    st.markdown('*"我们处于周期的哪个阶段?"*')
    
    # 经济周期定位
    cycle = indicators.get('economic_cycle', {})
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.markdown("### 🔄 经济周期定位")
        
        cycle_name = cycle.get('cycle', 'N/A')
        if cycle_name != 'N/A':
            cycle_desc = cycle.get('cycle_desc', '')
            
            # 周期图示
            cycles_list = ['衰退/放缓', '复苏', '扩张/过热', '滞胀']
            cycle_display = ""
            for c in cycles_list:
                if c == cycle_name:
                    cycle_display += f"**[{c}]** → "
                else:
                    cycle_display += f"{c} → "
            cycle_display = cycle_display.rstrip(' → ')
            
            st.markdown(cycle_display)
            st.markdown(f"**当前阶段: {cycle_name}**")
            st.markdown(f"*{cycle_desc}*")
            
            # 判断依据
            st.markdown("**判断依据:**")
            growth_signal = cycle.get('growth_signal', {})
            if growth_signal:
                change = growth_signal.get('change_20d', 0)
                direction = growth_signal.get('direction', '')
                st.markdown(f"- 铜/金比率 20日变化: {change:+.1f}% ({direction}) {'📈' if change > 0 else '📉'}")
            
            inflation_signal = cycle.get('inflation_signal', {})
            if inflation_signal:
                change_bp = inflation_signal.get('change_20d_bp', 0)
                direction = inflation_signal.get('direction', '')
                st.markdown(f"- 通胀预期 20日变化: {change_bp:+.0f}bp ({direction}) {'🔥' if change_bp > 0 else '❄️'}")
            
            curve_signal = cycle.get('curve_signal', {})
            if curve_signal:
                crv_change = curve_signal.get('change_20d_bp', 0)
                shape = curve_signal.get('shape', '')
                st.markdown(f"- 收益率曲线: {crv_change:+.0f}bp ({shape})")
        else:
            st.warning("数据不足，无法判断周期")
    
    with col2:
        st.markdown("### 💡 周期配置建议")
        
        if cycle.get('favorable_assets'):
            st.markdown("**✅ 当前周期有利:**")
            st.markdown(", ".join(cycle['favorable_assets']))
        
        if cycle.get('unfavorable_assets'):
            st.markdown("**❌ 当前周期不利:**")
            st.markdown(", ".join(cycle['unfavorable_assets']))
    
    # 领先指标仪表盘
    st.markdown("### 🎯 领先指标仪表盘")
    
    leading = indicators.get('leading_indicators', [])
    if leading:
        cols = st.columns(3)
        for i, ind in enumerate(leading):
            with cols[i % 3]:
                change_val = ind.get('change_20d', 0)
                unit = ind.get('unit', '%')
                if unit == 'bp':
                    change_str = f"{change_val:+.0f}bp"
                else:
                    change_str = f"{change_val:+.1f}%"
                    
                st.markdown(f"""
                **{ind['name']}** {ind['signal']}
                - 当前: {ind['value']}
                - 20日变化: {change_str}
                - *{ind['description']}*
                """)
    else:
        st.info("领先指标数据不足")
    
    # 相关性监控
    st.markdown("### 🔗 相关性异常监控")
    
    corr_monitor = indicators.get('correlation_monitor', [])
    if corr_monitor:
        # 只显示异常的
        abnormal = [c for c in corr_monitor if '异常' in c['status']]
        normal = [c for c in corr_monitor if '正常' in c['status']]
        
        if abnormal:
            st.markdown("**⚠️ 检测到相关性异常:**")
            for c in abnormal:
                st.markdown(f"""
                - **{c['name']}**: 当前={c['current_corr']:.2f} (历史均值={c['hist_mean']:.2f}) {c['status']}
                  - 解读: *{c['interpretation']}*
                """)
        else:
            st.success("所有监控的相关性对都在正常范围内")
        
        with st.expander("查看所有相关性监控"):
            for c in corr_monitor:
                normal_range = c.get('normal_range', (0, 0))
                st.markdown(f"- {c['name']}: {c['current_corr']:.2f} (均值{c['hist_mean']:.2f}, 正常范围{normal_range[0]:.1f}~{normal_range[1]:.1f}) {c['status']}")
    else:
        st.info("相关性监控数据不足")
    
    # ==================== 第五章：美股结构 ====================
    
    st.markdown('<div class="chapter-header">🇺🇸 第五章：美股内部结构</div>', unsafe_allow_html=True)
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
    
    # ==================== 第六章：资金轮动仪表盘 ====================
    
    if ROTATION_SCANNER_AVAILABLE:
        st.markdown('<div class="chapter-header">📊 第六章：资金轮动仪表盘</div>', unsafe_allow_html=True)
        st.markdown('*"资金正在流向哪里？市场广度如何？"*')
        
        # 计算资金轮动评分
        yahoo_data = all_data.get('yahoo', pd.DataFrame())
        rotation_result = calculate_rotation_score(indicators)
        radar_data = calculate_breadth_radar(indicators, yahoo_data)
        
        # 第一行：仪表盘 + 雷达图
        col_gauge, col_radar = st.columns([1, 1])
        
        with col_gauge:
            st.markdown("### 💹 资金轮动趋势评分")
            
            rotation_score = rotation_result['total_score']
            fig_gauge = create_rotation_gauge(rotation_score)
            st.plotly_chart(fig_gauge, use_container_width=True)
            
            # 市场状态解读
            st.markdown(f"**市场状态:** {rotation_result['market_state']}")
            
            # 分项评分
            st.markdown("**分项评分:**")
            for key, comp in rotation_result['components'].items():
                score = comp['score']
                emoji = '🟢' if score > 20 else '🔴' if score < -20 else '⚪'
                label = {'risk_appetite': '风险偏好', 'sector_rotation': '板块轮动', 'liquidity_breadth': '流动性广度'}.get(key, key)
                st.markdown(f"- {emoji} {label}: {score:.1f}")
        
        with col_radar:
            st.markdown("### 📡 市场广度雷达图")
            
            fig_radar = create_radar_chart(radar_data)
            st.plotly_chart(fig_radar, use_container_width=True)
            
            # 各维度信号
            st.markdown("**各维度信号:**")
            for i, cat in enumerate(radar_data['categories']):
                signal = radar_data['signals'][i]
                z_val = radar_data['values'][i]
                st.markdown(f"- {signal} {cat}: Z={z_val:.2f}")
            
            # 综合评分
            composite = radar_data.get('composite_score', 50)
            st.metric("综合广度评分", f"{composite:.0f}/100")
        
        # 第二行：ETF板块资金流入扫描
        st.markdown("### 📈 ETF板块资金流入扫描")
        st.markdown('*扫描各板块ETF的趋势强度，识别资金流入方向*')
        
        # 扫描ETF
        etf_scan = scan_etf_flows(yahoo_data)
        
        if not etf_scan.empty:
            # 资金流向摘要
            flow_summary = get_etf_flow_summary(etf_scan)
            
            col_sum1, col_sum2, col_sum3 = st.columns(3)
            
            with col_sum1:
                strong_list = flow_summary['strong_sectors'][:5]
                if strong_list:
                    st.success(f"🔥 **强势板块:** {', '.join(strong_list)}")
                else:
                    st.info("暂无强势板块")
            
            with col_sum2:
                weak_list = flow_summary['weak_sectors'][:5]
                if weak_list:
                    st.error(f"📉 **弱势板块:** {', '.join(weak_list)}")
                else:
                    st.info("暂无明显弱势板块")
            
            with col_sum3:
                risk_score = flow_summary['risk_on_score']
                if risk_score > 3:
                    st.success(f"**Risk-On评分:** +{risk_score} 🚀")
                elif risk_score < -3:
                    st.error(f"**Risk-Off评分:** {risk_score} 🔻")
                else:
                    st.info(f"**中性评分:** {risk_score} ⚖️")
            
            # ETF扫描表格
            with st.expander("📋 查看完整ETF扫描结果", expanded=True):
                # 简化显示
                display_cols = ['信号', 'ETF', '板块', '价格', '>SMA20', '>SMA50', '动量', 'OBV↑', '20日%', '评分']
                st.dataframe(
                    etf_scan[display_cols],
                    use_container_width=True,
                    hide_index=True,
                    height=400
                )
                
                st.caption("""
                **评分标准 (0-5分):**
                - 价格 > SMA20 (+1)
                - 价格 > SMA50 (+1)
                - 5日动量 > 0 (+1)
                - OBV上升 (+1)
                - 20日涨幅 > 0 (+1)
                
                **信号解读:** 🟢强势(4-5分) | 🟡偏多(3分) | ⚪中性(2分) | 🔴弱势(0-1分)
                """)
        else:
            st.info("ETF扫描数据暂不可用")
        
        # 资金轮动因子详情
        with st.expander("📊 资金轮动因子详情", expanded=False):
            st.markdown("**各因子Z-Score分解:**")
            
            for key, comp in rotation_result['components'].items():
                label = {'risk_appetite': '风险偏好因子', 'sector_rotation': '板块轮动因子', 'liquidity_breadth': '流动性广度因子'}.get(key, key)
                st.markdown(f"#### {label} (权重: {comp['weight']*100:.0f}%)")
                
                factors = comp.get('factors', [])
                if factors:
                    for f in factors:
                        z = f.get('z', 0)
                        emoji = '🟢' if z > 0.5 else '🔴' if z < -0.5 else '⚪'
                        name = f.get('name', '')
                        st.markdown(f"- {emoji} {name}: Z={z:.2f}σ")
    
    # ==================== 第七章：SpotGamma期权情绪 ====================
    
    if SPOTGAMMA_AVAILABLE and 'spotgamma_file' in st.session_state:
        st.markdown('<div class="chapter-header">🎯 第七章：SpotGamma期权情绪</div>', unsafe_allow_html=True)
        st.markdown('*"Gamma环境如何？期权市场在押注什么方向？"*')
        
        # 解析CSV
        spotgamma_file = st.session_state['spotgamma_file']
        
        # 需要重置文件指针
        spotgamma_file.seek(0)
        
        # 检查是否有日期过滤
        selected_date = st.session_state.get('spotgamma_selected_date', None)
        date_col = st.session_state.get('spotgamma_date_col', None)
        
        if selected_date and date_col:
            # 先读取原始CSV进行日期过滤
            try:
                raw_df = pd.read_csv(spotgamma_file)
                spotgamma_file.seek(0)
                
                # 解析日期列
                raw_df[date_col] = pd.to_datetime(raw_df[date_col], format='mixed', errors='coerce')
                selected_dt = pd.to_datetime(selected_date)
                
                # 过滤选中日期的数据
                filtered_df = raw_df[raw_df[date_col] == selected_dt].copy()
                
                # 显示当前分析的日期
                st.info(f"📅 当前分析日期: **{selected_date}** | 共 {len(filtered_df)} 条记录")
                
                if not filtered_df.empty:
                    # 列名映射（处理手动录入格式）
                    column_mapping = {
                        'Current Price(盘前价)': 'Current Price',
                        'previous close': 'Previous Close',
                    }
                    filtered_df = filtered_df.rename(columns=column_mapping)
                    
                    # 不预处理数值！让spotgamma_analyzer.py的parse_pct和parse_num处理
                    # 只需要处理特殊格式（如 -1.8B, 1.2M, 978K）
                    def parse_large_numbers(val):
                        """只处理B/M/K后缀的大数字，其他保持原样"""
                        if pd.isna(val):
                            return val
                        val_str = str(val).strip()
                        
                        # 检查是否有B/M/K后缀
                        multiplier = 1
                        clean_str = val_str.replace(' ', '').replace('$', '')
                        
                        if clean_str.endswith('B'):
                            try:
                                return float(clean_str[:-1]) * 1e9
                            except:
                                return val
                        elif clean_str.endswith('M'):
                            try:
                                return float(clean_str[:-1]) * 1e6
                            except:
                                return val
                        elif clean_str.endswith('K'):
                            try:
                                return float(clean_str[:-1]) * 1e3
                            except:
                                return val
                        
                        # 不是大数字格式，保持原样（包括百分比）
                        return val
                    
                    # 只处理可能有B/M/K后缀的列
                    large_number_cols = ['Call Gamma', 'Put Gamma', 'Call Volume', 'Put Volume',
                                        'Stock Volume', 'Next Exp Call Vol', 'Next Exp Put Vol']
                    
                    for col in large_number_cols:
                        if col in filtered_df.columns:
                            filtered_df[col] = filtered_df[col].apply(parse_large_numbers)
                    
                    # 处理双百分号问题（41.12%% → 41.12%）
                    for col in filtered_df.columns:
                        if filtered_df[col].dtype == 'object':
                            filtered_df[col] = filtered_df[col].astype(str).str.replace('%%', '%', regex=False)
                    
                    # 使用过滤后的数据调用parse_spotgamma_csv
                    # 创建一个临时文件对象（模拟上传的文件）
                    import io
                    temp_buffer = io.StringIO()
                    filtered_df.to_csv(temp_buffer, index=False)
                    temp_buffer.seek(0)
                    
                    sg_df = parse_spotgamma_csv(temp_buffer)
                else:
                    st.warning(f"所选日期 {selected_date} 没有数据")
                    sg_df = None
            except Exception as e:
                st.error(f"日期过滤出错: {e}")
                spotgamma_file.seek(0)
                sg_df = parse_spotgamma_csv(spotgamma_file)
        else:
            # 没有日期列，直接解析
            sg_df = parse_spotgamma_csv(spotgamma_file)
        
        if sg_df is not None and not sg_df.empty:
            # 获取当前价格 (如果有的话)
            yahoo_data = all_data.get('yahoo', pd.DataFrame())
            prices = {}
            if yahoo_data is not None and not yahoo_data.empty:
                if 'QQQ' in yahoo_data.columns:
                    prices['QQQ'] = float(yahoo_data['QQQ'].dropna().iloc[-1])
                if 'SPY' in yahoo_data.columns:
                    prices['SPY'] = float(yahoo_data['SPY'].dropna().iloc[-1])
            
            # 渲染SpotGamma分析
            sg_analysis = render_spotgamma_section(sg_df, st, prices)
            
            # 存储分析结果供其他模块使用
            st.session_state['spotgamma_analysis'] = sg_analysis
            
            # 生成分析摘要供Claude使用
            if sg_analysis:
                with st.expander("📋 SpotGamma分析摘要 (供Claude)", expanded=False):
                    summary = get_gamma_summary(sg_analysis)
                    st.code(summary, language="markdown")
        else:
            st.warning("SpotGamma CSV解析失败，请检查文件格式")
    elif SPOTGAMMA_AVAILABLE:
        # 显示提示
        with st.expander("🎯 SpotGamma期权情绪分析 (未启用)", expanded=False):
            st.info("""
            **如何启用SpotGamma分析:**
            1. 登录 SpotGamma 网站
            2. 进入 Data Table 页面
            3. 导出 CSV 文件
            4. 在左侧边栏上传 CSV
            
            **分析内容包括:**
            - Gamma环境总览 (正/负Gamma)
            - 关键位地图 (Call Wall, Put Wall, Zero Gamma, Hedge Wall)
            - 方向性指标 (Delta Ratio, Gamma Ratio, Volume Ratio)
            - 波动率洞察 (IV vs RV, Skew, IV Rank)
            - 情景分析和操作铁律
            - 风险预警和交易提示
            
            **官方指标定义:**
            - **Volume Ratio**: ATM Put Delta与Call Delta成交量比（非传统P/C Vol），高=到期后可能反弹
            - **Options Implied Move**: 美元值（非百分比）
            - **Hedge Wall**: 做市商风险暴露变化位，上方=均值回归，下方=高波动
            - **Next Exp Gamma >25%**: 短期头寸集中，到期前后易剧烈波动
            """)
    
    # ==================== 第八章：SpotGamma个股多空分析 ====================
    
    if SPOTGAMMA_AVAILABLE and 'equity_hub_file' in st.session_state:
        st.markdown('<div class="chapter-header">📈 第八章：SpotGamma个股多空分析</div>', unsafe_allow_html=True)
        st.markdown('*"哪些标的期权结构偏多？哪些偏空？做市商在押注什么？"*')
        
        equity_hub_file = st.session_state['equity_hub_file']
        equity_hub_file.seek(0)
        
        try:
            # 读取CSV（处理可能的多行表头）
            first_line = equity_hub_file.readline().decode('utf-8')
            equity_hub_file.seek(0)
            
            if 'Ticker Information' in first_line or 'isWatchlisted' in first_line:
                eh_df = pd.read_csv(equity_hub_file)
            else:
                eh_df = pd.read_csv(equity_hub_file, skiprows=1)
            
            eh_df = eh_df.dropna(subset=['Symbol'])
            
            # 辅助函数：解析数值
            def parse_eh_value(val):
                if pd.isna(val) or val == '':
                    return np.nan
                val_str = str(val).strip().replace("'", "").replace(",", "")
                try:
                    return float(val_str)
                except:
                    return np.nan
            
            # 解析关键列
            numeric_cols = ['Current Price', 'Delta Ratio', 'Gamma Ratio', 'Put Wall', 'Call Wall', 
                           'Hedge Wall', 'Options Impact', 'Volume Ratio', 'Next Exp Gamma', 
                           'Put/Call OI Ratio', 'IV Rank', 'Key Gamma Strike']
            
            for col in numeric_cols:
                if col in eh_df.columns:
                    eh_df[col] = eh_df[col].apply(parse_eh_value)
            
            # ===== 分析函数 =====
            def analyze_equity(row):
                """分析单个标的的期权结构"""
                symbol = row.get('Symbol', '')
                price = row.get('Current Price', 0)
                dr = row.get('Delta Ratio', -1)
                gr = row.get('Gamma Ratio', 1)
                pw = row.get('Put Wall', 0)
                cw = row.get('Call Wall', 0)
                hw = row.get('Hedge Wall', 0)
                oi = row.get('Options Impact', 0)
                vr = row.get('Volume Ratio', 1)
                neg = row.get('Next Exp Gamma', 0)
                
                # 方向性判断（基于Delta Ratio）
                # DR = Put Delta / Call Delta (负值)
                # > -1: 偏多 (Call Delta占优)
                # < -3: 偏空 (Put Delta占优)
                if pd.isna(dr):
                    direction = "❓ 数据缺失"
                    direction_score = 0
                elif dr > -1:
                    direction = "🟢 强力偏多"
                    direction_score = 2
                elif dr > -2:
                    direction = "🟢 偏多"
                    direction_score = 1
                elif dr > -3:
                    direction = "⚪ 中性"
                    direction_score = 0
                elif dr > -5:
                    direction = "🔴 偏空"
                    direction_score = -1
                else:
                    direction = "🔴 强力偏空"
                    direction_score = -2
                
                # Gamma结构判断（基于Gamma Ratio）
                # GR = Put Gamma / Call Gamma
                # < 1: Call Gamma主导，上涨加速
                # > 2: Put Gamma主导，下跌加速
                if pd.isna(gr):
                    gamma_struct = "❓"
                elif gr < 1:
                    gamma_struct = "📈 Call主导"
                elif gr < 2:
                    gamma_struct = "⚖️ 均衡"
                else:
                    gamma_struct = "📉 Put主导"
                
                # 价格位置判断
                position = "中间"
                if price > 0 and cw > 0 and pw > 0:
                    dist_to_cw = (cw - price) / price * 100
                    dist_to_pw = (price - pw) / price * 100
                    
                    if dist_to_cw < 3:
                        position = "近CW阻力"
                    elif dist_to_pw < 3:
                        position = "近PW支撑"
                
                # 波动环境（基于Hedge Wall）
                vol_env = "未知"
                if price > 0 and hw > 0:
                    if price > hw:
                        vol_env = "均值回归"
                    else:
                        vol_env = "趋势/高波动"
                
                # 综合信号
                if direction_score >= 1 and gr < 1.5:
                    signal = "🟢 做多"
                    signal_strength = "⭐⭐⭐" if direction_score == 2 else "⭐⭐"
                elif direction_score <= -1 and gr > 1.5:
                    signal = "🔴 做空"
                    signal_strength = "⭐⭐⭐" if direction_score == -2 else "⭐⭐"
                else:
                    signal = "⚪ 观望"
                    signal_strength = "⭐"
                
                # 特殊警告
                warnings = []
                if neg and neg > 25:
                    warnings.append(f"⚠️ NEG {neg:.0f}%集中")
                if vr and vr > 2:
                    warnings.append(f"📊 高VR={vr:.1f}")
                
                return {
                    'Symbol': symbol,
                    'Price': price,
                    'Signal': signal,
                    'Strength': signal_strength,
                    'Direction': direction,
                    'DR': dr,
                    'GR': gr,
                    'Gamma结构': gamma_struct,
                    'Position': position,
                    'Vol_Env': vol_env,
                    'PW': pw,
                    'CW': cw,
                    'OI%': oi * 100 if oi and oi < 1 else oi,
                    'Warnings': ', '.join(warnings) if warnings else ''
                }
            
            # 分析所有标的
            results = []
            for _, row in eh_df.iterrows():
                result = analyze_equity(row)
                if result['Symbol']:
                    results.append(result)
            
            results_df = pd.DataFrame(results)
            
            if not results_df.empty:
                # ===== 统计概览 =====
                st.subheader("📊 信号统计")
                
                bullish = results_df[results_df['Signal'] == '🟢 做多']
                bearish = results_df[results_df['Signal'] == '🔴 做空']
                neutral = results_df[results_df['Signal'] == '⚪ 观望']
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("🟢 做多信号", len(bullish))
                with col2:
                    st.metric("🔴 做空信号", len(bearish))
                with col3:
                    st.metric("⚪ 观望", len(neutral))
                with col4:
                    total = len(bullish) + len(bearish)
                    bull_pct = len(bullish) / total * 100 if total > 0 else 50
                    st.metric("多空比", f"{bull_pct:.0f}% : {100-bull_pct:.0f}%")
                
                # ===== 做多名单 =====
                st.subheader("🟢 做多信号")
                if not bullish.empty:
                    bullish_sorted = bullish.sort_values('Strength', ascending=False)
                    display_cols = ['Symbol', 'Price', 'Strength', 'Direction', 'DR', 'GR', 
                                   'Gamma结构', 'Position', 'Vol_Env', 'PW', 'CW', 'Warnings']
                    st.dataframe(
                        bullish_sorted[display_cols].round(2),
                        use_container_width=True,
                        hide_index=True
                    )
                else:
                    st.info("无做多信号")
                
                # ===== 做空名单 =====
                st.subheader("🔴 做空信号")
                if not bearish.empty:
                    bearish_sorted = bearish.sort_values('Strength', ascending=False)
                    display_cols = ['Symbol', 'Price', 'Strength', 'Direction', 'DR', 'GR', 
                                   'Gamma结构', 'Position', 'Vol_Env', 'PW', 'CW', 'Warnings']
                    st.dataframe(
                        bearish_sorted[display_cols].round(2),
                        use_container_width=True,
                        hide_index=True
                    )
                else:
                    st.info("无做空信号")
                
                # ===== 完整数据表 =====
                with st.expander("📋 完整分析表"):
                    st.dataframe(
                        results_df.round(2),
                        use_container_width=True,
                        hide_index=True
                    )
                
                # ===== 指标说明 =====
                with st.expander("📖 指标说明"):
                    st.markdown("""
                    **Delta Ratio (DR)** = Put Delta ÷ Call Delta
                    - DR > -1: 🟢 偏多 (Call Delta占优)
                    - DR = -1 ~ -3: ⚪ 中性
                    - DR < -3: 🔴 偏空 (Put Delta占优)
                    
                    **Gamma Ratio (GR)** = Put Gamma ÷ Call Gamma
                    - GR < 1: 📈 Call Gamma主导，上涨时加速
                    - GR = 1 ~ 2: ⚖️ 均衡
                    - GR > 2: 📉 Put Gamma主导，下跌时加速
                    
                    **综合信号逻辑**
                    - 🟢 做多: DR偏多 + GR偏Call
                    - 🔴 做空: DR偏空 + GR偏Put
                    - ⚪ 观望: 信号矛盾或中性
                    
                    **特殊警告**
                    - ⚠️ NEG集中: Next Exp Gamma > 25%，到期日前后波动大
                    - 📊 高VR: Volume Ratio > 2，Put成交活跃，可能有反弹潜力
                    """)
            else:
                st.warning("无法解析数据，请检查CSV格式")
                
        except Exception as e:
            st.error(f"解析Equity Hub数据出错: {e}")
            import traceback
            st.code(traceback.format_exc())
    
    elif SPOTGAMMA_AVAILABLE:
        with st.expander("📈 SpotGamma个股多空分析 (未启用)", expanded=False):
            st.info("""
            **如何启用个股分析:**
            1. 登录 SpotGamma 网站
            2. 进入 Equity Hub → Data Table
            3. 选择要分析的标的（如 NDX, IWM, GLD, TLT 等）
            4. 导出 CSV 文件
            5. 在左侧边栏上传 Equity Hub CSV
            
            **分析内容包括:**
            - 多空信号判断（基于Delta Ratio + Gamma Ratio）
            - 价格位置分析（近Call Wall / Put Wall / 中间）
            - 波动环境判断（均值回归 / 趋势）
            - 特殊风险警告（Gamma集中、高Volume Ratio）
            """)
    
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
