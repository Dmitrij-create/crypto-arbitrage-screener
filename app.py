import streamlit as st
import ccxt
import pandas as pd
import streamlit.components.v1 as components

st.set_page_config(page_title="DEX/CEX Arbitrage 2026", layout="wide")

# --- Настройки ---
# Hyperliquid — лидер DEX Perps в 2026 году. Также можно добавить dYdX или GMX.
CEX_LIST = ['mexc', 'bitget', 'okx','bingx','gate']
BASE_CURRENCY = 'USDT'

def play_sound():
    components.html("<script>var context = new (window.AudioContext || window.webkitAudioContext)(); var osc = context.createOscillator(); osc.connect(context.destination); osc.start(); setTimeout(()=>osc.stop(), 400);</script>", height=0)

def autorefresh(interval):
    if interval > 0:
        components.html(f"<script>setTimeout(()=>window.parent.location.reload(), {interval*1000});</script>", height=0)

@st.cache_data(ttl=10)
def get_dex_cex_data(invest_amount, min_diff):
    results = []
    
    # 1. Получаем данные с Hyperliquid (DEX) через CCXT (поддерживается в 2026)
    try:
        hyperliquid = ccxt.hyperliquid({'enableRateLimit': True})
        dex_tickers = hyperliquid.fetch_tickers()
    except Exception as e:
        st.error(f"Ошибка подключения к Hyperliquid: {e}")
        return pd.DataFrame()

    # 2. Получаем данные с CEX
    for cex_id in CEX_LIST:
        try:
            cex_obj = getattr(ccxt, cex_id)({'enableRateLimit': True, 'options': {'defaultType': 'swap'}})
            cex_tickers = cex_obj.fetch_tickers()
            
            # 3. Сравниваем пары
            for symbol, dex_t in dex_tickers.items():
                # Приводим к общему формату (например, BTC/USDT:USDT)
                clean_sym = symbol.split(':')[0].replace('/USDC', '').replace('/USDT', '')
                
                # Ищем эту же монету на CEX
                for cex_sym, cex_t in cex_tickers.items():
                    if clean_sym in cex_sym:
                        p_dex = (dex_t['ask'] + dex_t['bid']) / 2
                        p_cex = (cex_t['ask'] + cex_t['bid']) / 2
                        
                        diff = ((p_cex - p_dex) / p_dex) * 100
                        
                        # Арбитражная ситуация
                        if abs(diff) > min_diff:
                            buy_place = "Hyperliquid (DEX)" if diff > 0 else cex_id.upper()
                            sell_place = cex_id.upper() if diff > 0 else "Hyperliquid (DEX)"
                            
                            results.append({
                                'Asset': clean_sym,
                                'Buy At': buy_place,
                                'Sell At': sell_place,
                                'Spread %': round(abs(diff), 3),
                                'DEX Price': p_dex,
                                'CEX Price': p_cex,
                                'Est. Profit $': round(invest_amount * (abs(diff)/100), 2)
                            })
        except:
            continue
            
    return pd.DataFrame(results)

# --- UI ---
st.title("🔗 DEX/CEX Perp Arbitrage 2026")
st.markdown("Сравнение цен между **Hyperliquid (L1 DEX)** и основными фьючерсными биржами.")

with st.sidebar:
    st.header("Параметры")
    amount = st.number_input("Объем сделки ($)", 100, 50000, 1000)
    min_spread = st.slider("Мин. спред %", 0.05, 2.0, 0.2)
    refresh = st.select_slider("Обновление", options=[15, 30, 60, 120], value=30)
    if st.button("Проверить сейчас"):
        st.rerun()

autorefresh(refresh)

with st.spinner("Синхронизация блокчейна и лимитных ордеров..."):
    df = get_dex_cex_data(amount, min_spread)

if not df.empty:
    # Сортируем по максимальному профиту
    df = df.sort_values('Spread %', ascending=False).drop_duplicates(subset=['Asset'])
    
    # Звуковой алерт на жирный спред
    if df['Spread %'].max() > 0.5:
        play_sound()
        st.success(f"🚀 Найдена DEX связка: {df['Spread %'].max()}%")

    st.table(df)
    
    st.warning("""
    **Важно для 2026 года:**
    1. **Gas Fee**: Работа на DEX требует наличия нативного токена (HYPE или ETH) для оплаты газа.
    2. **Slippage**: На DEX ликвидность может быть ниже, чем на Binance. Проверяйте размер стакана перед входом.
    3. **Bridge**: Учитывайте время на перевод средств между CEX и вашим кошельком (Arbitrum/Hyperliquid).
    """)
else:
    st.info("Спредов между DEX и CEX выше порога не найдено. Ждем синхронизации...")

st.caption(f"Данные обновлены: {pd.Timestamp.now().strftime('%H:%M:%S')}. Используется Hyperliquid API v1.")
