from dotenv import load_dotenv
import os
from supabase import create_client

load_dotenv()
s = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])

# 信用残高の状態を確認
r1 = s.table("margin_balances").select("report_date, ticker_symbol").order("report_date", desc=True).limit(5).execute()
print("=== margin_balances (latest 5) ===")
for r in r1.data:
    print(f"  {r['ticker_symbol']}: {r['report_date']}")

r1_count = s.table("margin_balances").select("ticker_symbol", count="exact").execute()
print(f"Total: {r1_count.count}")

# 優待の状態を確認
r2 = s.table("shareholder_benefits").select("ticker_symbol, record_month, benefit_summary").limit(10).execute()
print("\n=== shareholder_benefits (first 10) ===")
for r in r2.data:
    summary = r['benefit_summary'][:40] if r.get('benefit_summary') else "N/A"
    print(f"  {r['ticker_symbol']} ({r['record_month']}): {summary}")

r2_count = s.table("shareholder_benefits").select("benefit_id", count="exact").execute()
print(f"Total: {r2_count.count}")

# 信用残高 - report_dateの種類
r3 = s.rpc("", {}).execute() if False else None
dates = set(r['report_date'] for r in s.table("margin_balances").select("report_date").execute().data)
print(f"\nmargin report_dates: {sorted(dates)}")
