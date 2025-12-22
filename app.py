import streamlit as st
import ccxt
import pandas as pd
import streamlit.components.v1 as components

st.set_page_config(page_title="Futures Arbitrage Scanner", layout="wide")

def autorefresh(interval_seconds):
    components.html(
        f"<script>setTimeout(function() {{ window.parent.location.reload(); }}, {interval_seconds * 1000});</script>",
        height=0,
    )

# Биржи (Binance часто блокирует облака, добавим больше альтернатив)
EXCHANGES = ['binance', 'bybit', 'huobi', 'gateio', 'okx']
BASE_CURRENCY = 'USDT'

@st.cache_data(ttl=30)
def get_futures_data():
    data = []
    prices_by_exchange = {}
    
    st.sidebar.info("Сканирование фьючерсов...")

    for ex_id in EXCHANGES:
        try:
            ex_class = getattr(ccxt, ex_id)
            # Принудительный режим SWAP (бессрочные фьючерсы)
            ex_obj = ex_class({'enableRateLimit': True, 'options': {'defaultType': 'swap'}}) 
            
            tickers = ex_obj.fetch_tickers()
            
            cleaned_tickers = {}
            for s, t in tickers.items():
                # Условие: пара к USDT и наличие цены
                if f'{BASE_CURRENCY}' in s and t.get('last'):
                    # НОРМАЛИЗАЦИЯ: убираем :USDT для сравнения разных бирж
                    base_symbol = s.split(':')[0] 
                    cleaned_tickers[base_symbol] = t['last']
            
            if cleaned_tickers:
                prices_by_exchange[ex_id] = cleaned_tickers
                st.sidebar.success(f"{ex_id.upper()}: OK ({len(cleaned_tickers)} пар)")
        except Exception as e:
            # Если ошибка 403 - это блокировка по IP (Streamlit Cloud)
            err_msg = str(e)
            if "403" in err_msg:
                st.sidebar.error(f"{ex_id.upper()}: Блок IP (403)")
            else:
                st.sidebar.warning(f"{ex_id.upper()}: Ошибка API")
            continue

    # Ищем общие монеты
    all_symbols = set()
    for ex_id in prices_by_exchange:
        all_symbols.update(prices_by_exchange[ex_id].keys())
    
    for symbol in all_symbols:
        prices = {}
        for ex_id in prices_by_exchange:
            if symbol in prices_by_exchange[ex_id]:
                prices[ex_id] = prices_by_exchange[ex_id][symbol]
        
        if len(prices) >= 2:
            ex_list = list(prices.keys())
            for i in range(len(ex_list)):
                for j in range(i + 1, len(ex_list)):
                    ex1, ex2 = ex_list[i], ex_list[j]
                    p1, p2 = prices[ex1], prices[ex2]
                    
                    diff = abs(p1 - p2) / min(p1, p2) * 100
                    
                    if diff > 0:
                        buy_ex = ex1 if p1 < p2 else ex2
                        sell_ex = ex2 if p1 < p2 else ex1
                        data.append({
                            'Инструмент': symbol,
                            'Купить на': buy_ex.upper(),
                            'Цена 1': min(p1, p2),
                            'Продать на': sell_ex.upper(),
                            'Цена 2': max(p1, p2),
                            'Профит (%)': round(diff, 3)
                        })

    return pd.DataFrame(data)

# --- ИНТЕРФЕЙС ---
st.title("📊 Фьючерсный Арбитраж (Бессрочные)")

st.sidebar.header("Настройки")
refresh_sec = st.sidebar.select_slider("Обновление (сек)", options=[0, 30, 60, 120, 300], value=60)
min_profit = st.sidebar.slider("Мин. профит (%)", 0.0, 5.0, 0.1)

if refresh_sec > 0:
    autorefresh(refresh_sec)

df = get_futures_data()

if not df.empty:
    filtered_df = df[df['Профит (%)'] >= min_profit]
    if not filtered_df.empty:
        st.dataframe(
            filtered_df.sort_values('Профит (%)', ascending=False),
            use_container_width=True
        )
    else:
        st.info(f"Нет связок выше {min_profit}%")
else:
    st.warning("Данные не получены. Скорее всего, биржи заблокировали IP облачного сервера. Запустите скрипт ЛОКАЛЬНО.")

st.caption(f"Обновлено: {pd.Timestamp.now().strftime('%H:%M:%S')}")
