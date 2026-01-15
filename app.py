import streamlit as st
import ccxt
import pandas as pd
import streamlit.components.v1 as components

# --- Настройка страницы ---
st.set_page_config(page_title="Funding Arbitrage 2026", layout="wide")

# Функция звука из вашего рабочего варианта (JS)
def play_sound():
    sound_js = """
        <script>
        var context = new (window.AudioContext || window.webkitAudioContext)();
        var oscillator = context.createOscillator();
        oscillator.type = 'sine';
        oscillator.frequency.setValueAtTime(523.25, context.currentTime); 
        oscillator.connect(context.destination);
        oscillator.start();
        setTimeout(function() { oscillator.stop(); }, 500); 
        </script>
    """
    components.html(sound_js, height=0)

def autorefresh(interval_seconds):
    if interval_seconds > 0:
        components.html(
            f"<script>setTimeout(function() {{ window.parent.location.reload(); }}, {interval_seconds * 1000});</script>",
            height=0,
        )

# Список бирж (поддерживающих фьючерсы)
EXCHANGES = ['okx', 'bybit', 'binance', 'bitget', 'gateio']

@st.cache_data(ttl=20)
def get_funding_data(min_funding, max_entry_spread):
    results = []
    
    for ex_id in EXCHANGES:
        try:
            # Инициализация биржи для фьючерсов
            ex = getattr(ccxt, ex_id)({
                'enableRateLimit': True,
                'options': {'defaultType': 'swap'}
            })
            
            # 1. Получаем все ставки финансирования
            funding_data = ex.fetch_funding_rates()
            
            # 2. Получаем тикеры для проверки спреда (Spot vs Futures)
            # Для этого создаем второй объект биржи для спота
            ex_spot = getattr(ccxt, ex_id)({'options': {'defaultType': 'spot'}})
            spot_tickers = ex_spot.fetch_tickers()
            futures_tickers = ex.fetch_tickers()
            
            for symbol, data in funding_data.items():
                funding_rate = data.get('fundingRate', 0)
                
                # Фильтруем только высокие положительные ставки (платит шортистам)
                if funding_rate >= (min_funding / 100):
                    
                    # Проверяем наличие цен и на споте и на фьючерсах на ОДНОЙ бирже
                    # (Внутрибиржевой арбитраж фандинга самый безопасный)
                    base_sym = symbol.split(':')[0] # BTC/USDT
                    if base_sym in spot_tickers and symbol in futures_tickers:
                        
                        spot_ask = spot_tickers[base_sym]['ask']      # Цена покупки на споте
                        futures_bid = futures_tickers[symbol]['bid']  # Цена шорта на фьючерсах
                        
                        if spot_ask and futures_bid:
                            # Спред входа: сколько мы теряем при мгновенном открытии
                            entry_spread = ((spot_ask - futures_bid) / spot_ask) * 100
                            
                            if entry_spread <= max_entry_spread:
                                # Сколько выплат фандинга нужно для окупаемости спреда (обычно 3 выплаты в сутки)
                                # Упрощенно: entry_spread / (funding_rate * 100)
                                breakeven_hours = (entry_spread / (funding_rate * 100)) * 8
                                
                                results.append({
                                    'Биржа': ex_id.upper(),
                                    'Символ': base_sym,
                                    'Funding (%)': round(funding_rate * 100, 4),
                                    'APR (%)': round(funding_rate * 100 * 3 * 365, 2),
                                    'Спред входа (%)': round(entry_spread, 3),
                                    'Окупаемость (часов)': round(breakeven_hours, 1),
                                    'Next Pay': data.get('datetime', 'N/A')[-8:-3]
                                })
        except Exception as e:
            continue
            
    return pd.DataFrame(results)

# --- ИНТЕРФЕЙС ---
st.title("💸 Скринер Арбитража Фандинга (Spot-Futures)")
st.info("Стратегия: BUY Spot + SELL Futures. Зарабатываем на положительной ставке Funding.")

with st.sidebar:
    st.header("⚙️ Фильтры")
    min_f = st.number_input("Мин. Funding за период (%)", 0.001, 1.0, 0.01, format="%.3f")
    max_s = st.slider("Макс. спред входа (%)", -1.0, 2.0, 0.1)
    
    refresh_options = [30, 60, 300, 600]
    ref_sec = st.select_slider("Обновление (сек)", options=refresh_options, value=60)
    
    st.header("🔔 Алерт")
    alert_val = st.number_input("Звук если APR > %", 10, 1000, 50)
    
autorefresh(ref_sec)

data_df = get_funding_data(min_f, max_s)

if not data_df.empty:
    # Сортировка по доходности
    data_df = data_df.sort_values('APR (%)', ascending=False)
    
    # Проверка на алерт
    top_apr = data_df['APR (%)'].iloc[0]
    if top_apr >= alert_val:
        play_sound()
        st.toast(f"🚀 Найдена доходность: {top_apr}% APR")

    # Отображение
    st.subheader("Найденные возможности")
    
    # Красивое форматирование таблицы
    def color_apr(val):
        color = 'green' if val > 30 else 'white'
        return f'color: {color}'

    st.dataframe(
        data_df.style.applymap(color_apr, subset=['APR (%)']),
        use_container_width=True
    )
    
    st.markdown("""
    **Как читать таблицу:**
    * **APR (%)**: Прогнозируемая годовая доходность, если ставка не изменится.
    * **Спред входа**: Разница между покупкой спота и шортом. Чем ниже, тем лучше.
    * **Окупаемость**: Через сколько часов доход от выплат фандинга полностью покроет ваши затраты на вход (спред).
    """)
else:
    st.warning("Подходящих связок не найдено. Попробуйте увеличить 'Макс. спред входа' или уменьшить 'Мин. Funding'.")

st.caption(f"Данные актуальны на 2026 год. Последнее обновление: {pd.Timestamp.now().strftime('%H:%M:%S')}")
