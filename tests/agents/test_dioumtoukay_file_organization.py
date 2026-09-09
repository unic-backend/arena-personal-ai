"""Dioumtoukay classe des fichiers via le connecteur `file_organization`
(DEC-0075) — le chemin réel par lequel n'importe quel modèle atteint la
capacité, sans savoir qu'un `Atelier` tourne derrière.

Un test utilise le VRAI connecteur, aucun mock : c'est la preuve que le
chemin USER -> MODEL -> ROUTER -> FILE_ORGANIZATION TOOL -> Atelier ->
ARTIFACT fonctionne réellement, sur disque, pas seulement dans le texte
d'une réponse.
"""
import pytest

from agents.dioumtoukay.dioumtoukay_agent import DioumtoukayAgent
from core.actions.resultat import ResultatAction, echec, succes
from core.connectors.file_organization import ConnecteurFileOrganization
from tools.atelier import Atelier


class ModeleScripte:
    def __init__(self, *reponses: str):
        self.reponses = list(reponses)

    async def is_available(self) -> bool:
        return True

    async def generate(self, prompt: str, system_prompt: str = None) -> str:
        return self.reponses.pop(0) if self.reponses else "ACTION: terminer\nCONTENU:\nfini\nFIN"


class FauxConnecteurFileOrganization:
    def __init__(self, resultat: ResultatAction):
        self.resultat = resultat
        self.appels = []

    def executer(self, capacite, **parametres):
        self.appels.append((capacite, parametres))
        return self.resultat


def agent(bac, reponses, connecteur_file_organization=None):
    return DioumtoukayAgent(provider=ModeleScripte(*reponses), atelier=Atelier(racine=bac),
                            connecteur_file_organization=connecteur_file_organization)


class TestBoucleReelle:
    """Aucun mock : le vrai connecteur, le vrai Atelier, de vrais fichiers."""

    @pytest.mark.asyncio
    async def test_inspecter_puis_planifier_puis_appliquer_puis_annuler(self, tmp_path):
        (tmp_path / "IMG_2048.jpg").write_bytes(b"x")
        connecteur = ConnecteurFileOrganization(atelier=Atelier(racine=tmp_path))

        a = agent(tmp_path, [
            "ACTION: organiser_inspecter\nDOSSIER: .",
            "ACTION: organiser_planifier\nDOSSIER: .\nCONTENU:\n"
            "creer_dossier|Images||photos a trier\n"
            "deplacer|IMG_2048.jpg|Images/clouds.jpg|photo de nuages\n"
            "FIN",
            "ACTION: terminer\nCONTENU:\nplan propose, en attente de confirmation\nFIN",
        ], connecteur_file_organization=connecteur)

        resultat = await a.run("range mes photos")

        inspection = resultat["actions"][0]
        assert inspection["ok"] is True
        assert "IMG_2048.jpg" in inspection["sortie"]

        planification = resultat["actions"][1]
        assert planification["ok"] is True
        assert "VALIDATED" in planification["sortie"]

        # Rien n'a ete deplace : planifier ne mute jamais.
        assert (tmp_path / "IMG_2048.jpg").is_file()
        assert not (tmp_path / "Images").exists()

        # Le plan_id se retrouve dans le detail rapporte par le connecteur.
        import re
        plan_id = re.search(r"([0-9a-f]{32})", planification["sortie"]).group(1)

        # Confirme separement, comme le proprietaire le ferait reellement.
        applique = connecteur.executer_confirmee("appliquer", plan_id=plan_id)
        assert applique.statut.value == "SUCCESS"
        assert (tmp_path / "Images" / "clouds.jpg").is_file()

        annule = connecteur.executer_confirmee("annuler", plan_id=plan_id)
        assert annule.statut.value == "SUCCESS"
        assert (tmp_path / "IMG_2048.jpg").is_file()


class TestChampsEtGardes:
    @pytest.mark.asyncio
    async def test_planifier_sans_bloc_contenu_natteint_pas_le_connecteur(self, tmp_path):
        connecteur = FauxConnecteurFileOrganization(succes("x", "x", "ne doit jamais etre lu", preuve="x"))
        a = agent(tmp_path, [
            "ACTION: organiser_planifier\nDOSSIER: .",
            "ACTION: terminer\nCONTENU:\nfini\nFIN",
        ], connecteur_file_organization=connecteur)

        resultat = await a.run("range mes fichiers")

        assert connecteur.appels == []
        assert resultat["actions"][0]["ok"] is False

    @pytest.mark.asyncio
    async def test_appliquer_sans_plan_id_natteint_pas_le_connecteur(self, tmp_path):
        connecteur = FauxConnecteurFileOrganization(succes("x", "x", "ne doit jamais etre lu", preuve="x"))
        a = agent(tmp_path, [
            "ACTION: organiser_appliquer",
            "ACTION: terminer\nCONTENU:\nfini\nFIN",
        ], connecteur_file_organization=connecteur)

        await a.run("applique le plan")

        assert connecteur.appels == []

    @pytest.mark.asyncio
    async def test_confirmer_suppression_oui_est_transmis(self, tmp_path):
        connecteur = FauxConnecteurFileOrganization(succes("appliquer", "x", "ok", preuve="p"))
        a = agent(tmp_path, [
            "ACTION: organiser_appliquer\nPLAN_ID: abc123\nCONFIRMER_SUPPRESSION: oui",
            "ACTION: terminer\nCONTENU:\nfini\nFIN",
        ], connecteur_file_organization=connecteur)

        await a.run("applique et supprime")

        assert connecteur.appels == [
            ("appliquer", {"plan_id": "abc123", "confirmer_suppression": True})]

    @pytest.mark.asyncio
    async def test_sans_connecteur_branche_est_rapporte_pas_devine(self, tmp_path):
        a = agent(tmp_path, [
            "ACTION: organiser_inspecter\nDOSSIER: .",
            "ACTION: terminer\nCONTENU:\nfini\nFIN",
        ], connecteur_file_organization=None)

        resultat = await a.run("range mes fichiers")

        assert "n'est pas branche" in resultat["actions"][0]["message"]

    @pytest.mark.asyncio
    async def test_un_echec_du_connecteur_est_rapporte_pas_masque(self, tmp_path):
        connecteur = FauxConnecteurFileOrganization(echec("planifier", "x", "plan refuse : source introuvable"))
        a = agent(tmp_path, [
            "ACTION: organiser_planifier\nDOSSIER: .\nCONTENU:\ndeplacer|x.txt|y.txt|\nFIN",
            "ACTION: terminer\nCONTENU:\nfini\nFIN",
        ], connecteur_file_organization=connecteur)

        resultat = await a.run("range")

        rendu = resultat["actions"][0]
        assert rendu["ok"] is False
        assert "source introuvable" in rendu["message"]

    def test_lire_operations_ligne_pipe_delimitee(self):
        operations = DioumtoukayAgent._lire_operations(
            "deplacer|a.txt|b.txt|une raison\ncreer_dossier|Nouveau\nsupprimer|c.txt")
        assert operations == [
            {"type": "deplacer", "source": "a.txt", "destination": "b.txt", "raison": "une raison"},
            {"type": "creer_dossier", "source": "Nouveau", "destination": "", "raison": ""},
            {"type": "supprimer", "source": "c.txt", "destination": "", "raison": ""},
        ]

    def test_lire_operations_ligne_illisible_rend_none(self):
        assert DioumtoukayAgent._lire_operations("juste-un-mot-sans-barre") is None
        assert DioumtoukayAgent._lire_operations("") is None
