"""Un devis sort du générateur, ou il n'existe pas.

**Mesuré le 20/09/2026, capture d'écran du propriétaire.** Le vrai générateur
avait refusé — « Aucune dimension lue dans la demande : je ne chiffre rien » —
et la réponse affichait quand même un devis complet : en-tête, tableau,
sous-total, TOTAL TTC, conditions générales, signature du gérant, et un numéro
« UC-2026-0920-KHADI ».

Ce numéro est la preuve que rien n'est sorti du générateur : le code rend
« UC-2026-0920-KD » pour Khady Diop, et la chaîne « KHADI » n'existe nulle part
dans le dépôt. Le modèle avait tout écrit, sans le logo, sans la charte, sans
la mise en page. Le propriétaire a vu un devis qui ne ressemblait pas au sien,
sans pouvoir savoir pourquoi.

*Note : les prix de cette capture avaient été dictés par le propriétaire pour
un test. Ce fichier ne parle donc pas de prix inventés — il parle d'un
DOCUMENT inventé.*
"""
from __future__ import annotations

import pytest

from agents.plaquiste.plaquiste_agent import (
    REFUS_DE_FAUX_DOCUMENT,
    _sans_faux_document,
    ressemble_a_un_document,
    suffixe_du_client,
)

#: La réponse reçue sur son téléphone, réduite à ce qui compte.
CAPTURE = """UniC Plaquiste – Devis
Date : 20 septembre 2026
Référence : UC-2026-0920-KHADI

Client : Khady Diop
Lieu du chantier : Dakar

Désignation            Quantité   Prix unitaire   Montant
Plaque standard BA13   20         4 500           90 000
Sous-total matériaux   –          –               110 500
TOTAL TTC              –          –               210 500
"""


def test_le_numero_de_la_capture_ne_vient_pas_du_code() -> None:
    """La preuve que le document était écrit par le modèle.

    Si un jour `suffixe_du_client` rendait « KHADI », ce test tomberait — et
    il faudrait alors rouvrir la question, parce que toute l'analyse repose
    sur cet écart.
    """
    assert suffixe_du_client("Khady Diop") == "KD"
    assert suffixe_du_client("Khady Diop") != "KHADI"


@pytest.mark.parametrize("texte", [
    CAPTURE,
    "Référence : UC-2026-0920-KD",
    "TOTAL TTC : 210 500 FCFA",
    "Sous-total matériaux : 110 500",
    "Total général : 90 000 FCFA",
])
def test_ce_qui_se_fait_passer_pour_un_document_est_reconnu(texte: str) -> None:
    assert ressemble_a_un_document(texte)


@pytest.mark.parametrize("texte", [
    "Pour 18 parois de 5,40 x 2,50 m, il te faut environ 234 plaques.",
    "La plaque standard BA13 est à 4 500 FCFA l'unité.",
    "Il me manque le lieu du chantier.",
    "",
])
def test_une_reponse_ordinaire_n_est_jamais_touchee(texte: str) -> None:
    """Expliquer un chiffrage en phrases reste permis — c'est même le travail.

    Ce qui est interdit, c'est d'imiter le DOCUMENT : son numéro, ses totaux.
    """
    assert not ressemble_a_un_document(texte)
    assert _sans_faux_document(texte, None) == texte


def test_sans_fichier_ecrit_le_faux_devis_est_remplace() -> None:
    remplacee = _sans_faux_document(CAPTURE, None)

    assert remplacee == REFUS_DE_FAUX_DOCUMENT
    assert "UC-2026-0920-KHADI" not in remplacee
    assert "TOTAL TTC" not in remplacee
    # Et le remplacement DIT ce qui manque, au lieu de refuser sèchement.
    assert "dimensions" in remplacee


@pytest.mark.parametrize("document", [
    None,
    {"statut": "INCOMPLET", "manquants": ["client"]},
    {"statut": "FAILED", "message": "moteur absent"},
    {"statut": "NOT_CONFIGURED"},
])
def test_tant_qu_aucun_fichier_n_existe_le_garde_tient(document) -> None:
    """`INCOMPLET` et `FAILED` n'ont produit aucun fichier : un devis écrit
    à côté reste un faux."""
    assert _sans_faux_document(CAPTURE, document) == REFUS_DE_FAUX_DOCUMENT


@pytest.mark.parametrize("statut", ["SUCCESS", "PARTIAL"])
def test_quand_le_document_existe_la_reponse_passe_telle_quelle(statut: str) -> None:
    """Le fichier existe, il porte son vrai numéro, son lien suit juste en
    dessous : la réponse peut en parler librement."""
    document = {"statut": statut, "url": "/media/rendered/devis.pdf"}

    assert _sans_faux_document(CAPTURE, document) == CAPTURE


def test_le_garde_est_atteint_par_run(monkeypatch) -> None:
    """Le garde doit être BRANCHÉ, pas seulement exister.

    Un sabotage retirant l'appel dans `run()` ne faisait échouer aucun test
    (mesuré le 20/09/2026) : ils appelaient tous la fonction en direct. C'est
    la troisième fois de la journée que la batterie trouve un branchement non
    couvert — le défaut serait revenu sans un bruit.
    """
    import asyncio

    from agents.plaquiste.plaquiste_agent import PlaquisteAgent, charger_metier

    class ModeleQuiEcritUnFauxDevis:
        async def generate(self, prompt, system_prompt=None, **kw):
            return CAPTURE

    agent = PlaquisteAgent(provider=ModeleQuiEcritUnFauxDevis(),
                           metier=charger_metier())
    resultat = asyncio.run(agent.run("fais-moi un devis pour Khady Diop a Dakar"))

    assert "UC-2026-0920-KHADI" not in resultat["response"]
    assert "TOTAL TTC" not in resultat["response"]
    assert "dimensions" in resultat["response"]


def test_l_instruction_interdit_aussi_au_modele_de_l_ecrire() -> None:
    """Le garde rattrape ; l'instruction évite. Les deux, pas l'un ou l'autre.

    Un garde seul laisserait le modèle produire le faux à chaque tour, et le
    propriétaire verrait un refus là où il attend un devis.
    """
    from agents.plaquiste.plaquiste_agent import charger_metier, composer_instruction

    instruction = composer_instruction(charger_metier())

    assert "TU N'ECRIS JAMAIS LE DOCUMENT LUI-MEME" in instruction
    assert "TOTAL TTC" in instruction
