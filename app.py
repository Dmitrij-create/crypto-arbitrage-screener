import streamlit as st
import ccxt
import pandas as pd
import streamlit.components.v1 as components

# --- Инициализация состояний ---
if 'alerts' not in st.session_state:
    st.session_state['alerts'] = []
if 'triggered_alerts' not in st.session_state:
    st.session_state['triggered_alerts'] = {}

st.set_page_config(page_title="Arbitrage Spot/Futures 2026", layout="wide")

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

EXCHANGES = ['gateio', 'okx', 'mexc', 'bingx', 'bitget', 'binance'] # Добавил Binance, т.к. он популярен для Spot
BASE_CURRENCY = 'USDT'

def get_l2_price(ex_obj, symbol, side, amount_usdt):
    # (Функция L2 осталась без изменений для краткости, она работает как и раньше)
    try:
        order_book = ex_obj.fetch_order_book(symbol, 10) 
        orders = order_book['asks'] if side == 'buy' else order_book['bids']
        accum_usdt, accum_crypto = 0, 0
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

@st.cache_data(ttl=15)
def get_data(market_type_buy, market_type_sell, max_spread, min_vol, taker_fee, invest_amount):
    data = []
    prices_ex = {}
    objs = {}
    
    type_buy = 'spot' if market_type_buy == 'Spot' else 'swap'
    type_sell = 'spot' if market_type_sell == 'Spot' else 'swap'

    for ex_id in EXCHANGES:
        try:
            # Запрос спота
            ex_obj_spot = getattr(ccxt, ex_id)({'enableRateLimit': True, 'timeout': 10000, 'options': {'defaultType': 'spot'}})
            # Запрос фьючерсов
            ex_obj_swap = getattr(ccxt, ex_id)({'enableRateLimit': True, 'timeout': 10000, 'options': {'defaultType': 'swap'}})
            
            # Определяем, какой объект использовать для покупки/продажи на этой бирже
            obj_buy = ex_obj_spot if market_type_buy == 'Spot' else ex_obj_swap
            obj_sell = ex_obj_spot if market_type_sell == 'Spot' else ex_obj_swap
            
            # Получаем тикеры для нужных рынков
            tickers_buy = obj_buy.fetch_tickers()
            tickers_sell = obj_sell.fetch_tickers()

            # Фильтрация и нормализация
            cleaned_buy = {
                s.replace(f':{BASE_CURRENCY}', '').replace(f'/{BASE_CURRENCY}', ''): 
                {'bid': t['bid'], 'ask': t['ask'], 'full_sym': s, 'vol': t.get('quoteVolume') or 0}
                for s, t in tickers_buy.items() 
                if f'{BASE_CURRENCY}' in s and t.get('bid') and t.get('ask')
            }
            cleaned_sell = {
                s.replace(f':{BASE_CURRENCY}', '').replace(f'/{BASE_CURRENCY}', ''): 
                {'bid': t['bid'], 'ask': t['ask'], 'full_sym': s, 'vol': t.get('quoteVolume') or 0}
                for s, t in tickers_sell.items() 
                if f'{BASE_CURRENCY}' in s and t.get('bid') and t.get('ask')
            }

            if cleaned_buy and cleaned_sell:
                 prices_ex[ex_id] = {'buy': cleaned_buy, 'sell': cleaned_sell}
                 objs[ex_id] = {'buy': obj_buy, 'sell': obj_sell}
        except Exception as e: 
            # st.sidebar.warning(f"{ex_id}: {e}")
            continue

    all_syms = set().union(*(prices_ex[e]['buy'].keys() for e in prices_ex), *(prices_ex[e]['sell'].keys() for e in prices_ex))
    
    pre_candidates = []
    for sym in all_syms:
        buy_ex_ids = [e for e in prices_ex if sym in prices_ex[e]['buy']]
        sell_ex_ids = [e for e in prices_ex if sym in prices_ex[e]['sell']]

        if buy_ex_ids and sell_ex_ids:
            # Находим лучшие цены (ask для покупки, bid для продажи)
            buy_ex_id = min(buy_ex_ids, key=lambda x: prices_ex[x]['buy'][sym]['ask'])
            sell_ex_id = max(sell_ex_ids, key=lambda x: prices_ex[x]['sell'][sym]['bid'])
            
            p_buy = prices_ex[buy_ex_id]['buy'][sym]['ask']
            p_sell = prices_ex[sell_ex_id]['sell'][sym]['bid']
            vol = max(prices_ex[buy_ex_id]['buy'][sym]['vol'], prices_ex[sell_ex_id]['sell'][sym]['vol'])
            
            if p_sell > p_buy and vol >= min_vol:
                diff = ((p_sell - p_buy) / p_buy) * 100
                if diff <= 10 and diff >= 0: # Фильтр аномалий
                    pre_candidates.append({'sym': sym, 'buy_ex': buy_ex_id, 'sell_ex': sell_ex_id, 'diff': diff})

    # 3. Глубокий анализ L2 ТОЛЬКО для ТОП-10 кандидатов
    pre_candidates = sorted(pre_candidates, key=lambda x: x['diff'], reverse=True)[:10]
    for c in pre_candidates:
        full_buy_sym = prices_ex[c['buy_ex']]['buy'][c['sym']]['full_sym']
        full_sell_sym = prices_ex[c['sell_ex']]['sell'][c['sym']]['full_sym']
        
        p_buy_l2 = get_l2_price(objs[c['buy_ex']]['buy'], full_buy_sym, 'buy', invest_amount)
        p_sell_l2 = get_l2_price(objs[c['sell_ex']]['sell'], full_sell_sym, 'sell', invest_amount)

        if p_buy_l2 and p_sell_l2:
            net_p = (((p_sell_l2 - p_buy_l2) / p_buy_l2) * 100) - (taker_fee * 2)
            if net_p > -1: 
                data.append({
                    'Инструмент': c['sym'], 
                    'КУПИТЬ': f"{c['buy_ex'].upper()} ({market_type_buy[0]})", 
                    'ПРОДАТЬ': f"{c['sell_ex'].upper()} ({market_type_sell[0]})", 
                    'L2 Чистый %': round(net_p, 3),
                    'Профит $': round(invest_amount * (net_p / 100), 2),
                    'Цена Buy': round(p_buy_l2, 6), 'Цена Sell': round(p_sell_l2, 6)
                })
    return pd.DataFrame(data)

# --- ИНТЕРФЕЙС ---
st.title("📊 Arbitrage Screener 2026 (Spot/Futures)")

with st.sidebar:
    st.header("🔄 Тип Арбитража")
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        type_buy_input = st.selectbox("Покупка", options=['Futures', 'Spot'], index=1)
    with col_t2:
        type_sell_input = st.selectbox("Продажа", options=['Futures', 'Spot'], index=0)

    st.header("⚙️ Настройки L2")
    min_v = st.number_input("Мин. объем (USDT)", 0, 10000000, 150000)
    
    # ИСПРАВЛЕННЫЙ СПИСОК
    refresh_options = [15, 30, 60, 120]
    refresh = st.select_slider("Обновление (сек)", options=refresh_options, value=60)

    st.header("💰 Параметры сделки")
    invest = st.number_input("Сумма (USDT)", 10, 100000, 50)
    fee = st.number_input("Taker Fee %", 0.0, 0.1, 0.05, format="%.3f")

    st.header("🔔 Алерты (L2)")
    with st.form("alert_form", clear_on_submit=True):
        in_sym = st.text_input("Монета").upper()
        in_profit = st.slider("Цель L2 %", 0.0, 5.0, 1.0)
        if st.form_submit_button("➕ Добавить"):
            if in_sym:
                st.session_state.alerts.append({'sym': in_sym, 'target': in_profit, 'buy_type': type_buy_input, 'sell_type': type_sell_input})

    if st.session_state.alerts:
        st.subheader("Активные Алерты:")
        for i, a in enumerate(st.session_state.alerts):
            if st.button(f"❌ {a['sym']} {a.get('buy_type', '')[0]}/{a.get('sell_type', '')[0]} @ {a['target']}%", key=f"d_{i}"):
                st.session_state.alerts.pop(i)
                st.rerun()

autorefresh(refresh)
# Передаем типы рынков в функцию get_data
df = get_data(type_buy_input, type_sell_input, 0.4, min_v, fee, invest)

if not df.empty:
    # Проверка алертов (обновлена для учета типов рынков)
    for alert in st.session_state.alerts:
        match = df[(df['Инструмент'] == alert['sym']) & 
                   (df['L2 Чистый %'] >= alert['target']) &
                   (df['КУПИТЬ'].str.contains(f"({alert['buy_type'][0]})")) &
                   (df['ПРОДАТЬ'].str.contains(f"({alert['sell_type'][0]})"))]
        if not match.empty:
            cur_p = match['L2 Чистый %'].iloc
            play_sound()
            st.sidebar.success(f"🎯 СИГНАЛ: {alert['sym']} {cur_p}%")

    st.subheader(f"ТОП связок {type_buy_input}->{type_sell_input} (Объем: {invest} USDT)")
    st.dataframe(df.sort_values('L2 Чистый %', ascending=False), use_container_width=True)
else:
    st.info(f"Связок {type_buy_input}->{type_sell_input} с учетом ликвидности не найдено.")

st.caption(f"Обновлено: {pd.Timestamp.now().strftime('%H:%M:%S')}")
