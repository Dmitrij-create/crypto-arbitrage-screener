import streamlit as st
from pycoingecko import CoinGeckoAPI
import pandas as pd
import streamlit.components.v1 as components

# Настройка страницы
st.set_page_config(page_title="Crypto Arbitrage Screener", layout="wide")

# Инициализация API
cg = CoinGeckoAPI()

# Список топ-монет
top_coins = [
    'bitcoin', 'ethereum', 'solana', 'binancecoin', 'ripple',
    'cardano', 'avalanche-2', 'polkadot', 'dogecoin', 'chainlink'
]

# Функция для автообновления страницы через JS-вставку
def autorefresh(interval_seconds):
    components.html(
        f"""
        <script>
        setTimeout(function() {{
            window.parent.location.reload();
        }}, {interval_seconds * 1000});
        </script>
        """,
        height=0,
    )

@st.cache_data(ttl=60)  # Кэш на 60 сек
def get_arbitrage_data():
    arbs = []
    progress_bar = st.progress(0)
    
    for idx, coin_id in enumerate(top_coins):
        try:
            tickers = cg.get_coin_ticker_by_id(id=coin_id)
            prices = []
            exchanges = []
            
            for ticker in tickers.get('tickers', []):
                # Фильтр по парам к USD/USDT
                if ticker.get('target') in ['USD', 'USDT']:
                    price_usd = ticker.get('converted_last', {}).get('usd')
                    market_name = ticker.get('market', {}).get('name')
                    
                    if price_usd and market_name:
                        prices.append(price_usd)
                        exchanges.append(market_name)
            
            if len(prices) >= 2:
                min_price = min(prices)
                max_price = max(prices)
                diff_percent = ((max_price - min_price) / min_price) * 100
                
                # Находим индексы бирж
                min_idx = prices.index(min_price)
                max_idx = prices.index(max_price)
                
                arbs.append({
                    'Монета': coin_id.upper(),
                    'Мин. цена (USD)': round(min_price, 4),
                    'Макс. цена (USD)': round(max_price, 4),
                    'Разница (%)': round(diff_percent, 2),
                    'Купить на': exchanges[min_idx],
                    'Продать на': exchanges[max_idx]
                })
        except Exception as e:
            st.error(f"Ошибка получения данных для {coin_id}: {e}")
        
        progress_bar.progress((idx + 1) / len(top_coins))
    
    progress_bar.empty()
    return pd.DataFrame(arbs)

# --- ИНТЕРФЕЙС ---
st.title('🚀 Скринер Арбитража Криптовалют (2025)')
st.markdown('Сканирует разницы цен между биржами через CoinGecko API.')

# Боковая панель управления
st.sidebar.header("Настройки")
refresh_interval = st.sidebar.select_slider(
    "Автообновление (сек)",
    options=[0, 30, 60, 120, 300],
    value=60
)

min_diff = st.sidebar.slider('Минимальный профит (%)', 0.0, 5.0, 0.5)

if st.sidebar.button('Очистить кэш и обновить'):
    st.cache_data.clear()
    st.rerun()

# Включаем автообновление, если выбрано > 0
if refresh_interval > 0:
    autorefresh(refresh_interval)
    st.sidebar.info(f"Обновление каждые {refresh_interval} сек.")

# Основной блок данных
df = get_arbitrage_data()

if not df.empty:
    # Фильтрация
    filtered_df = df[df['Разница (%)'] >= min_diff]
    
    if not filtered_df.empty:
        st.subheader(f"Найдено связок с профитом > {min_diff}%")
        
        # Красивая таблица с градиентом
        st.dataframe(
            filtered_df.sort_values('Разница (%)', ascending=False)
            .style.background_gradient(cmap='Greens', subset=['Разница (%)']),
            use_container_width=True
        )
        
        # Визуализация
        if st.checkbox('Показать график'):
            st.bar_chart(filtered_df.set_index('Монета')['Разница (%)'])
    else:
        st.warning(f"Связок с разницей более {min_diff}% не найдено.")
else:
    st.info('Не удалось получить данные. Проверьте подключение к интернету.')

st.caption(f"Последнее обновление: {pd.Timestamp.now().strftime('%H:%M:%S')}")
