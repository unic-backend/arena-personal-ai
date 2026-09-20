"""« Fais-moi un PDF de ça » — de la phrase au fichier téléchargeable.

Le trou, mesuré le 20/09/2026 : tous les moteurs PDF étaient disponibles
(`md -> pdf` WeasyPrint, `docx -> pdf` LibreOffice), la route
`/media/rendered/{nom:path}` savait servir le fichier, le connecteur `pdf`
savait fusionner et scinder — **mais les deux portes du connecteur de
conversion partaient d'un fichier déjà fourni par le propriétaire.** Aucune
capacité ne savait écrire un TEXTE sur le disque. « Fais-moi un PDF de ça »
n'avait donc rien à appeler, et la réponse restait à l'écran.

Ce fichier couvre la chaîne entière : le détecteur d'intention, l'écriture,
le refus, et le lien que l'interface reçoit.
"""
from __future__ import annotations

import asyncio
import zipfile
from pathlib import Path

import pytest

from apps.backend.routers.chat import (
    _joindre_document,
    _titre_du_document,
    format_de_document_demande,
)
from apps.backend.routers.pwa_gateway import _documents_produits
from core.connectors.file_conversion import TEXTE_MAX_OCTETS, ConnecteurFileConversion, _slug

TEXTE = "# Devis BA13\n\nBonjour **Saer**.\n\n| Poste | Prix |\n|---|---|\n| BA13 | 12000 |\n"


@pytest.fixture()
def connecteur(tmp_path: Path) -> ConnecteurFileConversion:
    return ConnecteurFileConversion(dossier=tmp_path)


# --- Le détecteur : fabriquer n'est pas lire --------------------------------

@pytest.mark.parametrize("phrase, attendu", [
    ("Fais-moi un PDF de ce rapport", "pdf"),
    ("génère un pdf du devis", "pdf"),
    ("Mets ça en PDF", "pdf"),
    ("prépare-moi un devis au format pdf", "pdf"),
    ("écris-moi ce résumé en word", "docx"),
    ("donne-moi ça en markdown", "md"),
    ("génère-moi ça en excel", "xlsx"),
])
def test_une_demande_de_fichier_est_reconnue(phrase: str, attendu: str) -> None:
    assert format_de_document_demande(phrase) == attendu


@pytest.mark.parametrize("phrase", [
    "Résume-moi ce PDF",
    "d'après le document, quel est le prix ?",
    "le pdf que tu m'as envoyé hier",
    "Analyse ce fichier pdf",
    "lis le pdf et fais un résumé",
    "Bonjour, ça va ?",
    "",
    # Les deux phrases qui font vivre les deux gardes. Sans elles, un
    # sabotage retirant l'une ou l'autre ne faisait echouer AUCUN test
    # (mesure du 20/09/2026) — et un garde qu'aucun sabotage ne fait tomber
    # est une branche morte, pas une precaution.
    #
    # Ici, un verbe de production ET un format nomme — mais « ce fichier »
    # dit que le PDF est la SOURCE, pas ce qu'on demande.
    "fais-moi un résumé de ce fichier pdf",
    # Ici, un format nomme et aucun verbe : rien n'est demande.
    "un pdf serait bien",
])
def test_lire_un_document_n_en_fabrique_jamais_un(phrase: str) -> None:
    """Le doute profite à la lecture.

    Sans cette règle, chaque question posée SUR un PDF reçu en fabriquerait
    un nouveau — `media/rendered/` se remplirait de documents que personne
    n'a demandés, et la réponse mentirait en annonçant un fichier.
    """
    assert format_de_document_demande(phrase) is None


# --- L'écriture : un fichier réel, relu -------------------------------------

def test_le_pdf_est_un_vrai_pdf(connecteur: ConnecteurFileConversion) -> None:
    resultat = connecteur._rediger(TEXTE, "pdf", "Devis BA13")

    assert resultat.statut.value == "SUCCESS"
    fichier = Path(resultat.preuve)
    assert fichier.is_file()
    # Relu comme un lecteur le lirait, pas cru sur le code de retour.
    assert fichier.read_bytes()[:5] == b"%PDF-"
    assert fichier.stat().st_size > 1000


def test_le_docx_contient_vraiment_le_texte(connecteur: ConnecteurFileConversion) -> None:
    """`html -> docx` a été branché pour que « en Word » ait un chemin.

    Un DOCX qui s'ouvre mais ne contient pas le texte serait un succès faux :
    on va chercher les mots dans le XML du document.
    """
    resultat = connecteur._rediger(TEXTE, "docx", "Devis BA13")
    assert resultat.statut.value == "SUCCESS"

    xml = zipfile.ZipFile(resultat.preuve).read("word/document.xml").decode("utf-8")
    assert "Devis BA13" in xml
    assert "Saer" in xml
    assert "12000" in xml  # le tableau markdown a survécu au passage


@pytest.mark.parametrize("format_cible", ["md", "txt", "html"])
def test_un_format_texte_s_ecrit_tel_quel(
    connecteur: ConnecteurFileConversion, format_cible: str,
) -> None:
    resultat = connecteur._rediger(TEXTE, format_cible, "Devis")
    assert resultat.statut.value == "SUCCESS"
    assert Path(resultat.preuve).read_text(encoding="utf-8") == TEXTE
    assert resultat.detail["moteur"] == "ecriture_directe"


def test_un_document_texte_tronque_a_l_ecriture_est_refuse(
    connecteur: ConnecteurFileConversion, tmp_path: Path, monkeypatch,
) -> None:
    """Un disque plein écrit un fichier tronqué **sans lever**.

    Le fichier est donc relu avant tout succès. Sans cette relecture, un
    document amputé se téléchargerait normalement — pire qu'un échec, parce
    que personne ne le remarque.
    """
    vrai_read = Path.read_text

    def read_tronque(self, *args, **kwargs):
        texte = vrai_read(self, *args, **kwargs)
        return texte[: len(texte) // 2] if self.suffix == ".md" else texte

    monkeypatch.setattr(Path, "read_text", read_tronque)
    resultat = connecteur._rediger(TEXTE, "md", "Devis")

    assert resultat.statut.value == "FAILED"
    assert "relu différent" in resultat.message
    # Le fichier douteux ne reste pas a portee de telechargement.
    assert not list(tmp_path.rglob("*.md"))


def test_un_texte_vide_ne_produit_aucun_fichier(
    connecteur: ConnecteurFileConversion, tmp_path: Path,
) -> None:
    """Un PDF d'une page blanche est un échec déguisé en succès."""
    resultat = connecteur._rediger("   \n  ", "pdf", "Vide")

    assert resultat.statut.value == "FAILED"
    assert not list(tmp_path.rglob("*.pdf"))


def test_un_texte_demesure_est_refuse(connecteur: ConnecteurFileConversion) -> None:
    resultat = connecteur._rediger("a" * (TEXTE_MAX_OCTETS + 1), "pdf", "Trop")
    assert resultat.statut.value == "FAILED"
    assert "plafond" in resultat.message


def test_un_format_sans_moteur_le_dit_sans_rien_ecrire(
    connecteur: ConnecteurFileConversion, tmp_path: Path,
) -> None:
    """`NOT_IMPLEMENTED`, jamais un fichier plausible — et rien sur le disque."""
    resultat = connecteur._rediger(TEXTE, "xlsx", "Devis")

    assert resultat.statut.value == "NOT_IMPLEMENTED"
    assert not list(tmp_path.rglob("*"))


def test_aucun_brouillon_ne_survit_a_la_conversion(
    connecteur: ConnecteurFileConversion, tmp_path: Path,
) -> None:
    """Ce qui se télécharge est le document, jamais le markdown intermédiaire."""
    connecteur._rediger(TEXTE, "pdf", "Devis")

    restes = [p for p in tmp_path.rglob("*") if p.name.startswith(".brouillon-")]
    assert restes == []
    assert [p.suffix for p in tmp_path.rglob("*") if p.is_file()] == [".pdf"]


def test_deux_documents_du_meme_titre_ne_s_ecrasent_pas(
    connecteur: ConnecteurFileConversion,
) -> None:
    premier = connecteur._rediger(TEXTE, "pdf", "Devis")
    second = connecteur._rediger(TEXTE, "pdf", "Devis")

    assert premier.preuve != second.preuve
    assert Path(premier.preuve).is_file() and Path(second.preuve).is_file()


@pytest.mark.parametrize("titre, attendu", [
    ("Rapport de chantier", "rapport-de-chantier"),
    ("Résumé du café", "resume-du-cafe"),
    ("  ///  ", "document"),
    (None, "document"),
    ("a" * 200, "a" * 60),
])
def test_le_nom_du_fichier_reste_lisible_sur_un_telephone(titre, attendu: str) -> None:
    """Un accent dans un nom de fichier téléchargé devient du mojibake selon
    le téléphone qui le reçoit — et un document illisible dans la liste des
    téléchargements est un document perdu."""
    assert _slug(titre) == attendu


# --- Le lien : ce que l'interface reçoit ------------------------------------

def test_l_url_rendue_est_servie_par_la_route_des_medias(
    connecteur: ConnecteurFileConversion, tmp_path: Path,
) -> None:
    from apps.backend.config import RENDERED_DIR

    connecteur.dossier = RENDERED_DIR / "conversions"
    try:
        resultat = connecteur._rediger(TEXTE, "md", "Devis")
        assert resultat.detail["url"].startswith("/media/rendered/conversions/")
        assert resultat.detail["url"].endswith(Path(resultat.preuve).name)
    finally:
        Path(resultat.preuve).unlink(missing_ok=True)


def test_la_reponse_passe_meme_quand_le_document_echoue() -> None:
    """Un échec d'écriture n'efface pas ce qui a été répondu — il s'ajoute."""
    reponse = asyncio.run(_joindre_document(
        "génère-moi ça en excel", {"response": TEXTE, "status": "success"}))

    assert TEXTE in reponse["response"]
    assert "non produit" in reponse["response"]
    assert reponse["document_echec"]
    # Un échec n'offre aucun fichier à ouvrir.
    assert _documents_produits(reponse) == []


def test_une_phrase_sans_demande_ne_touche_pas_la_reponse() -> None:
    origine = {"response": TEXTE, "status": "success"}
    reponse = asyncio.run(_joindre_document("résume-moi ce pdf", dict(origine)))

    assert reponse["response"] == origine["response"]
    assert "document" not in reponse


def test_une_reponse_vide_n_est_pas_sauvee_par_un_fichier_vide() -> None:
    reponse = asyncio.run(_joindre_document("fais-moi un pdf", {"response": "  "}))
    assert "document" not in reponse


def test_le_lien_atteint_l_interface_par_le_canal_existant() -> None:
    """`_documents_produits` est le canal par lequel le devis PDF arrive déjà
    sur le téléphone. En ouvrir un second demanderait à l'interface
    d'apprendre deux fois la même chose."""
    reponse = asyncio.run(_joindre_document(
        "fais-moi un pdf du devis", {"response": TEXTE, "status": "success"}))

    offerts = _documents_produits(reponse)
    assert len(offerts) == 1
    assert offerts[0]["url"].startswith("/media/rendered/")
    assert offerts[0]["url"].endswith(".pdf")
    # La cle n'est PAS dans l'URL : l'interface l'ajoute au clic. Une cle
    # ecrite ici serait recopiee dans la memoire de conversation.
    assert "cle=" not in offerts[0]["url"]

    Path(reponse["document"]["nom"])  # le nom est exploitable tel quel
    fichier = Path("media/rendered/conversions") / reponse["document"]["nom"]
    if fichier.is_file():
        fichier.unlink()


@pytest.mark.parametrize("texte, demande, attendu", [
    ("# Rapport de chantier\n\ncorps", "fais un pdf", "Rapport de chantier"),
    ("pas de titre ici", "fais-moi un pdf du devis", "fais-moi un pdf du devis"),
    ("", "", "document"),
])
def test_le_titre_vient_de_la_reponse_avant_la_demande(
    texte: str, demande: str, attendu: str,
) -> None:
    assert _titre_du_document(texte, demande) == attendu
