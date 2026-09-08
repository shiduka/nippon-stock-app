import os
import yfinance as yf
import pandas as pd
from datetime import datetime
import time
from dotenv import load_dotenv
from supabase import create_client, Client

def init_supabase() -> Client:
    load_dotenv()
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise ValueError(".envにSUPABASE_URLまたはSUPABASE_KEYが設定されていません")
    return create_client(url, key)

def get_active_tickers(supabase: Client, limit=None):
    """Supabaseの企業マスターから上場中の銘柄コード一覧を取得する"""
    print("Supabaseから取得対象の銘柄を読み込んでいます...")
    
    all_tickers = []
    start = 0
    step = 1000
    
    # 1000件制限を回避するため、全件取れるまでループ
    while True:
        res = supabase.table("companies").select("ticker_symbol").eq("status", "ACTIVE").range(start, start + step - 1).execute()
        if not res.data:
            break
        all_tickers.extend([item['ticker_symbol'] for item in res.data])
        start += step
        
    if limit:
        all_tickers = all_tickers[:limit]
    
    print(f"取得対象: {len(all_tickers)} 銘柄")
    return all_tickers

def fetch_daily_stock_data(ticker_list, days=3):
    """yfinanceを利用して直近の株価を取得する"""
    results = []
    total = len(ticker_list)
    
    for i, ticker in enumerate(ticker_list):
        yf_ticker = f"{ticker}.T"
        stock = yf.Ticker(yf_ticker)
        
        try:
            hist = stock.history(period=f"{days+1}d") 
            if hist.empty:
                continue
                
            hist['Prev_Close'] = hist['Close'].shift(1)
            hist['Price_Change'] = hist['Close'] - hist['Prev_Close']
            hist = hist.tail(days)
            
            for index, row in hist.iterrows():
                record = {
                    'ticker_symbol': ticker,
                    'trade_date': str(index.date()), # エラー防止のため文字列に変換
                    'open_price': float(row['Open']),
                    'high_price': float(row['High']),
                    'low_price': float(row['Low']),
                    'close_price': float(row['Close']),
                    'adjusted_close': float(row['Close']),
                    'volume': int(row['Volume']),
                    'price_change': float(row['Price_Change']) if not pd.isna(row['Price_Change']) else 0.0,
                    'is_stop_high': False,
                    'is_stop_low': False
                }
                results.append(record)
                
            # 進捗表示
            if (i + 1) % 10 == 0 or (i + 1) == total:
                print(f"  ... {i + 1} / {total} 銘柄を取得済み")
                
            time.sleep(0.1) # yfinanceサーバーへの負荷軽減
            
        except Exception as e:
            print(f"[{ticker}] 取得エラー: {e}")
            
    return results

def save_stock_prices(supabase: Client, data):
    """取得した株価をSupabaseへ保存(upsert)する"""
    total_count = len(data)
    print(f"\nSupabaseへの保存を開始します (合計 {total_count} レコード)")
    chunk_size = 1000
    success_count = 0
    
    for i in range(0, total_count, chunk_size):
        chunk = data[i:i + chunk_size]
        try:
            supabase.table('daily_stock_prices').upsert(chunk).execute()
            success_count += len(chunk)
            print(f"  [{success_count} / {total_count}] 件 保存完了...")
            time.sleep(0.5)
        except Exception as e:
            print(f"保存エラー: {e}")
            
    print("✅ 株価データの保存処理が完了しました！")

if __name__ == "__main__":
    supabase = init_supabase()
    
    # ⚠️ テスト実行用:
    # 全約4000社を一気に取得すると数十分かかってしまうため、
    # 今回はテストとして「上位30銘柄」だけを処理するようにしています。
    # （本番運用する際は limit=None に変更します）
    target_tickers = get_active_tickers(supabase, limit=None)
    
    if target_tickers:
        print("\nyfinanceから株価を取得中... (少々お待ちください)")
        stock_data = fetch_daily_stock_data(target_tickers, days=3)
        
        if stock_data:
            save_stock_prices(supabase, stock_data)
        else:
            print("保存できる株価データがありませんでした。")
