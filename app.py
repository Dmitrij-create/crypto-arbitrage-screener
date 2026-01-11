import streamlit as st
import ccxt
import pandas as pd
import streamlit.components.v1 as components

# Настройка страницы
st.set_page_config(page_title="Futures Bid/Ask Screener", layout="wide")

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
EXCHANGES = ['gateio', 'okx', 'mexc', 'bingx', 'bitget']
BASE_CURRENCY = 'USDT'

# <<< НОВОЕ: Переменная для хранения минимального объема (будет задаваться через UI)
# MAX_INTERNAL_SPREAD_PERCENT = 0.5 # Эта константа была перенесена ниже в UI настройки

@st.cache_data(ttl=10) # Кэш 10 секунд для актуальности цен
def get_bid_ask_data(max_internal_spread_percent, min_volume_usdt): # <<< ИЗМЕНЕНО: Функция принимает параметры
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
                # Проверяем пару и наличие цен покупки/продажи и объема
                is_usdt_pair = f'{BASE_CURRENCY}' in s
                has_prices = t.get('bid') and t.get('ask')
                volume_24h = t.get('quoteVolume') # В ccxt 'quoteVolume' обычно означает объем в базовой валюте (USDT)
                
                # <<< НОВОЕ/ИЗМЕНЕНО: Добавляем проверку объема
                has_volume = volume_24h is not None and volume_24h >= min_volume_usdt

                if is_usdt_pair and has_prices and has_volume:
                    bid = t['bid']
                    ask = t['ask']
                    
                    # Проверка внутреннего спреда
                    if bid and ask and bid > 0:
                        internal_spread = ((ask - bid) / bid) * 100
                        
                        if internal_spread <= max_internal_spread_percent:
                            # Нормализуем название (убираем :USDT или /USDT)
                            base_symbol = s.replace(f'/{BASE_CURRENCY}', '').replace(f':{BASE_CURRENCY}', '')
                            cleaned_data[base_symbol] = {
                                'bid': bid,
                                'ask': ask,
                                'volume': volume_24h # Сохраняем объем для вывода
                            }
            
            if cleaned_data:
                prices_by_exchange[ex_id] = cleaned_data
                st.sidebar.success(f"{ex_id.upper()}: OK ({len(cleaned_data)} пар прошли фильтры)")
        except Exception as e:
            err_msg = str(e)
            if "403" in err_msg:
                st.sidebar.error(f"{ex_id.upper()}: Блок IP (403)")
            else:
                st.sidebar.warning(f"{ex_id.upper()}: Ошибка API")
            continue

    # Собираем все уникальные инструменты для межбиржевого сравнения
    all_symbols = set()
    for ex_id in prices_by_exchange:
        all_symbols.update(prices_by_exchange[ex_id].keys())
    
    for symbol in all_symbols:
        bids = {}
        asks = {}
        volumes = {} # <<< НОВОЕ: Словарь для объемов
        for ex_id in prices_by_exchange:
            if symbol in prices_by_exchange[ex_id]:
                bids[ex_id] = prices_by_exchange[ex_id][symbol]['bid']
                asks[ex_id] = prices_by_exchange[ex_id][symbol]['ask']
                volumes[ex_id] = prices_by_exchange[ex_id][symbol]['volume'] # <<< НОВОЕ: Собираем объемы

        
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
                        'Цена покупки': round(buy_price, 6),
                        'ПРОДАТЬ (Bid) на': sell_ex.upper(),
                        'Цена продажи': round(sell_price, 6),
                        'Объем (24ч, Max)': round(max(volumes.values()), 0), # <<< НОВОЕ: Добавляем максимальный объем для наглядности
                        'Профит (%)': round(diff, 3)
                    })

    return pd.DataFrame(data)

# --- ИНТЕРФЕЙС ---
st.title("📊 Фьючерсный Арбитраж: Bid / Ask")

st.sidebar.header("Настройки")

# --- UI Фильтры ---

max_internal_spread = st.sidebar.slider(
    "Макс. внутр. спред Bid/Ask (%)", 
    0.0, 1.0, 0.3, step=0.05
)

min_volume = st.sidebar.slider(
    "Мин. объем торгов (USDT, 24ч)", 
    0, 5000000, 100000, step=50000
)

# ИСПРАВЛЕННЫЙ СЛАЙДЕР (добавлены опции)
refresh_sec = st.sidebar.select_slider(
    "Автообновление (сек)", 
    options=[0, 10, 30, 60, 300], 
    value=60
)

min_profit = st.sidebar.slider("Минимальный межбиржевой профит (%)", 0.0, 3.0, 0.8)

st.markdown(f"Скринер сравнивает цены между биржами, фильтруя пары с внутренним спредом **<{max_internal_spread}%** и объемом **>{min_volume:,} USDT**.")


if refresh_sec > 0:
    autorefresh(refresh_sec)

# Получение данных с передачей параметров фильтров
df = get_bid_ask_data(max_internal_spread, min_volume) # <<< ИЗМЕНЕНО: Вызов функции с параметрами

if not df.empty:
    # Фильтрация и сортировка
    filtered_df = df[df['Профит (%)'] >= min_profit]
    
    if not filtered_df.empty:
        st.subheader(f"Найдено {len(filtered_df)} арбитражных окон")
        # Улучшенное форматирование таблицы
        st.dataframe(
            filtered_df.sort_values('Профит (%)', ascending=False),
            use_container_width=True,
            column_config={
                'Цена покупки': st.column_config.NumberColumn(format="%.6f"),
                'Цена продажи': st.column_config.NumberColumn(format="%.6f"),
                'Профит (%)': st.column_config.NumberColumn(format="%.3f %%"),
                'Объем (24ч, Max)': st.column_config.NumberColumn(format="%,.0f"),
            }
        )
    else:
        st.info(f"Связок с доходностью выше {min_profit}% не найдено, удовлетворяющих всем фильтрам.")
else:
    st.warning("Данные не получены. Проверьте логи в сайдбаре. Если везде 'Блок IP', запустите скрипт локально.")

st.caption(f"Последнее обновление: {pd.Timestamp.now().strftime('%H:%M:%S')}")
