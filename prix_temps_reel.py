import yfinance as yf

def obtenir_prix_temps_reel(symbole):
    """
    Récupère le prix actuel d'une action.
    Exemple : obtenir_prix_temps_reel("AI.PA") -> 168.45
    """
    try:
        # Récupérer les données de la journée
        action = yf.Ticker(symbole)
        donnees = action.history(period="1d")
        
        # Vérifier si on a des données
        if not donnees.empty:
            # Prendre le dernier prix de clôture
            prix = donnees['Close'].iloc[-1]
            return prix
        else:
            return None
    except Exception as erreur:
        # En cas d'erreur, afficher le problème et retourner None
        print(f"Erreur pour {symbole} : {erreur}")
        return None

# --- Test rapide (cette partie ne s'exécute que si on lance ce fichier directement) ---
if __name__ == "__main__":
    # Test avec Air Liquide
    prix_air_liquide = obtenir_prix_temps_reel("AI.PA")
    if prix_air_liquide:
        print(f"Air Liquide : {prix_air_liquide} €")
    else:
        print("Erreur de récupération pour Air Liquide")
    
    # Test avec TotalEnergies
    prix_total = obtenir_prix_temps_reel("TTE.PA")
    if prix_total:
        print(f"TotalEnergies : {prix_total} €")