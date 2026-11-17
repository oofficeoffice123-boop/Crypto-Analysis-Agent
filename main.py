import os
import json
import urllib.request
import urllib.parse

from pathlib import Path
from typing import TypedDict

from dotenv import load_dotenv
from langchain_ollama import ChatOllama
from langgraph.graph import StateGraph, START, END


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=True)

COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")

if not COINGECKO_API_KEY:
    raise ValueError("COINGECKO_API_KEY is missing from your .env file")


llm = ChatOllama(
    model="qwen2.5:3b",
    temperature=0
)


BASE_URL = "https://api.coingecko.com/api/v3"

HEADERS = {
    "x-cg-demo-api-key": COINGECKO_API_KEY,
    "Accept": "application/json"
}


class CryptoState(TypedDict):
    question: str
    market_data: dict
    analysis: str


def fetch_coingecko(endpoint, params=None):

    query_string = urllib.parse.urlencode(params or {})

    url = f"{BASE_URL}{endpoint}"

    if query_string:
        url = f"{url}?{query_string}"

    request = urllib.request.Request(
        url,
        headers=HEADERS,
        method="GET"
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_optional(endpoint, params=None):

    try:
        return fetch_coingecko(endpoint, params)

    except Exception as error:
        return {
            "error": str(error)
        }


def get_crypto_market_data():

    endpoint_errors = {}

    markets = fetch_coingecko(
        "/coins/markets",
        {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": 100,
            "page": 1,
            "sparkline": "false",
            "price_change_percentage": "24h"
        }
    )

    bitcoin = next(
        (coin for coin in markets if coin["id"] == "bitcoin"),
        None
    )

    if bitcoin is None:
        raise ValueError("Bitcoin data was not returned")

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

    if historical_data.get("prices"):
        prices = historical_data["prices"]

        first_price = prices[0][1]
        latest_price = prices[-1][1]

        if first_price:
            seven_day_change = (
                (latest_price - first_price) / first_price
            ) * 100

    if historical_data.get("total_volumes"):
        volumes = historical_data["total_volumes"]

        first_volume = volumes[0][1]
        latest_volume = volumes[-1][1]

        if first_volume:
            seven_day_volume_change = (
                (latest_volume - first_volume) / first_volume
            ) * 100

    valid_coins = [
        coin for coin in markets
        if coin.get("price_change_percentage_24h") is not None
    ]

    sorted_coins = sorted(
        valid_coins,
        key=lambda coin: coin["price_change_percentage_24h"],
        reverse=True
    )

    gainers = [
        {
            "name": coin["name"],
            "symbol": coin["symbol"],
            "price_usd": coin["current_price"],
            "change_24h_percent": coin["price_change_percentage_24h"],
            "market_cap_usd": coin["market_cap"]
        }
        for coin in sorted_coins
        if coin["price_change_percentage_24h"] > 0
    ][:10]

    losers = [
        {
            "name": coin["name"],
            "symbol": coin["symbol"],
            "price_usd": coin["current_price"],
            "change_24h_percent": coin["price_change_percentage_24h"],
            "market_cap_usd": coin["market_cap"]
        }
        for coin in reversed(sorted_coins)
        if coin["price_change_percentage_24h"] < 0
    ][:10]

    global_data = fetch_optional("/global")

    if "error" in global_data:
        endpoint_errors["global_market"] = global_data["error"]

    global_market = global_data.get("data", {})

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

        "gainers_losers_scope": "Top 100 cryptocurrencies by market cap",
        "data_source": "CoinGecko Demo API"
    }

def fetch_market_data(state: CryptoState):

    print("\nFetching cryptocurrency market data...")

    market_data = get_crypto_market_data()

    return {
        "market_data": market_data
    }


def analyse_crypto(state: CryptoState):

    print("\nAnalysing market data with Qwen...")

    market_data = json.dumps(
        state["market_data"],
        indent=2
    )

    prompt = f"""
You are a cryptocurrency market analysis assistant.

USER QUESTION:
{state["question"]}

REAL MARKET DATA:
{market_data}

IMPORTANT RULES:

1. Answer the user's actual question first.
2. Use only the supplied market data.
3. Never invent missing values.
4. Never change numerical values.
5. Copy prices, market caps, volumes and percentages accurately.
6. Convert large numbers into readable units when appropriate:
   - 1 billion = 1B
   - 1 trillion = 1T
7. A null value means unavailable, NOT zero.
8. Never assume Bitcoin dominance is 100%.
9. Never invent explanations for price movements.
10. Clearly mention that gainers and losers are limited to the
    top 100 cryptocurrencies by market capitalization.
11. Do not describe trending coins as profitable investments.
12. Do not provide guaranteed financial predictions.

QUESTION HANDLING:

If the user asks for gainers:
- Show the top 10 gainers.
- Include name, symbol, price and 24-hour percentage change.
- Identify the strongest performer.
- Briefly explain the results.

If the user asks for losers:
- Show the top 10 losers.
- Include name, symbol, price and 24-hour percentage change.

If the user asks about Bitcoin:
- Analyse its current price, market cap, volume,
  24-hour movement and 7-day movement.

If the user asks about the overall market:
- Analyse global market capitalization, volume,
  Bitcoin dominance and top cryptocurrencies.
- Clearly state when global data is unavailable.

If an endpoint failed, mention that its data could not be retrieved.

Keep the answer structured, readable and concise.
"""

    response = llm.invoke(prompt)

    return {
        "analysis": response.content
    }

workflow = StateGraph(CryptoState)

workflow.add_node("fetch_market_data", fetch_market_data)
workflow.add_node("analyse_crypto", analyse_crypto)

workflow.add_edge(START, "fetch_market_data")
workflow.add_edge("fetch_market_data", "analyse_crypto")
workflow.add_edge("analyse_crypto", END)

graph = workflow.compile()


if __name__ == "__main__":

    question = input(
        "\nWhat would you like to know about the crypto market? "
    )

    result = graph.invoke({
        "question": question,
        "market_data": {},
        "analysis": ""
    })

    print("\n" + "=" * 60)
    print("CRYPTO MARKET DATA")
    print("=" * 60)

    print(
        json.dumps(
            result["market_data"],
            indent=2
        )
    )

    print("\n" + "=" * 60)
    print("AI MARKET ANALYSIS")
    print("=" * 60)

    print(result["analysis"])