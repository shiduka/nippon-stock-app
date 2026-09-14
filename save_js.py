import requests
from bs4 import BeautifulSoup

res = requests.get('https://tokuyutai.com/data/vesting-3', headers={'User-Agent': 'Mozilla/5.0'})
res.encoding = 'utf-8'

with open("debug_js.html", "w", encoding="utf-8") as f:
    f.write(res.text)
