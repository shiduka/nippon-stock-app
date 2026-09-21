import os
import yfinance as yf
import pandas as pd
from supabase import create_client, Client
from dotenv import load_dotenv

def get_supabase_client() -> Client:
    load_dotenv()
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise ValueError("SUPABASE_URL or SUPABASE_KEY is missing in .env")
    return create_client(url, key)

def fetch_historical_prices(years=10):
    print("=== 過去の株価データの一括取得を開始します ===")
    supabase = get_supabase_client()
    
    # 優待を実施している銘柄のみを取得
    print("Supabaseから優待銘柄一覧を取得中...")
    active_tickers = set()
    page_size = 1000
    start = 0
    while True:
        res = supabase.table("shareholder_benefits").select("ticker_symbol").range(start, start + page_size - 1).execute()
        if not res.data:
            break
        active_tickers.update(row['ticker_symbol'] for row in res.data)
        start += page_size
        
    tickers = list(active_tickers)
    print(f"対象銘柄数: {len(tickers)} 件")
    
    # yfinance用のシンボルリスト作成 (例: 7203 -> 7203.T)
    yf_symbols = [f"{t}.T" for t in tickers]
    
    # データを保存するディレクトリ
    os.makedirs('data', exist_ok=True)
    parquet_path = f"data/historical_prices_{years}y.parquet"
    
    print(f"\nyfinanceから過去{years}年分のデータを一括ダウンロードしています...")
    print("（※対象が多い場合、数分〜10分程度かかります）")
    
    # yfinance で一括ダウンロード
    # group_by="ticker" を指定すると、銘柄ごとのマルチインデックスになる
    data = yf.download(yf_symbols, period=f"{years}y", group_by="ticker", auto_adjust=False, threads=True)
    
    if data.empty:
        print("エラー: データのダウンロードに失敗しました。")
        return
        
    print("\nデータの整形中...")
    
    # データをフラットな形式（DBと同じ形式）に変換する
    records = []
    
    # 取得できた銘柄についてループ
    for t in tickers:
        yf_sym = f"{t}.T"
        if yf_sym not in data.columns.levels[0]:
            continue
            
        df_ticker = data[yf_sym].dropna(subset=['Close'])
        
        for date, row in df_ticker.iterrows():
            records.append({
                'ticker_symbol': t,
                'trade_date': date.strftime('%Y-%m-%d'),
                'open_price': float(row['Open']) if pd.notna(row['Open']) else None,
                'high_price': float(row['High']) if pd.notna(row['High']) else None,
                'low_price': float(row['Low']) if pd.notna(row['Low']) else None,
                'close_price': float(row['Close']) if pd.notna(row['Close']) else None,
                'adjusted_close': float(row['Adj Close']) if 'Adj Close' in row and pd.notna(row['Adj Close']) else float(row['Close']),
                'volume': int(row['Volume']) if pd.notna(row['Volume']) else 0
            })
            
    df_records = pd.DataFrame(records)
    
    if df_records.empty:
        print("有効なデータがありません。")
        return
        
    print(f"\n総レコード数: {len(df_records):,} 件")
    
    # Parquetとして保存
    print(f"Parquetファイルとして保存しています: {parquet_path}")
    df_records.to_parquet(parquet_path, index=False)
    
    print("\n完了しました！")
    print("このParquetファイルを使って、アノマリーの分析スクリプトを実行できます。")

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(line_buffering=True)
    fetch_historical_prices(years=10)
