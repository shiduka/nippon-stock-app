import os
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from dotenv import load_dotenv
from supabase import create_client, Client
import datetime

@st.cache_resource
def init_supabase() -> Client:
    load_dotenv()
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url:
        try:
            url = st.secrets["SUPABASE_URL"]
            key = st.secrets["SUPABASE_KEY"]
        except Exception:
            pass
    if not url or not key:
        st.error("エラー: 接続情報が見つかりません")
        st.stop()
    return create_client(url, key)

supabase = init_supabase()
st.set_page_config(page_title="日本株投資・発掘アプリ", layout="centered", initial_sidebar_state="collapsed")
st.title("📈 日本株投資・発掘アプリ")

tab1, tab2, tab3, tab4 = st.tabs(["🔍 個別銘柄詳細", "🎯 条件スクリーナー", "🔮 アノマリー・統計分析", "⚙️ システム管理"])

with tab1:
    st.subheader("🔍 銘柄の検索・分析")
    if "selected_ticker_direct" not in st.session_state:
        st.session_state["selected_ticker_direct"] = None
    
    col_search, col_btn = st.columns([4, 1])
    with col_search:
        search_query = st.text_input("銘柄コード または 企業名で検索", placeholder="例: 7203 または トヨタ", value="", key="search_input")
    with col_btn:
        st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
        search_btn = st.button("🔍 検索", use_container_width=True)
        
    direct_ticker = st.session_state["selected_ticker_direct"]
    if search_query:
        direct_ticker = None
        st.session_state["selected_ticker_direct"] = None
        
    if not search_query and not direct_ticker:
        fav_res = supabase.table("favorites").select("ticker_symbol").execute()
        if fav_res.data:
            st.markdown("⭐ **お気に入り:**")
            
            # companiesテーブルから企業名を取得
            tickers = [f['ticker_symbol'] for f in fav_res.data]
            comp_res = supabase.table("companies").select("ticker_symbol, company_name").in_("ticker_symbol", tickers).execute()
            comp_dict = {c['ticker_symbol']: c['company_name'] for c in comp_res.data} if comp_res.data else {}
            
            cols = st.columns(min(len(fav_res.data), 8))
            for i, fav in enumerate(fav_res.data):
                with cols[i % len(cols)]:
                    t = fav['ticker_symbol']
                    n = comp_dict.get(t, "")
                    label = f"{n}\n({t})" if n else t
                    if st.button(label, key=f"fav_btn_{t}", use_container_width=True):
                        st.session_state["selected_ticker_direct"] = t
                        st.rerun()

    query_str = direct_ticker if direct_ticker else search_query
    
    if query_str:
        with st.spinner("データベースを検索中..."):
            if query_str.isdigit():
                response = supabase.table("companies").select("*").eq("ticker_symbol", query_str).execute()
            else:
                response = supabase.table("companies").select("*").ilike("company_name", f"%{query_str}%").execute()
                
            data = response.data if response else []
            if data:
                company = data[0]
                ticker = company['ticker_symbol']
                
                header_col1, header_col2 = st.columns([5, 1])
                with header_col1:
                    st.markdown(f"### {company['company_name']} ({ticker})")
                    st.caption(f"{company.get('market', '不明')} | {company.get('sector_33', '不明')}")
                
                prices_res = supabase.table("daily_stock_prices").select("*").eq("ticker_symbol", ticker).order("trade_date", desc=True).limit(200).execute()
                price_data = prices_res.data
                
                col1, col2, col3, col4 = st.columns(4)
                if price_data:
                    latest = price_data[0]
                    prev_close = latest['close_price'] - latest['price_change']
                    pct_change = (latest['price_change'] / prev_close * 100) if prev_close else 0
                    col1.metric(label=f"終値 ({latest['trade_date']})", value=f"{latest['close_price']:,} 円", delta=f"{latest['price_change']:+,} ({pct_change:+.2f}%)")
                else:
                    col1.metric(label="終値", value="データなし", delta="---")
                
                div_yield = company.get('dividend_yield')
                if div_yield and div_yield > 0:
                    col2.metric(label="配当利回り", value=f"{div_yield:.2f} %", delta_color="off")
                else:
                    col2.metric(label="配当利回り", value="無配 / 未取得", delta_color="off")
                
                margin_res = supabase.table("margin_balances").select("*").eq("ticker_symbol", ticker).order("report_date", desc=True).limit(1).execute()
                if margin_res.data:
                    m_data = margin_res.data[0]
                    ratio_str = f"{m_data['margin_ratio']} 倍" if m_data.get('margin_ratio') is not None else "--- 倍"
                    col3.metric(label=f"信用倍率 ({m_data['report_date']})", value=ratio_str, delta=None)
                else:
                    col3.metric(label="信用倍率", value="データなし", delta="---")
                
                earnings_date = company.get('next_earnings_date')
                if earnings_date:
                    col4.metric(label="次回決算", value=earnings_date, delta_color="off")
                else:
                    col4.metric(label="次回決算", value="未定", delta_color="off")
                
                benefit_res = supabase.table("shareholder_benefits").select("*").eq("ticker_symbol", ticker).eq("is_active", True).execute()
                if benefit_res.data:
                    st.markdown("---")
                    st.write("🎁 **株主優待情報**")
                    for ben in benefit_res.data:
                        st.info(f"【{ben['record_month']}月権利】 {ben.get('min_shares', '-')}株以上: {ben.get('benefit_summary', '')}")
                
                st.markdown("---")
                st.write("📊 **直近の株価推移**")
                if price_data:
                    df_prices = pd.DataFrame(price_data).sort_values("trade_date")
                    fig = go.Figure(data=[go.Candlestick(x=df_prices['trade_date'], open=df_prices['open_price'], high=df_prices['high_price'], low=df_prices['low_price'], close=df_prices['close_price'], name="株価")])
                    fig.update_layout(xaxis_rangeslider_visible=False, margin=dict(l=0, r=0, t=10, b=0), height=400)
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning("この銘柄の株価データはまだ取得されていません。")
                
                anomaly_res = supabase.table("anomaly_analysis_results").select("*").eq("ticker_symbol", ticker).execute()
                if anomaly_res.data:
                    anom = anomaly_res.data[0]
                    st.markdown("---")
                    st.write("🎯 **優待権利月の株価上昇アノマリー（過去10年分析）**")
                    best_offset = anom.get('best_buy_offset')
                    if best_offset: st.info(f"💡 **最適な仕込み時期:** 権利確定月の **{best_offset}ヶ月前** の月末")
                    anom_data = []
                    for i in range(1, 7):
                        win_rate = anom.get(f'win_rate_{i}m')
                        avg_return = anom.get(f'avg_return_{i}m')
                        if win_rate is not None and avg_return is not None:
                            anom_data.append({"買いタイミング": f"{i}ヶ月前", "勝率": f"{win_rate * 100:.1f} %", "平均リターン": f"{avg_return * 100:+.2f} %"})
                    if anom_data:
                        st.table(pd.DataFrame(anom_data))
                        st.caption(f"※分析対象データ年数: {anom.get('analyzed_years', 'N/A')}年分")
                
                if len(data) > 1:
                    st.markdown("---")
                    st.markdown("**他の検索候補:**")
                    df_others = pd.DataFrame(data[1:])[['ticker_symbol', 'company_name', 'market', 'sector_33']]
                    df_others.columns = ['コード', '銘柄名', '市場', '業種']
                    st.dataframe(df_others, hide_index=True)

with tab2:
    menu_col, content_col = st.columns([1, 4])
    with menu_col:
        st.markdown("**🔍 分析メニュー**")
        analysis_mode = st.radio("条件を選択", [
            "🎁 株主優待スクリーナー",
            "📈 踏み上げ期待 (好取組)",
            "📉 しこり玉解消 (買い残減少)",
            "📊 出来高急増 (ブレイクアウト)",
            "💤 閑散からの底打ち (初動狙い)",
            "📅 1週間以内に決算発表",
            "💰 5万円以下で買える"
        ], label_visibility="collapsed")
    with content_col:
        if analysis_mode == "🎁 株主優待スクリーナー":
            st.subheader("🎁 株主優待スクリーナー")
            st.write("権利確定月を選んで、優待銘柄を検索します。")
            target_month = st.selectbox("権利確定月を選択", [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12], index=2)
            if st.button("優待銘柄を検索"):
                with st.spinner("検索中..."):
                    ben_res = supabase.table("shareholder_benefits").select("*").eq("record_month", target_month).execute()
                    if ben_res.data:
                        df_ben = pd.DataFrame(ben_res.data)
                        tickers = df_ben["ticker_symbol"].tolist()
                        comp_res = supabase.table("companies").select("ticker_symbol, company_name").in_("ticker_symbol", tickers).execute()
                        df_comps = pd.DataFrame(comp_res.data)
                        latest_price = supabase.table("daily_stock_prices").select("trade_date").order("trade_date", desc=True).limit(1).execute()
                        df_prices = pd.DataFrame(columns=["ticker_symbol", "close_price", "price_change"])
                        if latest_price.data:
                            price_res = supabase.table("daily_stock_prices").select("ticker_symbol, close_price, price_change").eq("trade_date", latest_price.data[0]['trade_date']).in_("ticker_symbol", tickers).execute()
                            if price_res.data: df_prices = pd.DataFrame(price_res.data)
                        df_merged = pd.merge(df_ben, df_comps, on="ticker_symbol", how="left")
                        if not df_prices.empty: df_merged = pd.merge(df_merged, df_prices, on="ticker_symbol", how="left")
                        else:
                            df_merged['close_price'] = None
                            df_merged['price_change'] = None
                        df_display = df_merged[['ticker_symbol', 'company_name', 'min_shares', 'close_price', 'benefit_summary']]
                        df_display.columns = ['コード', '銘柄名', '最低株数', '終値 (円)', '優待内容']
                        st.success(f"{target_month}月権利確定の優待銘柄: **{len(df_display)}銘柄**")
                        st.dataframe(df_display, hide_index=True, use_container_width=True)
                    else:
                        st.info(f"{target_month}月に権利確定する優待銘柄は見つかりませんでした。")
        elif analysis_mode == "📈 踏み上げ期待 (好取組)":
            st.subheader("📈 踏み上げ（ショートスクイズ）狙い")
            st.write("信用倍率1.0倍未満（売り残 ＞ 買い残）で、売り残高が50,000株以上の銘柄。好材料で一気に急騰しやすい状態です。")
            with st.spinner("データ取得中..."):
                margin_res = supabase.table("margin_balances").select("*").lt("margin_ratio", 1.0).gte("margin_sell_volume", 50000).execute()
                if margin_res.data:
                    df_margin = pd.DataFrame(margin_res.data).sort_values("report_date", ascending=False).drop_duplicates(subset="ticker_symbol", keep="first")
                    tickers = df_margin["ticker_symbol"].tolist()
                    comp_res = supabase.table("companies").select("ticker_symbol, company_name, sector_33").in_("ticker_symbol", tickers).execute()
                    df_comps = pd.DataFrame(comp_res.data)
                    latest_price = supabase.table("daily_stock_prices").select("trade_date").order("trade_date", desc=True).limit(1).execute()
                    df_prices = pd.DataFrame(columns=["ticker_symbol", "close_price"])
                    if latest_price.data:
                        price_res = supabase.table("daily_stock_prices").select("ticker_symbol, close_price").eq("trade_date", latest_price.data[0]['trade_date']).in_("ticker_symbol", tickers).execute()
                        if price_res.data: df_prices = pd.DataFrame(price_res.data)
                    today = datetime.date.today()
                    ben_res = supabase.table("shareholder_benefits").select("ticker_symbol").in_("record_month", [today.month, (today.month % 12) + 1]).execute()
                    ben_tickers = [d['ticker_symbol'] for d in ben_res.data] if ben_res.data else []
                    df_merged = pd.merge(df_margin, df_comps, on="ticker_symbol", how="left")
                    if not df_prices.empty: df_merged = pd.merge(df_merged, df_prices, on="ticker_symbol", how="left")
                    else: df_merged['close_price'] = None
                    df_filtered = df_merged[~df_merged['ticker_symbol'].isin(ben_tickers)].copy().sort_values("margin_ratio", ascending=True)
                    df_display = df_filtered[['ticker_symbol', 'company_name', 'sector_33', 'margin_ratio', 'margin_sell_volume', 'margin_buy_volume', 'close_price']]
                    df_display.columns = ['コード', '銘柄名', '業種', '信用倍率', '売残', '買残', '終値 (円)']
                    st.success(f"該当銘柄: **{len(df_display)}銘柄** (※直近優待銘柄は除外済み)")
                    st.dataframe(df_display, hide_index=True, use_container_width=True)
                else:
                    st.info("条件に一致する銘柄は見つかりませんでした。")
        elif analysis_mode == "📉 しこり玉解消 (買い残減少)":
            st.subheader("📉 しこり玉解消（アク抜け）狙い")
            st.write("信用買い残の前週比が大幅マイナス（-50,000株以下）の銘柄。高値掴みの損切りが終わり、上値が軽くなった状態です。")
            with st.spinner("データ取得中..."):
                margin_res = supabase.table("margin_balances").select("*").lte("margin_buy_volume_change", -50000).execute()
                if margin_res.data:
                    df_margin = pd.DataFrame(margin_res.data).sort_values("report_date", ascending=False).drop_duplicates(subset="ticker_symbol", keep="first")
                    tickers = df_margin["ticker_symbol"].tolist()
                    comp_res = supabase.table("companies").select("ticker_symbol, company_name, sector_33").in_("ticker_symbol", tickers).execute()
                    df_comps = pd.DataFrame(comp_res.data)
                    latest_price = supabase.table("daily_stock_prices").select("trade_date").order("trade_date", desc=True).limit(1).execute()
                    df_prices = pd.DataFrame(columns=["ticker_symbol", "close_price"])
                    if latest_price.data:
                        price_res = supabase.table("daily_stock_prices").select("ticker_symbol, close_price").eq("trade_date", latest_price.data[0]['trade_date']).in_("ticker_symbol", tickers).execute()
                        if price_res.data: df_prices = pd.DataFrame(price_res.data)
                    df_merged = pd.merge(df_margin, df_comps, on="ticker_symbol", how="left")
                    if not df_prices.empty: df_merged = pd.merge(df_merged, df_prices, on="ticker_symbol", how="left")
                    else: df_merged['close_price'] = None
                    df_merged = df_merged.sort_values("margin_buy_volume_change", ascending=True)
                    df_display = df_merged[['ticker_symbol', 'company_name', 'sector_33', 'margin_buy_volume', 'margin_buy_volume_change', 'margin_ratio', 'close_price']]
                    df_display.columns = ['コード', '銘柄名', '業種', '買残', '前週比 (株)', '信用倍率', '終値 (円)']
                    st.success(f"該当銘柄: **{len(df_display)}銘柄**")
                    st.dataframe(df_display, hide_index=True, use_container_width=True)
                else:
                    st.info("データがありません。")
        elif analysis_mode == "📊 出来高急増 (ブレイクアウト)":
            st.subheader("📊 出来高急増（ブレイクアウト）")
            st.write("前営業日と比較して、出来高が急激に（3倍以上）増加した銘柄。大口の資金流入やニュース発表による初動の可能性があります。")
            with st.spinner("全銘柄の直近の株価データを解析中..."):
                dates_res = supabase.table("daily_stock_prices").select("trade_date").order("trade_date", desc=True).limit(2).execute()
                if dates_res.data and len(dates_res.data) >= 2:
                    l_date = dates_res.data[0]['trade_date']
                    p_date = dates_res.data[1]['trade_date']
                    latest_data = []
                    start = 0
                    while True:
                        res = supabase.table("daily_stock_prices").select("ticker_symbol, close_price, volume, price_change").eq("trade_date", l_date).range(start, start + 999).execute()
                        if not res.data: break
                        latest_data.extend(res.data)
                        start += 1000
                    prev_data = []
                    start = 0
                    while True:
                        res = supabase.table("daily_stock_prices").select("ticker_symbol, volume").eq("trade_date", p_date).range(start, start + 999).execute()
                        if not res.data: break
                        prev_data.extend(res.data)
                        start += 1000
                    df_l = pd.DataFrame(latest_data)
                    df_p = pd.DataFrame(prev_data).rename(columns={"volume": "prev_volume"})
                    if not df_l.empty and not df_p.empty:
                        df_m = pd.merge(df_l, df_p, on="ticker_symbol", how="inner")
                        df_f = df_m[(df_m['prev_volume'] >= 10000) & (df_m['volume'] >= df_m['prev_volume'] * 3)].copy()
                        if not df_f.empty:
                            df_f['ratio'] = (df_f['volume'] / df_f['prev_volume']).round(1)
                            df_f = df_f.sort_values("ratio", ascending=False)
                            comp_res = supabase.table("companies").select("ticker_symbol, company_name, sector_33").in_("ticker_symbol", df_f["ticker_symbol"].tolist()).execute()
                            df_c = pd.DataFrame(comp_res.data)
                            df_d = pd.merge(df_f, df_c, on="ticker_symbol", how="left")
                            df_d = df_d[['ticker_symbol', 'company_name', 'sector_33', 'close_price', 'price_change', 'prev_volume', 'volume', 'ratio']]
                            df_d.columns = ['コード', '銘柄名', '業種', '終値 (円)', '前日比', '前日出来高', '本日出来高', '増加倍率']
                            st.success(f"該当銘柄: **{len(df_d)}銘柄**")
                            st.dataframe(df_d, hide_index=True, use_container_width=True)
                        else: st.info("該当銘柄なし")
                    else: st.warning("データ不足")
                else: st.warning("データ不足")
        elif analysis_mode == "💤 閑散からの底打ち (初動狙い)":
            st.subheader("💤 閑散からの底打ち（初動狙い）")
            st.write("前営業日まで出来高が非常に少なかった（見放されていた）銘柄に、突然大きな買いが入った銘柄を抽出します。")
            with st.spinner("全銘柄の直近の株価データを解析中..."):
                dates_res = supabase.table("daily_stock_prices").select("trade_date").order("trade_date", desc=True).limit(2).execute()
                if dates_res.data and len(dates_res.data) >= 2:
                    l_date = dates_res.data[0]['trade_date']
                    p_date = dates_res.data[1]['trade_date']
                    latest_data = []
                    start = 0
                    while True:
                        res = supabase.table("daily_stock_prices").select("ticker_symbol, close_price, volume, price_change").eq("trade_date", l_date).range(start, start + 999).execute()
                        if not res.data: break
                        latest_data.extend(res.data)
                        start += 1000
                    prev_data = []
                    start = 0
                    while True:
                        res = supabase.table("daily_stock_prices").select("ticker_symbol, volume").eq("trade_date", p_date).range(start, start + 999).execute()
                        if not res.data: break
                        prev_data.extend(res.data)
                        start += 1000
                    df_l = pd.DataFrame(latest_data)
                    df_p = pd.DataFrame(prev_data).rename(columns={"volume": "prev_volume"})
                    if not df_l.empty and not df_p.empty:
                        df_m = pd.merge(df_l, df_p, on="ticker_symbol", how="inner")
                        df_f = df_m[(df_m['prev_volume'] < 10000) & (df_m['volume'] >= 50000) & (df_m['price_change'] > 0)].copy()
                        if not df_f.empty:
                            df_f = df_f.sort_values("volume", ascending=False)
                            comp_res = supabase.table("companies").select("ticker_symbol, company_name, sector_33").in_("ticker_symbol", df_f["ticker_symbol"].tolist()).execute()
                            df_c = pd.DataFrame(comp_res.data)
                            df_d = pd.merge(df_f, df_c, on="ticker_symbol", how="left")
                            df_d = df_d[['ticker_symbol', 'company_name', 'sector_33', 'close_price', 'price_change', 'prev_volume', 'volume']]
                            df_d.columns = ['コード', '銘柄名', '業種', '終値 (円)', '前日比', '前日出来高', '本日出来高']
                            st.success(f"該当銘柄: **{len(df_d)}銘柄**")
                            st.dataframe(df_d, hide_index=True, use_container_width=True)
                        else: st.info("該当銘柄なし")
                    else: st.warning("データ不足")
                else: st.warning("データ不足")
        elif analysis_mode == "📅 1週間以内に決算発表":
            st.subheader("📅 1週間以内に決算発表")
            with st.spinner("データ取得中..."):
                today = datetime.date.today()
                next_week = today + datetime.timedelta(days=7)
                comp_res = supabase.table("companies").select("ticker_symbol, company_name, sector_33, next_earnings_date").gte("next_earnings_date", today.isoformat()).lte("next_earnings_date", next_week.isoformat()).order("next_earnings_date", desc=False).execute()
                if comp_res.data:
                    df_comps = pd.DataFrame(comp_res.data)
                    tickers = df_comps["ticker_symbol"].tolist()
                    latest_price = supabase.table("daily_stock_prices").select("trade_date").order("trade_date", desc=True).limit(1).execute()
                    df_prices = pd.DataFrame(columns=["ticker_symbol", "close_price", "price_change"])
                    if latest_price.data:
                        price_res = supabase.table("daily_stock_prices").select("ticker_symbol, close_price, price_change").eq("trade_date", latest_price.data[0]['trade_date']).in_("ticker_symbol", tickers).execute()
                        if price_res.data: df_prices = pd.DataFrame(price_res.data)
                    df_merged = pd.merge(df_comps, df_prices, on="ticker_symbol", how="left")
                    df_display = df_merged[['ticker_symbol', 'company_name', 'sector_33', 'next_earnings_date', 'close_price', 'price_change']]
                    df_display.columns = ['コード', '銘柄名', '業種', '次回決算日', '終値 (円)', '前日比 (円)']
                    st.success(f"該当銘柄: **{len(df_display)}銘柄**")
                    st.dataframe(df_display, hide_index=True, use_container_width=True)
                else: st.info("1週間以内に決算発表が予定されている銘柄は見つかりませんでした。")
        elif analysis_mode == "💰 5万円以下で買える":
            st.subheader("💰 5万円以下で買える少額投資")
            with st.spinner("データ取得中..."):
                latest_price = supabase.table("daily_stock_prices").select("trade_date").order("trade_date", desc=True).limit(1).execute()
                if latest_price.data:
                    l_date = latest_price.data[0]['trade_date']
                    price_res = supabase.table("daily_stock_prices").select("ticker_symbol, close_price, price_change, volume").eq("trade_date", l_date).lte("close_price", 500).gte("volume", 50000).order("volume", desc=True).limit(100).execute()
                    if price_res.data:
                        df_prices = pd.DataFrame(price_res.data)
                        comp_res = supabase.table("companies").select("ticker_symbol, company_name, sector_33, dividend_yield").in_("ticker_symbol", df_prices["ticker_symbol"].tolist()).execute()
                        df_comps = pd.DataFrame(comp_res.data)
                        df_merged = pd.merge(df_prices, df_comps, on="ticker_symbol", how="left")
                        df_display = df_merged[['ticker_symbol', 'company_name', 'sector_33', 'close_price', 'price_change', 'volume', 'dividend_yield']]
                        df_display.columns = ['コード', '銘柄名', '業種', '終値 (円)', '前日比', '出来高', '配当利回り(%)']
                        st.success(f"該当銘柄: **{len(df_display)}銘柄** (※出来高5万株以上のみ)")
                        st.dataframe(df_display, hide_index=True, use_container_width=True)
                    else: st.info("該当銘柄なし")
                else: st.warning("データ不足")
with tab3:
    st.subheader("🎯 優待権利月の株価上昇アノマリー")
    st.write("過去10年間の株価データから、権利確定月に向けて株価が上がりやすい銘柄をランキング表示します。")

    col1, col2 = st.columns(2)
    sort_by = col1.selectbox("ランキングの基準", ["平均リターンが高い順", "勝率が高い順"])
    buy_offset = col2.selectbox("仕込みタイミング", ["3ヶ月前 (標準)", "1ヶ月前", "2ヶ月前", "4ヶ月前", "5ヶ月前", "6ヶ月前"])

    offset_map = {"1ヶ月前": 1, "2ヶ月前": 2, "3ヶ月前": 3, "4ヶ月前": 4, "5ヶ月前": 5, "6ヶ月前": 6, "3ヶ月前 (標準)": 3}
    offset_val = offset_map[buy_offset]

    if st.button("ランキングを表示"):
        with st.spinner("アノマリーデータを取得中..."):
            order_col = f"avg_return_{offset_val}m" if sort_by == "平均リターンが高い順" else f"win_rate_{offset_val}m"
            anom_res = supabase.table("anomaly_analysis_results").select(f"ticker_symbol, analyzed_years, win_rate_{offset_val}m, avg_return_{offset_val}m").order(order_col, desc=True).limit(100).execute()
            if anom_res.data:
                tickers = [d['ticker_symbol'] for d in anom_res.data]
                comp_res = supabase.table("companies").select("ticker_symbol, company_name").in_("ticker_symbol", tickers).execute()
                ben_res = supabase.table("shareholder_benefits").select("ticker_symbol, record_month").in_("ticker_symbol", tickers).execute()
                df_anom = pd.DataFrame(anom_res.data)
                df_comp = pd.DataFrame(comp_res.data)
                df_ben = pd.DataFrame(ben_res.data)
                df_merged = pd.merge(df_anom, df_comp, on="ticker_symbol", how="left")
                df_merged = pd.merge(df_merged, df_ben, on="ticker_symbol", how="left")
                df_display = df_merged[["ticker_symbol", "company_name", "record_month", "analyzed_years", f"win_rate_{offset_val}m", f"avg_return_{offset_val}m"]]
                df_display.columns = ["コード", "銘柄名", "権利月", "データ年数", "勝率", "平均リターン"]
                df_display["勝率"] = df_display["勝率"].apply(lambda x: f"{x*100:.1f} %" if pd.notna(x) else "-")
                df_display["平均リターン"] = df_display["平均リターン"].apply(lambda x: f"{x*100:+.2f} %" if pd.notna(x) else "-")
                st.dataframe(df_display, hide_index=True, use_container_width=True)
            else:
                st.warning("アノマリーデータがありません。")

with tab4:
    st.subheader("⚙️ システム管理・データステータス")
    st.write("データベースの最新状況やバッチ処理のスケジュールを確認できます。")
    with st.spinner("ステータスを取得中..."):
        companies_res = supabase.table("companies").select("ticker_symbol", count="exact").execute()
        active_res = supabase.table("companies").select("ticker_symbol", count="exact").eq("is_active", True).execute()
        prices_res = supabase.table("daily_stock_prices").select("ticker_symbol", count="exact").execute()
        margin_res = supabase.table("margin_balances").select("ticker_symbol", count="exact").execute()
        benefits_res = supabase.table("shareholder_benefits").select("benefit_id", count="exact").execute()
        favorites_res = supabase.table("favorites").select("id", count="exact").execute()
        m1, m2, m3 = st.columns(3)
        m1.metric("📋 登録企業数", f"{companies_res.count:,} 社")
        m2.metric("✅ アクティブ企業数", f"{active_res.count:,} 社")
        m3.metric("⭐ お気に入り", f"{favorites_res.count:,} 銘柄")
        m4, m5, m6 = st.columns(3)
        m4.metric("📊 株価レコード数", f"{prices_res.count:,} 件")
        m5.metric("💹 信用残高レコード数", f"{margin_res.count:,} 件")
        m6.metric("🎁 優待レコード数", f"{benefits_res.count:,} 件")
    st.markdown("---")
    st.markdown("### 📅 データ鮮度 (最新更新日)")
    with st.spinner("データの鮮度を確認中..."):
        freshness_data = []
        latest_price = supabase.table("daily_stock_prices").select("trade_date").order("trade_date", desc=True).limit(1).execute()
        freshness_data.append({"データ": "📊 日次株価", "最新日": latest_price.data[0]["trade_date"] if latest_price.data else "データなし", "更新頻度": "毎日 (平日18:00)"})
        latest_margin = supabase.table("margin_balances").select("report_date").order("report_date", desc=True).limit(1).execute()
        freshness_data.append({"データ": "💹 信用残高", "最新日": latest_margin.data[0]["report_date"] if latest_margin.data else "データなし", "更新頻度": "毎週火曜 (21:00)"})
        earnings_count = supabase.table("companies").select("ticker_symbol", count="exact").not_.is_("next_earnings_date", "null").execute()
        freshness_data.append({"データ": "📅 次回決算日", "最新日": f"{earnings_count.count:,} 社に登録済み", "更新頻度": "毎月1日 (20:00)"})
        dividend_count = supabase.table("companies").select("ticker_symbol", count="exact").gt("dividend_yield", 0).execute()
        freshness_data.append({"データ": "💰 配当利回り", "最新日": f"{dividend_count.count:,} 社に登録済み", "更新頻度": "毎月1日 (21:00)"})
        freshness_data.append({"データ": "🎁 株主優待", "最新日": f"{benefits_res.count:,} 件登録済み", "更新頻度": "毎月15日 (20:00)"})
        df_freshness = pd.DataFrame(freshness_data)
        st.dataframe(df_freshness, hide_index=True, use_container_width=True)
    st.markdown("---")
    st.markdown("### 🔄 自動バッチスケジュール")
    batch_data = [
        {"バッチ名": "📊 Daily Stock Price", "スケジュール": "平日 18:00 (JST)", "スクリプト": "fetch_stock_prices.py", "対象": "全銘柄の株価"},
        {"バッチ名": "💹 Weekly Margin Balance", "スケジュール": "毎週火曜 21:00 (JST)", "スクリプト": "fetch_margin_balance.py", "対象": "全銘柄の信用残高"},
        {"バッチ名": "📅 Monthly Earnings Date", "スケジュール": "毎月1日 20:00 (JST)", "スクリプト": "fetch_earnings_dates.py", "対象": "全銘柄の決算日"},
        {"バッチ名": "💰 Monthly Dividend Yield", "スケジュール": "毎月1日 21:00 (JST)", "スク পণ্ডিত": "fetch_dividend_yields.py", "対象": "全銘柄の配当利回り"},
        {"バッチ名": "🎁 Monthly Benefits", "スケジュール": "毎月15日 20:00 (JST)", "スクリプト": "fetch_benefits.py", "対象": "全銘柄の株主優待"},
    ]
    st.dataframe(pd.DataFrame(batch_data), hide_index=True, use_container_width=True)
    st.caption("💡 バッチはGitHub Actionsで自動実行されます。")
