import os
from supabase import create_client, Client
from dotenv import load_dotenv

# .envファイルから環境変数を読み込む
load_dotenv()
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL or SUPABASE_KEY is missing in .env file")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 代表的な優待銘柄の本物データ（シードデータ）
benefits_data = [
    {"ticker_symbol": "8267", "record_month": 2, "min_shares": 100, "benefit_summary": "イオンオーナーズカード（買物金額の3%〜返金）"},
    {"ticker_symbol": "3197", "record_month": 6, "min_shares": 100, "benefit_summary": "自社グループお食事券 2,000円分 (すかいらーく)"},
    {"ticker_symbol": "3197", "record_month": 12, "min_shares": 100, "benefit_summary": "自社グループお食事券 2,000円分 (すかいらーく)"},
    {"ticker_symbol": "9861", "record_month": 2, "min_shares": 100, "benefit_summary": "吉野家 飲食券 500円×4枚 (2,000円分)"},
    {"ticker_symbol": "9861", "record_month": 8, "min_shares": 100, "benefit_summary": "吉野家 飲食券 500円×4枚 (2,000円分)"},
    {"ticker_symbol": "2702", "record_month": 6, "min_shares": 100, "benefit_summary": "マクドナルド 優待食事券 1冊（バーガー・サイド・ドリンク券 各6枚）"},
    {"ticker_symbol": "2702", "record_month": 12, "min_shares": 100, "benefit_summary": "マクドナルド 優待食事券 1冊（バーガー・サイド・ドリンク券 各6枚）"},
    {"ticker_symbol": "9433", "record_month": 3, "min_shares": 100, "benefit_summary": "KDDI カタログギフト 3,000円相当 (※2025年変更予定)"},
    {"ticker_symbol": "7421", "record_month": 2, "min_shares": 100, "benefit_summary": "コジマ お買物優待券 1,000円分"},
    {"ticker_symbol": "9831", "record_month": 3, "min_shares": 100, "benefit_summary": "ヤマダHD お買物優待券 500円分×1枚"},
    {"ticker_symbol": "3048", "record_month": 2, "min_shares": 100, "benefit_summary": "ビックカメラ お買物優待券 2,000円分"},
    {"ticker_symbol": "3048", "record_month": 8, "min_shares": 100, "benefit_summary": "ビックカメラ お買物優待券 1,000円分"},
    {"ticker_symbol": "7203", "record_month": 3, "min_shares": 100, "benefit_summary": "トヨタ カレンダー等の抽選など (実質的な金銭優待なし)"}
]

print(f"優待データ {len(benefits_data)} 件をSupabaseに登録します...")

for benefit in benefits_data:
    # 既存のデータがあれば上書き、なければ挿入する安全なUpsert処理
    # (本当はbenefit_idが主キーだが、今回はtickerとmonthで重複を簡易的に避ける処理にしてもよい。簡単のためそのままinsert)
    # 重複挿入を防ぐため、一度削除してから追加
    supabase.table("shareholder_benefits").delete().eq("ticker_symbol", benefit["ticker_symbol"]).eq("record_month", benefit["record_month"]).execute()
    supabase.table("shareholder_benefits").insert(benefit).execute()
    print(f"✅ {benefit['ticker_symbol']} ({benefit['record_month']}月) のデータを保存しました。")

print("\n🎉 すべての優待データの登録が完了しました！")
