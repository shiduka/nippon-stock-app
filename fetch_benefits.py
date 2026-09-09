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
    query = supabase.table("companies").select("ticker_symbol").eq("status", "ACTIVE")
    if limit:
        query = query.limit(limit)
    res = query.execute()
    return [row["ticker_symbol"] for row in res.data]

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
    
    all_benefits = []
    found_count = 0
    
    for i, ticker in enumerate(target_tickers):
        benefits = fetch_benefit_from_yahoo(ticker)
        
        if benefits:
            all_benefits.extend(benefits)
            found_count += 1
            print(f"  🎁 {ticker}: 優待あり ({len(benefits)}件) - {benefits[0]['benefit_summary'][:40]}")
        
        # 進捗表示
        if (i + 1) % 100 == 0:
            print(f"  ... {i + 1} / {len(target_tickers)} 銘柄を処理済み (優待あり: {found_count}社)")
        
        # サーバー負荷軽減
        time.sleep(0.8)
    
    print(f"\n取得完了！ 優待実施企業: {found_count}社 / 優待データ合計: {len(all_benefits)}件")
    
    if all_benefits:
        print("Supabaseへの保存を開始します...")
        
        # 既存データを一旦削除して全件入れ直す（最新の状態に完全同期）
        try:
            supabase.table("shareholder_benefits").delete().neq("benefit_id", 0).execute()
            print("  既存データをクリアしました。")
        except Exception as e:
            print(f"  既存データのクリアに失敗: {e}")
        
        # 50件ずつバッチでインサート
        batch_size = 50
        for j in range(0, len(all_benefits), batch_size):
            batch = all_benefits[j:j+batch_size]
            try:
                supabase.table("shareholder_benefits").insert(batch).execute()
            except Exception as e:
                print(f"  保存エラー (batch {j}): {e}")
        
        print(f"✅ 全 {len(all_benefits)} 件の優待データを保存しました！")
    else:
        print("優待データが取得できませんでした。")
