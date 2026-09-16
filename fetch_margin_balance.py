import requests
import re
import time
import random
import os
from datetime import datetime, timedelta
from supabase import create_client, Client
from dotenv import load_dotenv

def get_last_friday():
    """実行日の直近の金曜日（信用残高の基準日）を計算する"""
    today = datetime.now().date()
    offset = (today.weekday() - 4) % 7
    last_friday = today - timedelta(days=offset)
    return last_friday

def get_supabase_client() -> Client:
    load_dotenv()
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise ValueError("SUPABASE_URL or SUPABASE_KEY is missing in .env")
    return create_client(url, key)

def get_active_tickers(supabase: Client, limit: int = None):
    """全銘柄コードをページネーション付きで取得する"""
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

def fetch_margin_for_ticker(ticker, headers):
    """1銘柄の信用残高をYahoo!ファイナンスから取得する"""
    url = f"https://finance.yahoo.co.jp/quote/{ticker}.T/margin"
    
    res = requests.get(url, headers=headers, timeout=15)
    res.raise_for_status()
    html = res.text
    
    # テーブル行(tr)の中からデータセル(td)の数値を取得する
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)
    
    # 最新の1行目だけを取得（テーブルの最初のデータ行）
    for row in rows:
        values = re.findall(r'_StyledNumber__value[^>]*>([^<]+)<', row)
        if len(values) >= 5:
            # [売残, 買残, 売残増減, 買残増減, 倍率]
            sell_vol = int(values[0].replace(',', ''))
            buy_vol = int(values[1].replace(',', ''))
            # 倍率が「---」の場合はNoneにする（売残0の銘柄など）
            try:
                margin_ratio = float(values[4].replace(',', ''))
            except ValueError:
                margin_ratio = None
            
            return {
                'margin_buy_volume': buy_vol,
                'margin_sell_volume': sell_vol,
                'margin_ratio': margin_ratio
            }
    
    return None

def fetch_margin_balance_yahoo(ticker_list):
    """
    Yahoo!ファイナンスから信用残高データをスクレイピングする。
    レート制限対策として、リトライ・バッチ休憩・ランダム遅延を実装。
    """
    results = []
    report_date = get_last_friday()
    total = len(ticker_list)
    skip_count = 0
    error_count = 0
    consecutive_skips = 0
    
    # スクレイピング用のヘッダー
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'ja,en-US;q=0.7,en;q=0.3',
    }
    
    for i, ticker in enumerate(ticker_list):
        try:
            data = fetch_margin_for_ticker(ticker, headers)
            
            if data:
                data['ticker_symbol'] = ticker
                data['report_date'] = report_date.isoformat()
                results.append(data)
                print(f"  ✅ {ticker}: 売残={data['margin_sell_volume']:,} 買残={data['margin_buy_volume']:,} 倍率={data['margin_ratio']}")
                consecutive_skips = 0  # 成功したらリセット
            else:
                skip_count += 1
                consecutive_skips += 1
                
        except requests.exceptions.HTTPError as e:
            # e.response がある場合はステータスコードを取得
            status_code = e.response.status_code if hasattr(e, 'response') and e.response else 0
            
            # e.responseが取れない場合でも文字列から判定
            err_str = str(e)
            if '404' in err_str or '500' in err_str:
                skip_count += 1
                consecutive_skips += 1
            elif '403' in err_str or '429' in err_str:
                print(f"  ⚠ 403/429ブロックを検知。レート制限回避のため60秒待機します...")
                time.sleep(60)
                skip_count += 1
                error_count += 1
                consecutive_skips += 1
                print(f"  ❌ [{ticker}] HTTPエラー: {e}")
            else:
                error_count += 1
                consecutive_skips += 1
                print(f"  ❌ [{ticker}] HTTPエラー: {e}")
                
        except Exception as e:
            error_count += 1
            consecutive_skips += 1
            print(f"  ❌ [{ticker}] 取得エラー: {e}")
            
        # 安全装置: 100件連続でスキップが続いた場合、YahooのCAPTCHAにブロックされたと判断
        if consecutive_skips >= 100:
            print(f"\n  🚨 100件連続でデータが取得できませんでした。Yahooのボット検知に完全にブロックされたため、処理を中断します。")
            break
        
        # 進捗表示（50銘柄ごと）
        if (i + 1) % 50 == 0:
            success = len(results)
            print(f"\n  === 進捗: {i + 1}/{total} 処理済み | ✅ 成功: {success} | ⏭️ スキップ: {skip_count} | ❌ エラー: {error_count} ===\n")
            
        # 安全装置: 50回以上連続でスキップ（Noneまたはエラー）が続いた場合、Yahooのボット検知に引っかかっている可能性が高い
        if skip_count > 0 and len(results) > 0 and (skip_count % 50 == 0) and (i - len(results) > 50):
            # 最近の50件がすべてスキップかどうかを厳密に判定するのは複雑なので簡易的に
            pass # ここでは複雑化を避けるため実装をスキップ
        
        # 50銘柄ごとに長めの休憩（レート制限回避）
        if (i + 1) % 50 == 0:
            pause = random.uniform(30, 45) # 15秒から30〜45秒に延長
            print(f"  💤 ブロック回避のため {pause:.1f} 秒休憩します...")
            time.sleep(pause)
        else:
            # 通常は 3.0〜5.0 秒のランダム遅延（WAFの分間アクセス数制限を回避するため）
            time.sleep(random.uniform(3.0, 5.0))
        
    return results

def save_to_supabase(supabase: Client, data):
    """取得したデータを1000件ずつチャンクに分けてSupabaseに保存する"""
    chunk_size = 1000
    total_saved = 0
    
    for i in range(0, len(data), chunk_size):
        chunk = data[i:i + chunk_size]
        try:
            supabase.table("margin_balances").upsert(chunk).execute()
            total_saved += len(chunk)
            print(f"  💾 {total_saved}/{len(data)} 件を保存...")
        except Exception as e:
            print(f"  保存エラー (chunk {i}): {e}")
    
    return total_saved

if __name__ == "__main__":
    print("信用取引残高の取得を開始します (Yahoo!ファイナンス経由)...")
    print(f"基準日: {get_last_friday()}")
    supabase = get_supabase_client()
    
    # 全銘柄を対象に信用残高を取得する
    target_tickers = get_active_tickers(supabase, limit=None)
    print(f"取得対象: {len(target_tickers)} 銘柄\n")
    
    data = fetch_margin_balance_yahoo(target_tickers)
    
    if data:
        print(f"\nSupabaseへの保存を開始します ({len(data)} 件)...")
        saved = save_to_supabase(supabase, data)
        print(f"\n🎉 完了！ {saved} 件の信用残高データを保存しました！")
    else:
        print("データが取得できませんでした。")
