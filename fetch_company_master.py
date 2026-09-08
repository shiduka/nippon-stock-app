import os
import requests
from bs4 import BeautifulSoup
import pandas as pd
from urllib.parse import urljoin
from dotenv import load_dotenv
from supabase import create_client, Client
import time

def init_supabase() -> Client:
    """環境変数からURLとキーを読み込み、Supabaseクライアントを初期化する"""
    load_dotenv()
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise ValueError(".envファイルにSUPABASE_URLまたはSUPABASE_KEYが設定されていません")
    return create_client(url, key)

def fetch_company_master():
    """JPXから全上場銘柄を取得し、DB用フォーマットに整形する"""
    base_url = "https://www.jpx.co.jp"
    page_url = f"{base_url}/markets/statistics-equities/misc/01.html"
    
    print(f"JPXのページにアクセスしています: {page_url}")
    response = requests.get(page_url)
    response.raise_for_status()
    
    soup = BeautifulSoup(response.content, 'html.parser')
    excel_link = None
    
    for a_tag in soup.find_all('a', href=True):
        if a_tag['href'].endswith('.xls') or a_tag['href'].endswith('.xlsx'):
            excel_link = a_tag['href']
            break
            
    if not excel_link:
        raise ValueError("最新の銘柄一覧Excelファイルが見つかりませんでした。")
        
    full_excel_url = urljoin(base_url, excel_link)
    print(f"Excelファイルをダウンロード・解析中: {full_excel_url}")
    
    df = pd.read_excel(full_excel_url)
    results = []
    
    for index, row in df.iterrows():
        ticker = str(row.get('コード', '')).strip()
        market = str(row.get('市場・商品区分', '')).strip()
        sector = str(row.get('33業種区分', '')).strip()
        
        if not ticker:
            continue
            
        # ETF、REIT、インフラファンド等を除外
        if sector == '-':
            continue
            
        record = {
            'ticker_symbol': ticker,
            'company_name': str(row.get('銘柄名', '')).strip(),
            'market': market,
            'sector_33': sector,
            'status': 'ACTIVE',
            # まだ取得していないデータは一旦 None にしておく
            'delisted_date': None,
            'fiscal_month': None,
            'next_earnings_date': None,
            'dividend_yield': None
        }
        results.append(record)
        
    return results

def save_to_supabase(data):
    """取得したリストをSupabaseに保存する"""
    supabase = init_supabase()
    total_count = len(data)
    print(f"\nSupabaseへの保存を開始します (合計 {total_count} 件)")
    
    # サーバーへの負荷(一度に送信できる容量)を考慮し、1000件ずつに分けて送信する
    chunk_size = 1000
    success_count = 0
    
    for i in range(0, total_count, chunk_size):
        chunk = data[i:i + chunk_size]
        try:
            # upsert: 既に同じ銘柄コードがあれば上書き、無ければ新規追加する最強のコマンド
            supabase.table('companies').upsert(chunk).execute()
            success_count += len(chunk)
            print(f"  [{success_count} / {total_count}] 件 保存完了...")
            time.sleep(0.5) # サーバーに少し休憩を入れる
        except Exception as e:
            print(f"保存中にエラーが発生しました (chunk {i}~): {e}")
            
    print(f"\n✅ すべての保存処理が完了しました！ ({success_count}/{total_count} 件成功)")

if __name__ == "__main__":
    print("=== 企業マスター取得・DB保存バッチ ===")
    companies_data = fetch_company_master()
    
    if companies_data:
        print(f"Webからの取得成功！ 有効な企業数: {len(companies_data)} 社")
        save_to_supabase(companies_data)
    else:
        print("データが取得できませんでした。")
