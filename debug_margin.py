import yfinance as yf

# テスト銘柄で決算日が取れるか確認
test_tickers = ['7203.T', '9984.T', '8306.T', '1301.T']

for ticker_str in test_tickers:
    stock = yf.Ticker(ticker_str)
    
    print(f"\n=== {ticker_str} ===")
    
    # calendarプロパティを確認
    try:
        cal = stock.calendar
        print(f"calendar: {cal}")
    except Exception as e:
        print(f"calendar error: {e}")
    
    # infoからearnings関連を探す
    try:
        info = stock.info
        earnings_keys = [k for k in info.keys() if 'earn' in k.lower() or 'fiscal' in k.lower() or 'date' in k.lower() or 'quarter' in k.lower()]
        for k in earnings_keys:
            print(f"  info['{k}'] = {info[k]}")
    except Exception as e:
        print(f"info error: {e}")
