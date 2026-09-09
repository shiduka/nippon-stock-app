import requests
import json
import re

# marginではなく、historyページのデフォルト(株価時系列)を確認
# 実は信用残の時系列データはAPIで取得できる可能性がある
# Yahoo!ファイナンスの内部APIを探す

res = requests.get('https://finance.yahoo.co.jp/quote/1301.T/margin', headers={'User-Agent': 'Mozilla/5.0'})
html = res.text

# API URLを探す
api_patterns = re.findall(r'https?://[a-zA-Z0-9._/-]+(?:api|history|margin|timeseries)[a-zA-Z0-9._/?&=-]*', html)
print("API-like URLs found:")
for url in set(api_patterns):
    print(f"  {url}")

# すべてのscriptタグから marginHistory や marginTimeseries等のデータを探す
scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
all_scripts = "\n".join(scripts)

# marginHistoryデータ（テーブル行）を探す
# 信用残のテーブルはtr/tdで構成されているかも
table_data = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)
print(f"\nTable rows found: {len(table_data)}")
for i, row in enumerate(table_data[:5]):
    td_data = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
    if td_data:
        print(f"  Row {i}: {td_data[:6]}")

# marginBalanceRows のようなプロパティを探す
margin_props = re.findall(r'"(margin[A-Za-z]*)"', all_scripts)
print(f"\nMargin-related props: {set(margin_props)}")

# historyRows のようなプロパティを探す  
history_props = re.findall(r'"(history[A-Za-z]*)"', all_scripts)
print(f"History-related props: {set(history_props)}")

# rows のようなプロパティを探す
rows_match = re.search(r'"rows"\s*:\s*\[(.*?)\]', all_scripts)
if rows_match:
    print(f"\nRows data found: {rows_match.group(0)[:500]}")
    
# tableData のようなプロパティを探す  
table_match = re.search(r'"tableData"\s*:\s*\[(.*?)\]', all_scripts)
if table_match:
    print(f"\nTable data found: {table_match.group(0)[:500]}")

# 他のデータ構造を探す
data_props = re.findall(r'"([a-zA-Z]*(?:[Dd]ata|[Rr]ows|[Ii]tems|[Ll]ist))"', all_scripts)
print(f"\nData-related props: {set(data_props)}")
