# 🌍 宏观战情室 V2

一个全面的宏观经济监控仪表盘，用于日常复盘和投资决策支持。

## 功能特性

### 📊 四层宏观监控框架

1. **流动性水位** - Fed净流动性、RRP、TGA、信用利差
2. **货币与利率风向** - DXY、USD/JPY、实际利率、收益率曲线
3. **全球资产轮动雷达** - 各类资产对SPY的相对强度排名
4. **美股内部结构** - 风险偏好、板块轮动、市场广度因子

### 🎯 智能评分系统

- **Z-Score双时间框架**: 60日(战术)和252日(战略)
- **综合评分**: -100到+100，直观展示宏观环境
- **自动预警**: 极端值(|Z|>2)触发红色预警

### 🏦 央行政策追踪

- **Fed政策代理**: 2Y国债 vs Fed利率的利差信号
- **BOJ政策代理**: USD/JPY动量反映日本政策预期

### 🤖 Claude分析入口

一键生成结构化数据摘要，复制粘贴给Claude进行深度宏观分析。

## 安装

```bash
# 克隆或下载项目
cd macro_dashboard

# 安装依赖
pip install -r requirements.txt

# 设置FRED API Key (可选，有默认key)
export FRED_API_KEY="your_api_key"

# 运行
streamlit run app.py
```

## 数据源

| 数据类型 | 来源 | 更新频率 |
|---------|------|---------|
| Fed流动性数据 | FRED API | 日更新 |
| ETF/股票价格 | Yahoo Finance | 实时 |
| A股/港股指数 | AKShare | 日更新 |

## 项目结构

```
macro_dashboard/
├── app.py                 # Streamlit主程序
├── data_fetcher.py        # 数据获取模块
├── indicators.py          # 指标计算模块
├── scoring.py             # 评分系统模块
├── prompt_generator.py    # Claude Prompt生成
├── config.py              # 配置文件
├── requirements.txt       # 依赖列表
├── cache/                 # 本地数据缓存
└── README.md
```

## 配置说明

### config.py 主要参数

```python
# Z-Score计算窗口
ZSCORE_WINDOWS = {
    'short': 60,   # 短期
    'long': 252,   # 长期
}

# 评分权重
SCORE_WEIGHTS = {
    'liquidity': 0.30,
    'currency': 0.25,
    'rotation': 0.25,
    'us_structure': 0.20,
}

# 预警阈值
ALERT_THRESHOLDS = {
    'extreme': 2.0,  # |Z| > 2.0 触发红色预警
    'warning': 1.5,  # |Z| > 1.5 触发黄色关注
}

# 当前央行利率 (需定期更新)
CURRENT_FED_RATE = 4.375  # 4.25-4.50%中值
CURRENT_BOJ_RATE = 0.75
```

## 使用指南

### 每日复盘流程

1. 启动应用: `streamlit run app.py`
2. 查看**综合评分**和**预警信号**
3. 逐章节分析各层面数据
4. 复制**Claude分析入口**的Prompt
5. 粘贴给Claude获取深度分析

### 评分解读

| 评分范围 | 含义 | 建议 |
|---------|------|------|
| +50 ~ +100 | 极度有利 | Risk-On，积极配置 |
| +20 ~ +50 | 较好 | 偏Risk-On |
| -20 ~ +20 | 中性 | 维持平衡 |
| -50 ~ -20 | 较差 | 偏Risk-Off |
| -100 ~ -50 | 极度不利 | Risk-Off，防御配置 |

### 预警信号说明

- 🔴 **红色预警**: Z-Score超过±2σ，极端状态
- 🟡 **黄色关注**: Z-Score超过±1.5σ，需要关注

## 指标解读

### 流动性三要素

```
净流动性 = Fed资产负债表 - RRP - TGA

- RRP下降 → 流动性释放 → 利好
- TGA下降 → 财政支出 → 利好
- 净流动性上升 → 风险资产有支撑
```

### Carry Trade风险

```
USD/JPY 20日动量:
- < -3% → 高风险 (日元快速走强)
- -1% ~ -3% → 中等风险
- > -1% → 低风险
```

### 全球轮动信号

```
相对强度 = (资产/SPY)的20日变化率
Z-Score > +2 → 极端强势，可能回调
Z-Score < -2 → 极端弱势，可能反弹
```

## 注意事项

1. **数据延迟**: FRED数据可能有1-2天延迟
2. **缓存机制**: 数据缓存12小时，点击"刷新数据"强制更新
3. **网络要求**: 需要访问FRED、Yahoo Finance、AKShare
4. **央行利率**: 需要在config.py中手动更新当前利率

## 后续计划

- [ ] 添加历史评分走势图
- [ ] 支持自定义指标权重
- [ ] 添加更多预警规则
- [ ] 支持数据导出
- [ ] 移动端优化

## License

MIT License
