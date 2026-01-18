import streamlit as st
import pandas as pd
import asyncio
import ccxt.pro as ccxtpro
from datetime import datetime

st.set_page_config(page_title="Liquidation Tracker 2026", layout="wide")

# --- Инициализация состояния ---
if 'liq_data' not in st.session_state:
    st.session_state['liq_data'] = []

st.title("🔥 Crypto Liquidation Tracker 2026")
st.markdown("Мониторинг крупных ликвидаций на фьючерсном рынке в реальном времени.")

# --- Сайдбар с фильтрами ---
with st.sidebar:
    st.header("Фильтры")
    min_amount = st.number_input("Мин. объем ликвидации ($)", 0, 1000000, 1000)
    max_rows = st.slider("Показывать последних записей", 10, 100, 30)
    exchanges = st.multiselect("Биржи", ['binance', 'bybit', 'okx', 'bitget'], default=['binance', 'bybit'])
    
    if st.button("Очистить список"):
        st.session_state['liq_data'] = []
        st.rerun()

# --- Логика сбора данных ---
async def watch_liquidations(exchange_id):
    # Используем CCXT Pro для работы с вебсокетами
    exchange = getattr(ccxtpro, exchange_id)({
        'enableRateLimit': True,
        'options': {'defaultType': 'swap'}
    })
    
    while True:
        try:
            # Метод watch_liquidations поддерживается для крупнейших бирж в 2026
            liquidation = await exchange.watch_liquidations()
            
            # Обработка данных
            for liq in liquidation:
                symbol = liq['symbol']
                side = liq['side'].upper() # SELL (Long liq) или BUY (Short liq)
                price = liq['price']
                amount_crypto = liq['amount']
                amount_usd = amount_crypto * price
                
                if amount_usd >= min_amount:
                    new_entry = {
                        'Время': datetime.now().strftime('%H:%M:%S'),
                        'Биржа': exchange_id.upper(),
                        'Актив': symbol.split(':')[0],
                        'Тип': 'LONG (Sell)' if side == 'SELL' else 'SHORT (Buy)',
                        'Объем $': round(amount_usd, 2),
                        'Цена': price
                    }
                    st.session_state['liq_data'].insert(0, new_entry)
                    
                    # Ограничиваем размер списка
                    if len(st.session_state['liq_data']) > max_rows:
                        st.session_state['liq_data'] = st.session_state['liq_data'][:max_rows]
                        
        except Exception as e:
            # В случае ошибки API (например, монета не поддерживает ликвы)
            await asyncio.sleep(1)
            continue
        finally:
            await exchange.close()

# --- Отображение данных ---
placeholder = st.empty()

with placeholder.container():
    if st.session_state['liq_data']:
        df = pd.DataFrame(st.session_state['liq_data'])
        
        # Стилизация: подсвечиваем лонги красным, шорты зеленым
        def highlight_type(val):
            color = '#ff4b4b' if 'LONG' in val else '#00cc66'
            return f'color: {color}; font-weight: bold'

        st.dataframe(
            df.style.applymap(highlight_type, subset=['Тип']),
            use_container_width=True,
            height=600
        )
    else:
        st.info("Ожидание данных о ликвидациях... (Попробуйте снизить минимальный объем)")

# --- Запуск циклов ---
# В Streamlit сложно запускать бесконечные асинхронные циклы напрямую в UI.
# Для полноценного трекера рекомендуется использовать внешнюю БД или 
# запускать этот скрипт как отдельный процесс, а Streamlit будет только читать файл.
