import time
from datetime import datetime, timezone
import pandas as pd
import streamlit as st
import ccxt

st.set_page_config(page_title="Binance Paper Scanner", page_icon="📊", layout="wide")
st.title("📊 Binance 50+ Market Scanner — PAPER MODE")
st.caption("Public market data only • No API keys • No real orders • Educational demo")

with st.sidebar:
    st.header("Settings")
    market_count = st.slider("Markets to scan", 10, 100, 55, 5)
    timeframe = st.selectbox("Candlestick timeframe", ["5m", "15m", "1h", "4h"], index=2)
    refresh_seconds = st.selectbox("Refresh interval", [60, 120, 300], index=0)
    starting_cash = st.number_input("Paper cash (USDT)", min_value=100.0, max_value=1000000.0, value=1000.0, step=100.0)
    trade_usdt = st.number_input("Paper position size (USDT)", min_value=10.0, max_value=10000.0, value=50.0, step=10.0)
    fee_pct = st.number_input("Estimated fee per side (%)", min_value=0.0, max_value=1.0, value=0.1, step=0.01)
    auto_refresh = st.checkbox("Auto-refresh", value=False)

st.info("Signals use a simple EMA(9)/EMA(21) crossover. This is not an AI model and does not predict profits. Paper trades are illustrative only.")

@st.cache_resource
def get_exchange():
    return ccxt.kucoin({"enableRateLimit": True, "timeout": 20000, "options": {"defaultType": "spot"}})

def scan_markets(exchange, limit, tf):
    markets = exchange.load_markets()
    tickers = exchange.fetch_tickers()
    candidates = []
    for symbol, market in markets.items():
        if market.get("spot") and market.get("quote") == "USDT" and market.get("active") and symbol in tickers:
            qv = tickers[symbol].get("quoteVolume") or 0
            last = tickers[symbol].get("last")
            if last and qv > 0:
                candidates.append((symbol, float(qv)))
    candidates.sort(key=lambda x: x[1], reverse=True)
    selected = [s for s, _ in candidates[:limit]]
    rows = []
    progress = st.progress(0, text="Scanning public Binance spot markets...")
    for i, symbol in enumerate(selected):
        try:
            candles = exchange.fetch_ohlcv(symbol, timeframe=tf, limit=60)
            if len(candles) < 30:
                continue
            df = pd.DataFrame(candles, columns=["time","open","high","low","close","volume"])
            # Exclude the currently forming candle
            close = df["close"].iloc[:-1].astype(float)
            ema9 = close.ewm(span=9, adjust=False).mean()
            ema21 = close.ewm(span=21, adjust=False).mean()
            prev_diff = float(ema9.iloc[-2] - ema21.iloc[-2])
            curr_diff = float(ema9.iloc[-1] - ema21.iloc[-1])
            signal = "BUY" if prev_diff <= 0 and curr_diff > 0 else ("SELL" if prev_diff >= 0 and curr_diff < 0 else "HOLD")
            last = float(close.iloc[-1])
            rows.append({"Symbol": symbol, "Price (USDT)": last, "EMA 9": float(ema9.iloc[-1]), "EMA 21": float(ema21.iloc[-1]), "Signal": signal, "Candles": len(close)})
        except Exception as e:
            rows.append({"Symbol": symbol, "Price (USDT)": None, "EMA 9": None, "EMA 21": None, "Signal": "ERROR", "Candles": 0, "Error": str(e)[:100]})
        progress.progress((i+1)/max(len(selected),1), text=f"Scanned {i+1}/{len(selected)} markets")
    progress.empty()
    return pd.DataFrame(rows)

if "paper_cash" not in st.session_state:
    st.session_state.paper_cash = float(starting_cash)
    st.session_state.positions = {}
    st.session_state.trades = []
    st.session_state.last_signals = {}

if st.button("🔄 Scan now", type="primary"):
    st.session_state.scan_now = True

should_scan = st.session_state.get("scan_now", False) or "results" not in st.session_state
if should_scan:
    try:
        exchange = get_exchange()
        st.session_state.results = scan_markets(exchange, market_count, timeframe)
        st.session_state.last_scan = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        st.session_state.scan_now = False
    except Exception as e:
        st.error(f"Could not get market data: {e}")
        st.caption("Check internet connection and try again later.")

if "results" in st.session_state:
    results = st.session_state.results.copy()
    st.caption(f"Last scan: {st.session_state.get('last_scan','not yet')} • {len(results)} rows")
    good = results[results["Signal"].isin(["BUY","SELL"])]
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Markets scanned", len(results))
    c2.metric("BUY signals", int((results["Signal"]=="BUY").sum()))
    c3.metric("SELL signals", int((results["Signal"]=="SELL").sum()))
    c4.metric("Paper cash", f"${st.session_state.paper_cash:,.2f}")
    st.subheader("Market signals")
    st.dataframe(results, use_container_width=True, hide_index=True)
    st.download_button("Download scan CSV", results.to_csv(index=False).encode("utf-8"), "market_scan.csv", "text/csv")

    st.subheader("Paper trading (manual simulation)")
    st.write("Choose a BUY signal to simulate opening a position. SELL closes a paper position if one exists. No order is sent to Binance.")
    choices = results[results["Signal"]=="BUY"]["Symbol"].tolist()
    buy_symbol = st.selectbox("Symbol to paper-buy", ["— choose —"] + choices)
    if st.button("Simulate BUY") and buy_symbol != "— choose —":
        row = results[results["Symbol"]==buy_symbol].iloc[0]
        price = float(row["Price (USDT)"])
        cost = min(float(trade_usdt), st.session_state.paper_cash)
        fee = cost * float(fee_pct)/100
        if cost > fee and buy_symbol not in st.session_state.positions:
            qty = (cost-fee)/price
            st.session_state.paper_cash -= cost
            st.session_state.positions[buy_symbol] = {"qty": qty, "entry": price, "cost": cost, "fee_pct": float(fee_pct)}
            st.session_state.trades.append({"Time UTC": datetime.now(timezone.utc).isoformat(), "Action":"PAPER BUY", "Symbol":buy_symbol, "Price":price, "Qty":qty, "Fee":fee, "Note":"Simulated; not a real order"})
            st.success(f"Simulated buy: {buy_symbol} at {price:g} USDT")
        else:
            st.warning("Not enough paper cash or a paper position already exists for this symbol.")

    positions = st.session_state.positions
    if positions:
        pos_rows=[]
        for sym, p in positions.items():
            found = results[results["Symbol"]==sym]
            mark = float(found.iloc[0]["Price (USDT)"]) if len(found) and pd.notna(found.iloc[0]["Price (USDT)"]) else p["entry"]
            value = p["qty"]*mark
            est_sell_fee = value*p["fee_pct"]/100
            pnl = value-est_sell_fee-p["cost"]
            pos_rows.append({"Symbol":sym,"Entry":p["entry"],"Mark":mark,"Quantity":p["qty"],"Cost":p["cost"],"Estimated P/L after sell fee":pnl})
        st.dataframe(pd.DataFrame(pos_rows), use_container_width=True, hide_index=True)
        close_symbol = st.selectbox("Position to close", ["— choose —"] + list(positions.keys()))
        if st.button("Simulate SELL / close") and close_symbol != "— choose —":
            p=positions[close_symbol]
            found=results[results["Symbol"]==close_symbol]
            price=float(found.iloc[0]["Price (USDT)"]) if len(found) and pd.notna(found.iloc[0]["Price (USDT)"]) else p["entry"]
            gross=p["qty"]*price
            fee=gross*p["fee_pct"]/100
            proceeds=gross-fee
            pnl=proceeds-p["cost"]
            st.session_state.paper_cash += proceeds
            st.session_state.trades.append({"Time UTC":datetime.now(timezone.utc).isoformat(),"Action":"PAPER SELL","Symbol":close_symbol,"Price":price,"Qty":p["qty"],"Fee":fee,"Note":f"Simulated P/L {pnl:.4f} USDT; no real order"})
            del st.session_state.positions[close_symbol]
            st.success(f"Closed paper position. Estimated P/L: {pnl:.4f} USDT (before spread/slippage).")
    if st.session_state.trades:
        st.subheader("Paper trade history")
        st.dataframe(pd.DataFrame(st.session_state.trades), use_container_width=True, hide_index=True)
        st.download_button("Download trade history CSV", pd.DataFrame(st.session_state.trades).to_csv(index=False).encode("utf-8"), "paper_trades.csv", "text/csv")
    if auto_refresh:
        st.caption(f"Auto-refresh is enabled ({refresh_seconds}s). Keep the session open.")
        time.sleep(refresh_seconds)
        st.rerun()

st.divider()
st.caption("Safety: this project has no API key fields and no live-order functions. Restarting the app resets in-memory paper cash/positions. It is a learning prototype, not financial advice.")
