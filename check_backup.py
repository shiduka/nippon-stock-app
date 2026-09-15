import os
import pandas as pd
from supabase import create_client, Client
from dotenv import load_dotenv

def get_supabase_client() -> Client:
    load_dotenv()
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    return create_client(url, key)

def main():
    print("Supabase Storageからバックアップを確認します...")
    supabase = get_supabase_client()
    bucket_name = "backups"
    
    # 1. バケット内のファイル一覧を取得
    try:
        files = supabase.storage.from_(bucket_name).list()
        parquet_files = [f['name'] for f in files if f['name'].endswith('.parquet')]
        
        if not parquet_files:
            print("エラー: backupsバケットにParquetファイルが見つかりません。")
            return
            
        # 最新のファイルを選択
        latest_file = sorted(parquet_files)[-1]
        print(f"最新のバックアップファイルを発見: {latest_file}")
        
    except Exception as e:
        print(f"ファイル一覧の取得に失敗: {e}")
        return

    # 2. ファイルをダウンロード
    print(f"{latest_file} をダウンロード中...")
    try:
        with open(latest_file, 'wb') as f:
            res = supabase.storage.from_(bucket_name).download(latest_file)
            f.write(res)
    except Exception as e:
        print(f"ダウンロードに失敗: {e}")
        return

    # 3. ParquetファイルをPandasで読み込んで中身を確認
    print("\n--- バックアップデータの中身 ---")
    df = pd.read_parquet(latest_file)
    
    print(f"総レコード数: {len(df)} 件")
    print(f"データ期間: {df['trade_date'].min()} 〜 {df['trade_date'].max()}")
    print(f"銘柄の種類数: {df['ticker_symbol'].nunique()} 銘柄\n")
    
    print("▼ データの先頭5件 ▼")
    print(df.head())
    
    # Excelなどで見やすいように、先頭100件だけCSVとして出力しておく
    csv_file = "backup_sample.csv"
    df.head(100).to_csv(csv_file, index=False, encoding='utf-8-sig')
    print(f"\n※確認用に先頭100件をExcelで開ける '{csv_file}' として保存しました！")
    
    # Parquetファイルは大きいため削除
    os.remove(latest_file)

if __name__ == "__main__":
    main()
