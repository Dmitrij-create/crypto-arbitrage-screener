import streamlit as st
import ccxt
import pandas as pd
import streamlit.components.v1 as components

st.set_page_config(page_title="DEX/CEX Arbitrage 2026", layout="wide")

# --- Настройки ---
CEX_LIST = ['mexc', 'bitget', 'okx', 'bingx', 'gateio'] # Исправлено gate на gateio
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
    except Exception as e:
        st.error(f"Ошибка DEX: {e}")
        return pd.DataFrame()

    # 2. Перебираем CEX
    for cex_id in CEX_LIST:
        try:
            cex_ex = getattr(ccxt, cex_id)({'options': {'defaultType': 'swap'}})
            cex_tickers = cex_ex.fetch_tickers()
            
            for dex_symbol, dex_t in dex_tickers.items():
                # Нормализация имени (извлекаем BTC, ETH и т.д.)
                base_name = dex_symbol.split('/')[0].split('-')[0].split(':')[0].upper()
                
                # Поиск соответствия на CEX
                cex_match = None
                for s in cex_tickers.keys():
                    if s.startswith(base_name + "/") or s.startswith(base_name + ":"):
                        cex_match = s
                        break
                
                if cex_match:
                    cex_t = cex_tickers[cex_match]
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
                            'DEX Цена': round(p_dex, 5),
                            'CEX Цена': round(p_cex, 5),
                            'Объем CEX $': int(vol)
                        })
        except Exception as e:
            continue
            
    return pd.DataFrame(results)

# --- UI ---
st.title("🔗 DEX/CEX Perp Arbitrage 2026")

with st.sidebar:
    st.header("Параметры")
    amount = st.number_input("Объем сделки ($)", 10, 50000, 50)
    min_spread = st.slider("Мин. спред %", 0.01, 2.0, 0.1)
    min_vol = st.number_input("Мин. объем CEX ($)", 0, 100000000, 50000)
    refresh = st.select_slider("Обновление (сек)", options=[15, 30, 60, 120], value=30)
    if st.button("Обновить вручную"):
        st.rerun()

autorefresh(refresh)

with st.spinner("Сравнение цен Hyperliquid и CEX..."):
    # ИСПРАВЛЕНО: Передаем 3 аргумента
    df = get_dex_cex_data(amount, min_spread, min_vol)

if not df.empty:
    # ИСПРАВЛЕНО: Сортировка по корректному названию колонки 'Монета'
    df = df.sort_values('Спред %', ascending=False).drop_duplicates(subset=['Монета'])
    
    if df['Спред %'].max() > 0.5:
        play_sound()
        st.success(f"🚀 Найдена связка: {df['Спред %'].max()}%")

    st.dataframe(df, use_container_width=True)
else:
    st.info("Связок не найдено. Попробуйте снизить 'Мин. объем' или 'Мин. спред'.")

st.caption(f"Проверка в реальном времени: {pd.Timestamp.now().strftime('%H:%M:%S')} (2026)")
