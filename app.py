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
    if not url or not key:
        st.error("エラー: .env に接続情報がありません")
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
# タブ1: 個別銘柄詳細 (✨チャート機能追加！)
# ==========================================
with tab1:
    st.subheader("🔍 銘柄の検索・分析")
    search_query = st.text_input("銘柄コードまたは企業名で検索", placeholder="例: 7203 または トヨタ")
    
    if search_query:
        # Supabaseから企業検索
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
            
            # --- ✨ 株価データの取得とチャート表示 ---
            # 降順（新しい順）で直近の株価をDBから取得
            price_res = supabase.table("daily_stock_prices").select("*").eq("ticker_symbol", ticker).order("trade_date", desc=True).limit(100).execute()
            price_data = price_res.data
            
            if price_data:
                # 最新の日のデータを取り出す
                latest = price_data[0]
                latest_close = latest['close_price']
                price_change = latest['price_change']
                
                # 前日比の表示用文字列（プラスなら+、マイナスなら-をつける）
                delta_str = f"{price_change:+.1f} 円" if price_change else "±0 円"
                
                # 数値のハイライト表示
                col1, col2, col3 = st.columns(3)
                col1.metric(label=f"直近終値 ({latest['trade_date']})", value=f"{latest_close:,.1f} 円", delta=delta_str)
                col2.metric(label="信用倍率 (※準備中)", value="--- 倍", delta="---")
                col3.metric(label="次回決算 (※準備中)", value="未定", delta_color="off")
                
                st.markdown("---")
                st.write("📊 **直近の株価推移**")
                
                # グラフ描画用に、古い日付順に並び替え
                df_prices = pd.DataFrame(price_data).sort_values("trade_date")
                
                # Plotlyによる美しいローソク足チャートの生成
                fig = go.Figure(data=[go.Candlestick(
                    x=df_prices['trade_date'],
                    open=df_prices['open_price'],
                    high=df_prices['high_price'],
                    low=df_prices['low_price'],
                    close=df_prices['close_price'],
                    name="株価"
                )])
                # 見やすさのためのレイアウト調整
                fig.update_layout(xaxis_rangeslider_visible=False, margin=dict(l=0, r=0, t=10, b=0), height=400)
                
                st.plotly_chart(fig, use_container_width=True)
                
            else:
                st.warning("この銘柄の株価データはまだ取得されていません。（バッチ実行をお待ちください）")
            
            # 他の検索候補
            if len(data) > 1:
                st.markdown("---")
                st.markdown("**他の検索候補:**")
                df_others = pd.DataFrame(data[1:])[['ticker_symbol', 'company_name', 'market', 'sector_33']]
                df_others.columns = ['コード', '銘柄名', '市場', '業種']
                st.dataframe(df_others, hide_index=True)

# ==========================================
# 以下のタブはダミーのまま
# ==========================================
with tab2:
    st.subheader("🎁 株主優待から探す")
    st.write("※優待バッチ完成後に実装されます")

with tab3:
    st.subheader("⚡ プリセット条件で一発検索")
    st.write("※株価や信用残高バッチ完成後に実装されます")

with tab4:
    st.subheader("⚙️ バッチ処理ステータス")
    st.write("※自動化設定後に実装されます")
