"""
宏观战情室 V2 - 配置文件
"""
from datetime import datetime

# ==================== 数据源配置 ====================

# FRED 指标
FRED_INDICATORS = {
    # 流动性指标
    'WALCL': 'Fed资产负债表',
    'RRPONTSYD': 'RRP逆回购',
    'WTREGEN': 'TGA财政账户',
    'SOFR': 'SOFR利率',
    # 利率指标
    'DGS10': '10Y国债收益率',
    'DGS2': '2Y国债收益率',
    'DGS3MO': '3M国债收益率',
    'T10YIE': '10Y盈亏平衡通胀',
    'DFF': '有效联邦基金利率',
    # 日本利率 (月频，需要特殊处理)
    'IRLTLT01JPM156N': '日本10Y国债收益率',
}

# Yahoo Finance 指标
YAHOO_INDICATORS = {
    # 货币
    'DX-Y.NYB': 'DXY美元指数',
    'JPY=X': 'USDJPY',
    # 波动率
    '^VIX': 'VIX',
    # 信用
    'HYG': '高收益债ETF',
    'LQD': '投资级债ETF',
    'TLT': '长期国债ETF',
}

# 全球轮动ETF
ROTATION_ETFS = {
    # 美股
    'SPY': '美股大盘',
    'QQQ': '纳斯达克100',
    'IWM': '罗素2000小盘',
    # 贵金属/商品
    'GLD': '黄金',
    'SLV': '白银',
    'CPER': '铜',
    'DBC': '商品综合',
    'USO': '原油',
    # 国际市场
    'EEM': '新兴市场',
    'EWH': '港股ETF',
    'FXI': '中国大盘ETF',
    'ASHR': 'A股沪深300ETF',
    # 极端情绪
    'BTC-USD': '比特币',
    'ARKK': 'ARK创新ETF',
}

# 美股板块对
SECTOR_PAIRS = {
    # 风险偏好因子
    'risk_appetite': {
        'SPHB/SPLV': ('SPHB', 'SPLV', '高β/低波'),
        'IWF/IWD': ('IWF', 'IWD', '成长/价值'),
        'HYG/TLT': ('HYG', 'TLT', '垃圾债/国债'),
        'ARKK/SPY': ('ARKK', 'SPY', '投机/主流'),
    },
    # 板块轮动因子
    'sector_rotation': {
        'XLK/XLP': ('XLK', 'XLP', '科技/必需'),
        'SMH/QQQ': ('SMH', 'QQQ', '半导体/纳指'),
        'IGV/QQQ': ('IGV', 'QQQ', '软件/纳指'),
        'XLY/XLU': ('XLY', 'XLU', '可选/公用'),
        'XLF/SPY': ('XLF', 'SPY', '金融/大盘'),
    },
    # 市场广度因子
    'breadth': {
        'IWM/SPY': ('IWM', 'SPY', '小盘/大盘'),
        'RSP/SPY': ('RSP', 'SPY', '等权/市值'),
        'EEM/SPY': ('EEM', 'SPY', '新兴/美股'),
    },
}

# AKShare 指数 (A股/港股)
AKSHARE_INDICES = {
    'sh000300': '沪深300',
    'sh000001': '上证指数',
}

AKSHARE_HK_INDICES = {
    '恒生指数': 'HSI',
}

# ==================== 计算参数 ====================

# Z-Score 回看期
ZSCORE_WINDOWS = {
    'short': 60,   # 短期 (约3个月)
    'long': 252,   # 长期 (约1年)
}

# 趋势判断参数
TREND_MA_PERIODS = {
    'fast': 20,
    'slow': 50,
}

# 相对强度计算期
RS_PERIOD = 20

# ==================== 评分系统 ====================

# 评分权重
SCORE_WEIGHTS = {
    'liquidity': 0.30,      # 流动性
    'currency': 0.25,       # 货币/利率
    'rotation': 0.25,       # 全球轮动
    'us_structure': 0.20,   # 美股结构
}

# 子评分权重
LIQUIDITY_WEIGHTS = {
    'net_liquidity_trend': 0.40,
    'rrp_change': 0.15,
    'tga_change': 0.15,
    'hyg_lqd': 0.30,
}

CURRENCY_WEIGHTS = {
    'dxy_trend': 0.30,
    'usdjpy_trend': 0.25,
    'real_rate_trend': 0.25,
    'term_spread': 0.20,
}

ROTATION_WEIGHTS = {
    'risk_assets_rs': 0.40,
    'safe_assets_rs': 0.30,
    'em_vs_dm': 0.30,
}

US_STRUCTURE_WEIGHTS = {
    'risk_appetite': 0.35,
    'sector_rotation': 0.35,
    'breadth': 0.30,
}

# ==================== 预警系统 ====================

# Z-Score 阈值
ALERT_THRESHOLDS = {
    'extreme': 2.0,      # |Z| > 2.0 → 红色预警
    'warning': 1.5,      # |Z| > 1.5 → 黄色关注
}

# 关键位置预警
KEY_LEVELS = {
    'DXY': {'below': 100, 'above': 108},
    'USDJPY': {'below': 145, 'above': 160},
    'VIX': {'above': 25},
    'HYG_LQD': {'below': 0.70, 'above': 0.78},
    'TERM_SPREAD': {'below': -0.5},  # 深度倒挂
}

# ==================== 央行政策代理指标 ====================

# 当前Fed利率 (需要定期手动更新，或从FRED DFF获取)
CURRENT_FED_RATE = 4.375  # 4.25-4.50% 中值

# BOJ当前利率
CURRENT_BOJ_RATE = 0.75

# ==================== 缓存配置 ====================

CACHE_DIR = 'cache'
CACHE_EXPIRY_HOURS = 12  # 缓存过期时间

# ==================== UI 配置 ====================

# 颜色方案
COLORS = {
    'positive': '#00C853',    # 绿色
    'negative': '#FF1744',    # 红色
    'neutral': '#FFD600',     # 黄色
    'info': '#2196F3',        # 蓝色
    'background': '#1E1E1E',  # 深色背景
}

# 评分颜色映射
def get_score_color(score):
    if score >= 30:
        return COLORS['positive']
    elif score <= -30:
        return COLORS['negative']
    else:
        return COLORS['neutral']

# Z-Score 信号映射
def get_zscore_signal(z, threshold=1.5):
    if z > threshold:
        return '🟢', '强势'
    elif z < -threshold:
        return '🔴', '弱势'
    else:
        return '⚪', '中性'
