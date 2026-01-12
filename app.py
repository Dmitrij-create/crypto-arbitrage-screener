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

def play_sound():
    sound_js = """
        <script>
        var context = new (window.AudioContext || window.webkitAudioContext)();
        var oscillator = context.createOscillator();
        oscillator.type = 'sine';
        oscillator.frequency.setValueAtTime(523.25, context.currentTime); // Нота До
        oscillator.connect(context.destination);
        oscillator.start();
        setTimeout(function() { oscillator.stop(); }, 400);
        </script>
    """
    components.html(sound_js, height=0)

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
                if f'{BASE_CURRENCY}' in s and t.get('bid') and t.get('ask') and vol >= min_vol:
                    bid, ask = t['bid'], t['ask']
                    if bid > 0 and ((ask - bid) / bid) * 100 <= max_spread:
                        sym = s.split(':')[0].split('/')[0]
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
                    'Инструмент': sym, 'КУПИТЬ': buy_ex.upper(), 'Цена покупки': p_buy,
                    'ПРОДАТЬ': sell_ex.upper(), 'Цена продажи': p_sell, 'Профит (%)': round(diff, 3)
                })
    return pd.DataFrame(data)

# --- ИНТЕРФЕЙС ---
st.title("📊 Arbitrage Screener 2026")

with st.sidebar:
    st.header("⚙️ Настройки")
    max_s = st.slider("Макс. внутр. спред (%)", 0.0, 1.0, 0.4)
    min_v = st.number_input("Мин. объем (USDT)", 0, 10000000, 100000)
    refresh = st.select_slider("Обновление (сек)", options=[10, 30, 60, 300], value=60)
    min_p = st.slider("Мин. профит в таблице (%)", 0.0, 10.0, 0.5)

    st.header("🔔 Алерты")
    in_sym = st.text_input("Монета", value="BTC").upper()
    in_buy = st.selectbox("Купить на", EXCHANGES, index=0)
    in_sell = st.selectbox("Продать на", EXCHANGES, index=1)
    in_profit = st.slider("Целевой профит (%)", 0.0, 10.0, 1.0, step=0.1)
    
    if st.button("➕ Добавить"):
        alert = {'symbol': in_sym, 'buy': in_buy.upper(), 'sell': in_sell.upper(), 'target': in_profit}
        if alert not in st.session_state.alerts:
            st.session_state.alerts.append(alert)

    for i, a in enumerate(st.session_state.alerts):
        st.caption(f"{a['symbol']} {a['buy']}->{a['sell']} @ {a['target']}%")
        if st.button(f"Удалить {i}", key=f"del_{i}"):
            st.session_state.alerts.pop(i)
            st.rerun()

autorefresh(refresh)
df = get_data(max_s, min_v)

# Логика алертов и визуализации
triggered_now = []
if not df.empty:
    for alert in st.session_state.alerts:
        match = df[(df['Инструмент'] == alert['symbol']) & (df['КУПИТЬ'] == alert['buy']) & (df['ПРОДАТЬ'] == alert['sell'])]
        if not match.empty:
            cur_p = match['Профит (%)'].iloc[0]
            alert_key = f"{alert['symbol']}_{alert['buy']}_{alert['sell']}_{alert['target']}"
            
            # Точное срабатывание: пересечение границы
            if round(cur_p, 2) >= alert['target']:
                triggered_now.append(alert) # Для подсветки в таблице
                if alert_key not in st.session_state.triggered_alerts:
                    st.toast(f"🎯 ЦЕЛЬ: {alert['symbol']} {cur_p}%", icon="🔔")
                    st.session_state.triggered_alerts[alert_key] = True
                    play_sound()
            else:
                if alert_key in st.session_state.triggered_alerts:
                    del st.session_state.triggered_alerts[alert_key]

    # Функция для стилизации (визуальный индикатор)
    def highlight_alerts(row):
        for t in triggered_now:
            if row['Инструмент'] == t['symbol'] and row['КУПИТЬ'] == t['buy'] and row['ПРОДАТЬ'] == t['sell']:
                return ['background-color: #d4edda; color: #155724; font-weight: bold'] * len(row)
        return [''] * len(row)

    st.subheader("Найденные возможности")
    display_df = df[df['Профит (%)'] >= min_p].sort_values('Профит (%)', ascending=False)
    
    if not display_df.empty:
        st.dataframe(display_df.style.apply(highlight_alerts, axis=1), use_container_width=True)
    else:
        st.info("Нет монет, подходящих под фильтр профита.")
else:
    st.warning("Данные не получены. Проверьте подключение.")

st.caption(f"Последнее обновление: {pd.Timestamp.now().strftime('%H:%M:%S')}")
