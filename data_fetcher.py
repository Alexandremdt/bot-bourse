import yfinance as yf

def get_realtime_price(symbol):
    ticker = yf.Ticker(symbol)
    # Récupère les données en temps réel
    data = ticker.history(period="1d", interval="1m")
    if not data.empty:
        return data['Close'].iloc[-1]
    else:
        return None

# Test pour Air Liquide (exemple)
prix = get_realtime_price("AI.PA")
print(f"Prix actuel d'Air Liquide : {prix}")