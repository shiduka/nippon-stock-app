import pandas as pd
import numpy as np
import datetime
from supabase import create_client
import os
from dotenv import load_dotenv
import time

def main():
    load_dotenv()
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    supabase = create_client(url, key)

    print("1. 株価履歴データの読み込み中...")
    parquet_path = "data/historical_prices_10y.parquet"
    if not os.path.exists(parquet_path):
        print(f"Error: {parquet_path} が見つかりません。")
        return
    
    df_prices = pd.read_parquet(parquet_path)
    # trade_dateをdatetime型に変換
    df_prices['trade_date'] = pd.to_datetime(df_prices['trade_date'])
    df_prices = df_prices.sort_values(['ticker_symbol', 'trade_date'])
    print(f"読み込み完了: {len(df_prices)} 行")

    print("2. 企業の次回決算日を取得中...")
    companies_data = []
    start = 0
    while True:
        res = supabase.table("companies").select("ticker_symbol, next_earnings_date").not_.is_("next_earnings_date", "null").range(start, start + 999).execute()
        if not res.data:
            break
        companies_data.extend(res.data)
        start += 1000
    
    # 辞書化 {ticker: next_earnings_month}
    target_months = {}
    for c in companies_data:
        try:
            date_obj = datetime.datetime.strptime(c['next_earnings_date'], "%Y-%m-%d")
            target_months[c['ticker_symbol']] = date_obj.month
        except:
            continue
            
    print(f"決算予定が登録されている企業: {len(target_months)} 件")

    print("3. 決算アノマリーの分析を開始します...")
    
    # ターゲット月の前月末を売却日とするため、月をシフトする関数
    def get_prev_month(year, month, offset=0):
        # offset=0 は前月。offset=1 は2ヶ月前...
        m = month - 1 - offset
        y = year
        while m <= 0:
            m += 12
            y -= 1
        return y, m

    results = []
    tickers = df_prices['ticker_symbol'].unique()
    
    count = 0
    for ticker in tickers:
        count += 1
        if count % 100 == 0:
            print(f"  ... {count}/{len(tickers)} 銘柄分析完了")
            
        if ticker not in target_months:
            continue
            
        t_month = target_months[ticker]
        df_t = df_prices[df_prices['ticker_symbol'] == ticker].copy()
        df_t.set_index('trade_date', inplace=True)
        
        # 月末のデータを抽出 (各年月の最後の営業日)
        df_monthend = df_t.resample('ME').last().dropna(subset=['close_price'])
        
        # 過去10年間の各年についてシミュレーション
        years_data = df_monthend.index.year.unique()
        if len(years_data) < 3: # 最低3年のデータがなければスキップ
            continue
            
        returns_1m = []
        returns_2m = []
        returns_3m = []
        
        for y in years_data:
            # 売却日: ターゲット月の「前月」の月末
            sell_y, sell_m = get_prev_month(y, t_month, 0)
            
            # 買付日: ターゲット月の前月の 1ヶ月前(計2ヶ月前), 2ヶ月前(計3ヶ月前), 3ヶ月前(計4ヶ月前)
            # ※「決算発表の1ヶ月前〜3ヶ月前に買う」という定義
            buy1_y, buy1_m = get_prev_month(y, t_month, 1) # 発表月の2ヶ月前月末 = 発表1ヶ月前の月初付近
            buy2_y, buy2_m = get_prev_month(y, t_month, 2)
            buy3_y, buy3_m = get_prev_month(y, t_month, 3)
            
            # 価格の取得
            sell_price = None
            buy1_price = None
            buy2_price = None
            buy3_price = None
            
            for date, row in df_monthend.iterrows():
                if date.year == sell_y and date.month == sell_m:
                    sell_price = row['close_price']
                elif date.year == buy1_y and date.month == buy1_m:
                    buy1_price = row['close_price']
                elif date.year == buy2_y and date.month == buy2_m:
                    buy2_price = row['close_price']
                elif date.year == buy3_y and date.month == buy3_m:
                    buy3_price = row['close_price']
                    
            if sell_price:
                if buy1_price: returns_1m.append((sell_price - buy1_price) / buy1_price)
                if buy2_price: returns_2m.append((sell_price - buy2_price) / buy2_price)
                if buy3_price: returns_3m.append((sell_price - buy3_price) / buy3_price)
                
        # 勝率と平均リターンの計算
        def calc_stats(ret_list):
            if not ret_list: return None, None
            win_rate = len([r for r in ret_list if r > 0]) / len(ret_list)
            avg_return = np.mean(ret_list)
            return win_rate, avg_return
            
        w1, a1 = calc_stats(returns_1m)
        w2, a2 = calc_stats(returns_2m)
        w3, a3 = calc_stats(returns_3m)
        
        # すべてデータがない場合はスキップ
        if w1 is None and w2 is None and w3 is None:
            continue
            
        # ベストな仕込みタイミングを決定 (平均リターンが最も高いもの)
        best_offset = None
        best_ret = -999
        if a1 is not None and a1 > best_ret: best_ret = a1; best_offset = 1
        if a2 is not None and a2 > best_ret: best_ret = a2; best_offset = 2
        if a3 is not None and a3 > best_ret: best_ret = a3; best_offset = 3
        
        results.append({
            'ticker_symbol': ticker,
            'target_month': t_month,
            'best_buy_offset': best_offset,
            'analyzed_years': len(years_data),
            'win_rate_1m': w1, 'avg_return_1m': a1,
            'win_rate_2m': w2, 'avg_return_2m': a2,
            'win_rate_3m': w3, 'avg_return_3m': a3,
        })
        
    print(f"分析完了！ 対象銘柄: {len(results)} 件")
    
    print("4. Supabaseへの保存を開始します...")
    # 辞書を使って重複を排除（UPSERTエラー防止）
    unique_results = {r['ticker_symbol']: r for r in results}.values()
    
    upsert_data = []
    for r in unique_results:
        # None のものはキーから外す (Supabase制約回避)
        clean_r = {k: v for k, v in r.items() if v is not None}
        clean_r['updated_at'] = datetime.datetime.now().isoformat()
        upsert_data.append(clean_r)
        
    # 1000件ずつUPSERT
    for i in range(0, len(upsert_data), 1000):
        batch = upsert_data[i:i+1000]
        try:
            supabase.table("earnings_anomaly_results").upsert(batch).execute()
            print(f"  - {i+1}〜{i+len(batch)} 件目を保存完了")
        except Exception as e:
            print(f"Error saving batch: {e}")
            
    print("すべての処理が完了しました！")

if __name__ == "__main__":
    main()
