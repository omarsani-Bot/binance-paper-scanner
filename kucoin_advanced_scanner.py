
import streamlit as st
import pandas as pd
import ccxt
from datetime import datetime, timezone

st.set_page_config(
    page_title="KuCoin Advanced Scanner",
    page_icon="📈",
    layout="wide"
)

EXCHANGES = {
    "KuCoin": "kucoin",
    "Binance": "binance",
    "Bybit": "bybit",
    "OKX": "okx",
    "Gate.io": "gateio",
    "Bitget": "bitget",
    "MEXC": "mexc",
    "CoinEx": "coinex",
    "HTX": "htx",
    "BingX": "bingx",
}

st.title("📈 KuCoin Advanced Scanner")
st.caption("Compare the same USDT spot pair across 10 exchanges")

@st.cache_resource
def get_exchange(exchange_id):
    cls = getattr(ccxt, exchange_id)
    return cls({
        "enableRateLimit": True,
        "timeout": 20000,
        "options": {"defaultType": "spot"},
    })

def compare_prices(pair):
    pair = pair.strip().upper().replace("-", "/").replace("_", "/")
    if "/" not in pair:
        pair += "/USDT"

    base, quote = pair.split("/", 1)
    if not base or quote != "USDT":
        raise ValueError("Use a USDT pair, e.g. BTC/USDT")

    rows = []

    progress = st.progress(0)
    status = st.empty()

    for i, (name, exchange_id) in enumerate(EXCHANGES.items()):
        status.write(f"Checking {name}...")
        row = {
            "Exchange": name,
            "Pair": pair,
            "Last Price (USDT)": None,
            "Bid": None,
            "Ask": None,
            "24h Change (%)": None,
            "Difference from Lowest (%)": None,
            "Status": "Unavailable",
        }

        try:
            ex = get_exchange(exchange_id)
            markets = ex.load_markets()

            market = markets.get(pair)

            if not market or market.get("active") is False:
                row["Status"] = "Pair unavailable"
            elif market.get("spot") is not True:
                row["Status"] = "Not a spot market"
            else:
                ticker = ex.fetch_ticker(pair)
                last = ticker.get("last")

                if last is not None and float(last) > 0:
                    row["Last Price (USDT)"] = float(last)
                    row["Bid"] = ticker.get("bid")
                    row["Ask"] = ticker.get("ask")
                    row["24h Change (%)"] = ticker.get("percentage")
                    row["Status"] = "OK"
                else:
                    row["Status"] = "No valid price"

        except Exception as e:
            row["Status"] = f"Error: {type(e).__name__}"

        rows.append(row)
        progress.progress((i + 1) / len(EXCHANGES))

    status.empty()
    progress.empty()

    df = pd.DataFrame(rows)
    valid = df["Last Price (USDT)"].dropna()

    if not valid.empty:
        lowest = valid.min()
        df.loc[valid.index, "Difference from Lowest (%)"] = (
            (valid / lowest - 1) * 100
        )

    return df

st.subheader("🌐 Compare Exchange Prices")

with st.form("compare_form"):
    pair = st.text_input(
        "Coin pair",
        value="BTC/USDT",
        placeholder="BTC/USDT, ETH/USDT, SOL/USDT"
    )
    submitted = st.form_submit_button(
        "Compare 10 Exchanges",
        type="primary",
        use_container_width=True
    )

if submitted:
    try:
        with st.spinner("Fetching public market prices..."):
            df = compare_prices(pair)

        st.session_state["comparison_results"] = df
        st.session_state["comparison_pair"] = pair.upper()

    except Exception as e:
        st.error(f"Comparison failed: {type(e).__name__}: {e}")

if "comparison_results" in st.session_state:
    df = st.session_state["comparison_results"]
    valid = df.dropna(subset=["Last Price (USDT)"])

    if not valid.empty:
        lowest_row = valid.loc[
            valid["Last Price (USDT)"].idxmin()
        ]
        highest_row = valid.loc[
            valid["Last Price (USDT)"].idxmax()
        ]

        low = float(lowest_row["Last Price (USDT)"])
        high = float(highest_row["Last Price (USDT)"])
        gap = ((high / low) - 1) * 100 if low > 0 else 0

        a, b, c = st.columns(3)
        a.metric("Exchanges responding", f"{len(valid)}/10")
        b.metric("Lowest price", f"{low:.10g} USDT")
        c.metric("Price gap", f"{gap:.4f}%")

        st.write(
            f"**Lowest:** {lowest_row['Exchange']}  |  "
            f"**Highest:** {highest_row['Exchange']}"
        )

    st.subheader("Price comparison table")
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True
    )

    st.download_button(
        "Download results as CSV",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name="exchange_prices.csv",
        mime="text/csv",
        use_container_width=True
    )

st.caption(
    "Public spot prices only. No API keys or live orders. "
    "Price gaps do not guarantee profit; fees, slippage, "
    "liquidity and transfer delays may eliminate arbitrage opportunities."
)

st.caption(
    "Last page update: " +
    datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
)
