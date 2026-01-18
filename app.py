import streamlit as st
import ccxt
import pandas as pd
import streamlit.components.v1 as components

st.set_page_config(page_title="Arbitrage Scanner 2026", layout="wide")

# Биржи для 2026: MEXC и Gate часто имеют самый большой спред к DEX
CEX_LIST = ['mexc', 'gateio', 'bitget', 'okx', 'bybit']

@st.cache_data(ttl=15)
def get_all_data(min_spread, min_vol):
    all_results = []
    
    # 1. Инициализация DEX
    try:
        dex = ccxt.hyperliquid({'enableRateLimit': True})
        dex.load_markets() # КРИТИЧНО для 2026 года
        dex_tickers = dex.fetch_tickers()
        st.sidebar.success(f"DEX: {len(dex_tickers)} пар получено")
    except Exception as e:
        st.sidebar.error(f"DEX Error: {e}")
        return pd.DataFrame()

    # 2. Перебор CEX
    for cex_id in CEX_LIST:
        try:
            cex = getattr(ccxt, cex_id)({'enableRateLimit': True, 'options': {'defaultType': 'swap'}})
            cex.load_markets()
            cex_tickers = cex.fetch_tickers()
            
            # Сопоставление
            for d_sym, d_tick in dex_tickers.items():
                # Очищаем имя (Hyperliquid часто добавляет :USDC или /USDC)
                base = d_sym.split('/')[0].split(':')[0].split('-')[0].upper()
                
                # Ищем похожий символ на CEX
                target_symbol = next((s for s in cex_tickers.keys() if s.startswith(base + "/")), None)
                
                if target_symbol:
                    c_tick = cex_tickers[target_symbol]
                    
                    # Цены (средние между bid/ask)
                    p_dex = (d_tick['ask'] + d_tick['bid']) / 2 if d_tick['ask'] else d_tick['last']
                    p_cex = (c_tick['ask'] + c_tick['bid']) / 2 if c_tick['ask'] else c_tick['last']
                    
                    if not p_dex or not p_cex: continue
                    
                    vol = c_tick.get('quoteVolume', 0)
                    diff = ((p_cex - p_dex) / p_dex) * 100
                    
                    if abs(diff) >= min_spread and vol >= min_vol:
                        all_results.append({
                            'Asset': base,
                            'Buy': "DEX" if diff > 0 else cex_id.upper(),
                            'Sell': cex_id.upper() if diff > 0 else "DEX",
                            'Spread %': round(abs(diff), 3),
                            'DEX Price': round(p_dex, 6),
                            'CEX Price': round(p_cex, 6),
                            'Vol 24h ($)': int(vol)
                        })
        except Exception as e:
            continue

    return pd.DataFrame(all_results)

# --- UI ---
st.sidebar.header("Фильтры 2026")
s_spread = st.sidebar.slider("Мин. спред %", 0.0, 1.0, 0.8, step=0.01) # Снизил до 0.05 для теста
s_vol = st.sidebar.number_input("Мин. объем ($)", 0, 1000000, 10000)

if st.sidebar.button("SCAN NOW"):
    st.cache_data.clear() # Очистка кеша для свежих данных

df = get_all_data(s_spread, s_vol)

if not df.empty:
    df = df.sort_values('Spread %', ascending=False).drop_duplicates(subset=['Asset'])
    st.success(f"Найдено {len(df)} потенциальных связок")
    st.dataframe(df, use_container_width=True)
else:
    st.warning("Связки не найдены. Попробуйте поставить 'Мин. спред' на 0.01 для проверки связи.")

st.caption(f"Текущее время системы: {pd.Timestamp.now()} | CCXT Version: {ccxt.__version__}")
