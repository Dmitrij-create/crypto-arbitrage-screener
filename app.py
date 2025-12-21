import streamlit as st
import ccxt
import pandas as pd
import streamlit.components.v1 as components

st.set_page_config(page_title="Arbitrage Scanner", layout="wide")

def autorefresh(interval_seconds):
    components.html(
        f"<script>setTimeout(function() {{ window.parent.location.reload(); }}, {interval_seconds * 1000});</script>",
        height=0,
    )

# Список бирж и базовая валюта
EXCHANGES = [
    'binance', 
    'bybit', 
    'kraken', 
    'gateio', 
    'huobi',
    'okx',
    'mexc',
    'bingx',
    'bitget',
    'whitebit'
]
BASE_CURRENCY = 'USDT'
# --- ДОБАВЛЕНО ---
# Минимальный объем торгов за 24 часа в базовой валюте (например, 10000 USDT)
MIN_VOLUME = 10000 
# -----------------

@st.cache_data(ttl=30)
def get_data_optimized():
    data = []
    prices_by_exchange = {}
    
    st.sidebar.info("Загрузка цен...")

    for ex_id in EXCHANGES:
        try:
            ex_class = getattr(ccxt, ex_id)
            ex_obj = ex_class({'enableRateLimit': True})
            tickers = ex_obj.fetch_tickers()
            
            # --- ИЗМЕНЕНО: Добавлена проверка объема ---
            prices_by_exchange[ex_id] = {}
            for s, t in tickers.items():
                # Проверяем, что символ заканчивается на BASE_CURRENCY
                if s.endswith(f'/{BASE_CURRENCY}') and t is not None:
                    last_price = t.get('last')
                    # 'quoteVolume' или 'baseVolume' можно использовать в зависимости от биржи и требований
                    # Для простоты используем 'quoteVolume' (объем в USDT)
                    volume = t.get('quoteVolume') 

                    if last_price is not None and volume is not None and volume >= MIN_VOLUME:
                         prices_by_exchange[ex_id][s] = last_price
            # -------------------------------------------
        except Exception as e:
            st.sidebar.warning(f"Биржа {ex_id} недоступна")
            continue

    all_symbols = set()
    for ex_id in prices_by_exchange:
        all_symbols.update(prices_by_exchange[ex_id].keys())
    
    for symbol in all_symbols:
        prices = {}
        for ex_id in prices_by_exchange:
            if symbol in prices_by_exchange[ex_id]:
                prices[ex_id] = prices_by_exchange[ex_id][symbol]
        
        # Оставляем только те монеты, которые торгуются хотя бы на двух биржах из списка
        if len(prices) >= 2: 
            min_ex = min(prices, key=prices.get)
            max_ex = max(prices, key=prices.get)
            min_p = prices[min_ex]
            max_p = prices[max_ex]
            
            if min_p > 0:
                diff = ((max_p - min_p) / min_p) * 100
                if diff > 0:
                    data.append({
                        'Монета': symbol,
                        'Купить на': min_ex.upper(),
                        'Цена покупки': min_p,
                        'Продать на': max_ex.upper(),
                        'Цена продажи': max_p,
                        'Профит (%)': round(diff, 3)
                    })
    return pd.DataFrame(data)

st.title("🚀 Crypto Arbitrage Scanner")

st.sidebar.header("Настройки")
# Обновляем список опций для слайдера (была синтаксическая ошибка в оригинале)
refresh_sec = st.sidebar.select_slider("Обновление (сек)", options=[0, 30, 60, 120, 300], value=60) 
min_profit = st.sidebar.slider("Мин. профит (%)", 0.0, 5.0, 0.3)

if refresh_sec > 0:
    autorefresh(refresh_sec)

try:
    df = get_data_optimized() 
    if not df.empty:
        filtered_df = df[df['Профит (%)'] >= min_profit]
        if not filtered_df.empty:
            st.subheader(f"Найдено {len(filtered_df)} связок")
            st.dataframe(
                filtered_df.sort_values('Профит (%)', ascending=False),
                use_container_width=True
            )
        else:
            st.info(f"Нет связок с профитом выше {min_profit}%")
    else:
        st.warning("Данные не получены.")
except Exception as e:
    st.error(f"Ошибка приложения: {e}")

st.caption(f"Обновлено: {pd.Timestamp.now().strftime('%H:%M:%S')}")
