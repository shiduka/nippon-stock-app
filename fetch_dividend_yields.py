import os
import sys
import time
import yfinance as yf
from supabase import create_client, Client
from dotenv import load_dotenv

# .envファイルから環境変数を読み込む
load_dotenv()

def get_supabase_client() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise ValueError("SUPABASE_URL or SUPABASE_KEY is missing in .env")
    return create_client(url, key)

def get_active_tickers(supabase: Client):
    """アクティブな銘柄コードの一覧をDBから取得する（1000件制限を回避）"""
    tickers = []
    page_size = 1000
    start = 0
    while True:
        res = supabase.table("companies").select("ticker_symbol").eq("status", "ACTIVE").range(start, start + page_size - 1).execute()
        if not res.data:
            break
        tickers.extend([row["ticker_symbol"] for row in res.data])
        if len(res.data) < page_size:
            break
        start += page_size
    return tickers

def fetch_and_save_dividend_yields():
    supabase = get_supabase_client()
    target_tickers = get_active_tickers(supabase)
    print(f"取得対象: {len(target_tickers)} 銘柄\n")
    
    success_count = 0
    skip_count = 0
    error_count = 0
    
    for i, ticker in enumerate(target_tickers):
        ticker_yf = f"{ticker}.T"
        
        try:
            stock = yf.Ticker(ticker_yf)
            info = stock.info
            
            # dividendYieldは%(例:3.31=3.31%)で返ってくる
            dividend_yield = info.get('dividendYield')
            
            if dividend_yield is not None and dividend_yield > 0:
                # yfinanceはパーセント値(例:3.31=3.31%, 0.95=0.95%)で返す
                dividend_yield = round(float(dividend_yield), 2)
                    
                supabase.table("companies").update({
                    "dividend_yield": dividend_yield
                }).eq("ticker_symbol", ticker).execute()
                
                success_count += 1
                if success_count % 50 == 0:
                    print(f"  ... {i + 1} / {len(target_tickers)} 処理済み（配当あり: {success_count}件）")
            else:
                # 無配/取得不可 → 0.0に更新（NULLのまま残さない）
                supabase.table("companies").update({
                    "dividend_yield": 0.0
                }).eq("ticker_symbol", ticker).execute()
                skip_count += 1
                
        except Exception as e:
            error_count += 1
            if error_count <= 10:
                print(f"  x [{ticker}] 取得エラー: {e}")
        
        # yfinanceレート制限回避のため適度に休憩
        time.sleep(0.3)
    
    print(f"\n完了: 配当あり {success_count}件 / 無配(0%) {skip_count}件 / エラー {error_count}件")

if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    print("=== 配当利回りの一括更新を開始します (yfinance経由) ===")
    fetch_and_save_dividend_yields()
