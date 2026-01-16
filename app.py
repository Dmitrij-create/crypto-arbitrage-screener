import streamlit as st
import ccxt
import pandas as pd
import streamlit.components.v1 as components

# --- Инициализация состояний ---
if 'alerts' not in st.session_state:
    st.session_state['alerts'] = []

st.set_page_config(page_title="Futures Arbitrage 2026", layout="wide")

# Функция звука
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

# Список бирж (актуальные для фьючерсов в 2026)
EXCHANGES = ['binance', 'okx', 'bybit', 'mexc', 'gateio', 'bitget']
BASE_CURRENCY = 'USDT'

def get_l2_price(ex_obj, symbol, side, amount_usdt):
    """Рассчитывает цену исполнения L2 на фьючерсном стакане"""
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

    # 1. Сбор тикеров ТОЛЬКО для фьючерсного рынка
    for ex_id in EXCHANGES:
        try:
            # Принудительно устанавливаем тип swap (фьючерсы)
            ex_obj = getattr(ccxt, ex_id)({
                'enableRateLimit': True, 
                'timeout': 7000,
                'options': {'defaultType': 'swap'} 
            })
            objs[ex_id] = ex_obj
            tickers = ex_obj.fetch_tickers()
            
            cleaned = {}
            for s, t in tickers.items():
                # Очищаем тикеры, чтобы сравнивать их между биржами
                if BASE_CURRENCY in s and t.get('bid') and t.get('ask'):
                    # Удаляем лишние приставки бирж (напр. :USDT)
                    clean_name = s.split(':')[0].replace(f'/{BASE_CURRENCY}', '')
                    vol = t.get('quoteVolume') or 0
                    cleaned[clean_name] = {'bid': t['bid'], 'ask': t['ask'], 'full_sym': s, 'vol': vol}
            
            if cleaned: prices_ex[ex_id] = cleaned
        except: continue

    # 2. Поиск кандидатов по тикерам
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
                if 0.1 < diff < 10: # Фильтр разумного спреда
                    pre_candidates.append({'sym': sym, 'buy_ex': buy_ex, 'sell_ex': sell_ex, 'diff': diff})

    # 3. Анализ L2 (стаканы) для ТОП-10 фьючерсных пар
    pre_candidates = sorted(pre_candidates, key=lambda x: x['diff'], reverse=True)[:10]
    for c in pre_candidates:
        p_buy_l2 = get_l2_price(objs[c['buy_ex']], prices_ex[c['buy_ex']][c['sym']]['full_sym'], 'buy', invest_amount)
        p_sell_l2 = get_l2_price(objs[c['sell_ex']], prices_ex[c['sell_ex']][c['sym']]['full_sym'], 'sell', invest_amount)

        if p_buy_l2 and p_sell_l2:
            net_p = (((p_sell_l2 - p_buy_l2) / p_buy_l2) * 100) - (taker_fee * 2)
            if net_p > 0:
                data.append({
                    'Монета': c['sym'], 
                    'КУПИТЬ (Long)': c['buy_ex'].upper(), 
                    'ПРОДАТЬ (Short)': c['sell_ex'].upper(), 
                    'Чистый %': round(net_p, 3),
                    'Профит $': round(invest_amount * (net_p / 100), 2)
                })
    return pd.DataFrame(data)

# --- ИНТЕРФЕЙС ---
st.title("📉 Futures/Futures Arbitrage 2026")
st.info("Скринер ищет разницу цен между бессрочными фьючерсами на разных биржах.")

with st.sidebar:
    st.header("Настройки")
    invest = st.number_input("Объем позиции (USDT)", 10, 100000, 50)
    fee = st.number_input("Taker Fee %", 0.0, 0.1, 0.04, step=0.01, format="%.3f")
    min_v = st.number_input("Мин. 24h Объем (USDT)", 0, 50000000, 500000)
    
    # Исправленный список без ошибок
    refresh_options = [15, 30, 60, 120, 300]
    refresh = st.select_slider("Обновление (сек)", options=refresh_options, value=30)
    
    st.header("Алерты")
    alert_p = st.slider("Звук если профит > %", 0.1, 20.0, 2.0)

autorefresh(refresh)

df = get_data(min_v, fee, invest)

if not df.empty:
    if df['Чистый %'].max() >= alert_p:
        play_sound()
        st.success(f"🎯 Найдена связка: {df['Чистый %'].max()}%")

    st.subheader(f"Актуальные фьючерсные связки (Объем: {invest}$)")
    st.dataframe(df.sort_values('Чистый %', ascending=False), use_container_width=True)
else:
    st.info("Сканирование фьючерсных рынков... Попробуйте снизить 'Мин. 24h Объем'.")

st.caption(f"Дата: 2026-01-16 | Обновлено: {pd.Timestamp.now().strftime('%H:%M:%S')}")
