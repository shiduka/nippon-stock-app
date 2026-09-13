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
    tickers = []
    page_size = 1000
    start = 0
    
    while True:
        query = supabase.table("companies").select("ticker_symbol").eq("status", "ACTIVE")
        query = query.range(start, start + page_size - 1)
        res = query.execute()
        
        if not res.data:
            break
            
        tickers.extend([row["ticker_symbol"] for row in res.data])
        
        if limit and len(tickers) >= limit:
            tickers = tickers[:limit]
            break
            
        if len(res.data) < page_size:
            break
            
        start += page_size
        
    return tickers

def fetch_earnings_dates(ticker_list):
    """yfinanceから次回決算日を取得する"""
    results = []
    
    for i, ticker in enumerate(ticker_list):
        ticker_yf = f"{ticker}.T"
        
        try:
            stock = yf.Ticker(ticker_yf)
            cal = stock.calendar
            
            if cal and cal.get('Earnings Date'):
                earnings_date = cal['Earnings Date'][0].isoformat()
                results.append({
                    'ticker_symbol': ticker,
                    'next_earnings_date': earnings_date
                })
                print(f"  ✅ {ticker}: 次回決算日 = {earnings_date}")
            else:
                print(f"  ⚠️ {ticker}: 決算日データなし")
                
        except Exception as e:
            print(f"  ❌ [{ticker}] 取得エラー: {e}")
        
        # 進捗表示
        if (i + 1) % 50 == 0:
            print(f"  ... {i + 1} / {len(ticker_list)} 銘柄を処理済み")
        
        # サーバー負荷軽減のため少し待つ
        time.sleep(0.5)
    
    return results

if __name__ == "__main__":
    print("次回決算日の取得を開始します (yfinance経由)...")
    supabase = get_supabase_client()
    
    # 全銘柄を対象に取得
    target_tickers = get_active_tickers(supabase, limit=None)
    print(f"取得対象: {len(target_tickers)} 銘柄\n")
    
    data = fetch_earnings_dates(target_tickers)
    
    if data:
        print(f"\nSupabaseへの保存を開始します ({len(data)} 件)...")
        # 50件ずつバッチで更新（companiesテーブルのnext_earnings_dateカラムを更新）
        success_count = 0
        for record in data:
            try:
                supabase.table("companies").update({
                    "next_earnings_date": record["next_earnings_date"]
                }).eq("ticker_symbol", record["ticker_symbol"]).execute()
                success_count += 1
            except Exception as e:
                print(f"  保存エラー [{record['ticker_symbol']}]: {e}")
        
        print(f"✅ {success_count} 件の決算日データを保存しました！")
    else:
        print("データが取得できませんでした。")
