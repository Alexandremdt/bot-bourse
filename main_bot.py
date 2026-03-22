"""
BOT DE TRADING PRINCIPAL - Version complète avec boucle continue
Utilise l'API Telegram directement - Compatible Python 3.13
"""

import os
import sys
import time
import json
import logging
import signal
import traceback
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

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

logger.info("✅ requests chargé")


# ============================================================================
# PARTIE 2 : CONFIGURATION (À MODIFIER AVEC VOS IDENTIFIANTS)
# ============================================================================

@dataclass
class ConfigTelegram:
    """Configuration Telegram"""
    # 🔑 REMPLACEZ ICI AVEC VOS IDENTIFIANTS
    token: str = "8610437171:AAE58osb70J-VnObUxps3kM-XAQqU5ZLGvQ"
    chat_id: str = "8416526688"


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
            ]


@dataclass
class ConfigStrategie:
    """Configuration de la stratégie de trading"""
    # Seuils de prix (personnalisez selon vos actions)
    prix_achat_max_ai: float = 170.0    # Air Liquide
    prix_achat_max_tte: float = 80.0     # TotalEnergies
    prix_achat_max_mc: float = 800.0     # LVMH
    prix_achat_max_defaut: float = 150.0  # Par défaut
    
    # Gestion des risques
    stop_loss_pct: float = -3.0
    take_profit_pct: float = 10.0
    
    # Poids des signaux
    poids_signal_prix: float = 0.6
    poids_signal_tweet: float = 0.4
    seuil_achat: float = 0.2
    seuil_vente: float = 0.5
    
    # Paramètres d'ordre
    quantite_par_defaut: int = 10
    compte_par_defaut: str = "comptant"
    
    def get_prix_achat_max(self, symbole: str) -> float:
        """Retourne le prix d'achat max selon l'action"""
        if symbole == "AI.PA":
            return self.prix_achat_max_ai
        elif symbole == "TTE.PA":
            return self.prix_achat_max_tte
        elif symbole == "MC.PA":
            return self.prix_achat_max_mc
        else:
            return self.prix_achat_max_defaut


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
    
    def obtenir_infos_actions(self, symbole: str) -> Dict:
        """Récupère les informations détaillées d'une action"""
        try:
            action = yf.Ticker(symbole)
            infos = action.info
            return {
                'nom': infos.get('longName', symbole),
                'secteur': infos.get('sector', 'Inconnu'),
                'variation_24h': infos.get('regularMarketChangePercent', 0),
                'volume': infos.get('volume', 0),
            }
        except Exception as e:
            logger.error(f"Erreur infos {symbole}: {e}")
            return {'nom': symbole, 'secteur': 'Inconnu', 'variation_24h': 0, 'volume': 0}


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
            "risque", "crainte", "effondrement", "perte", "déception",
            "avertissement", "diminution"
        ]
    
    def _nettoyer_texte(self, texte: str) -> str:
        import re
        texte = re.sub(r'https?://t\.co/\w+', '', texte)
        texte = re.sub(r'http\S+', '', texte)
        texte = re.sub(r'@\w+', '', texte)
        texte = texte.replace('\n', ' ').replace('\r', ' ')
        texte = re.sub(r'\s+', ' ', texte)
        return texte.strip()
    
    def recuperer_tweets(self, compte: str) -> List[Dict]:
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
        if not tweets:
            return 0.0
        
        score_total = 0.0
        tweets_pertinents = 0
        symbole_simple = symbole.replace('.PA', '').lower()
        
        for tweet in tweets:
            texte = tweet['texte'].lower()
            if symbole_simple in texte:
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
        self.positions_ouvertes: Dict[str, Dict] = {}
    
    def analyser_achat(self, symbole: str, prix: float, sentiment: float, 
                       prix_achat_max: float) -> Dict:
        force_signal = 0.0
        raisons = []
        
        # Vérifier si on a déjà une position ouverte
        if symbole in self.positions_ouvertes:
            return {'decision': False, 'force_signal': 0, 'raisons': ["Position déjà ouverte"]}
        
        # Signal prix
        if prix < prix_achat_max:
            contribution = self.config.poids_signal_prix * 1.0
            force_signal += contribution
            raisons.append(f"✅ Prix attractif: {prix:.2f}€ < {prix_achat_max:.2f}€")
        else:
            contribution = self.config.poids_signal_prix * -0.5
            force_signal += contribution
            raisons.append(f"⚠️ Prix élevé: {prix:.2f}€ > {prix_achat_max:.2f}€")
        
        # Signal sentiment
        if sentiment > 0.3:
            contribution = self.config.poids_signal_tweet * 1.0
            force_signal += contribution
            raisons.append(f"📈 Sentiment positif: {sentiment:.2f}")
        elif sentiment < -0.3:
            contribution = self.config.poids_signal_tweet * -0.8
            force_signal += contribution
            raisons.append(f"📉 Sentiment négatif: {sentiment:.2f}")
        else:
            raisons.append(f"⚖️ Sentiment neutre: {sentiment:.2f}")
        
        decision = force_signal > self.config.seuil_achat
        
        if decision:
            raisons.append(f"🎯 FORCE TOTALE: {force_signal:.2f} > {self.config.seuil_achat}")
        else:
            raisons.append(f"⏸️ FORCE TOTALE: {force_signal:.2f} < {self.config.seuil_achat}")
        
        return {
            'decision': decision,
            'force_signal': round(force_signal, 2),
            'raisons': raisons
        }
    
    def analyser_vente(self, symbole: str, prix: float, sentiment: float) -> Dict:
        force_signal = 0.0
        raisons = []
        
        if symbole not in self.positions_ouvertes:
            return {'decision': False, 'force_signal': 0, 'raisons': ["Pas de position ouverte"]}
        
        position = self.positions_ouvertes[symbole]
        prix_achat = position['prix_achat']
        performance = (prix - prix_achat) / prix_achat * 100
        
        raisons.append(f"💰 Performance: {performance:.1f}%")
        
        # Take profit
        if performance >= self.config.take_profit_pct:
            force_signal += 0.9
            raisons.append(f"🎯 TAKE PROFIT: +{performance:.1f}% atteint!")
        
        # Stop loss
        elif performance <= self.config.stop_loss_pct:
            force_signal += 0.9
            raisons.append(f"🛑 STOP LOSS: {performance:.1f}% atteint!")
        
        # Sentiment très négatif
        if sentiment < -0.5:
            force_signal += 0.4
            raisons.append(f"📉 Sentiment très négatif: {sentiment:.2f}")
        
        decision = force_signal > self.config.seuil_vente
        
        if decision:
            raisons.append(f"🎯 VENTE RECOMMANDÉE: force {force_signal:.2f} > {self.config.seuil_vente}")
        else:
            raisons.append(f"⏸️ Garder la position: force {force_signal:.2f} < {self.config.seuil_vente}")
        
        return {
            'decision': decision,
            'force_signal': round(force_signal, 2),
            'raisons': raisons,
            'performance': performance,
            'prix_achat': prix_achat
        }
    
    def ouvrir_position(self, symbole: str, prix: float):
        self.positions_ouvertes[symbole] = {
            'prix_achat': prix,
            'date_ouverture': datetime.now(),
            'quantite': self.config.quantite_par_defaut
        }
        logger.info(f"📊 Position ouverte sur {symbole} à {prix:.2f}€")
    
    def fermer_position(self, symbole: str):
        if symbole in self.positions_ouvertes:
            del self.positions_ouvertes[symbole]
            logger.info(f"📊 Position fermée sur {symbole}")


# ============================================================================
# PARTIE 6 : MODULE DE FORMATAGE D'ORDRE
# ============================================================================

class FormateurOrdre:
    """Formate un ordre pour Bourse Direct"""
    
    def __init__(self, config: ConfigStrategie):
        self.config = config
    
    def formater_ordre_achat(self, symbole: str, prix_actuel: float, 
                              quantite: int = None) -> Dict:
        if quantite is None:
            quantite = self.config.quantite_par_defaut
        
        prix_limite = round(prix_actuel * 0.98, 2)  # 2% en dessous
        montant_total = quantite * prix_limite
        
        return {
            'statut': 'OK',
            'date_generation': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'ordre': {
                'symbole': symbole,
                'decision': 'ACHAT',
                'compte': self.config.compte_par_defaut,
                'type_ordre': 'À cours limité',
                'quantite': quantite,
                'montant_total': round(montant_total, 2),
                'prix_actuel': prix_actuel,
                'prix_limite': prix_limite,
                'validite': 'Date (30 jours)',
                'strategie': 'Take profit + Stop loss',
                'objectif_take_profit': round(prix_actuel * (1 + self.config.take_profit_pct / 100), 2),
                'seuil_stop_loss': round(prix_actuel * (1 + self.config.stop_loss_pct / 100), 2)
            }
        }
    
    def formater_ordre_vente(self, symbole: str, prix_actuel: float,
                              quantite: int = None) -> Dict:
        if quantite is None:
            quantite = self.config.quantite_par_defaut
        
        seuil = round(prix_actuel * 0.97, 2)  # Stop-loss à -3%
        montant_total = quantite * seuil
        
        return {
            'statut': 'OK',
            'date_generation': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'ordre': {
                'symbole': symbole,
                'decision': 'VENTE',
                'compte': self.config.compte_par_defaut,
                'type_ordre': 'À seuil de déclenchement',
                'quantite': quantite,
                'montant_total': round(montant_total, 2),
                'prix_actuel': prix_actuel,
                'seuil_declenchement': seuil,
                'validite': 'Date (30 jours)',
                'strategie': 'Stop loss'
            }
        }


# ============================================================================
# PARTIE 7 : MODULE D'ENVOI TELEGRAM (VIA API DIRECTE)
# ============================================================================

class TelegramSender:
    """Envoi de messages sur Telegram via l'API directe"""
    
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{token}"
        self._verifier_connexion()
    
    def _verifier_connexion(self):
        try:
            response = requests.get(f"{self.api_url}/getMe", timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('ok'):
                    bot_info = data.get('result', {})
                    logger.info(f"✅ Bot Telegram: @{bot_info.get('username', 'unknown')}")
                    return True
            logger.error(f"❌ Erreur connexion Telegram")
            return False
        except Exception as e:
            logger.error(f"❌ Erreur connexion Telegram: {e}")
            return False
    
    def envoyer_message(self, message: str, parse_mode: str = 'Markdown') -> bool:
        try:
            if len(message) > 4096:
                message = message[:4093] + "..."
            
            response = requests.post(
                f"{self.api_url}/sendMessage",
                data={"chat_id": self.chat_id, "text": message, "parse_mode": parse_mode},
                timeout=30
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Erreur envoi: {e}")
            return False
    
    def envoyer_alerte_achat(self, ordre: Dict, analyse: Dict) -> bool:
        data = ordre['ordre']
        message = (
            "🟢 *ALERTE ACHAT BOURSE DIRECT* 🟢\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"*{data['symbole']}*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"💰 *Prix actuel* : {data['prix_actuel']:.2f} €\n"
            f"🎯 *Prix limite* : {data['prix_limite']:.2f} €\n"
            f"📊 *Quantité* : {data['quantite']} actions\n"
            f"💶 *Montant total* : {data['montant_total']:,.2f} €\n\n"
            f"📈 *Force du signal* : {analyse['force_signal']:.2f}\n\n"
            "🎯 *Stratégie* :\n"
            f"   ├ *Objectif* : {data['objectif_take_profit']:.2f} € (+10%)\n"
            f"   └ *Stop-loss* : {data['seuil_stop_loss']:.2f} € (-3%)\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "📱 *Pour passer l'ordre sur Bourse Direct* :\n\n"
            f"1️⃣ Ordre d'achat sur {data['symbole']}\n"
            f"2️⃣ Compte {data['compte']}\n"
            f"3️⃣ Type: {data['type_ordre']}\n"
            f"4️⃣ Quantité: {data['quantite']}\n"
            f"5️⃣ Prix limite: {data['prix_limite']:.2f} €\n\n"
            f"*Généré le* : {ordre['date_generation']}"
        )
        return self.envoyer_message(message)
    
    def envoyer_alerte_vente(self, ordre: Dict, analyse: Dict) -> bool:
        data = ordre['ordre']
        message = (
            "🔴 *ALERTE VENTE BOURSE DIRECT* 🔴\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"*{data['symbole']}*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"💰 *Prix actuel* : {data['prix_actuel']:.2f} €\n"
            f"⚡ *Seuil déclenchement* : {data['seuil_declenchement']:.2f} €\n"
            f"📊 *Quantité* : {data['quantite']} actions\n"
            f"💶 *Montant estimé* : {data['montant_total']:,.2f} €\n\n"
            f"📉 *Performance* : {analyse.get('performance', 0):.1f}%\n"
            f"💰 *Prix d'achat* : {analyse.get('prix_achat', 0):.2f} €\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "📱 *Pour passer l'ordre sur Bourse Direct* :\n\n"
            f"1️⃣ Ordre de vente sur {data['symbole']}\n"
            f"2️⃣ Compte {data['compte']}\n"
            f"3️⃣ Type: {data['type_ordre']}\n"
            f"4️⃣ Quantité: {data['quantite']}\n"
            f"5️⃣ Seuil: {data['seuil_declenchement']:.2f} €\n\n"
            f"*Généré le* : {ordre['date_generation']}"
        )
        return self.envoyer_message(message)
    
    def envoyer_message_test(self) -> bool:
        message = (
            "🧪 *MESSAGE DE TEST* 🧪\n\n"
            "✅ Votre bot Telegram fonctionne correctement !\n\n"
            f"📅 *Date* : {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n\n"
            "Le bot est prêt à surveiller les marchés.\n\n"
            "*Statut* : 🟢 ACTIF"
        )
        return self.envoyer_message(message)
    
    def envoyer_message_demarrage(self, actions: List[str]) -> bool:
        actions_list = "\n".join([f"   • {a}" for a in actions])
        message = (
            "🤖 *BOT DE TRADING DÉMARRÉ* 🤖\n\n"
            f"📅 *Date et heure* : {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n\n"
            "📊 *Actions surveillées* :\n"
            f"{actions_list}\n\n"
            "🎯 *Stratégie* :\n"
            "   • Achat si prix < seuil + sentiment positif\n"
            "   • Vente si +10% (take profit) ou -3% (stop loss)\n"
            "   • Analyse des tweets pour le sentiment\n\n"
            f"⏱️ *Intervalle d'analyse* : 30 minutes\n\n"
            "Vous recevrez des alertes lorsque des opportunités seront détectées.\n\n"
            "*Statut* : 🟢 ACTIF"
        )
        return self.envoyer_message(message)
    
    def envoyer_rapport_quotidien(self, analyses: List[Dict], positions: Dict) -> bool:
        """Envoie un rapport quotidien"""
        message = (
            "📊 *RAPPORT QUOTIDIEN* 📊\n\n"
            f"📅 *Date* : {datetime.now().strftime('%d/%m/%Y')}\n\n"
            "📈 *Analyses du jour* :\n"
        )
        
        for a in analyses[-10:]:  # Les 10 dernières
            if a['decision'] != 'ATTENDRE':
                message += f"   • {a['symbole']}: {a['decision']} @ {a['prix']:.2f}€\n"
        
        if positions:
            message += "\n💰 *Positions ouvertes* :\n"
            for symbole, pos in positions.items():
                message += f"   • {symbole}: acheté à {pos['prix_achat']:.2f}€\n"
        
        return self.envoyer_message(message)


# ============================================================================
# PARTIE 8 : BOT PRINCIPAL
# ============================================================================

class BotTrading:
    """Bot de trading complet avec boucle continue"""
    
    def __init__(self, config: ConfigBot):
        self.config = config
        self.actif = True
        self.stats = {
            'analyses': 0,
            'alertes_achat': 0,
            'alertes_vente': 0,
            'demarrage': datetime.now()
        }
        self.historique_analyses = []
        
        # Initialiser les modules
        self.prix_fetcher = PrixFetcher(config.strategie)
        self.twitter_fetcher = TwitterFetcher(config)
        self.strategie = StrategieDecision(config.strategie)
        self.formateur = FormateurOrdre(config.strategie)
        self.sender = TelegramSender(config.telegram.token, config.telegram.chat_id)
        
        logger.info("✅ Bot de trading initialisé")
    
    def analyser_action(self, symbole: str) -> Optional[Dict]:
        """Analyse une action et retourne la décision"""
        try:
            logger.info(f"🔍 Analyse de {symbole}...")
            
            # 1. Récupérer le prix
            prix = self.prix_fetcher.obtenir_prix_actuel(symbole)
            if prix is None:
                logger.warning(f"⚠️ Prix non disponible pour {symbole}")
                return None
            
            # 2. Récupérer les infos supplémentaires
            infos = self.prix_fetcher.obtenir_infos_actions(symbole)
            
            # 3. Récupérer et analyser les tweets
            tous_tweets = []
            for compte in self.config.twitter.comptes:
                tweets = self.twitter_fetcher.recuperer_tweets(compte)
                tous_tweets.extend(tweets)
            
            sentiment = self.twitter_fetcher.analyser_sentiment(tous_tweets, symbole)
            
            # 4. Obtenir le prix d'achat max spécifique à l'action
            prix_achat_max = self.config.strategie.get_prix_achat_max(symbole)
            
            # 5. Analyser l'achat et la vente
            analyse_achat = self.strategie.analyser_achat(
                symbole, prix, sentiment, prix_achat_max
            )
            analyse_vente = self.strategie.analyser_vente(symbole, prix, sentiment)
            
            # 6. Déterminer la décision
            resultat = {
                'symbole': symbole,
                'prix': prix,
                'sentiment': sentiment,
                'variation_24h': infos['variation_24h'],
                'timestamp': datetime.now()
            }
            
            if analyse_vente['decision']:
                resultat['decision'] = 'VENTE'
                resultat['force_signal'] = analyse_vente['force_signal']
                resultat['raisons'] = analyse_vente['raisons']
                resultat['performance'] = analyse_vente.get('performance')
                resultat['prix_achat'] = analyse_vente.get('prix_achat')
                
                # Formater et envoyer l'alerte
                ordre = self.formateur.formater_ordre_vente(symbole, prix)
                self.sender.envoyer_alerte_vente(ordre, analyse_vente)
                self.stats['alertes_vente'] += 1
                self.strategie.fermer_position(symbole)
                
            elif analyse_achat['decision']:
                resultat['decision'] = 'ACHAT'
                resultat['force_signal'] = analyse_achat['force_signal']
                resultat['raisons'] = analyse_achat['raisons']
                
                # Formater et envoyer l'alerte
                ordre = self.formateur.formater_ordre_achat(symbole, prix)
                self.sender.envoyer_alerte_achat(ordre, analyse_achat)
                self.stats['alertes_achat'] += 1
                self.strategie.ouvrir_position(symbole, prix)
                
            else:
                resultat['decision'] = 'ATTENDRE'
                resultat['force_signal'] = max(analyse_achat['force_signal'], 
                                                analyse_vente['force_signal'])
                resultat['raisons'] = analyse_achat['raisons'] if analyse_achat['raisons'] else []
            
            # Log des résultats
            logger.info(f"   Prix: {prix:.2f}€ | Sentiment: {sentiment:.2f}")
            logger.info(f"   Décision: {resultat['decision']} (force: {resultat['force_signal']:.2f})")
            
            return resultat
            
        except Exception as e:
            logger.error(f"❌ Erreur analyse {symbole}: {e}")
            logger.debug(traceback.format_exc())
            return None
    
    def analyser_toutes_actions(self) -> List[Dict]:
        """Analyse toutes les actions configurées"""
        logger.info("\n" + "="*60)
        logger.info(f"🔍 DÉBUT DE L'ANALYSE - {datetime.now().strftime('%H:%M:%S')}")
        logger.info("="*60)
        
        resultats = []
        for symbole in self.config.actions.symboles:
            resultat = self.analyser_action(symbole)
            if resultat:
                resultats.append(resultat)
            time.sleep(2)  # Pause entre les analyses
        
        self.stats['analyses'] += 1
        self.historique_analyses.extend(resultats)
        
        # Garder seulement les 100 dernières analyses
        if len(self.historique_analyses) > 100:
            self.historique_analyses = self.historique_analyses[-100:]
        
        # Résumé
        nb_achats = len([r for r in resultats if r['decision'] == 'ACHAT'])
        nb_ventes = len([r for r in resultats if r['decision'] == 'VENTE'])
        
        logger.info(f"\n📊 RÉSUMÉ: {nb_achats} achat(s), {nb_ventes} vente(s)")
        
        for r in resultats:
            if r['decision'] != 'ATTENDRE':
                logger.info(f"   • {r['symbole']}: {r['decision']} @ {r['prix']:.2f}€ (force: {r['force_signal']:.2f})")
        
        return resultats
    
    def demarrer(self):
        """Démarre le bot en mode continu"""
        logger.info("\n" + "="*60)
        logger.info("🤖 BOT DE TRADING DÉMARRÉ")
        logger.info("="*60)
        logger.info(f"📊 Actions: {len(self.config.actions.symboles)}")
        logger.info(f"🐦 Comptes Twitter: {len(self.config.twitter.comptes)}")
        logger.info(f"⏱️  Intervalle: {self.config.intervalle_analyse_minutes} minutes")
        logger.info("="*60)
        
        # Envoyer message de démarrage
        self.sender.envoyer_message_demarrage(self.config.actions.symboles)
        
        # Gestion de l'arrêt
        def handler_arret(signum, frame):
            logger.info("\n🛑 Arrêt demandé...")
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
                    logger.error(f"❌ Erreur boucle principale: {e}")
                    logger.info("Attente 5 minutes avant reprise...")
                    time.sleep(300)
                    
        finally:
            self.arreter()
    
    def arreter(self):
        """Arrête le bot proprement"""
        duree = datetime.now() - self.stats['demarrage']
        
        logger.info("\n" + "="*60)
        logger.info("🛑 BOT DE TRADING ARRÊTÉ")
        logger.info("="*60)
        logger.info(f"📊 Statistiques:")
        logger.info(f"   • Durée: {str(duree).split('.')[0]}")
        logger.info(f"   • Analyses: {self.stats['analyses']}")
        logger.info(f"   • Alertes achat: {self.stats['alertes_achat']}")
        logger.info(f"   • Alertes vente: {self.stats['alertes_vente']}")
        logger.info(f"   • Positions ouvertes: {len(self.strategie.positions_ouvertes)}")
        logger.info("="*60)
        
        # Envoyer rapport final
        if self.stats['analyses'] > 0:
            message = (
                "🛑 *BOT ARRÊTÉ* 🛑\n\n"
                f"📊 *Statistiques de la session* :\n"
                f"   • Durée: {str(duree).split('.')[0]}\n"
                f"   • Analyses: {self.stats['analyses']}\n"
                f"   • Alertes achat: {self.stats['alertes_achat']}\n"
                f"   • Alertes vente: {self.stats['alertes_vente']}\n\n"
                "À bientôt ! 👋"
            )
            self.sender.envoyer_message(message)


# ============================================================================
# PARTIE 9 : FONCTIONS DE TEST
# ============================================================================

def test_telegram():
    """Test d'envoi Telegram"""
    print("\n" + "="*60)
    print("📱 TEST D'ENVOI TELEGRAM")
    print("="*60)
    
    config = ConfigBot()
    token = config.telegram.token
    chat_id = config.telegram.chat_id
    
    print(f"🔑 Token: {token[:15]}...")
    print(f"📱 Chat ID: {chat_id}")
    print("\n📤 Envoi du message de test...")
    
    sender = TelegramSender(token, chat_id)
    success = sender.envoyer_message_test()
    
    if success:
        print("\n✅ Message de test envoyé avec succès !")
        print("   Vérifiez votre téléphone Telegram")
        print("\n💡 Pour lancer le bot en continu, choisissez l'option 1")
    else:
        print("\n❌ Échec de l'envoi")
        print("   Vérifiez que vous avez envoyé /start au bot")


def test_analyse_unique():
    """Test d'analyse unique"""
    print("\n" + "="*60)
    print("🔍 TEST D'ANALYSE UNIQUE")
    print("="*60)
    
    config = ConfigBot()
    bot = BotTrading(config)
    
    print("\n📊 Analyse des actions en cours...\n")
    resultats = bot.analyser_toutes_actions()
    
    print("\n" + "="*60)
    print("📋 RÉSULTATS:")
    print("="*60)
    
    for r in resultats:
        if r['decision'] == 'ACHAT':
            print(f"🟢 {r['symbole']}: ACHAT @ {r['prix']:.2f}€ (force: {r['force_signal']:.2f})")
        elif r['decision'] == 'VENTE':
            print(f"🔴 {r['symbole']}: VENTE @ {r['prix']:.2f}€ (force: {r['force_signal']:.2f})")
        else:
            print(f"⚪ {r['symbole']}: ATTENDRE @ {r['prix']:.2f}€")


# ============================================================================
# PARTIE 10 : EXÉCUTION PRINCIPALE
# ============================================================================

def main():
    print("\n" + "="*60)
    print("🤖 BOT DE TRADING - VERSION COMPLÈTE")
    print("="*60)
    print("\nChoisissez un mode d'exécution:")
    print("  1 - Mode continu (analyse toutes les 30 minutes)")
    print("  2 - Test analyse unique")
    print("  3 - Test Telegram uniquement")
    print("  4 - Tous les tests")
    
    choix = input("\nVotre choix (1-4) : ").strip()
    
    if choix == "1":
        config = ConfigBot()
        bot = BotTrading(config)
        bot.demarrer()
        
    elif choix == "2":
        test_analyse_unique()
        
    elif choix == "3":
        test_telegram()
        
    elif choix == "4":
        test_telegram()
        print("\n" + "="*60)
        test_analyse_unique()
        
    else:
        print("Choix invalide. Exécution du mode continu...")
        config = ConfigBot()
        bot = BotTrading(config)
        bot.demarrer()


if __name__ == "__main__":
    main()