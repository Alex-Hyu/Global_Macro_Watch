"""
宏观战情室 V2 - 数据获取模块
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import warnings
import time
warnings.filterwarnings('ignore')

from config import (
    FRED_INDICATORS, YAHOO_INDICATORS, ROTATION_ETFS, 
    SECTOR_PAIRS, AKSHARE_INDICES, AKSHARE_HK_INDICES,
    CACHE_DIR, CACHE_EXPIRY_HOURS
)


class DataFetcher:
    """数据获取器"""
    
    def __init__(self, cache_dir=CACHE_DIR):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self._fred = None
        self.errors = []
        
    def _get_cache_path(self, name):
        """获取缓存文件路径"""
        return os.path.join(self.cache_dir, f"{name}.csv")
    
    def _is_cache_valid(self, cache_path, hours=None):
        """检查缓存是否有效"""
        if hours is None:
            hours = CACHE_EXPIRY_HOURS
        if not os.path.exists(cache_path):
            return False
        mtime = datetime.fromtimestamp(os.path.getmtime(cache_path))
        return datetime.now() - mtime < timedelta(hours=hours)
    
    def _save_cache(self, df, name):
        """保存到缓存"""
        if df is not None and not df.empty:
            cache_path = self._get_cache_path(name)
            df.to_csv(cache_path)
        
    def _load_cache(self, name):
        """从缓存加载"""
        cache_path = self._get_cache_path(name)
        if self._is_cache_valid(cache_path):
            try:
                df = pd.read_csv(cache_path, index_col=0, parse_dates=True)
                return df
            except Exception as e:
                print(f"缓存加载失败: {e}")
        return None
    
    # ==================== FRED 数据 ====================
    
    def fetch_fred_data(self, indicators=None, start_date='2023-01-01', force_refresh=False):
        """获取FRED数据"""
        if indicators is None:
            indicators = FRED_INDICATORS
            
        cache_name = 'fred_data'
        if not force_refresh:
            cached = self._load_cache(cache_name)
            if cached is not None:
                print(f"✓ FRED: 从缓存加载 {len(cached.columns)} 个指标")
                return cached
        
        try:
            from fredapi import Fred
            
            # 尝试从环境变量获取API key，或使用Streamlit secrets
            api_key = os.environ.get('FRED_API_KEY')
            if not api_key:
                try:
                    import streamlit as st
                    api_key = st.secrets.get("FRED_API_KEY")
                except:
                    pass
            if not api_key:
                # 默认key
                api_key = 'c804807c4d5649ebeba394d4ab50f3c1'
            
            fred = Fred(api_key=api_key)
            
            data = {}
            for symbol, name in indicators.items():
                try:
                    series = fred.get_series(symbol, observation_start=start_date)
                    if series is not None and len(series) > 0:
                        data[symbol] = series
                        print(f"✓ FRED: {symbol} ({name})")
                except Exception as e:
                    error_msg = str(e)[:80]
                    print(f"✗ FRED: {symbol} - {error_msg}")
                    self.errors.append(f"FRED {symbol}: {error_msg}")
                    
            if data:
                df = pd.DataFrame(data)
                df.index = pd.to_datetime(df.index)
                df = df.ffill()
                self._save_cache(df, cache_name)
                return df
            return pd.DataFrame()
            
        except ImportError:
            print("需要安装 fredapi: pip install fredapi")
            self.errors.append("FRED: 需要安装 fredapi")
            return pd.DataFrame()
        except Exception as e:
            print(f"FRED数据获取失败: {e}")
            self.errors.append(f"FRED: {str(e)[:80]}")
            return pd.DataFrame()
    
    # ==================== Yahoo Finance 数据 ====================
    
    def fetch_yahoo_data(self, tickers=None, period='2y', force_refresh=False):
        """获取Yahoo Finance数据"""
        if tickers is None:
            # 合并所有需要的ticker
            tickers = list(YAHOO_INDICATORS.keys())
            tickers.extend(ROTATION_ETFS.keys())
            # 添加板块对的所有ticker
            for category in SECTOR_PAIRS.values():
                for pair_info in category.values():
                    tickers.extend([pair_info[0], pair_info[1]])
            tickers = list(set(tickers))
            
        cache_name = 'yahoo_data'
        if not force_refresh:
            cached = self._load_cache(cache_name)
            if cached is not None:
                print(f"✓ Yahoo: 从缓存加载 {len(cached.columns)} 个标的")
                return cached
        
        try:
            import yfinance as yf
            
            print(f"正在获取 {len(tickers)} 个Yahoo Finance标的...")
            
            all_prices = {}
            failed_tickers = []
            
            # 先尝试批量下载
            try:
                data = yf.download(tickers, period=period, progress=False, threads=True, timeout=30)
                
                if not data.empty:
                    # 提取收盘价
                    if isinstance(data.columns, pd.MultiIndex):
                        prices = data['Close']
                    elif 'Close' in data.columns:
                        prices = data[['Close']]
                        prices.columns = [tickers[0]] if len(tickers) == 1 else prices.columns
                    else:
                        prices = data
                    
                    for col in prices.columns:
                        if prices[col].notna().sum() > 10:
                            all_prices[col] = prices[col]
                    
                    print(f"✓ Yahoo批量: 获取了 {len(all_prices)} 个标的")
            except Exception as e:
                print(f"Yahoo批量下载失败: {e}")
                # 批量失败，尝试单独获取
                for ticker in tickers:
                    try:
                        stock = yf.Ticker(ticker)
                        hist = stock.history(period=period)
                        if not hist.empty and len(hist) > 10:
                            all_prices[ticker] = hist['Close']
                            print(f"✓ Yahoo: {ticker}")
                        else:
                            failed_tickers.append(ticker)
                    except Exception as e2:
                        failed_tickers.append(ticker)
                        print(f"✗ Yahoo: {ticker}")
                    time.sleep(0.1)  # 避免请求过快
            
            if all_prices:
                df = pd.DataFrame(all_prices)
                df.index = pd.to_datetime(df.index)
                if df.index.tz is not None:
                    df.index = df.index.tz_localize(None)
                df = df.ffill()
                self._save_cache(df, cache_name)
                print(f"✓ Yahoo Finance: 共获取 {len(df.columns)} 个标的")
                if failed_tickers:
                    print(f"  失败: {len(failed_tickers)} 个")
                return df
            
            print("Yahoo Finance: 未获取到任何数据")
            return pd.DataFrame()
            
        except ImportError:
            print("需要安装 yfinance: pip install yfinance")
            self.errors.append("Yahoo: 需要安装 yfinance")
            return pd.DataFrame()
        except Exception as e:
            print(f"Yahoo Finance数据获取失败: {e}")
            self.errors.append(f"Yahoo: {str(e)[:80]}")
            return pd.DataFrame()
    
    # ==================== AKShare 数据 ====================
    
    def fetch_akshare_data(self, force_refresh=False):
        """获取A股/港股指数数据"""
        cache_name = 'akshare_data'
        if not force_refresh:
            cached = self._load_cache(cache_name)
            if cached is not None:
                print(f"✓ AKShare: 从缓存加载 {len(cached.columns)} 个指数")
                return cached
        
        try:
            import akshare as ak
            
            data = {}
            
            # A股指数
            for symbol, name in AKSHARE_INDICES.items():
                try:
                    df = ak.stock_zh_index_daily(symbol=symbol)
                    if df is not None and len(df) > 0:
                        df['date'] = pd.to_datetime(df['date'])
                        df = df.set_index('date')
                        df = df[df.index >= datetime.now() - timedelta(days=730)]
                        data[symbol] = df['close']
                        print(f"✓ AKShare: {symbol} ({name})")
                except Exception as e:
                    print(f"✗ AKShare: {symbol} - {str(e)[:50]}")
                    self.errors.append(f"AKShare {symbol}: {str(e)[:50]}")
            
            # 港股指数
            for name, symbol in AKSHARE_HK_INDICES.items():
                try:
                    df = ak.stock_hk_index_daily_em(symbol=name)
                    if df is not None and len(df) > 0:
                        df['日期'] = pd.to_datetime(df['日期'])
                        df = df.set_index('日期')
                        df = df[df.index >= datetime.now() - timedelta(days=730)]
                        data[symbol] = df['收盘']
                        print(f"✓ AKShare: {name} ({symbol})")
                except Exception as e:
                    print(f"✗ AKShare: {name} - {str(e)[:50]}")
                    self.errors.append(f"AKShare {name}: {str(e)[:50]}")
            
            if data:
                df = pd.DataFrame(data)
                df.index = pd.to_datetime(df.index)
                df = df.ffill()
                self._save_cache(df, cache_name)
                return df
            return pd.DataFrame()
            
        except ImportError:
            print("AKShare未安装，跳过A股/港股数据")
            return pd.DataFrame()
        except Exception as e:
            print(f"AKShare数据获取失败: {e}")
            self.errors.append(f"AKShare: {str(e)[:80]}")
            return pd.DataFrame()
    
    # ==================== 合并所有数据 ====================
    
    def fetch_all_data(self, force_refresh=False):
        """获取所有数据并合并"""
        self.errors = []
        
        print("=" * 50)
        print("开始获取数据...")
        print("=" * 50)
        
        # FRED数据
        fred_data = self.fetch_fred_data(force_refresh=force_refresh)
        
        # Yahoo数据 (主要数据源)
        yahoo_data = self.fetch_yahoo_data(force_refresh=force_refresh)
        
        # AKShare数据 (可选)
        akshare_data = self.fetch_akshare_data(force_refresh=force_refresh)
        
        print("=" * 50)
        print("数据获取完成")
        
        # 汇总
        total_indicators = 0
        if not fred_data.empty:
            total_indicators += len(fred_data.columns)
        if not yahoo_data.empty:
            total_indicators += len(yahoo_data.columns)
        if not akshare_data.empty:
            total_indicators += len(akshare_data.columns)
            
        print(f"总计: {total_indicators} 个指标")
        if self.errors:
            print(f"错误: {len(self.errors)} 个")
        print("=" * 50)
        
        return {
            'fred': fred_data,
            'yahoo': yahoo_data,
            'akshare': akshare_data,
        }
    
    def get_latest_values(self, all_data):
        """获取所有指标的最新值"""
        latest = {}
        
        for source, df in all_data.items():
            if df is not None and not df.empty:
                for col in df.columns:
                    valid = df[col].dropna()
                    if len(valid) > 0:
                        latest[col] = {
                            'value': valid.iloc[-1],
                            'date': valid.index[-1],
                            'source': source,
                        }
        
        return latest


# ==================== 便捷函数 ====================

def fetch_data(force_refresh=False):
    """便捷函数：获取所有数据"""
    fetcher = DataFetcher()
    return fetcher.fetch_all_data(force_refresh=force_refresh)


if __name__ == '__main__':
    # 测试数据获取
    data = fetch_data(force_refresh=True)
    
    print("\n数据摘要:")
    for source, df in data.items():
        if df is not None and not df.empty:
            print(f"  {source}: {len(df.columns)} 列, {len(df)} 行")
            print(f"    时间范围: {df.index.min()} ~ {df.index.max()}")
