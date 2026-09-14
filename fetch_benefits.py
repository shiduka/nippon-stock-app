import os
import re
import time
import requests
from supabase import create_client, Client
from dotenv import load_dotenv

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

def fetch_benefit_from_yahoo(ticker):
    """
    Yahoo!ファイナンスの株主優待ページから優待情報をスクレイピングする。
    優待がない企業はNoneを返す。
    """
    url = f"https://finance.yahoo.co.jp/quote/{ticker}.T/incentive"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()
        html = res.text
        
        # 「権利付き最終日」が含まれていなければ優待なし
        if '権利付き最終日' not in html:
            return None
        
        # 権利確定月を取得（「2027年2月24日」のような日付から月を抽出）
        date_matches = re.findall(r'権利付き最終日</th><td[^>]*>([^<]+)</td>', html)
        months = set()
        if date_matches:
            month_nums = re.findall(r'(\d{1,2})月', date_matches[0])
            months = set(int(m) for m in month_nums)
        
        # 優待内容の要約を取得（優待の種類）
        type_match = re.search(r'優待の種類</th><td[^>]*>([^<]+)</td>', html)
        benefit_type = type_match.group(1).strip() if type_match else ""
        
        # 詳細な優待内容のタイトルを取得
        detail_titles = re.findall(r'IncentiveDetail__detailBox.*?_BasicHeader__heading[^>]*>([^<]+)<', html)
        detail_summary = " / ".join(detail_titles) if detail_titles else benefit_type
        
        # 最低必要株数（「100株」のような表記から取得）
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
        
    except Exception as e:
        return None

if __name__ == "__main__":
    print("株主優待データの全件取得を開始します (Yahoo!ファイナンス経由)...")
    supabase = get_supabase_client()
    
    target_tickers = get_active_tickers(supabase, limit=None)
    print(f"取得対象: {len(target_tickers)} 銘柄\n")
    
    import random
    all_benefits = []
    found_count = 0
    skip_count = 0
    error_count = 0
    total = len(target_tickers)
    
    for i, ticker in enumerate(target_tickers):
        # 1銘柄取得（例外処理付き）
        url = f"https://finance.yahoo.co.jp/quote/{ticker}.T/incentive"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'ja,en-US;q=0.7,en;q=0.3',
        }
        
        benefits = None
        try:
            res = requests.get(url, headers=headers, timeout=15)
            res.raise_for_status()
            html = res.text
            
            if '権利付き最終日' in html:
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
                
                if months:
                    benefits = []
                    for month in months:
                        benefits.append({
                            'ticker_symbol': ticker,
                            'record_month': month,
                            'min_shares': min_shares,
                            'benefit_summary': detail_summary[:500],
                            'is_active': True
                        })
            else:
                # 優待なし
                pass
                
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if hasattr(e, 'response') and e.response else 0
            err_str = str(e)
            if '404' in err_str:
                skip_count += 1
            elif '500' in err_str:
                print(f"  ⚠️ [{ticker}] 500エラー（レート制限の可能性）。15秒待機してスキップします...")
                time.sleep(15)
                error_count += 1
            else:
                error_count += 1
        except Exception as e:
            error_count += 1
            
        if benefits:
            all_benefits.extend(benefits)
            found_count += 1
            print(f"  🎁 {ticker}: 優待あり ({len(benefits)}件) - {benefits[0]['benefit_summary'][:40]}")
        else:
            skip_count += 1
            
        # 進捗表示
        if (i + 1) % 50 == 0:
            print(f"\n  === 進捗: {i + 1}/{total} 処理済み | 🎁 優待あり: {found_count} | ⏭️ なし/スキップ: {skip_count} | ❌ エラー: {error_count} ===\n")
            pause = random.uniform(10, 15)
            print(f"  💤 ブロック回避のため {pause:.1f} 秒休憩します...")
            time.sleep(pause)
        else:
            time.sleep(random.uniform(1.5, 3.0))
            
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
                print(f"  💾 {min(j+batch_size, len(all_benefits))}/{len(all_benefits)} 件を保存...")
            except Exception as e:
                print(f"  保存エラー: {e}")
        
        print(f"✅ 全 {len(all_benefits)} 件の優待データを保存しました！")
    else:
        print("優待データが取得できませんでした。")
