"""Un bon de commande, un bon de livraison, un reliquat, une décharge n'ont
pas besoin de surface pour exister — et une démonstration se produit enfin
en fichier, quel que soit le type nommé.

**Mesuré le 21/09/2026, message du propriétaire** :

    « le vrai format n'a pas besoin de surface ou d'autres choses pour être
    créé, même s'il n'a aucune info ni prix — car c'est avec ce format qu'il
    doit créer les bons de commande, bons de livraison, décharges etc. […]
    il doit créer des démos pour qu'on puisse l'amélioration »

Deux défauts fermés ici :

1. `RELIQUAT` et `DECHARGE` n'existaient dans aucune table de reconnaissance
   — ils tombaient toujours sur DEVIS par défaut.
2. Une demande de démonstration (« exemple de bon de commande », « devis de
   démonstration ») ne contenait ni « pdf » ni « document » ni « génère le
   X » : `DEMANDE_DE_DOCUMENT` seule ne la voyait jamais, donc aucune démo ne
   produisait de fichier — la phrase restait en l'air.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from agents.plaquiste.plaquiste_agent import (
    ARTICLES_DEMONSTRATION,
    DESTINATAIRE_DEMONSTRATION,
    TYPES_SANS_CHIFFRAGE_OBLIGATOIRE,
    PlaquisteAgent,
    charger_metier,
    lignes_demonstration,
    type_document_demande,
)
from core.connectors.devis import DevisConnector
from core.connectors.registre import RegistreConnecteurs


class ModeleFixe:
    """Rend toujours la meme reponse, sans jamais lire les prompts."""

    async def generate(self, prompt: str, system_prompt: str | None = None, **kw):
        return "Compte-rendu."


@pytest.fixture(scope="module")
def metier():
    return charger_metier()


def _agent(metier: dict, dossier: Path) -> PlaquisteAgent:
    dossier.mkdir(parents=True, exist_ok=True)
    registre = RegistreConnecteurs()
    registre.declarer("devis", lambda: DevisConnector(metier=metier, dossier=dossier))
    return PlaquisteAgent(provider=ModeleFixe(), metier=metier, registre=registre)


# --- Reconnaissance du type --------------------------------------------------

@pytest.mark.parametrize("phrase, attendu", [
    ("genere le bon de commande", "BON DE COMMANDE"),
    ("génère le bon de livraison", "BON DE LIVRAISON"),
    ("genere le reliquat", "RELIQUAT"),
    ("génère la décharge", "DECHARGE"),
    ("genere la facture", "FACTURE"),
    ("genere le devis", "DEVIS"),  # jamais matché explicitement : le defaut
    ("exemple de reliquat", "RELIQUAT"),
    ("démo du bon de commande", "BON DE COMMANDE"),
    ("decharge de demonstration", "DECHARGE"),
])
def test_le_type_est_reconnu(phrase: str, attendu: str) -> None:
    assert type_document_demande(phrase) == attendu


def test_une_mention_en_passant_ne_detourne_pas_le_type() -> None:
    """La regression que la table evite deja : citer un type EN PASSANT ne
    doit jamais l'emporter sur ce qui a ete reellement demande."""
    phrase = "genere le devis, comme la facture de la semaine derniere"
    assert type_document_demande(phrase) == "DEVIS"


# --- Le connecteur : le chiffrage n'est plus obligatoire pour quatre types --

@pytest.mark.parametrize("type_document", sorted(TYPES_SANS_CHIFFRAGE_OBLIGATOIRE))
def test_un_type_sans_chiffrage_se_produit_sans_dimension(
    metier: dict, tmp_path: Path, type_document: str,
) -> None:
    connecteur = DevisConnector(metier=metier, dossier=tmp_path)
    resultat = connecteur.executer(
        "produire", demande="aucune dimension ici",
        type_document=type_document,
        client="Fast Group", lieu="Dakar", objet="Materiaux du chantier")

    assert resultat.statut.value == "SUCCESS", resultat.message
    assert Path(resultat.preuve).is_file()


@pytest.mark.parametrize("type_document", ["DEVIS", "FACTURE"])
def test_un_type_chiffre_refuse_toujours_sans_dimension(
    metier: dict, tmp_path: Path, type_document: str,
) -> None:
    """Ce que la mission protege : un prix ne s'improvise jamais."""
    connecteur = DevisConnector(metier=metier, dossier=tmp_path)
    resultat = connecteur.executer(
        "produire", demande="aucune dimension ici",
        type_document=type_document,
        client="Fast Group", lieu="Dakar", objet="Cloisons")

    assert resultat.statut.value == "FAILED"
    assert "Aucune dimension lue" in resultat.message


def test_le_type_est_normalise_avant_comparaison(metier: dict, tmp_path: Path) -> None:
    """Un appelant qui passe une casse differente ne doit pas retomber,
    par accident, sur le chemin strict des types chiffres."""
    connecteur = DevisConnector(metier=metier, dossier=tmp_path)
    resultat = connecteur.executer(
        "produire", demande="x", type_document="bon de commande",
        client="Fast Group", lieu="Dakar", objet="x")
    assert resultat.statut.value == "SUCCESS", resultat.message


# --- Les lignes de démonstration ---------------------------------------------

def test_les_lignes_de_demonstration_viennent_de_la_vraie_grille(metier: dict) -> None:
    lignes = lignes_demonstration(metier)
    grille = dict(metier.get("prix_materiaux") or {})

    assert lignes, "aucune ligne de demonstration : la grille a-t-elle change ?"
    for ligne in lignes:
        assert ligne["designation"] in grille, "un prix invente n'est jamais permis"


def test_un_seul_article_present_rend_une_seule_ligne() -> None:
    """Ce qui manque a la grille manque a l'exemple — jamais improvise a la
    place. Un seul des deux articles de reference donne UNE ligne, pas deux."""
    metier_partiel = {"prix_materiaux": {ARTICLES_DEMONSTRATION[0]: 4500}}
    lignes = lignes_demonstration(metier_partiel)
    assert [ligne["designation"] for ligne in lignes] == [ARTICLES_DEMONSTRATION[0]]


def test_aucun_article_de_reference_rend_une_liste_vide() -> None:
    """Sans aucun des deux articles connus, l'exemple reste vide plutot que
    d'improviser un troisieme article absent du fichier metier."""
    assert lignes_demonstration({"prix_materiaux": {"Un autre article": 100}}) == []


# --- Bout en bout : une démo se produit vraiment, quel que soit le type ----

@pytest.mark.parametrize("phrase", [
    "exemple de bon de commande",
    "devis de démonstration",
    "démo du reliquat",
    "exemple de décharge",
    "montre-moi un exemple de bon de livraison",
])
def test_une_demonstration_produit_reellement_un_fichier(
    metier: dict, tmp_path: Path, phrase: str,
) -> None:
    """Le défaut exact du 21/09/2026 : aucune de ces phrases ne contient
    « pdf »/« document »/« génère le X » — avant ce soir, aucune ne
    produisait rien."""
    agent = _agent(metier, tmp_path / phrase.replace(" ", "_"))

    resultat = asyncio.run(agent.run(phrase))

    document = resultat.get("document")
    assert document is not None, "la demande de demonstration n'a rien produit"
    assert document["statut"] == "SUCCESS", document
    assert Path(document["preuve"]).is_file()


def test_le_destinataire_de_demonstration_ne_nomme_plus_le_devis_specifiquement() -> None:
    """Corrige le 21/09/2026 : l'ancien texte disait « DEVIS DE
    DEMONSTRATION » meme sur un bon de commande — contradictoire avec son
    propre en-tete."""
    assert "DEVIS" not in DESTINATAIRE_DEMONSTRATION["objet"]
    assert "DEMONSTRATION" in DESTINATAIRE_DEMONSTRATION["objet"]


def test_une_demo_de_bon_de_commande_porte_le_bon_titre_sur_le_pdf(
    metier: dict, tmp_path: Path,
) -> None:
    """Preuve que le format entier — pas seulement le statut — est correct :
    le PDF relu porte « BON DE COMMANDE » et son fournisseur, pas « CLIENT »."""
    import pypdfium2 as pdfium

    agent = _agent(metier, tmp_path)
    resultat = asyncio.run(agent.run("exemple de bon de commande"))
    document = resultat["document"]

    page = pdfium.PdfDocument(document["preuve"])[0]
    texte = page.get_textpage().get_text_range()
    assert "BON DE COMMANDE" in texte
    assert "FOURNISSEUR" in texte
    assert "DEMONSTRATION" in texte
