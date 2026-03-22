"""
BOT DE TRADING - Version pour Render.com (sans interaction)
Tourne en continu 24h/24
"""

import os
import sys
import time
import logging
import signal
import requests
import yfinance as yf
import feedparser
from datetime import datetime
from typing import Dict, List, Optional

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION (À MODIFIER AVEC VOS IDENTIFIANTS)
# ============================================================================

# 🔑 REMPLACEZ ICI AVEC VOS IDENTIFIANTS
TELEGRAM_TOKEN = "8610437171:AAE58osb70J-VnObUxps3kM-XAQqU5ZLGvQ"
TELEGRAM_CHAT_ID = "8416526688"

# Actions à surveiller
ACTIONS = [
    "AI.PA",   # Air Liquide
    "TTE.PA",  # TotalEnergies
    "MC.PA",   # LVMH
]

# Comptes Twitter à surveiller
COMPTES_TWITTER = ["BourseDirect", "Investir_FR"]

# Paramètres de la stratégie
PRIX_ACHAT_MAX = {
    "AI.PA": 170.0,
    "TTE.PA": 80.0,
    "MC.PA": 800.0,
}
QUANTITE_PAR_DEFAUT = 10
STOP_LOSS_PCT = -3.0
TAKE_PROFIT_PCT = 10.0

# Intervalle d'analyse (en secondes)
INTERVALLE_SECONDES = 30 * 60  # 30 minutes

# ============================================================================
# CLASSE TELEGRAM
# ============================================================================

class TelegramSender:
    def __init__(self):
        self.api_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
    
    def envoyer(self, message: str) -> bool:
        try:
            response = requests.post(
                f"{self.api_url}/sendMessage",
                data={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"},
                timeout=30
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Erreur envoi: {e}")
            return False
    
    def envoyer_alerte_achat(self, symbole: str, prix: float, force: float) -> bool:
        message = (
            "🟢 *ALERTE ACHAT* 🟢\n\n"
            f"*Action* : {symbole}\n"
            f"*Prix actuel* : {prix:.2f} €\n"
            f"*Force du signal* : {force:.2f}\n\n"
            f"👉 Quantité suggérée: {QUANTITE_PAR_DEFAUT} actions\n"
            f"👉 Ordre à cours limité à {prix * 0.98:.2f} €"
        )
        return self.envoyer(message)
    
    def envoyer_alerte_vente(self, symbole: str, prix: float, perf: float) -> bool:
        message = (
            "🔴 *ALERTE VENTE* 🔴\n\n"
            f"*Action* : {symbole}\n"
            f"*Prix actuel* : {prix:.2f} €\n"
            f"*Performance* : {perf:.1f}%\n\n"
            f"👉 Vendre {QUANTITE_PAR_DEFAUT} actions"
        )
        return self.envoyer(message)
    
    def envoyer_demarrage(self) -> bool:
        message = (
            "🤖 *BOT DE TRADING DÉMARRÉ* 🤖\n\n"
            f"📅 *Date* : {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n"
            f"📊 *Actions* : {', '.join(ACTIONS)}\n"
            "✅ Bot actif et en surveillance"
        )
        return self.envoyer(message)

# ============================================================================
# CLASSE PRINCIPALE
# ============================================================================

class BotTrading:
    def __init__(self):
        self.telegram = TelegramSender()
        self.positions = {}
        self.analyses = []
        self.running = True
        
        # Configurer la gestion de l'arrêt
        signal.signal(signal.SIGINT, self._arret)
        signal.signal(signal.SIGTERM, self._arret)
    
    def _arret(self, signum, frame):
        logger.info("Arrêt demandé...")
        self.running = False
    
    def obtenir_prix(self, symbole: str) -> Optional[float]:
        try:
            action = yf.Ticker(symbole)
            donnees = action.history(period="1d")
            if not donnees.empty:
                return round(donnees['Close'].iloc[-1], 2)
            return None
        except Exception as e:
            logger.error(f"Erreur prix {symbole}: {e}")
            return None
    
    def recuperer_tweets(self) -> List[Dict]:
        tweets = []
        instances = [
            "https://nitter.net",
            "https://nitter.privacydev.net",
            "https://nitter.poast.org",
        ]
        
        for compte in COMPTES_TWITTER:
            for instance in instances:
                try:
                    url = f"{instance}/{compte}/rss"
                    flux = feedparser.parse(url)
                    if flux.entries:
                        for entry in flux.entries[:5]:
                            tweets.append({
                                'texte': entry.title,
                                'compte': compte
                            })
                        break
                except:
                    continue
        return tweets
    
    def analyser_sentiment(self, tweets: List[Dict], symbole: str) -> float:
        mots_positifs = ["hausse", "monte", "croissance", "positif", "achat"]
        mots_negatifs = ["baisse", "descend", "chute", "négatif", "vente"]
        
        score = 0
        compteur = 0
        symbole_simple = symbole.replace('.PA', '').lower()
        
        for tweet in tweets:
            texte = tweet['texte'].lower()
            if symbole_simple in texte:
                compteur += 1
                for mot in mots_positifs:
                    if mot in texte:
                        score += 1
                for mot in mots_negatifs:
                    if mot in texte:
                        score -= 1
        
        if compteur == 0:
            return 0
        return max(-1, min(1, score / compteur / 2))
    
    def analyser_achat(self, symbole: str, prix: float, sentiment: float) -> Dict:
        prix_max = PRIX_ACHAT_MAX.get(symbole, 150.0)
        force = 0
        
        if prix < prix_max:
            force += 0.6
            raison = f"Prix bas: {prix:.2f}€ < {prix_max:.2f}€"
        else:
            force -= 0.3
            raison = f"Prix élevé: {prix:.2f}€"
        
        if sentiment > 0.3:
            force += 0.4
            raison += f" | Sentiment positif: {sentiment:.2f}"
        
        return {'decision': force > 0.2, 'force': round(force, 2), 'raison': raison}
    
    def analyser_vente(self, symbole: str, prix: float) -> Dict:
        if symbole not in self.positions:
            return {'decision': False, 'force': 0, 'raison': "Pas de position"}
        
        pos = self.positions[symbole]
        perf = (prix - pos['prix']) / pos['prix'] * 100
        
        if perf >= TAKE_PROFIT_PCT:
            return {'decision': True, 'force': 0.9, 'perf': perf, 'raison': f"Take profit: +{perf:.1f}%"}
        elif perf <= STOP_LOSS_PCT:
            return {'decision': True, 'force': 0.9, 'perf': perf, 'raison': f"Stop loss: {perf:.1f}%"}
        
        return {'decision': False, 'force': 0, 'perf': perf, 'raison': f"Performance: {perf:.1f}%"}
    
    def analyser_action(self, symbole: str) -> Optional[Dict]:
        try:
            prix = self.obtenir_prix(symbole)
            if not prix:
                return None
            
            tweets = self.recuperer_tweets()
            sentiment = self.analyser_sentiment(tweets, symbole)
            
            achat = self.analyser_achat(symbole, prix, sentiment)
            vente = self.analyser_vente(symbole, prix)
            
            resultat = {
                'symbole': symbole,
                'prix': prix,
                'sentiment': sentiment,
                'timestamp': datetime.now()
            }
            
            if vente['decision']:
                resultat['decision'] = 'VENTE'
                resultat['force'] = vente['force']
                self.telegram.envoyer_alerte_vente(symbole, prix, vente['perf'])
                del self.positions[symbole]
                logger.info(f"🔴 VENTE {symbole} @ {prix:.2f}€")
                
            elif achat['decision']:
                resultat['decision'] = 'ACHAT'
                resultat['force'] = achat['force']
                self.telegram.envoyer_alerte_achat(symbole, prix, achat['force'])
                self.positions[symbole] = {'prix': prix, 'date': datetime.now()}
                logger.info(f"🟢 ACHAT {symbole} @ {prix:.2f}€")
                
            else:
                resultat['decision'] = 'ATTENDRE'
                resultat['force'] = max(achat['force'], vente['force'])
            
            logger.info(f"📊 {symbole}: {resultat['decision']} | Prix: {prix:.2f}€ | Force: {resultat['force']:.2f}")
            return resultat
            
        except Exception as e:
            logger.error(f"Erreur {symbole}: {e}")
            return None
    
    def analyser_tout(self):
        logger.info("="*50)
        logger.info(f"🔍 ANALYSE - {datetime.now().strftime('%H:%M:%S')}")
        logger.info("="*50)
        
        for symbole in ACTIONS:
            self.analyser_action(symbole)
            time.sleep(2)
        
        if self.positions:
            logger.info(f"💰 Positions ouvertes: {len(self.positions)}")
            for sym, pos in self.positions.items():
                logger.info(f"   • {sym}: acheté à {pos['prix']:.2f}€")
    
    def demarrer(self):
        logger.info("🚀 Démarrage du bot...")
        self.telegram.envoyer_demarrage()
        
        while self.running:
            try:
                self.analyser_tout()
                
                if self.running:
                    logger.info(f"⏰ Prochaine analyse dans {INTERVALLE_SECONDES//60} minutes")
                    for _ in range(INTERVALLE_SECONDES):
                        if not self.running:
                            break
                        time.sleep(1)
                        
            except Exception as e:
                logger.error(f"Erreur: {e}")
                time.sleep(60)


if __name__ == "__main__":
    bot = BotTrading()
    bot.demarrer()