from bs4 import BeautifulSoup
import re

html = open('debug_js.html', encoding='utf-8').read()
soup = BeautifulSoup(html, 'html.parser')
for s in soup.find_all('script'):
    if s.get('src'):
        print(s.get('src'))
