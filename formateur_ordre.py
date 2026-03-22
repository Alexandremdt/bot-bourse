from cerveau_strategie import CerveauStrategie
from formateur_ordre import FormateurOrdre, GenerateurMessageTelegram

# Initialisation
cerveau = CerveauStrategie()
formateur = FormateurOrdre()
generateur = GenerateurMessageTelegram()

# Analyser une action
analyse = cerveau.analyser_action("AI.PA")

# Si décision d'achat/vente, formater l'ordre
if analyse['decision'] in ['ACHAT', 'VENTE']:
    ordre = formateur.formater_ordre(
        symbole=analyse['symbole'],
        decision=analyse['decision'],
        prix_actuel=analyse['prix_actuel'],
        type_ordre="cours_limite",
        compte="comptant",
        quantite=10,
        prix_limite=analyse['prix_actuel'] * 0.98,  # 2% en dessous
        strategie="take_profit" if analyse['decision'] == 'ACHAT' else "stop_loss",
        seuil_strategie=analyse['prix_actuel'] * (1.10 if analyse['decision'] == 'ACHAT' else 0.97)
    )
    
    # Générer le message Telegram
    message = generateur.generer_message_complet(ordre)
    print(message)