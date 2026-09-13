import os
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

def get_active_tickers(supabase: Client, limit: int = None):
    """アクティブな銘柄コードの一覧をDBから取得する"""
    query = supabase.table("companies").select("ticker_symbol").eq("status", "ACTIVE")
    if limit:
        query = query.limit(limit)
    res = query.execute()
    return [row["ticker_symbol"] for row in res.data]

def fetch_dividend_yields(ticker_list):
    """yfinanceから配当利回りを取得する"""
    results = []
    
    for i, ticker in enumerate(ticker_list):
        ticker_yf = f"{ticker}.T"
        
        try:
            stock = yf.Ticker(ticker_yf)
            info = stock.info
            
            dividend_yield = info.get('dividendYield')
            
            if dividend_yield is not None and dividend_yield > 0:
                # yfinanceは小数(0.033)で返す場合と%(3.3)で返す場合があるので正規化
                if dividend_yield < 1:
                    dividend_yield = round(dividend_yield * 100, 2)
                else:
                    dividend_yield = round(dividend_yield, 2)
                    
                results.append({
                    'ticker_symbol': ticker,
                    'dividend_yield': dividend_yield
                })
                print(f"  ✅ {ticker}: 配当利回り = {dividend_yield}%")
            else:
                # 無配の銘柄は0%として記録
                results.append({
                    'ticker_symbol': ticker,
                    'dividend_yield': 0.0
                })
                
        except Exception as e:
            print(f"  ❌ [{ticker}] 取得エラー: {e}")
        
        # 進捗表示
        if (i + 1) % 50 == 0:
            print(f"  ... {i + 1} / {len(ticker_list)} 銘柄を処理済み")
        
        # サーバー負荷軽減
        time.sleep(0.5)
    
    return results

if __name__ == "__main__":
    print("配当利回りの取得を開始します (yfinance経由)...")
    supabase = get_supabase_client()
    
    # 全銘柄を対象に取得
    target_tickers = get_active_tickers(supabase, limit=None)
    print(f"取得対象: {len(target_tickers)} 銘柄\n")
    
    data = fetch_dividend_yields(target_tickers)
    
    if data:
        print(f"\nSupabaseへの保存を開始します ({len(data)} 件)...")
        success_count = 0
        for record in data:
            try:
                supabase.table("companies").update({
                    "dividend_yield": record["dividend_yield"]
                }).eq("ticker_symbol", record["ticker_symbol"]).execute()
                success_count += 1
            except Exception as e:
                print(f"  保存エラー [{record['ticker_symbol']}]: {e}")
        
        print(f"✅ {success_count} 件の配当利回りデータを保存しました！")
    else:
        print("データが取得できませんでした。")
