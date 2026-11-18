# Crypto Analysis Agent

A local cryptocurrency market dashboard and question-answering agent. It retrieves current market data from the CoinGecko Demo API, calculates factual observations in Python, coordinates analysis with LangGraph, and uses Ollama with `smollm2:360m` to explain the verified results. The dashboard is built with Streamlit and Plotly.

## Features

- Global cryptocurrency market overview and Bitcoin analysis.
- Top cryptocurrencies, 24-hour gainers and losers, and trending coins.
- Historical price explorer with selectable coins and periods.
- Chat questions about supported market data, with conversation history.
- Cached market and historical data, plus a manual refresh control.
- Optional endpoint failures are reported while available dashboard data remains usable.
- Deterministic Python analysis is the source of market facts. If Ollama is unavailable or changes the verified analysis, the workflow returns the Python analysis.

## Architecture

| Component | Responsibility |
|---|---|
| CoinGecko Demo API | Supplies current market, global, trending, and historical data. |
| Python (`main.py`) | Validates data and calculates market observations and rankings. |
| LangGraph (`main.py`) | Coordinates fetching, intent recognition, deterministic analysis, and chat explanation. |
| Ollama / LangChain Ollama | Runs the local `smollm2:360m` model for a concise explanation of verified analysis. |
| Streamlit (`app.py`) | Presents the dashboard and chat interface. |
| Pandas and Plotly | Prepare tables and render interactive charts. |
| python-dotenv | Loads the CoinGecko API key from `.env`. |

There are two LangGraph workflows:

1. `graph` fetches fresh market data, identifies the request, and performs deterministic analysis. It is used by the command-line entry point.
2. `analysis_graph` analyzes market data already loaded by Streamlit, then asks Ollama to explain the result. It avoids a new CoinGecko fetch for each chat question. Unsupported questions and unavailable data receive a direct response. Ollama failures use the Python analysis as a fallback.

## Project structure

```text
CryptoAnalysisAgent/
├── .env                     # Local CoinGecko key; do not commit
├── .gitignore
├── .streamlit/
│   └── config.toml           # Dark theme and orange accent
├── app.py                    # Streamlit dashboard
├── main.py                   # CoinGecko client, Python analysis, LangGraph, Ollama
├── README.md
└── venv/                     # Local virtual environment (created during setup)
```

## Requirements

- Windows 10 or later with PowerShell.
- Python 3.10 or later.
- An active CoinGecko Demo API key.
- Ollama installed and running locally, with `smollm2:360m` available.

## Installation (Windows PowerShell)

Open PowerShell in the project directory:

```powershell
Set-Location 'C:\Users\zain.zia\CryptoAnalysisAgent'
```

Create and activate a virtual environment, then install the packages used by the application:

```powershell
py -3 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install streamlit pandas plotly python-dotenv langgraph langchain-core langchain-ollama
```

If PowerShell blocks environment activation, run this for the current PowerShell process and activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
```

Install Ollama for Windows, then open a new PowerShell window and download the configured model:

```powershell
ollama pull smollm2:360m
ollama list
```

Ollama must be running locally when you use the chat workflow. The application uses the model name `smollm2:360m`, temperature `0.1`, a 140-token output limit, and a 60-second request timeout.

## Configure the CoinGecko Demo API key

Create a `.env` file in the project root (next to `main.py`) containing your own key:

```dotenv
COINGECKO_API_KEY=your_demo_api_key_here
```

Replace the example value with your key. Keep `.env` private; it is excluded by `.gitignore`. The key is sent to CoinGecko by the Python client and is not displayed in the dashboard.

## Run the application

Start the Streamlit dashboard from the project root with the virtual environment active:

```powershell
python -m streamlit run app.py
```

Streamlit prints a local URL in the terminal. Open it in a browser. Use **Refresh data** in the sidebar to clear the dashboard's market and historical data caches.

To run the command-line analysis instead:

```powershell
python main.py
```

Enter a question about Bitcoin, the global market, the top coins, gainers, losers, or trending coins when prompted.

## Dashboard pages

- **Market overview** — global market metrics and leading cryptocurrencies.
- **Bitcoin analysis** — Bitcoin market information and calculated changes.
- **Price explorer** — historical prices and period change for a selected cryptocurrency.
- **Gainers & losers** — strongest positive and negative 24-hour movements in the retrieved market list.
- **Trending coins** — trending data provided by CoinGecko.
- **Ask crypto agent** — chat over the market data currently loaded by the dashboard. Conversation history can be cleared from the page.

## Configuration and caching

- Market data is cached for 60 seconds; historical data is cached for 5 minutes. The **Refresh data** button clears both caches.
- The Streamlit theme is configured in `.streamlit/config.toml`.
- The CoinGecko API key is read from `.env`; do not put secrets in source code or screenshots.
- The dashboard can show available data when an optional CoinGecko endpoint fails. A failure of the required market endpoint is reported on the page.

## Troubleshooting

| Problem | What to check |
|---|---|
| `COINGECKO_API_KEY is missing` | Confirm `.env` is in the project root and the variable is spelled exactly `COINGECKO_API_KEY`. Restart Streamlit after changing it. |
| CoinGecko rejects the key | Confirm it is a valid Demo API key and has no surrounding quotes or extra spaces. |
| CoinGecko rate limit | Wait briefly before refreshing; repeated manual refreshes can use API quota. |
| Ollama connection or model error | Start Ollama, run `ollama list`, and confirm `smollm2:360m` is installed. Chat falls back to deterministic Python analysis if the model call fails. |
| PowerShell cannot activate `venv` | Use the process-scoped execution policy command in the installation section, then activate again. |
| Package import error | Activate the project's `venv` and install the packages with the provided `python -m pip install` command. |
| Historical chart is empty | The selected coin or period may not have historical observations available; try another period or coin. |

## Data and analysis notes

Market values and rankings come from CoinGecko responses and Python calculations. Trending status reflects CoinGecko search activity. Historical change is calculated from available returned price observations. A chart or statistic is shown as unavailable when the source data is missing or invalid. This application is informational and does not provide investment advice.
