import os
import datetime
from dateutil.relativedelta import relativedelta
import pandas as pd
from supabase import create_client, Client
from dotenv import load_dotenv

def get_supabase_client() -> Client:
    load_dotenv()
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise ValueError("SUPABASE_URL or SUPABASE_KEY is missing in .env")
    return create_client(url, key)

def fetch_all_daily_prices(supabase: Client):
    """Supabaseから全ての日次株価データを取得する"""
    print("DBから株価データを取得中...")
    all_data = []
    page_size = 1000
    start = 0
    
    while True:
        query = supabase.table("daily_stock_prices").select("*")
        query = query.range(start, start + page_size - 1)
        res = query.execute()
        
        if not res.data:
            break
            
        all_data.extend(res.data)
        
        if len(res.data) < page_size:
            break
            
        start += page_size
        print(f"  ... {len(all_data)}件 取得完了")
        
    return all_data

if __name__ == "__main__":
    print("=== 株価データのバックアップ＆パージ処理を開始します ===")
    
    supabase = get_supabase_client()
    today = datetime.date.today()
    
    # 1. 全データの取得
    all_data = fetch_all_daily_prices(supabase)
    print(f"合計 {len(all_data)} 件の株価データを取得しました。")
    
    if not all_data:
        print("バックアップするデータがありません。終了します。")
        exit(0)
        
    # 2. DataFrameに変換してParquet形式でローカルに保存
    df = pd.DataFrame(all_data)
    
    # Parquet（PyArrow）は空のJSON/ディクショナリ（struct）をうまく処理できないため、
    # JSONB型のカラム（extra_data等）は一旦文字列(String)に変換してから保存する
    if 'extra_data' in df.columns:
        # NoneやNaNを空のJSON文字列 '{}' にし、それ以外はJSON文字列に変換
        df['extra_data'] = df['extra_data'].apply(lambda x: '{}' if pd.isna(x) or x is None else str(x))
        
    # 日付を文字列にしてファイル名を作成
    date_str = today.strftime("%Y%m%d")
    filename = f"daily_stock_prices_{date_str}.parquet"
    
    print(f"{filename} に圧縮（Parquet）保存中...")
    df.to_parquet(filename, index=False)
    
    file_size_mb = os.path.getsize(filename) / (1024 * 1024)
    print(f"ファイル作成完了: サイズ約 {file_size_mb:.2f} MB")
    
    # 3. Supabase Storage の 'backups' バケットにアップロード
    bucket_name = "backups"
    print(f"Supabase Storage '{bucket_name}' バケットへアップロード中...")
    
    with open(filename, "rb") as f:
        # 既に同じ名前のファイルがあれば上書き（upsert=True のオプション的な挙動のため一応削除してからアップロード）
        try:
            supabase.storage.from_(bucket_name).remove([filename])
        except Exception:
            pass
            
        res = supabase.storage.from_(bucket_name).upload(
            path=filename,
            file=f,
            file_options={"content-type": "application/vnd.apache.parquet"}
        )
        print("アップロード完了！")
        
    # 4. パージ（古いデータの削除）処理
    # 今日から2年前の日付を計算
    two_years_ago = today - relativedelta(years=2)
    two_years_ago_str = two_years_ago.strftime("%Y-%m-%d")
    
    print(f"\nパージ処理: {two_years_ago_str} より古い株価データをDBから削除します...")
    
    try:
        # SupabaseのREST APIの delete は条件に一致するものを一括削除可能
        delete_res = supabase.table("daily_stock_prices") \
            .delete() \
            .lt("trade_date", two_years_ago_str) \
            .execute()
            
        # 何件削除されたかを確認
        deleted_count = len(delete_res.data) if delete_res.data else 0
        print(f"✅ 古いデータ {deleted_count} 件をDBから削除（パージ）し、容量を節約しました！")
    except Exception as e:
        print(f"❌ 削除処理中にエラーが発生しました: {e}")
        
    # 後片付け（ローカルのParquetファイルを削除）
    os.remove(filename)
    print("ローカルの一時ファイルを削除しました。")
    print("\n=== バックアップ＆パージ処理が正常に完了しました ===")
