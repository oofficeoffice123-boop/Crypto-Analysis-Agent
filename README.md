# Crypto Analysis Agent

An AI-powered cryptocurrency analysis agent built with **Python, LangGraph, and Qwen 2.5 3B**. It fetches live market data from CoinGecko and uses a locally running LLM to analyse market trends.

### Features
- Bitcoin market analysis
- Top 10 cryptocurrencies by market cap
- Top 10 gainers and losers
- 7 day price movement analysis
- Global market overview
- Trending cryptocurrencies
- AI powered market insights

### Tech Stack
- Python
- LangGraph & LangChain
- Ollama (Qwen 2.5 3B)
- CoinGecko API

### Setup

```bash
pip install langchain langgraph langchain-ollama langchain-core python-dotenv
ollama pull qwen2.5:3b
```

Create a `.env` file:

```env
COINGECKO_API_KEY=your_api_key
```

### Example Queries
`gainers` · `losers` · `top 10 coins` · `Bitcoin analysis` · `market overview`

### Disclaimer
For fun purposes only. Not financial advice.
