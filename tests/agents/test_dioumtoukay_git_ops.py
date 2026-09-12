"""Dioumtoukay et les opérations git mutantes (DEC-0094, mission ARENA x
GITGUI, second passage) — via la boucle COMPLÈTE de l'agent, jamais un appel
direct qui contournerait le parsing réel des actions (même discipline que
`test_dioumtoukay_git.py`, DEC-0093).
"""
import subprocess
from pathlib import Path

import pytest

from agents.dioumtoukay.dioumtoukay_agent import DioumtoukayAgent
from tools.atelier.atelier import Atelier


def _git(racine: Path, *arguments: str) -> None:
    subprocess.run(["git", *arguments], cwd=str(racine), capture_output=True,
                   text=True, check=True)


class ModeleScripte:
    def __init__(self, *reponses: str):
        self.reponses = list(reponses)

    async def is_available(self) -> bool:
        return True

    async def generate(self, prompt: str, system_prompt: str = None) -> str:
        return self.reponses.pop(0) if self.reponses else "ACTION: terminer\nCONTENU:\nfini\nFIN"


@pytest.fixture
def depot(tmp_path) -> Path:
    racine = tmp_path / "depot"
    racine.mkdir()
    _git(racine, "init", "-q", "-b", "main")
    _git(racine, "config", "user.email", "test@test.local")
    _git(racine, "config", "user.name", "test")
    (racine / "a.txt").write_text("contenu initial\n", encoding="utf-8")
    _git(racine, "add", "-A")
    _git(racine, "commit", "-q", "-m", "initial")
    return racine


def agent(depot: Path, *reponses: str) -> DioumtoukayAgent:
    return DioumtoukayAgent(provider=ModeleScripte(*reponses), atelier=Atelier(racine=depot))


@pytest.mark.asyncio
class TestStagerEtCommettreViaLaBoucle:
    async def test_stager_puis_commettre_deux_tours(self, depot):
        (depot / "a.txt").write_text("modifie\n", encoding="utf-8")
        a = agent(
            depot,
            "ACTION: git_stager\nCHEMIN: a.txt",
            "ACTION: git_commettre\nCONTENU:\ncorrige a.txt\nFIN",
        )
        resultat = await a.run("indexe et commite a.txt")

        stage_action, commit_action = resultat["actions"][0], resultat["actions"][1]
        assert stage_action["ok"] is True
        assert commit_action["ok"] is True

        log = subprocess.run(["git", "log", "--oneline"], cwd=str(depot),
                             capture_output=True, text=True, check=True).stdout
        assert len(log.splitlines()) == 2

    async def test_identifiant_operation_repete_ne_recommite_pas(self, depot):
        (depot / "a.txt").write_text("modifie\n", encoding="utf-8")
        atelier = Atelier(racine=depot)
        atelier.git_stager(["a.txt"])

        a = DioumtoukayAgent(
            provider=ModeleScripte(
                "ACTION: git_commettre\nIDENTIFIANT_OPERATION: op-boucle-1\nCONTENU:\nmodif\nFIN"),
            atelier=atelier)
        await a.run("commite avec un identifiant")

        # Un second passage, meme identifiant : ne doit pas recreer un commit.
        a2 = DioumtoukayAgent(
            provider=ModeleScripte(
                "ACTION: git_commettre\nIDENTIFIANT_OPERATION: op-boucle-1\nCONTENU:\nmodif\nFIN"),
            atelier=atelier)
        resultat2 = await a2.run("recommence, meme identifiant")

        action2 = resultat2["actions"][0]
        assert action2["ok"] is True
        log = subprocess.run(["git", "log", "--oneline"], cwd=str(depot),
                             capture_output=True, text=True, check=True).stdout
        assert len(log.splitlines()) == 2  # initial + modif, jamais un troisieme

    async def test_commettre_sans_message_est_refuse(self, depot):
        (depot / "a.txt").write_text("x\n", encoding="utf-8")
        a = agent(depot, "ACTION: git_commettre\nDOSSIER: .")
        resultat = await a.run("commite sans message")
        action = resultat["actions"][0]
        assert action["ok"] is False
        assert "message" in action["message"].lower()


@pytest.mark.asyncio
class TestBranchesViaLaBoucle:
    async def test_creer_branche_et_basculer(self, depot):
        a = agent(depot, "ACTION: git_branche_creer\nNOM: correctif-x\nBASCULER: oui")
        resultat = await a.run("cree une branche et bascule dessus")
        action = resultat["actions"][0]
        assert action["ok"] is True

        atelier2 = Atelier(racine=depot)
        etat = atelier2.git_statut()
        assert etat.donnees["branche"] == "correctif-x"


@pytest.mark.asyncio
class TestConflitViaLaBoucle:
    async def test_fusion_en_conflit_puis_resolution_puis_continuer(self, depot):
        _git(depot, "checkout", "-q", "-b", "branche-a")
        (depot / "a.txt").write_text("version A\n", encoding="utf-8")
        _git(depot, "commit", "-q", "-am", "a")
        _git(depot, "checkout", "-q", "main")
        (depot / "a.txt").write_text("version B\n", encoding="utf-8")
        _git(depot, "commit", "-q", "-am", "b")

        atelier = Atelier(racine=depot)
        a1 = DioumtoukayAgent(provider=ModeleScripte("ACTION: git_fusionner\nBRANCHE: branche-a"), atelier=atelier)
        resultat1 = await a1.run("fusionne branche-a")
        assert resultat1["actions"][0]["ok"] is False

        a2 = DioumtoukayAgent(provider=ModeleScripte("ACTION: git_conflit_lire\nCHEMIN: a.txt"), atelier=atelier)
        resultat2 = await a2.run("montre le conflit")
        assert resultat2["actions"][0]["ok"] is True

        (depot / "a.txt").write_text("resolu\n", encoding="utf-8")
        a3 = DioumtoukayAgent(
            provider=ModeleScripte("ACTION: git_stager\nCHEMIN: a.txt", "ACTION: git_continuer\nDOSSIER: ."),
            atelier=atelier)
        resultat3 = await a3.run("resous et continue")
        assert resultat3["actions"][0]["ok"] is True
        assert resultat3["actions"][1]["ok"] is True

        etat = atelier.git_statut()
        assert etat.donnees["operation"] == "PROPRE"


@pytest.mark.asyncio
class TestPousserJamaisForceNu:
    async def test_champ_force_sans_suffixe_est_ignore(self, depot):
        # Seul FORCE_AVEC_BAIL existe dans le vocabulaire de champs reconnu ;
        # un champ "FORCE:" seul n'est simplement pas un champ reconnu par le
        # modele — jamais un mode cache pour forcer.
        (depot / "a.txt").write_text("x\n", encoding="utf-8")
        a = agent(depot, "ACTION: git_pousser\nDISTANT: origin\nFORCE: oui")
        resultat = await a.run("pousse")
        action = resultat["actions"][0]
        # Rend un echec nomme (pas de distant configure) — jamais une
        # tentative de --force nu, quel que soit ce que le modele a ecrit.
        assert action["ok"] is False
