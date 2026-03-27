"""
整合补丁 - 将新闻情绪模块加入宏观战情室

使用方法:
1. 把 news_sentiment_module.py 放到 app.py 同级目录
2. 按照下面的说明修改 app.py

修改位置一共3处:
1. 顶部导入区域
2. 侧边栏配置区域 (可选 - Telegram设置)
3. 主内容区域 (添加新闻情绪板块)
"""

# ============================================================================
# 修改1: 在 app.py 顶部的导入区域添加 (约第70行之后)
# ============================================================================

IMPORT_PATCH = '''
# 导入新闻情绪模块
try:
    from news_sentiment_module import (
        render_news_sentiment_section,
        get_news_sentiment_for_prompt,
        NewsSentimentModule,
        FINNHUB_API_KEY,
    )
    NEWS_SENTIMENT_AVAILABLE = True
except ImportError:
    NEWS_SENTIMENT_AVAILABLE = False
'''

# ============================================================================
# 修改2: 在侧边栏添加Telegram配置 (可选)
# 位置: 在 "SpotGamma个股数据" 区块之后添加
# ============================================================================

SIDEBAR_PATCH = '''
        # ==================== 新闻情绪配置 ====================
        if NEWS_SENTIMENT_AVAILABLE:
            st.divider()
            st.subheader("📰 新闻情绪配置")
            
            # Telegram推送设置
            tg_enabled = st.checkbox("启用Telegram预警推送", value=False, key="tg_enabled")
            
            if tg_enabled:
                tg_token = st.text_input("Bot Token", type="password", key="tg_token",
                                        help="从BotFather获取")
                tg_chat = st.text_input("Chat ID", key="tg_chat",
                                       help="你的Telegram Chat ID")
                
                if tg_token and tg_chat:
                    st.session_state['telegram_config'] = {
                        'enabled': True,
                        'bot_token': tg_token,
                        'chat_id': tg_chat,
                        'webhook_url': None
                    }
                    st.success("✅ Telegram已配置")
                else:
                    st.session_state['telegram_config'] = {'enabled': False}
            else:
                st.session_state['telegram_config'] = {'enabled': False}
'''

# ============================================================================
# 修改3: 在主内容区域添加新闻情绪板块
# 位置: 在 "第七章: SpotGamma分析" 之后, "第八章: 个股多空分析" 之前
# 或者作为新的第八章，原来的第八章改为第九章
# ============================================================================

MAIN_CONTENT_PATCH = '''
    # ==================== 第八章：新闻情绪监控 ====================
    
    if NEWS_SENTIMENT_AVAILABLE:
        # 获取Gamma环境 (如果SpotGamma数据可用)
        gamma_env = None
        if 'spotgamma_analysis' in st.session_state:
            sg_data = st.session_state['spotgamma_analysis']
            if sg_data.get('gamma_environment') == 'positive':
                gamma_env = 'positive'
            else:
                gamma_env = 'negative'
        
        # 渲染新闻情绪板块
        render_news_sentiment_section(gamma_environment=gamma_env)
'''

# ============================================================================
# 修改4: 在Claude Prompt生成部分添加新闻情绪摘要
# 位置: 在 generate_claude_prompt 调用之后
# ============================================================================

PROMPT_PATCH = '''
    # 添加新闻情绪到prompt
    if NEWS_SENTIMENT_AVAILABLE:
        try:
            news_summary = get_news_sentiment_for_prompt()
            if news_summary:
                prompt = prompt + "\\n\\n" + news_summary
        except:
            pass
'''

# ============================================================================
# 完整的修改后代码片段示例
# ============================================================================

FULL_EXAMPLE = '''
# ================== app.py 修改示例 ==================

# === 1. 在文件顶部导入区 (约第70行) 添加: ===

# 导入新闻情绪模块
try:
    from news_sentiment_module import (
        render_news_sentiment_section,
        get_news_sentiment_for_prompt,
        NewsSentimentModule,
    )
    NEWS_SENTIMENT_AVAILABLE = True
except ImportError:
    NEWS_SENTIMENT_AVAILABLE = False


# === 2. 在侧边栏 SpotGamma个股数据 之后添加: ===
# (约第645行之后)

        # ==================== 新闻情绪配置 ====================
        if NEWS_SENTIMENT_AVAILABLE:
            st.divider()
            st.subheader("📰 新闻情绪配置")
            tg_enabled = st.checkbox("启用Telegram预警", value=False, key="tg_enabled")
            if tg_enabled:
                tg_token = st.text_input("Bot Token", type="password", key="tg_token")
                tg_chat = st.text_input("Chat ID", key="tg_chat")


# === 3. 在主内容区添加新闻板块 ===
# 在黄金分析之后、个股分析之前 (约第1550行)

    # ==================== 新闻情绪监控 ====================
    
    if NEWS_SENTIMENT_AVAILABLE:
        # 获取Gamma环境
        gamma_env = None
        if 'spotgamma_analysis' in st.session_state:
            sg_data = st.session_state['spotgamma_analysis']
            gamma_env = 'positive' if sg_data.get('gamma_environment') == 'positive' else 'negative'
        
        render_news_sentiment_section(gamma_environment=gamma_env)


# === 4. 在Claude Prompt部分添加新闻摘要 ===
# (约第1823行之后)

    # 添加新闻情绪到prompt
    if NEWS_SENTIMENT_AVAILABLE:
        try:
            news_summary = get_news_sentiment_for_prompt()
            if news_summary:
                prompt = prompt + "\\n\\n" + news_summary
        except:
            pass
'''

# ============================================================================
# 打印说明
# ============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("宏观战情室 - 新闻情绪模块整合指南")
    print("=" * 60)
    print()
    print("文件清单:")
    print("  1. news_sentiment_module.py - 新闻情绪模块主文件")
    print("  2. integration_patch.py - 本文件，整合说明")
    print()
    print("整合步骤:")
    print("  1. 把 news_sentiment_module.py 放到 app.py 同级目录")
    print("  2. 在 app.py 顶部添加导入代码")
    print("  3. 在主内容区添加 render_news_sentiment_section()")
    print("  4. (可选) 在侧边栏添加Telegram配置")
    print("  5. (可选) 在Claude Prompt中添加新闻摘要")
    print()
    print("详细代码见上方 FULL_EXAMPLE 变量")
    print("=" * 60)
