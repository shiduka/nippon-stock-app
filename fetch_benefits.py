import requests
import re
import time
from bs4 import BeautifulSoup
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

def fetch_tokuyutai_by_month(month: int):
    """ゆうかぶ (tokuyutai.com) から指定月の優待銘柄一覧を取得する"""
    url = f"https://tokuyutai.com/data/vesting-{month}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
    }
    
    results = []
    
    try:
        res = requests.get(url, headers=headers, timeout=15)
        res.raise_for_status()
        res.encoding = res.apparent_encoding # 文字化け対策
        
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # yutai_box クラスの中に1銘柄分のデータが入っている
        boxes = soup.find_all('div', class_='yutai_box')
        
        for box in boxes:
            # 銘柄名とコード (例: "丸千代山岡家（3399）")
            title_elem = box.find('div', class_='yutai_tl')
            if not title_elem:
                continue
                
            title_text = title_elem.text.strip()
            # 正規表現で4桁の数字（銘柄コード）を抽出
            code_match = re.search(r'（(\d{4})）', title_text)
            if not code_match:
                continue
                
            ticker = code_match.group(1)
            
            # 優待のサマリー内容
            summary_elem = box.find('div', class_='yutai_title')
            summary = summary_elem.text.strip() if summary_elem else "株主優待"
            
            # 株数や権利月の詳細テキスト
            stock_info = box.find('div', class_='yutai_stock')
            stock_text = stock_info.text.replace('\n', ' ') if stock_info else ""
            
            results.append({
                'ticker_symbol': ticker,
                'record_month': month,
                'min_shares': 100, # ゆうかぶの一覧画面には株数が明記されないことが多いので、ひとまず100とする
                'benefit_summary': summary,
                'is_active': True
            })
            
    except Exception as e:
        print(f"  ❌ {month}月の取得エラー: {e}")
        
    return results

if __name__ == "__main__":
    print("株主優待データの取得を開始します (ゆうかぶ経由)...")
    supabase = get_supabase_client()
    
    all_benefits = []
    
    # 1月〜12月までの全ページを順番にアクセス
    for month in range(1, 13):
        print(f"\n▶ {month}月の優待データを取得中...")
        benefits = fetch_tokuyutai_by_month(month)
        
        if benefits:
            all_benefits.extend(benefits)
            print(f"  ✅ {month}月: {len(benefits)}件の優待を発見")
            # 最初の1件だけサンプルとして表示
            if benefits:
                print(f"      (例: {benefits[0]['ticker_symbol']} - {benefits[0]['benefit_summary']})")
        else:
            print(f"  ⚠️ {month}月: 優待データが見つかりませんでした")
            
        # サーバー負荷軽減のためページ移動ごとに少し待つ
        time.sleep(2)
        
    print(f"\n取得完了！ 優待実施企業: 合計 {len(all_benefits)}件")
    
    # データベースの存在チェック用（Activeな銘柄コード一覧）
    print("データベースと照合中...")
    active_res = supabase.table("companies").select("ticker_symbol").execute()
    active_tickers = set(row['ticker_symbol'] for row in active_res.data)
    
    # DBに存在する銘柄のみにフィルタリング
    valid_benefits = [b for b in all_benefits if b['ticker_symbol'] in active_tickers]
    print(f"有効な優待データ（DB登録対象）: {len(valid_benefits)}件")
    
    if valid_benefits:
        print("\nSupabaseへの保存を開始します...")
        try:
            supabase.table("shareholder_benefits").delete().neq("benefit_id", 0).execute()
            print("  既存データをクリアしました。")
        except Exception as e:
            print(f"  既存データのクリアに失敗: {e}")
        
        # 1000件ずつインサート
        batch_size = 1000
        for j in range(0, len(valid_benefits), batch_size):
            batch = valid_benefits[j:j+batch_size]
            try:
                supabase.table("shareholder_benefits").insert(batch).execute()
                print(f"  💾 {min(j+batch_size, len(valid_benefits))}/{len(valid_benefits)} 件を保存...")
            except Exception as e:
                print(f"  保存エラー: {e}")
        
        print(f"✅ 全 {len(valid_benefits)} 件の優待データを保存しました！")
    else:
        print("保存するデータがありません。")
