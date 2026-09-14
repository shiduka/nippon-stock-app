import requests
import re
import time
import random
import sys
from supabase import create_client, Client
import os
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

def fetch_benefit_from_yahoo(ticker, headers):
    url = f"https://finance.yahoo.co.jp/quote/{ticker}.T/incentive"
    
    res = requests.get(url, headers=headers, timeout=15)
    res.raise_for_status()
    html = res.text
    
    if '権利付き最終日' not in html:
        return None
        
    date_matches = re.findall(r'権利付き最終日</th><td[^>]*>([^<]+)</td>', html)
    months = set()
    if date_matches:
        months = set(int(m) for m in re.findall(r'(\d{1,2})月', date_matches[0]))
    
    type_match = re.search(r'優待の種類</th><td[^>]*>([^<]+)</td>', html)
    benefit_type = type_match.group(1).strip() if type_match else ""
    
    detail_titles = re.findall(r'IncentiveDetail__detailBox.*?_BasicHeader__heading[^>]*>([^<]+)<', html)
    detail_summary = " / ".join(detail_titles) if detail_titles else benefit_type
    
    min_shares_match = re.search(r'単元株数</th><td[^>]*>(\d+)株</td>', html)
    min_shares = int(min_shares_match.group(1)) if min_shares_match else 100
    
    results = []
    for month in months:
        results.append({
            'ticker_symbol': ticker,
            'record_month': month,
            'min_shares': min_shares,
            'benefit_summary': detail_summary[:500],
            'is_active': True
        })
    
    return results if results else None

if __name__ == "__main__":
    # printのバッファリングを強制解除するための設定（-uがなくてもリアルタイム出力されるようにする）
    sys.stdout.reconfigure(line_buffering=True)
    
    print("株主優待データの全件取得を開始します (Yahoo!ファイナンス経由 - 極低速安定版)...")
    supabase = get_supabase_client()
    
    target_tickers = get_active_tickers(supabase, limit=None)
    print(f"取得対象: {len(target_tickers)} 銘柄\n")
    
    all_benefits = []
    found_count = 0
    skip_count = 0
    error_count = 0
    total = len(target_tickers)
    
    # 完全に人間と同じように見せるためのヘッダー
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'ja,en-US;q=0.7,en;q=0.3',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }
    
    consecutive_errors = 0
    
    for i, ticker in enumerate(target_tickers):
        benefits = None
        is_error = False
        
        try:
            benefits = fetch_benefit_from_yahoo(ticker, headers)
            consecutive_errors = 0 # 正常に200OKが返ればリセット
            
        except requests.exceptions.HTTPError as e:
            is_error = True
            error_count += 1
            consecutive_errors += 1
            
            if '404' in str(e):
                print(f"  [404] {ticker}: ページが存在しません。")
            else:
                print(f"  [HTTPエラー] {ticker}: {e}")
                
        except Exception as e:
            is_error = True
            error_count += 1
            consecutive_errors += 1
            print(f"  [エラー] {ticker}: {e}")
        
        # エラーなし（200 OK）だった場合のみ結果を判定
        if not is_error:
            if benefits:
                all_benefits.extend(benefits)
                found_count += 1
                print(f"  [OK] {ticker}: 優待あり ({len(benefits)}件) - {benefits[0]['benefit_summary'][:30]}...")
            else:
                skip_count += 1
                # print(f"  [-] {ticker}: 優待なし") # ログが埋まるので通常は非表示
        
        # もし3回連続でエラー(500や403など)になったら、ブロックされているので3分間休む
        if consecutive_errors >= 3:
            print(f"  🚨 [厳重ブロック検知] 3回連続でアクセスエラー。サーバーを休ませるため3分間待機します...")
            time.sleep(180)
            consecutive_errors = 0
            
        # 進捗表示
        if (i + 1) % 50 == 0:
            print(f"\n  --- 進捗: {i + 1}/{total} | 優待: {found_count} | なし: {skip_count} | エラー: {error_count} ---\n")
            # 50件ごとに15〜20秒の長めの休憩
            pause = random.uniform(15, 20)
            print(f"  [休憩] {pause:.1f} 秒待機...")
            time.sleep(pause)
        else:
            time.sleep(random.uniform(2.0, 3.5))
            
    print(f"\n取得完了！ 優待実施企業: {found_count}社 / 優待データ合計: {len(all_benefits)}件")
    
    if all_benefits:
        print("Supabaseへの保存を開始します...")
        try:
            supabase.table("shareholder_benefits").delete().neq("benefit_id", 0).execute()
            print("  既存データをクリアしました。")
        except Exception as e:
            print(f"  既存データのクリアに失敗: {e}")
        
        batch_size = 1000
        for j in range(0, len(all_benefits), batch_size):
            batch = all_benefits[j:j+batch_size]
            try:
                supabase.table("shareholder_benefits").insert(batch).execute()
                print(f"  [保存] {min(j+batch_size, len(all_benefits))}/{len(all_benefits)} 件を保存完了。")
            except Exception as e:
                print(f"  保存エラー: {e}")
        
        print(f"全 {len(all_benefits)} 件の優待データを保存しました！")
    else:
        print("保存するデータがありませんでした。")
