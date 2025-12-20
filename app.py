import streamlit as st
import ccxt
import pandas as pd
import streamlit.components.v1 as components
# Модуль time больше не нужен, так как запросы быстрые

st.set_page_config(page_title="Arbitrage Scanner (Optimized)", layout="wide")

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

# Список бирж для сканирования и базовая валюта
EXCHANGES = ['binance', 'bybit', 'kraken', 'gateio', 'huobi']
BASE_CURRENCY = 'USDT'

@st.cache_data(ttl=30)
def get_data_optimized():
    data = []
    ex_objects = {}
    
    st.sidebar.info("Загрузка данных со всех бирж...")

    # 1. Загружаем все цены ОДНИМ запросом для каждой биржи
    prices_by_exchange = {}
    for ex_id in EXCHANGES:
        try:
            ex_class = getattr(ccxt, ex_id)
            ex_obj = ex_class({'enableRateLimit': True})
            # Fetch_tickers получает все пары сразу
            tickers = ex_obj.fetch_tickers()
            # Сохраняем только нужные пары (например, к USDT)
            prices_by_exchange[ex_id] = {
                s: t['last'] for s, t in tickers.items() 
                if s.endswith(f'/{BASE_CURRENCY}') and t and 'last' in t
            }
        except Exception as e:
            st.warning(f"Ошибка загрузки данных с {ex_id}: {e}")
            continue

    # Получаем общий набор всех символов, которые есть хотя бы на 2 биржах
    all_symbols = set()
    for ex_id in prices_by_exchange:
        for symbol in prices_by_exchange[ex_id]:
            all_symbols.add(symbol)
    
    # Можно ограничить количество пар здесь, но теперь это не обязательно, т.к. код быстрый
    # limit_symbols = list(all_symbols)[:100] 

    # 2. Перебираем все символы и сравниваем цены (происходит мгновенно в памяти)
    for symbol in all_symbols:
        prices = {}
        for ex_id in prices_by_exchange:
            if symbol in prices_by_exchange[ex_id]:
                prices[ex_id] = prices_by_exchange[ex_id][symbol]
        
        # Если найдено 2 или более цены для одной монеты
        if len(prices) >= 2:
            min_ex = min(prices, key=prices.get)
            max_ex = max(prices, key=prices.get)
            min_p = prices[min_ex]
            max_p = prices[max_ex]
            diff = ((max_p - min_p) / min_p) * 100
            
            if diff > 0:
                data.append({
                    'Монета': symbol,
                    'Купить на': min_ex.upper(),
                    'Цена покупки': f"{min_p:,.4f}",
                    'Продать на': max_ex.upper(),
                    'Цена продажи': f"{max_p:,.4f}",
                    'Профит (%)': round(diff, 3)
                })

    return pd.DataFrame(data)

# --- ИНТЕРФЕЙС ---
st.title("🚀 Crypto Arbitrage Scanner (Optimized)")

st.sidebar.header("Настройки")
refresh_sec = st.sidebar.select_slider("Обновление (сек)", options=, value=60)
min_profit = st.sidebar.slider("Мин. профит (%)", 0.0, 5.0, 0.3)

if refresh_sec > 0:
    autorefresh(refresh_sec)

try:
    df = get_data_optimized() 
    if not df.empty:
        filtered_df = df[df['Профит (%)'] >= min_profit]
        st.subheader(f"Найдено {len(filtered_df)} связок с профитом > {min_profit}%")
        
        st.dataframe(
            filtered_df.sort_values('Профит (%)', ascending=False)
            .style.background_gradient(cmap='plasma', subset=['Профит (%)']),
            use_container_width=True
        )
    else:
        st.warning("Биржи временно недоступны или нет данных. Попробуйте обновить через минуту.")
except Exception as e:
    st.error(f"Произошла критическая ошибка: {e}")

st.caption(f"Последнее обновление: {pd.Timestamp.now().strftime('%H:%M:%S')}")
