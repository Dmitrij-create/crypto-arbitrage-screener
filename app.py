import streamlit as st
import ccxt
import pandas as pd
import streamlit.components.v1 as components

st.set_page_config(page_title="Futures Arbitrage Scanner (Bid/Ask)", layout="wide")

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

EXCHANGES = ['binance', 'bybit', 'huobi', 'gateio', 'okx', 'mexc', 'bingx', 'bitget']
BASE_CURRENCY = 'USDT'

@st.cache_data(ttl=15) # Уменьшаем кэш до 15 сек, так как bid/ask быстро меняются
def get_futures_data_bid_ask():
    data = []
    # Теперь мы храним и bid, и ask для каждой биржи
    bid_ask_by_exchange = {} 
    
    st.sidebar.info("Сканирование цен Bid/Ask...")

    for ex_id in EXCHANGES:
        try:
            ex_class = getattr(ccxt, ex_id)
            ex_obj = ex_class({'enableRateLimit': True, 'options': {'defaultType': 'swap'}}) 
            
            tickers = ex_obj.fetch_tickers()
            
            cleaned_market_data = {}
            for s, t in tickers.items():
                # Проверяем наличие bid И ask цены
                if f'{BASE_CURRENCY}' in s and t.get('bid') and t.get('ask'):
                    base_symbol = s.split(':')
                    cleaned_market_data[base_symbol] = {
                        'bid': t['bid'],
                        'ask': t['ask']
                    }
            
            if cleaned_market_data:
                bid_ask_by_exchange[ex_id] = cleaned_market_data
                st.sidebar.success(f"{ex_id.upper()}: OK ({len(cleaned_market_data)} пар)")
        except Exception as e:
            err_msg = str(e)
            if "403" in err_msg or "blocked" in err_msg:
                st.sidebar.error(f"{ex_id.upper()}: Блок IP (403)")
            else:
                st.sidebar.warning(f"{ex_id.upper()}: Ошибка API")
            continue

    all_symbols = set()
    for ex_id in bid_ask_by_exchange:
        all_symbols.update(bid_ask_by_exchange[ex_id].keys())
    
    for symbol in all_symbols:
        # Собираем все bid и ask цены для этого символа
        bids = {}
        asks = {}
        for ex_id in bid_ask_by_exchange:
            if symbol in bid_ask_by_exchange[ex_id]:
                bids[ex_id] = bid_ask_by_exchange[ex_id][symbol]['bid']
                asks[ex_id] = bid_ask_by_exchange[ex_id][symbol]['ask']
        
        # Нужно минимум 2 биржи с данными
        if len(bids) >= 2 and len(asks) >= 2:
            # Ищем, где купить дешевле (Min Ask) и где продать дороже (Max Bid)
            buy_ex = min(asks, key=asks.get)
            sell_ex = max(bids, key=bids.get)
            
            # Цена покупки = Ask, Цена продажи = Bid
            buy_price = asks[buy_ex]
            sell_price = bids[sell_ex]

            if buy_price > 0 and sell_price > buy_price:
                # Расчет профита на основе реальных цен входа/выхода
                diff = ((sell_price - buy_price) / buy_price) * 100
                
                if diff > 0:
                    data.append({
                        'Инструмент': symbol,
                        'Купить (Ask) на': buy_ex.upper(),
                        'Цена покупки': buy_price,
                        'Продать (Bid) на': sell_ex.upper(),
                        'Цена продажи': sell_price,
                        'Профит (%)': round(diff, 3)
                    })

    return pd.DataFrame(data)

# --- ИНТЕРФЕЙС ---
st.title("📊 Фьючерсный Арбитраж (Bid/Ask)")

st.sidebar.header("Настройки")
refresh_sec = st.sidebar.select_slider("Обновление (сек)", options=, value=30)
min_profit = st.sidebar.slider("Мин. профит (%)", 0.0, 5.0, 0.1)

if refresh_sec > 0:
    autorefresh(refresh_sec)

df = get_futures_data_bid_ask()

if not df.empty:
    filtered_df = df[df['Профит (%)'] >= min_profit]
    if not filtered_df.empty:
        st.dataframe(
            filtered_df.sort_values('Профит (%)', ascending=False),
            use_container_width=True
        )
    else:
        st.info(f"Нет связок с профитом выше {min_profit}%")
else:
    st.warning("Данные не получены. Скорее всего, биржи заблокировали IP облачного сервера. Запустите скрипт ЛОКАЛЬНО.")

st.caption(f"Обновлено: {pd.Timestamp.now().strftime('%H:%M:%S')}")
