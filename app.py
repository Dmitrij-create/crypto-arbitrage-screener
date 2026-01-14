import streamlit as st
import ccxt
import pandas as pd
import streamlit.components.v1 as components

# --- Инициализация состояний ---
if 'alerts' not in st.session_state:
    st.session_state['alerts'] = []

st.set_page_config(page_title="Arbitrage L2 Fast 2026", layout="wide")

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
    """Быстрый расчет цены исполнения L2"""
    try:
        # Устанавливаем короткий таймаут для стакана, чтобы не вешать скрипт
        order_book = ex_obj.fetch_order_book(symbol, 10) 
        orders = order_book['asks'] if side == 'buy' else order_book['bids']
        
        accum_usdt = 0
        accum_crypto = 0
        for price, amount in orders:
            vol_usdt = price * amount
            if accum_usdt + vol_usdt >= amount_usdt:
                needed = amount_usdt - accum_usdt
                accum_crypto += needed / price
                return amount_usdt / accum_crypto
            accum_crypto += amount
            accum_usdt += vol_usdt
        return None
    except:
        return None

@st.cache_data(ttl=15) # Увеличили кэш для стабильности
def get_data(max_spread, min_vol, taker_fee, invest_amount):
    data = []
    prices_ex = {}
    objs = {}

    # 1. Быстрый сбор тикеров (один запрос на биржу)
    for ex_id in EXCHANGES:
        try:
            ex_obj = getattr(ccxt, ex_id)({
                'enableRateLimit': True, 
                'timeout': 10000,
                'options': {'defaultType': 'swap'}
            })
            objs[ex_id] = ex_obj
            tickers = ex_obj.fetch_tickers()
            cleaned = {
                s.replace(f':{BASE_CURRENCY}', '').replace(f'/{BASE_CURRENCY}', ''): 
                {'bid': t['bid'], 'ask': t['ask'], 'full_sym': s, 'vol': t.get('quoteVolume') or 0}
                for s, t in tickers.items() 
                if f'{BASE_CURRENCY}' in s and t.get('bid') and t.get('ask')
            }
            if cleaned: prices_ex[ex_id] = cleaned
        except: continue

    # 2. Предварительный отбор лучших связок по тикерам
    pre_candidates = []
    all_syms = set().union(*(ex.keys() for ex in prices_ex.values()))
    for sym in all_syms:
        ex_with_sym = [ex for ex in prices_ex if sym in prices_ex[ex]]
        if len(ex_with_sym) >= 2:
            buy_ex = min(ex_with_sym, key=lambda x: prices_ex[x][sym]['ask'])
            sell_ex = max(ex_with_sym, key=lambda x: prices_ex[x][sym]['bid'])
            p_buy = prices_ex[buy_ex][sym]['ask']
            p_sell = prices_ex[sell_ex][sym]['bid']
            vol = max(prices_ex[ex][sym]['vol'] for ex in ex_with_sym)
            
            if p_sell > p_buy and vol >= min_vol:
                diff = ((p_sell - p_buy) / p_buy) * 100
                if diff <= 10: # Фильтр аномалий > 10% (обычно ошибки API)
                    pre_candidates.append({'sym': sym, 'buy_ex': buy_ex, 'sell_ex': sell_ex, 'diff': diff})

    # 3. Глубокий анализ L2 ТОЛЬКО для ТОП-10 кандидатов (чтобы не зависало)
    pre_candidates = sorted(pre_candidates, key=lambda x: x['diff'], reverse=True)[:10]

    for c in pre_candidates:
        sym = c['sym']
        full_buy_sym = prices_ex[c['buy_ex']][sym]['full_sym']
        full_sell_sym = prices_ex[c['sell_ex']][sym]['full_sym']
        
        p_buy_l2 = get_l2_price(objs[c['buy_ex']], full_buy_sym, 'buy', invest_amount)
        p_sell_l2 = get_l2_price(objs[c['sell_ex']], full_sell_sym, 'sell', invest_amount)

        if p_buy_l2 and p_sell_l2:
            net_p = (((p_sell_l2 - p_buy_l2) / p_buy_l2) * 100) - (taker_fee * 2)
            data.append({
                'Инструмент': sym, 
                'КУПИТЬ': c['buy_ex'].upper(), 'ПРОДАТЬ': c['sell_ex'].upper(), 
                'L2 Чистый %': round(net_p, 3),
                'Профит $': round(invest_amount * (net_p / 100), 2),
                'L2 Buy': round(p_buy_l2, 6), 'L2 Sell': round(p_sell_l2, 6)
            })
    return pd.DataFrame(data)

# --- ИНТЕРФЕЙС ---
st.sidebar.header("⚙️ Оптимизированный L2")
min_v = st.sidebar.number_input("Мин. объем (USDT)", 0, 10000000, 150000)
refresh_options = [15, 30, 60, 120] # Исправлено
refresh = st.sidebar.select_slider("Обновление (сек)", options=refresh_options, value=60)

st.sidebar.header("💰 Параметры сделки")
invest = st.sidebar.number_input("Сумма (USDT)", 10, 100000, 100)
fee = st.sidebar.number_input("Taker Fee %", 0.0, 0.1, 0.05, format="%.3f")

# Алерты
with st.sidebar.form("alert_form"):
    in_sym = st.text_input("Монета").upper()
    in_profit = st.slider("Цель L2 %", 0.0, 5.0, 1.0)
    if st.form_submit_button("➕ Добавить"):
        if in_sym: st.session_state.alerts.append({'sym': in_sym, 'target': in_profit})

for i, a in enumerate(st.session_state.alerts):
    if st.sidebar.button(f"❌ {a['sym']} {a['target']}%", key=f"d_{i}"):
        st.session_state.alerts.pop(i)
        st.rerun()

autorefresh(refresh)
st.info("⌛ Сканирование рынка и стаканов ТОП-10 пар...")

df = get_data(0.4, min_v, fee, invest)

if not df.empty:
    # Проверка алертов
    for alert in st.session_state.alerts:
        match = df[(df['Инструмент'] == alert['sym']) & (df['L2 Чистый %'] >= alert['target'])]
        if not match.empty:
            play_sound()
            st.sidebar.success(f"🎯 СИГНАЛ: {alert['sym']} {match['L2 Чистый %'].iloc[0]}%")

    st.subheader(f"ТОП связок с учетом ликвидности на {invest} USDT")
    st.dataframe(df.sort_values('L2 Чистый %', ascending=False), use_container_width=True)
else:
    st.warning("Выгодных связок с учетом ликвидности не найдено. Попробуйте уменьшить сумму сделки.")

st.caption(f"Обновлено в 2026 году: {pd.Timestamp.now().strftime('%H:%M:%S')}")
