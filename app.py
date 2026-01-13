import streamlit as st
import ccxt
import pandas as pd
import streamlit.components.v1 as components
import json

# Настройка страницы
st.set_page_config(page_title="Arbitrage Screener 2026", layout="wide")

# --- JS КОМПОНЕНТ ДЛЯ СОХРАНЕНИЯ АЛЕРТОВ В БРАУЗЕРЕ ---
# Этот скрипт позволяет Python общаться с localStorage браузера
def sync_alerts_js(alerts_list):
    alerts_json = json.dumps(alerts_list)
    js_code = f"""
    <script>
    // 1. Сохраняем алерты в браузер, если они пришли из Python
    var alerts = {alerts_json};
    if (alerts.length > 0) {{
        localStorage.setItem('arbitrage_alerts', JSON.stringify(alerts));
    }}
    
    // 2. Если в Python пусто, пробуем загрузить из браузера
    var stored = localStorage.getItem('arbitrage_alerts');
    if (stored && alerts.length === 0) {{
        window.parent.postMessage({{type: 'streamlit:set_alerts', data: JSON.parse(stored)}}, '*');
    }}
    </script>
    """
    components.html(js_code, height=0)

# Функция звука (ваша рабочая версия)
def play_sound():
    sound_js = """
        <script>
        var context = new (window.AudioContext || window.webkitAudioContext)();
        var oscillator = context.createOscillator();
        oscillator.type = 'sine';
        oscillator.frequency.setValueAtTime(440, context.currentTime); 
        oscillator.connect(context.destination);
        oscillator.start();
        setTimeout(function() {{ oscillator.stop(); }}, 500); 
        </script>
    """
    components.html(sound_js, height=0)

# Функция автообновления
def autorefresh(interval_seconds):
    if interval_seconds > 0:
        components.html(
            f"<script>setTimeout(function() {{ window.parent.location.reload(); }}, {interval_seconds * 1000});</script>",
            height=0,
        )

# --- Инициализация состояний ---
if 'alerts' not in st.session_state:
    st.session_state['alerts'] = []

# Синхронизация с браузером
sync_alerts_js(st.session_state['alerts'])

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
                        cleaned[sym] = {'bid': bid, 'ask': ask}
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
st.title("📊 Arbitrage Screener 2026")

with st.sidebar:
    st.header("⚙️ Настройки")
    max_s = st.slider("Макс. внутр. спред (%)", 0.0, 1.0, 0.2)
    min_v = st.number_input("Мин. объем (USDT)", 0, 10000000, 200000)
    
    refresh_opts = [10, 30, 60, 300]
    refresh = st.select_slider("Обновление (сек)", options=refresh_opts, value=60)
    min_p = st.slider("Мин. профит в таблице (%)", 0.0, 5.0, 0.8)

    st.header("🔔 Добавить Алерт")
    with st.form("alert_form", clear_on_submit=True):
        in_sym = st.text_input("Монета (напр. BTC)").upper()
        in_buy = st.selectbox("Купить на", EXCHANGES)
        in_sell = st.selectbox("Продать на", EXCHANGES, index=1)
        in_profit = st.slider("Целевой профит (%)", 0.0, 10.0, 1.0, step=0.1)
        add_btn = st.form_submit_button("➕ Добавить")
        
        if add_btn and in_sym:
            new_alert = {'symbol': in_sym, 'buy': in_buy.upper(), 'sell': in_sell.upper(), 'target': in_profit}
            if new_alert not in st.session_state.alerts:
                st.session_state.alerts.append(new_alert)
                # Принудительно сохраняем в localStorage
                st.rerun()

    if st.session_state.alerts:
        st.subheader("Активные Алерты:")
        for i, a in enumerate(st.session_state.alerts):
            col_t, col_d = st.columns([3, 1])
            col_t.caption(f"{a['symbol']} {a['buy']}->{a['sell']} @ {a['target']}%")
            if col_d.button("❌", key=f"del_{i}"):
                st.session_state.alerts.pop(i)
                # Очищаем localStorage, если удалили всё
                if not st.session_state.alerts:
                    components.html("<script>localStorage.removeItem('arbitrage_alerts');</script>", height=0)
                st.rerun()

autorefresh(refresh)
df = get_data(max_s, min_v)

triggered_now_keys = set()
if not df.empty:
    for i, alert in enumerate(st.session_state.alerts):
        match = df[(df['Инструмент'] == alert['symbol']) & (df['КУПИТЬ'] == alert['buy']) & (df['ПРОДАТЬ'] == alert['sell'])]
        if not match.empty:
            cur_p = match['Профит (%)'].values[0]
            if round(cur_p, 2) >= alert['target']:
                triggered_now_keys.add(f"{alert['symbol']}|{alert['buy']}|{alert['sell']}")
                play_sound()
                st.sidebar.success(f"🎯 СРАБОТАЛ: {alert['symbol']} {cur_p}%")

    def highlight_rows(row):
        key = f"{row['Инструмент']}|{row['КУПИТЬ']}|{row['ПРОДАТЬ']}"
        return ['background-color: #d4edda; color: #155724; font-weight: bold'] * len(row) if key in triggered_now_keys else [''] * len(row)

    st.subheader("Актуальные возможности")
    display_df = df[df['Профит (%)'] >= min_p].sort_values('Профит (%)', ascending=False)
    if not display_df.empty:
        st.dataframe(display_df.style.apply(highlight_rows, axis=1), use_container_width=True)
    else:
        st.info("Нет связок по вашим фильтрам.")

st.caption(f"Обновлено: {pd.Timestamp.now().strftime('%H:%M:%S')}")
