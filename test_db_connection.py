import os
from dotenv import load_dotenv
from supabase import create_client, Client

# 1. .envファイルから接続情報（URLとキー）を読み込む
load_dotenv()
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")

if not url or not key:
    print("❌ エラー: .env ファイルに SUPABASE_URL または SUPABASE_KEY が設定されていません。")
    exit(1)

# 2. Supabaseへの接続クライアントを作成
supabase: Client = create_client(url, key)

def test_connection():
    print("Supabaseへの接続をテストしています...")
    
    # 企業マスター(companies)に入れるダミーデータ
    test_data = [
        {
            "ticker_symbol": "TEST",
            "company_name": "Supabase接続テスト株式会社",
            "market": "プライム",
            "sector_33": "情報・通信業",
            "status": "ACTIVE"
        }
    ]
    
    try:
        # 3. データを書き込む (upsertは「既にあれば上書き、無ければ新規作成」の便利コマンド)
        response = supabase.table("companies").upsert(test_data).execute()
        
        print("\n✅ 大成功！Supabaseへの接続と書き込みが完了しました！")
        print("--- 書き込まれたデータ ---")
        print(response.data)
        print("--------------------------")
        print("※Supabaseのダッシュボード「Table Editor」から、companiesテーブルを見てみてください！")
        
    except Exception as e:
        print("\n❌ エラーが発生しました。URLやAPIキーが間違っていないか確認してください。")
        print(f"詳細: {e}")

if __name__ == "__main__":
    test_connection()
