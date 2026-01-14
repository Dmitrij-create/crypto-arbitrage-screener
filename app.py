import streamlit as st
import ccxt
import pandas as pd
import streamlit.components.v1 as components
import json

# --- Инициализация состояний ---
if 'alerts' not in st.session_state:
    st.session_state['alerts'] = []
if 'triggered_alerts' not in st.session_state:
    st.session_state['triggered_alerts'] = {}

st.set_page_config(page_title="Arbitrage Screener 2026 Pro", layout="wide")

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

def autorefresh(interval_seconds):
    if interval_seconds > 0:
        components.html(
            f"<script>setTimeout(function() {{ window.parent.location.reload(); }}, {interval_seconds * 1000});</script>",
            height=0,
        )

EXCHANGES = ['gateio', 'okx', 'mexc', 'bingx', 'bitget']
BASE_CURRENCY = 'USDT'

@st.cache_data(ttl=10)
def get_data(max_spread, min_vol, taker_fee_percent, investment_amount):
    data = []
    prices_ex = {}
    funding_rates_ex = {}
    
    for ex_id in EXCHANGES:
        try:
            ex_obj = getattr(ccxt, ex_id)({'enableRateLimit': True, 'options': {'defaultType': 'swap'}})
            tickers = ex_obj.fetch_tickers()
            # Пытаемся получить ставки финансирования (может не работать для всех CCXT версий)
            try:
                # CCXT Unified API метод fetch_funding_rate требует символ 'BTC/USDT', а не просто 'BTC'
                all_symbols = [s for s in tickers.keys() if f'{BASE_CURRENCY}' in s]
                # Ограничиваем количество запросов, чтобы не превысить лимиты
                rates = {s: ex_obj.fetch_funding_rate(s)['fundingRate'] for s in all_symbols[:50]} 
                funding_rates_ex[ex_id] = rates
            except Exception as e_rate:
                # st.sidebar.warning(f"{ex_id}: Ошибка при получении фандинга ({e_rate})")
                pass

            cleaned = {}
            for s, t in tickers.items():
                vol = t.get('quoteVolume') or 0
                if f'{BASE_CURRENCY}' in s and t.get('bid') and t.get('ask') and vol >= min_vol:
                    bid, ask = t['bid'], t['ask']
                    if bid > 0 and ((ask - bid) / bid) * 100 <= max_spread:
                        sym = s.replace(f':{BASE_CURRENCY}', '').replace(f'/{BASE_CURRENCY}', '')
                        cleaned[sym] = {'bid': bid, 'ask': ask}
            if cleaned: prices_ex[ex_id] = cleaned
        except Exception as e_ex: 
            # st.sidebar.error(f"{ex_id}: Ошибка API ({e_ex})")
            continue

    all_syms = set().union(*(ex.keys() for ex in prices_ex.values()))
    for sym in all_syms:
        ex_with_sym = [ex for ex in prices_ex if sym in prices_ex[ex]]
        if len(ex_with_sym) >= 2:
            bids = {ex: prices_ex[ex][sym]['bid'] for ex in ex_with_sym}
            asks = {ex: prices_ex[ex][sym]['ask'] for ex in ex_with_sym}
            buy_ex, sell_ex = min(asks, key=asks.get), max(bids, key=bids.get)
            p_buy, p_sell = asks[buy_ex], bids[sell_ex]
            
            if p_sell > p_buy:
                gross_profit = ((p_sell - p_buy) / p_buy) * 100
                total_fee_rate = (taker_fee_percent / 100) * 2 
                net_profit_percent = gross_profit - total_fee_rate
                net_profit_usd = investment_amount * (net_profit_percent / 100)
                
                # --- НОВОЕ: Расчет APR фандинга ---
                buy_fr = funding_rates_ex.get(buy_ex, {}).get(f'{sym}/{BASE_CURRENCY}', 0)
                sell_fr = funding_rates_ex.get(sell_ex, {}).get(f'{sym}/{BASE_CURRENCY}', 0)
                # Разница фандинга * 3 раза в день * 365 дней (если ставки не меняются)
                apr_percent = (sell_fr - buy_fr) * 3 * 365 * 100
                
                data.append({
                    'Инструмент': sym, 
                    'КУПИТЬ': buy_ex.upper(), 
                    'ПРОДАТЬ': sell_ex.upper(), 
                    'Грязный %': round(gross_profit, 3),
                    'Чистый %': round(net_profit_percent, 3),
                    'Профит $': round(net_profit_usd, 2),
                    'APR Фандинга (%)': round(apr_percent, 2), # Новый столбец
                })
    return pd.DataFrame(data)

# --- ИНТЕРФЕЙС ---
st.title("📊 Arbitrage Screener 2026 Pro (Alpha)")

with st.sidebar:
    st.header("⚙️ Настройки Фильтров")
    max_s = st.slider("Макс. внутр. спред Bid/Ask (%)", 0.0, 1.0, 0.4)
    min_v = st.number_input("Мин. объем торгов (USDT)", 0, 10000000, 100000)
    
    refresh_opts =
    refresh = st.select_slider("Автообновление (сек)", options=refresh_opts, value=30)
    min_p = st.slider("Мин. чистый профит (%)", 0.0, 5.0, 0.5)

    st.header("💰 Калькулятор Прибыли")
    invest = st.number_input("Ваш депозит (USDT)", 100, 100000, 1000)
    fee = st.number_input("Taker Fee % (0.04 средняя)", 0.0, 0.1, 0.04, step=0.005, format="%.3f")

    st.header("🔔 Добавить Алерт")
    with st.form("alert_form", clear_on_submit=True):
        in_sym = st.text_input("Монета (напр. BTC)").upper()
        in_buy = st.selectbox("Купить на", EXCHANGES)
        in_sell = st.selectbox("Продать на", EXCHANGES, index=1)
        in_profit = st.slider("Цель: Чистый %", 0.0, 10.0, 1.0, step=0.1)
        if st.form_submit_button("➕ Добавить"):
            if in_sym:
                new_alert = {'sym': in_sym, 'buy': in_buy.upper(), 'sell': in_sell.upper(), 'target': in_profit}
                if new_alert not in st.session_state.alerts:
                    st.session_state.alerts.append(new_alert)

    if st.session_state.alerts:
        st.subheader("Активные Алерты:")
        for i, a in enumerate(st.session_state.alerts):
            col_t, col_d = st.columns()
            col_t.caption(f"{a['sym']} {a['buy']}->{a['sell']} @ {a['target']}%")
            if col_d.button("❌", key=f"del_{i}"):
                st.session_state.alerts.pop(i)
                st.rerun()

autorefresh(refresh)
df = get_data(max_s, min_v, fee, invest)

triggered_now = set()
if not df.empty:
    for alert in st.session_state.alerts:
        match = df[(df['Инструмент'] == alert['sym']) & (df['КУПИТЬ'] == alert['buy']) & (df['ПРОДАТЬ'] == alert['sell'])]
        if not match.empty:
            cur_net_p = match['Чистый %'].iloc
            alert_key = f"{alert['sym']}_{alert['buy']}_{alert['sell']}_{alert['target']}"
            if round(cur_net_p, 2) >= alert['target']:
                triggered_now.add(f"{alert['sym']}|{alert['buy']}|{alert['sell']}")
                if alert_key not in st.session_state.triggered_alerts:
                    st.session_state.triggered_alerts[alert_key] = True
                    play_sound()
                    st.sidebar.success(f"🎯 СИГНАЛ: {alert['sym']} {cur_net_p}%")
            else:
                if alert_key in st.session_state.triggered_alerts:
                    del st.session_state.triggered_alerts[alert_key]

    def highlight(row):
        key = f"{row['Инструмент']}|{row['КУПИТЬ']}|{row['ПРОДАТЬ']}"
        return ['background-color: #d4edda; color: #155724; font-weight: bold'] * len(row) if key in triggered_now else [''] * len(row)

    st.subheader("Актуальные возможности (с учетом комиссий)")
    display_df = df[df['Чистый %'] >= min_p].sort_values('Чистый %', ascending=False)
    if not display_df.empty:
        st.dataframe(display_df.style.apply(highlight, axis=1), use_container_width=True)
    else:
        st.info("Связок с таким чистым профитом пока нет.")

st.caption(f"Обновлено: {pd.Timestamp.now().strftime('%H:%M:%S')}")
