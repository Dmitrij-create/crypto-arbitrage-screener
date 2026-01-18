import streamlit as st
import ccxt
import pandas as pd

st.set_page_config(page_title="DEX/CEX Precise 2026", layout="wide")

CEX_LIST = ['binance', 'bybit', 'okx', 'mexc', 'gateio']

@st.cache_data(ttl=5) # Уменьшили кеш до 5 секунд для точности
def get_precise_data(min_spread, min_vol):
    results = []
    
    # 1. Загружаем DEX (Hyperliquid)
    try:
        dex = ccxt.hyperliquid()
        # На Hyperliquid все пары - это Swap (бессрочные фьючерсы)
        dex_tickers = dex.fetch_tickers()
    except Exception as e:
        st.error(f"DEX API Error: {e}")
        return pd.DataFrame()

    # 2. Перебираем CEX
    for cex_id in CEX_LIST:
        try:
            # Принудительно устанавливаем тип SWAP для CEX
            cex = getattr(ccxt, cex_id)({
                'enableRateLimit': True, 
                'options': {'defaultType': 'swap'} 
            })
            cex_tickers = cex.fetch_tickers()
            
            for d_sym, d_tick in dex_tickers.items():
                # Чистим имя: "BTC/USDC:USDC" -> "BTC"
                base = d_sym.split('/')[0].split(':')[0].split('-')[0].upper()
                
                # Ищем точное соответствие фьючерса на CEX (напр. BTC/USDT:USDT)
                # Важно найти именно фьючерсную пару к USDT/USDC
                target_symbol = None
                for s in cex_tickers.keys():
                    if s.startswith(base + "/") and (":USDT" in s or ":USDC" in s):
                        target_symbol = s
                        break
                
                if target_symbol:
                    c_tick = cex_tickers[target_symbol]
                    
                    # ИСПОЛЬЗУЕМ ТОЛЬКО BID/ASK (это реальные цены покупки/продажи)
                    # p_buy (где мы покупаем) / p_sell (где мы продаем)
                    
                    # Ситуация А: Покупаем на DEX, продаем на CEX
                    if d_tick['ask'] and c_tick['bid']:
                        diff_a = ((c_tick['bid'] - d_tick['ask']) / d_tick['ask']) * 100
                        if diff_a >= min_spread:
                            add_row(results, base, "DEX", cex_id, d_tick['ask'], c_tick['bid'], diff_a, c_tick)

                    # Ситуация Б: Покупаем на CEX, продаем на DEX
                    if c_tick['ask'] and d_tick['bid']:
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
st.title("🎯 Precise DEX/CEX Arbitrage (Futures Only)")

with st.sidebar:
    st.header("Настройки")
    min_s = st.slider("Мин. спред %", 0.01, 1.0, 0.1)
    min_v = st.number_input("Мин. объем ($)", 0, 1000000, 100000)
    if st.button("ОБНОВИТЬ ДАННЫЕ"):
        st.cache_data.clear()

df = get_precise_data(min_s, min_v)

if not df.empty:
    # Очистка от дублей и сортировка
    df = df.sort_values('Спред %', ascending=False)
    st.dataframe(df, use_container_width=True)
else:
    st.info("Реальных спредов по ценам Bid/Ask не найдено.")

st.caption(f"Обновлено: {pd.Timestamp.now().strftime('%H:%M:%S')} (Январь 2026)")
