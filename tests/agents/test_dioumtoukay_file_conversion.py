"""Dioumtoukay convertit un fichier via le connecteur `file_conversion`
(DEC-0074) — le chemin réel par lequel n'importe quel modèle atteint la
capacité, sans savoir qu'un moteur en particulier tourne derrière.

Un test utilise le VRAI connecteur (`ConnecteurFileConversion`, sans mock) :
c'est la garantie que la mission demande explicitement — que le chemin
USER -> MODEL -> ROUTER -> FILE_CONVERSION TOOL -> ENGINE -> ARTIFACT
fonctionne réellement, pas seulement que Dioumtoukay sait construire l'appel.
"""
import pytest

from agents.dioumtoukay.dioumtoukay_agent import DioumtoukayAgent
from core.actions.resultat import ResultatAction, echec, succes
from core.connectors.file_conversion import ConnecteurFileConversion
from tools.atelier import Atelier


class ModeleScripte:
    def __init__(self, *reponses: str):
        self.reponses = list(reponses)

    async def is_available(self) -> bool:
        return True

    async def generate(self, prompt: str, system_prompt: str = None) -> str:
        return self.reponses.pop(0) if self.reponses else "ACTION: terminer\nCONTENU:\nfini\nFIN"


class FauxConnecteurFileConversion:
    def __init__(self, resultat: ResultatAction):
        self.resultat = resultat
        self.appels = []

    def executer(self, capacite, **parametres):
        self.appels.append((capacite, parametres))
        return self.resultat


def agent(bac, reponses, connecteur_file_conversion=None):
    return DioumtoukayAgent(provider=ModeleScripte(*reponses), atelier=Atelier(racine=bac),
                            connecteur_file_conversion=connecteur_file_conversion)


class TestConversionReelle:
    """Aucun mock : le vrai connecteur, le vrai LibreOffice, un vrai fichier."""

    @pytest.mark.asyncio
    async def test_dioumtoukay_convertit_reellement_un_fichier(self, tmp_path):
        from docx import Document
        d = Document()
        d.add_paragraph("Contenu réel, converti par Dioumtoukay.")
        source = tmp_path / "note.docx"
        d.save(source)

        connecteur = ConnecteurFileConversion(dossier=tmp_path)
        a = agent(tmp_path, [
            f"ACTION: convertir\nCHEMIN: {source}\nFORMAT: pdf",
            "ACTION: terminer\nCONTENU:\nconverti\nFIN",
        ], connecteur_file_conversion=connecteur)

        resultat = await a.run("convertis ce fichier en pdf")

        rendu = resultat["actions"][0]
        assert rendu["ok"] is True, rendu["message"]
        assert "libreoffice" in rendu["sortie"]
        # Le fichier annonce existe vraiment, et c'est un PDF réel.
        from pypdf import PdfReader
        fichiers_pdf = list((tmp_path / "conversions").glob("*.pdf"))
        assert len(fichiers_pdf) == 1, "aucun PDF réel écrit par la conversion"
        assert PdfReader(fichiers_pdf[0]).pages


class TestChampsEtGardes:
    @pytest.mark.asyncio
    async def test_sans_chemin_ou_format_rien_natteint_le_connecteur(self, tmp_path):
        connecteur = FauxConnecteurFileConversion(succes("x", "x", "ne doit jamais etre lu", preuve="x"))
        a = agent(tmp_path, [
            "ACTION: convertir\nFORMAT: pdf",
            "ACTION: terminer\nCONTENU:\nfini\nFIN",
        ], connecteur_file_conversion=connecteur)

        resultat = await a.run("convertis")

        assert connecteur.appels == []
        assert resultat["actions"][0]["ok"] is False

    @pytest.mark.asyncio
    async def test_sans_connecteur_branche_est_rapporte_pas_devine(self, tmp_path):
        a = agent(tmp_path, [
            "ACTION: convertir\nCHEMIN: x.docx\nFORMAT: pdf",
            "ACTION: terminer\nCONTENU:\nfini\nFIN",
        ], connecteur_file_conversion=None)

        resultat = await a.run("convertis ce fichier")

        assert "n'est pas branche" in resultat["actions"][0]["message"]

    @pytest.mark.asyncio
    async def test_un_echec_du_connecteur_est_rapporte_pas_masque(self, tmp_path):
        connecteur = FauxConnecteurFileConversion(echec("convertir", "file_conversion", "format refusé"))
        a = agent(tmp_path, [
            "ACTION: convertir\nCHEMIN: x.docx\nFORMAT: epub",
            "ACTION: terminer\nCONTENU:\nfini\nFIN",
        ], connecteur_file_conversion=connecteur)

        resultat = await a.run("convertis")

        rendu = resultat["actions"][0]
        assert rendu["ok"] is False
        assert "format refusé" in rendu["message"]

    @pytest.mark.asyncio
    async def test_les_bons_parametres_partent_vers_le_connecteur(self, tmp_path):
        connecteur = FauxConnecteurFileConversion(succes("convertir", "x", "ok", preuve="p"))
        a = agent(tmp_path, [
            "ACTION: convertir\nCHEMIN: rapport.pdf\nFORMAT: docx",
            "ACTION: terminer\nCONTENU:\nfini\nFIN",
        ], connecteur_file_conversion=connecteur)

        await a.run("convertis rapport.pdf en docx")

        assert connecteur.appels == [
            ("convertir", {"entree": "rapport.pdf", "format_cible": "docx"})]
