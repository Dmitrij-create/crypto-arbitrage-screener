import streamlit as st
import ccxt
import pandas as pd
import streamlit.components.v1 as components

st.set_page_config(page_title="Arbitrage Scanner", layout="wide")

def autorefresh(interval_seconds):
    components.html(
        f"<script>setTimeout(function() {{ window.parent.location.reload(); }}, {interval_seconds * 1000});</script>",
        height=0,
    )

# Список бирж для сканирования
EXCHANGES = ['binance', 'bybit', 'kraken', 'gateio', 'huobi']

@st.cache_data(ttl=30)
def get_data():
    data = []
    # Список популярных монет к USDT
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'ADA/USDT', 'XRP/USDT', 'DOT/USDT']
    
    # Создаем объекты бирж
    ex_objects = {}
    for ex_id in EXCHANGES:
        try:
            ex_class = getattr(ccxt, ex_id)
            ex_objects[ex_id] = ex_class({'enableRateLimit': True})
        except:
            continue

    progress_bar = st.progress(0)
    
    for i, symbol in enumerate(symbols):
        prices = {}
        for ex_id, ex_obj in ex_objects.items():
            try:
                ticker = ex_obj.fetch_ticker(symbol)
                if ticker and 'last' in ticker:
                    prices[ex_id] = ticker['last']
            except:
                continue
        
        if len(prices) >= 2:
            min_ex = min(prices, key=prices.get)
            max_ex = max(prices, key=prices.get)
            min_p = prices[min_ex]
            max_p = prices[max_ex]
            diff = ((max_p - min_p) / min_p) * 100
            
            if diff > 0:
                data.append({
                    'Монета': symbol,
                    'Купить на': min_ex.upper(),
                    'Цена покупки': f"{min_p:,.4f}",
                    'Продать на': max_ex.upper(),
                    'Цена продажи': f"{max_p:,.4f}",
                    'Профит (%)': round(diff, 3)
                })
        progress_bar.progress((i + 1) / len(symbols))
    
    progress_bar.empty()
    return pd.DataFrame(data)

st.title("🚀 Crypto Arbitrage Scanner (CCXT)")

# Настройки в боковой панели
refresh_sec = st.sidebar.select_slider("Обновление (сек)", options=[30, 60, 120, 300], value=60)
min_profit = st.sidebar.slider("Мин. профит (%)", 0.0, 2.0, 0.1)

if refresh_sec > 0:
    autorefresh(refresh_sec)

try:
    df = get_data()
    if not df.empty:
        filtered_df = df[df['Профит (%)'] >= min_profit]
        st.table(filtered_df.sort_values('Профит (%)', ascending=False))
    else:
        st.warning("Биржи временно недоступны или нет данных.")
except Exception as e:
    st.error(f"Ошибка: {e}")

st.caption(f"Последнее обновление: {pd.Timestamp.now().strftime('%H:%M:%S')}")
