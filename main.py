import json
import math
import os
import urllib.error
import urllib.parse
import urllib.request

from pathlib import Path
from typing import Any, TypedDict

from dotenv import load_dotenv
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=True)

COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")

BASE_URL = "https://api.coingecko.com/api/v3"
REQUEST_TIMEOUT = 30
MARKET_LIMIT = 100


HEADERS = {
    "Accept": "application/json",
    "User-Agent": "CryptoAnalysisAgent/1.0"
}


class CryptoState(TypedDict):
    question: str
    market_data: dict[str, Any]
    intent: str
    analysis: str
    response: str


llm = ChatOllama(
    model="smollm2:360m",
    temperature=0.1,
    num_predict=140,
    client_kwargs={"timeout": 60},
)


# API COMMUNICATION
def fetch_coingecko(
    endpoint: str,
    params: dict[str, Any] | None = None
) -> Any:

    if not COINGECKO_API_KEY:
        raise RuntimeError(
            "COINGECKO_API_KEY is missing. Add it to the project .env file."
        )

    query_string = urllib.parse.urlencode(params or {})
    url = f"{BASE_URL}{endpoint}"

    if query_string:
        url = f"{url}?{query_string}"

    request = urllib.request.Request(
        url,
        headers={**HEADERS, "x-cg-demo-api-key": COINGECKO_API_KEY},
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
        if error.code in (401, 403):
            message = "CoinGecko rejected the Demo API key. Check COINGECKO_API_KEY."
        elif error.code == 429:
            message = "CoinGecko rate limit reached. Wait briefly, then retry."
        elif error.code >= 500:
            message = "CoinGecko is temporarily unavailable. Try again later."
        else:
            message = f"CoinGecko returned HTTP {error.code}."

        raise RuntimeError(message) from error

    except urllib.error.URLError as error:
        raise RuntimeError(
            f"Could not connect to CoinGecko: {error.reason}"
        ) from error

    except (json.JSONDecodeError, UnicodeDecodeError) as error:
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

    if not is_valid_number(first_value) or not is_valid_number(latest_value):
        return None

    if first_value == 0:
        return None

    return (
        (latest_value - first_value) / first_value
    ) * 100


def is_valid_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def as_number(data: Any, key: str) -> float | int | None:
    value = data.get(key) if isinstance(data, dict) else None
    return value if is_valid_number(value) else None


def get_historical_change(
    historical_data: dict,
    data_key: str
) -> float | None:

    if not isinstance(historical_data, dict):
        return None

    observations = historical_data.get(data_key, [])

    if not isinstance(observations, list) or len(observations) < 2:
        return None

    first, latest = observations[0], observations[-1]
    if (
        not isinstance(first, (list, tuple)) or len(first) < 2
        or not isinstance(latest, (list, tuple)) or len(latest) < 2
    ):
        return None

    return calculate_percentage_change(
        first[1],
        latest[1]
    )


def calculate_market_breadth(coins: list[dict]) -> dict[str, int]:
    changes = [
        coin.get("price_change_percentage_24h")
        for coin in coins
        if is_valid_number(coin.get("price_change_percentage_24h"))
    ]

    return {
        "sample_size": len(changes),
        "advancing": sum(change > 0 for change in changes),
        "declining": sum(change < 0 for change in changes),
        "unchanged": sum(change == 0 for change in changes),
    }


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

    if not isinstance(markets, list):
        raise ValueError(
            "CoinGecko did not return cryptocurrency market data."
        )

    markets = [coin for coin in markets if isinstance(coin, dict)]
    if not markets:
        raise ValueError(
            "CoinGecko returned no valid cryptocurrency market entries."
        )

    numeric_fields = (
        "current_price",
        "market_cap",
        "total_volume",
        "price_change_percentage_24h",
    )
    for coin in markets:
        coin["name"] = coin.get("name") if isinstance(coin.get("name"), str) else "Unknown"
        coin["symbol"] = coin.get("symbol") if isinstance(coin.get("symbol"), str) else ""
        coin["id"] = coin.get("id") if isinstance(coin.get("id"), str) else None
        for field in numeric_fields:
            if not is_valid_number(coin.get(field)):
                coin[field] = None

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

    if not isinstance(historical_data, dict) or historical_data.get("error"):
        endpoint_errors["historical_data"] = (
            historical_data.get("error", "CoinGecko returned an invalid response.")
            if isinstance(historical_data, dict)
            else "CoinGecko returned an invalid response."
        )

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
    market_breadth_24h = calculate_market_breadth(markets)

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

    if not isinstance(global_data, dict) or global_data.get("error"):
        endpoint_errors["global_market"] = (
            global_data.get("error", "CoinGecko returned an invalid response.")
            if isinstance(global_data, dict)
            else "CoinGecko returned an invalid response."
        )
        global_market = {}
    else:
        global_market = global_data.get("data", {})
        if not isinstance(global_market, dict):
            endpoint_errors["global_market"] = (
                "CoinGecko returned invalid global market data."
            )
            global_market = {}

    # Trending cryptocurrencies
    trending_data = fetch_optional("/search/trending")

    if not isinstance(trending_data, dict) or trending_data.get("error"):
        endpoint_errors["trending"] = (
            trending_data.get("error", "CoinGecko returned an invalid response.")
            if isinstance(trending_data, dict)
            else "CoinGecko returned an invalid response."
        )
        trending_items = []
    else:
        trending_items = trending_data.get("coins", [])
        if not isinstance(trending_items, list):
            endpoint_errors["trending"] = (
                "CoinGecko returned invalid trending coin data."
            )
            trending_items = []

    trending_coins = []

    for coin in trending_items:
        if not isinstance(coin, dict):
            continue
        item = coin.get("item", {})
        if not isinstance(item, dict):
            continue

        trending_coins.append({
            "name": item.get("name") if isinstance(item.get("name"), str) else "Unknown",
            "symbol": item.get("symbol") if isinstance(item.get("symbol"), str) else "",
            "market_cap_rank": (
                item.get("market_cap_rank")
                if isinstance(item.get("market_cap_rank"), int)
                and not isinstance(item.get("market_cap_rank"), bool)
                else None
            )
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
            "total_market_cap_usd": as_number(
                global_market.get("total_market_cap"), "usd"
            ),

            "total_volume_24h_usd": as_number(
                global_market.get("total_volume"), "usd"
            ),

            "market_cap_change_24h_percent": as_number(
                global_market, "market_cap_change_percentage_24h_usd"
            ),

            "bitcoin_dominance_percent": as_number(
                global_market.get("market_cap_percentage"), "btc"
            )
        },

        "gainers_24h": gainers,
        "losers_24h": losers,
        "market_breadth_24h": market_breadth_24h,

        "top_10_cryptocurrencies": [
            {
                "id": coin.get("id"),
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
def understand_intent(state: CryptoState) -> dict[str, str]:
    """Map common questions to the existing deterministic analysis categories."""
    question = state["question"].lower().strip()

    if any(term in question for term in (
        "invest", "investment", "should i", "buy", "sell", "forecast",
        "prediction", "predict", "what will", "why did", "what caused"
    )):
        intent = "unsupported"
    elif "movement" in question and any(
        word in question for word in ("mean", "means", "meaning", "explain")
    ):
        intent = "movement_meaning"
    elif any(term in question for term in (
        "gainer", "best performing", "performing best", "best performers",
        "going up", "up the most", "highest gains", "highest performing",
        "top performers", "top performing", "performing the best", "best coins",
        "best cryptocurrencies"
    )):
        intent = "gainers"
    elif any(term in question for term in (
        "loser", "worst performing", "performing worst", "worst performers",
        "losing the most", "going down", "down the most", "largest losses",
        "biggest losses", "underperforming"
    )):
        intent = "losers"
    elif "trending" in question:
        intent = "trending"
    elif any(term in question for term in (
        "top 10", "top ten", "largest", "top cryptocurrencies", "top crypto"
    )):
        intent = "top_coins"
    elif "bitcoin" in question or "btc" in question:
        intent = "bitcoin"
    elif any(term in question for term in (
        "market", "global", "overview", "happening", "situation"
    )):
        intent = "market"
    else:
        intent = "unsupported"

    return {"intent": intent}


def analyse_crypto(state: CryptoState) -> dict[str, str]:

    data = state["market_data"]
    intent = state["intent"]

    print("\nPreparing market analysis...")

    bitcoin = data.get("bitcoin") or {}
    global_market = data.get("global_market") or {}

    # General market concepts do not require fresh market data.
    if intent == "movement_meaning":
        analysis = (
            "A negative market movement means prices declined during the "
            "stated period. A positive movement means prices increased. "
            "This describes the observed change; it does not explain its "
            "cause or predict future prices."
        )

    # Gainers
    elif intent == "gainers":

        coins = data.get("gainers_24h", [])

        analysis = (
            "TOP 10 CRYPTOCURRENCY GAINERS (24H)\n"
            "===================================\n\n"
            f"{format_coin_list(coins)}\n\n"
            f"Scope: {data.get('gainers_losers_scope', 'available market data')}."
        )

        if coins:
            strongest = coins[0]

            analysis += (
                f"\n\nStrongest performer: {strongest['name']} "
                f"({strongest['symbol'].upper()}) at "
                f"{format_percentage(strongest['change_24h_percent'])}."
            )

    # Losers
    elif intent == "losers":

        coins = data.get("losers_24h", [])

        analysis = (
            "TOP 10 CRYPTOCURRENCY LOSERS (24H)\n"
            f"{format_coin_list(coins)}\n\n"
            f"Scope: {data.get('gainers_losers_scope', 'available market data')}."
        )

    # Trending
    elif intent == "trending":

        coins = data.get("trending_coins", [])

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
        intent == "top_coins"
    ):

        coins = data.get("top_10_cryptocurrencies", [])

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
    elif intent == "bitcoin":

        analysis = (
            "BITCOIN MARKET ANALYSIS\n"
            f"Current Price: {format_price(bitcoin.get('current_price_usd'))}\n"
            f"Market Cap: {format_number(bitcoin.get('market_cap_usd'))}\n"
            f"Market Rank: {bitcoin.get('market_cap_rank') or 'Unavailable'}\n"
            f"24H Trading Volume: {format_number(bitcoin.get('total_volume_24h_usd'))}\n"
            f"24H Price Change: {format_percentage(bitcoin.get('price_change_24h_percent'))}\n"
            f"7D Price Change: {format_percentage(bitcoin.get('price_change_7d_percent'))}\n"
            f"7D Volume Change: {format_percentage(bitcoin.get('volume_change_7d_percent'))}"
        )

    # Global market overview
    elif intent == "market":

        analysis = (
            "GLOBAL CRYPTOCURRENCY MARKET\n"
            f"Total Market Capitalization: "
            f"{format_number(global_market.get('total_market_cap_usd'))}\n"
            f"24H Trading Volume: "
            f"{format_number(global_market.get('total_volume_24h_usd'))}\n"
            f"24H Market Cap Change: "
            f"{format_percentage(global_market.get('market_cap_change_24h_percent'))}\n"
            f"Bitcoin Dominance: "
            f"{format_percentage(global_market.get('bitcoin_dominance_percent'))}"
        )

        breadth = data.get("market_breadth_24h", {})
        sample_size = breadth.get("sample_size", 0)

        if sample_size:
            advancing = breadth["advancing"]
            declining = breadth["declining"]
            unchanged = breadth["unchanged"]
            tilt = (
                "More tracked coins rose than fell."
                if advancing > declining
                else "More tracked coins fell than rose."
                if declining > advancing
                else "Rising and falling coin counts were equal."
            )
            analysis += (
                "\n\nCALCULATED 24H MARKET BREADTH "
                f"(top {MARKET_LIMIT} by market cap; "
                f"{sample_size} valid changes)\n"
                f"Rose: {advancing} | Fell: {declining} | Unchanged: {unchanged}\n"
                f"{tilt}"
            )
        else:
            analysis += "\n\nCalculated 24H market breadth: Unavailable."

    # This node is only reached for a recognized intent.
    else:
        raise ValueError(f"Unsupported analysis intent: {intent}")

    analysis += format_endpoint_errors(
        data.get("endpoint_errors", {})
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


def route_analysis(state: CryptoState) -> str:
    """Select an analysis path without fetching data or invoking the model."""
    intent = state["intent"]
    if intent == "unsupported":
        return "unsupported"
    if intent == "movement_meaning":
        return "analyse"

    data = state.get("market_data")
    if not isinstance(data, dict) or not data:
        return "missing_data"

    required_data = {
        "bitcoin": "bitcoin",
        "market": "global_market",
        "gainers": "gainers_24h",
        "losers": "losers_24h",
        "top_coins": "top_10_cryptocurrencies",
        "trending": "trending_coins",
    }
    if required_data[intent] not in data:
        return "missing_data"

    return "analyse"


def unsupported_request(state: CryptoState) -> dict[str, str]:
    analysis = (
        "I couldn't identify that request. Ask about Bitcoin, the global "
        "market, top 10 cryptocurrencies, gainers, losers, trending coins, "
        "or what positive and negative market movements mean."
    )
    return {"analysis": analysis, "response": analysis}


def missing_market_data(state: CryptoState) -> dict[str, str]:
    analysis = (
        "Market data for this request is unavailable. Refresh the market "
        "data and try again."
    )
    return {"analysis": analysis, "response": analysis}


workflow = StateGraph(CryptoState)

workflow.add_node(
    "fetch_market_data",
    fetch_market_data
)

workflow.add_node(
    "analyse_crypto",
    analyse_crypto
)
workflow.add_node("understand_intent", understand_intent)
workflow.add_node("unsupported_request", unsupported_request)
workflow.add_node("missing_market_data", missing_market_data)

workflow.add_edge(START, "fetch_market_data")
workflow.add_edge("fetch_market_data", "understand_intent")
workflow.add_conditional_edges(
    "understand_intent",
    route_analysis,
    {
        "analyse": "analyse_crypto",
        "unsupported": "unsupported_request",
        "missing_data": "missing_market_data",
    },
)
workflow.add_edge("analyse_crypto", END)
workflow.add_edge("unsupported_request", END)
workflow.add_edge("missing_market_data", END)

graph = workflow.compile()

analysis_workflow = StateGraph(CryptoState)

analysis_workflow.add_node(
    "analyse_crypto",
    analyse_crypto
)
analysis_workflow.add_node("understand_intent", understand_intent)
analysis_workflow.add_node("unsupported_request", unsupported_request)
analysis_workflow.add_node("missing_market_data", missing_market_data)


def explain_crypto(state: CryptoState) -> dict[str, str]:
    """Explain Python-verified market analysis without fetching new data."""
    analysis = state["analysis"]

    if analysis.startswith("I couldn't identify that request."):
        return {"response": analysis}

    try:
        result = llm.invoke([
            SystemMessage(content=(
                "Use only the verified facts below. Copy values and signs "
                "exactly. Do not add causes or predictions."
            )),
            HumanMessage(content=(
                f"Question: {state['question']}\n"
                f"Verified facts:\n{analysis}\n"
                "Answer in 1-3 short bullets. State if requested data is unavailable."
            ))
        ])
        response = result.content
        if isinstance(response, str) and response.strip():
            response = response.strip()
            if response == analysis.strip():
                return {"response": response}
            print("Ollama changed the verified analysis; using Python analysis.")
    except Exception as error:
        print(f"Ollama explanation unavailable; using Python analysis: {error}")

    return {"response": analysis}


analysis_workflow.add_node(
    "explain_crypto",
    explain_crypto
)

analysis_workflow.add_edge(START, "understand_intent")
analysis_workflow.add_conditional_edges(
    "understand_intent",
    route_analysis,
    {
        "analyse": "analyse_crypto",
        "unsupported": "unsupported_request",
        "missing_data": "missing_market_data",
    },
)
analysis_workflow.add_edge("analyse_crypto", "explain_crypto")
analysis_workflow.add_edge("explain_crypto", END)
analysis_workflow.add_edge("unsupported_request", END)
analysis_workflow.add_edge("missing_market_data", END)

analysis_graph = analysis_workflow.compile()

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