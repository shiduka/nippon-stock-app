"""
dividendYield が 1% 未満(0.17% など)の銘柄が誤って×100されて保存された可能性があるため、
「dividend_yield >= 10」の銘柄を見つけて正しい値に修正する緊急パッチスクリプト。
"""
import os
import sys
import yfinance as yf
import time
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()
supabase = create_client(os.environ.get('SUPABASE_URL'), os.environ.get('SUPABASE_KEY'))

sys.stdout.reconfigure(line_buffering=True)
print("=== 配当利回りの誤変換銘柄を修正します ===")

# dividend_yield >= 10 の銘柄を全件取得（異常値の可能性が高い）
# 実際の株式で10%を超える配当は非常に稀なため
suspicious = []
start = 0
while True:
    res = supabase.table("companies").select("ticker_symbol, dividend_yield").gte("dividend_yield", 10).range(start, start + 999).execute()
    if not res.data:
        break
    suspicious.extend(res.data)
    start += 1000

print(f"dividend_yield >= 10 の銘柄数: {len(suspicious)} 件")

fixed_count = 0
for row in suspicious:
    ticker = row['ticker_symbol']
    stored = row['dividend_yield']
    
    try:
        info = yf.Ticker(f"{ticker}.T").info
        real_yield = info.get('dividendYield')
        
        if real_yield is not None and real_yield > 0:
            correct = round(float(real_yield), 2)
            supabase.table("companies").update({"dividend_yield": correct}).eq("ticker_symbol", ticker).execute()
            print(f"  修正: {ticker} {stored} -> {correct}%")
            fixed_count += 1
        else:
            # 無配として0に修正
            supabase.table("companies").update({"dividend_yield": 0.0}).eq("ticker_symbol", ticker).execute()
            print(f"  無配に修正: {ticker} {stored} -> 0.0%")
            fixed_count += 1
            
        time.sleep(0.3)
    except Exception as e:
        print(f"  x エラー: {ticker}: {e}")

print(f"\n完了: {fixed_count} 件を修正しました")
