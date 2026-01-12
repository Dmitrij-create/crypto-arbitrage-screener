import streamlit as st
import ccxt
import pandas as pd
import streamlit.components.v1 as components

# Инициализация состояний
if 'alerts' not in st.session_state:
    st.session_state['alerts'] = []
if 'triggered_alerts' not in st.session_state:
    st.session_state['triggered_alerts'] = {}

st.set_page_config(page_title="Arbitrage 2026 Pro", layout="wide")

# ФУНКЦИЯ ЗВУКА: максимально простая и надежная версия через HTML audio tag
def play_sound_html():
    # Используем очень короткий и простой MP3 файл
    sound_url = "www.soundjay.com"
    sound_html = f"""
        <audio autoplay controls style="display:none;">
            <source src="{sound_url}" type="audio/mp3">
        </audio>
    """
    st.components.v1.html(sound_html, height=0)


# Функция автообновления
def autorefresh(interval_seconds):
    components.html(f"<script>setTimeout(function() {{ window.parent.location.reload(); }}, {interval_seconds * 1000});</script>", height=0)

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
                vol = t.get('quoteVolume') or 0
                # Нормализуем символ для сравнения (убираем :USDT или /USDT)
                if f'{BASE_CURRENCY}' in s and t.get('bid') and t.get('ask') and vol >= min_vol:
                    bid, ask = t['bid'], t['ask']
                    if bid > 0 and ((ask - bid) / bid) * 100 <= max_spread:
                        sym = s.replace(f':{BASE_CURRENCY}', '').replace(f'/{BASE_CURRENCY}', '')
                        cleaned[sym] = {'bid': bid, 'ask': ask, 'vol': vol}
            if cleaned: prices_by_ex[ex_id] = cleaned
        except: continue

    all_syms = set().union(*(ex.keys() for ex in prices_by_ex.values()))
    for sym in all_syms:
        ex_with_sym = [ex for ex in prices_by_ex if sym in prices_by_ex[ex]]
        if len(ex_with_sym) >= 2:
            bids = {ex: prices_by_ex[ex][sym]['bid'] for ex in ex_with_sym}
            asks = {ex: prices_by_ex[ex][sym]['ask'] for ex in ex_with_sym}
            buy_ex, sell_ex = min(asks, key=asks.get), max(bids, key=bids.get)
            p_buy, p_sell = asks[buy_ex], bids[sell_ex]
            if p_sell > p_buy:
                diff = ((p_sell - p_buy) / p_buy) * 100
                data.append({
                    'Инструмент': sym, 'КУПИТЬ': buy_ex.upper(), 'ПРОДАТЬ': sell_ex.upper(), 
                    'Профит (%)': round(diff, 3) # Упростил столбцы для ясности сравнения
                })
    return pd.DataFrame(data)

# --- ИНТЕРФЕЙС ---
st.title("📊 Arbitrage Screener 2026")

with st.sidebar:
    st.header("⚙️ Настройки")
    max_s = st.slider("Макс. внутр. спред (%)", 0.0, 1.0, 0.3)
    min_v = st.number_input("Мин. объем (USDT)", 0, 10000000, 100000)
    refresh = st.select_slider("Обновление (сек)", options=, value=30)
    min_p = st.slider("Мин. профит в таблице (%)", 0.0, 5.0, 0.5)

    st.header("🔔 Управление Алертами")
    in_sym = st.text_input("Монета", value="ETH").upper()
    in_buy = st.selectbox("Купить на", EXCHANGES, index=0)
    in_sell = st.selectbox("Продать на", EXCHANGES, index=1)
    in_profit = st.slider("Целевой профит (%)", 0.0, 5.0, 1.0, step=0.1)
    
    if st.button("➕ Добавить"):
        alert = {'symbol': in_sym, 'buy': in_buy.upper(), 'sell': in_sell.upper(), 'target': in_profit}
        if alert not in st.session_state.alerts:
            st.session_state.alerts.append(alert)
        # st.rerun() # Убираем, чтобы не мешать звуку

    st.subheader("Активные Алерты:")
    for i, a in enumerate(st.session_state.alerts):
        col_a, col_b = st.columns([3, 1])
        col_a.caption(f"{a['symbol']} {a['buy']}->{a['sell']} > {a['target']}%")
        if col_b.button("❌", key=f"del_{i}"):
            st.session_state.alerts.pop(i)
            st.experimental_rerun() # st.rerun() здесь нужен только для обновления сайдбара

autorefresh(refresh)
df = get_data(max_s, min_v)

# Логика алертов и визуализации
triggered_now_symbols = set()
if not df.empty:
    for alert in st.session_state.alerts:
        # Проверяем совпадение по всем трем параметрам
        match = df[
            (df['Инструмент'] == alert['symbol']) & 
            (df['КУПИТЬ'] == alert['buy']) & 
            (df['ПРОДАТЬ'] == alert['sell'])
        ]
        
        if not match.empty:
            cur_p = match['Профит (%)'].iloc[0] # Получаем текущий профит
            alert_key = f"{alert['symbol']}_{alert['buy']}_{alert['sell']}_{alert['target']}"
            
            # Если цель достигнута или превышена
            if round(cur_p, 2) >= alert['target']:
                triggered_now_symbols.add(f"{alert['symbol']}{alert['buy']}{alert['sell']}") # Добавляем ключ для подсветки
                if alert_key not in st.session_state.triggered_alerts:
                    st.session_state.triggered_alerts[alert_key] = True
                    play_sound_html() # Запускаем звук
                    st.sidebar.warning(f"🎯 СИГНАЛ: {alert['symbol']} {cur_p}%")
            else:
                # Если упало ниже цели, сбрасываем флаг для повторного триггера
                if alert_key in st.session_state.triggered_alerts:
                    del st.session_state.triggered_alerts[alert_key]

    # Функция стилизации таблицы
    def highlight_alerts(row):
        row_key = f"{row['Инструмент']}{row['КУПИТЬ']}{row['ПРОДАТЬ']}"
        if row_key in triggered_now_symbols:
            return ['background-color: #d4edda; color: #155724; font-weight: bold'] * len(row)
        return [''] * len(row)

    st.subheader("Найденные возможности")
    display_df = df[df['Профит (%)'] >= min_p].sort_values('Профит (%)', ascending=False)
    
    if not display_df.empty:
        # Применяем стиль
        st.dataframe(display_df.style.apply(highlight_alerts, axis=1), use_container_width=True)
    else:
        st.info("Нет монет, подходящих под фильтр профита.")
else:
    st.warning("Данные не получены. Проверьте подключение.")

st.caption(f"Последнее обновление: {pd.Timestamp.now().strftime('%H:%M:%S')}")
