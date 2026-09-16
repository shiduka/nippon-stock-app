import requests
import re
import time
import random
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

def fetch_all_pages_from_url(base_url, session):
    """
    指定された利回り別URLから、1ページ目〜最終ページまでの全銘柄を取得する
    """
    results = []
    
    # 1. 最初のページをGETして、CSRFトークンとフォーム初期値を取得
    print(f"  [GET] {base_url}")
    try:
        res = session.get(base_url, timeout=15)
        res.raise_for_status()
        res.encoding = res.apparent_encoding
        soup = BeautifulSoup(res.text, 'html.parser')
    except Exception as e:
        print(f"    エラー: 初期ページの取得に失敗: {e}")
        return results
        
    # CSRFトークン
    csrf_meta = soup.find('meta', attrs={'name': 'csrf-token'})
    if not csrf_meta:
        print("    エラー: CSRFトークンが見つかりません")
        return results
    csrf_token = csrf_meta['content']
    
    # Hidden Formの初期値
    form_data = {}
    form = soup.find('form', id='form_hid')
    if form:
        for inp in form.find_all('input', type='hidden'):
            form_data[inp.get('name', '')] = inp.get('value', '')
            
    # 初期ロード時のHTMLには件数が表示されていないため、ここでは件数チェックを行いません。
    # 代わりに、Ajaxリクエストでデータが空になるか、重複銘柄が出るまで進めます。


    # Ajax用のベースヘッダー
    ajax_base_url = "https://tokuyutai.com/ajax/meigara/search/list"
    ajax_headers = {
        'X-CSRF-TOKEN': csrf_token,
        'X-Requested-With': 'XMLHttpRequest',
        'Referer': base_url,
    }
    
    # 2. 1ページ目から順番にPOSTリクエストを送ってデータを取得
    page = 1
    seen_tickers = set() # 無限ループ防止用
    
    while True:
        # Laravel等のページネーション仕様のため、POSTデータではなくURLパラメータでページ番号を渡す
        ajax_url = f"{ajax_base_url}?page={page}"
        form_data['hdn_page'] = str(page)
        
        try:
            # サーバー負荷軽減
            time.sleep(1.0)
            
            ajax_res = session.post(ajax_url, data=form_data, headers=ajax_headers, timeout=15)
            ajax_res.raise_for_status()
            data = ajax_res.json()
            
            # JSONの中の HTML（meigaraData） をパース
            html_list = data.get('meigaraData', [])
            if not html_list:
                break
                
            page_results = []
            page_has_new_ticker = False
            
            for html_str in html_list:
                item_soup = BeautifulSoup(html_str, 'html.parser')
                
                # 銘柄名とコード (例: "エックスネット(4762)")
                title_elem = item_soup.find('div', class_='yutai_tl')
                if not title_elem:
                    continue
                    
                title_text = title_elem.text.strip()
                code_match = re.search(r'（?(\d{4})）?', title_text)
                if not code_match:
                    continue
                ticker = code_match.group(1)
                
                # 無限ループ防止（既にこのURLで取得済みの銘柄が出たら終了）
                if ticker not in seen_tickers:
                    seen_tickers.add(ticker)
                    page_has_new_ticker = True
                
                # 優待内容要約
                summary_elem = item_soup.find('div', class_='yutai_title')
                summary = summary_elem.text.strip() if summary_elem else "株主優待"
                
                # 権利確定月
                stock_elem = item_soup.find('div', class_='yutai_stock')
                stock_text = stock_elem.text if stock_elem else ""
                
                # 「権利確定日　3月末、9月末」などのテキストから月をすべて抽出
                months = set()
                month_matches = re.findall(r'(\d{1,2})月末?', stock_text)
                for m in month_matches:
                    months.add(int(m))
                    
                # 最低必要株数は一覧にはないため、デフォルト100株とする
                min_shares = 100
                
                if not months:
                    # 月が不明な場合はスキップ
                    continue
                    
                for month in months:
                    page_results.append({
                        'ticker_symbol': ticker,
                        'record_month': month,
                        'min_shares': min_shares,
                        'benefit_summary': summary[:500],
                        'is_active': True
                    })
                    
            # ページ内に新しい銘柄が1つもなければ（すべて重複なら）無限ループとみなして終了
            if not page_has_new_ticker:
                break
                
            results.extend(page_results)
            print(f"    - {page} ページ目を取得完了 ({len(page_results)}件)")
            
            page += 1
            
        except Exception as e:
            print(f"    エラー: {page}ページ目の取得に失敗: {e}")
            break
            
    return results

if __name__ == "__main__":
    print("=== 株主優待データの全件取得を開始します (ゆうかぶ経由) ===\n")
    
    supabase = get_supabase_client()
    
    # ゆうかぶは1つのURLからAjaxのページネーションを辿るだけで全件（約2300件）取得できることが判明したため、
    # 検索条件なしの基本URL1つだけを使用します。
    base_url = "https://tokuyutai.com/data/yield-over-05"
    
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
    })
    
    # 全ページを取得
    valid_benefits = []
    all_benefits = fetch_all_pages_from_url(base_url, session)
    print(f"\n総抽出件数: {len(all_benefits)}件")
    
    # 重複排除
    unique_benefits_dict = {}
    for b in all_benefits:
        key = (b['ticker_symbol'], b['record_month'])
        unique_benefits_dict[key] = b
        
    valid_benefits = list(unique_benefits_dict.values())
    print(f"重複排除後の件数: {len(valid_benefits)}件")
    
    # Supabase上の有効な企業（companies）のticker_symbol一覧を取得 (1000件制限を回避)
    print("データベースと照合中...")
    active_tickers = set()
    page_size = 1000
    start = 0
    while True:
        active_res = supabase.table("companies").select("ticker_symbol").range(start, start + page_size - 1).execute()
        if not active_res.data:
            break
        active_tickers.update(row['ticker_symbol'] for row in active_res.data)
        start += page_size
        
    valid_benefits = [b for b in valid_benefits if b['ticker_symbol'] in active_tickers]
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
                print(f"  [保存] {min(j+batch_size, len(valid_benefits))}/{len(valid_benefits)} 件を保存完了。")
            except Exception as e:
                print(f"  保存エラー: {e}")
        
        print(f"\n🎉 全 {len(valid_benefits)} 件の優待データを保存しました！")
    else:
        print("保存するデータがありませんでした。")
