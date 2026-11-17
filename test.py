import socket
import urllib.request

try:
    print("DNS lookup:")
    print(socket.gethostbyname("api.coingecko.com"))

    print("\nTesting HTTPS:")

    url = "https://api.coingecko.com/api/v3/ping"

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "CryptoAnalysisAgent/1.0"}
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        print("Status:", response.status)
        print("Response:", response.read().decode())

except Exception as error:
    print("Error:", repr(error))