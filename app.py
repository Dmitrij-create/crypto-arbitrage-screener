import streamlit as st
import ccxt
import pandas as pd  # ИСПРАВЛЕНО ЗДЕСЬ
import time
import streamlit.components.v1 as components

st.set_page_config(page_title="Futures Hedge Scanner 2026", layout="wide")

# --- Функция автообновления через JS ---
def autorefresh(interval_seconds):
    if interval_seconds > 0:
        components.html(
            f"<script>setTimeout(function() {{ window.parent.location.reload(); }}, {interval_seconds * 1000});</script>",
            height=0,
        )

# Только топовые биржи для фьючерсного арбитража (без переводов)
CEX_LIST = ['bingx', 'gateio', 'okx', 'bitget', 'mexc']

@st.cache_data(ttl=5)
def get_futures_spreads(min_spread, min_vol):
    results = []
    
    # 1. Данные с Hyperliquid (DEX Perp)
    try:
        dex = ccxt.hyperliquid({'enableRateLimit': True})
        dex_tickers = dex.fetch_tickers()
    except:
        return pd.DataFrame()

    # 2. Данные с CEX (только USDT-M Futures)
    for cex_id in CEX_LIST:
        try:
            cex = getattr(ccxt, cex_id)({
                'enableRateLimit': True, 
                'options': {'defaultType': 'swap'} 
            })
            cex_tickers = cex.fetch_tickers()
            
            for d_sym, d_tick in dex_tickers.items():
                # Нормализация тикера: "BTC/USDC:USDC" -> "BTC"
                base = d_sym.split('/')[0].split(':')[0].split('-')[0].upper()
                
                # Ищем фьючерс на CEX (BTC/USDT:USDT)
                target = next((s for s in cex_tickers.keys() if s.startswith(base + "/")), None)
                
                if target:
                    c_tick = cex_tickers[target]
                    vol = c_tick.get('quoteVolume', 0)
                    
                    if vol < min_vol: continue

                    # Вариант 1: Buy DEX (Ask) / Sell CEX (Bid)
                    if d_tick['ask'] and c_tick['bid'] and d_tick['ask'] > 0:
                        spread_1 = ((c_tick['bid'] - d_tick['ask']) / d_tick['ask']) * 100
                        if spread_1 >= min_spread:
                            results.append({
                                'Монета': base,
                                'LONG (Купить)': 'Hyperliquid',
                                'SHORT (Продать)': cex_id.upper(),
                                'Спред %': round(spread_1, 3),
                                'Цена Long': d_tick['ask'],
                                'Цена Short': c_tick['bid'],
                                'Объем CEX $': int(vol)
                            })

                    # Вариант 2: Buy CEX (Ask) / Sell DEX (Bid)
                    if c_tick['ask'] and d_tick['bid'] and c_tick['ask'] > 0:
                        spread_2 = ((d_tick['bid'] - c_tick['ask']) / c_tick['ask']) * 100
                        if spread_2 >= min_spread:
                            results.append({
                                'Монета': base,
                                'LONG (Купить)': cex_id.upper(),
                                'SHORT (Продать)': 'Hyperliquid',
                                'Спред %': round(spread_2, 3),
                                'Цена Long': c_tick['ask'],
                                'Цена Short': d_tick['bid'],
                                'Объем CEX $': int(vol)
                            })
        except: continue
    return pd.DataFrame(results)

# --- ИНТЕРФЕЙС ---
st.title("📊 Futures Hedge Arbitrage 2026")
st.markdown("Скринер для открытия встречных позиций на фьючерсах (без перевода монет).")

with st.sidebar:
    st.header("Настройки")
    interval = st.selectbox("Автообновление", [10, 15, 30, 60, 120], index=2)
    min_s = st.slider("Мин. спред %", 0.01, 1.0, 0.8)
    min_v = st.number_input("Мин. объем 24ч ($)", 0, 100000000, 100000)
    if st.button("Обновить кеш"):
        st.cache_data.clear()

# Запуск автообновления
autorefresh(interval)

st.caption(f"Последнее обновление: {time.strftime('%H:%M:%S')} | Интервал: {interval}с")

df = get_futures_spreads(min_s, min_v)

if not df.empty:
    df = df.sort_values('Спред %', ascending=False).drop_duplicates(subset=['Монета', 'LONG (Купить)'])
    st.dataframe(df, use_container_width=True)
else:
    st.info("Поиск активных спредов на рынке фьючерсов...")

st.caption("Данные: Hyperliquid & Tier-1 CEX | Дата: 18 января 2026")
