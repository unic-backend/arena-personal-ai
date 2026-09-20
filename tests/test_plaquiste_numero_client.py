"""Le numéro d'un document porte les initiales du client.

**La règle du propriétaire, donnée le 20/09/2026** : « UC-2026-0714-FG, le FG
est le nom de Fast Group ; tout autre client aussi doit avoir celle de son nom
et prénom à la fin du numéro pour qu'il soit facile à identifier. Ceci est
valable sur tous les fichiers : devis, bon, reliquat, etc. »

Avant ce fichier, `Devis.suffixe_client` valait `XXX` et **rien ne le
calculait** — aucun appelant ne le passait. Mesuré sur un devis réel le même
jour : `UC-2026-0920-XXX`, sur un document qui nommait Fast Group deux lignes
plus bas.

Couvre aussi les quatre défauts de format mesurés sur ce même rendu : accents
absents, texte qui déborde d'une colonne, devise manquante, et la mention des
prix unitaires présente dans `config/metier.yaml` mais rendue nulle part.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from agents.plaquiste.devis_pdf import Devis, Ligne, construire
from agents.plaquiste.plaquiste_agent import (
    SUFFIXE_INCONNU,
    charger_metier,
    numero_du_jour,
    suffixe_du_client,
)


@pytest.fixture(scope="module")
def metier() -> dict:
    return charger_metier()


def _texte_du_pdf(chemin: Path) -> str:
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(str(chemin))
    return "\n".join(
        document[i].get_textpage().get_text_range() for i in range(len(document)))


# --- Les initiales ----------------------------------------------------------

@pytest.mark.parametrize("client, attendu", [
    ("Fast Group", "FG"),              # son exemple, mot pour mot
    ("fast group", "FG"),              # la casse ne decide de rien
    ("Ousmane Diop", "OD"),
    # Ses deux exemples du 20/09/2026, quand il a verifie que « FG » n'etait
    # pas ecrit en dur : « si le client s'appelle Mbaye Ndiaye son numero de
    # devis serait MN, si c'est Pape Diop la fin c'est PD ».
    ("Mbaye Ndiaye", "MN"),
    ("Pape Diop", "PD"),
    ("Jean-Pierre Ndiaye", "JPN"),     # le trait d'union separe deux prenoms
    ("Aïssatou Ndèye Fall", "ANF"),
    ("Sonatel", "SON"),                # un seul mot : trois lettres, pas une
    ("Fatou", "FAT"),
    ("Entreprise Générale de Bâtiment du Sénégal", "EGB"),  # plafonne a trois
])
def test_les_initiales_viennent_du_nom_du_client(client: str, attendu: str) -> None:
    assert suffixe_du_client(client) == attendu


@pytest.mark.parametrize("client", ["", "   ", None, "///", "—"])
def test_sans_nom_exploitable_le_trou_reste_visible(client) -> None:
    """`XXX` n'est pas un identifiant : c'est une case vide qui se remarque.

    Inventer des initiales à partir de rien mettrait un faux identifiant sur
    un document qui part chez quelqu'un — pire qu'un trou, parce que personne
    ne le corrigerait.
    """
    assert suffixe_du_client(client) == SUFFIXE_INCONNU


def test_le_numero_complet_suit_sa_convention() -> None:
    assert numero_du_jour(date(2026, 7, 14), "FG") == "UC-2026-0714-FG"


# --- La règle vaut pour TOUS les types de document --------------------------

@pytest.mark.parametrize("type_document", [
    "DEVIS", "FACTURE", "BON DE COMMANDE", "BON DE LIVRAISON", "RELIQUAT", "DECHARGE",
])
def test_chaque_type_de_document_porte_les_initiales(type_document: str) -> None:
    """« Ceci est valable sur toutes les fichiers », dit-il.

    La déduction vit dans `Devis.__post_init__`, par où les six types passent —
    donc aucun appelant ne peut l'oublier pour l'un d'eux.
    """
    devis = Devis(client="Fast Group", lieu="Dakar", objet="x",
                  type_document=type_document)
    assert devis.numero.endswith("-FG")
    assert devis.suffixe_client == "FG"


def test_deux_clients_differents_n_ont_jamais_le_meme_suffixe() -> None:
    """Le suffixe SUIT le client — il n'est pas une constante de la maison.

    C'est la question qu'il a posee le 20/09/2026 : « j'espere que tu ne l'as
    pas fait pour qu'a chaque devis le numero ecrive FG a la fin ». Ce test
    echoue si quelqu'un fige un suffixe, quel qu'il soit.
    """
    numeros = {c: Devis(client=c, lieu="Dakar", objet="x").numero
               for c in ("Mbaye Ndiaye", "Pape Diop", "Fast Group", "Aminata Sow")}

    assert numeros["Mbaye Ndiaye"].endswith("-MN")
    assert numeros["Pape Diop"].endswith("-PD")
    assert numeros["Fast Group"].endswith("-FG")
    # Quatre clients, quatre fins differentes.
    assert len({n.rsplit("-", 1)[1] for n in numeros.values()}) == 4


def test_un_suffixe_donne_explicitement_gagne_toujours() -> None:
    """Ses variantes existent : FGP pour les portes, FGM pour la main-d'œuvre.

    Déduire par-dessus une valeur choisie les rendrait impossibles à écrire.
    """
    devis = Devis(client="Fast Group", lieu="Dakar", objet="x", suffixe_client="FGP")
    assert devis.numero.endswith("-FGP")


def test_un_numero_donne_n_est_jamais_recalcule() -> None:
    devis = Devis(client="Fast Group", lieu="Dakar", objet="x",
                  numero="UC-2026-0714-FG")
    assert devis.numero == "UC-2026-0714-FG"


# --- Le document rendu ------------------------------------------------------

def test_le_pdf_porte_le_numero_du_client(metier: dict, tmp_path: Path) -> None:
    sortie = tmp_path / "devis.pdf"
    construire(Devis(client="Fast Group", lieu="Diamniadio, Dakar",
                     objet="Pose de 18 parois BA13.",
                     lignes=[Ligne("Plaque standard BA13", 234)]), metier, sortie)

    texte = _texte_du_pdf(sortie)
    assert "-FG" in texte
    assert "XXX" not in texte


def test_les_libelles_du_document_sont_accentues(metier: dict, tmp_path: Path) -> None:
    """Un devis qui part chez un client écrit « Désignation », pas « Designation ».

    Mesuré le 20/09/2026 : le rendu sortait « Specialiste », « Senegal »,
    « Validite », « Materiaux », « Designation », « Quantite ».
    """
    sortie = tmp_path / "devis.pdf"
    construire(Devis(client="Fast Group", lieu="Dakar", objet="Pose BA13.",
                     lignes=[Ligne("Plaque standard BA13", 10)]), metier, sortie)

    texte = _texte_du_pdf(sortie)
    for attendu in ("Désignation", "Quantité", "Matériaux", "Validité",
                    "Spécialiste", "Sénégal", "Rénovation", "Gérant"):
        assert attendu in texte, attendu
    for interdit in ("Designation", "Quantite", "Validite", "Specialiste"):
        assert interdit not in texte, interdit


def test_la_devise_accompagne_chaque_prix_unitaire(metier: dict, tmp_path: Path) -> None:
    """« 4 500 FCFA », comme sur son devis Fast Group — pas « 4 500 »."""
    sortie = tmp_path / "devis.pdf"
    construire(Devis(client="Fast Group", lieu="Dakar", objet="Pose BA13.",
                     lignes=[Ligne("Plaque standard BA13", 10)]), metier, sortie)

    assert "4 500 FCFA" in _texte_du_pdf(sortie)


def test_la_mention_des_prix_unitaires_est_rendue(metier: dict, tmp_path: Path) -> None:
    """Elle était dans `config/metier.yaml` et sur aucun document.

    Elle existe pour qu'un client ne lise pas 4 500 FCFA comme le prix des 234
    plaques — un malentendu qui se règle après signature, donc mal.
    """
    sortie = tmp_path / "devis.pdf"
    construire(Devis(client="Fast Group", lieu="Dakar", objet="Pose BA13.",
                     lignes=[Ligne("Plaque standard BA13", 10)]), metier, sortie)

    texte = _texte_du_pdf(sortie)
    assert "Prix unitaires" in texte
    assert "ne sont pas des montants totaux" in texte or "non des montants totaux" in texte


def test_un_libelle_long_ne_recouvre_pas_les_colonnes_voisines(
    metier: dict, tmp_path: Path,
) -> None:
    """Le libellé de main-d'œuvre écrasait le prix au m² ET la surface.

    Un texte posé en chaîne brute dans une cellule ReportLab ne se coupe pas :
    il déborde. Un Paragraphe revient à la ligne dans sa colonne. On vérifie
    que les trois valeurs sont bien là, chacune lisible.
    """
    sortie = tmp_path / "devis.pdf"
    construire(Devis(client="Fast Group", lieu="Dakar", objet="Pose BA13.",
                     lignes=[Ligne("Plaque standard BA13", 10)],
                     main_oeuvre_m2=486.0), metier, sortie)

    import pypdfium2 as pdfium

    page = pdfium.PdfDocument(str(sortie))[0]
    page_texte = page.get_textpage()
    texte = page_texte.get_text_range()
    assert "5 000 FCFA/m²" in texte and "486 m²" in texte

    # La preuve n'est pas dans le texte — un libelle qui deborde reste lisible
    # a l'extraction, il RECOUVRE seulement ses voisins a l'ecran. Un sabotage
    # remettant la chaine brute ne faisait donc echouer aucun test (mesure du
    # 20/09/2026). On lit les positions reelles des caracteres.
    debut = texte.find("peinture")
    assert debut != -1, "le libelle de main-d'œuvre n'est pas dans le document"
    bord_droit = max(page_texte.get_charbox(i)[2]
                     for i in range(debut, debut + len("peinture")))

    # Colonne 1 : marge gauche 15 mm + largeur 78 mm, en points PDF.
    LIMITE_COLONNE_PT = (15 + 78) * 72 / 25.4
    assert bord_droit < LIMITE_COLONNE_PT, (
        f"le libelle sort de sa colonne : {bord_droit:.0f} pt > {LIMITE_COLONNE_PT:.0f} pt")


# --- La grille de prix n'a pas bougé ----------------------------------------

def test_le_renommage_des_articles_n_a_change_aucun_prix(metier: dict) -> None:
    """Les noms d'articles ont été accentués dans `config/metier.yaml`.

    Ils servent AUSSI de références croisées dans `ratios_materiaux` : les
    renommer d'un seul côté casserait silencieusement le calcul. Ce total est
    celui mesuré avant le renommage, sur le chantier de référence des 18
    parois — 3 298 000 FCFA, 12 articles, aucun sans prix.
    """
    from agents.plaquiste.calcul_materiaux import quantites_pour

    resultat = quantites_pour(243.0, metier, faces=2, parois=18)

    assert resultat.total_connu == 3_298_000
    assert len(resultat.besoins) == 12
    assert resultat.articles_sans_prix == []


def test_un_article_hors_grille_reste_refuse(metier: dict) -> None:
    """L'accent ne doit pas devenir une porte ouverte : un article inconnu
    n'a toujours pas de prix, et il est nommé."""
    ligne = Ligne("Plaque en or massif", 3)
    assert ligne.chiffrer(dict(metier.get("prix_materiaux") or {})) == (None, None)
