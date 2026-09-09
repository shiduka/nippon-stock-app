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
            
            st.markdown(f"### {ticker}: {company['company_name']}")
            st.markdown(f"**市場:** {company['market']} ｜ **業種:** {company['sector_33']}")
            
            price_res = supabase.table("daily_stock_prices").select("*").eq("ticker_symbol", ticker).order("trade_date", desc=True).limit(100).execute()
            price_data = price_res.data
            
            if price_data:
                latest = price_data[0]
                latest_close = latest['close_price']
                price_change = latest['price_change']
                delta_str = f"{price_change:+.1f} 円" if price_change else "±0 円"
                
                col1, col2, col3 = st.columns(3)
                col1.metric(label=f"直近終値 ({latest['trade_date']})", value=f"{latest_close:,.1f} 円", delta=delta_str)
                
                # 信用残高データの取得
                margin_res = supabase.table("margin_balances").select("*").eq("ticker_symbol", ticker).order("report_date", desc=True).limit(1).execute()
                if margin_res.data:
                    m_data = margin_res.data[0]
                    # 倍率がNoneの場合は「計算不可」等にする
                    ratio_str = f"{m_data['margin_ratio']} 倍" if m_data.get('margin_ratio') is not None else "--- 倍"
                    col2.metric(label=f"信用倍率 (基準日:{m_data['report_date']})", value=ratio_str, delta=None)
                else:
                    col2.metric(label="信用倍率", value="データなし", delta="---")
                
                # 次回決算日の表示 (companiesテーブルから取得済み)
                earnings_date = company.get('next_earnings_date')
                if earnings_date:
                    col3.metric(label="次回決算", value=earnings_date, delta_color="off")
                else:
                    col3.metric(label="次回決算", value="未定", delta_color="off")
                
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
    st.write("データベースに蓄積された最新の株価データを分析し、条件に合う銘柄を一発抽出します。")
    
    preset = st.selectbox("検索条件を選択", [
        "🔥 本日の値上がり額 トップ30",
        "🌊 本日の出来高 トップ30",
        "📉 本日の値下がり額 トップ30"
    ])
    
    if st.button("スクリーニング実行"):
        with st.spinner("データベースでSQLを実行中..."):
            latest_date_res = supabase.table("daily_stock_prices").select("trade_date").order("trade_date", desc=True).limit(1).execute()
            
            if not latest_date_res.data:
                st.warning("株価データがまだありません。")
            else:
                latest_date = latest_date_res.data[0]["trade_date"]
                st.info(f"基準日: **{latest_date}** のデータでスクリーニングしました！")
                
                if preset == "🔥 本日の値上がり額 トップ30":
                    res = supabase.table("daily_stock_prices").select("*").eq("trade_date", latest_date).order("price_change", desc=True).limit(30).execute()
                elif preset == "🌊 本日の出来高 トップ30":
                    res = supabase.table("daily_stock_prices").select("*").eq("trade_date", latest_date).order("volume", desc=True).limit(30).execute()
                elif preset == "📉 本日の値下がり額 トップ30":
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
                    else:
                        st.warning("企業名データが見つかりませんでした。")
                else:
                    st.warning("該当する銘柄が見つかりませんでした。")

# ==========================================
# タブ4: システム管理
# ==========================================
with tab4:
    st.subheader("⚙️ バッチ処理ステータス")
    st.write("※自動化設定後に実装されます")
