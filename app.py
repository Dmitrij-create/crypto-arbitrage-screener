import streamlit as st
import ccxt
import pandas as pd
import streamlit.components.v1 as components

# Настройка страницы
st.set_page_config(page_title="Futures Arbitrage Sound", layout="wide")

# Функция для проигрывания звука через HTML
def play_sound():
    sound_url = "www.redringtones.com"
    sound_html = f"""
        <audio autoplay>
            <source src="{sound_url}" type="audio/mp3">
        </audio>
    """
    st.components.v1.html(sound_html, height=0)

# Функция автообновления
def autorefresh(interval_seconds):
    components.html(
        f"<script>setTimeout(function() {{ window.parent.location.reload(); }}, {interval_seconds * 1000});</script>",
        height=0,
    )

EXCHANGES = ['gateio', 'okx', 'mexc', 'bingx', 'bitget']
BASE_CURRENCY = 'USDT'

@st.cache_data(ttl=10)
def get_data(max_spread, min_vol):
    data = []
    prices_by_ex = {}
    
    for ex_id in EXCHANGES:
        try:
            ex_obj = getattr(ccxt, ex_id)({'enableRateLimit': True, 'options': {'defaultType': 'swap'}})
            tickers = ex_obj.fetch_tickers()
            cleaned = {}
            for s, t in tickers.items():
                vol = t.get('quoteVolume', 0)
                if f'{BASE_CURRENCY}' in s and t.get('bid') and t.get('ask') and vol >= min_vol:
                    bid, ask = t['bid'], t['ask']
                    if ((ask - bid) / bid) * 100 <= max_spread:
                        sym = s.replace(f'/{BASE_CURRENCY}', '').replace(f':{BASE_CURRENCY}', '')
                        cleaned[sym] = {'bid': bid, 'ask': ask, 'vol': vol}
            if cleaned: prices_by_ex[ex_id] = cleaned
        except: continue

    all_syms = set().union(*(ex.keys() for ex in prices_by_ex.values()))
    for sym in all_syms:
        bids = {ex: prices_by_ex[ex][sym]['bid'] for ex in prices_by_ex if sym in prices_by_ex[ex]}
        asks = {ex: prices_by_ex[ex][sym]['ask'] for ex in prices_by_ex if sym in prices_by_ex[ex]}
        
        if len(bids) >= 2:
            buy_ex, sell_ex = min(asks, key=asks.get), max(bids, key=bids.get)
            p_buy, p_sell = asks[buy_ex], bids[sell_ex]
            diff = ((p_sell - p_buy) / p_buy) * 100
            if diff > 0:
                data.append({
                    'Инструмент': sym, 'КУПИТЬ': buy_ex.upper(), 'Цена покупки': p_buy,
                    'ПРОДАТЬ': sell_ex.upper(), 'Цена продажи': p_sell, 'Профит (%)': round(diff, 3)
                })
    return pd.DataFrame(data)

# --- ИНТЕРФЕЙС ---
st.sidebar.header("⚙️ Настройки фильтров")
max_s = st.sidebar.slider("Макс. внутр. спред (%)", 0.0, 1.0, 0.4)
min_v = st.sidebar.number_input("Мин. объем (USDT)", 0, 10000000, 100000)
refresh = st.sidebar.select_slider("Обновление (сек)", options=[10, 30, 60], value=30)
min_p = st.sidebar.slider("Мин. профит для таблицы (%)", 0.0, 3.0, 0.8)

st.sidebar.header("🔔 Звуковой сигнал (Алерт)")
alert_active = st.sidebar.checkbox("Включить звук")
target_sym = st.sidebar.text_input("Монета (напр. BTC)", "BTC").upper()
target_buy = st.sidebar.selectbox("Где купить", EXCHANGES, index=0)
target_sell = st.sidebar.selectbox("Где продать", EXCHANGES, index=1)
target_p = st.sidebar.slider("Сигнал при профите (%)", 0.0, 10.0, 1.0)

autorefresh(refresh)
df = get_data(max_s, min_v)

if not df.empty:
    # Проверка условия для звука
    if alert_active:
        match = df[
            (df['Инструмент'] == target_sym) & 
            (df['КУПИТЬ'] == target_buy.upper()) & 
            (df['ПРОДАТЬ'] == target_sell.upper()) & 
            (df['Профит (%)'] >= target_p)
        ]
        if not match.empty:
            st.sidebar.warning(f"🎯 ЦЕЛЬ ДОСТИГНУТА: {target_sym}!")
            play_sound()

    st.subheader("Актуальные связки")
    st.dataframe(df[df['Профит (%)'] >= min_p].sort_values('Профит (%)', ascending=False), use_container_width=True)
else:
    st.info("Поиск связок...")

st.caption(f"Обновлено: {pd.Timestamp.now().strftime('%H:%M:%S')}")
