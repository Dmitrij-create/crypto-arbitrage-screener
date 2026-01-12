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

# ФУНКЦИЯ ЗВУКА
def play_sound_html():
    # Надёжная бесплатная короткая ссылка (digital clock buzzer ~8 сек)
    sound_url = "https://assets.mixkit.co/sfx/preview/mixkit-digital-clock-digital-alarm-buzzer-989.mp3"
    
    sound_html = f"""
        <audio autoplay style="display:none;">
            <source src="{sound_url}" type="audio/mpeg">
            Your browser does not support the audio element.
        </audio>
    """
    components.html(sound_html, height=0)

# Автообновление страницы
def autorefresh(interval_seconds):
    components.html(
        f"""
        <script>
            setTimeout(function() {{ window.parent.location.reload(); }}, {interval_seconds * 1000});
        </script>
        """,
        height=0,
    )

# Список бирж и базовая валюта
EXCHANGES = ['gateio', 'okx', 'mexc', 'bingx', 'bitget']
BASE_CURRENCY = 'USDT'

@st.cache_data(ttl=12)
def get_data(max_spread_pct, min_volume_usdt):
    data = []
    prices_by_ex = {}

    for ex_id in EXCHANGES:
        try:
            ex = getattr(ccxt, ex_id)({
                'enableRateLimit': True,
                'options': {'defaultType': 'future'}  # 'swap' тоже можно, но 'future' чаще работает
            })
            tickers = ex.fetch_tickers()

            cleaned = {}
            for symbol, ticker in tickers.items():
                if BASE_CURRENCY not in symbol:
                    continue
                vol = ticker.get('quoteVolume') or ticker.get('baseVolume') or 0
                bid = ticker.get('bid')
                ask = ticker.get('ask')

                if bid and ask and bid > 0 and vol >= min_volume_usdt:
                    spread_pct = ((ask - bid) / bid) * 100
                    if spread_pct <= max_spread_pct:
                        # Улучшенная очистка символа
                        clean_sym = symbol.split('/')[0].split(':')[0].replace(f":{BASE_CURRENCY}", "")
                        cleaned[clean_sym] = {'bid': bid, 'ask': ask, 'vol': vol}

            if cleaned:
                prices_by_ex[ex_id] = cleaned

        except Exception as e:
            # st.warning(f"Ошибка на {ex_id}: {e}")  # можно раскомментировать для отладки
            continue

    # Собираем все уникальные символы
    all_symbols = set()
    for prices in prices_by_ex.values():
        all_symbols.update(prices.keys())

    for sym in all_symbols:
        exchanges_with_sym = [ex for ex in prices_by_ex if sym in prices_by_ex[ex]]
        if len(exchanges_with_sym) < 2:
            continue

        bids = {ex: prices_by_ex[ex][sym]['bid'] for ex in exchanges_with_sym}
        asks = {ex: prices_by_ex[ex][sym]['ask'] for ex in exchanges_with_sym}

        buy_ex = min(asks, key=asks.get)     # самая низкая цена покупки
        sell_ex = max(bids, key=bids.get)    # самая высокая цена продажи

        p_buy = asks[buy_ex]
        p_sell = bids[sell_ex]

        if p_sell > p_buy:
            profit_pct = ((p_sell - p_buy) / p_buy) * 100
            data.append({
                'Инструмент': sym,
                'КУПИТЬ': buy_ex.upper(),
                'ПРОДАТЬ': sell_ex.upper(),
                'Профит (%)': round(profit_pct, 3)
            })

    return pd.DataFrame(data)


# ── ИНТЕРФЕЙС ────────────────────────────────────────────────

st.sidebar.header("⚙️ Настройки")

max_spread = st.sidebar.slider("Макс. внутр. спред (%)", 0.0, 1.5, 0.35, 0.05)
min_vol = st.sidebar.number_input("Мин. объём (USDT)", 0, 20_000_000, 80_000, step=10000)

refresh_options = [10, 20, 30, 45, 60, 120, 300]
refresh_sec = st.sidebar.select_slider("Обновление (сек)", options=refresh_options, value=30)

min_profit_filter = st.sidebar.slider("Мин. профит в таблице (%)", 0.0, 8.0, 0.4, 0.1)

# ── АЛЕРТЫ ───────────────────────────────────────────────────

st.sidebar.header("🔔 Управление алертами")

col1, col2 = st.sidebar.columns([3, 2])
with col1:
    alert_symbol = st.text_input("Монета (напр. BTC)", value="BTC").strip().upper()
with col2:
    alert_target = st.number_input("Целевой профит %", 0.1, 10.0, 0.8, step=0.1)

col_buy, col_sell = st.sidebar.columns(2)
with col_buy:
    alert_buy_ex = st.selectbox("Купить на", EXCHANGES, index=0).upper()
with col_sell:
    alert_sell_ex = st.selectbox("Продать на", EXCHANGES, index=1).upper()

if st.sidebar.button("➕ Добавить алерт", use_container_width=True):
    if alert_symbol:
        new_alert = {
            'symbol': alert_symbol,
            'buy': alert_buy_ex,
            'sell': alert_sell_ex,
            'target': alert_target
        }
        if new_alert not in st.session_state.alerts:
            st.session_state.alerts.append(new_alert)
            st.rerun()

# Отображение и удаление алертов
if st.session_state.alerts:
    st.sidebar.subheader("Активные алерты")
    
    to_delete = None
    for i, alert in enumerate(st.session_state.alerts):
        label = f"{alert['symbol']}  {alert['buy']} → {alert['sell']}  ≥ {alert['target']}%"
        if st.sidebar.button(f"❌ {label}", key=f"del_alert_{i}"):
            to_delete = i
    
    if to_delete is not None:
        st.session_state.alerts.pop(to_delete)
        st.rerun()

# ── ОСНОВНАЯ ЛОГИКА ─────────────────────────────────────────

autorefresh(refresh_sec)

df = get_data(max_spread, min_vol)

triggered_now = set()

if not df.empty:
    for alert in st.session_state.alerts:
        match = df[
            (df['Инструмент'] == alert['symbol']) &
            (df['КУПИТЬ'] == alert['buy']) &
            (df['ПРОДАТЬ'] == alert['sell'])
        ]
        
        if not match.empty:
            current_profit = match['Профит (%)'].iloc[0]
            key = f"{alert['symbol']}_{alert['buy']}_{alert['sell']}_{alert['target']}"
            
            if current_profit >= alert['target']:
                triggered_now.add(f"{alert['symbol']}|{alert['buy']}|{alert['sell']}")
                
                if key not in st.session_state.triggered_alerts:
                    st.session_state.triggered_alerts[key] = True
                    play_sound_html()
                    st.toast(f"🔔 СИГНАЛ: {alert['symbol']} → {round(current_profit,2)}%", icon="🚨")
            else:
                # Убираем метку, если профит упал ниже
                st.session_state.triggered_alerts.pop(key, None)

    def highlight_row(row):
        key = f"{row['Инструмент']}|{row['КУПИТЬ']}|{row['ПРОДАТЬ']}"
        if key in triggered_now:
            return ['background-color: #d4edda; color: #0f5132; font-weight: bold'] * len(row)
        return [''] * len(row)

    st.subheader("Найденные связки")
    
    display_df = df[df['Профит (%)'] >= min_profit_filter].sort_values('Профит (%)', ascending=False)
    
    if not display_df.empty:
        st.dataframe(
            display_df.style.apply(highlight_row, axis=1),
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("Нет связок с профитом выше выбранного порога.")
else:
    st.warning("Не удалось загрузить данные ни с одной биржи.")

st.caption(f"Обновлено: {pd.Timestamp.now().strftime('%H:%M:%S')}   ·   Кликните по странице, если звук не воспроизводится")
