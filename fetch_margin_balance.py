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
    Yahoo!ファイナンスの各銘柄ページ（信用取引タブ）から信用残高データをスクレイピングする。
    """
    results = []
    report_date = get_last_friday()
    
    # スクレイピング対策を回避するためのヘッダー
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    for ticker in ticker_list:
        # Yahooファイナンスの信用取引専用ページ URL
        url = f"https://finance.yahoo.co.jp/quote/{ticker}.T/margin"
        print(f"取得中: {ticker} ({url})")
        
        try:
            res = requests.get(url, headers=headers, timeout=10)
            res.raise_for_status()
            html = res.text
            
            # HTML内から「信用買残」「信用売残」「信用倍率」の付近にある数値を正規表現で抽出
            # ※WebサイトのUIが変更されると抽出ルールを直す必要があります
            buy_match = re.search(r'信用買残.*?<span[^>]*>([\d,\.]+)</span>', html)
            sell_match = re.search(r'信用売残.*?<span[^>]*>([\d,\.]+)</span>', html)
            ratio_match = re.search(r'信用倍率.*?<span[^>]*>([\d,\.]+)</span>', html)
            
            # 数値への変換（カンマを取り除く）
            buy_vol = int(buy_match.group(1).replace(',', '')) if buy_match else 0
            sell_vol = int(sell_match.group(1).replace(',', '')) if sell_match else 0
            
            margin_ratio = None
            if ratio_match:
                margin_ratio = float(ratio_match.group(1).replace(',', ''))
            elif sell_vol > 0:
                # 倍率が見つからない場合は自分で計算する
                margin_ratio = round(buy_vol / sell_vol, 2)
                
            record = {
                'ticker_symbol': ticker,
                'report_date': report_date.isoformat(),
                'margin_buy_volume': buy_vol,
                'margin_sell_volume': sell_vol,
                'margin_ratio': margin_ratio
            }
            results.append(record)
            
        except Exception as e:
            print(f"[{ticker}] 取得エラー: {e}")
            
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
    query = supabase.table("companies").select("ticker_symbol").eq("status", "ACTIVE")
    if limit:
        query = query.limit(limit)
    res = query.execute()
    return [row["ticker_symbol"] for row in res.data]

if __name__ == "__main__":
    print("信用取引残高の取得を開始します (Yahoo!ファイナンス経由)...")
    supabase = get_supabase_client()
    
    # テストのため今回は上位30銘柄だけを取得
    target_tickers = get_active_tickers(supabase, limit=30)
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
