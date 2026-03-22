"""
BOT TRADING - Version pour GitHub Actions
S'exécute selon le schedule défini dans .github/workflows
"""

import os
import sys
import requests
import json
import logging
from datetime import datetime
from typing import Optional, List, Dict

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration depuis les secrets GitHub
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '')
CHAT_ID = os.environ.get('CHAT_ID', '')

# Actions à surveiller
ACTIONS = ["AI.PA", "TTE.PA", "MC.PA", "BNP.PA", "OR.PA"]

# Seuils d'achat personnalisés
SEUILS_ACHAT = {
    "AI.PA": 170.0,   # Air Liquide
    "TTE.PA": 80.0,   # TotalEnergies
    "MC.PA": 800.0,   # LVMH
    "BNP.PA": 65.0,   # BNP Paribas
    "OR.PA": 450.0,   # L'Oréal
    "default": 150.0
}

# Seuils de vente (prise de profit)
PRISE_PROFIT_PCT = 10.0  # +10%

# Stop loss
STOP_LOSS_PCT = -3.0  # -3%


def get_price(symbol: str) -> Optional[float]:
    """Récupère le prix actuel d'une action"""
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        data = ticker.history(period="1d")
        if not data.empty:
            return round(data['Close'].iloc[-1], 2)
        return None
    except Exception as e:
        logger.error(f"Erreur prix {symbol}: {e}")
        return None


def send_telegram(message: str) -> bool:
    """Envoie un message sur Telegram"""
    if not TELEGRAM_TOKEN or not CHAT_ID:
        logger.error("Telegram non configuré")
        return False
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        }
        response = requests.post(url, data=data, timeout=30)
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Erreur envoi: {e}")
        return False


def verifier_heure_marche() -> bool:
    """Vérifie si on est dans les heures de marché"""
    now = datetime.now()
    
    # Weekend ?
    if now.weekday() >= 5:
        return False
    
    # Heures de marché (09:00 - 17:30)
    heure = now.hour
    minute = now.minute
    
    if heure < 9:
        return False
    if heure > 17:
        return False
    if heure == 17 and minute > 30:
        return False
    
    return True


def analyser_action(symbole: str) -> Dict:
    """Analyse une action"""
    resultat = {
        'symbole': symbole,
        'timestamp': datetime.now().isoformat(),
        'decision': 'ATTENDRE'
    }
    
    try:
        prix = get_price(symbole)
        if prix is None:
            resultat['decision'] = 'ERREUR'
            resultat['message'] = "Prix non disponible"
            return resultat
        
        resultat['prix'] = prix
        
        seuil = SEUILS_ACHAT.get(symbole, SEUILS_ACHAT['default'])
        
        # Logique d'achat simple
        if prix < seuil:
            resultat['decision'] = 'ACHAT'
            resultat['message'] = f"Prix bas: {prix:.2f}€ < {seuil:.2f}€"
        elif prix > seuil * 1.10:  # +10%
            resultat['decision'] = 'VENTE_PROFIT'
            resultat['message'] = f"Prise de profit: +{(prix/seuil - 1)*100:.1f}%"
        else:
            resultat['decision'] = 'ATTENDRE'
            resultat['message'] = f"Prix: {prix:.2f}€ (seuil: {seuil:.2f}€)"
        
        return resultat
        
    except Exception as e:
        logger.error(f"Erreur analyse {symbole}: {e}")
        resultat['decision'] = 'ERREUR'
        resultat['message'] = str(e)
        return resultat


def envoyer_alerte_achat(symbole: str, prix: float, seuil: float):
    """Envoie une alerte d'achat"""
    message = (
        "🟢 *ALERTE ACHAT* 🟢\n\n"
        f"*{symbole}*\n"
        f"💰 Prix actuel: **{prix:.2f} €**\n"
        f"🎯 Seuil d'achat: {seuil:.2f} €\n"
        f"📉 Potentiel: +{((seuil - prix) / prix * 100):.1f}%\n\n"
        "👉 *Action*: Passer un ordre d'achat sur Bourse Direct\n"
        f"   • Quantité suggérée: 10 actions\n"
        f"   • Prix limite: {prix:.2f} €"
    )
    send_telegram(message)


def envoyer_alerte_vente(symbole: str, prix: float, seuil: float, perf: float):
    """Envoie une alerte de vente"""
    message = (
        "🔴 *ALERTE VENTE* 🔴\n\n"
        f"*{symbole}*\n"
        f"💰 Prix actuel: **{prix:.2f} €**\n"
        f"🎯 Prix d'achat: {seuil:.2f} €\n"
        f"📈 Performance: **+{perf:.1f}%**\n\n"
        "👉 *Action*: Passer un ordre de vente sur Bourse Direct\n"
        f"   • Quantité suggérée: 10 actions\n"
        f"   • Type: Au marché"
    )
    send_telegram(message)


def main():
    """Fonction principale exécutée par GitHub Actions"""
    
    # Vérifier les horaires de marché
    if not verifier_heure_marche():
        logger.info("⏸️ En dehors des heures de marché (09:00-17:30 lun-ven)")
        return
    
    # Vérifier la configuration
    if not TELEGRAM_TOKEN or TELEGRAM_TOKEN == "VOTRE_TOKEN_TELEGRAM":
        logger.error("❌ Token Telegram non configuré")
        logger.error("   Configurez les secrets GitHub: TELEGRAM_TOKEN et CHAT_ID")
        return
    
    logger.info(f"🤖 Début analyse - {datetime.now().strftime('%H:%M:%S')}")
    logger.info(f"📊 Actions: {', '.join(ACTIONS)}")
    
    # Analyser chaque action
    alertes = []
    for symbole in ACTIONS:
        logger.info(f"🔍 Analyse {symbole}...")
        resultat = analyser_action(symbole)
        
        if resultat['decision'] == 'ACHAT':
            logger.info(f"   ✅ ACHAT: {symbole} @ {resultat['prix']:.2f}€")
            envoyer_alerte_achat(
                symbole,
                resultat['prix'],
                SEUILS_ACHAT.get(symbole, SEUILS_ACHAT['default'])
            )
            alertes.append(resultat)
            
        elif resultat['decision'] == 'VENTE_PROFIT':
            prix_achat = SEUILS_ACHAT.get(symbole, SEUILS_ACHAT['default'])
            perf = (resultat['prix'] - prix_achat) / prix_achat * 100
            logger.info(f"   ✅ VENTE: {symbole} @ {resultat['prix']:.2f}€ (+{perf:.1f}%)")
            envoyer_alerte_vente(symbole, resultat['prix'], prix_achat, perf)
            alertes.append(resultat)
            
        else:
            logger.info(f"   ⚪ ATTENDRE: {symbole} @ {resultat['prix']:.2f}€")
    
    # Rapport
    if alertes:
        logger.info(f"📱 {len(alertes)} alerte(s) envoyée(s)")
    else:
        logger.info("📱 Aucune alerte envoyée")
    
    logger.info("✅ Fin analyse")


if __name__ == "__main__":
    main()
