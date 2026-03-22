from pyfin_sentiment.model import SentimentModel

# Télécharger le modèle (une seule fois)
SentimentModel.download("small")

# Charger le modèle
model = SentimentModel("small")

# Analyser un tweet
tweet = "Je suis très optimiste sur $AAPL, ça va monter !"
resultat = model.predict([tweet])

# Résultat : '1' = Bullish (positif), '2' = Neutre, '3' = Bearish (négatif)
sentiment_map = {'1': '🐂 HAUSSIER', '2': '⚖️ NEUTRE', '3': '🐻 BAISSIER'}
print(f"Tweet: {tweet}")
print(f"Sentiment: {sentiment_map.get(resultat[0], 'Inconnu')}")