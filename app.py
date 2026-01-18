import streamlit as st
import ccxt
import pandas as pd
import time
import streamlit.components.v1 as components

st.set_page_config(page_title="Precise Arbitrage 2026", layout="wide")

# --- Функция автообновления через JavaScript ---
def autorefresh(interval_seconds):
    if interval_seconds > 0:
        # JS код для перезагрузки страницы через заданный интервал
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

# --- Настройки бирж ---
CEX_LIST = ['binance', 'bybit', 'okx', 'mexc', 'gateio']

@st.cache_data(ttl=5)
def get_precise_data(min_spread, min_vol):
    results = []
    try:
        dex = ccxt.hyperliquid()
        dex_tickers = dex.fetch_tickers()
    except Exception as e:
        st.error(f"DEX API Error: {e}")
        return pd.DataFrame()

    for cex_id in CEX_LIST:
        try:
            cex = getattr(ccxt, cex_id)({
                'enableRateLimit': True, 
                'options': {'defaultType': 'swap'} 
            })
            cex_tickers = cex.fetch_tickers()
            
            for d_sym, d_tick in dex_tickers.items():
                base = d_sym.split('/')[0].split(':')[0].split('-')[0].upper()
                
                target_symbol = None
                for s in cex_tickers.keys():
                    if s.startswith(base + "/") and (":USDT" in s or ":USDC" in s):
                        target_symbol = s
                        break
                
                if target_symbol:
                    c_tick = cex_tickers[target_symbol]
                    
                    # Ситуация А: Buy DEX / Sell CEX
                    if d_tick['ask'] and c_tick['bid'] and d_tick['ask'] > 0:
                        diff_a = ((c_tick['bid'] - d_tick['ask']) / d_tick['ask']) * 100
                        if diff_a >= min_spread:
                            add_row(results, base, "DEX", cex_id, d_tick['ask'], c_tick['bid'], diff_a, c_tick)

                    # Ситуация Б: Buy CEX / Sell DEX
                    if c_tick['ask'] and d_tick['bid'] and c_tick['ask'] > 0:
                        diff_b = ((d_tick['bid'] - c_tick['ask']) / c_tick['ask']) * 100
                        if diff_b >= min_spread:
                            add_row(results, base, cex_id, "DEX", c_tick['ask'], d_tick['bid'], diff_b, c_tick)
        except: continue
    return pd.DataFrame(results)

def add_row(res_list, asset, buy_ex, sell_ex, p_buy, p_sell, diff, c_tick):
    vol = c_tick.get('quoteVolume', 0)
    res_list.append({
        'Монета': asset,
        'КУПИТЬ': buy_ex.upper(),
        'ПРОДАТЬ': sell_ex.upper(),
        'Спред %': round(diff, 3),
        'Цена Покупки': f"{p_buy:.6f}",
        'Цена Продажи': f"{p_sell:.6f}",
        'Объем CEX $': int(vol)
    })

# --- ИНТЕРФЕЙС ---
st.title("🎯 Precise DEX/CEX Arbitrage 2026")

with st.sidebar:
    st.header("⚙️ Настройки")
    
    # Выбор интервала обновления
    refresh_interval = st.selectbox(
        "Интервал обновления",
        options=[10, 30, 60, 300, 0],
        format_func=lambda x: f"{x} секунд" if x > 0 else "Выключено",
        index=1 # По умолчанию 30 секунд
    )
    
    min_s = st.slider("Мин. спред %", 0.01, 1.0, 0.8)
    min_v = st.number_input("Мин. объем ($)", 0, 1000000, 50000)
    
    if st.button("🔄 ОБНОВИТЬ СЕЙЧАС"):
        st.cache_data.clear()
        st.rerun()

# Запуск автообновления
if refresh_interval > 0:
    autorefresh(refresh_interval)

# Индикатор работы
status_placeholder = st.empty()
status_placeholder.caption(f"Последнее обновление: {time.strftime('%H:%M:%S')} | Автообновление: {refresh_interval}с")

df = get_precise_data(min_s, min_v)

if not df.empty:
    df = df.sort_values('Спред %', ascending=False).drop_duplicates(subset=['Монета', 'КУПИТЬ'])
    st.dataframe(df, use_container_width=True, height=600)
else:
    st.info("Реальных спредов по ценам Bid/Ask не найдено. Ожидание данных...")

st.markdown(f"""
<div style="font-size: 0.8rem; color: gray;">
    * <b>DEX:</b> Hyperliquid (USDC base) | <b>CEX:</b> USDT-Margined Futures<br>
    * Расчет ведется по ценам <b>Best Ask</b> для покупки и <b>Best Bid</b> для продажи.<br>
    * Текущая дата: 18 января 2026 г.
</div>
""", unsafe_allow_html=True)
