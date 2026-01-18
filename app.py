import streamlit as st
import ccxt
import pandas as pd
import streamlit.components.v1 as components

st.set_page_config(page_title="Futures/Funding Arbitrage 2026", layout="wide")

def play_sound():
    sound_js = """<script>var context = new (window.AudioContext || window.webkitAudioContext)(); var oscillator = context.createOscillator(); oscillator.type = 'sine'; oscillator.frequency.setValueAtTime(440, context.currentTime); oscillator.connect(context.destination); oscillator.start(); setTimeout(function() { oscillator.stop(); }, 500);</script>"""
    components.html(sound_js, height=0)

def autorefresh(interval_seconds):
    if interval_seconds > 0:
        components.html(f"<script>setTimeout(function() {{ window.parent.location.reload(); }}, {interval_seconds * 1000});</script>", height=0)

EXCHANGES = ['binance', 'okx', 'bybit', 'bitget'] # Оставили самые стабильные по фандингу
BASE_CURRENCY = 'USDT'

def get_l2_price(ex_obj, symbol, side, amount_usdt):
    try:
        order_book = ex_obj.fetch_order_book(symbol, 5)
        orders = order_book['asks'] if side == 'buy' else order_book['bids']
        accum_usdt, accum_crypto = 0, 0
        for price, amount in orders:
            vol = price * amount
            if accum_usdt + vol >= amount_usdt:
                needed = amount_usdt - accum_usdt
                accum_crypto += (needed / price)
                return amount_usdt / accum_crypto
            accum_crypto += amount
            accum_usdt += vol
        return None
    except: return None

@st.cache_data(ttl=15)
def get_futures_data(min_vol, taker_fee, invest_amount):
    data = []
    prices_ex = {}
    objs = {}

    for ex_id in EXCHANGES:
        try:
            ex_obj = getattr(ccxt, ex_id)({'enableRateLimit': True, 'options': {'defaultType': 'swap'}})
            objs[ex_id] = ex_obj
            
            # В 2026 fetch_tickers на многих биржах сразу отдает fundingRate
            tickers = ex_obj.fetch_tickers()
            
            cleaned = {}
            for s, t in tickers.items():
                if BASE_CURRENCY in s and t.get('bid') and t.get('ask'):
                    # Извлекаем чистый тикер (напр. BTC)
                    clean_name = s.split(':')[0].split('/')[0]
                    funding = t.get('info', {}).get('lastFundingRate') or t.get('fundingRate') or 0
                    cleaned[clean_name] = {
                        'bid': t['bid'], 'ask': t['ask'], 
                        'full_sym': s, 'vol': t.get('quoteVolume') or 0,
                        'funding': float(funding) * 100 # переводим в %
                    }
            if cleaned: prices_ex[ex_id] = cleaned
        except: continue

    all_syms = set().union(*(ex.keys() for ex in prices_ex.values()))
    
    pre_candidates = []
    for sym in all_syms:
        ex_with_sym = [ex for ex in prices_ex if sym in prices_ex[ex]]
        if len(ex_with_sym) >= 2:
            # Ищем экстремумы по цене
            buy_ex = min(ex_with_sym, key=lambda x: prices_ex[x][sym]['ask'])
            sell_ex = max(ex_with_sym, key=lambda x: prices_ex[x][sym]['bid'])
            
            p_buy = prices_ex[buy_ex][sym]['ask']
            p_sell = prices_ex[sell_ex][sym]['bid']
            
            if p_sell > p_buy:
                diff = ((p_sell - p_buy) / p_buy) * 100
                if 0.05 < diff < 10:
                    pre_candidates.append({'sym': sym, 'buy_ex': buy_ex, 'sell_ex': sell_ex, 'diff': diff})

    pre_candidates = sorted(pre_candidates, key=lambda x: x['diff'], reverse=True)[:10]
    
    for c in pre_candidates:
        p_buy_l2 = get_l2_price(objs[c['buy_ex']], prices_ex[c['buy_ex']][c['sym']]['full_sym'], 'buy', invest_amount)
        p_sell_l2 = get_l2_price(objs[c['sell_ex']], prices_ex[c['sell_ex']][c['sym']]['full_sym'], 'sell', invest_amount)

        if p_buy_l2 and p_sell_l2:
            f_buy = prices_ex[c['buy_ex']][c['sym']]['funding']
            f_sell = prices_ex[c['sell_ex']][c['sym']]['funding']
            
            # Итоговый профит = Спред - Комиссии
            net_p = (((p_sell_l2 - p_buy_l2) / p_buy_l2) * 100) - (taker_fee * 2)
            
            # Фандинг профит: если мы в Long, нам платят если f_buy < 0. Если в Short, нам платят если f_sell > 0.
            # Разница фандинга (f_sell - f_buy) показывает потенциальный доход в следующем цикле (8ч).
            funding_diff = f_sell - f_buy

            if net_p > -0.1: # Показываем даже околонулевые, если фандинг жирный
                data.append({
                    'Монета': c['sym'],
                    'LONG': c['buy_ex'].upper(),
                    'SHORT': c['sell_ex'].upper(),
                    'Спред %': round(net_p, 3),
                    'Funding Diff %': round(funding_diff, 4),
                    'F_Buy %': f_buy,
                    'F_Sell %': f_sell,
                    'Итого $': round(invest_amount * (net_p / 100), 2)
                })
    return pd.DataFrame(data)

# --- UI ---
st.title("📉 Futures Arbitrage + Funding 2026")

with st.sidebar:
    invest = st.number_input("Объем (USDT)", 10, 100000, 50)
    fee = st.number_input("Taker Fee %", 0.0, 0.1, 0.05, format="%.3f")
    min_v = st.number_input("Мин. 24h Объем", 0, 100000000, 50000)
    refresh = st.select_slider("Обновление", options=[15, 30, 60, 120], value=30)
    alert_p = st.slider("Сигнал (Профит > %)", 0.1, 9.0, 2.0)

autorefresh(refresh)
df = get_futures_data(min_v, fee, invest)

if not df.empty:
    if df['Спред %'].max() >= alert_p:
        play_sound()
    
    # Сортировка по спреду
    st.dataframe(df.sort_values('Спред %', ascending=False), use_container_width=True)
    
    st.info("""
    **Как читать Funding Diff %:**
    - Если значение **положительное**, вы дополнительно зарабатываете на разнице ставок финансирования каждые 8 часов.
    - Если **отрицательное**, фандинг будет постепенно уменьшать вашу прибыль от спреда.
    """)
else:
    st.warning("Связки не найдены. Попробуйте уменьшить фильтр объема.")

st.caption(f"Обновлено: {pd.Timestamp.now().strftime('%H:%M:%S')} | Данные: CCXT 2026")
