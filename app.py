import streamlit as st
import ccxt
import pandas as pd
import streamlit.components.v1 as components

# --- Инициализация состояний ---
if 'alerts' not in st.session_state:
    st.session_state['alerts'] = []
if 'triggered_alerts' not in st.session_state:
    st.session_state['triggered_alerts'] = {}

st.set_page_config(page_title="Arbitrage L2 Screener 2026", layout="wide")

def play_sound():
    sound_js = """
        <script>
        var context = new (window.AudioContext || window.webkitAudioContext)();
        var oscillator = context.createOscillator();
        oscillator.type = 'sine';
        oscillator.frequency.setValueAtTime(440, context.currentTime); 
        oscillator.connect(context.destination);
        oscillator.start();
        setTimeout(function() { oscillator.stop(); }, 500); 
        </script>
    """
    components.html(sound_js, height=0)

def autorefresh(interval_seconds):
    if interval_seconds > 0:
        components.html(
            f"<script>setTimeout(function() {{ window.parent.location.reload(); }}, {interval_seconds * 1000});</script>",
            height=0,
        )

EXCHANGES = ['gateio', 'okx', 'mexc', 'bingx', 'bitget']
BASE_CURRENCY = 'USDT'

def get_l2_price(ex_obj, symbol, side, amount_usdt):
    """Рассчитывает среднюю цену исполнения для заданного объема в USDT"""
    try:
        limit = 20
        order_book = ex_obj.fetch_order_book(symbol, limit)
        orders = order_book['asks'] if side == 'buy' else order_book['bids']
        
        accumulated_usdt = 0
        accumulated_crypto = 0
        
        for price, amount in orders:
            order_usdt = price * amount
            if accumulated_usdt + order_usdt >= amount_usdt:
                needed_usdt = amount_usdt - accumulated_usdt
                accumulated_crypto += needed_usdt / price
                accumulated_usdt += needed_usdt
                break
            else:
                accumulated_crypto += amount
                accumulated_usdt += order_usdt
        
        if accumulated_usdt < amount_usdt: # Недостаточно ликвидности в стакане
            return None
        return accumulated_usdt / accumulated_crypto
    except:
        return None

@st.cache_data(ttl=10)
def get_data(max_spread, min_vol, taker_fee_percent, investment_amount):
    data = []
    prices_ex = {}
    objs = {}

    # 1. Быстрый сбор тикеров для фильтрации
    for ex_id in EXCHANGES:
        try:
            ex_obj = getattr(ccxt, ex_id)({'enableRateLimit': True, 'options': {'defaultType': 'swap'}})
            objs[ex_id] = ex_obj
            tickers = ex_obj.fetch_tickers()
            cleaned = {}
            for s, t in tickers.items():
                vol = t.get('quoteVolume') or 0
                if f'{BASE_CURRENCY}' in s and t.get('bid') and t.get('ask') and vol >= min_vol:
                    sym = s.replace(f':{BASE_CURRENCY}', '').replace(f'/{BASE_CURRENCY}', '')
                    cleaned[sym] = {'bid': t['bid'], 'ask': t['ask'], 'full_sym': s}
            if cleaned: prices_ex[ex_id] = cleaned
        except: continue

    # 2. Анализ пересечений и L2 стакана
    all_syms = set().union(*(ex.keys() for ex in prices_ex.values()))
    for sym in all_syms:
        ex_with_sym = [ex for ex in prices_ex if sym in prices_ex[ex]]
        if len(ex_with_sym) >= 2:
            # Предварительный отбор по лучшим ценам
            bids_best = {ex: prices_ex[ex][sym]['bid'] for ex in ex_with_sym}
            asks_best = {ex: prices_by_ex[ex][sym]['ask'] for ex in ex_with_sym if sym in prices_ex[ex]} # Fix
            
            # Для упрощения берем лучшую биржу покупки и продажи по тикерам
            buy_ex_id = min(ex_with_sym, key=lambda x: prices_ex[x][sym]['ask'])
            sell_ex_id = max(ex_with_sym, key=lambda x: prices_ex[x][sym]['bid'])
            
            # 3. Глубокий анализ стакана для выбранной пары (L2)
            p_buy_l2 = get_l2_price(objs[buy_ex_id], prices_ex[buy_ex_id][sym]['full_sym'], 'buy', investment_amount)
            p_sell_l2 = get_l2_price(objs[sell_ex_id], prices_ex[sell_ex_id][sym]['full_sym'], 'sell', investment_amount)

            if p_buy_l2 and p_sell_l2 and p_sell_l2 > p_buy_l2:
                gross_profit = ((p_sell_l2 - p_buy_l2) / p_buy_l2) * 100
                total_fee_rate = (taker_fee_percent / 100) * 2 
                net_profit_percent = gross_profit - total_fee_rate
                
                if net_profit_percent > -1: # Показываем даже небольшие минусы после L2 для анализа
                    data.append({
                        'Инструмент': sym, 
                        'КУПИТЬ': buy_ex_id.upper(), 
                        'ПРОДАТЬ': sell_ex_id.upper(), 
                        'L2 Чистый %': round(net_profit_percent, 3),
                        'Профит $': round(investment_amount * (net_profit_percent / 100), 2),
                        'Цена L2 Buy': round(p_buy_l2, 6),
                        'Цена L2 Sell': round(p_sell_l2, 6)
                    })
    return pd.DataFrame(data)

# --- ИНТЕРФЕЙС ---
st.sidebar.header("⚙️ Настройки L2")
max_s = st.sidebar.slider("Макс. внутр. спред (%)", 0.0, 1.0, 0.4)
min_v = st.sidebar.number_input("Мин. объем (USDT)", 0, 10000000, 100000)

# Явное указание значений
refresh_opts = [10, 30, 60, 120]
refresh = st.sidebar.select_slider("Обновление (сек)", options=refresh_opts, value=60)

st.sidebar.header("💰 Депозит для анализа стакана")
invest = st.sidebar.number_input("Объем сделки (USDT)", 10, 50000, 100)
fee = st.sidebar.number_input("Taker Fee %", 0.0, 0.1, 0.05, step=0.005, format="%.3f")

st.sidebar.header("🔔 Алерты")
with st.sidebar.form("alert_form", clear_on_submit=True):
    in_sym = st.text_input("Монета").upper()
    in_buy = st.selectbox("Купить на", EXCHANGES)
    in_sell = st.selectbox("Продать на", EXCHANGES, index=1)
    in_profit = st.slider("Цель L2 %", 0.0, 5.0, 1.0, step=0.1)
    if st.form_submit_button("➕ Добавить"):
        if in_sym:
            st.session_state.alerts.append({'sym': in_sym, 'buy': in_buy.upper(), 'sell': in_sell.upper(), 'target': in_profit})

# Удаление алертов
for i, a in enumerate(st.session_state.alerts):
    if st.sidebar.button(f"❌ {a['sym']} {a['target']}%", key=f"d_{i}"):
        st.session_state.alerts.pop(i)
        st.rerun()

autorefresh(refresh)
df = get_data(max_s, min_v, fee, invest)

if not df.empty:
    # Логика алертов
    for alert in st.session_state.alerts:
        match = df[(df['Инструмент'] == alert['sym']) & (df['КУПИТЬ'] == alert['buy']) & (df['ПРОДАТЬ'] == alert['sell'])]
        if not match.empty:
            cur_p = match['L2 Чистый %'].iloc[0]
            if cur_p >= alert['target']:
                play_sound()
                st.sidebar.success(f"🎯 L2 СИГНАЛ: {alert['sym']} {cur_p}%")

    st.subheader(f"Результаты анализа стакана (Depth: {invest} USDT)")
    st.dataframe(df.sort_values('L2 Чистый %', ascending=False), use_container_width=True)
else:
    st.info("Связок с учетом глубины стакана не найдено.")

st.caption(f"Обновлено: {pd.Timestamp.now().strftime('%H:%M:%S')}")
``` [1, 2]
