import json
import os
import urllib.error
import urllib.parse
import urllib.request

from pathlib import Path
from typing import Any, TypedDict

from dotenv import load_dotenv
from langgraph.graph import StateGraph, START, END


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=True)

COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")

BASE_URL = "https://api.coingecko.com/api/v3"
REQUEST_TIMEOUT = 30
MARKET_LIMIT = 100


if not COINGECKO_API_KEY:
    raise ValueError(
        "COINGECKO_API_KEY is missing from your .env file."
    )


HEADERS = {
    "x-cg-demo-api-key": COINGECKO_API_KEY,
    "Accept": "application/json",
    "User-Agent": "CryptoAnalysisAgent/1.0"
}


class CryptoState(TypedDict):
    question: str
    market_data: dict[str, Any]
    analysis: str


# API COMMUNICATION
def fetch_coingecko(
    endpoint: str,
    params: dict[str, Any] | None = None
) -> Any:

    query_string = urllib.parse.urlencode(params or {})
    url = f"{BASE_URL}{endpoint}"

    if query_string:
        url = f"{url}?{query_string}"

    request = urllib.request.Request(
        url,
        headers=HEADERS,
        method="GET"
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=REQUEST_TIMEOUT
        ) as response:

            response_data = response.read().decode("utf-8")
            return json.loads(response_data)

    except urllib.error.HTTPError as error:
        error_body = error.read().decode("utf-8", errors="replace")

        raise RuntimeError(
            f"CoinGecko returned HTTP {error.code}: {error_body}"
        ) from error

    except urllib.error.URLError as error:
        raise RuntimeError(
            f"Could not connect to CoinGecko: {error.reason}"
        ) from error

    except json.JSONDecodeError as error:
        raise RuntimeError(
            "CoinGecko returned an invalid JSON response."
        ) from error

def fetch_optional(
    endpoint: str,
    params: dict[str, Any] | None = None
) -> Any:

    try:
        return fetch_coingecko(endpoint, params)

    except Exception as error:
        return {"error": str(error)}


# DATA CALCULATIONS
def calculate_percentage_change(
    first_value: float | None,
    latest_value: float | None
) -> float | None:

    if first_value is None or latest_value is None:
        return None

    if first_value == 0:
        return None

    return (
        (latest_value - first_value) / first_value
    ) * 100


def get_historical_change(
    historical_data: dict,
    data_key: str
) -> float | None:

    observations = historical_data.get(data_key, [])

    if len(observations) < 2:
        return None

    first_value = observations[0][1]
    latest_value = observations[-1][1]

    return calculate_percentage_change(
        first_value,
        latest_value
    )


# FETCH AND PREPARE MARKET DATA
def get_crypto_market_data() -> dict[str, Any]:

    endpoint_errors = {}

    print("\nFetching cryptocurrency market data...")

    # Top 100 cryptocurrencies
    markets = fetch_coingecko(
        "/coins/markets",
        {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": MARKET_LIMIT,
            "page": 1,
            "sparkline": "false",
            "price_change_percentage": "24h"
        }
    )

    if not isinstance(markets, list) or not markets:
        raise ValueError(
            "CoinGecko did not return cryptocurrency market data."
        )

    bitcoin = next(
        (
            coin for coin in markets
            if coin.get("id") == "bitcoin"
        ),
        None
    )

    if bitcoin is None:
        raise ValueError(
            "Bitcoin data was not found in the market response."
        )

    # Bitcoin historical data
    historical_data = fetch_optional(
        "/coins/bitcoin/market_chart",
        {
            "vs_currency": "usd",
            "days": 7
        }
    )

    if "error" in historical_data:
        endpoint_errors["historical_data"] = historical_data["error"]

        seven_day_change = None
        seven_day_volume_change = None

    else:
        seven_day_change = get_historical_change(
            historical_data,
            "prices"
        )

        seven_day_volume_change = get_historical_change(
            historical_data,
            "total_volumes"
        )

    # Sort cryptocurrencies by 24-hour percentage change
    valid_coins = [
        coin for coin in markets
        if coin.get("price_change_percentage_24h") is not None
    ]

    sorted_coins = sorted(
        valid_coins,
        key=lambda coin: coin["price_change_percentage_24h"],
        reverse=True
    )

    # Top gainers
    gainers = [
        {
            "name": coin.get("name"),
            "symbol": coin.get("symbol"),
            "price_usd": coin.get("current_price"),
            "change_24h_percent": coin.get(
                "price_change_percentage_24h"
            ),
            "market_cap_usd": coin.get("market_cap")
        }
        for coin in sorted_coins
        if coin["price_change_percentage_24h"] > 0
    ][:10]

    # Top losers
    losers = [
        {
            "name": coin.get("name"),
            "symbol": coin.get("symbol"),
            "price_usd": coin.get("current_price"),
            "change_24h_percent": coin.get(
                "price_change_percentage_24h"
            ),
            "market_cap_usd": coin.get("market_cap")
        }
        for coin in reversed(sorted_coins)
        if coin["price_change_percentage_24h"] < 0
    ][:10]

    # Global market data
    global_data = fetch_optional("/global")

    if "error" in global_data:
        endpoint_errors["global_market"] = global_data["error"]

    global_market = global_data.get("data", {})

    # Trending cryptocurrencies
    trending_data = fetch_optional("/search/trending")

    if "error" in trending_data:
        endpoint_errors["trending"] = trending_data["error"]

    trending_coins = []

    for coin in trending_data.get("coins", []):
        item = coin.get("item", {})

        trending_coins.append({
            "name": item.get("name"),
            "symbol": item.get("symbol"),
            "market_cap_rank": item.get("market_cap_rank")
        })

    # Prepare final structured data
    return {
        "bitcoin": {
            "name": bitcoin.get("name"),
            "symbol": bitcoin.get("symbol"),
            "current_price_usd": bitcoin.get("current_price"),
            "market_cap_usd": bitcoin.get("market_cap"),
            "market_cap_rank": bitcoin.get("market_cap_rank"),
            "total_volume_24h_usd": bitcoin.get("total_volume"),
            "price_change_24h_percent": bitcoin.get(
                "price_change_percentage_24h"
            ),
            "price_change_7d_percent": seven_day_change,
            "volume_change_7d_percent": seven_day_volume_change
        },

        "global_market": {
            "total_market_cap_usd": global_market.get(
                "total_market_cap", {}
            ).get("usd"),

            "total_volume_24h_usd": global_market.get(
                "total_volume", {}
            ).get("usd"),

            "market_cap_change_24h_percent": global_market.get(
                "market_cap_change_percentage_24h_usd"
            ),

            "bitcoin_dominance_percent": global_market.get(
                "market_cap_percentage", {}
            ).get("btc")
        },

        "gainers_24h": gainers,
        "losers_24h": losers,

        "top_10_cryptocurrencies": [
            {
                "name": coin.get("name"),
                "symbol": coin.get("symbol"),
                "price_usd": coin.get("current_price"),
                "market_cap_usd": coin.get("market_cap"),
                "market_cap_rank": coin.get("market_cap_rank"),
                "price_change_24h_percent": coin.get(
                    "price_change_percentage_24h"
                )
            }
            for coin in markets[:10]
        ],

        "trending_coins": trending_coins,
        "endpoint_errors": endpoint_errors,

        "gainers_losers_scope": (
            f"Top {MARKET_LIMIT} cryptocurrencies by market capitalization"
        ),

        "data_source": "CoinGecko Demo API"
    }

# FORMATTING HELPERS
def format_price(value: float | None) -> str:

    if value is None:
        return "Unavailable"

    if abs(value) >= 1:
        return f"${value:,.2f}"

    return f"${value:.8f}".rstrip("0").rstrip(".")


def format_number(value: float | None) -> str:

    if value is None:
        return "Unavailable"

    if abs(value) >= 1_000_000_000_000:
        return f"${value / 1_000_000_000_000:.2f}T"

    if abs(value) >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"

    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"

    return f"${value:,.2f}"


def format_percentage(value: float | None) -> str:

    if value is None:
        return "Unavailable"

    return f"{value:+.2f}%"


def format_coin_list(coins: list[dict]) -> str:

    if not coins:
        return "No matching cryptocurrency data is available."

    lines = []

    for index, coin in enumerate(coins, 1):

        symbol = (coin.get("symbol") or "").upper()

        lines.append(
            f"{index}. {coin.get('name', 'Unknown')} ({symbol})\n"
            f"   Price: {format_price(coin.get('price_usd'))}\n"
            f"   24H Change: {format_percentage(coin.get('change_24h_percent'))}\n"
            f"   Market Cap: {format_number(coin.get('market_cap_usd'))}"
        )

    return "\n\n".join(lines)


def format_endpoint_errors(errors: dict) -> str:

    if not errors:
        return ""

    lines = [
        "\n\nDATA AVAILABILITY NOTES"
    ]

    for endpoint, message in errors.items():
        lines.append(f"- {endpoint}: {message}")

    return "\n".join(lines)


# MARKET ANALYSIS
def analyse_crypto(state: CryptoState) -> dict[str, str]:

    question = state["question"].lower().strip()
    data = state["market_data"]

    print("\nPreparing market analysis...")

    bitcoin = data["bitcoin"]
    global_market = data["global_market"]

    # Gainers
    if "gainer" in question:

        coins = data["gainers_24h"]

        analysis = (
            "TOP 10 CRYPTOCURRENCY GAINERS (24H)\n"
            "===================================\n\n"
            f"{format_coin_list(coins)}\n\n"
            f"Scope: {data['gainers_losers_scope']}."
        )

        if coins:
            strongest = coins[0]

            analysis += (
                f"\n\nStrongest performer: {strongest['name']} "
                f"({strongest['symbol'].upper()}) at "
                f"{format_percentage(strongest['change_24h_percent'])}."
            )

    # Losers
    elif "loser" in question:

        coins = data["losers_24h"]

        analysis = (
            "TOP 10 CRYPTOCURRENCY LOSERS (24H)\n"
            f"{format_coin_list(coins)}\n\n"
            f"Scope: {data['gainers_losers_scope']}."
        )

    # Trending
    elif "trending" in question:

        coins = data["trending_coins"]

        if coins:
            lines = []

            for index, coin in enumerate(coins, 1):

                rank = coin.get("market_cap_rank")

                rank_text = (
                    f"Market Rank: #{rank}"
                    if rank is not None
                    else "Market Rank: Unavailable"
                )

                lines.append(
                    f"{index}. {coin.get('name', 'Unknown')} "
                    f"({coin.get('symbol', 'N/A')}) | {rank_text}"
                )

            coin_text = "\n".join(lines)

        else:
            coin_text = "No trending data is available."

        analysis = (
            "TRENDING CRYPTOCURRENCIES\n"
            f"{coin_text}\n\n"
            "Trending status reflects CoinGecko search activity. "
            "It does not indicate profitability or investment quality."
        )

    # Top 10 cryptocurrencies
    elif (
        "top 10" in question
        or "top ten" in question
        or "largest" in question
    ):

        coins = data["top_10_cryptocurrencies"]

        lines = []

        for index, coin in enumerate(coins, 1):

            symbol = (coin.get("symbol") or "").upper()

            lines.append(
                f"{index}. {coin.get('name', 'Unknown')} ({symbol})\n"
                f"   Price: {format_price(coin.get('price_usd'))}\n"
                f"   Market Cap: {format_number(coin.get('market_cap_usd'))}\n"
                f"   24H Change: {format_percentage(coin.get('price_change_24h_percent'))}"
            )

        analysis = (
            "TOP 10 CRYPTOCURRENCIES BY MARKET CAPITALIZATION\n"
            + (
                "\n\n".join(lines)
                if lines
                else "No cryptocurrency data is available."
            )
        )

    # Bitcoin
    elif "bitcoin" in question or "btc" in question:

        analysis = (
            "BITCOIN MARKET ANALYSIS\n"
            f"Current Price: {format_price(bitcoin['current_price_usd'])}\n"
            f"Market Cap: {format_number(bitcoin['market_cap_usd'])}\n"
            f"Market Rank: {bitcoin['market_cap_rank'] or 'Unavailable'}\n"
            f"24H Trading Volume: {format_number(bitcoin['total_volume_24h_usd'])}\n"
            f"24H Price Change: {format_percentage(bitcoin['price_change_24h_percent'])}\n"
            f"7D Price Change: {format_percentage(bitcoin['price_change_7d_percent'])}\n"
            f"7D Volume Change: {format_percentage(bitcoin['volume_change_7d_percent'])}"
        )

    # Global market overview
    elif (
        "market" in question
        or "global" in question
        or "overview" in question
        or not question
    ):

        analysis = (
            "GLOBAL CRYPTOCURRENCY MARKET\n"
            f"Total Market Capitalization: "
            f"{format_number(global_market['total_market_cap_usd'])}\n"
            f"24H Trading Volume: "
            f"{format_number(global_market['total_volume_24h_usd'])}\n"
            f"24H Market Cap Change: "
            f"{format_percentage(global_market['market_cap_change_24h_percent'])}\n"
            f"Bitcoin Dominance: "
            f"{format_percentage(global_market['bitcoin_dominance_percent'])}"
        )

    # Unrecognized question
    else:

        analysis = (
            "I couldn't identify that request.\n\n"
            "Try asking about:\n"
            "- Bitcoin analysis\n"
            "- Global crypto market overview\n"
            "- Top 10 cryptocurrencies\n"
            "- Top gainers\n"
            "- Top losers\n"
            "- Trending cryptocurrencies"
        )

    analysis += format_endpoint_errors(
        data["endpoint_errors"]
    )

    return {
        "analysis": analysis
    }

# LANGGRAPH WORKFLOW
def fetch_market_data(state: CryptoState) -> dict:

    market_data = get_crypto_market_data()

    return {
        "market_data": market_data
    }


workflow = StateGraph(CryptoState)

workflow.add_node(
    "fetch_market_data",
    fetch_market_data
)

workflow.add_node(
    "analyse_crypto",
    analyse_crypto
)

workflow.add_edge(START, "fetch_market_data")
workflow.add_edge("fetch_market_data", "analyse_crypto")
workflow.add_edge("analyse_crypto", END)

graph = workflow.compile()

# APPLICATION ENTRY POINT
if __name__ == "__main__":

    print("=" * 55)
    print("          CRYPTO ANALYSIS AGENT")
    print("=" * 55)

    question = input(
        "\nWhat would you like to know about the crypto market? "
    ).strip()

    if not question:
        print("\nPlease enter a question.")
    else:
        try:
            result = graph.invoke({
                "question": question,
                "market_data": {},
                "analysis": ""
            })

            print("\n" + "=" * 55)
            print("MARKET ANALYSIS")
            print("=" * 55)

            print(result["analysis"])

            print("\n" + "=" * 55)
            print("Source: CoinGecko Demo API")
            print("=" * 55)

        except Exception as error:
            print("\nUnable to complete the market analysis.")
            print(f"Error: {error}")