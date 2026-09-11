"""Dioumtoukay et le connecteur Case (DEC-0092) — un ordinateur Linux isolé,
jamais la machine du propriétaire.

Même discipline que `test_dioumtoukay_github.py` : la première section vérifie
que chaque action `ordinateur_*` extrait les bons champs et passe par le même
`connecteur.executer()`/`executer_confirmee()` que l'API le ferait — jamais un
raccourci qui contournerait la garde de `ordinateur_detruire`.

La seconde section (`TestContreUneVraieInstanceCase`, marquée `integration`)
fait tourner la boucle ENTIÈRE de Dioumtoukay contre une vraie instance Case
— la preuve exigée par la mission (§52) : « Do not bypass ARENA for proof. »
"""
import os

import pytest

from agents.dioumtoukay.dioumtoukay_agent import DioumtoukayAgent
from core.actions.resultat import ResultatAction, a_confirmer, succes
from core.connectors.case_computer import ConnecteurCaseComputer
from tools.atelier.atelier import Atelier


class ModeleScripte:
    def __init__(self, *reponses: str):
        self.reponses = list(reponses)

    async def is_available(self) -> bool:
        return True

    async def generate(self, prompt: str, system_prompt: str = None) -> str:
        return self.reponses.pop(0) if self.reponses else "ACTION: terminer\nCONTENU:\nfini\nFIN"


class FauxConnecteurCase:
    """Rend d'avance ce qu'on lui donne, garde une trace de chaque appel —
    jamais le vrai réseau."""

    def __init__(self, resultat: ResultatAction):
        self.resultat = resultat
        self.appels = []
        self.appels_confirmes = []

    def executer(self, capacite, **parametres):
        self.appels.append((capacite, parametres))
        return self.resultat

    def executer_confirmee(self, capacite, **parametres):
        self.appels_confirmes.append((capacite, parametres))
        return self.resultat


@pytest.fixture
def bac(tmp_path):
    return tmp_path


def agent(bac, reponses, connecteur_case=None):
    return DioumtoukayAgent(provider=ModeleScripte(*reponses), atelier=Atelier(racine=bac),
                            connecteur_case=connecteur_case)


class TestSansConnecteurBranche:
    @pytest.mark.asyncio
    async def test_le_dit_au_lieu_de_planter(self, bac):
        a = agent(bac, ["ACTION: ordinateur_lister"])

        resultat = await a.run("liste les ordinateurs Case")

        action = resultat["actions"][0]
        assert action["ok"] is False
        assert "pas branche" in action["message"].lower()


class TestChampsExtraits:
    """Chaque action passe les bons parametres a `connecteur.executer()` —
    la seule chose qui compte reellement pour la garde en aval."""

    @pytest.mark.asyncio
    async def test_ordinateur_creer_passe_le_nom(self, bac):
        connecteur = FauxConnecteurCase(succes("creer", "c1", "cree.", preuve="c1"))
        a = agent(bac, ["ACTION: ordinateur_creer\nNOM: test-linux"],
                 connecteur_case=connecteur)

        await a.run("cree un ordinateur")

        assert connecteur.appels == [("creer", {"nom": "test-linux"})]

    @pytest.mark.asyncio
    async def test_ordinateur_executer_passe_computer_id_et_commande(self, bac):
        connecteur = FauxConnecteurCase(succes(
            "executer_commande", "c1", "code 0", preuve="0", sortie="bonjour\n", erreur="", code=0))
        a = agent(bac, ["ACTION: ordinateur_executer\nCOMPUTER_ID: c1\nCOMMANDE: echo bonjour"],
                 connecteur_case=connecteur)

        await a.run("lance une commande")

        assert connecteur.appels == [
            ("executer_commande", {"computer_id": "c1", "commande": "echo bonjour"})]

    @pytest.mark.asyncio
    async def test_ordinateur_ecrire_fichier_passe_le_bloc_contenu(self, bac):
        connecteur = FauxConnecteurCase(succes("ecrire_fichier", "c1", "ecrit.", preuve="/x"))
        a = agent(bac, ["ACTION: ordinateur_ecrire_fichier\nCOMPUTER_ID: c1\n"
                       "CHEMIN: /home/agent/notes.txt\nCONTENU:\nARENA-OK\nFIN"],
                 connecteur_case=connecteur)

        await a.run("ecrit un fichier")

        assert connecteur.appels == [
            ("ecrire_fichier", {"computer_id": "c1", "chemin": "/home/agent/notes.txt",
                                "contenu": "ARENA-OK"})]

    @pytest.mark.asyncio
    async def test_ordinateur_naviguer_passe_l_url(self, bac):
        connecteur = FauxConnecteurCase(succes("naviguer", "c1", "navigue.", preuve="u"))
        a = agent(bac, ["ACTION: ordinateur_naviguer\nCOMPUTER_ID: c1\nURL: https://exemple.test"],
                 connecteur_case=connecteur)

        await a.run("navigue")

        assert connecteur.appels == [
            ("naviguer", {"computer_id": "c1", "url": "https://exemple.test"})]

    @pytest.mark.asyncio
    async def test_computer_id_manquant_est_refuse_sans_appeler_le_connecteur(self, bac):
        connecteur = FauxConnecteurCase(succes("etat", "c1", "ok", preuve="running"))
        a = agent(bac, ["ACTION: ordinateur_etat"], connecteur_case=connecteur)

        resultat = await a.run("etat")

        assert connecteur.appels == []
        assert "COMPUTER_ID" in resultat["actions"][0]["message"]


class TestDestructionExigeConfirmation:
    """La garde qui compte le plus, comme pour `ouvrir_pr` : `ordinateur_
    detruire` n'appelle JAMAIS `executer_confirmee` directement — un A_CONFIRMER
    du connecteur reste un A_CONFIRMER, Dioumtoukay ne le contourne pas."""

    @pytest.mark.asyncio
    async def test_rapporte_l_attente_de_confirmation_sans_pretendre_avoir_detruit(self, bac):
        connecteur = FauxConnecteurCase(a_confirmer(
            "detruire", "c1", "Pret : detruit c1. Risque HIGH. Rien n'est parti."))
        a = agent(bac, ["ACTION: ordinateur_detruire\nCOMPUTER_ID: c1"],
                 connecteur_case=connecteur)

        resultat = await a.run("detruis l'ordinateur c1")

        action = resultat["actions"][0]
        assert action["ok"] is True  # A_CONFIRMER est un succes PARTIEL, jamais cache
        assert "rien n'est parti" in action["message"].lower()
        assert connecteur.appels == [("detruire", {"computer_id": "c1"})]
        assert connecteur.appels_confirmes == []  # jamais appelee directement


class TestEchecReseau:
    @pytest.mark.asyncio
    async def test_une_exception_du_connecteur_devient_un_echec_nomme(self, bac):
        class ConnecteurQuiLeve:
            def executer(self, capacite, **parametres):
                raise ConnectionError("refuse")
        a = agent(bac, ["ACTION: ordinateur_lister"], connecteur_case=ConnecteurQuiLeve())

        resultat = await a.run("liste")

        action = resultat["actions"][0]
        assert action["ok"] is False
        assert "injoignable" in action["message"].lower()


class TestRenduBinaireLisible:
    """`capture_ecran` rend des octets PNG bruts — jamais recopies dans le
    texte du rapport, decrits par leur taille (voir `_via_case`)."""

    @pytest.mark.asyncio
    async def test_les_octets_png_deviennent_une_taille_pas_du_texte(self, bac):
        octets = b"\x89PNG\r\n\x1a\n" + b"x" * 100
        connecteur = FauxConnecteurCase(succes(
            "capture_ecran", "c1", "Capture recue.", preuve="c1", png=octets))
        a = agent(bac, ["ACTION: ordinateur_capture_ecran\nCOMPUTER_ID: c1"],
                 connecteur_case=connecteur)

        resultat = await a.run("capture l'ecran")

        sortie = resultat["actions"][0]["sortie"]
        assert "108 octet" in sortie  # 8 + 100
        assert b"\x89PNG" not in sortie.encode("utf-8", errors="ignore")


@pytest.mark.integration
class TestContreUneVraieInstanceCase:
    """La boucle ENTIERE de Dioumtoukay, contre une vraie instance Case —
    aucun double. Suppose `USMAN_CASE_URL`/`USMAN_CASE_TOKEN` deja pointes
    sur un `cased` reellement lance (voir docs/audits/case_audit.md pour la
    procedure de deploiement local suivie pendant l'audit) ; cette classe
    n'en demarre aucun."""

    @pytest.fixture(autouse=True)
    def _skip_sans_case_reel(self):
        if not os.getenv("USMAN_CASE_URL"):
            pytest.skip("USMAN_CASE_URL non configure : aucune instance Case reelle a joindre.")

    @pytest.mark.asyncio
    async def test_la_boucle_complete_atteint_reellement_case(self, tmp_path):
        """USER -> ARENA -> Dioumtoukay -> computer_runtime -> Case -> un
        VRAI cased. Cree pas d'image de bureau construite dans cette session
        (contrainte disque, voir l'audit) : la creation echoue reellement
        (ImageNotFound), et c'est exactement ce que ce test verifie — la
        chaine entiere porte l'echec reel de bout en bout, sans jamais le
        transformer en un succes simule."""
        a = agent(tmp_path, [
            "ACTION: ordinateur_lister",
            "ACTION: ordinateur_creer\nNOM: arena-e2e-test",
            "ACTION: terminer\nCONTENU:\nfini\nFIN",
        ], connecteur_case=ConnecteurCaseComputer())

        resultat = await a.run("liste les ordinateurs Case puis essaie d'en creer un")

        lister = resultat["actions"][0]
        creer = resultat["actions"][1]
        assert lister["ok"] is True, lister["message"]
        assert creer["ok"] is False, "attendu : echec reel (aucune image de bureau construite ici)"
        assert "ImageNotFound" in creer["message"] or "create_failed" in creer["message"]
