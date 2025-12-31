"""
宏观战情室 V2 - 数据获取模块
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import warnings
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
        
    def _get_cache_path(self, name):
        """获取缓存文件路径"""
        return os.path.join(self.cache_dir, f"{name}.csv")
    
    def _is_cache_valid(self, cache_path):
        """检查缓存是否有效"""
        if not os.path.exists(cache_path):
            return False
        mtime = datetime.fromtimestamp(os.path.getmtime(cache_path))
        return datetime.now() - mtime < timedelta(hours=CACHE_EXPIRY_HOURS)
    
    def _save_cache(self, df, name):
        """保存到缓存"""
        cache_path = self._get_cache_path(name)
        df.to_csv(cache_path)
        
    def _load_cache(self, name):
        """从缓存加载"""
        cache_path = self._get_cache_path(name)
        if self._is_cache_valid(cache_path):
            df = pd.read_csv(cache_path, index_col=0, parse_dates=True)
            return df
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
                return cached
        
        try:
            from fredapi import Fred
            import os
            
            # 尝试从环境变量获取API key
            api_key = os.environ.get('FRED_API_KEY', '0e47e16eb3d393d2b253e32f44c4ad5c')
            fred = Fred(api_key=api_key)
            
            data = {}
            for symbol, name in indicators.items():
                try:
                    series = fred.get_series(symbol, observation_start=start_date)
                    if series is not None and len(series) > 0:
                        data[symbol] = series
                        print(f"✓ FRED: {symbol} ({name})")
                except Exception as e:
                    print(f"✗ FRED: {symbol} - {str(e)[:50]}")
                    
            if data:
                df = pd.DataFrame(data)
                df.index = pd.to_datetime(df.index)
                df = df.ffill()  # 前向填充缺失值
                self._save_cache(df, cache_name)
                return df
            return pd.DataFrame()
            
        except ImportError:
            print("需要安装 fredapi: pip install fredapi")
            return pd.DataFrame()
        except Exception as e:
            print(f"FRED数据获取失败: {e}")
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
                return cached
        
        try:
            import yfinance as yf
            
            print(f"正在获取 {len(tickers)} 个Yahoo Finance标的...")
            
            # 批量下载
            data = yf.download(tickers, period=period, progress=False, threads=True)
            
            if data.empty:
                print("Yahoo Finance返回空数据")
                return pd.DataFrame()
                
            # 提取收盘价
            if 'Close' in data.columns:
                # 单个ticker的情况
                prices = data['Close'].to_frame()
            else:
                # 多个ticker的情况
                prices = data['Close'] if 'Close' in data.columns.get_level_values(0) else data.xs('Close', axis=1, level=0)
            
            # 确保是DataFrame
            if isinstance(prices, pd.Series):
                prices = prices.to_frame()
                
            prices = prices.ffill()
            self._save_cache(prices, cache_name)
            
            print(f"✓ Yahoo Finance: 获取了 {len(prices.columns)} 个标的")
            return prices
            
        except ImportError:
            print("需要安装 yfinance: pip install yfinance")
            return pd.DataFrame()
        except Exception as e:
            print(f"Yahoo Finance数据获取失败: {e}")
            import traceback
            traceback.print_exc()
            return pd.DataFrame()
    
    # ==================== AKShare 数据 ====================
    
    def fetch_akshare_data(self, force_refresh=False):
        """获取A股/港股指数数据"""
        cache_name = 'akshare_data'
        if not force_refresh:
            cached = self._load_cache(cache_name)
            if cached is not None:
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
                        # 只保留最近2年
                        df = df[df.index >= datetime.now() - timedelta(days=730)]
                        data[symbol] = df['close']
                        print(f"✓ AKShare: {symbol} ({name})")
                except Exception as e:
                    print(f"✗ AKShare: {symbol} - {str(e)[:50]}")
            
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
            
            if data:
                df = pd.DataFrame(data)
                df.index = pd.to_datetime(df.index)
                df = df.ffill()
                self._save_cache(df, cache_name)
                return df
            return pd.DataFrame()
            
        except ImportError:
            print("需要安装 akshare: pip install akshare")
            return pd.DataFrame()
        except Exception as e:
            print(f"AKShare数据获取失败: {e}")
            return pd.DataFrame()
    
    # ==================== 合并所有数据 ====================
    
    def fetch_all_data(self, force_refresh=False):
        """获取所有数据并合并"""
        print("=" * 50)
        print("开始获取数据...")
        print("=" * 50)
        
        # FRED数据
        fred_data = self.fetch_fred_data(force_refresh=force_refresh)
        
        # Yahoo数据
        yahoo_data = self.fetch_yahoo_data(force_refresh=force_refresh)
        
        # AKShare数据
        akshare_data = self.fetch_akshare_data(force_refresh=force_refresh)
        
        print("=" * 50)
        print("数据获取完成")
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
                    # 获取最新非空值
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
