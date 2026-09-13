import os
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from dotenv import load_dotenv
from supabase import create_client, Client

# ==========================================
# データベース接続初期化 (キャッシュして高速化)
# ==========================================
@st.cache_resource
def init_supabase() -> Client:
    load_dotenv()
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    
    # Streamlit Cloud環境では st.secrets から取得する
    if not url:
        try:
            url = st.secrets["SUPABASE_URL"]
            key = st.secrets["SUPABASE_KEY"]
        except Exception:
            pass
            
    if not url or not key:
        st.error("エラー: 接続情報が見つかりません (Secretsの設定を確認してください)")
        st.stop()
    return create_client(url, key)

supabase = init_supabase()

# ==========================================
# ページ全体の設定
# ==========================================
st.set_page_config(page_title="日本株投資先発掘アプリ", layout="centered", initial_sidebar_state="collapsed")
st.title("📈 日本株投資先発掘アプリ")

tab1, tab2, tab3, tab4 = st.tabs(["個別銘柄詳細", "優待スクリーナー", "スマート検索", "システム管理"])

# ==========================================
# タブ1: 個別銘柄詳細
# ==========================================
with tab1:
    st.subheader("🔍 銘柄の検索・分析")
    
    # ==========================================
    # お気に入り一覧の表示
    # ==========================================
    fav_res = supabase.table("favorites").select("ticker_symbol, created_at").order("created_at", desc=True).execute()
    if fav_res.data:
        fav_tickers = [f["ticker_symbol"] for f in fav_res.data]
        fav_comp_res = supabase.table("companies").select("ticker_symbol, company_name").in_("ticker_symbol", fav_tickers).execute()
        fav_name_map = {c["ticker_symbol"]: c["company_name"] for c in fav_comp_res.data}
        
        st.markdown("⭐ **お気に入り銘柄** （クリックで検索欄にコピーしてください）")
        # お気に入りをボタンとして横並びに表示
        fav_cols = st.columns(min(len(fav_tickers), 5))
        for i, t in enumerate(fav_tickers[:10]):
            name = fav_name_map.get(t, t)
            fav_cols[i % 5].caption(f"**{t}** {name}")
        st.markdown("---")
    
    search_query = st.text_input("銘柄コードまたは企業名で検索", placeholder="例: 7203 または トヨタ")
    
    if search_query:
        query = f"%{search_query}%"
        response = supabase.table("companies").select("*").or_(f"ticker_symbol.ilike.{query},company_name.ilike.{query}").limit(5).execute()
        
        data = response.data
        if not data:
            st.warning(f"「{search_query}」に一致する銘柄が見つかりませんでした。")
        else:
            company = data[0]
            ticker = company['ticker_symbol']
            
            # お気に入り登録/解除ボタン
            is_fav = supabase.table("favorites").select("id").eq("ticker_symbol", ticker).execute()
            
            title_col, btn_col = st.columns([4, 1])
            title_col.markdown(f"### {ticker}: {company['company_name']}")
            
            if is_fav.data:
                # すでにお気に入り → 解除ボタンを表示
                if btn_col.button("⭐ 解除", key="fav_remove"):
                    supabase.table("favorites").delete().eq("ticker_symbol", ticker).execute()
                    st.rerun()
            else:
                # まだお気に入りでない → 追加ボタンを表示
                if btn_col.button("☆ 追加", key="fav_add"):
                    supabase.table("favorites").insert({"ticker_symbol": ticker}).execute()
                    st.rerun()
            
            st.markdown(f"**市場:** {company['market']} ｜ **業種:** {company['sector_33']}")
            
            price_res = supabase.table("daily_stock_prices").select("*").eq("ticker_symbol", ticker).order("trade_date", desc=True).limit(100).execute()
            price_data = price_res.data
            
            if price_data:
                latest = price_data[0]
                latest_close = latest['close_price']
                price_change = latest['price_change']
                delta_str = f"{price_change:+.1f} 円" if price_change else "±0 円"
                
                col1, col2, col3, col4 = st.columns(4)
                col1.metric(label=f"直近終値 ({latest['trade_date']})", value=f"{latest_close:,.1f} 円", delta=delta_str)
                
                # 配当利回りの表示
                div_yield = company.get('dividend_yield')
                if div_yield and div_yield > 0:
                    col2.metric(label="配当利回り", value=f"{div_yield:.2f} %", delta_color="off")
                else:
                    col2.metric(label="配当利回り", value="無配 / 未取得", delta_color="off")
                
                # 信用残高データの取得
                margin_res = supabase.table("margin_balances").select("*").eq("ticker_symbol", ticker).order("report_date", desc=True).limit(1).execute()
                if margin_res.data:
                    m_data = margin_res.data[0]
                    ratio_str = f"{m_data['margin_ratio']} 倍" if m_data.get('margin_ratio') is not None else "--- 倍"
                    col3.metric(label=f"信用倍率 ({m_data['report_date']})", value=ratio_str, delta=None)
                else:
                    col3.metric(label="信用倍率", value="データなし", delta="---")
                
                # 次回決算日の表示
                earnings_date = company.get('next_earnings_date')
                if earnings_date:
                    col4.metric(label="次回決算", value=earnings_date, delta_color="off")
                else:
                    col4.metric(label="次回決算", value="未定", delta_color="off")
                
                st.markdown("---")
                st.write("📊 **直近の株価推移**")
                
                df_prices = pd.DataFrame(price_data).sort_values("trade_date")
                fig = go.Figure(data=[go.Candlestick(
                    x=df_prices['trade_date'],
                    open=df_prices['open_price'],
                    high=df_prices['high_price'],
                    low=df_prices['low_price'],
                    close=df_prices['close_price'],
                    name="株価"
                )])
                fig.update_layout(xaxis_rangeslider_visible=False, margin=dict(l=0, r=0, t=10, b=0), height=400)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("この銘柄の株価データはまだ取得されていません。")
            
            if len(data) > 1:
                st.markdown("---")
                st.markdown("**他の検索候補:**")
                df_others = pd.DataFrame(data[1:])[['ticker_symbol', 'company_name', 'market', 'sector_33']]
                df_others.columns = ['コード', '銘柄名', '市場', '業種']
                st.dataframe(df_others, hide_index=True)

# ==========================================
# タブ2: 優待スクリーナー
# ==========================================
with tab2:
    st.subheader("🎁 株主優待スクリーナー")
    st.write("権利確定月を選んで、優待銘柄を検索します。（※現在は代表的な人気銘柄のみ登録されています）")
    
    target_month = st.selectbox("権利確定月を選択", [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12], index=2) # デフォルトは3月
    
    if st.button("優待銘柄を検索"):
        with st.spinner("データベースから優待情報を検索中..."):
            # 1. 優待テーブルから該当月のデータを取得
            ben_res = supabase.table("shareholder_benefits").select("*").eq("record_month", target_month).execute()
            
            if ben_res.data:
                df_ben = pd.DataFrame(ben_res.data)
                tickers = df_ben["ticker_symbol"].tolist()
                
                # 2. 企業情報と最新株価を取得して結合
                comp_res = supabase.table("companies").select("ticker_symbol, company_name").in_("ticker_symbol", tickers).execute()
                df_comps = pd.DataFrame(comp_res.data)
                
                # 最新の株価を取得
                latest_date_res = supabase.table("daily_stock_prices").select("trade_date").order("trade_date", desc=True).limit(1).execute()
                if latest_date_res.data:
                    latest_date = latest_date_res.data[0]["trade_date"]
                    price_res = supabase.table("daily_stock_prices").select("ticker_symbol, close_price").eq("trade_date", latest_date).in_("ticker_symbol", tickers).execute()
                    df_prices = pd.DataFrame(price_res.data)
                else:
                    df_prices = pd.DataFrame(columns=["ticker_symbol", "close_price"])
                
                # 3. すべてのデータを合体
                df_merged = pd.merge(df_ben, df_comps, on="ticker_symbol", how="left")
                df_merged = pd.merge(df_merged, df_prices, on="ticker_symbol", how="left")
                
                # 4. 「最低投資金額」を計算 (最新の株価 × 最低必要株数)
                df_merged["investment_amount"] = df_merged["close_price"] * df_merged["min_shares"]
                
                # 表示用に整理
                df_display = df_merged[["ticker_symbol", "company_name", "record_month", "benefit_summary", "min_shares", "investment_amount"]]
                df_display.columns = ["コード", "銘柄名", "権利月", "優待内容", "最低株数", "最低投資額 (目安)"]
                
                # 金額を見やすくフォーマット (例: 150000 -> 約 150,000 円)
                df_display["最低投資額 (目安)"] = df_display["最低投資額 (目安)"].apply(lambda x: f"約 {int(x):,} 円" if pd.notna(x) else "---")
                
                # 表を表示
                st.dataframe(df_display, hide_index=True, use_container_width=True)
            else:
                st.info(f"{target_month}月が権利確定の優待銘柄は見つかりませんでした。")

# ==========================================
# タブ3: スマート検索 (✨ 今回実装！)
# ==========================================
with tab3:
    st.subheader("⚡ スマート・スクリーナー")
    st.write("データベースに蓄積された最新データを分析し、条件に合う銘柄を一発抽出します。")
    
    from datetime import datetime, timedelta
    from dateutil.relativedelta import relativedelta
    
    preset = st.selectbox("検索条件を選択", [
        "🔥 本日の値上がり額 トップ30",
        "🌊 本日の出来高 トップ30",
        "📉 本日の値下がり額 トップ30",
        "🚀 本日のストップ高銘柄",
        "📅 決算発表が近い銘柄 (1週間以内)",
        "💹 踏み上げ期待！売り長銘柄 (信用倍率1倍未満)",
        "💰 5万円以下で買える！少額投資ランキング",
        "🏭 業種別 値上がりランキング",
        "🎁 優待先回り買い候補 (3ヶ月後に権利確定)",
        "🎁 優待先回り買い候補 (6ヶ月後に権利確定)",
    ])
    
    # 業種別の場合はセクター選択を表示
    selected_sector = None
    if preset == "🏭 業種別 値上がりランキング":
        sector_res = supabase.table("companies").select("sector_33").execute()
        sectors = sorted(set(r["sector_33"] for r in sector_res.data if r.get("sector_33")))
        selected_sector = st.selectbox("業種を選択", sectors)
    
    if st.button("スクリーニング実行"):
        with st.spinner("データベースでスクリーニング中..."):
            latest_date_res = supabase.table("daily_stock_prices").select("trade_date").order("trade_date", desc=True).limit(1).execute()
            
            if not latest_date_res.data:
                st.warning("株価データがまだありません。")
            else:
                latest_date = latest_date_res.data[0]["trade_date"]
                
                # ==========================================
                # 既存の3条件: 値上がり / 出来高 / 値下がり
                # ==========================================
                if preset in ["🔥 本日の値上がり額 トップ30", "🌊 本日の出来高 トップ30", "📉 本日の値下がり額 トップ30"]:
                    st.info(f"基準日: **{latest_date}** のデータでスクリーニングしました！")
                    
                    if preset == "🔥 本日の値上がり額 トップ30":
                        res = supabase.table("daily_stock_prices").select("*").eq("trade_date", latest_date).order("price_change", desc=True).limit(30).execute()
                    elif preset == "🌊 本日の出来高 トップ30":
                        res = supabase.table("daily_stock_prices").select("*").eq("trade_date", latest_date).order("volume", desc=True).limit(30).execute()
                    else:
                        res = supabase.table("daily_stock_prices").select("*").eq("trade_date", latest_date).order("price_change", desc=False).limit(30).execute()
                    
                    stock_data = res.data
                    if stock_data:
                        df_stocks = pd.DataFrame(stock_data)
                        tickers = df_stocks["ticker_symbol"].tolist()
                        comp_res = supabase.table("companies").select("ticker_symbol, company_name, market, sector_33").in_("ticker_symbol", tickers).execute()
                        df_comps = pd.DataFrame(comp_res.data)
                        if not df_comps.empty:
                            df_merged = pd.merge(df_stocks, df_comps, on="ticker_symbol", how="left")
                            df_display = df_merged[['ticker_symbol', 'company_name', 'market', 'sector_33', 'close_price', 'price_change', 'volume']]
                            df_display.columns = ['コード', '銘柄名', '市場', '業種', '終値 (円)', '前日比 (円)', '出来高']
                            st.dataframe(df_display, hide_index=True, use_container_width=True)
                
                # ==========================================
                # ストップ高銘柄
                # ==========================================
                elif preset == "🚀 本日のストップ高銘柄":
                    st.info(f"基準日: **{latest_date}**")
                    # ストップ高フラグがまだ設定されていない場合は、値上がり率が大きい銘柄で代用
                    res = supabase.table("daily_stock_prices").select("*").eq("trade_date", latest_date).order("price_change", desc=True).limit(100).execute()
                    
                    if res.data:
                        df_stocks = pd.DataFrame(res.data)
                        # 値上がり率を計算して上位を抽出（前日終値 = 終値 - 前日比）
                        df_stocks["prev_close"] = df_stocks["close_price"] - df_stocks["price_change"]
                        df_stocks["change_pct"] = (df_stocks["price_change"] / df_stocks["prev_close"] * 100).round(2)
                        # 値上がり率15%以上をストップ高相当として抽出
                        df_stop_high = df_stocks[df_stocks["change_pct"] >= 15.0]
                        
                        if df_stop_high.empty:
                            st.info("本日のストップ高銘柄はありませんでした。（値上がり率15%以上で判定）")
                        else:
                            tickers = df_stop_high["ticker_symbol"].tolist()
                            comp_res = supabase.table("companies").select("ticker_symbol, company_name, market, sector_33").in_("ticker_symbol", tickers).execute()
                            df_comps = pd.DataFrame(comp_res.data)
                            df_merged = pd.merge(df_stop_high, df_comps, on="ticker_symbol", how="left")
                            df_display = df_merged[['ticker_symbol', 'company_name', 'sector_33', 'close_price', 'price_change', 'change_pct', 'volume']]
                            df_display.columns = ['コード', '銘柄名', '業種', '終値 (円)', '前日比 (円)', '値上がり率 (%)', '出来高']
                            st.success(f"🚀 ストップ高相当（+15%以上）: **{len(df_display)}銘柄**")
                            st.dataframe(df_display, hide_index=True, use_container_width=True)
                
                # ==========================================
                # 決算発表が近い銘柄
                # ==========================================
                elif preset == "📅 決算発表が近い銘柄 (1週間以内)":
                    today = datetime.now().date()
                    one_week_later = today + timedelta(days=7)
                    
                    comp_res = supabase.table("companies").select("ticker_symbol, company_name, market, sector_33, next_earnings_date").gte("next_earnings_date", today.isoformat()).lte("next_earnings_date", one_week_later.isoformat()).order("next_earnings_date", desc=False).execute()
                    
                    if comp_res.data:
                        df_comps = pd.DataFrame(comp_res.data)
                        tickers = df_comps["ticker_symbol"].tolist()
                        
                        # 最新株価を取得
                        price_res = supabase.table("daily_stock_prices").select("ticker_symbol, close_price, price_change").eq("trade_date", latest_date).in_("ticker_symbol", tickers).execute()
                        df_prices = pd.DataFrame(price_res.data) if price_res.data else pd.DataFrame(columns=["ticker_symbol", "close_price", "price_change"])
                        
                        df_merged = pd.merge(df_comps, df_prices, on="ticker_symbol", how="left")
                        df_display = df_merged[['ticker_symbol', 'company_name', 'sector_33', 'next_earnings_date', 'close_price', 'price_change']]
                        df_display.columns = ['コード', '銘柄名', '業種', '次回決算日', '終値 (円)', '前日比 (円)']
                        
                        st.success(f"📅 1週間以内に決算発表: **{len(df_display)}銘柄**")
                        st.dataframe(df_display, hide_index=True, use_container_width=True)
                    else:
                        st.info("1週間以内に決算発表が予定されている銘柄は見つかりませんでした。")
                
                # ==========================================
                # 売り長銘柄 (信用倍率1倍未満)
                # ==========================================
                elif preset == "💹 踏み上げ期待！売り長銘柄 (信用倍率1倍未満)":
                    margin_res = supabase.table("margin_balances").select("*").lt("margin_ratio", 1.0).order("margin_ratio", desc=False).limit(50).execute()
                    
                    if margin_res.data:
                        df_margin = pd.DataFrame(margin_res.data)
                        # 各銘柄の最新データだけを残す
                        df_margin = df_margin.sort_values("report_date", ascending=False).drop_duplicates(subset="ticker_symbol", keep="first")
                        tickers = df_margin["ticker_symbol"].tolist()
                        
                        comp_res = supabase.table("companies").select("ticker_symbol, company_name, sector_33").in_("ticker_symbol", tickers).execute()
                        df_comps = pd.DataFrame(comp_res.data)
                        
                        price_res = supabase.table("daily_stock_prices").select("ticker_symbol, close_price, volume").eq("trade_date", latest_date).in_("ticker_symbol", tickers).execute()
                        df_prices = pd.DataFrame(price_res.data) if price_res.data else pd.DataFrame(columns=["ticker_symbol", "close_price", "volume"])
                        
                        df_merged = pd.merge(df_margin, df_comps, on="ticker_symbol", how="left")
                        df_merged = pd.merge(df_merged, df_prices, on="ticker_symbol", how="left")
                        df_merged = df_merged.sort_values("margin_ratio", ascending=True)
                        
                        df_display = df_merged[['ticker_symbol', 'company_name', 'sector_33', 'margin_ratio', 'margin_sell_volume', 'margin_buy_volume', 'close_price']]
                        df_display.columns = ['コード', '銘柄名', '業種', '信用倍率', '売残', '買残', '終値 (円)']
                        
                        st.success(f"💹 売り長銘柄 (倍率1倍未満): **{len(df_display)}銘柄**")
                        st.caption("信用倍率が1倍未満 ＝ 売り残が買い残を上回っている状態。株価上昇時に空売りの買い戻しが入り、さらに上がりやすい（踏み上げ相場）傾向があります。")
                        st.dataframe(df_display, hide_index=True, use_container_width=True)
                    else:
                        st.info("信用倍率1倍未満の銘柄は見つかりませんでした。")
                
                # ==========================================
                # 5万円以下で買える少額投資ランキング
                # ==========================================
                elif preset == "💰 5万円以下で買える！少額投資ランキング":
                    st.info(f"基準日: **{latest_date}** ｜ 株価500円以下 × 100株 = 投資額5万円以下")
                    # 株価500円以下で出来高が多い銘柄
                    res = supabase.table("daily_stock_prices").select("*").eq("trade_date", latest_date).lte("close_price", 500).order("volume", desc=True).limit(30).execute()
                    
                    if res.data:
                        df_stocks = pd.DataFrame(res.data)
                        df_stocks["investment"] = (df_stocks["close_price"] * 100).astype(int)
                        tickers = df_stocks["ticker_symbol"].tolist()
                        
                        comp_res = supabase.table("companies").select("ticker_symbol, company_name, sector_33").in_("ticker_symbol", tickers).execute()
                        df_comps = pd.DataFrame(comp_res.data)
                        df_merged = pd.merge(df_stocks, df_comps, on="ticker_symbol", how="left")
                        
                        df_display = df_merged[['ticker_symbol', 'company_name', 'sector_33', 'close_price', 'investment', 'price_change', 'volume']]
                        df_display.columns = ['コード', '銘柄名', '業種', '終値 (円)', '100株購入額 (円)', '前日比 (円)', '出来高']
                        st.dataframe(df_display, hide_index=True, use_container_width=True)
                    else:
                        st.info("該当する銘柄が見つかりませんでした。")
                
                # ==========================================
                # 業種別 値上がりランキング
                # ==========================================
                elif preset == "🏭 業種別 値上がりランキング":
                    if selected_sector:
                        st.info(f"基準日: **{latest_date}** ｜ 業種: **{selected_sector}**")
                        # 該当業種の銘柄コードを取得
                        sector_comp_res = supabase.table("companies").select("ticker_symbol, company_name").eq("sector_33", selected_sector).execute()
                        
                        if sector_comp_res.data:
                            sector_tickers = [r["ticker_symbol"] for r in sector_comp_res.data]
                            df_comps = pd.DataFrame(sector_comp_res.data)
                            
                            # 最新株価を取得
                            price_res = supabase.table("daily_stock_prices").select("ticker_symbol, close_price, price_change, volume").eq("trade_date", latest_date).in_("ticker_symbol", sector_tickers[:100]).execute()
                            
                            if price_res.data:
                                df_prices = pd.DataFrame(price_res.data)
                                df_merged = pd.merge(df_prices, df_comps, on="ticker_symbol", how="left")
                                df_merged = df_merged.sort_values("price_change", ascending=False).head(30)
                                
                                df_display = df_merged[['ticker_symbol', 'company_name', 'close_price', 'price_change', 'volume']]
                                df_display.columns = ['コード', '銘柄名', '終値 (円)', '前日比 (円)', '出来高']
                                st.dataframe(df_display, hide_index=True, use_container_width=True)
                
                # ==========================================
                # 優待先回り買い候補
                # ==========================================
                elif "優待先回り" in preset:
                    today = datetime.now().date()
                    months_ahead = 3 if "3ヶ月後" in preset else 6
                    target_date = today + relativedelta(months=months_ahead)
                    target_month = target_date.month
                    
                    st.info(f"今日から約{months_ahead}ヶ月後 = **{target_date.year}年{target_month}月** が権利確定の優待銘柄を検索します")
                    
                    # 該当月の優待銘柄を検索
                    ben_res = supabase.table("shareholder_benefits").select("*").eq("record_month", target_month).execute()
                    
                    if ben_res.data:
                        df_ben = pd.DataFrame(ben_res.data)
                        tickers = df_ben["ticker_symbol"].tolist()
                        
                        comp_res = supabase.table("companies").select("ticker_symbol, company_name, sector_33").in_("ticker_symbol", tickers).execute()
                        df_comps = pd.DataFrame(comp_res.data)
                        
                        price_res = supabase.table("daily_stock_prices").select("ticker_symbol, close_price, price_change").eq("trade_date", latest_date).in_("ticker_symbol", tickers).execute()
                        df_prices = pd.DataFrame(price_res.data) if price_res.data else pd.DataFrame(columns=["ticker_symbol", "close_price", "price_change"])
                        
                        df_merged = pd.merge(df_ben, df_comps, on="ticker_symbol", how="left")
                        df_merged = pd.merge(df_merged, df_prices, on="ticker_symbol", how="left")
                        df_merged["investment"] = (df_merged["close_price"] * df_merged["min_shares"]).apply(lambda x: f"約 {int(x):,} 円" if pd.notna(x) else "---")
                        
                        df_display = df_merged[['ticker_symbol', 'company_name', 'sector_33', 'record_month', 'benefit_summary', 'close_price', 'investment']]
                        df_display.columns = ['コード', '銘柄名', '業種', '権利月', '優待内容', '現在株価 (円)', '最低投資額']
                        
                        st.success(f"🎁 {target_month}月に優待権利確定: **{len(df_display)}銘柄** — 今が仕込み時！")
                        st.caption(f"優待権利確定の{months_ahead}ヶ月前から株価が上昇する傾向があります。早めの購入検討にお役立てください。")
                        st.dataframe(df_display, hide_index=True, use_container_width=True)
                    else:
                        st.info(f"{target_month}月が権利確定の優待銘柄は見つかりませんでした。")

# ==========================================
# タブ4: システム管理
# ==========================================
with tab4:
    st.subheader("⚙️ バッチ処理ステータス")
    st.write("※自動化設定後に実装されます")
