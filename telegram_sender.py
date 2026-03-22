"""
BOT DE TRADING PRINCIPAL - Étape 6
Assemble le cerveau stratégique, le formateur d'ordre et l'envoi Telegram.
Version complète et fonctionnelle.
"""

import os
import sys
import time
import json
import logging
import signal
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot_trading.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================================================
# PARTIE 1 : IMPORT DES MODULES EXTERNES
# ============================================================================

# Vérifier et importer les modules nécessaires
try:
    import requests
    logger.info("✅ requests chargé")
except ImportError:
    logger.error("❌ requests non installé. Exécutez: pip install requests")
    sys.exit(1)

try:
    from telegram import Bot
    from telegram.error import TelegramError
    logger.info("✅ python-telegram-bot chargé")
except ImportError:
    logger.error("❌ python-telegram-bot non installé. Exécutez: pip install python-telegram-bot")
    sys.exit(1)

try:
    import yfinance as yf
    logger.info("✅ yfinance chargé")
except ImportError:
    logger.error("❌ yfinance non installé. Exécutez: pip install yfinance")
    sys.exit(1)

try:
    import feedparser
    logger.info("✅ feedparser chargé")
except ImportError:
    logger.error("❌ feedparser non installé. Exécutez: pip install feedparser")
    sys.exit(1)


# ============================================================================
# PARTIE 2 : CONFIGURATION (à personnaliser)
# ============================================================================

@dataclass
class ConfigTelegram:
    """Configuration Telegram"""
    token: str = "8610437171:AAE58osb70J-VnObUxps3kM-XAQqU5ZLGvQ"  # À remplacer
    chat_id: str = "8416526688"        # À remplacer


@dataclass
class ConfigActions:
    """Configuration des actions à surveiller"""
    symboles: List[str] = None
    
    def __post_init__(self):
        if self.symboles is None:
            self.symboles = [
                "AI.PA",   # Air Liquide
                "TTE.PA",  # TotalEnergies
                "MC.PA",   # LVMH
                "BNP.PA",  # BNP Paribas
                "OR.PA",   # L'Oréal
                "SAN.PA",  # Sanofi
                "SU.PA",   # Schneider Electric
                "CAP.PA",  # Capgemini
            ]


@dataclass
class ConfigTwitter:
    """Configuration des comptes Twitter à surveiller"""
    comptes: List[str] = None
    
    def __post_init__(self):
        if self.comptes is None:
            self.comptes = [
                "BourseDirect",
                "Investir_FR",
                "CAC40",
                "BloombergFR",
                "LesEchos",
            ]


@dataclass
class ConfigStrategie:
    """Configuration de la stratégie de trading"""
    # Seuils de prix
    prix_achat_max: float = 150.0
    prix_vente_min: float = 180.0
    
    # Gestion des risques
    stop_loss_pct: float = -3.0
    take_profit_pct: float = 10.0
    
    # Poids des signaux
    poids_signal_prix: float = 0.6
    poids_signal_tweet: float = 0.4
    
    # Seuils de décision
    seuil_achat: float = 0.2
    seuil_vente: float = 0.5
    
    # Paramètres d'ordre par défaut
    quantite_par_defaut: int = 10
    type_ordre_achat: str = "cours_limite"
    type_ordre_vente: str = "seuil_declenchement"
    compte_par_defaut: str = "comptant"
    validite_par_defaut: str = "date"
    duree_validite_jours: int = 30


@dataclass
class ConfigBot:
    """Configuration principale du bot"""
    telegram: ConfigTelegram = None
    actions: ConfigActions = None
    twitter: ConfigTwitter = None
    strategie: ConfigStrategie = None
    intervalle_analyse_minutes: int = 30
    nb_max_tweets: int = 10
    instances_nitter: List[str] = None
    
    def __post_init__(self):
        if self.telegram is None:
            self.telegram = ConfigTelegram()
        if self.actions is None:
            self.actions = ConfigActions()
        if self.twitter is None:
            self.twitter = ConfigTwitter()
        if self.strategie is None:
            self.strategie = ConfigStrategie()
        if self.instances_nitter is None:
            self.instances_nitter = [
                "https://nitter.net",
                "https://nitter.privacydev.net",
                "https://nitter.poast.org",
                "https://nitter.lacontrevoie.fr",
            ]


# ============================================================================
# PARTIE 3 : MODULE DE RÉCUPÉRATION DES PRIX
# ============================================================================

class PrixFetcher:
    """Récupération des prix boursiers"""
    
    def __init__(self, config: ConfigStrategie):
        self.config = config
    
    def obtenir_prix_actuel(self, symbole: str) -> Optional[float]:
        """
        Récupère le prix actuel d'une action.
        """
        try:
            action = yf.Ticker(symbole)
            donnees = action.history(period="1d")
            
            if not donnees.empty:
                prix = donnees['Close'].iloc[-1]
                return round(prix, 2)
            return None
            
        except Exception as e:
            logger.error(f"Erreur récupération prix {symbole}: {e}")
            return None
    
    def obtenir_prix_historique(self, symbole: str, jours: int = 1) -> tuple:
        """
        Récupère le prix d'il y a 'jours' jours.
        Retourne (prix_ancien, prix_actuel)
        """
        try:
            action = yf.Ticker(symbole)
            date_debut = datetime.now() - timedelta(days=jours + 1)
            donnees = action.history(start=date_debut, end=datetime.now())
            
            if not donnees.empty and len(donnees) >= 2:
                prix_ancien = donnees['Close'].iloc[0]
                prix_actuel = donnees['Close'].iloc[-1]
                return round(prix_ancien, 2), round(prix_actuel, 2)
            return None, None
            
        except Exception as e:
            logger.error(f"Erreur historique {symbole}: {e}")
            return None, None
    
    def calculer_variation(self, symbole: str, jours: int = 1) -> dict:
        """
        Calcule la variation en pourcentage.
        """
        prix_ancien, prix_actuel = self.obtenir_prix_historique(symbole, jours)
        
        resultat = {
            'variation_pct': None,
            'prix_ancien': prix_ancien,
            'prix_actuel': prix_actuel
        }
        
        if prix_ancien and prix_actuel and prix_ancien > 0:
            resultat['variation_pct'] = round(
                (prix_actuel - prix_ancien) / prix_ancien * 100, 2
            )
        
        return resultat


# ============================================================================
# PARTIE 4 : MODULE DE RÉCUPÉRATION DES TWEETS
# ============================================================================

class TwitterFetcher:
    """Récupération et analyse des tweets"""
    
    def __init__(self, config: ConfigBot):
        self.config = config
        self.mots_haussiers = [
            "hausse", "monte", "croissance", "positif", "optimiste",
            "achat", "démarre", "rallye", "boom", "record", "excellent",
            "performance", "bénéfice", "augmentation", "progression"
        ]
        self.mots_baissiers = [
            "baisse", "descend", "chute", "négatif", "vente", "alerte",
            "risque", "crainte", "effondrement", "perte", "déception"
        ]
    
    def _nettoyer_texte(self, texte: str) -> str:
        """Nettoie un tweet"""
        import re
        texte = re.sub(r'https?://t\.co/\w+', '', texte)
        texte = re.sub(r'http\S+', '', texte)
        texte = re.sub(r'@\w+', '', texte)
        texte = texte.replace('\n', ' ').replace('\r', ' ')
        texte = re.sub(r'\s+', ' ', texte)
        return texte.strip()
    
    def recuperer_tweets(self, compte: str) -> List[Dict]:
        """
        Récupère les derniers tweets d'un compte.
        """
        tweets = []
        
        for instance in self.config.instances_nitter:
            url_rss = f"{instance}/{compte}/rss"
            
            try:
                flux = feedparser.parse(url_rss)
                
                if flux.entries and len(flux.entries) > 0:
                    for entry in flux.entries[:self.config.nb_max_tweets]:
                        tweets.append({
                            'texte': self._nettoyer_texte(entry.title),
                            'date': entry.published if hasattr(entry, 'published') else "Date inconnue",
                            'lien': entry.link,
                            'compte': compte
                        })
                    return tweets
                    
            except Exception:
                continue
        
        return tweets
    
    def analyser_sentiment(self, tweets: List[Dict], symbole: str) -> float:
        """
        Analyse le sentiment des tweets pour un symbole.
        Retourne un score entre -1 et +1.
        """
        if not tweets:
            return 0.0
        
        score_total = 0.0
        tweets_pertinents = 0
        
        for tweet in tweets:
            texte = tweet['texte'].lower()
            
            if symbole.lower() in texte:
                tweets_pertinents += 1
                score_tweet = 0
                
                for mot in self.mots_haussiers:
                    if mot in texte:
                        score_tweet += 1
                
                for mot in self.mots_baissiers:
                    if mot in texte:
                        score_tweet -= 1
                
                score_tweet = max(-1.0, min(1.0, score_tweet / 3.0))
                score_total += score_tweet
        
        if tweets_pertinents == 0:
            return 0.0
        
        return round(score_total / tweets_pertinents, 2)


# ============================================================================
# PARTIE 5 : MODULE DE DÉCISION STRATÉGIQUE
# ============================================================================

class StrategieDecision:
    """Logique de décision d'achat/vente"""
    
    def __init__(self, config: ConfigStrategie):
        self.config = config
        self.prix_achat_reference: Dict[str, float] = {}
    
    def analyser_achat(self, symbole: str, prix: float, sentiment: float) -> Dict:
        """
        Analyse si c'est le moment d'acheter.
        """
        force_signal = 0.0
        raisons = []
        
        # Signal prix
        if prix < self.config.prix_achat_max:
            contribution = self.config.poids_signal_prix * 1.0
            force_signal += contribution
            raisons.append(f"Prix bas: {prix:.2f}€ < {self.config.prix_achat_max}€ (+{contribution:.2f})")
        else:
            contribution = self.config.poids_signal_prix * -0.3
            force_signal += contribution
            raisons.append(f"Prix élevé: {prix:.2f}€ > {self.config.prix_achat_max}€ ({contribution:.2f})")
        
        # Signal sentiment
        if sentiment > 0.3:
            contribution = self.config.poids_signal_tweet * 1.0
            force_signal += contribution
            raisons.append(f"Sentiment positif: {sentiment:.2f} (+{contribution:.2f})")
        elif sentiment < -0.3:
            contribution = self.config.poids_signal_tweet * -0.8
            force_signal += contribution
            raisons.append(f"Sentiment négatif: {sentiment:.2f} ({contribution:.2f})")
        else:
            raisons.append(f"Sentiment neutre: {sentiment:.2f}")
        
        decision = force_signal > self.config.seuil_achat
        
        return {
            'decision': decision,
            'force_signal': round(force_signal, 2),
            'raisons': raisons
        }
    
    def analyser_vente(self, symbole: str, prix: float, sentiment: float) -> Dict:
        """
        Analyse si c'est le moment de vendre.
        """
        force_signal = 0.0
        raisons = []
        
        # Si on a un prix d'achat de référence
        if symbole in self.prix_achat_reference:
            prix_achat = self.prix_achat_reference[symbole]
            performance = (prix - prix_achat) / prix_achat * 100
            
            raisons.append(f"Performance: {performance:.1f}%")
            
            # Take profit
            if performance >= self.config.take_profit_pct:
                force_signal += 0.8
                raisons.append(f"Take profit: +{performance:.1f}% atteint!")
            
            # Stop loss
            elif performance <= self.config.stop_loss_pct:
                force_signal += 0.9
                raisons.append(f"Stop loss: {performance:.1f}% de baisse!")
        
        # Signal sentiment très négatif
        if sentiment < -0.5:
            force_signal += 0.4
            raisons.append(f"Sentiment très négatif: {sentiment:.2f}")
        
        decision = force_signal > self.config.seuil_vente
        
        return {
            'decision': decision,
            'force_signal': round(force_signal, 2),
            'raisons': raisons,
            'performance': performance if symbole in self.prix_achat_reference else None
        }
    
    def enregistrer_achat(self, symbole: str, prix: float):
        """Enregistre un achat pour référence future"""
        self.prix_achat_reference[symbole] = prix
    
    def enregistrer_vente(self, symbole: str):
        """Supprime la référence d'achat"""
        if symbole in self.prix_achat_reference:
            del self.prix_achat_reference[symbole]


# ============================================================================
# PARTIE 6 : MODULE DE FORMATAGE D'ORDRE
# ============================================================================

class FormateurOrdre:
    """Formate un ordre pour Bourse Direct"""
    
    def __init__(self, config: ConfigStrategie):
        self.config = config
    
    def formater_ordre_achat(self, symbole: str, prix_actuel: float, 
                              quantite: int = None, prix_limite: float = None) -> Dict:
        """
        Formate un ordre d'achat.
        """
        if quantite is None:
            quantite = self.config.quantite_par_defaut
        
        if prix_limite is None:
            prix_limite = round(prix_actuel * 0.98, 2)  # 2% en dessous
        
        return {
            'statut': 'OK',
            'date_generation': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'ordre': {
                'symbole': symbole,
                'decision': 'ACHAT',
                'compte': self.config.compte_par_defaut,
                'type_ordre': self.config.type_ordre_achat,
                'quantite': quantite,
                'montant_total': round(quantite * prix_limite, 2),
                'prix_actuel': prix_actuel,
                'prix_limite': prix_limite,
                'validite': self.config.validite_par_defaut,
                'strategie': 'take_profit',
                'seuil_strategie': round(prix_actuel * (1 + self.config.take_profit_pct / 100), 2),
                'stop_loss': round(prix_actuel * (1 + self.config.stop_loss_pct / 100), 2)
            }
        }
    
    def formater_ordre_vente(self, symbole: str, prix_actuel: float,
                              quantite: int = None, seuil: float = None) -> Dict:
        """
        Formate un ordre de vente.
        """
        if quantite is None:
            quantite = self.config.quantite_par_defaut
        
        if seuil is None:
            seuil = round(prix_actuel * (1 + self.config.stop_loss_pct / 100), 2)
        
        return {
            'statut': 'OK',
            'date_generation': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'ordre': {
                'symbole': symbole,
                'decision': 'VENTE',
                'compte': self.config.compte_par_defaut,
                'type_ordre': self.config.type_ordre_vente,
                'quantite': quantite,
                'montant_total': round(quantite * seuil, 2),
                'prix_actuel': prix_actuel,
                'seuil_declenchement': seuil,
                'validite': self.config.validite_par_defaut,
                'strategie': 'stop_loss',
                'seuil_strategie': seuil
            }
        }


# ============================================================================
# PARTIE 7 : MODULE D'ENVOI TELEGRAM
# ============================================================================

class TelegramSender:
    """Envoi de messages sur Telegram"""
    
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self.bot = None
        self._initialiser()
    
    def _initialiser(self):
        try:
            self.bot = Bot(token=self.token)
            # Tester la connexion
            self.bot.get_me()
            logger.info("✅ Bot Telegram initialisé")
        except Exception as e:
            logger.error(f"❌ Erreur initialisation Telegram: {e}")
            self.bot = None
    
    def envoyer_message(self, message: str, parse_mode: str = 'Markdown') -> bool:
        """Envoie un message sur Telegram"""
        if not self.bot:
            logger.error("Bot Telegram non initialisé")
            return False
        
        try:
            # Tronquer si trop long
            if len(message) > 4096:
                message = message[:4093] + "..."
            
            self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode=parse_mode
            )
            return True
        except TelegramError as e:
            logger.error(f"Erreur envoi Telegram: {e}")
            return False
    
    def envoyer_alerte_achat(self, ordre: Dict) -> bool:
        """Envoie une alerte d'achat"""
        data = ordre['ordre']
        
        message = f"""
🟢 *ALERTE ACHAT BOURSE DIRECT* 🟢

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
*ACHAT* - {data['symbole']}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 *Détails de l'ordre*

┌ *Compte* : {data['compte']}
├ *Type d'ordre* : {data['type_ordre']}
├ *Quantité* : {data['quantite']} actions
└ *Montant total* : {data['montant_total']:,.2f} €

💰 *Prix actuel* : {data['prix_actuel']:,.2f} €
🎯 *Prix limite* : {data['prix_limite']:,.2f} €

🎯 *Stratégie* : Take profit
   ├ *Objectif* : {data['seuil_strategie']:,.2f} €
   └ *Stop-loss* : {data['stop_loss']:,.2f} €

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📱 *Instructions pour Bourse Direct*

1️⃣ Ouvrir l'application Bourse Direct
2️⃣ Sélectionner "{data['symbole']}"
3️⃣ Ordre d'achat
4️⃣ Saisir les paramètres ci-dessus
5️⃣ Vérifier et confirmer

*Date* : {ordre['date_generation']}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        return self.envoyer_message(message)
    
    def envoyer_alerte_vente(self, ordre: Dict) -> bool:
        """Envoie une alerte de vente"""
        data = ordre['ordre']
        
        message = f"""
🔴 *ALERTE VENTE BOURSE DIRECT* 🔴

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
*VENTE* - {data['symbole']}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 *Détails de l'ordre*

┌ *Compte* : {data['compte']}
├ *Type d'ordre* : {data['type_ordre']}
├ *Quantité* : {data['quantite']} actions
└ *Montant total* : {data['montant_total']:,.2f} €

💰 *Prix actuel* : {data['prix_actuel']:,.2f} €
⚡ *Seuil déclenchement* : {data['seuil_declenchement']:,.2f} €

🛑 *Stratégie* : Stop loss
   └ *Seuil* : {data['seuil_strategie']:,.2f} €

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📱 *Instructions pour Bourse Direct*

1️⃣ Ouvrir l'application Bourse Direct
2️⃣ Sélectionner "{data['symbole']}"
3️⃣ Ordre de vente
4️⃣ Saisir les paramètres ci-dessus
5️⃣ Vérifier et confirmer

*Date* : {ordre['date_generation']}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        return self.envoyer_message(message)
    
    def envoyer_message_demarrage(self, actions: List[str]) -> bool:
        """Envoie un message de démarrage"""
        message = f"""
🤖 *BOT DE TRADING DÉMARRÉ* 🤖

*Date et heure* : {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}

📊 *Actions surveillées* :
"""
        for action in actions:
            message += f"   • {action}\n"
        
        message += f"""
⏱️  *Intervalle d'analyse* : 30 minutes

Le bot est maintenant actif. Vous recevrez des alertes lorsque des opportunités seront détectées.

*Statut* : 🟢 ACTIF
"""
        return self.envoyer_message(message)
    
    def envoyer_message_arret(self, stats: Dict) -> bool:
        """Envoie un message d'arrêt"""
        message = f"""
🛑 *BOT DE TRADING ARRÊTÉ* 🛑

*Date et heure* : {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}

📊 *Statistiques de la session* :
   • Analyses effectuées : {stats.get('analyses', 0)}
   • Alertes envoyées : {stats.get('alertes', 0)}
   • Achats suggérés : {stats.get('achats', 0)}
   • Ventes suggérées : {stats.get('ventes', 0)}

À bientôt ! 👋
"""
        return self.envoyer_message(message)


# ============================================================================
# PARTIE 8 : BOT PRINCIPAL
# ============================================================================

class BotTrading:
    """
    Bot de trading complet qui analyse, décide et alerte.
    """
    
    def __init__(self, config: ConfigBot):
        self.config = config
        self.actif = False
        self.stats = {
            'analyses': 0,
            'alertes': 0,
            'achats': 0,
            'ventes': 0,
            'demarrage': datetime.now()
        }
        self.historique_alertes = []
        
        # Initialiser les modules
        self.prix_fetcher = PrixFetcher(config.strategie)
        self.twitter_fetcher = TwitterFetcher(config)
        self.strategie = StrategieDecision(config.strategie)
        self.formateur = FormateurOrdre(config.strategie)
        self.sender = TelegramSender(
            config.telegram.token,
            config.telegram.chat_id
        )
        
        logger.info("✅ Bot de trading initialisé")
    
    def analyser_action(self, symbole: str) -> Optional[Dict]:
        """
        Analyse une action et retourne un ordre si opportunité.
        """
        try:
            logger.info(f"🔍 Analyse de {symbole}...")
            
            # 1. Récupérer le prix
            prix = self.prix_fetcher.obtenir_prix_actuel(symbole)
            if prix is None:
                logger.warning(f"⚠️ Prix non disponible pour {symbole}")
                return None
            
            # 2. Récupérer les tweets et analyser le sentiment
            tous_tweets = []
            for compte in self.config.twitter.comptes:
                tweets = self.twitter_fetcher.recuperer_tweets(compte)
                tous_tweets.extend(tweets)
            
            sentiment = self.twitter_fetcher.analyser_sentiment(tous_tweets, symbole)
            
            # 3. Analyser l'achat
            analyse_achat = self.strategie.analyser_achat(symbole, prix, sentiment)
            
            # 4. Analyser la vente
            analyse_vente = self.strategie.analyser_vente(symbole, prix, sentiment)
            
            # 5. Déterminer la décision finale
            if analyse_vente['decision']:
                decision = "VENTE"
                analyse = analyse_vente
                ordre = self.formateur.formater_ordre_vente(symbole, prix)
                message_func = self.sender.envoyer_alerte_vente
                self.stats['ventes'] += 1
                
            elif analyse_achat['decision']:
                decision = "ACHAT"
                analyse = analyse_achat
                ordre = self.formateur.formater_ordre_achat(symbole, prix)
                message_func = self.sender.envoyer_alerte_achat
                self.stats['achats'] += 1
                
            else:
                decision = "ATTENDRE"
                analyse = None
                ordre = None
                message_func = None
            
            # 6. Afficher les résultats
            logger.info(f"   Prix: {prix:.2f}€ | Sentiment: {sentiment:.2f}")
            
            if analyse:
                logger.info(f"   Décision: {decision} (force: {analyse['force_signal']:.2f})")
                for raison in analyse['raisons'][:3]:
                    logger.info(f"      • {raison}")
            
            # 7. Envoyer l'alerte si nécessaire
            if ordre and message_func:
                success = message_func(ordre)
                if success:
                    self.stats['alertes'] += 1
                    self.historique_alertes.append({
                        'timestamp': datetime.now(),
                        'symbole': symbole,
                        'decision': decision,
                        'prix': prix,
                        'force_signal': analyse['force_signal'] if analyse else None
                    })
                    logger.info(f"📱 Alerte envoyée pour {symbole}")
            
            return {
                'symbole': symbole,
                'decision': decision,
                'prix': prix,
                'sentiment': sentiment,
                'force_signal': analyse['force_signal'] if analyse else None,
                'raisons': analyse['raisons'] if analyse else []
            }
            
        except Exception as e:
            logger.error(f"❌ Erreur lors de l'analyse de {symbole}: {e}")
            logger.debug(traceback.format_exc())
            return None
    
    def analyser_toutes_actions(self) -> List[Dict]:
        """
        Analyse toutes les actions configurées.
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"🔍 DÉBUT DE L'ANALYSE - {datetime.now().strftime('%H:%M:%S')}")
        logger.info(f"{'='*60}")
        
        resultats = []
        
        for symbole in self.config.actions.symboles:
            resultat = self.analyser_action(symbole)
            if resultat:
                resultats.append(resultat)
            time.sleep(2)  # Pause entre les analyses
        
        self.stats['analyses'] += 1
        
        # Afficher le résumé
        nb_alertes = len([r for r in resultats if r['decision'] != 'ATTENDRE'])
        logger.info(f"\n📊 RÉSUMÉ: {nb_alertes} alerte(s) générée(s)")
        
        for r in resultats:
            if r['decision'] != 'ATTENDRE':
                logger.info(f"   • {r['symbole']}: {r['decision']} @ {r['prix']:.2f}€")
        
        return resultats
    
    def demarrer(self):
        """
        Démarre le bot en mode continu.
        """
        logger.info("\n" + "="*60)
        logger.info("🤖 BOT DE TRADING DÉMARRÉ")
        logger.info("="*60)
        logger.info(f"📊 Actions surveillées: {len(self.config.actions.symboles)} actions")
        logger.info(f"🐦 Comptes Twitter: {len(self.config.twitter.comptes)} comptes")
        logger.info(f"⏱️  Intervalle d'analyse: {self.config.intervalle_analyse_minutes} minutes")
        logger.info("="*60)
        
        # Envoyer message de démarrage
        self.sender.envoyer_message_demarrage(self.config.actions.symboles)
        
        self.actif = True
        
        def handler_arret(signum, frame):
            logger.info("\n🛑 Signal d'arrêt reçu")
            self.actif = False
        
        signal.signal(signal.SIGINT, handler_arret)
        signal.signal(signal.SIGTERM, handler_arret)
        
        try:
            while self.actif:
                try:
                    # Analyser toutes les actions
                    self.analyser_toutes_actions()
                    
                    # Attendre avant la prochaine analyse
                    if self.actif:
                        logger.info(f"\n⏰ Prochaine analyse dans {self.config.intervalle_analyse_minutes} minutes...")
                        for _ in range(self.config.intervalle_analyse_minutes * 60):
                            if not self.actif:
                                break
                            time.sleep(1)
                            
                except Exception as e:
                    logger.error(f"❌ Erreur dans la boucle principale: {e}")
                    logger.info("Attente 5 minutes avant reprise...")
                    time.sleep(300)
                    
        finally:
            self.arreter()
    
    def arreter(self):
        """
        Arrête le bot proprement.
        """
        self.actif = False
        
        # Calculer les statistiques finales
        stats_finales = {
            'analyses': self.stats['analyses'],
            'alertes': self.stats['alertes'],
            'achats': self.stats['achats'],
            'ventes': self.stats['ventes'],
            'duree': str(datetime.now() - self.stats['demarrage']).split('.')[0]
        }
        
        logger.info("\n" + "="*60)
        logger.info("🛑 BOT DE TRADING ARRÊTÉ")
        logger.info("="*60)
        logger.info(f"📊 Statistiques de la session:")
        logger.info(f"   • Durée: {stats_finales['duree']}")
        logger.info(f"   • Analyses: {stats_finales['analyses']}")
        logger.info(f"   • Alertes envoyées: {stats_finales['alertes']}")
        logger.info(f"   • Achats suggérés: {stats_finales['achats']}")
        logger.info(f"   • Ventes suggérées: {stats_finales['ventes']}")
        logger.info("="*60)
        
        # Envoyer message d'arrêt
        self.sender.envoyer_message_arret(stats_finales)
    
    def executer_analyse_unique(self) -> List[Dict]:
        """
        Exécute une seule analyse (mode manuel).
        """
        logger.info("🔍 Mode analyse unique")
        return self.analyser_toutes_actions()
    
    def afficher_historique(self, nb: int = 10):
        """
        Affiche l'historique des alertes.
        """
        if not self.historique_alertes:
            logger.info("Aucune alerte dans l'historique")
            return
        
        logger.info(f"\n📜 HISTORIQUE DES {min(nb, len(self.historique_alertes))} DERNIÈRES ALERTES:")
        for alerte in self.historique_alertes[-nb:]:
            logger.info(f"   {alerte['timestamp'].strftime('%d/%m %H:%M')} - {alerte['symbole']}: {alerte['decision']} @ {alerte['prix']:.2f}€")


# ============================================================================
# PARTIE 9 : FONCTIONS DE TEST ET UTILITAIRES
# ============================================================================

def creer_config_demo() -> ConfigBot:
    """
    Crée une configuration de démonstration.
    """
    config = ConfigBot()
    
    # Pour la démo, on utilise des valeurs par défaut
    # À remplacer par vos vraies valeurs
    config.telegram.token = "8610437171:AAE58osb70J-VnObUxps3kM-XAQqU5ZLGvQ"
    config.telegram.chat_id = "8416526688"
    
    return config


def verifier_configuration(config: ConfigBot) -> bool:
    """
    Vérifie que la configuration est valide.
    """
    erreurs = []
    
    if config.telegram.token == "8610437171:AAE58osb70J-VnOzUxps3kM-XAQcU5ZLGvQ":
        erreurs.append("Token Telegram non configuré")
    
    if config.telegram.chat_id == "41987817":
        erreurs.append("Chat ID Telegram non configuré")
    
    if not config.actions.symboles:
        erreurs.append("Aucune action à surveiller")
    
    if not config.twitter.comptes:
        erreurs.append("Aucun compte Twitter à surveiller")
    
    if erreurs:
        logger.error("❌ Erreurs de configuration:")
        for err in erreurs:
            logger.error(f"   • {err}")
        return False
    
    return True


def test_telegram():
    """Test d'envoi Telegram"""
    print("\n" + "="*60)
    print("📱 TEST D'ENVOI TELEGRAM")
    print("="*60)
    
    config = creer_config_demo()
    
    if config.telegram.token == "VOTRE_TOKEN_TELEGRAM":
        print("\n❌ Veuillez configurer vos identifiants Telegram dans config.py")
        print("   TOKEN: votre token BotFather")
        print("   CHAT_ID: votre ID utilisateur")
        return
    
    sender = TelegramSender(config.telegram.token, config.telegram.chat_id)
    
    message_test = f"""
🧪 *MESSAGE DE TEST* 🧪

Ceci est un message de test pour vérifier que votre bot Telegram fonctionne correctement.

*Date* : {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}

Si vous recevez ce message, tout fonctionne ! ✅
"""
    
    success = sender.envoyer_message(message_test)
    
    if success:
        print("\n✅ Message de test envoyé avec succès !")
        print("   Vérifiez votre téléphone Telegram")
    else:
        print("\n❌ Échec de l'envoi du message")
        print("   Vérifiez votre token et chat_id")


def test_prix():
    """Test de récupération des prix"""
    print("\n" + "="*60)
    print("💰 TEST DE RÉCUPÉRATION DES PRIX")
    print("="*60)
    
    config = ConfigBot()
    fetcher = PrixFetcher(config.strategie)
    
    for symbole in ["AI.PA", "TTE.PA"]:
        prix = fetcher.obtenir_prix_actuel(symbole)
        if prix:
            print(f"✅ {symbole}: {prix:.2f}€")
            
            variation = fetcher.calculer_variation(symbole, 1)
            if variation['variation_pct']:
                print(f"   Variation 1j: {variation['variation_pct']:+.2f}%")
        else:
            print(f"❌ {symbole}: prix non disponible")


def test_twitter():
    """Test de récupération des tweets"""
    print("\n" + "="*60)
    print("🐦 TEST DE RÉCUPÉRATION DES TWEETS")
    print("="*60)
    
    config = ConfigBot()
    fetcher = TwitterFetcher(config)
    
    for compte in ["BourseDirect"]:
        print(f"\n📡 Récupération des tweets de @{compte}:")
        tweets = fetcher.recuperer_tweets(compte)
        
        if tweets:
            print(f"   ✅ {len(tweets)} tweets récupérés")
            for tweet in tweets[:2]:
                print(f"      • {tweet['texte'][:80]}...")
            
            sentiment = fetcher.analyser_sentiment(tweets, "AIR LIQUIDE")
            print(f"   📊 Sentiment: {sentiment:.2f}")
        else:
            print(f"   ❌ Aucun tweet récupéré")


# ============================================================================
# PARTIE 10 : EXÉCUTION PRINCIPALE
# ============================================================================

def main():
    """Point d'entrée principal"""
    
    print("\n" + "="*60)
    print("🤖 BOT DE TRADING - VERSION COMPLÈTE")
    print("="*60)
    print("\nChoisissez un mode d'exécution:")
    print("  1 - Mode continu (analyse toutes les X minutes)")
    print("  2 - Mode analyse unique (une seule analyse)")
    print("  3 - Test Telegram uniquement")
    print("  4 - Test récupération des prix")
    print("  5 - Test récupération des tweets")
    print("  6 - Tous les tests")
    
    choix = input("\nVotre choix (1-6) : ").strip()
    
    if choix == "1":
        # Mode continu
        config = creer_config_demo()
        
        if not verifier_configuration(config):
            print("\n⚠️ Configuration incomplète. Éditez config.py avec vos identifiants.")
            return
        
        bot = BotTrading(config)
        bot.demarrer()
        
    elif choix == "2":
        # Mode analyse unique
        config = creer_config_demo()
        
        if not verifier_configuration(config):
            print("\n⚠️ Configuration incomplète. Éditez config.py avec vos identifiants.")
            return
        
        bot = BotTrading(config)
        resultats = bot.executer_analyse_unique()
        
        if resultats:
            print("\n📊 RÉSULTATS DE L'ANALYSE:")
            for r in resultats:
                if r['decision'] != 'ATTENDRE':
                    print(f"   ✅ {r['symbole']}: {r['decision']} @ {r['prix']:.2f}€")
                else:
                    print(f"   ⏸️ {r['symbole']}: {r['decision']}")
        
    elif choix == "3":
        test_telegram()
        
    elif choix == "4":
        test_prix()
        
    elif choix == "5":
        test_twitter()
        
    elif choix == "6":
        test_telegram()
        test_prix()
        test_twitter()
        
    else:
        print("Choix invalide")


if __name__ == "__main__":
    main()