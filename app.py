import streamlit as st
import ccxt
import pandas as pd
import streamlit.components.v1 as components

# Настройка страницы
st.set_page_config(page_title="Futures Bid/Ask Arbitrage", layout="wide")

# Функция автообновления через JS
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

# Список бирж (2025)
EXCHANGES = ['binance', 'bybit', 'huobi', 'gateio', 'okx', 'mexc', 'bingx', 'bitget']
BASE_CURRENCY = 'USDT'

@st.cache_data(ttl=10) # Кэш 10 секунд для актуальности цен
def get_bid_ask_data():
    data = []
    prices_by_exchange = {}
    
    st.sidebar.info("Сканирование стаканов (Bid/Ask)...")

    for ex_id in EXCHANGES:
        try:
            ex_class = getattr(ccxt, ex_id)
            # Настройка на работу с бессрочными фьючерсами
            ex_obj = ex_class({'enableRateLimit': True, 'options': {'defaultType': 'swap'}}) 
            
            # Получаем тикеры всех монет сразу
            tickers = ex_obj.fetch_tickers()
            
            cleaned_data = {}
            for s, t in tickers.items():
                # Проверяем пару и наличие цен покупки/продажи
                if f'{BASE_CURRENCY}' in s and t.get('bid') and t.get('ask'):
                    # Нормализуем название (убираем :USDT)
                    base_symbol = s.split(':')[0]
                    cleaned_data[base_symbol] = {
                        'bid': t['bid'],
                        'ask': t['ask']
                    }
            
            if cleaned_data:
                prices_by_exchange[ex_id] = cleaned_data
                st.sidebar.success(f"{ex_id.upper()}: OK ({len(cleaned_data)} пар)")
        except Exception as e:
            err_msg = str(e)
            if "403" in err_msg:
                st.sidebar.error(f"{ex_id.upper()}: Блок IP (403)")
            else:
                st.sidebar.warning(f"{ex_id.upper()}: Ошибка API")
            continue

    # Собираем все уникальные инструменты
    all_symbols = set()
    for ex_id in prices_by_exchange:
        all_symbols.update(prices_by_exchange[ex_id].keys())
    
    for symbol in all_symbols:
        bids = {}
        asks = {}
        for ex_id in prices_by_exchange:
            if symbol in prices_by_exchange[ex_id]:
                bids[ex_id] = prices_by_exchange[ex_id][symbol]['bid']
                asks[ex_id] = prices_by_exchange[ex_id][symbol]['ask']
        
        # Сравниваем биржи, если монета есть минимум на двух
        if len(bids) >= 2:
            # Где дешевле купить (Min Ask) и где дороже продать (Max Bid)
            buy_ex = min(asks, key=asks.get)
            sell_ex = max(bids, key=bids.get)
            
            buy_price = asks[buy_ex]
            sell_price = bids[sell_ex]

            if sell_price > buy_price and buy_price > 0:
                diff = ((sell_price - buy_price) / buy_price) * 100
                
                if diff > 0:
                    data.append({
                        'Инструмент': symbol,
                        'КУПИТЬ (Ask) на': buy_ex.upper(),
                        'Цена покупки': buy_price,
                        'ПРОДАТЬ (Bid) на': sell_ex.upper(),
                        'Цена продажи': sell_price,
                        'Профит (%)': round(diff, 3)
                    })

    return pd.DataFrame(data)

# --- ИНТЕРФЕЙС ---
st.title("📊 Фьючерсный Арбитраж: Bid / Ask")
st.markdown("Скринер сравнивает цену **покупки (Ask)** на одной бирже с ценой **продажи (Bid)** на другой.")

st.sidebar.header("Настройки")

# ИСПРАВЛЕННЫЙ СЛАЙДЕР (добавлены опции)
refresh_sec = st.sidebar.select_slider(
    "Автообновление (сек)", 
    options=[0, 10, 30, 60, 300], 
    value=60
)

min_profit = st.sidebar.slider("Минимальный профит (%)", 0.0, 3.0, 0.8)

if refresh_sec > 0:
    autorefresh(refresh_sec)

# Получение данных
df = get_bid_ask_data()

if not df.empty:
    # Фильтрация и сортировка
    filtered_df = df[df['Профит (%)'] >= min_profit]
    
    if not filtered_df.empty:
        st.subheader(f"Найдено {len(filtered_df)} арбитражных окон")
        st.dataframe(
            filtered_df.sort_values('Профит (%)', ascending=False),
            use_container_width=True
        )
    else:
        st.info(f"Связок с доходностью выше {min_profit}% не найдено.")
else:
    st.warning("Данные не получены. Проверьте логи в сайдбаре. Если везде 'Блок IP', запустите скрипт локально.")

st.caption(f"Последнее обновление: {pd.Timestamp.now().strftime('%H:%M:%S')}")
