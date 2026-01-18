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
             
def get_dex_cex_data(invest_amount, min_diff, min_v_filter):
    results = []
    
    try:
        # 1. Загружаем DEX (Hyperliquid)
        dex_ex = ccxt.hyperliquid()
        dex_tickers = dex_ex.fetch_tickers()
        st.sidebar.write(f"DEX пар загружено: {len(dex_tickers)}") # Для теста
    except Exception as e:
        st.error(f"Ошибка DEX: {e}")
        return pd.DataFrame()

    # 2. Перебираем CEX
    for cex_id in CEX_LIST:
        try:
            cex_ex = getattr(ccxt, cex_id)({'options': {'defaultType': 'swap'}})
            cex_tickers = cex_ex.fetch_tickers()
            
            for dex_symbol, dex_t in dex_tickers.items():
                # --- УЛУЧШЕННАЯ НОРМАЛИЗАЦИЯ ИМЕНИ ---
                # Превращаем "BTC/USDC:USDC" или "BTC-P" в "BTC"
                base_name = dex_symbol.split('/')[0].split('-')[0].split(':')[0].upper()
                
                # Ищем совпадение на CEX (ищем ключ, содержащий base_name)
                # Например, ищем "BTC" в "BTC/USDT:USDT"
                cex_match = None
                for s in cex_tickers.keys():
                    if s.startswith(base_name + "/") or s.startswith(base_name + ":"):
                        cex_match = s
                        break
                
                if cex_match:
                    cex_t = cex_tickers[cex_match]
                    
                    # Проверка объема (иногда на DEX он меньше, берем CEX)
                    vol = cex_t.get('quoteVolume', 0)
                    if vol < min_v_filter:
                        continue

                    p_dex = (dex_t['ask'] + dex_t['bid']) / 2
                    p_cex = (cex_t['ask'] + cex_t['bid']) / 2
                    
                    if p_dex == 0 or p_cex == 0: continue
                    
                    diff = ((p_cex - p_dex) / p_dex) * 100
                    
                    if abs(diff) >= min_diff:
                        results.append({
                            'Монета': base_name,
                            'Купить': "DEX" if diff > 0 else cex_id.upper(),
                            'Продать': cex_id.upper() if diff > 0 else "DEX",
                            'Спред %': round(abs(diff), 3),
                            'DEX Цена': f"{p_dex:.4f}",
                            'CEX Цена': f"{p_cex:.4f}",
                            'Объем CEX $': int(vol)
                        })
        except Exception as e:
            st.sidebar.error(f"Ошибка {cex_id}: {e}")
            continue
            
    return pd.DataFrame(results)


# --- UI ---
st.title("🔗 DEX/CEX Perp Arbitrage 2026")
st.markdown("Сравнение цен между **Hyperliquid (L1 DEX)** и основными фьючерсными биржами.")

with st.sidebar:
    st.header("Параметры")
    amount = st.number_input("Объем сделки ($)", 10, 50000, 10)
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
