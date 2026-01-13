import streamlit as st
import ccxt
import pandas as pd
import streamlit.components.v1 as components

# Инициализация состояний
if 'alerts' not in st.session_state:
    st.session_state['alerts'] = []
if 'triggered_alerts' not in st.session_state:
    st.session_state['triggered_alerts'] = {}

# Настройка страницы
st.set_page_config(page_title="Arbitrage 2026 Pro", layout="wide")

# ФУНКЦИЯ ЗВУКА: Генерация тона через JavaScript (AudioContext)
def play_sound_js():
    # Этот скрипт создает звуковую волну программно. Не требует внешних файлов.
    sound_js = """
        <script>
        var context = new (window.AudioContext || window.webkitAudioContext)();
        if (context.state === 'suspended') {
            context.resume();
        }
        var oscillator = context.createOscillator();
        var gainNode = context.createGain();
        
        oscillator.type = 'sine'; 
        oscillator.frequency.setValueAtTime(523.25, context.currentTime); // Нота До (C5)
        
        gainNode.gain.setValueAtTime(0.1, context.currentTime); // Громкость 10%
        gainNode.gain.exponentialRampToValueAtTime(0.0001, context.currentTime + 0.5);
        
        oscillator.connect(gainNode);
        gainNode.connect(context.destination);
        
        oscillator.start();
        oscillator.stop(context.currentTime + 0.5);
        </script>
    """
    components.html(sound_js, height=0)

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
                vol = t.get('quoteVolume') or 0
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
                    'Инструмент': sym, 'КУПИТЬ': buy_ex.upper(), 'ПРОДАТЬ': sell_ex.upper(), 'Профит (%)': round(diff, 3)
                })
    return pd.DataFrame(data)

# --- ИНТЕРФЕЙС ---
st.sidebar.header("⚙️ Настройки")
max_s = st.sidebar.slider("Макс. внутр. спред (%)", 0.0, 1.0, 0.3)
min_v = st.sidebar.number_input("Мин. объем (USDT)", 0, 10000000, 100000)

# Список интервалов (явно задан для избежания SyntaxError)
refresh_options = [10, 30, 60, 300]
refresh_sec = st.sidebar.select_slider("Обновление (сек)", options=refresh_options, value=30)
min_p = st.sidebar.slider("Мин. профит в таблице (%)", 0.0, 5.0, 0.5)

st.sidebar.header("🔔 Управление Алертами")
in_sym = st.sidebar.text_input("Монета (напр. BTC)", value="BTC").upper()
in_buy = st.sidebar.selectbox("Купить на", EXCHANGES, index=0)
in_sell = st.sidebar.selectbox("Продать на", EXCHANGES, index=1)
in_profit = st.sidebar.slider("Целевой профит (%)", 0.0, 5.0, 1.0, step=0.1)

if st.sidebar.button("➕ Добавить алерт"):
    alert = {'symbol': in_sym, 'buy': in_buy.upper(), 'sell': in_sell.upper(), 'target': in_profit}
    if alert not in st.session_state.alerts:
        st.session_state.alerts.append(alert)

if st.session_state.alerts:
    st.sidebar.subheader("Активные Алерты:")
    for i, a in enumerate(st.session_state.alerts):
        if st.sidebar.button(f"❌ {a['symbol']} {a['buy']}->{a['sell']} @ {a['target']}%", key=f"del_{i}"):
            st.session_state.alerts.pop(i)
            st.rerun()

autorefresh(refresh_sec)
df = get_data(max_s, min_v)

triggered_now_keys = set()
if not df.empty:
    for alert in st.session_state.alerts:
        match = df[(df['Инструмент'] == alert['symbol']) & (df['КУПИТЬ'] == alert['buy']) & (df['ПРОДАТЬ'] == alert['sell'])]
        if not match.empty:
            cur_p = match['Профит (%)'].values[0]
            alert_key = f"{alert['symbol']}_{alert['buy']}_{alert['sell']}_{alert['target']}"
            if round(cur_p, 2) >= alert['target']:
                triggered_now_keys.add(f"{alert['symbol']}|{alert['buy']}|{alert['sell']}")
                if alert_key not in st.session_state.triggered_alerts:
                    st.session_state.triggered_alerts[alert_key] = True
                    play_sound_js() # ВЫЗОВ JS ЗВУКА
                    st.toast(f"🔔 СИГНАЛ: {alert['symbol']} {cur_p}%")
            else:
                if alert_key in st.session_state.triggered_alerts:
                    del st.session_state.triggered_alerts[alert_key]

    def highlight_rows(row):
        key = f"{row['Инструмент']}|{row['КУПИТЬ']}|{row['ПРОДАТЬ']}"
        return ['background-color: #d4edda; color: #155724; font-weight: bold'] * len(row) if key in triggered_now_keys else [''] * len(row)

    st.subheader("Найденные возможности")
    display_df = df[df['Профит (%)'] >= min_p].sort_values('Профит (%)', ascending=False)
    if not display_df.empty:
        st.dataframe(display_df.style.apply(highlight_rows, axis=1), use_container_width=True)
    else:
        st.info("Нет связок выше порога.")
else:
    st.warning("Данные не получены.")

st.caption(f"Последнее обновление: {pd.Timestamp.now().strftime('%H:%M:%S')}. Не забудьте кликнуть по странице!")
