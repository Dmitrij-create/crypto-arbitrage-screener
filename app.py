import streamlit as st
from pycoingecko import CoinGeckoAPI
import pandas as pd
import time

# Инициализация API
cg = CoinGeckoAPI()

# Список топ-монет (можно расширить)
top_coins = [
    'bitcoin', 'ethereum', 'solana', 'binancecoin', 'ripple',
    'cardano', 'avalanche-2', 'terra-luna-2', 'polkadot', 'dogecoin'
]

@st.cache_data(ttl=60)  # Кэш на 60 сек для снижения нагрузки на API
def get_arbitrage_data():
    arbs = []
    for coin_id in top_coins:
        try:
            tickers = cg.get_coin_ticker_by_id(id=coin_id)
            prices = []
            exchanges = []
            for ticker in tickers['tickers']:
                # Фильтр по USDT/USD парам (арбитраж в USD-эквиваленте)
                if ticker['target'] in ['USD', 'USDT']:
                    price_usd = ticker['converted_last'].get('usd')
                    if price_usd:
                        prices.append(price_usd)
                        exchanges.append(ticker['market']['name'])
            
            if prices and len(prices) >= 2:  # Нужно минимум 2 биржи
                min_price = min(prices)
                max_price = max(prices)
                diff_percent = (max_price - min_price) / min_price * 100
                min_exchange = exchanges[prices.index(min_price)]
                max_exchange = exchanges[prices.index(max_price)]
                
                arbs.append({
                    'Монета': coin_id.upper(),
                    'Мин. цена (USD)': round(min_price, 4),
                    'Макс. цена (USD)': round(max_price, 4),
                    'Разница (%)': round(diff_percent, 2),
                    'Биржа мин.': min_exchange,
                    'Биржа макс.': max_exchange
                })
        except Exception as e:
            st.warning(f"Ошибка для {coin_id}: {e}")
    
    return pd.DataFrame(arbs)

# Интерфейс Streamlit
st.title('Скринер Арбитража Криптовалют')
st.markdown('Сканирует разницы цен на CEX биржах через CoinGecko API. Обновляйте для свежих данных.')
# Добавь слайдер для выбора интервала обновления
refresh_interval = st.select_slider(
    "Автообновление (секунды)",
    options=[0, 30, 60, 120, 300],
    value=60,
    help="0 = без автообновления"
)

if refresh_interval > 0:
    st.autoreload(interval=refresh_interval * 1000)
# Кнопка обновления
if st.button('Обновить данные'):
    st.cache_data.clear()

# Получение данных
df = get_arbitrage_data()

if not df.empty:
    # Фильтр по минимальной разнице
    min_diff = st.slider('Минимальная разница (%) для показа', 0.0, 10.0, 0.5)
    filtered_df = df[df['Разница (%)'] >= min_diff]
    
    # Сортировка по разнице
    st.dataframe(
        filtered_df.sort_values('Разница (%)', ascending=False).style.background_gradient(cmap='viridis', subset=['Разница (%)']),
        use_container_width=True
    )
    
    # График (опционально)
    if st.checkbox('Показать график разниц'):
        st.bar_chart(filtered_df.set_index('Монета')['Разница (%)'])
else:
    st.info('Нет данных. Попробуйте обновить или проверить API.')

# Автообновление каждые 60 сек
# Автообновление каждые 60 секунд (правильный способ для Streamlit)
placeholder = st.empty()
with placeholder.container():
    st.info("Данные обновляются автоматически каждые 60 секунд ⏳")

# Это заставит Streamlit перезапускать скрипт периодически
if st.session_state.get('auto_refresh', True):
    st.autoreload(interval=60 * 1000)  # 60 секунд в миллисекундах
