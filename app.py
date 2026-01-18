import streamlit as st
import ccxt
import pd
import streamlit.components.v1 as components

st.set_page_config(page_title="Futures Hedge Scanner 2026", layout="wide")

# Только те биржи, где отличная ликвидность на фьючерсах (Perps)
CEX_LIST = ['binance', 'bybit', 'okx', 'bitget', 'mexc']

def autorefresh(interval):
    if interval > 0:
        components.html(f"<script>setTimeout(()=>window.parent.location.reload(), {interval*1000});</script>", height=0)

@st.cache_data(ttl=5)
def get_futures_spreads(min_spread, min_vol):
    results = []
    
    # 1. Данные с Hyperliquid (DEX Perp)
    try:
        dex = ccxt.hyperliquid()
        dex_tickers = dex.fetch_tickers()
    except:
        return pd.DataFrame()

    # 2. Данные с CEX (только USDT-M Futures)
    for cex_id in CEX_LIST:
        try:
            cex = getattr(ccxt, cex_id)({
                'enableRateLimit': True, 
                'options': {'defaultType': 'swap'} # Строго фьючерсы
            })
            cex_tickers = cex.fetch_tickers()
            
            for d_sym, d_tick in dex_tickers.items():
                # Чистим тикер (BTC/USDC:USDC -> BTC)
                base = d_sym.split('/').split(':').split('-').upper()
                
                # Ищем фьючерс на CEX (BTC/USDT:USDT)
                target = next((s for s in cex_tickers.keys() if s.startswith(base + "/")), None)
                
                if target:
                    c_tick = cex_tickers[target]
                    vol = c_tick.get('quoteVolume', 0)
                    
                    if vol < min_vol: continue

                    # Цены исполнения (Best Bid / Best Ask)
                    # Вариант 1: Buy DEX (Ask) / Sell CEX (Bid)
                    if d_tick['ask'] > 0 and c_tick['bid'] > 0:
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
                    if c_tick['ask'] > 0 and d_tick['bid'] > 0:
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
st.subheader("Межбиржевой арбитраж без перевода монет (Long/Short)")

with st.sidebar:
    interval = st.selectbox("Автообновление", [10, 30, 60], index=0)
    min_s = st.slider("Минимальный спред %", 0.05, 1.0, 0.15)
    min_v = st.number_input("Мин. объем 24ч ($)", 0, 10000000, 500000)

autorefresh(interval)

df = get_futures_spreads(min_s, min_v)

if not df.empty:
    df = df.sort_values('Спред %', ascending=False)
    st.dataframe(df, use_container_width=True)
    
    st.info("""
    **Инструкция по хедж-арбитражу:**
    1. У вас должен быть депозит в USDT на обеих биржах.
    2. Вы **не переводите** монеты. Вы открываете позиции одновременно.
    3. Когда цена сходится (спред исчезает), вы закрываете обе сделки.
    """)
else:
    st.info("Поиск активных спредов на фьючерсном рынке...")

st.caption(f"Обновлено: {pd.Timestamp.now().strftime('%H:%M:%S')} | Только бессрочные контракты (Perpetual)")
