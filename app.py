import time
from datetime import datetime, timezone

import ccxt
import pandas as pd
import streamlit as st

# ============================================================
# KuCoin Advanced Crypto Scanner + Paper Trading
# Paper trading only: this app does NOT place live orders.
# ============================================================

st.set_page_config(
    page_title="KuCoin Advanced Crypto Scanner",
    page_icon="📈",
    layout="wide",
)

DEFAULT_CASH = 1000.0
TIMEFRAMES = ["15m", "1h", "4h", "1d"]
STABLECOIN_PAIRS = {
    "USDC/USDT", "BUSD/USDT", "TUSD/USDT",
    "DAI/USDT", "FDUSD/USDT", "USDE/USDT",
    "USDP/USDT", "USTC/USDT",
}


# ------------------------- Session state -------------------------
def init_state():
    defaults = {
        "paper_cash": DEFAULT_CASH,
        "paper_positions": {},
        "paper_history": [],
        "scan_df": pd.DataFrame(),
        "btc_trend": "UNKNOWN",
        "last_scan_time": None,
        "scan_errors": [],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_state()


# ------------------------- Exchange -------------------------
@st.cache_resource
def get_exchange():
    # Public market data only; no API keys are required.
    return ccxt.kucoin({
        "enableRateLimit": True,
        "timeout": 20000,
        "options": {"defaultType": "spot"},
    })


exchange = get_exchange()


# ------------------------- Sidebar -------------------------
st.sidebar.header("⚙️ Scanner Settings")
timeframe = st.sidebar.selectbox("Main timeframe", TIMEFRAMES, index=1)
scan_limit = st.sidebar.slider("Maximum markets to scan", 10, 100, 50, 10)
min_quote_volume = st.sidebar.number_input(
    "Minimum 24h quote volume (USDT)",
    min_value=0.0,
    value=250000.0,
    step=50000.0,
)
trade_size = st.sidebar.number_input(
    "Paper position size (USDT)",
    min_value=10.0,
    max_value=1000.0,
    value=100.0,
    step=10.0,
)
fee_pct = st.sidebar.number_input(
    "Estimated fee per side (%)",
    min_value=0.0,
    max_value=2.0,
    value=0.1,
    step=0.01,
    help="Illustrative estimate. Change this to match your actual fee tier.",
) / 100.0
atr_multiplier = st.sidebar.slider("ATR stop-loss multiplier", 1.0, 4.0, 2.0, 0.25)
reward_risk = st.sidebar.slider("Take-profit reward/risk ratio", 1.0, 5.0, 2.0, 0.25)
use_btc_filter = st.sidebar.checkbox("Require bullish BTC trend for altcoin BUY", value=True)

if st.sidebar.button("Reset Paper Portfolio"):
    st.session_state.paper_cash = DEFAULT_CASH
    st.session_state.paper_positions = {}
    st.session_state.paper_history = []
    st.session_state.scan_df = pd.DataFrame()
    st.session_state.btc_trend = "UNKNOWN"
    st.session_state.last_scan_time = None
    st.session_state.scan_errors = []
    st.sidebar.success("Paper portfolio reset to $1,000.")
    st.rerun()


# ------------------------- Indicators -------------------------
def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(
        alpha=1 / period, min_periods=period, adjust=False
    ).mean()
    avg_loss = loss.ewm(
        alpha=1 / period, min_periods=period, adjust=False
    ).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.mask((avg_loss == 0) & (avg_gain > 0), 100)
    rsi = rsi.mask((avg_gain == 0) & (avg_loss > 0), 0)
    rsi = rsi.mask((avg_gain == 0) & (avg_loss == 0), 50)
    return rsi


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    prev_close = df["close"].shift(1)
    true_range = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.ewm(
        alpha=1 / period, min_periods=period, adjust=False
    ).mean()


def fetch_closed_candles(symbol: str, tf: str, limit: int = 150):
    raw = exchange.fetch_ohlcv(symbol, timeframe=tf, limit=limit)
    if not raw or len(raw) < 60:
        raise ValueError("Not enough OHLCV candles.")

    df = pd.DataFrame(
        raw,
        columns=["time", "open", "high", "low", "close", "volume"],
    )
    df = df.drop_duplicates(subset=["time"]).sort_values("time").reset_index(drop=True)

    # Exchange OHLCV usually includes the current, still-forming candle.
    # Drop it only when its expected close time is still in the future.
    tf_ms = exchange.parse_timeframe(tf) * 1000
    now_ms = exchange.milliseconds()
    if len(df) and int(df.iloc[-1]["time"]) + tf_ms > now_ms:
        df = df.iloc[:-1].copy()

    if len(df) < 50:
        raise ValueError("Not enough completed candles after filtering.")
    if df[["open", "high", "low", "close", "volume"]].isna().any().any():
        raise ValueError("OHLCV contains missing values.")
    if (df["close"] <= 0).any():
        raise ValueError("OHLCV contains invalid prices.")
    return df.reset_index(drop=True)


def get_btc_trend(tf: str) -> str:
    try:
        df = fetch_closed_candles("BTC/USDT", tf, limit=100)
        close = df["close"]
        ema9 = close.ewm(span=9, adjust=False).mean().iloc[-1]
        ema21 = close.ewm(span=21, adjust=False).mean().iloc[-1]
        if ema9 > ema21:
            return "BULLISH"
        if ema9 < ema21:
            return "BEARISH"
        return "NEUTRAL"
    except Exception as exc:
        st.session_state.scan_errors.append(f"BTC trend: {type(exc).__name__}: {exc}")
        return "NEUTRAL"


def analyze_market(symbol: str, btc_trend: str, tf: str):
    try:
        df = fetch_closed_candles(symbol, tf, limit=150)
        close = df["close"]

        df["EMA9"] = close.ewm(span=9, adjust=False).mean()
        df["EMA21"] = close.ewm(span=21, adjust=False).mean()
        df["EMA20"] = close.ewm(span=20, adjust=False).mean()
        df["EMA50"] = close.ewm(span=50, adjust=False).mean()
        df["RSI"] = calculate_rsi(close, 14)

        macd_fast = close.ewm(span=12, adjust=False).mean()
        macd_slow = close.ewm(span=26, adjust=False).mean()
        df["MACD"] = macd_fast - macd_slow
        df["MACD_signal"] = df["MACD"].ewm(span=9, adjust=False).mean()
        df["MACD_hist"] = df["MACD"] - df["MACD_signal"]
        df["Vol_MA20"] = df["volume"].rolling(20).mean()
        df["ATR"] = calculate_atr(df, 14)

        latest = df.iloc[-1]
        required = ["EMA9", "EMA21", "EMA20", "EMA50", "RSI",
                    "MACD", "MACD_signal", "Vol_MA20", "ATR"]
        if latest[required].isna().any() or latest["ATR"] <= 0:
            return None

        ema_bullish = latest["EMA9"] > latest["EMA21"]
        trend_bullish = latest["EMA20"] > latest["EMA50"]
        rsi_valid = 50 <= latest["RSI"] <= 70
        macd_bullish = latest["MACD"] > latest["MACD_signal"]
        volume_strong = latest["volume"] > latest["Vol_MA20"]

        ema_bearish = latest["EMA9"] < latest["EMA21"]
        macd_bearish = latest["MACD"] < latest["MACD_signal"]

        btc_allowed = (
            not use_btc_filter
            or symbol == "BTC/USDT"
            or btc_trend == "BULLISH"
        )

        score = sum([
            bool(ema_bullish),
            bool(trend_bullish),
            bool(rsi_valid),
            bool(macd_bullish),
            bool(volume_strong),
            bool(btc_allowed),
        ])

        if (
            ema_bullish and trend_bullish and rsi_valid
            and macd_bullish and volume_strong and btc_allowed
        ):
            signal = "BUY"
        elif ema_bearish and macd_bearish:
            signal = "EXIT / BEARISH"
        else:
            signal = "HOLD"

        price = float(latest["close"])
        atr = float(latest["ATR"])
        stop_loss = price - atr_multiplier * atr
        take_profit = price + (atr_multiplier * atr * reward_risk)

        return {
            "Symbol": symbol,
            "Price (USDT)": price,
            "EMA9": float(latest["EMA9"]),
            "EMA21": float(latest["EMA21"]),
            "EMA20": float(latest["EMA20"]),
            "EMA50": float(latest["EMA50"]),
            "RSI (14)": float(latest["RSI"]),
            "MACD": float(latest["MACD"]),
            "MACD Signal": float(latest["MACD_signal"]),
            "Volume Spike": "YES" if volume_strong else "NO",
            "ATR": atr,
            "Suggested Stop": stop_loss,
            "Suggested Target": take_profit,
            "Score (/6)": int(score),
            "Signal": signal,
            "Candle Time (UTC)": datetime.fromtimestamp(
                int(latest["time"]) / 1000, tz=timezone.utc
            ).strftime("%Y-%m-%d %H:%M"),
        }
    except Exception as exc:
        st.session_state.scan_errors.append(
            f"{symbol}: {type(exc).__name__}: {exc}"
        )
        return None


# ------------------------- Market selection -------------------------
def get_candidate_symbols(max_markets: int, min_volume: float):
    markets = exchange.load_markets()
    candidates = [
        symbol for symbol, market in markets.items()
        if market.get("active") is True
        and market.get("spot") is True
        and market.get("quote") == "USDT"
        and market.get("base")
        and symbol not in STABLECOIN_PAIRS
        and not market.get("contract", False)
    ]

    # Batch ticker request where supported; fall back to per-symbol filtering
    # if the exchange rejects a bulk request.
    ranked = []
    try:
        tickers = exchange.fetch_tickers(candidates)
        for symbol in candidates:
            ticker = tickers.get(symbol) or {}
            quote_volume = ticker.get("quoteVolume")
            last = ticker.get("last")
            bid, ask = ticker.get("bid"), ticker.get("ask")

            if quote_volume is None and ticker.get("baseVolume") is not None and last:
                quote_volume = float(ticker["baseVolume"]) * float(last)

            if quote_volume is None or last is None:
                continue
            if float(quote_volume) < min_volume or float(last) <= 0:
                continue

            spread_pct = None
            if bid and ask and float(bid) > 0:
                spread_pct = (float(ask) - float(bid)) / float(bid) * 100
                if spread_pct < 0 or spread_pct > 2:
                    continue

            ranked.append((symbol, float(quote_volume)))
    except Exception as exc:
        st.session_state.scan_errors.append(
            f"Ticker ranking fallback: {type(exc).__name__}: {exc}"
        )
        # Avoid scanning every market without liquidity data.
        raise RuntimeError(
            "Could not retrieve ticker liquidity data. Please try again later."
        ) from exc

    ranked.sort(key=lambda item: item[1], reverse=True)
    return [symbol for symbol, _ in ranked[:max_markets]]


# ------------------------- Paper trading helpers -------------------------
def get_latest_price(symbol: str):
    df = st.session_state.scan_df
    if not df.empty and symbol in df["Symbol"].values:
        return float(df.loc[df["Symbol"] == symbol, "Price (USDT)"].iloc[0])
    # Do not silently substitute the entry price for current market price.
    ticker = exchange.fetch_ticker(symbol)
    last = ticker.get("last")
    if last is None or float(last) <= 0:
        raise ValueError(f"Could not get a valid current price for {symbol}.")
    return float(last)


def paper_buy(symbol: str, price: float, amount_usdt: float, fee_rate: float):
    if symbol in st.session_state.paper_positions:
        raise ValueError("This coin already has an open paper position.")
    if price <= 0 or amount_usdt <= 0:
        raise ValueError("Price and order size must be positive.")

    fee = amount_usdt * fee_rate
    total_debit = amount_usdt + fee
    if st.session_state.paper_cash < total_debit:
        raise ValueError("Insufficient paper cash including estimated fee.")

    units = amount_usdt / price
    st.session_state.paper_cash -= total_debit
    st.session_state.paper_positions[symbol] = {
        "amount": units,
        "buy_price": price,
        "invested": amount_usdt,
        "buy_fee": fee,
        "opened_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    st.session_state.paper_history.append({
        "Time (UTC)": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "Symbol": symbol,
        "Action": "PAPER BUY",
        "Price": price,
        "Units": units,
        "Fee": fee,
        "Realized P/L": None,
        "Note": "Entry cost excludes fee; fee tracked separately.",
    })


def paper_close(symbol: str, price: float, fee_rate: float):
    if symbol not in st.session_state.paper_positions:
        raise ValueError("No open position for this coin.")
    if price <= 0:
        raise ValueError("Invalid exit price.")

    pos = st.session_state.paper_positions.pop(symbol)
    gross_value = pos["amount"] * price
    sell_fee = gross_value * fee_rate
    net_proceeds = gross_value - sell_fee
    total_cost = pos["invested"] + pos["buy_fee"]
    pnl = net_proceeds - total_cost
    st.session_state.paper_cash += net_proceeds

    st.session_state.paper_history.append({
        "Time (UTC)": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "Symbol": symbol,
        "Action": "PAPER SELL",
        "Price": price,
        "Units": pos["amount"],
        "Fee": sell_fee,
        "Realized P/L": pnl,
        "Note": "Estimated fees included; slippage not modeled.",
    })
    return pnl


# ------------------------- UI -------------------------
st.title("📈 KuCoin Advanced Crypto Scanner")
st.caption(
    "EMA + Wilder RSI + MACD + Volume + BTC trend + ATR risk levels. "
    "Paper trading only; no live orders."
)

scan_col, info_col = st.columns([1, 3])
with scan_col:
    scan_clicked = st.button("🔎 Scan Market Now", type="primary", use_container_width=True)
with info_col:
    st.info(
        "Public market data only. Signals use completed candles. "
        "API availability, liquidity and indicator signals can change."
    )

if scan_clicked:
    st.session_state.scan_errors = []
    results = []
    progress = st.progress(0, text="Checking BTC trend...")

    try:
        btc_trend = get_btc_trend(timeframe)
        st.session_state.btc_trend = btc_trend

        progress.progress(10, text="Selecting liquid Spot USDT markets...")
        symbols = get_candidate_symbols(scan_limit, min_quote_volume)

        if not symbols:
            st.warning("No markets matched your liquidity filters.")
            st.session_state.scan_df = pd.DataFrame()
        else:
            total = len(symbols)
            for idx, symbol in enumerate(symbols, start=1):
                result = analyze_market(symbol, btc_trend, timeframe)
                if result:
                    results.append(result)
                progress.progress(
                    10 + int(90 * idx / total),
                    text=f"Scanning {idx}/{total}: {symbol}",
                )
                # CCXT enableRateLimit is active; no additional fixed sleep needed.

            st.session_state.scan_df = pd.DataFrame(results)
            st.session_state.last_scan_time = datetime.now(timezone.utc).isoformat(
                timespec="seconds"
            )
    except Exception as exc:
        st.error(f"Scan failed: {type(exc).__name__}: {exc}")
    finally:
        progress.empty()

if st.session_state.last_scan_time:
    st.caption(f"Last scan (UTC): {st.session_state.last_scan_time}")

if st.session_state.scan_df is not None and not st.session_state.scan_df.empty:
    df_res = st.session_state.scan_df.copy()
    btc_status = st.session_state.btc_trend

    if btc_status == "BULLISH":
        st.success(f"BTC trend: BULLISH ({timeframe})")
    elif btc_status == "BEARISH":
        st.warning(f"BTC trend: BEARISH ({timeframe}); altcoin BUYs may be filtered.")
    else:
        st.warning("BTC trend: NEUTRAL/UNKNOWN; verify market data before acting.")

    buy_count = int((df_res["Signal"] == "BUY").sum())
    bearish_count = int((df_res["Signal"] == "EXIT / BEARISH").sum())
    st.subheader(f"📊 Scan Results — {len(df_res)} markets analyzed")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("BUY Signals", buy_count)
    c2.metric("Bearish / Exit Watch", bearish_count)
    c3.metric("Paper Cash", f"${st.session_state.paper_cash:,.2f}")
    c4.metric("Open Positions", len(st.session_state.paper_positions))

    display_df = df_res.sort_values(
        by=["Signal", "Score (/6)"], ascending=[True, False]
    ).copy()
    st.dataframe(
        display_df.style.format({
            "Price (USDT)": "{:.8f}",
            "EMA9": "{:.8f}",
            "EMA21": "{:.8f}",
            "EMA20": "{:.8f}",
            "EMA50": "{:.8f}",
            "RSI (14)": "{:.2f}",
            "MACD": "{:.8f}",
            "MACD Signal": "{:.8f}",
            "ATR": "{:.8f}",
            "Suggested Stop": "{:.8f}",
            "Suggested Target": "{:.8f}",
        }, na_rep="—"),
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("---")
    st.subheader("🧪 Paper Trading")
    buy_candidates = df_res.loc[df_res["Signal"] == "BUY", "Symbol"].tolist()
    active_positions = list(st.session_state.paper_positions.keys())

    buy_col, sell_col = st.columns(2)
    with buy_col:
        st.markdown("**Open a paper position**")
        if buy_candidates:
            selected_buy = st.selectbox("BUY candidate", buy_candidates, key="buy_symbol")
            if st.button("Simulate BUY", key="paper_buy_button"):
                try:
                    buy_price = get_latest_price(selected_buy)
                    paper_buy(selected_buy, buy_price, float(trade_size), float(fee_pct))
                    st.success(f"Paper BUY recorded: {selected_buy} at {buy_price:.8g}")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Paper BUY failed: {exc}")
        else:
            st.caption("No BUY candidates in the latest scan.")

    with sell_col:
        st.markdown("**Close an open paper position**")
        if active_positions:
            selected_sell = st.selectbox(
                "Open position", active_positions, key="sell_symbol"
            )
            if st.button("Simulate SELL / Close", key="paper_sell_button"):
                try:
                    sell_price = get_latest_price(selected_sell)
                    pnl = paper_close(selected_sell, sell_price, float(fee_pct))
                    if pnl >= 0:
                        st.success(f"Closed {selected_sell}; net P/L: +${pnl:.2f}")
                    else:
                        st.error(f"Closed {selected_sell}; net P/L: -${abs(pnl):.2f}")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Paper SELL failed: {exc}")
        else:
            st.caption("No open positions.")

    if st.session_state.paper_positions:
        st.subheader("📌 Open Paper Positions")
        rows = []
        for symbol, pos in st.session_state.paper_positions.items():
            try:
                current = get_latest_price(symbol)
                gross_value = pos["amount"] * current
                estimated_sell_fee = gross_value * fee_pct
                unrealized = (
                    gross_value - estimated_sell_fee
                    - pos["invested"] - pos["buy_fee"]
                )
                rows.append({
                    "Symbol": symbol,
                    "Entry Price": pos["buy_price"],
                    "Current Price": current,
                    "Units": pos["amount"],
                    "Invested (USDT)": pos["invested"],
                    "Estimated Value": gross_value,
                    "Unrealized P/L (fees est.)": unrealized,
                    "Opened (UTC)": pos["opened_at"],
                })
            except Exception as exc:
                rows.append({
                    "Symbol": symbol,
                    "Entry Price": pos["buy_price"],
                    "Current Price": None,
                    "Units": pos["amount"],
                    "Invested (USDT)": pos["invested"],
                    "Estimated Value": None,
                    "Unrealized P/L (fees est.)": None,
                    "Opened (UTC)": pos["opened_at"],
                })
                st.warning(f"Could not refresh {symbol} price: {exc}")
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    if st.session_state.paper_history:
        st.subheader("🧾 Paper Trade History")
        st.dataframe(
            pd.DataFrame(st.session_state.paper_history).iloc[::-1],
            use_container_width=True,
            hide_index=True,
        )
else:
    st.info("Press **Scan Market Now** to fetch current KuCoin market data.")

if st.session_state.scan_errors:
    with st.expander(f"Scan warnings/errors ({len(st.session_state.scan_errors)})"):
        for err in st.session_state.scan_errors[-50:]:
            st.text(err)

st.caption(
    "Risk notice: indicator-based signals are not guaranteed. "
    "Fees are estimates; slippage, spread changes, partial fills, and exchange outages "
    "are not fully simulated. Test with historical data and paper trading before "
    "considering any live trading."
)
