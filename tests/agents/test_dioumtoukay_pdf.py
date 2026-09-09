"""Dioumtoukay manipule des PDF via le connecteur `pdf` (DEC-0076) — le
chemin réel par lequel n'importe quel modèle atteint la capacité.

Le premier test reproduit le scénario de bout en bout de la mission
(section 25) mot pour mot : « Prends ces 4 documents, rassemble-les... »,
avec le VRAI connecteur, aucun mock, vérifié sur le fichier réel produit.
"""
import pytest

from agents.dioumtoukay.dioumtoukay_agent import DioumtoukayAgent
from core.actions.resultat import ResultatAction, echec, succes
from core.connectors.pdf import ConnecteurPdf
from tools.atelier import Atelier


class ModeleScripte:
    def __init__(self, *reponses: str):
        self.reponses = list(reponses)

    async def is_available(self) -> bool:
        return True

    async def generate(self, prompt: str, system_prompt: str = None) -> str:
        return self.reponses.pop(0) if self.reponses else "ACTION: terminer\nCONTENU:\nfini\nFIN"


class FauxConnecteurPdf:
    def __init__(self, resultat: ResultatAction):
        self.resultat = resultat
        self.appels = []

    def executer(self, capacite, **parametres):
        self.appels.append((capacite, parametres))
        return self.resultat


def agent(bac, reponses, connecteur_pdf=None):
    return DioumtoukayAgent(provider=ModeleScripte(*reponses), atelier=Atelier(racine=bac),
                            connecteur_pdf=connecteur_pdf)


def _pdf(tmp_path, nom, titre):
    import weasyprint
    chemin = tmp_path / f"{nom}.pdf"
    weasyprint.HTML(string=f"<h1>{titre}</h1><p>contenu {nom}</p>").write_pdf(chemin)
    return chemin


class TestScenarioDeLaMission:
    """Section 25 de la mission, mot pour mot : quatre documents, un ordre
    précis, un artefact final. Aucun mock."""

    @pytest.mark.asyncio
    async def test_rassembler_quatre_documents_dans_l_ordre_demande(self, tmp_path):
        for nom, titre in [("contrat", "Contrat"), ("devis", "Devis"),
                           ("facture", "Facture"), ("plans", "Plans")]:
            _pdf(tmp_path, nom, titre)

        connecteur = ConnecteurPdf(dossier=tmp_path)
        a = agent(tmp_path, [
            f"ACTION: pdf_fusionner\nTITRE: Dossier complet\nCONTENU:\n"
            f"{tmp_path}/contrat.pdf\n{tmp_path}/devis.pdf\n{tmp_path}/facture.pdf\n{tmp_path}/plans.pdf\nFIN",
            "ACTION: terminer\nCONTENU:\ndossier assemblé dans l'ordre demandé\nFIN",
        ], connecteur_pdf=connecteur)

        resultat = await a.run(
            "Prends ces 4 documents, rassemble-les dans un seul document, garde l'ordre "
            "contrat, devis, facture, plans. Puis donne-moi le document final.")

        rendu = resultat["actions"][0]
        assert rendu["ok"] is True, rendu["message"]

        from pypdf import PdfReader
        fichiers = list((tmp_path / "documents").glob("*.pdf"))
        assert len(fichiers) == 1
        pages = PdfReader(fichiers[0]).pages
        assert len(pages) == 4
        ordre_reel = [p.extract_text() for p in pages]
        assert "Contrat" in ordre_reel[0]
        assert "Devis" in ordre_reel[1]
        assert "Facture" in ordre_reel[2]
        assert "Plans" in ordre_reel[3]


class TestChampsEtGardes:
    @pytest.mark.asyncio
    async def test_fusionner_sans_bloc_contenu_natteint_pas_le_connecteur(self, tmp_path):
        connecteur = FauxConnecteurPdf(succes("x", "x", "ne doit jamais etre lu", preuve="x"))
        a = agent(tmp_path, [
            "ACTION: pdf_fusionner\nTITRE: X",
            "ACTION: terminer\nCONTENU:\nfini\nFIN",
        ], connecteur_pdf=connecteur)

        await a.run("fusionne des PDF")

        assert connecteur.appels == []

    @pytest.mark.asyncio
    async def test_pages_operation_inconnue_natteint_pas_le_connecteur(self, tmp_path):
        connecteur = FauxConnecteurPdf(succes("x", "x", "ne doit jamais etre lu", preuve="x"))
        a = agent(tmp_path, [
            "ACTION: pdf_pages\nCHEMIN: a.pdf\nOPERATION: formater\nPAGES: 0",
            "ACTION: terminer\nCONTENU:\nfini\nFIN",
        ], connecteur_pdf=connecteur)

        await a.run("modifie les pages")

        assert connecteur.appels == []

    @pytest.mark.asyncio
    async def test_pages_index_a_partir_de_0_transmis_tel_quel(self, tmp_path):
        connecteur = FauxConnecteurPdf(succes("extraire_pages", "x", "ok", preuve="p"))
        a = agent(tmp_path, [
            "ACTION: pdf_pages\nCHEMIN: a.pdf\nOPERATION: extraire_pages\nPAGES: 0,2,4",
            "ACTION: terminer\nCONTENU:\nfini\nFIN",
        ], connecteur_pdf=connecteur)

        await a.run("extrais des pages")

        assert connecteur.appels == [("extraire_pages", {"fichier": "a.pdf", "pages": [0, 2, 4]})]

    @pytest.mark.asyncio
    async def test_pivoter_transmet_degres(self, tmp_path):
        connecteur = FauxConnecteurPdf(succes("pivoter_pages", "x", "ok", preuve="p"))
        a = agent(tmp_path, [
            "ACTION: pdf_pages\nCHEMIN: a.pdf\nOPERATION: pivoter_pages\nPAGES: 0\nDEGRES: 180",
            "ACTION: terminer\nCONTENU:\nfini\nFIN",
        ], connecteur_pdf=connecteur)

        await a.run("pivote une page")

        assert connecteur.appels == [
            ("pivoter_pages", {"fichier": "a.pdf", "pages": [0], "degres": 180})]

    @pytest.mark.asyncio
    async def test_sans_connecteur_branche_est_rapporte_pas_devine(self, tmp_path):
        a = agent(tmp_path, [
            "ACTION: pdf_extraire_texte\nCHEMIN: a.pdf",
            "ACTION: terminer\nCONTENU:\nfini\nFIN",
        ], connecteur_pdf=None)

        resultat = await a.run("lis ce pdf")

        assert "n'est pas branche" in resultat["actions"][0]["message"]

    @pytest.mark.asyncio
    async def test_un_echec_du_connecteur_est_rapporte_pas_masque(self, tmp_path):
        connecteur = FauxConnecteurPdf(echec("fusionner", "x", "un fichier de la liste est introuvable"))
        a = agent(tmp_path, [
            "ACTION: pdf_fusionner\nCONTENU:\na.pdf\nb.pdf\nFIN",
            "ACTION: terminer\nCONTENU:\nfini\nFIN",
        ], connecteur_pdf=connecteur)

        resultat = await a.run("fusionne")

        rendu = resultat["actions"][0]
        assert rendu["ok"] is False
        assert "introuvable" in rendu["message"]

    def test_lire_pages_liste_valide(self):
        assert DioumtoukayAgent._lire_pages("0,2, 4") == [0, 2, 4]

    def test_lire_pages_invalide_rend_none(self):
        assert DioumtoukayAgent._lire_pages("zero,un") is None
        assert DioumtoukayAgent._lire_pages("") is None

    def test_lire_fichiers_une_ligne_par_chemin(self):
        assert DioumtoukayAgent._lire_fichiers("a.pdf\nb.pdf\n\nc.pdf") == ["a.pdf", "b.pdf", "c.pdf"]
        assert DioumtoukayAgent._lire_fichiers("") is None
