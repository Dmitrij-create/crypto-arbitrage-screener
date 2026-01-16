import streamlit as st
import ccxt
import pandas as pd
import streamlit.components.v1 as components

# --- Инициализация состояний ---
if 'alerts' not in st.session_state:
    st.session_state['alerts'] = []

st.set_page_config(page_title="Arbitrage Pro 2026", layout="wide")

# Функция звука (JS AudioContext)
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

# Функция автообновления
def autorefresh(interval_seconds):
    if interval_seconds > 0:
        components.html(
            f"<script>setTimeout(function() {{ window.parent.location.reload(); }}, {interval_seconds * 1000});</script>",
            height=0,
        )

EXCHANGES = ['binance', 'okx', 'bybit', 'mexc', 'gateio', 'bitget']
BASE_CURRENCY = 'USDT'

def get_l2_price(ex_obj, symbol, side, amount_usdt):
    """Рассчитывает цену исполнения для конкретного объема (L2)"""
    try:
        order_book = ex_obj.fetch_order_book(symbol, 10)
        orders = order_book['asks'] if side == 'buy' else order_book['bids']
        accum_usdt, accum_crypto = 0, 0
        for price, amount in orders:
            vol = price * amount
            if accum_usdt + vol >= amount_usdt:
                needed = amount_usdt - accum_usdt
                accum_crypto += needed / price
                return amount_usdt / accum_crypto
            accum_crypto += amount
            accum_usdt += vol
        return None
    except: return None

@st.cache_data(ttl=15)
def get_data(min_vol, taker_fee, invest_amount):
    data = []
    prices_ex = {}
    objs = {}

    # 1. Сбор тикеров
    for ex_id in EXCHANGES:
        try:
            ex_obj = getattr(ccxt, ex_id)({'enableRateLimit': True, 'timeout': 7000})
            objs[ex_id] = ex_obj
            tickers = ex_obj.fetch_tickers()
            cleaned = {
                s.replace(f'/{BASE_CURRENCY}', '').replace(f':{BASE_CURRENCY}', ''): 
                {'bid': t['bid'], 'ask': t['ask'], 'full_sym': s, 'vol': t.get('quoteVolume') or 0}
                for s, t in tickers.items() if BASE_CURRENCY in s and t.get('bid') and t.get('ask')
            }
            if cleaned: prices_ex[ex_id] = cleaned
        except: continue

    # 2. Предварительный поиск связок
    pre_candidates = []
    all_syms = set().union(*(ex.keys() for ex in prices_ex.values()))
    for sym in all_syms:
        ex_with_sym = [ex for ex in prices_ex if sym in prices_ex[ex]]
        if len(ex_with_sym) >= 2:
            buy_ex = min(ex_with_sym, key=lambda x: prices_ex[x][sym]['ask'])
            sell_ex = max(ex_with_sym, key=lambda x: prices_ex[x][sym]['bid'])
            p_buy, p_sell = prices_ex[buy_ex][sym]['ask'], prices_ex[sell_ex][sym]['bid']
            vol = max(prices_ex[ex][sym]['vol'] for ex in ex_with_sym)
            
            if p_sell > p_buy and vol >= min_vol:
                diff = ((p_sell - p_buy) / p_buy) * 100
                if 0.1 < diff < 15:
                    pre_candidates.append({'sym': sym, 'buy_ex': buy_ex, 'sell_ex': sell_ex, 'diff': diff})

    # 3. Анализ L2 (Глубина стакана) для ТОП-10
    pre_candidates = sorted(pre_candidates, key=lambda x: x['diff'], reverse=True)[:10]
    for c in pre_candidates:
        p_buy_l2 = get_l2_price(objs[c['buy_ex']], prices_ex[c['buy_ex']][c['sym']]['full_sym'], 'buy', invest_amount)
        p_sell_l2 = get_l2_price(objs[c['sell_ex']], prices_ex[c['sell_ex']][c['sym']]['full_sym'], 'sell', invest_amount)

        if p_buy_l2 and p_sell_l2:
            net_p = (((p_sell_l2 - p_buy_l2) / p_buy_l2) * 100) - (taker_fee * 2)
            if net_p > 0:
                data.append({
                    'Монета': c['sym'], 
                    'КУПИТЬ': c['buy_ex'].upper(), 
                    'ПРОДАТЬ': c['sell_ex'].upper(), 
                    'Чистый %': round(net_p, 3),
                    'Профит $': round(invest_amount * (net_p / 100), 2)
                })
    return pd.DataFrame(data)

# --- ИНТЕРФЕЙС ---
st.title("🚀 Arbitrage Screener 2026 Pro")

with st.sidebar:
    st.header("Настройки")
    invest = st.number_input("Ваш объем (USDT)", 100, 100000, 100)
    fee = st.number_input("Комиссия Taker %", 0.0, 0.2, 0.04, format="%.3f")
    min_v = st.number_input("Мин. объем монеты (USDT)", 0, 10000000, 100000)
    
    # СТРОКА 117: Исправленный список опций
    refresh_options = [10, 30, 60, 120, 300]
    refresh = st.select_slider("Обновление (сек)", options=refresh_options, value=60)
    
    st.header("Уведомления")
    alert_p = st.slider("Звук при профите > %", 0.1, 20.0, 0.5)

autorefresh(refresh)

df = get_data(min_v, fee, invest)

if not df.empty:
    if df['Чистый %'].max() >= alert_p:
        play_sound()
        st.success(f"🔥 Найдена связка: {df['Чистый %'].max()}%")

    st.subheader(f"ТОП связок с учетом стаканов (на {invest}$)")
    st.dataframe(df.sort_values('Чистый %', ascending=False), use_container_width=True)
else:
    st.info("Поиск связок... Попробуйте изменить фильтры в сайдбаре.")

st.caption(f"Обновлено: {pd.Timestamp.now().strftime('%H:%M:%S')} | Данные актуальны для 2026 года")
