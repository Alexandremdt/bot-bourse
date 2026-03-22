import feedparser
import re

# Configuration
INSTANCES_NITTER = [
    "https://nitter.net",
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
]

def nettoyer_texte(texte_brut):
    """Nettoie un tweet"""
    # Supprimer les liens
    texte = re.sub(r'https?://t\.co/\w+', '', texte_brut)
    texte = re.sub(r'http\S+', '', texte)
    # Nettoyer les retours à la ligne
    texte = texte.replace('\n', ' ').replace('\r', ' ')
    # Supprimer les espaces multiples
    texte = re.sub(r'\s+', ' ', texte)
    return texte.strip()

def recuperer_tweets(compte, nb_max=10):
    """
    Récupère les derniers tweets d'un compte Twitter.
    Retourne une liste de dictionnaires avec 'texte', 'date', 'lien'.
    """
    tweets = []
    
    for instance in INSTANCES_NITTER:
        url_rss = f"{instance}/{compte}/rss"
        print(f"🔍 Essai avec {url_rss}")
        
        try:
            flux = feedparser.parse(url_rss)
            
            if flux.entries and len(flux.entries) > 0:
                print(f"✅ Connexion réussie avec {instance}")
                
                for entry in flux.entries[:nb_max]:
                    tweet = {
                        'texte': nettoyer_texte(entry.title),
                        'date': entry.published if hasattr(entry, 'published') else "Date inconnue",
                        'lien': entry.link,
                        'compte': compte
                    }
                    tweets.append(tweet)
                
                return tweets  # On arrête dès qu'on a trouvé une instance qui marche
                
        except Exception as e:
            print(f"❌ Erreur avec {instance}: {e}")
            continue
    
    print("❌ Aucune instance Nitter fonctionnelle trouvée")
    return tweets

# --- TEST ---
if __name__ == "__main__":
    print("=== RÉCUPÉRATION DES TWEETS ===\n")
    
# Liste des comptes à surveiller
comptes_a_surveiller = [
    "BourseDirect",
    "Baradez", 
    "fuckthedip",  # Exemple d'autre compte
    # Ajoutez vos propres comptes ici
]

print("=== SURVEILLANCE DE PLUSIEURS COMPTES ===\n")

for compte in comptes_a_surveiller:
    print(f"\n--- Compte: @{compte} ---")
    tweets = recuperer_tweets(compte, nb_max=3)
    
    if tweets:
        for tweet in tweets:
            print(f"  • {tweet['texte'][:80]}...")
    else:
        print(f"  ❌ Impossible de récupérer les tweets de @{compte}")
