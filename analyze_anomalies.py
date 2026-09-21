import os
import sys
import pandas as pd
import numpy as np
from datetime import timedelta
from supabase import create_client, Client
from dotenv import load_dotenv

def get_supabase_client() -> Client:
    load_dotenv()
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise ValueError("SUPABASE_URL or SUPABASE_KEY is missing in .env")
    return create_client(url, key)

def get_last_business_day(df_dates, target_year, target_month):
    """
    対象月の最終営業日を株価データのカレンダーから取得する。
    """
    # 月の全営業日
    mask = (df_dates.dt.year == target_year) & (df_dates.dt.month == target_month)
    month_dates = df_dates[mask]
    
    if month_dates.empty:
        return None
        
    return month_dates.max()

def analyze_anomalies(parquet_path="data/historical_prices_10y.parquet"):
    print("=== 優待権利月の株価上昇アノマリー分析を開始します ===")
    
    if not os.path.exists(parquet_path):
        print(f"エラー: 株価データファイルが見つかりません: {parquet_path}")
        print("先に fetch_historical_prices.py を実行してデータを取得してください。")
        return
        
    print(f"株価データ ({parquet_path}) を読み込み中...")
    df_prices = pd.read_parquet(parquet_path)
    df_prices['trade_date'] = pd.to_datetime(df_prices['trade_date'])
    
    # 営業日カレンダー（全銘柄共通として概算）
    trading_days = pd.Series(df_prices['trade_date'].unique()).sort_values()
    
    supabase = get_supabase_client()
    
    # 優待銘柄とその権利確定月を取得
    print("Supabaseから優待の権利確定月を取得中...")
    benefits = []
    page_size = 1000
    start = 0
    while True:
        res = supabase.table("shareholder_benefits").select("ticker_symbol, record_month").range(start, start + page_size - 1).execute()
        if not res.data:
            break
        benefits.extend(res.data)
        start += page_size
        
    print(f"対象となる優待銘柄: {len(benefits)} 件")
    
    results = []
    
    # 処理の高速化のため、銘柄ごとにグループ化
    print("分析を実行中...")
    grouped = df_prices.groupby('ticker_symbol')
    
    processed_count = 0
    for benefit in benefits:
        ticker = benefit['ticker_symbol']
        record_month = benefit['record_month']
        
        if not record_month:
            continue
            
        if ticker not in grouped.groups:
            continue
            
        df_ticker = grouped.get_group(ticker).sort_values('trade_date').set_index('trade_date')
        
        if df_ticker.empty:
            continue
            
        years = df_ticker.index.year.unique()
        
        # 各月オフセット(1〜6ヶ月前)ごとのリターンを記録
        returns_by_offset = {1: [], 2: [], 3: [], 4: [], 5: [], 6: []}
        analyzed_years_count = 0
        
        for year in years:
            # 売却日（権利確定月の権利付き最終日＝月末から2〜3営業日前等だが、ここでは簡易的に対象月の最終営業日とする）
            sell_date = get_last_business_day(trading_days, year, record_month)
            if sell_date is None or sell_date not in df_ticker.index:
                continue
                
            sell_price = df_ticker.loc[sell_date, 'adjusted_close']
            
            # 各買いタイミングでのリターン計算
            valid_year = False
            for offset in range(1, 7):
                # 買い月を計算
                buy_month = record_month - offset
                buy_year = year
                if buy_month <= 0:
                    buy_month += 12
                    buy_year -= 1
                    
                buy_date = get_last_business_day(trading_days, buy_year, buy_month)
                if buy_date is None or buy_date not in df_ticker.index:
                    continue
                    
                buy_price = df_ticker.loc[buy_date, 'adjusted_close']
                
                # リターン計算 (分割調整後終値を使用)
                if buy_price > 0:
                    ret = (sell_price - buy_price) / buy_price
                    returns_by_offset[offset].append(ret)
                    valid_year = True
                    
            if valid_year:
                analyzed_years_count += 1
                
        if analyzed_years_count == 0:
            continue
            
        # 勝率と平均リターンの算出
        stats = {'ticker_symbol': ticker, 'analyzed_years': analyzed_years_count}
        
        best_offset = 1
        best_score = -float('inf')
        
        for offset in range(1, 7):
            rets = returns_by_offset[offset]
            if rets:
                win_rate = sum(1 for r in rets if r > 0) / len(rets)
                avg_return = np.mean(rets)
            else:
                win_rate = 0.0
                avg_return = 0.0
                
            stats[f'win_rate_{offset}m'] = float(win_rate)
            stats[f'avg_return_{offset}m'] = float(avg_return)
            
            # ベストタイミングの判定（ここでは「勝率 * 平均リターン」のスコアで簡易判定、または単に平均リターン）
            score = avg_return
            if score > best_score:
                best_score = score
                best_offset = offset
                
        stats['best_buy_offset'] = best_offset
        results.append(stats)
        
        processed_count += 1
        if processed_count % 100 == 0:
            print(f"  ... {processed_count} 件完了")
            
    print(f"\n分析完了。結果を保存します: {len(results)} 件")
    
    if not results:
        return
        
    # 重複排除（同じticker_symbolが複数ある場合、最初のものを優先または上書き）
    unique_results = {}
    for r in results:
        unique_results[r['ticker_symbol']] = r
        
    final_results = list(unique_results.values())
    
    # Supabaseに一括アップロード
    chunk_size = 500
    total_saved = 0
    for i in range(0, len(final_results), chunk_size):
        chunk = final_results[i:i + chunk_size]
        try:
            supabase.table("anomaly_analysis_results").upsert(chunk).execute()
            total_saved += len(chunk)
            print(f"  > {total_saved}/{len(final_results)} 件を保存...")
        except Exception as e:
            print(f"  x 保存エラー (chunk {i}): {e}")
            
    print("\nすべての処理が完了しました！")

if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    analyze_anomalies()
