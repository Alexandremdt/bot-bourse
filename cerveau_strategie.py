"""
CERVEAU STRATÉGIQUE - Étape 4
Ce module analyse les données de prix et les tweets pour prendre des décisions d'achat/vente.
Version complète et fonctionnelle.
"""

import yfinance as yf
import feedparser
import re
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional

# ============================================================================
# PARTIE 1 : CONFIGURATION DE LA STRATÉGIE
# ============================================================================

class ConfigurationStrategie:
    """Stocke tous les paramètres de la stratégie"""
    
    def __init__(self):
        # === PARAMÈTRES DE PRIX ===
        self.prix_achat_max = 150.0      # Acheter si prix < 150€
        self.prix_vente_min = 180.0      # Vendre si prix > 180€ (prise de profit simple)
        
        # === PARAMÈTRES DE GESTION DES RISQUES ===
        self.stop_loss_pct = -3.0        # Vendre si baisse > 3%
        self.take_profit_pct = 10.0      # Vendre si hausse > 10% (par rapport à l'achat)
        
        # === MOTS-CLÉS POUR L'ANALYSE DES TWEETS ===
        self.mots_haussiers = [
            "hausse", "monte", "croissance", "positif", "optimiste", 
            "achat", "démarre", "rallye", "boom", "record", "excellent",
            "performance", "bénéfice", "augmentation", "progression"
        ]
        
        self.mots_baissiers = [
            "baisse", "descend", "chute", "négatif", "vente", "alerte", 
            "risque", "crainte", "chute", "effondrement", "perte", 
            "déception", "avertissement", "diminution"
        ]
        
        # === POIDS DES DIFFÉRENTS SIGNAUX ===
        self.poids_signal_prix = 0.6      # 60% d'importance au prix
        self.poids_signal_tweet = 0.4     # 40% d'importance aux tweets
        
        # === SEUILS DE DÉCISION ===
        self.seuil_achat = 0.2            # Force du signal > 0.2 = achat
        self.seuil_vente = 0.5            # Force du signal > 0.5 = vente
        
        # === INSTANCES NITTER (pour récupérer les tweets) ===
        self.instances_nitter = [
            "https://nitter.net",
            "https://nitter.privacydev.net",
            "https://nitter.poast.org",
            "https://nitter.lacontrevoie.fr",
            "https://nitter.woodland.cafe"
        ]


# ============================================================================
# PARTIE 2 : RÉCUPÉRATION DES PRIX
# ============================================================================

def obtenir_prix_temps_reel(symbole: str) -> Optional[float]:
    """
    Récupère le prix actuel d'une action.
    
    Args:
        symbole: Code de l'action (ex: "AI.PA" pour Air Liquide)
        
    Returns:
        Prix actuel en euros, ou None si erreur
    """
    try:
        # Récupérer les données de la journée
        action = yf.Ticker(symbole)
        donnees = action.history(period="1d")
        
        if not donnees.empty:
            # Prendre le dernier prix de clôture
            prix = donnees['Close'].iloc[-1]
            return round(prix, 2)
        else:
            return None
            
    except Exception as e:
        print(f"  ⚠️ Erreur récupération prix {symbole}: {e}")
        return None


def obtenir_prix_historique(symbole: str, jours: int = 1) -> Tuple[Optional[float], Optional[float]]:
    """
    Récupère le prix d'il y a 'jours' jours et le prix actuel.
    
    Args:
        symbole: Code de l'action
        jours: Nombre de jours dans le passé
        
    Returns:
        (prix_ancien, prix_actuel) ou (None, None) si erreur
    """
    try:
        action = yf.Ticker(symbole)
        date_debut = datetime.now() - timedelta(days=jours + 1)
        donnees = action.history(start=date_debut, end=datetime.now())
        
        if not donnees.empty and len(donnees) >= 2:
            prix_ancien = donnees['Close'].iloc[0]
            prix_actuel = donnees['Close'].iloc[-1]
            return round(prix_ancien, 2), round(prix_actuel, 2)
        else:
            return None, None
            
    except Exception as e:
        print(f"  ⚠️ Erreur historique {symbole}: {e}")
        return None, None


def calculer_variation(symbole: str, jours: int = 1) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """
    Calcule la variation en pourcentage sur 'jours' jours.
    
    Args:
        symbole: Code de l'action
        jours: Nombre de jours
        
    Returns:
        (variation_pct, prix_ancien, prix_actuel) ou (None, None, None) si erreur
    """
    prix_ancien, prix_actuel = obtenir_prix_historique(symbole, jours)
    
    if prix_ancien and prix_actuel and prix_ancien > 0:
        variation = (prix_actuel - prix_ancien) / prix_ancien * 100
        return round(variation, 2), prix_ancien, prix_actuel
    else:
        return None, None, None


# ============================================================================
# PARTIE 3 : RÉCUPÉRATION ET ANALYSE DES TWEETS
# ============================================================================

# Instance globale de la configuration (chargée une fois)
_config = ConfigurationStrategie()


def nettoyer_texte(texte_brut: str) -> str:
    """Nettoie un tweet : supprime les liens, retours à la ligne, etc."""
    
    # Supprimer les liens t.co (liens raccourcis Twitter)
    texte = re.sub(r'https?://t\.co/\w+', '', texte_brut)
    
    # Supprimer les autres URLs
    texte = re.sub(r'http\S+', '', texte)
    
    # Supprimer les mentions @
    texte = re.sub(r'@\w+', '', texte)
    
    # Remplacer les retours à la ligne par des espaces
    texte = texte.replace('\n', ' ').replace('\r', ' ')
    
    # Supprimer les espaces multiples
    texte = re.sub(r'\s+', ' ', texte)
    
    return texte.strip()


def recuperer_tweets(compte: str, nb_max: int = 10) -> List[Dict]:
    """
    Récupère les derniers tweets d'un compte Twitter via Nitter.
    
    Args:
        compte: Nom du compte Twitter (ex: "BourseDirect")
        nb_max: Nombre maximum de tweets à récupérer
        
    Returns:
        Liste de dictionnaires contenant 'texte', 'date', 'lien'
    """
    tweets = []
    
    for instance in _config.instances_nitter:
        url_rss = f"{instance}/{compte}/rss"
        
        try:
            flux = feedparser.parse(url_rss)
            
            if flux.entries and len(flux.entries) > 0:
                for entry in flux.entries[:nb_max]:
                    tweet = {
                        'texte': nettoyer_texte(entry.title),
                        'date': entry.published if hasattr(entry, 'published') else "Date inconnue",
                        'lien': entry.link,
                        'compte': compte
                    }
                    tweets.append(tweet)
                
                # On arrête dès qu'on a trouvé une instance qui marche
                return tweets
                
        except Exception:
            # On essaie l'instance suivante
            continue
    
    return tweets


def analyser_sentiment_tweets(tweets: List[Dict], symbole: str) -> float:
    """
    Analyse les tweets pour un symbole donné.
    
    Args:
        tweets: Liste des tweets récupérés
        symbole: Code de l'action à analyser
        
    Returns:
        Score entre -1 (très négatif) et +1 (très positif)
    """
    if not tweets:
        return 0.0
    
    score_total = 0.0
    tweets_pertinents = 0
    
    for tweet in tweets:
        texte = tweet['texte'].lower()
        
        # Vérifier si le tweet parle de notre action
        if symbole.lower() in texte:
            tweets_pertinents += 1
            
            # Compter les mots haussiers et baissiers
            score_tweet = 0
            
            for mot in _config.mots_haussiers:
                if mot in texte:
                    score_tweet += 1
            
            for mot in _config.mots_baissiers:
                if mot in texte:
                    score_tweet -= 1
            
            # Normaliser entre -1 et +1 (on limite à +/-3 mots)
            score_tweet = max(-1.0, min(1.0, score_tweet / 3.0))
            score_total += score_tweet
    
    if tweets_pertinents == 0:
        return 0.0
    
    # Score moyen
    score_moyen = score_total / tweets_pertinents
    
    return round(score_moyen, 2)


# ============================================================================
# PARTIE 4 : GÉNÉRATION DES SIGNAUX D'ACHAT/VENTE
# ============================================================================

def generer_signal_achat(symbole: str, prix_actuel: float, score_sentiment: float) -> Tuple[bool, float, List[str]]:
    """
    Analyse si c'est le moment d'acheter.
    
    Returns:
        (decision, force_signal, list_des_raisons)
    """
    force_signal = 0.0
    raisons = []
    decision = False
    
    # 1. Signal basé sur le prix (seuil d'achat)
    if prix_actuel < _config.prix_achat_max:
        contribution = _config.poids_signal_prix * 1.0
        force_signal += contribution
        raisons.append(f"  ✅ Prix bas : {prix_actuel:.2f}€ < {_config.prix_achat_max}€ (+{contribution:.2f})")
    else:
        contribution = _config.poids_signal_prix * -0.3
        force_signal += contribution
        raisons.append(f"  ⚠️ Prix élevé : {prix_actuel:.2f}€ > {_config.prix_achat_max}€ ({contribution:.2f})")
    
    # 2. Signal basé sur les tweets
    if score_sentiment > 0.3:
        contribution = _config.poids_signal_tweet * 1.0
        force_signal += contribution
        raisons.append(f"  ✅ Sentiment positif : score {score_sentiment:.2f} (+{contribution:.2f})")
    elif score_sentiment < -0.3:
        contribution = _config.poids_signal_tweet * -0.8
        force_signal += contribution
        raisons.append(f"  ❌ Sentiment négatif : score {score_sentiment:.2f} ({contribution:.2f})")
    else:
        contribution = 0.0
        force_signal += contribution
        raisons.append(f"  ⚖️ Sentiment neutre : score {score_sentiment:.2f}")
    
    # 3. Décision finale
    if force_signal > _config.seuil_achat:
        decision = True
        raisons.append(f"  🎯 FORCE TOTALE : {force_signal:.2f} > {_config.seuil_achat} → ACHETER")
    else:
        raisons.append(f"  ⏸️ FORCE TOTALE : {force_signal:.2f} < {_config.seuil_achat} → ATTENDRE")
    
    return decision, round(force_signal, 2), raisons


def generer_signal_vente(symbole: str, prix_actuel: float, prix_achat_reference: float, 
                         score_sentiment: float) -> Tuple[bool, float, List[str]]:
    """
    Analyse si c'est le moment de vendre.
    
    Returns:
        (decision, force_signal, list_des_raisons)
    """
    force_signal = 0.0
    raisons = []
    decision = False
    
    # 1. Calcul de la performance depuis l'achat
    if prix_achat_reference and prix_achat_reference > 0:
        performance = (prix_actuel - prix_achat_reference) / prix_achat_reference * 100
        performance = round(performance, 2)
        raisons.append(f"  📊 Performance depuis achat : {performance:.1f}%")
        
        # 2. Take profit (prise de profit)
        if performance >= _config.take_profit_pct:
            contribution = 0.8
            force_signal += contribution
            raisons.append(f"  💰 TAKE PROFIT : +{performance:.1f}% atteint ! (+{contribution:.2f})")
        
        # 3. Stop loss (couper les pertes)
        elif performance <= _config.stop_loss_pct:
            contribution = 0.9
            force_signal += contribution
            raisons.append(f"  ⚠️ STOP LOSS : {performance:.1f}% de baisse ! (+{contribution:.2f})")
        
        # 4. Prix trop haut (prise de profit simple)
        elif prix_actuel > _config.prix_vente_min:
            contribution = 0.5
            force_signal += contribution
            raisons.append(f"  💰 Prix élevé : {prix_actuel:.2f}€ > {_config.prix_vente_min}€ (+{contribution:.2f})")
    
    # 5. Signal basé sur le sentiment (si très négatif, vendre)
    if score_sentiment < -0.5:
        contribution = 0.4
        force_signal += contribution
        raisons.append(f"  📉 Sentiment très négatif : {score_sentiment:.2f} (+{contribution:.2f})")
    
    # 6. Décision finale
    if force_signal > _config.seuil_vente:
        decision = True
        raisons.append(f"  🎯 FORCE TOTALE : {force_signal:.2f} > {_config.seuil_vente} → VENDRE")
    else:
        raisons.append(f"  ⏸️ FORCE TOTALE : {force_signal:.2f} < {_config.seuil_vente} → GARDER")
    
    return decision, round(force_signal, 2), raisons


# ============================================================================
# PARTIE 5 : CERVEAU PRINCIPAL
# ============================================================================

class CerveauStrategie:
    """
    Le cerveau qui prend les décisions d'achat/vente.
    """
    
    def __init__(self):
        self.prix_achat_reference: Dict[str, float] = {}  # Stocke le prix d'achat pour chaque action
        self.historique_decisions: List[Dict] = []        # Historique des décisions prises
    
    def analyser_action(self, symbole: str, comptes_twitter: Optional[List[str]] = None) -> Dict:
        """
        Analyse complète d'une action.
        
        Args:
            symbole: Code de l'action (ex: "AI.PA")
            comptes_twitter: Liste des comptes Twitter à surveiller
            
        Returns:
            Dictionnaire contenant la décision et toutes les analyses
        """
        if comptes_twitter is None:
            comptes_twitter = ["BourseDirect", "Investir_FR", "CAC40"]
        
        print(f"\n{'='*60}")
        print(f"🔍 ANALYSE DE {symbole} - {datetime.now().strftime('%H:%M:%S')}")
        print(f"{'='*60}")
        
        # 1. Récupérer le prix actuel
        prix_actuel = obtenir_prix_temps_reel(symbole)
        if prix_actuel is None:
            return {
                'decision': 'ERREUR',
                'symbole': symbole,
                'message': f"Impossible de récupérer le prix pour {symbole}",
                'erreur': True
            }
        print(f"💰 Prix actuel : {prix_actuel:.2f}€")
        
        # 2. Récupérer et analyser les tweets
        print(f"📡 Récupération des tweets...")
        tous_les_tweets = []
        for compte in comptes_twitter:
            tweets = recuperer_tweets(compte, nb_max=8)
            if tweets:
                print(f"   ✓ {compte}: {len(tweets)} tweets")
                tous_les_tweets.extend(tweets)
            else:
                print(f"   ⚠️ {compte}: aucun tweet récupéré")
        
        score_sentiment = analyser_sentiment_tweets(tous_les_tweets, symbole)
        print(f"📊 Sentiment Twitter : {score_sentiment:.2f}")
        
        # 3. Décision d'achat
        decision_achat, force_achat, raisons_achat = generer_signal_achat(
            symbole, prix_actuel, score_sentiment
        )
        
        # 4. Décision de vente (si on a déjà acheté)
        decision_vente = False
        force_vente = 0.0
        raisons_vente = []
        
        if symbole in self.prix_achat_reference:
            print(f"📈 Prix d'achat de référence : {self.prix_achat_reference[symbole]:.2f}€")
            decision_vente, force_vente, raisons_vente = generer_signal_vente(
                symbole, prix_actuel, self.prix_achat_reference[symbole], score_sentiment
            )
        
        # 5. Décision finale
        if decision_vente:
            decision = "VENTE"
            force = force_vente
            raisons = raisons_vente
        elif decision_achat:
            decision = "ACHAT"
            force = force_achat
            raisons = raisons_achat
        else:
            decision = "ATTENDRE"
            force = max(force_achat, force_vente)
            raisons = raisons_achat + raisons_vente if raisons_vente else raisons_achat
        
        # 6. Afficher les raisons de manière structurée
        print(f"\n📋 RAISONS DE LA DÉCISION :")
        for raison in raisons:
            print(raison)
        
        resultat = {
            'decision': decision,
            'symbole': symbole,
            'prix_actuel': prix_actuel,
            'score_sentiment': score_sentiment,
            'force_signal': force,
            'raisons': raisons,
            'prix_achat_reference': self.prix_achat_reference.get(symbole),
            'timestamp': datetime.now().isoformat(),
            'erreur': False
        }
        
        # Enregistrer dans l'historique
        self.historique_decisions.append(resultat)
        
        return resultat
    
    def enregistrer_achat(self, symbole: str, prix_achat: Optional[float] = None) -> None:
        """
        Enregistre un achat pour référence future.
        
        Args:
            symbole: Code de l'action
            prix_achat: Prix d'achat (si None, utilise le prix actuel)
        """
        if prix_achat is None:
            prix_achat = obtenir_prix_temps_reel(symbole)
            if prix_achat is None:
                print(f"❌ Impossible d'enregistrer l'achat pour {symbole}: prix non disponible")
                return
        
        self.prix_achat_reference[symbole] = prix_achat
        print(f"\n📝 Achat enregistré : {symbole} à {prix_achat:.2f}€")
    
    def enregistrer_vente(self, symbole: str) -> None:
        """
        Supprime la référence d'achat après une vente.
        
        Args:
            symbole: Code de l'action
        """
        if symbole in self.prix_achat_reference:
            del self.prix_achat_reference[symbole]
            print(f"\n🗑️ Vente enregistrée : {symbole} retiré du suivi")
    
    def afficher_historique(self, nb_dernieres: int = 5) -> None:
        """Affiche l'historique des dernières décisions."""
        print(f"\n{'='*60}")
        print(f"📜 HISTORIQUE DES DERNIÈRES DÉCISIONS")
        print(f"{'='*60}")
        
        for dec in self.historique_decisions[-nb_dernieres:]:
            print(f"{dec['timestamp'][:19]} | {dec['symbole']} | {dec['decision']} | Prix: {dec['prix_actuel']:.2f}€ | Force: {dec['force_signal']:.2f}")
    
    def get_statistiques(self) -> Dict:
        """Retourne les statistiques des décisions."""
        if not self.historique_decisions:
            return {'total': 0}
        
        achats = sum(1 for d in self.historique_decisions if d['decision'] == 'ACHAT')
        ventes = sum(1 for d in self.historique_decisions if d['decision'] == 'VENTE')
        attendre = sum(1 for d in self.historique_decisions if d['decision'] == 'ATTENDRE')
        erreurs = sum(1 for d in self.historique_decisions if d.get('erreur', False))
        
        return {
            'total': len(self.historique_decisions),
            'achats': achats,
            'ventes': ventes,
            'attendre': attendre,
            'erreurs': erreurs
        }


# ============================================================================
# PARTIE 6 : TESTS ET DÉMONSTRATION
# ============================================================================

def test_analyse_simple():
    """Test simple avec une action et des comptes Twitter de base."""
    print("\n" + "="*60)
    print("🧪 TEST 1 : ANALYSE SIMPLE")
    print("="*60)
    
    cerveau = CerveauStrategie()
    
    # Tester avec Air Liquide
    resultat = cerveau.analyser_action("AI.PA", comptes_twitter=["BourseDirect"])
    
    print(f"\n{'='*60}")
    print("📋 RÉSULTAT FINAL")
    print(f"{'='*60}")
    print(f"🎯 DÉCISION : {resultat['decision']}")
    print(f"💰 Prix : {resultat['prix_actuel']:.2f}€")
    print(f"📊 Sentiment : {resultat['score_sentiment']:.2f}")
    print(f"⚡ Force du signal : {resultat['force_signal']:.2f}")
    
    return cerveau


def test_avec_achat_simule():
    """Test simulant un achat puis une analyse de vente ultérieure."""
    print("\n" + "="*60)
    print("🧪 TEST 2 : SIMULATION ACHAT → VENTE")
    print("="*60)
    
    cerveau = CerveauStrategie()
    
    # 1. Analyser d'abord (pour voir si on doit acheter)
    resultat_analyse = cerveau.analyser_action("AI.PA", comptes_twitter=["BourseDirect"])
    
    # 2. Si le signal est fort, on simule un achat
    if resultat_analyse['force_signal'] > 0.3:
        print(f"\n💡 Signal fort détecté ! Simulation d'achat à {resultat_analyse['prix_actuel']:.2f}€")
        cerveau.enregistrer_achat("AI.PA", resultat_analyse['prix_actuel'])
        
        # 3. Afficher l'état actuel
        print(f"\n📊 État actuel :")
        print(f"   Prix d'achat : {cerveau.prix_achat_reference['AI.PA']:.2f}€")
        print(f"   Prix actuel : {resultat_analyse['prix_actuel']:.2f}€")
        
        variation = (resultat_analyse['prix_actuel'] - cerveau.prix_achat_reference['AI.PA']) / cerveau.prix_achat_reference['AI.PA'] * 100
        print(f"   Performance : {variation:.1f}%")
        
        print(f"\n💡 Conseil : relancez ce test plus tard pour voir les signaux de vente")
    else:
        print(f"\n⏸️ Signal trop faible ({resultat_analyse['force_signal']:.2f}), pas d'achat simulé")


def test_plusieurs_actions():
    """Test avec plusieurs actions différentes."""
    print("\n" + "="*60)
    print("🧪 TEST 3 : ANALYSE MULTIPLE")
    print("="*60)
    
    actions_a_tester = ["AI.PA", "TTE.PA", "MC.PA"]  # Air Liquide, Total, LVMH
    
    cerveau = CerveauStrategie()
    
    for symbole in actions_a_tester:
        resultat = cerveau.analyser_action(symbole, comptes_twitter=["BourseDirect"])
        
        # Afficher un résumé compact
        icone = "🟢" if resultat['decision'] == 'ACHAT' else "🔴" if resultat['decision'] == 'VENTE' else "⚪"
        print(f"\n{icone} {symbole}: {resultat['decision']} (force: {resultat['force_signal']:.2f})")
    
    # Afficher les statistiques
    stats = cerveau.get_statistiques()
    print(f"\n📊 STATISTIQUES : {stats['total']} analyses, {stats['achats']} achats, {stats['ventes']} ventes")
    
    return cerveau


def test_analyse_tweets_seule():
    """Test spécifique pour l'analyse des tweets."""
    print("\n" + "="*60)
    print("🧪 TEST 4 : ANALYSE DES TWEETS UNIQUEMENT")
    print("="*60)
    
    # Tester la récupération de tweets
    comptes = ["BourseDirect", "Investir_FR"]
    symbole_test = "AIR LIQUIDE"
    
    for compte in comptes:
        print(f"\n📡 Récupération des tweets de @{compte}:")
        tweets = recuperer_tweets(compte, nb_max=5)
        
        if tweets:
            for tweet in tweets[:3]:
                print(f"   📝 {tweet['texte'][:80]}...")
        
        # Analyser le sentiment
        score = analyser_sentiment_tweets(tweets, symbole_test)
        print(f"   📊 Sentiment pour {symbole_test}: {score:.2f}")


def test_variation_prix():
    """Test le calcul des variations de prix."""
    print("\n" + "="*60)
    print("🧪 TEST 5 : CALCUL DES VARIATIONS DE PRIX")
    print("="*60)
    
    symbole = "AI.PA"
    
    # Variation sur 1 jour
    variation_1j, ancien, actuel = calculer_variation(symbole, jours=1)
    if variation_1j is not None:
        print(f"📈 {symbole} - Variation 1 jour : {variation_1j:+.2f}%")
        print(f"   Hier : {ancien:.2f}€ → Aujourd'hui : {actuel:.2f}€")
    
    # Variation sur 5 jours
    variation_5j, ancien_5j, actuel_5j = calculer_variation(symbole, jours=5)
    if variation_5j is not None:
        print(f"📈 Variation 5 jours : {variation_5j:+.2f}%")
        print(f"   Il y a 5 jours : {ancien_5j:.2f}€ → Aujourd'hui : {actuel_5j:.2f}€")


# ============================================================================
# PARTIE 7 : EXÉCUTION PRINCIPALE
# ============================================================================

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🧠 CERVEAU STRATÉGIQUE - VERSION COMPLÈTE")
    print("="*60)
    print("\nCe programme analyse les marchés et les tweets pour prendre")
    print("des décisions d'achat/vente automatisées.")
    print("\nChoisissez un test à exécuter :")
    print("  1 - Analyse simple (Air Liquide)")
    print("  2 - Simulation achat → vente")
    print("  3 - Analyse multiple (3 actions)")
    print("  4 - Analyse des tweets uniquement")
    print("  5 - Calcul des variations de prix")
    print("  6 - TOUS les tests")
    
    choix = input("\nVotre choix (1-6) : ").strip()
    
    if choix == "1":
        test_analyse_simple()
    elif choix == "2":
        test_avec_achat_simule()
    elif choix == "3":
        test_plusieurs_actions()
    elif choix == "4":
        test_analyse_tweets_seule()
    elif choix == "5":
        test_variation_prix()
    elif choix == "6":
        test_analyse_simple()
        test_avec_achat_simule()
        test_plusieurs_actions()
        test_analyse_tweets_seule()
        test_variation_prix()
    else:
        print("Choix invalide. Exécution du test par défaut...")
        test_analyse_simple()
    
    print("\n" + "="*60)
    print("✅ Fin de l'analyse")
    print("="*60)