import logging

import streamlit as st
import pandas as pd
import plotly.express as px

from main import (
    get_crypto_market_data,
    fetch_coingecko,
    analysis_graph
)

logger = logging.getLogger(__name__)

# PAGE CONFIGURATION
st.set_page_config(
    page_title="Crypto Analysis Agent",
    page_icon=":material/query_stats:",
    layout="wide",
    initial_sidebar_state="expanded"
)


# DATA LOADING
@st.cache_data(ttl=300, max_entries=40)
def load_historical_data(coin_id, days):
    return fetch_coingecko(
        f"/coins/{coin_id}/market_chart",
        {
            "vs_currency": "usd",
            "days": days
        }
    )


@st.cache_data(ttl=60)
def load_market_data():
    return get_crypto_market_data()


# FORMATTING HELPERS
def format_price(value):
    if value is None:
        return "Unavailable"

    if abs(value) >= 1:
        return f"${value:,.2f}"

    return f"${value:.8f}".rstrip("0").rstrip(".")


def format_number(value):
    if value is None:
        return "Unavailable"

    if abs(value) >= 1_000_000_000_000:
        return f"${value / 1_000_000_000_000:.2f}T"

    if abs(value) >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"

    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"

    return f"${value:,.2f}"


def format_percentage(value):
    if value is None:
        return "Unavailable"

    return f"{value:+.2f}%"


def prepare_coin_dataframe(coins):
    df = pd.DataFrame(coins)

    if "symbol" in df.columns:
        df["symbol"] = df["symbol"].fillna("").str.upper()

    return df.drop(columns=["id"], errors="ignore").rename(columns={
        "name": "Name",
        "symbol": "Symbol",
        "price_usd": "Price (USD)",
        "market_cap_usd": "Market Cap (USD)",
        "market_cap_rank": "Market rank",
        "change_24h_percent": "24h change (%)",
        "price_change_24h_percent": "24h change (%)",
    })


def prepare_historical_prices(prices):
    rows = [
        row[:2]
        for row in prices
        if isinstance(row, (list, tuple)) and len(row) >= 2
    ] if isinstance(prices, list) else []

    if not rows:
        return pd.DataFrame(columns=["Timestamp", "Price", "Date"])

    df = pd.DataFrame(rows, columns=["Timestamp", "Price"])
    df["Timestamp"] = pd.to_numeric(df["Timestamp"], errors="coerce")
    df["Price"] = pd.to_numeric(df["Price"], errors="coerce")
    df["Date"] = pd.to_datetime(
        df["Timestamp"], unit="ms", errors="coerce", utc=True
    )
    return df.dropna(subset=["Date", "Price"]).sort_values("Date")


COIN_COLUMN_CONFIG = {
    "Price (USD)": st.column_config.NumberColumn(format="$%.8f"),
    "Market Cap (USD)": st.column_config.NumberColumn(format="$%.2f"),
    "24h change (%)": st.column_config.NumberColumn(format="%.2f%%"),
}


# SIDEBAR
with st.sidebar:
    st.title(":material/query_stats: Crypto agent")

    page = st.radio(
        "Pages",
        [
            "Market overview",
            "Bitcoin analysis",
            "Price explorer",
            "Gainers & losers",
            "Trending coins",
            "Ask crypto agent"
        ]
    )


# HEADER
st.title("Crypto Analysis Agent")

header_col, refresh_col = st.columns([5, 1])


with refresh_col:
    refresh = st.button(
        "Refresh data",
        icon=":material/refresh:",
        width="stretch"
    )

if refresh:
    load_market_data.clear()
    load_historical_data.clear()


# FETCH DATA
try:
    with st.spinner("Fetching cryptocurrency market data..."):
        data = load_market_data()

except Exception as error:
    st.error(f"Unable to load cryptocurrency market data: {error}")
    st.stop()


# DATA AVAILABILITY
endpoint_errors = data.get("endpoint_errors", {})

if endpoint_errors:
    with st.expander("Market data warnings"):
        for endpoint, error in endpoint_errors.items():
            st.warning(f"{endpoint}: {error}")


# MARKET OVERVIEW
if page == "Market overview":

    st.subheader("Global market")

    market = data.get("global_market", {})

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Total market cap",
        format_number(market.get("total_market_cap_usd")),
        format_percentage(
            market.get("market_cap_change_24h_percent")
        ),
        delta_description="24h change",
        border=True,
    )

    col2.metric(
        "24h trading volume",
        format_number(market.get("total_volume_24h_usd")),
        border=True,
    )

    col3.metric(
        "Bitcoin dominance",
        format_percentage(
            market.get("bitcoin_dominance_percent")
        ),
        help="Bitcoin's share of the total cryptocurrency market capitalization.",
        border=True,
    )

    col4.metric(
        "Coins in top 10 table",
        len(data.get("top_10_cryptocurrencies", [])),
        border=True,
    )

    st.subheader("Bitcoin overview")

    btc = data.get("bitcoin", {})

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Bitcoin price",
        format_price(btc.get("current_price_usd")),
        border=True,
    )

    col2.metric(
        "24h change",
        format_percentage(btc.get("price_change_24h_percent")),
        border=True,
    )

    col3.metric(
        "7d change",
        format_percentage(btc.get("price_change_7d_percent")),
        border=True,
    )

    rank = btc.get("market_cap_rank")

    col4.metric(
        "Market rank",
        f"#{rank}" if rank is not None else "Unavailable",
        border=True,
    )

    st.subheader("Top 10 cryptocurrencies")

    top_coins = data.get("top_10_cryptocurrencies", [])

    if top_coins:

        st.dataframe(
            prepare_coin_dataframe(top_coins),
            width="stretch",
            hide_index=True,
            column_config=COIN_COLUMN_CONFIG,
        )

    else:
        st.info("No cryptocurrency data available.")


# BITCOIN ANALYSIS
elif page == "Bitcoin analysis":

    st.subheader("Bitcoin market analysis")

    btc = data.get("bitcoin", {})

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Current price",
        format_price(btc.get("current_price_usd")),
        border=True,
    )

    col2.metric(
        "Market capitalization",
        format_number(btc.get("market_cap_usd")),
        border=True,
    )

    col3.metric(
        "24h trading volume",
        format_number(btc.get("total_volume_24h_usd")),
        border=True,
    )

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "24h price change",
        format_percentage(btc.get("price_change_24h_percent")),
        border=True,
    )

    col2.metric(
        "7d price change",
        format_percentage(btc.get("price_change_7d_percent")),
        border=True,
    )

    col3.metric(
        "7d volume change",
        format_percentage(btc.get("volume_change_7d_percent")),
        border=True,
    )

# PRICE EXPLORER
elif page == "Price explorer":

    st.subheader("Cryptocurrency price explorer")

    coins = data.get("top_10_cryptocurrencies", [])

    # Build options using actual CoinGecko IDs.
    coin_options = {
        f"{coin.get('name', 'Unknown')} "
        f"({(coin.get('symbol') or '').upper()})": coin["id"]
        for coin in coins
        if coin.get("id")
    }
    selected_coin = st.selectbox(
        "Select cryptocurrency",
        options=list(coin_options.keys())
    )

    period_options = {
        "24 Hours": "1",
        "7 Days": "7",
        "30 Days": "30",
        "90 Days": "90"
    }

    selected_period = st.radio(
        "Historical period",
        options=list(period_options.keys()),
        horizontal=True,
        index=1
    )

    coin_id = coin_options[selected_coin]
    days = period_options[selected_period]

    try:

        with st.spinner(
            f"Loading {selected_coin} historical data..."
        ):

            history = load_historical_data(
                coin_id,
                days
                )

            if not isinstance(history, dict):
                st.error("Unexpected response from CoinGecko.")
                st.stop()

            if history.get("error"):
                st.error(
                    f"CoinGecko error: {history['error']}"
                )
                st.stop()

            prices = history.get("prices", [])
            if not prices:
                st.warning(
                    "Historical price data is unavailable for this "
                    "cryptocurrency and period."
                )
                st.stop()

            df = prepare_historical_prices(prices)
            if df.empty:
                st.warning("CoinGecko returned no valid historical price observations.")
                st.stop()

            current_price = df["Price"].iloc[-1]
            starting_price = df["Price"].iloc[0]
            price_change = (
                ((current_price - starting_price) / starting_price) * 100
                if starting_price != 0
                else None
            )

            col1, col2, col3 = st.columns(3)
            col1.metric("Latest price", format_price(current_price), border=True)
            col2.metric("Period change", format_percentage(price_change), border=True)
            col3.metric("Valid observations", len(df), border=True)

            fig = px.line(
                df,
                x="Date",
                y="Price",
                title=f"{selected_coin} price over {selected_period.lower()}",
                labels={"Date": "Date (UTC)", "Price": "Price (USD)"},
            )
            fig.update_traces(
                line=dict(color="#F7931A", width=2),
                hovertemplate=(
                    "Date: %{x|%b %d, %Y %H:%M UTC}<br>"
                    "Price: $%{y:,.8~f}<extra></extra>"
                ),
            )
            fig.update_layout(
                template="plotly_dark",
                paper_bgcolor="#0B0E11",
                plot_bgcolor="#151A21",
                font_color="#EAECEF",
                hovermode="x unified",
                height=450,
                title_x=0,
                margin=dict(l=20, r=20, t=60, b=20),
            )
            fig.update_xaxes(
                showgrid=False,
                tickformat="%b %d\n%H:%M" if days == "1" else "%b %d",
                hoverformat="%b %d, %Y %H:%M UTC",
            )
            fig.update_yaxes(
                gridcolor="#252B34",
                tickprefix="$",
                tickformat=",.8~f",
            )
            st.plotly_chart(
                fig,
                width="stretch",
                height=450,
                alt=(
                    f"{selected_coin} price over {selected_period.lower()}, "
                    f"ending at {format_price(current_price)}"
                ),
            )

    except Exception as error:
        st.error(
            f"Unable to load historical data: {error}"
        )


# GAINERS AND LOSERS
elif page == "Gainers & losers":

    st.subheader("Market movers")

    gainers_tab, losers_tab = st.tabs(
        ["Top gainers", "Top losers"]
    )

    with gainers_tab:

        st.caption(
            data.get("gainers_losers_scope", "")
        )

        gainers = data.get("gainers_24h", [])

        if gainers:

            st.dataframe(
                prepare_coin_dataframe(gainers),
                width="stretch",
                hide_index=True,
                column_config=COIN_COLUMN_CONFIG,
                alt="Top gainers by 24-hour price change",
            )

        else:

            st.info("No gainers available.")

    with losers_tab:

        st.caption(
            data.get("gainers_losers_scope", "")
        )

        losers = data.get("losers_24h", [])

        if losers:

            st.dataframe(
                prepare_coin_dataframe(losers),
                width="stretch",
                hide_index=True,
                column_config=COIN_COLUMN_CONFIG,
                alt="Top losers by 24-hour price change",
            )

        else:

            st.info("No losers available.")


# TRENDING COINS
elif page == "Trending coins":

    st.subheader("Trending cryptocurrencies")

    coins = data.get("trending_coins", [])

    if coins:

        st.dataframe(
            prepare_coin_dataframe(coins),
            width="stretch",
            hide_index=True,
            alt="Coins currently trending by CoinGecko search activity",
        )

        st.caption(
            "Trending reflects CoinGecko search activity, "
            "not investment performance."
        )

    else:

        st.info("No trending data available.")


# ASK CRYPTO AGENT
elif page == "Ask crypto agent":

    st.subheader("Ask your crypto agent")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display conversation history
    for message in st.session_state.messages:

        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Chat input
    question = st.chat_input(
        "Hi there!"
    )

    if question:

        st.session_state.messages.append({
            "role": "user",
            "content": question
        })

        with st.chat_message("user"):
            st.markdown(question)

        with st.chat_message("assistant"):

            with st.spinner("Analysing market data and preparing an explanation..."):

                try:

                    result = analysis_graph.invoke({
                        "question": question,
                        "market_data": data,
                        "analysis": ""
                    })

                    answer = result["response"]

                except Exception:
                    logger.exception("Crypto chat analysis failed")
                    answer = "Unable to analyse this question. Please try again."

                st.markdown(answer)

        st.session_state.messages.append({
            "role": "assistant",
            "content": answer
        })

    if st.session_state.messages:

        if st.button("Clear conversation"):

            st.session_state.messages = []
            st.rerun()

# FOOTER
st.divider()

st.caption(
    "Data provided by CoinGecko"
)