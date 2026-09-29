"""« Convertis ce fichier en Word » (DEC-0177) : une piece jointe envoyee du
telephone, convertie par le connecteur — relue, jamais inventee."""
from pathlib import Path

import pytest

from agents.orchestrator.orchestrator_agent import OrchestratorAgent
from apps.backend.config import RENDERED_DIR
from apps.backend.pieces_jointes import DepotPiecesJointes
from apps.backend.routers import chat as module_chat
from apps.backend.routers.pwa_gateway import _documents_produits
from core.production.conversion.demande import format_de_conversion


@pytest.fixture()
def depot(monkeypatch) -> DepotPiecesJointes:
    """Un depot neuf, branche la ou le chat le lit."""
    neuf = DepotPiecesJointes()
    monkeypatch.setattr(module_chat, "pieces_jointes", neuf)
    return neuf


def _word(texte: str) -> bytes:
    import io

    from docx import Document

    document = Document()
    document.add_paragraph(texte)
    flux = io.BytesIO()
    document.save(flux)
    return flux.getvalue()


# --- La phrase ------------------------------------------------------------------

@pytest.mark.parametrize("phrase, attendu", [
    ("Convertis ce PDF en Word", "docx"),
    ("transforme ce fichier en PDF stp", "pdf"),
    ("Jarvis, mets cette présentation au format PDF", "pdf"),
    ("convertis la pièce jointe vers Excel", "xlsx"),
    ("passe ces documents en texte", "txt"),
    ("convertis cette photo en png", "png"),
])
def test_ces_phrases_demandent_une_conversion(phrase, attendu):
    assert format_de_conversion(phrase) == attendu
    assert OrchestratorAgent.demande_de_conversion(phrase) is True


@pytest.mark.parametrize("phrase", [
    "fais-moi un PDF de ça",                # une redaction : la REPONSE en fichier
    "résume ce PDF",                         # une lecture
    "convertis 100 dollars en francs",       # pas un fichier
    "ce fichier est en PDF ?",               # une question
    "convertis ce fichier",                  # aucun format : rien a deviner
    "mets ce fichier en ordre",              # « ordre » n'est pas un format
    "transforme ta réponse en Word",         # la REPONSE : redaction, pas conversion
    "convertis ça en pdf",                   # « ça » ne designe pas un fichier envoye
])
def test_ces_phrases_ne_demandent_pas_de_conversion(phrase):
    assert format_de_conversion(phrase) is None


async def test_la_conversion_passe_avant_le_controle_date(provider_factory):
    orchestrateur = OrchestratorAgent(provider=provider_factory("CHAT"), memory=None)

    assert await orchestrateur.analyze_intent(
        "convertis ce fichier en PDF aujourd'hui") == "CONVERSION"


# --- Le fichier -----------------------------------------------------------------

def test_un_document_depose_garde_ses_octets_en_memoire_seulement(depot):
    contenu = _word("Devis Almadies")
    piece = depot.deposer("devis.docx", contenu)

    assert piece.octets_originaux() == contenu
    assert "contenu_base64" not in piece.to_dict(), "jamais renvoye a l'interface"


def test_un_fichier_illisible_ne_garde_rien_a_convertir(depot):
    piece = depot.deposer("casse.docx", b"PK pas un docx")

    assert piece.statut != "LU"
    assert piece.octets_originaux() is None


async def test_un_word_joint_devient_un_fichier_texte_telechargeable(depot):
    piece = depot.deposer("devis.docx", _word("Devis Almadies : 40 plaques BA13"))

    reponse = await module_chat._aiguiller(
        module_chat.ChatRequest(prompt="convertis ce fichier en texte", attachments=[piece.identifiant]),
        "CONVERSION")

    assert reponse["status"] == "success", reponse["response"]
    assert "1 sur 1" in reponse["response"]
    document = reponse["document"]
    assert document["statut"] == "SUCCESS" and document["url"].startswith("/media/rendered/")
    produit = RENDERED_DIR / document["url"].removeprefix("/media/rendered/")
    assert "40 plaques BA13" in produit.read_text(encoding="utf-8")
    produit.unlink()


async def test_le_fichier_recrit_pour_la_conversion_est_efface(depot, monkeypatch):
    piece = depot.deposer("devis.docx", _word("x"))
    vus = []

    class Registre:
        def executer(self, connecteur, capacite, **parametres):
            vus.append(Path(parametres["entree"]))
            assert vus[-1].read_bytes() == piece.octets_originaux()
            from core.actions.resultat import echec
            return echec(capacite, connecteur, "arret volontaire du test")

    monkeypatch.setattr(module_chat, "registre", Registre())
    reponse = await module_chat._convertir_les_pieces("convertis ce fichier en pdf", [piece.identifiant])

    assert reponse["status"] == "error"
    assert "arret volontaire du test" in reponse["response"], "l'echec est dit, avec sa raison"
    assert vus and not vus[0].exists(), "la copie temporaire ne reste pas sur le disque"


async def test_sans_piece_jointe_il_demande_le_fichier(depot):
    reponse = await module_chat._convertir_les_pieces("convertis ce fichier en pdf", [])

    assert reponse["status"] == "error"
    assert "Joins le fichier" in reponse["response"]


async def test_une_piece_perimee_ou_inconnue_est_dite(depot):
    reponse = await module_chat._convertir_les_pieces("convertis ce fichier en pdf", ["inconnue"])

    assert reponse["status"] == "error"
    assert "n'est plus disponible" in reponse["response"]
    assert reponse["documents"] == []


async def test_au_dela_du_maximum_le_reste_est_annonce(depot, monkeypatch):
    monkeypatch.setattr(module_chat, "PIECES_CONVERTIES_MAX", 1)
    ids = [depot.deposer(f"n{i}.docx", _word(f"n{i}")).identifiant for i in range(3)]

    reponse = await module_chat._convertir_les_pieces("convertis ces fichiers en texte", ids)

    assert "2 autre(s) fichier(s) non traite(s)" in reponse["response"]
    for document in reponse["documents"]:
        (RENDERED_DIR / document["url"].removeprefix("/media/rendered/")).unlink()


def test_l_interface_recoit_chaque_fichier_converti():
    resultat = {
        "document": {"statut": "SUCCESS", "url": "/media/rendered/a.pdf", "message": "a"},
        "documents": [
            {"statut": "SUCCESS", "url": "/media/rendered/a.pdf", "message": "a"},
            {"statut": "SUCCESS", "url": "/media/rendered/b.pdf", "message": "b"},
            {"statut": "FAILED", "url": None},
        ],
    }

    assert [d["url"] for d in _documents_produits(resultat)] == [
        "/media/rendered/a.pdf", "/media/rendered/b.pdf"]
    assert _documents_produits({"document": resultat["document"]})[0]["url"] == "/media/rendered/a.pdf"
