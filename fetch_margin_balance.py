import requests
import re
import time
import math
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from supabase import create_client, Client
import os
import sys
from dotenv import load_dotenv

def get_last_friday():
    """日付が取得できなかった場合のフォールバック用"""
    today = datetime.now().date()
    offset = (today.weekday() - 4) % 7
    last_friday = today - timedelta(days=offset)
    return last_friday.isoformat()

def get_supabase_client() -> Client:
    load_dotenv()
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise ValueError("SUPABASE_URL or SUPABASE_KEY is missing in .env")
    return create_client(url, key)

def fetch_kabutan_margin_ranking():
    """
    株探の信用残高増減ランキング4種類からデータを取得し、計算で買い残・売り残を導出する。
    """
    results_dict = {}
    report_date_str = None
    
    modes = [
        ('7_1', '売り残増加'),
        ('7_2', '買い残増加'),
        ('7_3', '売り残減少'),
        ('7_4', '買い残減少')
    ]
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'ja,en-US;q=0.7,en;q=0.3',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
    }
    
    for mode, mode_name in modes:
        print(f"\n▶ [{mode_name}] ランキングの取得を開始します...")
        page = 1
        
        while True:
            url = f"https://kabutan.jp/warning/?mode={mode}&page={page}"
            
            try:
                time.sleep(1.5) # サーバー負荷軽減
                res = requests.get(url, headers=headers, timeout=15)
                res.raise_for_status()
                res.encoding = res.apparent_encoding
                soup = BeautifulSoup(res.text, 'html.parser')
                
                # 最初に見つかったページから基準日を抽出
                if not report_date_str:
                    date_match = re.search(r'信用残：\s*(\d{4})年(\d{2})月(\d{2})日', soup.text)
                    if date_match:
                        y, m, d = date_match.groups()
                        report_date_str = f"{y}-{m}-{d}"
                        print(f"  📅 基準日を検出: {report_date_str}")
                
                table = soup.find('table', class_='stock_table')
                if not table:
                    print(f"  ⚠ テーブルが見つかりませんでした。({page}ページ目)")
                    break
                    
                rows = table.find_all('tr')
                if len(rows) <= 1:
                    break # ヘッダー行のみなら終了
                    
                data_count = 0
                for row in rows[1:]:
                    cols = row.find_all(['th', 'td'])
                    if len(cols) < 11:
                        continue
                        
                    ticker = cols[0].text.strip()
                    if not ticker.isdigit():
                        continue
                        
                    # 信用倍率
                    ratio_str = cols[9].text.replace(',', '').strip()
                    try:
                        ratio = float(ratio_str)
                    except ValueError:
                        ratio = 0.0 # 倍率が "-" などの場合
                        
                    # 残高
                    volume_str = cols[10].text.replace(',', '').strip()
                    try:
                        volume = int(volume_str)
                    except ValueError:
                        volume = 0
                        
                    buy_vol = 0
                    sell_vol = 0
                    
                    if mode in ['7_1', '7_3']:
                        # 売り残ランキングの場合、cols[10]は「売り残」
                        sell_vol = volume
                        buy_vol = int(math.floor(sell_vol * ratio)) if ratio > 0 else 0
                    else:
                        # 買い残ランキングの場合、cols[10]は「買い残」
                        buy_vol = volume
                        sell_vol = int(math.floor(buy_vol / ratio)) if ratio > 0 else 0
                        
                    # 既に別ランキングで取得済みなら上書き（より新しい/整合性のあるものを優先）
                    results_dict[ticker] = {
                        'ticker_symbol': ticker,
                        'margin_buy_volume': buy_vol,
                        'margin_sell_volume': sell_vol,
                        'margin_ratio': ratio if ratio > 0 else None
                    }
                    data_count += 1
                
                print(f"    - {page} ページ目を取得完了 ({data_count}件)")
                
                # 次のページがあるかチェック
                pagination = soup.find('div', class_='pagination')
                if pagination and '次へ' in pagination.text:
                    page += 1
                else:
                    break # 最後のページ
                    
            except Exception as e:
                print(f"    ❌ エラー: {page}ページ目の取得に失敗: {e}")
                break
                
    # 基準日が取れなかった場合は計算
    if not report_date_str:
        report_date_str = get_last_friday()
        print(f"  ⚠ 基準日が見つからないため、自動計算した日付を使用: {report_date_str}")
        
    # 日付をセットしてリストに変換
    final_results = []
    for ticker, data in results_dict.items():
        data['report_date'] = report_date_str
        final_results.append(data)
        
    return final_results

def save_to_supabase(supabase: Client, data):
    chunk_size = 1000
    total_saved = 0
    
    for i in range(0, len(data), chunk_size):
        chunk = data[i:i + chunk_size]
        try:
            supabase.table("margin_balances").upsert(chunk).execute()
            total_saved += len(chunk)
            print(f"  💾 {total_saved}/{len(data)} 件を保存...")
        except Exception as e:
            print(f"  ❌ 保存エラー (chunk {i}): {e}")
            
    return total_saved

if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    print("=== 信用取引残高データの取得を開始します (株探ランキング経由) ===\n")
    
    supabase = get_supabase_client()
    
    # 4つのランキングから全件取得
    data = fetch_kabutan_margin_ranking()
    print(f"\n合計 {len(data)} 銘柄の信用残高データを抽出しました。")
    
    if data:
        # DBに存在する銘柄のみにフィルタリング
        print("データベースと照合中...")
        active_res = supabase.table("companies").select("ticker_symbol").execute()
        active_tickers = set(row['ticker_symbol'] for row in active_res.data)
        
        valid_data = [d for d in data if d['ticker_symbol'] in active_tickers]
        print(f"有効な信用残高データ（DB登録対象）: {len(valid_data)}件\n")
        
        if valid_data:
            print("Supabaseへの保存を開始します...")
            saved = save_to_supabase(supabase, valid_data)
            print(f"\n🎉 完了: 全 {saved} 件の信用残高データを保存しました！")
        else:
            print("保存対象の有効なデータがありませんでした。")
    else:
        print("データが取得できませんでした。")
