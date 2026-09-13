import requests
import re
import pandas as pd
import time
from datetime import datetime, timedelta

def get_last_friday():
    """実行日の直近の金曜日（信用残高の基準日）を計算する"""
    today = datetime.now().date()
    offset = (today.weekday() - 4) % 7
    last_friday = today - timedelta(days=offset)
    return last_friday

def fetch_margin_balance_yahoo(ticker_list):
    """
    Yahoo!ファイナンスの各銘柄ページ（信用残時系列）から信用残高データをスクレイピングする。
    テーブルの列構造: [売残, 買残, 売残増減, 買残増減, 倍率]
    """
    results = []
    report_date = get_last_friday()
    
    # スクレイピング対策を回避するためのヘッダー
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    for ticker in ticker_list:
        # Yahooファイナンスの信用残時系列ページ URL
        url = f"https://finance.yahoo.co.jp/quote/{ticker}.T/margin"
        
        try:
            res = requests.get(url, headers=headers, timeout=10)
            res.raise_for_status()
            html = res.text
            
            # テーブル行(tr)の中からデータセル(td)の数値を取得する
            # _StyledNumber__value クラスの span タグに数値が入っている
            rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)
            
            # 最新の1行目だけを取得（テーブルの最初のデータ行）
            for row in rows:
                values = re.findall(r'_StyledNumber__value[^>]*>([^<]+)<', row)
                if len(values) >= 5:
                    # [売残, 買残, 売残増減, 買残増減, 倍率]
                    sell_vol_str = values[0].replace(',', '')
                    buy_vol_str = values[1].replace(',', '')
                    ratio_str = values[4].replace(',', '')
                    
                    sell_vol = int(sell_vol_str)
                    buy_vol = int(buy_vol_str)
                    # 倍率が「---」の場合はNoneにする（売残0の銘柄など）
                    try:
                        margin_ratio = float(ratio_str)
                    except ValueError:
                        margin_ratio = None
                    
                    record = {
                        'ticker_symbol': ticker,
                        'report_date': report_date.isoformat(),
                        'margin_buy_volume': buy_vol,
                        'margin_sell_volume': sell_vol,
                        'margin_ratio': margin_ratio
                    }
                    results.append(record)
                    print(f"  ✅ {ticker}: 売残={sell_vol:,} 買残={buy_vol:,} 倍率={margin_ratio}")
                    break  # 最新の1行だけ取得したらループを抜ける
            else:
                print(f"  ⚠️ {ticker}: 信用残データが見つかりませんでした（非信用銘柄の可能性）")
                
        except Exception as e:
            print(f"  ❌ [{ticker}] 取得エラー: {e}")
            
        # サーバーへの負荷を下げるために1秒待つ（スクレイピングのマナー）
        time.sleep(1)
        
    return results

import os
from supabase import create_client, Client
from dotenv import load_dotenv

def get_supabase_client() -> Client:
    load_dotenv()
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise ValueError("SUPABASE_URL or SUPABASE_KEY is missing in .env")
    return create_client(url, key)

def get_active_tickers(supabase: Client, limit: int = None):
    tickers = []
    page_size = 1000
    start = 0
    
    while True:
        query = supabase.table("companies").select("ticker_symbol").eq("status", "ACTIVE")
        
        # ページネーションの範囲を指定
        query = query.range(start, start + page_size - 1)
        res = query.execute()
        
        if not res.data:
            break
            
        tickers.extend([row["ticker_symbol"] for row in res.data])
        
        # limitが指定されていれば、その数に達したら終了
        if limit and len(tickers) >= limit:
            tickers = tickers[:limit]
            break
            
        # 取得件数がpage_size未満なら全件取得完了
        if len(res.data) < page_size:
            break
            
        start += page_size
        
    return tickers

if __name__ == "__main__":
    print("信用取引残高の取得を開始します (Yahoo!ファイナンス経由)...")
    supabase = get_supabase_client()
    
    # 全銘柄を対象に信用残高を取得する
    target_tickers = get_active_tickers(supabase, limit=None)
    print(f"取得対象: {len(target_tickers)} 銘柄")
    
    data = fetch_margin_balance_yahoo(target_tickers)
    
    if data:
        print("\nSupabaseへの保存を開始します...")
        try:
            supabase.table("margin_balances").upsert(data).execute()
            print(f"✅ 全 {len(data)} 件の信用残高データを保存しました！")
        except Exception as e:
            print(f"保存エラー: {e}")
    else:
        print("データが取得できませんでした。")
