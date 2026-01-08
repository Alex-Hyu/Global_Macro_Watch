"""
宏观战情室 V2 - 资金轮动与ETF扫描模块
包含:
1. SOFR/Repo历史数据获取
2. ETF板块资金流入扫描
3. 市场广度雷达图数据
4. 资金轮动趋势评分
5. 综合评分仪表盘
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import requests
import warnings
warnings.filterwarnings('ignore')

try:
    import yfinance as yf
except ImportError:
    yf = None

# ==================== SOFR/Repo 数据获取 ====================

def get_sofr_repo_history(days=30):
    """
    获取 SOFR 和 Repo 利率的历史数据
    数据来源: NY Fed API
    """
    result = {
        'dates': [],
        'sofr': [],
        'tgcr': [],  # Tri-Party General Collateral Rate
        'bgcr': [],  # Broad General Collateral Rate
        'spread': [],  # SOFR - TGCR
        'current_sofr': 4.33,
        'current_tgcr': 4.32,
        'current_spread': 0.01,
        'spread_alert': False,
        'spread_alert_msg': '',
        'success': False,
    }
    
    try:
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days + 15)  # 多取一些确保有足够数据
        
        # 获取 SOFR 数据
        sofr_url = f"https://markets.newyorkfed.org/api/rates/secured/sofr/search.json?startDate={start_date}&endDate={end_date}"
        r_sofr = requests.get(sofr_url, timeout=15)
        sofr_data = {}
        if r_sofr.status_code == 200:
            data = r_sofr.json()
            for item in data.get('refRates', []):
                date = item.get('effectiveDate', '')
                rate = item.get('percentRate', 0)
                sofr_data[date] = float(rate)
        
        # 获取 TGCR 数据 (Tri-Party General Collateral Rate)
        tgcr_url = f"https://markets.newyorkfed.org/api/rates/secured/tgcr/search.json?startDate={start_date}&endDate={end_date}"
        r_tgcr = requests.get(tgcr_url, timeout=15)
        tgcr_data = {}
        if r_tgcr.status_code == 200:
            data = r_tgcr.json()
            for item in data.get('refRates', []):
                date = item.get('effectiveDate', '')
                rate = item.get('percentRate', 0)
                tgcr_data[date] = float(rate)
        
        # 获取 BGCR 数据 (Broad General Collateral Rate)
        bgcr_url = f"https://markets.newyorkfed.org/api/rates/secured/bgcr/search.json?startDate={start_date}&endDate={end_date}"
        r_bgcr = requests.get(bgcr_url, timeout=15)
        bgcr_data = {}
        if r_bgcr.status_code == 200:
            data = r_bgcr.json()
            for item in data.get('refRates', []):
                date = item.get('effectiveDate', '')
                rate = item.get('percentRate', 0)
                bgcr_data[date] = float(rate)
        
        # 合并数据 - 取共同日期
        common_dates = set(sofr_data.keys())
        if tgcr_data:
            common_dates = common_dates & set(tgcr_data.keys())
        all_dates = sorted(common_dates)[-days:]
        
        for date in all_dates:
            result['dates'].append(date)
            result['sofr'].append(sofr_data.get(date, 0))
            result['tgcr'].append(tgcr_data.get(date, 0))
            result['bgcr'].append(bgcr_data.get(date, 0))
            spread = sofr_data.get(date, 0) - tgcr_data.get(date, 0)
            result['spread'].append(spread)
        
        if result['sofr']:
            result['current_sofr'] = result['sofr'][-1]
            result['current_tgcr'] = result['tgcr'][-1] if result['tgcr'] else result['current_sofr']
            result['current_spread'] = result['spread'][-1] if result['spread'] else 0
            result['success'] = True
            
            # 利差预警
            if result['current_spread'] > 0.10:
                result['spread_alert'] = True
                result['spread_alert_msg'] = f'🚨 流动性紧缺: SOFR-Repo利差 {result["current_spread"]:.3f}% 超过警戒线'
            elif result['current_spread'] > 0.05:
                result['spread_alert'] = True
                result['spread_alert_msg'] = f'⚠️ 流动性偏紧: SOFR-Repo利差 {result["current_spread"]:.3f}%'
            else:
                result['spread_alert_msg'] = f'✅ 流动性充裕: SOFR-Repo利差 {result["current_spread"]:.3f}%'
                
    except Exception as e:
        print(f"SOFR/Repo数据获取失败: {e}")
        result['spread_alert_msg'] = '⚠️ SOFR/Repo数据获取失败'
    
    return result


def get_rrp_tga_history(days=30):
    """
    获取 RRP 和 TGA 的历史数据
    数据来源: FRED
    """
    result = {
        'dates': [],
        'rrp': [],
        'tga': [],
        'net_drain': [],  # RRP + TGA 合计抽水
        'current_rrp': 0,
        'current_tga': 0,
        'rrp_chg_1d': 0,
        'tga_chg_1d': 0,
    }
    
    try:
        # RRP (Overnight Reverse Repo)
        rrp_url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=RRPONTSYD"
        rrp_df = pd.read_csv(rrp_url)
        
        # 自动检测列名
        date_col = rrp_df.columns[0]
        rrp_col = 'RRPONTSYD' if 'RRPONTSYD' in rrp_df.columns else rrp_df.columns[1]
        
        rrp_df = rrp_df.dropna().tail(days + 5)
        rrp_df[date_col] = pd.to_datetime(rrp_df[date_col])
        
        # TGA (Treasury General Account) - 周度数据
        tga_url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=WTREGEN"
        tga_df = pd.read_csv(tga_url)
        
        tga_date_col = tga_df.columns[0]
        tga_col = 'WTREGEN' if 'WTREGEN' in tga_df.columns else tga_df.columns[1]
        
        tga_df = tga_df.dropna().tail(days + 5)
        tga_df[tga_date_col] = pd.to_datetime(tga_df[tga_date_col])
        
        # 取最近 days 天的 RRP 数据
        result['dates'] = rrp_df[date_col].dt.strftime('%Y-%m-%d').tolist()[-days:]
        result['rrp'] = rrp_df[rrp_col].tolist()[-days:]
        
        # TGA 是周度数据，需要前向填充对齐
        tga_dict = dict(zip(tga_df[tga_date_col].dt.strftime('%Y-%m-%d'), tga_df[tga_col]))
        result['tga'] = []
        last_tga = list(tga_dict.values())[-1] if tga_dict else 0
        for d in result['dates']:
            if d in tga_dict:
                last_tga = tga_dict[d]
            result['tga'].append(last_tga / 1000)  # 转换为十亿美元
        
        # 计算净抽水
        for i in range(len(result['dates'])):
            net = result['rrp'][i] + result['tga'][i] * 1000  # TGA单位是百万
            result['net_drain'].append(net)
        
        if result['rrp']:
            result['current_rrp'] = result['rrp'][-1]
            result['rrp_chg_1d'] = result['rrp'][-1] - result['rrp'][-2] if len(result['rrp']) > 1 else 0
        if result['tga']:
            result['current_tga'] = result['tga'][-1]
            result['tga_chg_1d'] = result['tga'][-1] - result['tga'][-2] if len(result['tga']) > 1 else 0
            
    except Exception as e:
        print(f"RRP/TGA数据获取失败: {e}")
    
    return result


# ==================== ETF板块资金流入扫描 ====================

# 核心板块ETF列表
SECTOR_ETFS = {
    # 科技
    'XLK': ('科技', 'Technology'),
    'SMH': ('半导体', 'Semiconductors'),
    'IGV': ('软件', 'Software'),
    # 金融
    'XLF': ('金融', 'Financials'),
    # 能源
    'XLE': ('能源', 'Energy'),
    # 医疗健康
    'XLV': ('医疗', 'Healthcare'),
    'XBI': ('生物科技', 'Biotech'),
    # 工业
    'XLI': ('工业', 'Industrials'),
    # 消费
    'XLY': ('可选消费', 'Consumer Discretionary'),
    'XLP': ('必需消费', 'Consumer Staples'),
    # 公用事业
    'XLU': ('公用事业', 'Utilities'),
    # 房地产
    'XLRE': ('房地产', 'Real Estate'),
    # 材料
    'XLB': ('材料', 'Materials'),
    # 通信
    'XLC': ('通信服务', 'Communication'),
    # 规模因子
    'IWM': ('小盘股', 'Small Cap'),
    'QQQ': ('纳指100', 'Nasdaq 100'),
    'SPY': ('S&P500', 'S&P 500'),
    # 风格因子
    'IWF': ('成长', 'Growth'),
    'IWD': ('价值', 'Value'),
}


def scan_etf_flows(yahoo_data=None, lookback=20):
    """
    扫描ETF资金流入信号
    
    评分标准 (0-5分):
    1. 价格 > SMA20 (+1)
    2. 价格 > SMA50 (+1)
    3. 成交量 > 20日均量 (+1) 或 动量>0
    4. OBV上升 (+1)
    5. 20日涨幅 > 0 (+1)
    
    返回: DataFrame with columns ['ETF', '板块', '价格', '>SMA20', '>SMA50', '放量', 'OBV↑', '20日涨幅%', '评分']
    """
    results = []
    
    # 如果没有传入数据，尝试用yfinance获取
    if yahoo_data is None or yahoo_data.empty:
        if yf is None:
            return pd.DataFrame()
        try:
            tickers = list(SECTOR_ETFS.keys())
            yahoo_data = yf.download(tickers, period='3mo', progress=False)
            if isinstance(yahoo_data.columns, pd.MultiIndex):
                yahoo_data = yahoo_data['Close']
        except Exception as e:
            print(f"ETF数据获取失败: {e}")
            return pd.DataFrame()
    
    for ticker, (name_cn, name_en) in SECTOR_ETFS.items():
        if ticker not in yahoo_data.columns:
            continue
            
        try:
            prices = yahoo_data[ticker].dropna()
            if len(prices) < 50:
                continue
            
            # 计算指标
            sma20 = prices.rolling(20).mean()
            sma50 = prices.rolling(50).mean()
            
            latest = prices.iloc[-1]
            prev_20d = prices.iloc[-21] if len(prices) > 20 else prices.iloc[0]
            prev_5d = prices.iloc[-6] if len(prices) > 5 else prices.iloc[0]
            
            # 计算OBV (简化版，用价格变化方向)
            price_diff = prices.diff()
            obv_direction = (price_diff.iloc[-5:] > 0).sum() > 2.5  # 近5天多数上涨
            
            # 评分
            score = 0
            signals = {}
            
            # 1. 价格 > SMA20
            above_sma20 = latest > sma20.iloc[-1]
            signals['>SMA20'] = '✅' if above_sma20 else '❌'
            if above_sma20:
                score += 1
            
            # 2. 价格 > SMA50
            above_sma50 = latest > sma50.iloc[-1] if not pd.isna(sma50.iloc[-1]) else False
            signals['>SMA50'] = '✅' if above_sma50 else '❌'
            if above_sma50:
                score += 1
            
            # 3. 近期动量 (简化: 5日涨幅 > 0)
            mom_5d = (latest / prev_5d - 1) * 100
            signals['动量'] = '✅' if mom_5d > 0 else '❌'
            if mom_5d > 0:
                score += 1
            
            # 4. OBV方向
            signals['OBV↑'] = '✅' if obv_direction else '❌'
            if obv_direction:
                score += 1
            
            # 5. 20日涨幅
            returns_20d = (latest / prev_20d - 1) * 100
            if returns_20d > 0:
                score += 1
            
            # 信号强度
            if score >= 4:
                signal = '🟢'
            elif score >= 3:
                signal = '🟡'
            elif score <= 1:
                signal = '🔴'
            else:
                signal = '⚪'
            
            results.append({
                'ETF': ticker,
                '板块': name_cn,
                '信号': signal,
                '价格': round(latest, 2),
                '>SMA20': signals['>SMA20'],
                '>SMA50': signals['>SMA50'],
                '动量': signals['动量'],
                'OBV↑': signals['OBV↑'],
                '20日%': round(returns_20d, 1),
                '评分': score,
            })
            
        except Exception as e:
            print(f"ETF {ticker} 扫描失败: {e}")
            continue
    
    # 排序
    df = pd.DataFrame(results)
    if not df.empty:
        df = df.sort_values('评分', ascending=False)
    
    return df


def get_etf_flow_summary(scan_results):
    """
    生成ETF资金流向摘要
    """
    if scan_results.empty:
        return {
            'strong_sectors': [],
            'weak_sectors': [],
            'neutral_sectors': [],
            'risk_on_score': 0,
            'summary': '数据不足',
        }
    
    strong = scan_results[scan_results['评分'] >= 4]['板块'].tolist()
    weak = scan_results[scan_results['评分'] <= 1]['板块'].tolist()
    neutral = scan_results[(scan_results['评分'] > 1) & (scan_results['评分'] < 4)]['板块'].tolist()
    
    # Risk-On 评分: 强势板块数 - 弱势板块数
    risk_on_score = len(strong) - len(weak)
    
    # 判断整体情绪
    if risk_on_score > 3:
        summary = '🟢 资金积极流入风险资产'
    elif risk_on_score < -3:
        summary = '🔴 资金撤离风险资产'
    else:
        summary = '⚪ 资金流向分化'
    
    return {
        'strong_sectors': strong,
        'weak_sectors': weak,
        'neutral_sectors': neutral,
        'risk_on_score': risk_on_score,
        'summary': summary,
    }


# ==================== 市场广度雷达图数据 ====================

def calculate_breadth_radar(indicators, yahoo_data=None):
    """
    计算市场广度雷达图数据
    
    5个维度:
    1. 流动性 (净流动性Z-Score)
    2. 风险偏好 (HYG/LQD Z-Score)
    3. 汇率环境 (DXY逆向, 弱美元利好)
    4. 波动率 (VIX逆向, 低VIX利好)
    5. 市场广度 (小盘/大盘 Z-Score)
    
    返回: dict with 'categories', 'values', 'normalized' (0-100 scale)
    """
    radar_data = {
        'categories': ['流动性', '风险偏好', '汇率环境', '波动率', '市场广度'],
        'values': [],
        'normalized': [],
        'signals': [],
        'raw_values': {},
    }
    
    def calc_zscore(series, window=60):
        if series is None or len(series) < window:
            return 0
        recent = series.iloc[-window:]
        mean = recent.mean()
        std = recent.std()
        if std == 0:
            return 0
        return (series.iloc[-1] - mean) / std
    
    # 1. 流动性 (净流动性Z-Score, 正值利好)
    liq = indicators.get('liquidity', {})
    net_liq = liq.get('net_liquidity', {})
    liq_z = net_liq.get('z_60d', 0) if net_liq else 0
    if pd.isna(liq_z):
        liq_z = 0
    radar_data['values'].append(liq_z)
    radar_data['normalized'].append(min(100, max(0, (liq_z + 3) / 6 * 100)))
    radar_data['signals'].append('🟢' if liq_z > 0.5 else '🔴' if liq_z < -0.5 else '⚪')
    radar_data['raw_values']['流动性'] = {'z': liq_z, 'desc': '净流动性'}
    
    # 2. 风险偏好 (HYG/LQD Z-Score, 正值利好)
    hyg_lqd = liq.get('hyg_lqd', {})
    risk_z = hyg_lqd.get('z_60d', 0) if hyg_lqd else 0
    if pd.isna(risk_z):
        risk_z = 0
    radar_data['values'].append(risk_z)
    radar_data['normalized'].append(min(100, max(0, (risk_z + 3) / 6 * 100)))
    radar_data['signals'].append('🟢' if risk_z > 0.5 else '🔴' if risk_z < -0.5 else '⚪')
    radar_data['raw_values']['风险偏好'] = {'z': risk_z, 'desc': 'HYG/LQD'}
    
    # 3. 汇率环境 (DXY Z-Score 取反, 弱美元利好)
    curr = indicators.get('currency', {})
    dxy = curr.get('dxy', {})
    dxy_z = dxy.get('z_60d', 0) if dxy else 0
    if pd.isna(dxy_z):
        dxy_z = 0
    fx_z = -dxy_z  # 取反: 弱美元利好
    radar_data['values'].append(fx_z)
    radar_data['normalized'].append(min(100, max(0, (fx_z + 3) / 6 * 100)))
    radar_data['signals'].append('🟢' if fx_z > 0.5 else '🔴' if fx_z < -0.5 else '⚪')
    radar_data['raw_values']['汇率环境'] = {'z': fx_z, 'desc': 'DXY反向'}
    
    # 4. 波动率 (VIX Z-Score 取反, 低波动利好)
    vix = curr.get('vix', {})
    vix_z = vix.get('z_60d', 0) if vix else 0
    if pd.isna(vix_z):
        vix_z = 0
    vol_z = -vix_z  # 取反: 低VIX利好
    radar_data['values'].append(vol_z)
    radar_data['normalized'].append(min(100, max(0, (vol_z + 3) / 6 * 100)))
    radar_data['signals'].append('🟢' if vol_z > 0.5 else '🔴' if vol_z < -0.5 else '⚪')
    radar_data['raw_values']['波动率'] = {'z': vol_z, 'desc': 'VIX反向'}
    
    # 5. 市场广度 (小盘/大盘 Z-Score, 正值表示小盘股走强)
    us = indicators.get('us_structure', {})
    breadth_factors = us.get('breadth', [])
    breadth_z = 0
    for f in breadth_factors:
        if f.get('name') == '小盘/大盘':
            breadth_z = f.get('z', 0)
            break
    if pd.isna(breadth_z):
        breadth_z = 0
    
    # 如果没有从indicators获取到，尝试从yahoo_data计算
    if breadth_z == 0 and yahoo_data is not None:
        if 'IWM' in yahoo_data.columns and 'SPY' in yahoo_data.columns:
            iwm = yahoo_data['IWM'].dropna()
            spy = yahoo_data['SPY'].dropna()
            if len(iwm) > 60 and len(spy) > 60:
                ratio = iwm / spy
                ratio = ratio.dropna()
                if len(ratio) > 60:
                    breadth_z = calc_zscore(ratio, 60)
    
    radar_data['values'].append(breadth_z)
    radar_data['normalized'].append(min(100, max(0, (breadth_z + 3) / 6 * 100)))
    radar_data['signals'].append('🟢' if breadth_z > 0.5 else '🔴' if breadth_z < -0.5 else '⚪')
    radar_data['raw_values']['市场广度'] = {'z': breadth_z, 'desc': 'IWM/SPY'}
    
    # 计算综合评分 (归一化到0-100)
    avg_z = np.mean(radar_data['values'])
    radar_data['composite_score'] = min(100, max(0, (avg_z + 3) / 6 * 100))
    radar_data['composite_z'] = avg_z
    
    return radar_data


# ==================== 资金轮动趋势评分 ====================

def calculate_rotation_score(indicators, etf_scan_results=None):
    """
    计算资金轮动趋势综合评分 (-100 到 +100)
    
    评分维度:
    1. 风险偏好因子 (35%)
    2. 板块轮动因子 (40%)
    3. 流动性广度因子 (25%)
    
    正值 = Risk-On (进攻)
    负值 = Risk-Off (防御)
    """
    score_components = {
        'risk_appetite': {'weight': 0.35, 'score': 0, 'factors': []},
        'sector_rotation': {'weight': 0.40, 'score': 0, 'factors': []},
        'liquidity_breadth': {'weight': 0.25, 'score': 0, 'factors': []},
    }
    
    us = indicators.get('us_structure', {})
    
    # 1. 风险偏好因子
    risk_factors = us.get('risk_appetite', [])
    if risk_factors:
        z_sum = sum(f.get('z', 0) for f in risk_factors if not pd.isna(f.get('z', 0)))
        avg_z = z_sum / len(risk_factors) if risk_factors else 0
        # 转换为 -100 到 +100 (假设Z-Score范围是 -3 到 +3)
        score_components['risk_appetite']['score'] = np.clip(avg_z / 3 * 100, -100, 100)
        score_components['risk_appetite']['factors'] = [
            {'name': f['name'], 'z': f.get('z', 0), 'signal': f.get('emoji', '⚪')}
            for f in risk_factors
        ]
    
    # 2. 板块轮动因子
    sector_factors = us.get('sector_rotation', [])
    if sector_factors:
        z_sum = sum(f.get('z', 0) for f in sector_factors if not pd.isna(f.get('z', 0)))
        avg_z = z_sum / len(sector_factors) if sector_factors else 0
        score_components['sector_rotation']['score'] = np.clip(avg_z / 3 * 100, -100, 100)
        score_components['sector_rotation']['factors'] = [
            {'name': f['name'], 'z': f.get('z', 0), 'signal': f.get('emoji', '⚪')}
            for f in sector_factors
        ]
    
    # 3. 流动性广度因子
    breadth_factors = us.get('breadth', [])
    if breadth_factors:
        z_sum = sum(f.get('z', 0) for f in breadth_factors if not pd.isna(f.get('z', 0)))
        avg_z = z_sum / len(breadth_factors) if breadth_factors else 0
        score_components['liquidity_breadth']['score'] = np.clip(avg_z / 3 * 100, -100, 100)
        score_components['liquidity_breadth']['factors'] = [
            {'name': f['name'], 'z': f.get('z', 0), 'signal': f.get('emoji', '⚪')}
            for f in breadth_factors
        ]
    
    # 加入ETF扫描结果 (如果有)
    if etf_scan_results is not None and not etf_scan_results.empty:
        # 计算强势/弱势板块比例
        strong = len(etf_scan_results[etf_scan_results['评分'] >= 4])
        weak = len(etf_scan_results[etf_scan_results['评分'] <= 1])
        total = len(etf_scan_results)
        
        if total > 0:
            etf_score = ((strong - weak) / total) * 100
            # 微调板块轮动评分 (加权平均)
            old_score = score_components['sector_rotation']['score']
            score_components['sector_rotation']['score'] = old_score * 0.7 + etf_score * 0.3
    
    # 综合评分
    total_score = sum(
        comp['score'] * comp['weight']
        for comp in score_components.values()
    )
    
    # 判断市场状态
    if total_score > 60:
        market_state = '🚀 强力进攻 (Strong Risk-On)'
    elif total_score > 20:
        market_state = '📈 震荡偏多 (Mild Risk-On)'
    elif total_score > -20:
        market_state = '⚖️ 无序震荡 (Neutral)'
    elif total_score > -60:
        market_state = '📉 避险调整 (Mild Risk-Off)'
    else:
        market_state = '🔻 恐慌抛售 (Strong Risk-Off)'
    
    return {
        'total_score': np.clip(total_score, -100, 100),
        'market_state': market_state,
        'components': score_components,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M'),
    }


# ==================== 测试 ====================

if __name__ == '__main__':
    print("测试 SOFR/Repo 数据获取...")
    sofr_data = get_sofr_repo_history()
    print(f"  SOFR: {sofr_data['current_sofr']:.2f}%")
    print(f"  TGCR: {sofr_data['current_tgcr']:.2f}%")
    print(f"  利差: {sofr_data['current_spread']:.3f}%")
    print(f"  预警: {sofr_data['spread_alert_msg']}")
    
    print("\n测试 RRP/TGA 数据获取...")
    rrp_tga = get_rrp_tga_history()
    print(f"  RRP: ${rrp_tga['current_rrp']:.0f}B")
    print(f"  TGA: ${rrp_tga['current_tga']:.0f}B")
