import streamlit as st
import ccxt
import pandas as pd

# Page configuration
st.set_page_config(page_title="Multi-Indicator Crypto Scanner", layout="wide")

# Initialize Session State for Paper Trading
if "paper_cash" not in st.session_state:
    st.session_state.paper_cash = 1000.0
if "paper_positions" not in st.session_state:
    st.session_state.paper_positions = {}

# Connect to KuCoin Exchange
@st.cache_resource
def get_exchange():
    return ccxt.kucoin({"enableRateLimit": True, "timeout": 20000, "options": {"defaultType": "spot"}})

exchange = get_exchange()

# Sidebar Settings
st.sidebar.header("⚙️ Scanner Settings")
timeframe = st.sidebar.selectbox("Timeframe", ["15m", "1h", "4h", "1d"], index=1)
trade_size = st.sidebar.number_input("Paper Position Size (USDT)", min_value=10.0, max_value=1000.0, value=100.0, step=10.0)

if st.sidebar.button("Reset Paper Portfolio"):
    st.session_state.paper_cash = 1000.0
    st.session_state.paper_positions = {}
    st.sidebar.success("Portfolio Reset to $1,000 USDT!")

# Main Title & Info
st.title("🚀 Advanced Crypto Market Scanner (EMA + RSI + MACD)")
st.caption("Real-Time Multi-Indicator Scanner for KuCoin Spot Markets")

# Function to calculate RSI without external dependency
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# Function to fetch and analyze
def analyze_market(symbol):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=100)
        df = pd.DataFrame(ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        
        # Calculate Indicators
        df['EMA9'] = df['close'].ewm(span=9, adjust=False).mean()
        df['EMA21'] = df['close'].ewm(span=21, adjust=False).mean()
        df['RSI'] = calculate_rsi(df['close'], period=14)
        
        exp1 = df['close'].ewm(span=12, adjust=False).mean()
        exp2 = df['close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = exp1 - exp2
        df['MACD_signal'] = df['MACD'].ewm(span=9, adjust=False).mean()

        latest = df.iloc[-1]

        # Multi-Indicator Filter Logic
        ema_bullish = latest['EMA9'] > latest['EMA21']
        rsi_valid = 50 <= latest['RSI'] <= 70
        macd_bullish = latest['MACD'] > latest['MACD_signal']

        ema_bearish = latest['EMA9'] < latest['EMA21']
        macd_bearish = latest['MACD'] < latest['MACD_signal']

        if ema_bullish and rsi_valid and macd_bullish:
            signal = "BUY"
        elif ema_bearish and macd_bearish:
            signal = "SELL"
        else:
            signal = "HOLD"

        return {
            "Symbol": symbol,
            "Price (USDT)": round(latest['close'], 6),
            "EMA9": round(latest['EMA9'], 4),
            "EMA21": round(latest['EMA21'], 4),
            "RSI (14)": round(latest['RSI'], 2),
            "MACD": round(latest['MACD'], 4),
            "Signal": signal
        }
    except Exception:
        return None

# Scan Button & Results
if st.button("🔴 Scan Market Now", type="primary"):
    with st.spinner("Scanning top USDT markets with EMA, RSI & MACD..."):
        try:
            markets = exchange.load_markets()
            symbols = [s for s in markets if s.endswith('/USDT') and markets[s]['active']][:50]
            
            results = []
            for sym in symbols:
                res = analyze_market(sym)
                if res:
                    results.append(res)

            st.session_state.scan_df = pd.DataFrame(results)
        except Exception as e:
            st.error(f"Error fetching data: {e}")

# Display Scanner Results
if "scan_df" in st.session_state and not st.session_state.scan_df.empty:
    df_res = st.session_state.scan_df
    
    st.subheader(f"📊 Market Signals ({len(df_res)} Markets Analyzed)")
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("BUY Signals", len(df_res[df_res['Signal'] == 'BUY']))
    col2.metric("SELL Signals", len(df_res[df_res['Signal'] == 'SELL']))
    col3.metric("Paper Cash", f"${st.session_state.paper_cash:.2f}")
    col4.metric("Open Positions", len(st.session_state.paper_positions))

    st.dataframe(df_res, use_container_width=True)
    st.markdown("---")
    
    st.subheader("💡 Paper Trading Simulation")
    col_buy, col_sell = st.columns(2)

    with col_buy:
        buy_candidates = df_res[df_res['Signal'] == 'BUY']['Symbol'].tolist()
        selected_buy = st.selectbox("Choose a BUY Signal Coin", ["-- Select --"] + buy_candidates)
        
        if st.button("Simulate BUY"):
            if selected_buy != "-- Select --":
                price = df_res[df_res['Symbol'] == selected_buy]['Price (USDT)'].values[0]
                if st.session_state.paper_cash >= trade_size:
                    st.session_state.paper_cash -= trade_size
                    st.session_state.paper_positions[selected_buy] = {
                        'amount': trade_size / price,
                        'buy_price': price
                    }
                    st.success(f"Successfully Paper-Bought {selected_buy} at ${price}")
                    st.rerun()
                else:
                    st.error("Insufficient Paper Cash!")
            else:
                st.warning("Please select a valid coin to buy!")

    with col_sell:
        active_positions = list(st.session_state.paper_positions.keys())
        selected_sell = st.selectbox("Choose Open Position to Close", ["-- Select --"] + active_positions)
        
        if st.button("Simulate SELL / Close"):
            if selected_sell != "-- Select --":
                current_price = df_res[df_res['Symbol'] == selected_sell]['Price (USDT)'].values[0] if selected_sell in df_res['Symbol'].values else st.session_state.paper_positions[selected_sell]['buy_price']
                pos = st.session_state.paper_positions.pop(selected_sell)
                return_val = pos['amount'] * current_price
                pnl = return_val - trade_size
                st.session_state.paper_cash += return_val
                
                if pnl >= 0:
                    st.success(f"Closed {selected_sell}! Profit: +${pnl:.2f}")
                else:
                    st.error(f"Closed {selected_sell}! Loss: -${abs(pnl):.2f}")
                st.rerun()
            else:
                st.warning("Please select a valid position to close!")

    if st.session_state.paper_positions:
        st.subheader("📈 Active Paper Positions")
        pos_data = []
        for sym, details in st.session_state.paper_positions.items():
            curr_p = df_res[df_res['Symbol'] == sym]['Price (USDT)'].values[0] if sym in df_res['Symbol'].values else details['buy_price']
            val = details['amount'] * curr_p
            pnl = val - trade_size
            pos_data.append({
                "Symbol": sym,
                "Buy Price": details['buy_price'],
                "Current Price": curr_p,
                "Current Value ($)": round(val, 2),
                "Unrealized P/L ($)": round(pnl, 2)
            })
        st.table(pd.DataFrame(pos_data))
